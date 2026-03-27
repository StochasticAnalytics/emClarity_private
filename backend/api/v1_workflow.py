"""V1 Workflow state machine API endpoints.

Provides workflow state management endpoints for emClarity projects using
UUID-based project identifiers.

Routes:
    GET  /api/v1/workflow/state-machine                     - Full state machine definition
    GET  /api/v1/workflow/{project_id}/available-commands   - Commands available in current state
    POST /api/v1/workflow/{project_id}/run                  - Run a command (enforces prerequisites)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.models.project import ProjectState

router = APIRouter(prefix="/api/v1/workflow", tags=["workflow-v1"])

# ---------------------------------------------------------------------------
# State machine definition
# ---------------------------------------------------------------------------

# Maps each project state to the set of commands that are allowed (enabled)
# in that state.  Only commands whose prerequisites have been completed
# should appear here.
_STATE_ALLOWED_COMMANDS: dict[ProjectState, list[str]] = {
    ProjectState.UNINITIALIZED: [
        "autoAlign",
    ],
    ProjectState.TILT_ALIGNED: [
        "autoAlign",
        "ctf estimate",
    ],
    ProjectState.CTF_ESTIMATED: [
        "autoAlign",
        "ctf estimate",
        "ctf 3d",
    ],
    ProjectState.RECONSTRUCTED: [
        "autoAlign",
        "ctf estimate",
        "ctf 3d",
        "templateSearch",
    ],
    ProjectState.PARTICLES_PICKED: [
        "autoAlign",
        "ctf estimate",
        "ctf 3d",
        "templateSearch",
        "init",
    ],
    ProjectState.INITIALIZED: [
        "autoAlign",
        "ctf estimate",
        "ctf 3d",
        "templateSearch",
        "init",
        "avg",
    ],
    ProjectState.CYCLE_N: [
        "autoAlign",
        "ctf estimate",
        "ctf 3d",
        "templateSearch",
        "init",
        "avg",
        "alignRaw",
        "tomoCPR",
        "pca",
        "cluster",
        "fsc",
        "reconstruct",
    ],
    ProjectState.EXPORT: [
        "autoAlign",
        "ctf estimate",
        "ctf 3d",
        "templateSearch",
        "init",
        "avg",
        "alignRaw",
        "tomoCPR",
        "pca",
        "cluster",
        "fsc",
        "reconstruct",
    ],
    ProjectState.DONE: [],
}

# Full state machine definition for client consumption
_STATE_MACHINE: dict[str, Any] = {
    "states": {
        "UNINITIALIZED": {
            "description": "No processing has started; raw data only",
            "available_commands": ["autoAlign"],
            "transitions": {
                "autoAlign": "TILT_ALIGNED",
            },
        },
        "TILT_ALIGNED": {
            "description": "Tilt-series alignment complete",
            "available_commands": ["autoAlign", "ctf estimate"],
            "transitions": {
                "ctf estimate": "CTF_ESTIMATED",
            },
        },
        "CTF_ESTIMATED": {
            "description": "CTF estimation complete",
            "available_commands": ["autoAlign", "ctf estimate", "ctf 3d"],
            "transitions": {
                "ctf 3d": "RECONSTRUCTED",
            },
        },
        "RECONSTRUCTED": {
            "description": "3D tomograms reconstructed",
            "available_commands": ["autoAlign", "ctf estimate", "ctf 3d", "templateSearch"],
            "transitions": {
                "templateSearch": "PARTICLES_PICKED",
            },
        },
        "PARTICLES_PICKED": {
            "description": "Template search / particle picking complete",
            "available_commands": [
                "autoAlign", "ctf estimate", "ctf 3d", "templateSearch", "init",
            ],
            "transitions": {
                "init": "INITIALIZED",
            },
        },
        "INITIALIZED": {
            "description": "Project initialised; subTomoMeta.mat created",
            "available_commands": [
                "autoAlign", "ctf estimate", "ctf 3d", "templateSearch", "init", "avg",
            ],
            "transitions": {
                "avg": "CYCLE_N",
            },
        },
        "CYCLE_N": {
            "description": "Iterative alignment/averaging in progress",
            "available_commands": [
                "autoAlign", "ctf estimate", "ctf 3d", "templateSearch", "init",
                "avg", "alignRaw", "tomoCPR", "pca", "cluster", "fsc", "reconstruct",
            ],
            "transitions": {
                "reconstruct": "EXPORT",
            },
        },
        "EXPORT": {
            "description": "Final reconstruction exported to cisTEM format",
            "available_commands": [
                "autoAlign", "ctf estimate", "ctf 3d", "templateSearch", "init",
                "avg", "alignRaw", "tomoCPR", "pca", "cluster", "fsc", "reconstruct",
            ],
            "transitions": {},
        },
        "DONE": {
            "description": "Processing complete",
            "available_commands": [],
            "transitions": {},
        },
    },
    "initial_state": "UNINITIALIZED",
}

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CommandEntry(BaseModel):
    """Describes a single available command."""

    name: str = Field(..., description="Command name as passed to emClarity CLI")
    description: str = Field(default="", description="Human-readable description")


class AvailableCommandsResponse(BaseModel):
    """Response body for the available-commands endpoint."""

    project_id: str
    state: str
    commands: list[CommandEntry]


class RunCommandRequest(BaseModel):
    """Request body for running a workflow command."""

    command: str = Field(..., description="emClarity command to execute")
    args: dict[str, Any] = Field(
        default_factory=dict,
        description="Command-specific arguments",
    )
    param_file: str | None = Field(
        default=None,
        description="Path to the .m parameter file for this run",
    )


class RunCommandResponse(BaseModel):
    """Response body after successfully accepting a run request."""

    project_id: str
    command: str
    status: str = "accepted"
    message: str = ""
    param_file: str | None = None


# ---------------------------------------------------------------------------
# Human-readable descriptions per command
# ---------------------------------------------------------------------------

_COMMAND_DESCRIPTIONS: dict[str, str] = {
    "autoAlign": "Align raw tilt-series images using fiducial or patch tracking",
    "ctf estimate": "Estimate defocus and astigmatism for each tilt image",
    "ctf 3d": "Apply 3D CTF correction and reconstruct tomograms",
    "templateSearch": "Search for particles using a 3D template",
    "init": "Initialise the sub-tomogram averaging project",
    "avg": "Compute the sub-tomogram average from aligned particles",
    "alignRaw": "Refine particle orientations against the current average",
    "tomoCPR": "Refine tilt-series geometry using current particle positions",
    "pca": "Principal component analysis for heterogeneity detection",
    "cluster": "Classify particles based on PCA eigenvectors",
    "fsc": "Compute Fourier Shell Correlation for resolution estimation",
    "reconstruct": "Generate the final high-resolution 3D reconstruction",
}


# ---------------------------------------------------------------------------
# Shared project registry accessor
# ---------------------------------------------------------------------------

def _get_projects() -> dict[str, Any]:
    """Return the shared in-memory project registry.

    Imported lazily to avoid circular-import issues at module load time.
    """
    from backend.api.v1_projects import _projects
    return _projects  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/state-machine")
async def get_state_machine() -> dict[str, Any]:
    """Return the full state machine definition.

    Describes every state, its available commands, and allowed transitions.
    Clients use this to render pipeline progress UIs and validate user actions.
    """
    return _STATE_MACHINE


@router.get("/{project_id}/available-commands", response_model=AvailableCommandsResponse)
async def get_available_commands(project_id: str) -> AvailableCommandsResponse:
    """Return the commands available for a project in its current state.

    Only commands whose prerequisites have been satisfied are included.
    Returns 404 if the project ID is unknown.
    """
    projects = _get_projects()
    record = projects.get(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    state: ProjectState = record.state
    allowed_names = _STATE_ALLOWED_COMMANDS.get(state, [])

    commands = [
        CommandEntry(
            name=name,
            description=_COMMAND_DESCRIPTIONS.get(name, ""),
        )
        for name in allowed_names
    ]

    return AvailableCommandsResponse(
        project_id=project_id,
        state=state.value.upper(),
        commands=commands,
    )


@router.post("/{project_id}/run", response_model=RunCommandResponse)
async def run_command(project_id: str, request: RunCommandRequest) -> RunCommandResponse:
    """Execute an emClarity pipeline command for a project.

    Enforces the state machine: returns 409 if the requested command is not
    available in the project's current state (i.e. prerequisites not met).
    Returns 404 if the project ID is unknown.
    """
    projects = _get_projects()
    record = projects.get(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    state: ProjectState = record.state
    allowed_names = _STATE_ALLOWED_COMMANDS.get(state, [])

    if request.command not in allowed_names:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Command '{request.command}' is not available in state "
                f"'{state.value.upper()}'. "
                f"Available commands: {allowed_names}"
            ),
        )

    # Command is permitted – in a full implementation this would launch a job.
    # For now we return 'accepted' and let the caller poll for job status.
    return RunCommandResponse(
        project_id=project_id,
        command=request.command,
        status="accepted",
        message=f"Command '{request.command}' accepted for execution",
        param_file=request.param_file,
    )
