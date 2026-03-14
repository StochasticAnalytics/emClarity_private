"""V1 API endpoints for system information (GPU, CPU, memory).

Routes:
    GET /api/v1/system/info - Full system information
    GET /api/v1/system/gpus - Detect available NVIDIA GPUs
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.services.system_service import GpuInfo, SystemInfo, SystemService

router = APIRouter(prefix="/api/v1/system", tags=["system-v1"])

_service = SystemService()


@router.get("/info", response_model=SystemInfo)
async def get_system_info_v1() -> SystemInfo:
    """Return system information including CPU cores, RAM, hostname, and GPUs."""
    return _service.get_system_info()


@router.get("/gpus", response_model=list[GpuInfo])
async def detect_gpus_v1() -> list[GpuInfo]:
    """Detect NVIDIA GPUs via nvidia-smi.

    Returns an empty list if no GPUs are found or nvidia-smi is
    not available.
    """
    return _service.detect_gpus()
