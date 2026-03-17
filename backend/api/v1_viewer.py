"""V1 Viewer launcher API endpoint.

Provides endpoints to launch an external viewer program (e.g. 3dmod, ChimeraX)
as a non-blocking subprocess.

POST /api/v1/viewer/launch
    body: { viewer_path: str, args: list[str] }
    Returns { launched: true, pid: int } on success.
    400 if path is not executable (exists but not executable).
    404 if path does not exist.
    Subprocess launched with list form, never shell=True.

GET /api/v1/viewer/default
    Returns { viewer_path: str | null } — the currently stored default viewer path.

PUT /api/v1/viewer/default
    body: { viewer_path: str }
    Validates path exists (does not need to be running, just a file that exists).
    Stores it in module-level variable. Returns 200 on success.
"""

from __future__ import annotations

import os
import subprocess

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/viewer", tags=["viewer-v1"])

_default_viewer_path: str | None = None


class LaunchRequest(BaseModel):
    viewer_path: str
    args: list[str] = []


class LaunchResponse(BaseModel):
    launched: bool
    pid: int


class DefaultViewerResponse(BaseModel):
    viewer_path: str | None


class SetDefaultRequest(BaseModel):
    viewer_path: str


@router.post("/launch", response_model=LaunchResponse)
def launch_viewer(request: LaunchRequest) -> LaunchResponse:
    """Launch an external viewer as a non-blocking subprocess."""
    viewer_path = request.viewer_path

    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404, detail=f"Viewer not found: {viewer_path}")

    if not os.access(viewer_path, os.X_OK):
        raise HTTPException(
            status_code=400, detail=f"Path is not executable: {viewer_path}"
        )

    proc = subprocess.Popen(
        [viewer_path] + request.args,
        start_new_session=True,
    )

    return LaunchResponse(launched=True, pid=proc.pid)


@router.get("/default", response_model=DefaultViewerResponse)
def get_default_viewer() -> DefaultViewerResponse:
    """Return the currently stored default viewer path."""
    return DefaultViewerResponse(viewer_path=_default_viewer_path)


@router.put("/default", response_model=DefaultViewerResponse)
def set_default_viewer(request: SetDefaultRequest) -> DefaultViewerResponse:
    """Set the default viewer path. Validates that the path exists."""
    global _default_viewer_path

    viewer_path = request.viewer_path

    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404, detail=f"Viewer not found: {viewer_path}")

    _default_viewer_path = viewer_path
    return DefaultViewerResponse(viewer_path=_default_viewer_path)
