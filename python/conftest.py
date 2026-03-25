"""Shared pytest configuration for emClarity Python test suites.

Provides:
- Session-scoped GPU/CuPy consistency check: fails loudly when GPU hardware
  is detected but CuPy cannot be imported or initialized.
- Project-wide fixtures consumed by multiple test modules.
"""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _verify_gpu_cupy_consistency() -> None:
    """Assert CuPy is usable when NVIDIA GPU hardware is present.

    Checks /dev/nvidia0 as a proxy for GPU availability.  If the device
    exists but CuPy fails to import or cannot allocate on the device, the
    entire test session fails with a clear diagnostic rather than silently
    skipping GPU tests.
    """
    gpu_detected = os.path.exists("/dev/nvidia0")
    if not gpu_detected:
        return

    try:
        import cupy as cp

        cp.array([1.0])
    except Exception as exc:
        pytest.fail(
            f"GPU detected (/dev/nvidia0 exists) but CuPy is unusable: {exc}\n"
            "Install a compatible CuPy wheel or fix the CUDA environment."
        )
