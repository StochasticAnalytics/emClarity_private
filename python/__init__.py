"""
emClarity Python Package

This package contains Python conversions of emClarity's cryo-EM processing
functionality.
"""

__version__ = "1.0.0"
__author__ = "emClarity Development Team"

# Top-level imports for commonly used modules
from .masking import emc_pad_zeros_3d

# Core parameter management system
from .parameters import (
    ParameterDefinition,
    UnifiedParameterManager,
    get_parameter_manager,
)

# Optional CUDA support
try:
    from .cuda_ops import CudaBasicOps

    HAS_CUDA = True
except ImportError:
    HAS_CUDA = False

# Explicitly export public API
__all__ = [
    "emc_pad_zeros_3d",
    "ParameterDefinition",
    "UnifiedParameterManager",
    "get_parameter_manager",
    "HAS_CUDA",
]

# Add CUDA ops to exports if available
if HAS_CUDA:
    __all__.append("CudaBasicOps")

__all__ = [
    "UnifiedParameterManager",
    "ParameterDefinition",
    "get_parameter_manager",
    "emc_pad_zeros_3d",
    "HAS_CUDA",
]

if HAS_CUDA:
    __all__.append("CudaBasicOps")
