"""API endpoints for parameter schema, file I/O, and validation.

Routes:
    GET  /api/v1/parameters/schema    - Return the full parameter schema (v1, wrapped)
    POST /api/v1/parameters/validate  - Validate a dict of parameter values (v1)
    GET  /api/parameters/schema       - Return the full parameter schema (legacy, flat list)
    GET  /api/parameters/file/{path}  - Load a parameter file from disk
    POST /api/parameters/file         - Save a parameter file to disk
    POST /api/parameters/validate     - Validate parameter values (legacy)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.models.parameter import (
    ParameterDefinition,
    ParameterFile,
    ParameterSchemaResponse,
    ParameterValidationRequest,
    ParameterValidationResult,
    ParameterValue,
)
from backend.services.parameter_service import ParameterService

router = APIRouter(prefix="/api/parameters", tags=["parameters"])

# v1 router serves the schema wrapped in {"parameters": [...]} as the
# frontend E2E tests expect.
v1_router = APIRouter(prefix="/api/v1/parameters", tags=["parameters-v1"])

# Singleton service instance
_service = ParameterService()


# ---- v1 endpoint (wrapped response) ------------------------------------

@v1_router.get("/schema", response_model=ParameterSchemaResponse)
async def get_parameter_schema_v1() -> ParameterSchemaResponse:
    """Return the complete parameter schema wrapped in a JSON object.

    Response body: ``{"parameters": [<ParameterDefinition>, ...]}``

    This is the preferred endpoint for the React frontend.
    """
    return ParameterSchemaResponse(parameters=_service.get_schema())


@v1_router.get("/file/{path:path}", response_model=ParameterFile)
async def load_parameter_file_v1(path: str) -> ParameterFile:
    """Load and parse a MATLAB-style parameter file (v1).

    Reads the file at the given server-side filesystem path, parses all
    ``key = value`` assignments, and transparently migrates any deprecated
    parameter names (e.g. ``flgCCCcutoff`` → ``ccc_cutoff``) before
    returning the result.

    Args:
        path: Absolute or relative filesystem path to the ``.m`` file.

    Returns:
        A :class:`ParameterFile` with parsed and migrated parameter values.

    Raises:
        404: When the file does not exist at the given path.
    """
    try:
        return _service.load_parameter_file_v1(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Parameter file not found: {path}")


@v1_router.post("/file", response_model=ParameterFile)
async def save_parameter_file_v1(param_file: ParameterFile) -> ParameterFile:
    """Write parameter values to a MATLAB-style ``.m`` file (v1).

    Creates any missing parent directories.  The output format is
    compatible with the emClarity MATLAB parameter file parser.

    Args:
        param_file: The parameter file to write, including the target path
            and the list of ``{name, value}`` pairs.

    Returns:
        The saved :class:`ParameterFile` echoed back on success.

    Raises:
        500: When the file cannot be written (e.g. permission denied).
    """
    try:
        _service.save_parameter_file(param_file)
        return param_file
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")


@v1_router.post("/validate", response_model=ParameterValidationResult)
async def validate_parameters_v1(
    request: ParameterValidationRequest,
) -> ParameterValidationResult:
    """Validate a flat dict of parameter values against the schema.

    Accepts ``{"parameters": {"PIXEL_SIZE": 1.35e-10, ...}}`` and returns
    a validation result.  Deprecated parameter names (e.g. ``flgCCCcutoff``)
    are transparently translated to their canonical form before validation.
    """
    return _service.validate_parameters_dict(request.parameters)


# ---- legacy endpoint (flat list, backward compat) -----------------------

@router.get("/schema", response_model=list[ParameterDefinition])
async def get_parameter_schema() -> list[ParameterDefinition]:
    """Return the complete parameter schema as a flat list.

    The schema describes every parameter that emClarity accepts,
    including type, range constraints, and descriptions. The frontend
    uses this to render dynamic parameter forms.

    .. deprecated::
        Prefer ``GET /api/v1/parameters/schema`` which wraps the
        response in ``{"parameters": [...]}``.
    """
    return _service.get_schema()


@router.get("/file/{path:path}", response_model=ParameterFile)
async def load_parameter_file(path: str) -> ParameterFile:
    """Load and parse a MATLAB-style parameter file.

    The path should be an absolute filesystem path or relative to
    the server's working directory.
    """
    try:
        return _service.load_parameter_file(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Parameter file not found: {path}")


@router.post("/file", response_model=ParameterFile)
async def save_parameter_file(param_file: ParameterFile) -> ParameterFile:
    """Write parameter values to a .m file on disk.

    Creates parent directories if they do not exist.
    """
    try:
        _service.save_parameter_file(param_file)
        return param_file
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")


@router.post("/validate", response_model=ParameterValidationResult)
async def validate_parameters(
    parameters: list[ParameterValue],
) -> ParameterValidationResult:
    """Validate a list of parameter values against the schema.

    Returns a result indicating whether all values are valid, along
    with any errors or warnings.
    """
    return _service.validate_parameters(parameters)
