"""API endpoints for workflow management and command execution.

Routes:
    GET  /api/workflow/commands          - List available pipeline commands
    POST /api/workflow/execute           - Execute a pipeline command
    GET  /api/workflow/state/{path}      - Get pipeline state for a project
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.models.job import Job
from backend.models.workflow import CommandInfo, CommandRequest, WorkflowState
from backend.services.job_service import JobService
from backend.services.project_service import ProjectService
from backend.services.workflow_service import WorkflowService

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

_workflow_service = WorkflowService()
_project_service = ProjectService()
_job_service = JobService()


@router.get("/commands", response_model=list[CommandInfo])
async def list_commands() -> list[CommandInfo]:
    """Return metadata for all available pipeline commands.

    Includes human-readable labels, descriptions, and prerequisite
    information that the frontend uses to enable/disable buttons.
    """
    return _workflow_service.list_commands()


@router.post("/execute", response_model=Job)
async def execute_command(request: CommandRequest) -> Job:
    """Execute an emClarity pipeline command.

    Launches the command as a background subprocess and returns a Job
    object that can be polled for status. The project must have a
    parameter file set.
    """
    # We need a project path from the request parameters
    project_path = request.parameters.get("project_path")
    if not project_path:
        raise HTTPException(
            status_code=400,
            detail="'project_path' must be provided in parameters",
        )

    # Load project to find the parameter file
    try:
        project = _project_service.load_project(project_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_path}")

    param_file = project.parameter_file
    if not param_file:
        raise HTTPException(
            status_code=400,
            detail="No parameter file found in project directory",
        )

    # Build and launch the CLI command
    cli_args = _workflow_service.build_cli_command(request, param_file)
    job = _job_service.start_job(
        command=request.command,
        cli_args=cli_args,
        project_path=project_path,
    )

    return job


@router.get("/state/{path:path}", response_model=WorkflowState)
async def get_workflow_state(path: str) -> WorkflowState:
    """Determine which commands are available for a project.

    Inspects the project directory to figure out which steps have
    been completed, then calculates which commands can be run next.
    """
    try:
        project = _project_service.load_project(f"/{path}")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: /{path}")

    # Map project state to completed commands (simplified heuristic)
    from backend.models.project import ProjectState
    from backend.models.workflow import PipelineCommand

    state_to_commands: dict[ProjectState, list[PipelineCommand]] = {
        ProjectState.UNINITIALIZED: [],
        ProjectState.TILT_ALIGNED: [PipelineCommand.AUTO_ALIGN],
        ProjectState.CTF_ESTIMATED: [
            PipelineCommand.AUTO_ALIGN,
            PipelineCommand.CTF_ESTIMATE,
        ],
        ProjectState.RECONSTRUCTED: [
            PipelineCommand.AUTO_ALIGN,
            PipelineCommand.CTF_ESTIMATE,
            PipelineCommand.CTF_3D,
        ],
        ProjectState.PARTICLES_PICKED: [
            PipelineCommand.AUTO_ALIGN,
            PipelineCommand.CTF_ESTIMATE,
            PipelineCommand.CTF_3D,
            PipelineCommand.TEMPLATE_SEARCH,
        ],
        ProjectState.INITIALIZED: [
            PipelineCommand.AUTO_ALIGN,
            PipelineCommand.CTF_ESTIMATE,
            PipelineCommand.CTF_3D,
            PipelineCommand.TEMPLATE_SEARCH,
            PipelineCommand.INIT,
        ],
        ProjectState.CYCLE_N: [
            PipelineCommand.AUTO_ALIGN,
            PipelineCommand.CTF_ESTIMATE,
            PipelineCommand.CTF_3D,
            PipelineCommand.TEMPLATE_SEARCH,
            PipelineCommand.INIT,
            PipelineCommand.AVG,
        ],
    }

    completed = state_to_commands.get(project.state, [])
    return _workflow_service.get_workflow_state(completed)
