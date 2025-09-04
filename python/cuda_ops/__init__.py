"""
cuda_ops package

CUDA-accelerated operations for emClarity Python conversion.
Provides high-performance GPU implementations of common array operations.

Author: emClarity Python Conversion
Date: September 2025
"""

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False

if CUDA_AVAILABLE:
    from .basic_array_ops import (
        BasicArrayOps,
        cuda_array_add,
        cuda_array_scale,
        cuda_transpose_2d,
        cuda_transpose_3d_xy,
    )

    # Explicitly export these for the package API
    __all__ = [
        "CUDA_AVAILABLE",
        "BasicArrayOps",
        "cuda_array_add",
        "cuda_array_scale",
        "cuda_transpose_2d",
        "cuda_transpose_3d_xy",
    ]

    __all__ = [
        "CUDA_AVAILABLE",
        "BasicArrayOps",
        "cuda_array_add",
        "cuda_array_scale",
        "cuda_transpose_2d",
        "cuda_transpose_3d_xy",
    ]
else:
    __all__ = ["CUDA_AVAILABLE"]

__version__ = "0.1.0"
