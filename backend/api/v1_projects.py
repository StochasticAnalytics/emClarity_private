"""V1 Project management API endpoints.

Provides CRUD operations for emClarity projects using UUID-based identifiers.
Projects are backed by on-disk directory structures following emClarity conventions.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.models.project import ProjectState, TiltSeries
from backend.services.project_service import ProjectService

router = APIRouter(prefix="/api/v1/projects", tags=["projects-v1"])

# ---------------------------------------------------------------------------
# In-memory project registry (keyed by UUID string)
# ---------------------------------------------------------------------------

_projects: dict[str, "_ProjectRecord"] = {}
_project_service = ProjectService()


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


class ProjectResponse(BaseModel):
    """Response body for project endpoints."""

    id: str
    name: str
    directory: str
    state: str
    parameters: dict[str, Any]
    current_cycle: int = 0


class TiltSeriesListResponse(BaseModel):
    """Response body for tilt series listing."""

    tilt_series: list[TiltSeries]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(request: CreateProjectRequest) -> ProjectResponse:
    """Create a new emClarity project.

    Creates the standard directory structure on disk and registers the
    project in memory with an UNINITIALIZED state.
    """
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
