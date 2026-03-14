"""V1 API endpoints for standalone utility operations.

Routes:
    POST /api/v1/utilities/check    - Run emClarity check to verify installation
    POST /api/v1/utilities/mask     - Run emClarity mask command
    POST /api/v1/utilities/rescale  - Run emClarity rescale command
    POST /api/v1/utilities/geometry - Run emClarity geometry operations
"""

from __future__ import annotations

import shlex
import subprocess

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/utilities", tags=["utilities-v1"])

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

VALID_GEOMETRY_OPERATIONS: set[str] = {
    "RemoveClasses",
    "RemoveFraction",
    "RemoveLowScoringParticles",
    "RestoreParticles",
    "PrintGeometry",
}


class CheckResult(BaseModel):
    """Result of running emClarity check."""

    success: bool = Field(..., description="Whether the check passed")
    output: str = Field(default="", description="Standard output from the command")
    errors: str = Field(default="", description="Standard error output from the command")


class CommandResult(BaseModel):
    """Result of running an emClarity utility command."""

    success: bool = Field(..., description="Whether the command succeeded")
    output: str = Field(default="", description="Command output (stdout + stderr)")
    command: str = Field(default="", description="The command that was executed")


class GeometryResult(CommandResult):
    """Result of running an emClarity geometry operation."""

    operation: str = Field(..., description="The geometry operation that was run")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class MaskRequest(BaseModel):
    """Parameters for the emClarity mask command."""

    param_file: str = Field(..., description="Path to the parameter file (.m)")
    tilt_series_name: str = Field(..., description="Name of the tilt series")


class RescaleRequest(BaseModel):
    """Parameters for the emClarity rescale command."""

    param_file: str = Field(..., description="Path to the parameter file (.m)")
    target_pixel_size: float = Field(
        ...,
        gt=0,
        description="Target pixel size in Angstroms",
    )


class GeometryRequest(BaseModel):
    """Parameters for an emClarity geometry operation."""

    param_file: str = Field(..., description="Path to the parameter file (.m)")
    operation: str = Field(..., description="Geometry operation to perform")
    cycle: int = Field(default=1, ge=1, description="Processing cycle number")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _run(cmd: list[str], timeout: int = 300) -> tuple[bool, str, str]:
    """Run a subprocess command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except FileNotFoundError:
        return (
            False,
            "",
            "emClarity executable not found in PATH. "
            "Please ensure emClarity is installed and accessible.",
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504,
            detail=f"Command timed out after {timeout} seconds",
        ) from exc


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/check", response_model=CheckResult)
async def run_system_check() -> CheckResult:
    """Run emClarity check to verify installation and all dependencies."""
    success, stdout, stderr = _run(["emClarity", "check"], timeout=60)
    return CheckResult(success=success, output=stdout, errors=stderr)


@router.post("/mask", response_model=CommandResult)
async def run_mask(request: MaskRequest) -> CommandResult:
    """Run emClarity mask command to create particle masks."""
    cmd = ["emClarity", "mask", request.param_file, request.tilt_series_name]
    cmd_str = shlex.join(cmd)
    success, stdout, stderr = _run(cmd)
    combined = stdout + (f"\n{stderr}" if stderr else "")
    return CommandResult(success=success, output=combined.strip(), command=cmd_str)


@router.post("/rescale", response_model=CommandResult)
async def run_rescale(request: RescaleRequest) -> CommandResult:
    """Run emClarity rescale command to rescale volumes to a new pixel size."""
    cmd = [
        "emClarity",
        "rescale",
        request.param_file,
        str(request.target_pixel_size),
    ]
    cmd_str = shlex.join(cmd)
    success, stdout, stderr = _run(cmd)
    combined = stdout + (f"\n{stderr}" if stderr else "")
    return CommandResult(success=success, output=combined.strip(), command=cmd_str)


@router.post("/geometry", response_model=GeometryResult)
async def run_geometry(request: GeometryRequest) -> GeometryResult:
    """Run an emClarity geometry operation on the particle set."""
    if request.operation not in VALID_GEOMETRY_OPERATIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown geometry operation: {request.operation!r}. "
                f"Valid operations: {sorted(VALID_GEOMETRY_OPERATIONS)}"
            ),
        )
    cmd = [
        "emClarity",
        "geometry",
        request.operation,
        request.param_file,
        str(request.cycle),
    ]
    cmd_str = shlex.join(cmd)
    success, stdout, stderr = _run(cmd)
    combined = stdout + (f"\n{stderr}" if stderr else "")
    return GeometryResult(
        success=success,
        output=combined.strip(),
        command=cmd_str,
        operation=request.operation,
    )
