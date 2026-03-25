"""
emClarity Python Package.

This package contains Python conversions of emClarity's cryo-EM processing
functionality.
"""

__version__ = "1.7.0"
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
    from .cuda_ops import BasicArrayOps

    HAS_CUDA = True
except ImportError:
    HAS_CUDA = False

# Explicitly export public API
__all__ = [
    "HAS_CUDA",
    "ParameterDefinition",
    "UnifiedParameterManager",
    "emc_pad_zeros_3d",
    "get_parameter_manager",
]

# Add CUDA ops to exports if available
if HAS_CUDA:
    __all__.append("BasicArrayOps")
