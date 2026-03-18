"""Parameter snapshot endpoints for saving and exporting parameter snapshots.

Provides:
- POST /api/v1/projects/{project_id}/parameter-snapshots
  Save a parameter snapshot to the project's parameters/ directory.
- POST /api/v1/projects/{project_id}/parameter-snapshots/{snapshot_id}/export-m
  Export a snapshot to MATLAB .m format.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.v1_projects import _get_project
from backend.services.parameter_service import ParameterService

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/parameter-snapshots",
    tags=["parameter-snapshots-v1"],
)

_parameter_service = ParameterService()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CreateSnapshotRequest(BaseModel):
    """Request body for creating a parameter snapshot."""
    parameters: dict[str, Any] = Field(
        ..., description="Parameter key-value pairs to snapshot"
    )


class CreateSnapshotResponse(BaseModel):
    """Response after successfully creating a parameter snapshot."""
    snapshot_id: str
    filename: str
    created_at: str


class ExportMResponse(BaseModel):
    """Response after exporting a snapshot to .m format."""
    m_file_path: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=CreateSnapshotResponse)
def create_snapshot(
    project_id: str,
    body: CreateSnapshotRequest,
) -> CreateSnapshotResponse:
    """Save a parameter snapshot to the project's parameters/ directory.

    Generates a UUID-based snapshot file, writes the parameters as JSON,
    and enforces a retention cap of 50 snapshots per project (oldest deleted).
    """
    record = _get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    project_dir = Path(record.directory)
    if not project_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Project directory does not exist: {record.directory}",
        )

    try:
        snapshot_id, filename, created_at = _parameter_service.save_snapshot(
            project_dir, body.parameters
        )
    except Exception as exc:
        log.exception("Failed to save parameter snapshot for project %s", project_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save snapshot: {exc}",
        ) from exc

    return CreateSnapshotResponse(
        snapshot_id=snapshot_id,
        filename=filename,
        created_at=created_at,
    )


@router.post("/{snapshot_id}/export-m", response_model=ExportMResponse)
def export_snapshot_m(
    project_id: str,
    snapshot_id: str,
) -> ExportMResponse:
    """Export a parameter snapshot to MATLAB .m format.

    Reads the snapshot JSON identified by *snapshot_id*, converts to .m
    format, and writes the file alongside the JSON snapshot.
    """
    record = _get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    project_dir = Path(record.directory)
    params_dir = project_dir / "parameters"
    if not params_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"No parameters directory found for project {project_id}",
        )

    # Find the snapshot file by matching the UUID prefix in filenames
    try:
        matching = [
            f for f in params_dir.iterdir()
            if f.name.startswith(f"snapshot_{snapshot_id}") and f.suffix == ".json"
        ]
    except OSError as exc:
        log.exception("Failed to list parameters directory for project %s", project_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list snapshots directory: {exc}",
        ) from exc

    if not matching:
        raise HTTPException(
            status_code=404,
            detail=f"Snapshot {snapshot_id} not found in project {project_id}",
        )

    if len(matching) > 1:
        raise HTTPException(
            status_code=409,
            detail=f"Snapshot ID prefix '{snapshot_id}' is ambiguous: matches {len(matching)} files",
        )

    snapshot_path = matching[0]

    try:
        m_file_path = _parameter_service.export_snapshot_to_m(snapshot_path)
    except Exception as exc:
        log.exception("Failed to export snapshot %s to .m format", snapshot_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export snapshot: {exc}",
        ) from exc

    return ExportMResponse(m_file_path=str(m_file_path))
