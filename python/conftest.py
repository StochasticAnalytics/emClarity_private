"""Shared pytest configuration for emClarity Python test suites.

Provides:
- Session-scoped GPU/CuPy consistency check: fails loudly when GPU hardware
  is detected but CuPy cannot be imported or initialized.
- Project-wide fixtures consumed by multiple test modules.
"""

import shutil
import subprocess

import pytest


@pytest.fixture(scope="session", autouse=True)
def _assert_cupy_when_gpu_present():
    """Assert CuPy is importable on machines that have NVIDIA GPU hardware.

    When GPU hardware is detected but CuPy is missing, tests silently skip
    instead of running on the GPU.  This fixture surfaces that configuration
    gap at session start rather than hiding it behind per-test skips.
    """
    if shutil.which("nvidia-smi") is None:
        return  # No GPU tooling detected; GPU check not applicable.

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        gpu_present = result.returncode == 0 and bool(result.stdout.strip())
    except Exception as exc:
        import warnings

        warnings.warn(f"nvidia-smi query failed: {exc}", stacklevel=1)
        gpu_present = False

    if not gpu_present:
        return

    try:
        import cupy  # noqa: F401
    except ImportError:
        pytest.fail(
            "NVIDIA GPU detected but CuPy is not importable. "
            "Install the GPU extras: pip install 'emclarity[gpu]'"
        )
