"""V1 Project management API endpoints.

Provides CRUD operations for emClarity projects using UUID-based identifiers.
Projects are backed by on-disk directory structures following emClarity conventions.

The in-memory registry is persisted to ~/.emclarity/projects.json so that
project IDs remain valid across backend restarts.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.models.project import ProjectState, TiltSeries
from backend.services.project_service import ProjectService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects-v1"])

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_REGISTRY_DIR = Path.home() / ".emclarity"
_REGISTRY_FILE = _REGISTRY_DIR / "projects.json"


def _save_registry() -> None:
    """Persist the in-memory project registry to disk."""
    try:
        _REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        data = {k: v.model_dump(mode="json") for k, v in _projects.items()}
        _REGISTRY_FILE.write_text(json.dumps(data, indent=2))
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not persist project registry: %s", exc)


def _load_registry() -> None:
    """Load the project registry from disk (called once at module import)."""
    if not _REGISTRY_FILE.exists():
        return
    try:
        raw = json.loads(_REGISTRY_FILE.read_text())
        for project_id, record_data in raw.items():
            try:
                _projects[project_id] = _ProjectRecord(**record_data)
            except Exception as exc:  # noqa: BLE001
                log.warning("Skipping corrupt registry entry %s: %s", project_id, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load project registry from %s: %s", _REGISTRY_FILE, exc)


# ---------------------------------------------------------------------------
# In-memory project registry (keyed by UUID string)
# ---------------------------------------------------------------------------

_projects: dict[str, "_ProjectRecord"] = {}
_project_service = ProjectService()

# Load persisted registry at startup
_load_registry()


class _ProjectRecord(BaseModel):
    """Internal record stored in memory for each created project."""

    id: str
    name: str
    directory: str
    state: ProjectState
    parameters: dict[str, Any]
    current_cycle: int = 0


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    """Payload for creating a new project."""

    name: str = Field(..., description="Human-readable project name")
    directory: str = Field(..., description="Absolute path to the project directory on disk")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Initial emClarity parameters",
    )


class LoadProjectRequest(BaseModel):
    """Payload for loading an existing project by its filesystem path."""

    directory: str = Field(..., description="Absolute path to an existing emClarity project")
    name: str | None = Field(None, description="Override the project name (defaults to dir name)")


class ProjectResponse(BaseModel):
    """Response body for project endpoints."""

    id: str
    name: str
    directory: str
    state: str
    parameters: dict[str, Any]
    current_cycle: int = 0


class ProjectStatisticsResponse(BaseModel):
    """Response body for the project statistics endpoint."""

    project_id: str
    particle_count: int | None = None
    resolution_angstrom: float | None = None
    tilt_series_count: int


class TiltSeriesListResponse(BaseModel):
    """Response body for tilt series listing."""

    tilt_series: list[TiltSeries]


# ---------------------------------------------------------------------------
# Path safety helpers
# ---------------------------------------------------------------------------

# Patterns that indicate path traversal or clearly unsafe inputs
_UNSAFE_PATH_PATTERNS = re.compile(r"\.\.|/etc/|/proc/|/sys/|/dev/")


def _validate_project_path(directory: str) -> Path:
    """Return a resolved absolute path after basic safety checks.

    Raises HTTPException 400 if the path looks dangerous or non-absolute.
    """
    if not directory or not directory.strip():
        raise HTTPException(status_code=400, detail="Directory path must not be empty")

    if _UNSAFE_PATH_PATTERNS.search(directory):
        raise HTTPException(
            status_code=400,
            detail="Directory path contains unsafe components",
        )

    path = Path(directory)
    if not path.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="Directory path must be absolute (start with /)",
        )

    return path


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def _count_particles(project_dir: Path) -> int | None:
    """Count particles from .coords files in the recon/ directory.

    Each line in a .coords file represents one particle coordinate triplet.
    Returns None if no .coords files are found.
    """
    recon_dir = project_dir / "recon"
    if not recon_dir.exists():
        return None

    total = 0
    found_any = False
    for coords_file in recon_dir.glob("*.coords"):
        try:
            lines = coords_file.read_text().splitlines()
            # Count non-empty, non-comment lines
            count = sum(
                1 for line in lines
                if line.strip() and not line.strip().startswith("#")
            )
            total += count
            found_any = True
        except OSError:
            continue

    return total if found_any else None


def _detect_best_resolution(project_dir: Path) -> float | None:
    """Parse FSC text files to find the best resolution achieved.

    Only reads files matching the canonical emClarity FSC naming pattern
    (*_fsc_GLD.txt) and extracts the resolution from the last data line.
    The resolution line must follow the format:
        <spatial_frequency> <FSC_value>
    where spatial_frequency is in 1/Å units (reciprocal space).

    Returns the resolution in Ångströms, or None if not determinable.
    """
    fsc_dir = project_dir / "FSC"
    if not fsc_dir.exists():
        return None

    best_angstrom: float | None = None

    # Only match the canonical FSC output files; ignore PDFs and other outputs
    fsc_pattern = re.compile(r"^[\w\-]+_fsc_GLD\.txt$")

    for fsc_file in fsc_dir.glob("*_fsc_GLD.txt"):
        if not fsc_pattern.match(fsc_file.name):
            continue
        try:
            lines = fsc_file.read_text().splitlines()
        except OSError:
            continue

        # Each line: <1/Å_frequency>  <FSC_value>
        # The FSC=0.143 threshold marks the resolution limit.
        # We find the last line where FSC > 0.143 (or the highest freq where FSC≥0.143).
        resolution_freq: float | None = None
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                freq = float(parts[0])
                fsc_val = float(parts[1])
            except ValueError:
                continue
            # freq must be a realistic reciprocal-space value (0 < freq ≤ 0.5 1/Å)
            if freq <= 0 or freq > 0.5:
                continue
            if fsc_val >= 0.143:
                resolution_freq = freq

        if resolution_freq is not None and resolution_freq > 0:
            angstrom = 1.0 / resolution_freq
            if best_angstrom is None or angstrom < best_angstrom:
                best_angstrom = angstrom

    return round(best_angstrom, 2) if best_angstrom is not None else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(request: CreateProjectRequest) -> ProjectResponse:
    """Create a new emClarity project.

    Creates the standard directory structure on disk and registers the
    project in memory with an UNINITIALIZED state.
    """
    _validate_project_path(request.directory)

    # Create the directory structure on disk
    _project_service.create_project(name=request.name, path=request.directory)

    project_id = str(uuid.uuid4())
    record = _ProjectRecord(
        id=project_id,
        name=request.name,
        directory=request.directory,
        state=ProjectState.UNINITIALIZED,
        parameters=request.parameters,
        current_cycle=0,
    )
    _projects[project_id] = record
    _save_registry()

    return ProjectResponse(
        id=project_id,
        name=record.name,
        directory=record.directory,
        state=record.state.value,
        parameters=record.parameters,
        current_cycle=record.current_cycle,
    )


@router.post("/load", status_code=200, response_model=ProjectResponse)
async def load_project(request: LoadProjectRequest) -> ProjectResponse:
    """Load an existing emClarity project by filesystem path.

    Inspects the directory structure to determine the pipeline state.
    Registers the project in the registry and returns a stable project ID.

    Security: only absolute paths without traversal components are accepted.
    """
    project_path = _validate_project_path(request.directory)

    if not project_path.exists() or not project_path.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Directory not found: {request.directory}",
        )

    # Check if this directory is already registered (by resolved path)
    resolved = str(project_path.resolve())
    for existing_id, existing_record in _projects.items():
        if Path(existing_record.directory).resolve() == Path(resolved):
            return ProjectResponse(
                id=existing_id,
                name=existing_record.name,
                directory=existing_record.directory,
                state=existing_record.state.value,
                parameters=existing_record.parameters,
                current_cycle=existing_record.current_cycle,
            )

    # Load project state from disk
    try:
        project = _project_service.load_project(request.directory)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    project_name = request.name or project.name
    project_id = str(uuid.uuid4())
    record = _ProjectRecord(
        id=project_id,
        name=project_name,
        directory=project.path,
        state=project.state,
        parameters={},
        current_cycle=project.current_cycle,
    )
    _projects[project_id] = record
    _save_registry()

    return ProjectResponse(
        id=project_id,
        name=record.name,
        directory=record.directory,
        state=record.state.value,
        parameters=record.parameters,
        current_cycle=record.current_cycle,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str) -> ProjectResponse:
    """Return the current state and metadata for a project.

    Returns 404 if the project ID is not found.
    """
    record = _projects.get(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    return ProjectResponse(
        id=record.id,
        name=record.name,
        directory=record.directory,
        state=record.state.value,
        parameters=record.parameters,
        current_cycle=record.current_cycle,
    )


@router.get("/{project_id}/statistics", response_model=ProjectStatisticsResponse)
async def get_project_statistics(project_id: str) -> ProjectStatisticsResponse:
    """Return computed statistics for a project.

    Inspects the project directory to count particles and estimate resolution.
    Returns 404 if the project ID is not found.
    """
    record = _projects.get(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    project_dir = Path(record.directory)
    tilt_series = _project_service.list_tilt_series(record.directory)

    particle_count = _count_particles(project_dir)
    resolution = _detect_best_resolution(project_dir)

    return ProjectStatisticsResponse(
        project_id=project_id,
        particle_count=particle_count,
        resolution_angstrom=resolution,
        tilt_series_count=len(tilt_series),
    )


@router.get("/{project_id}/tilt-series")
async def list_tilt_series(project_id: str) -> TiltSeriesListResponse:
    """List tilt series for a project.

    Returns an empty list for new projects with no data in rawData/.
    Returns 404 if the project ID is not found.
    """
    record = _projects.get(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    tilt_series = _project_service.list_tilt_series(record.directory)

    return TiltSeriesListResponse(tilt_series=tilt_series)
