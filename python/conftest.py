"""
Centralized tolerance constants for emClarity Python test suites.

These values reflect the expected numerical differences between computation
paths (GPU vs CPU, float32 vs float64, analytical vs finite-difference).
Import them in test modules or use the corresponding pytest fixtures for
auto-injection.
"""

import pytest

# float32 + --use_fast_math compiler differences (GPU kernels vs MATLAB reference)
GPU_VS_MATLAB_ATOL = 1e-4

# Same formula, float32 vs float64 accumulation order differences
GPU_VS_CPU_RTOL = 1e-5

# Single float32 operation tolerance (e.g., one multiply or add)
FLOAT32_PARAM_ATOL = 1e-6

# Finite-difference gradient vs analytical gradient relative tolerance
FD_GRADIENT_RTOL = 0.02


# ---------------------------------------------------------------------------
# Fixtures — auto-available to all tests under python/
# ---------------------------------------------------------------------------


@pytest.fixture
def gpu_vs_matlab_atol() -> float:
    """GPU vs MATLAB absolute tolerance (float32 + fast-math)."""
    return GPU_VS_MATLAB_ATOL


@pytest.fixture
def gpu_vs_cpu_rtol() -> float:
    """GPU vs CPU relative tolerance (float64 accumulation order)."""
    return GPU_VS_CPU_RTOL


@pytest.fixture
def float32_param_atol() -> float:
    """Single float32 operation absolute tolerance."""
    return FLOAT32_PARAM_ATOL


@pytest.fixture
def fd_gradient_rtol() -> float:
    """Finite-difference vs analytical gradient relative tolerance."""
    return FD_GRADIENT_RTOL
