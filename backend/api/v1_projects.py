"""V1 Project management API endpoints.

Provides CRUD operations for emClarity projects using UUID-based identifiers.
Projects are backed by on-disk directory structures following emClarity conventions.

The in-memory registry is persisted to ~/.emclarity/projects.json so that
project IDs remain valid across backend restarts.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from backend.models.project import ProjectState, TiltSeries
from backend.models.project_settings import ProjectSettings, ProjectSettingsPatch
from backend.services.project_service import ProjectService
from backend.utils.machine_config import get_registry_dir
from backend.utils.safe_json import locked_json_read, locked_json_read_write

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects-v1"])

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_REGISTRY_DIR = get_registry_dir()
_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
_REGISTRY_FILE = _REGISTRY_DIR / "projects.json"

# In-process lock protecting _projects dict access.
_registry_lock = threading.Lock()


def _save_registry() -> None:
    """Persist the in-memory project registry to disk using dual-locking.

    Serialises the current in-memory ``_projects`` dict through the
    locked-JSON read-modify-write pattern so that concurrent threads
    and processes cannot corrupt the file.
    """
    try:
        with _registry_lock:
            snapshot = {k: v.model_dump(mode="json") for k, v in _projects.items()}

        def _replace(_existing: Any) -> dict[str, Any]:
            return snapshot

        locked_json_read_write(_REGISTRY_FILE, _replace)
    except Exception as exc:  # noqa: BLE001
        log.error("Could not persist project registry: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to persist project registry: {exc}",
        ) from exc


def _load_registry() -> None:
    """Load the project registry from disk (called once at module import).

    Uses :func:`locked_json_read` so that a concurrent writer
    cannot produce a partial read, without redundantly rewriting the file.
    """
    if not _REGISTRY_FILE.exists():
        return
    try:
        raw = locked_json_read(_REGISTRY_FILE)
        if raw is None:
            return

        with _registry_lock:
            for project_id, record_data in raw.items():
                try:
                    _projects[project_id] = _ProjectRecord(**record_data)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Skipping corrupt registry entry %s: %s", project_id, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load project registry from %s: %s", _REGISTRY_FILE, exc)


def _get_projects() -> dict[str, _ProjectRecord]:
    """Return a snapshot of the in-memory registry (thread-safe)."""
    with _registry_lock:
        return dict(_projects)


def _get_project(project_id: str) -> _ProjectRecord | None:
    """Look up a single project by ID (thread-safe)."""
    with _registry_lock:
        return _projects.get(project_id)


def _set_project(project_id: str, record: _ProjectRecord) -> None:
    """Insert or update a project in the in-memory registry (thread-safe)."""
    with _registry_lock:
        _projects[project_id] = record


# ---------------------------------------------------------------------------
# In-memory project registry (keyed by UUID string)
# ---------------------------------------------------------------------------

class _ProjectRecord(BaseModel):
    """Internal record stored in memory for each created project."""

    id: str
    name: str
    directory: str
    state: ProjectState
    parameters: dict[str, Any]
    current_cycle: int = 0
    last_accessed: str | None = None
    settings: ProjectSettings = Field(default_factory=ProjectSettings)


_projects: dict[str, _ProjectRecord] = {}
_project_service = ProjectService()

# Load persisted registry at startup
_load_registry()


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
    last_accessed: str | None = None


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
        implausible_warned = False  # emit at most one warning per file
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
            # freq must be a realistic reciprocal-space value (0 < freq ≤ 1.0 1/Å).
            # The upper bound of 1.0 corresponds to ~1 Å resolution, which is the
            # practical physical limit for cryo-EM; values beyond this indicate
            # misinterpreted units or corrupt data.
            if freq <= 0 or freq > 1.0:
                continue
            if fsc_val >= 0.143:
                angstrom = 1.0 / freq
                # Accept physically meaningful cryo-EM resolutions up to 200 Å.
                # No lower bound: sub-2 Å results are valid for high-resolution structures.
                # Guard is applied per-line so one implausible line cannot silently
                # discard an otherwise valid resolution result from the same file.
                if angstrom <= 200.0:
                    resolution_freq = freq
                elif not implausible_warned:
                    log.warning(
                        "Discarding implausible resolution(s) from %s "
                        "(first offender: %.2f Å exceeds 200 Å upper bound; "
                        "likely a unit mismatch).",
                        fsc_file,
                        angstrom,
                    )
                    implausible_warned = True

        if resolution_freq is not None:
            angstrom = 1.0 / resolution_freq
            if best_angstrom is None or angstrom < best_angstrom:
                best_angstrom = angstrom

    return round(best_angstrom, 2) if best_angstrom is not None else None


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------


def _to_response(record: _ProjectRecord) -> ProjectResponse:
    """Convert an internal record to an API response."""
    return ProjectResponse(
        id=record.id,
        name=record.name,
        directory=record.directory,
        state=record.state.value,
        parameters=record.parameters,
        current_cycle=record.current_cycle,
        last_accessed=record.last_accessed,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ProjectResponse])
async def list_projects() -> list[ProjectResponse]:
    """Return all registered projects sorted by last_accessed descending.

    Projects that have never been accessed (``last_accessed`` is ``None``)
    appear after all projects with a timestamp.
    """
    projects = _get_projects()

    # Partition into accessed and never-accessed, sort accessed newest-first
    with_ts = [(k, v) for k, v in projects.items() if v.last_accessed is not None]
    without_ts = [(k, v) for k, v in projects.items() if v.last_accessed is None]
    with_ts.sort(key=lambda item: item[1].last_accessed or "", reverse=True)
    sorted_items = with_ts + without_ts

    return [_to_response(rec) for _, rec in sorted_items]


@router.patch("/{project_id}/accessed", response_model=ProjectResponse)
async def mark_project_accessed(project_id: str) -> ProjectResponse:
    """Touch a project's last_accessed timestamp (set to current UTC time).

    Used by the frontend to track recently accessed projects.
    Returns 404 if the project ID is not found.
    """
    with _registry_lock:
        record = _projects.get(project_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        record.last_accessed = datetime.now(timezone.utc).isoformat()
        # record is already in _projects; no need to re-insert

    _save_registry()

    return _to_response(record)


@router.delete("/{project_id}", status_code=204)
async def deregister_project(project_id: str) -> None:
    """Remove a project from the registry (does NOT delete files on disk).

    Used by the frontend to hide a project from the recent-projects list.
    Returns 404 if the project ID is not found.
    """
    record = _get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    with _registry_lock:
        _projects.pop(project_id, None)
    _save_registry()


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
    _set_project(project_id, record)
    _save_registry()

    return _to_response(record)


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
    for existing_id, existing_record in _get_projects().items():
        if Path(existing_record.directory).resolve() == Path(resolved):
            return _to_response(existing_record)

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
    _set_project(project_id, record)
    _save_registry()

    return _to_response(record)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str) -> ProjectResponse:
    """Return the current state and metadata for a project.

    Returns 404 if the project ID is not found.
    """
    record = _get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    return _to_response(record)


@router.get("/{project_id}/statistics", response_model=ProjectStatisticsResponse)
async def get_project_statistics(project_id: str) -> ProjectStatisticsResponse:
    """Return computed statistics for a project.

    Inspects the project directory to count particles and estimate resolution.
    Returns 404 if the project ID is not found.
    """
    record = _get_project(project_id)
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
    record = _get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    tilt_series = _project_service.list_tilt_series(record.directory)

    return TiltSeriesListResponse(tilt_series=tilt_series)


@router.get("/{project_id}/settings")
async def get_project_settings(project_id: str) -> ProjectSettings:
    """Return the settings for a project."""
    record = _get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return record.settings


@router.patch("/{project_id}/settings")
async def update_project_settings(project_id: str, patch: ProjectSettingsPatch) -> ProjectSettings:
    """Partial update of project settings.

    Accepts a typed partial-update model, merges provided fields with
    existing settings. Uses locked write pattern for concurrent safety.
    """
    record = _get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    # Get only the fields that were explicitly provided in the request body
    provided = patch.model_dump(exclude_unset=True)

    with _registry_lock:
        record = _projects.get(project_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

        # Merge: existing settings dict + provided fields
        existing = record.settings.model_dump()

        for key, value in provided.items():
            if key == "run_profiles":
                if value is None:
                    raise HTTPException(
                        status_code=422,
                        detail="run_profiles must be a list, not null",
                    )
                existing["run_profiles"] = value
            elif key == "executable_paths":
                if value is None:
                    raise HTTPException(
                        status_code=422,
                        detail="executable_paths must be an object, not null",
                    )
                existing["executable_paths"] = value
            elif key == "system_params" and value is not None and isinstance(value, dict):
                if existing.get("system_params") is not None:
                    existing["system_params"].update(value)
                else:
                    existing["system_params"] = value
            else:
                existing[key] = value

        try:
            record.settings = ProjectSettings(**existing)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=exc.errors(),
            )

    _save_registry()
    return record.settings
