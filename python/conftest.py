"""
Centralized tolerance constants for emClarity Python test suites.

These values reflect the expected numerical differences between computation
paths (GPU vs CPU, float32 vs float64, analytical vs finite-difference).
Import them in test modules to ensure consistent tolerance usage.
"""

# float32 + --use_fast_math compiler differences (GPU kernels vs MATLAB reference)
GPU_VS_MATLAB_ATOL = 1e-4

# Same formula, float32 vs float64 accumulation order differences
GPU_VS_CPU_RTOL = 1e-5

# Single float32 operation tolerance (e.g., one multiply or add)
FLOAT32_PARAM_ATOL = 1e-6

# Finite-difference gradient vs analytical gradient relative tolerance
FD_GRADIENT_RTOL = 0.02
