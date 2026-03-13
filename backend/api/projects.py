"""API endpoints for emClarity project management.

Routes:
    POST /api/projects                    - Create a new project
    GET  /api/projects/{path}             - Load project state
    GET  /api/projects/{path}/tilt-series - List tilt series in a project
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.models.project import Project, TiltSeries
from backend.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects", tags=["projects"])

_service = ProjectService()


class CreateProjectRequest(BaseModel):
    """Request body for creating a new project."""

    name: str = Field(..., description="Project name")
    path: str = Field(..., description="Absolute path for the project directory")


@router.post("", response_model=Project)
async def create_project(request: CreateProjectRequest) -> Project:
    """Create a new emClarity project directory.

    Sets up the standard directory structure (rawData/, fixedStacks/,
    aliStacks/, cache/, convmap/, FSC/, logFile/).
    """
    try:
        return _service.create_project(request.name, request.path)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create project: {exc}")


@router.get("/{path:path}/tilt-series", response_model=list[TiltSeries])
async def list_tilt_series(path: str) -> list[TiltSeries]:
    """List tilt series found in the project's rawData/ directory."""
    try:
        return _service.list_tilt_series(f"/{path}")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: /{path}")


@router.get("/{path:path}", response_model=Project)
async def load_project(path: str) -> Project:
    """Load project state by inspecting the directory structure.

    The backend determines the current pipeline state by checking
    which processing directories contain data.
    """
    try:
        return _service.load_project(f"/{path}")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: /{path}")
