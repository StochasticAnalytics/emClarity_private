"""
Acceptance tests: System Information
=====================================

These tests verify that the backend correctly detects and reports hardware
capabilities.  The frontend uses this information to:

  - Set sensible defaults for nGPUs and nCpuCores
  - Warn users if no GPU is available
  - Display system status in the dashboard
"""

import pytest
import httpx


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

SYSTEM_INFO_ENDPOINT = "/api/v1/system/info"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_system_info_returns_200(api_client: httpx.AsyncClient):
    """The system info endpoint must respond successfully."""
    response = await api_client.get(SYSTEM_INFO_ENDPOINT)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio
async def test_get_system_info_returns_cpu_count(
    api_client: httpx.AsyncClient,
):
    """The system info must include a ``cpu_count`` field with a positive
    integer value.  The frontend uses this to set the default for nCpuCores.
    """
    response = await api_client.get(SYSTEM_INFO_ENDPOINT)
    assert response.status_code == 200
    data = response.json()

    cpu_count = data.get("cpu_count")
    assert cpu_count is not None, (
        "System info must include 'cpu_count'"
    )
    assert isinstance(cpu_count, int) and cpu_count > 0, (
        f"cpu_count must be a positive integer, got: {cpu_count}"
    )


@pytest.mark.asyncio
async def test_gpu_detection_returns_list(api_client: httpx.AsyncClient):
    """The system info must include a ``gpus`` field that is a list.

    The list may be empty (no GPU available) or contain objects describing
    each detected GPU.  The frontend uses this to populate the GPU selector.
    """
    response = await api_client.get(SYSTEM_INFO_ENDPOINT)
    assert response.status_code == 200
    data = response.json()

    gpus = data.get("gpus")
    assert gpus is not None, "System info must include 'gpus' field"
    assert isinstance(gpus, list), (
        f"'gpus' must be a list, got {type(gpus).__name__}"
    )

    # If GPUs are present, each entry should have at least a name
    for i, gpu in enumerate(gpus):
        assert isinstance(gpu, dict), (
            f"GPU entry {i} must be a dict, got {type(gpu).__name__}"
        )
        assert "name" in gpu, (
            f"GPU entry {i} must have a 'name' field"
        )


@pytest.mark.asyncio
async def test_system_info_includes_memory(api_client: httpx.AsyncClient):
    """The system info should include available memory information so the
    frontend can warn about insufficient resources."""
    response = await api_client.get(SYSTEM_INFO_ENDPOINT)
    assert response.status_code == 200
    data = response.json()

    # At minimum, total system memory should be reported
    memory = data.get("memory_total_gb") or data.get("memory_gb") or data.get("memory")
    assert memory is not None, (
        "System info should include memory information "
        "(field: memory_total_gb, memory_gb, or memory)"
    )


@pytest.mark.asyncio
async def test_system_info_includes_hostname(api_client: httpx.AsyncClient):
    """The system info should include the hostname for display in the
    dashboard header."""
    response = await api_client.get(SYSTEM_INFO_ENDPOINT)
    assert response.status_code == 200
    data = response.json()

    hostname = data.get("hostname")
    assert hostname is not None, (
        "System info should include 'hostname'"
    )
    assert isinstance(hostname, str) and len(hostname) > 0, (
        f"hostname must be a non-empty string, got: {hostname!r}"
    )
