"""API endpoints for system information (GPU, CPU, memory).

Routes:
    GET /api/system/gpus - Detect available NVIDIA GPUs
    GET /api/system/info - Full system information
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.services.system_service import GpuInfo, SystemInfo, SystemService

router = APIRouter(prefix="/api/system", tags=["system"])

_service = SystemService()


@router.get("/gpus", response_model=list[GpuInfo])
async def detect_gpus() -> list[GpuInfo]:
    """Detect NVIDIA GPUs via nvidia-smi.

    Returns an empty list if no GPUs are found or nvidia-smi is
    not available.
    """
    return _service.detect_gpus()


@router.get("/info", response_model=SystemInfo)
async def get_system_info() -> SystemInfo:
    """Return system information including CPU cores, RAM, and GPUs."""
    return _service.get_system_info()
