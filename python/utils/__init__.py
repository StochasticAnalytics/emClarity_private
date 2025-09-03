"""
emClarity Python utilities package

This package contains common utilities used across emClarity Python modules.
"""

from .common import (DEFAULT_TEMP_DIR, EMCLARITY_PYTHON_VERSION, HAS_CUPY,
                     GPUContext, deprecated_warning, ensure_temp_directory,
                     gpu_context, memory_info, safe_file_path, setup_logging,
                     validate_array_dimensions, validate_array_dtype,
                     validate_array_shape_compatibility)

__all__ = [
    "GPUContext",
    "gpu_context",
    "validate_array_dimensions",
    "validate_array_shape_compatibility",
    "validate_array_dtype",
    "safe_file_path",
    "ensure_temp_directory",
    "setup_logging",
    "deprecated_warning",
    "memory_info",
    "HAS_CUPY",
    "DEFAULT_TEMP_DIR",
    "EMCLARITY_PYTHON_VERSION",
]
__version__ = "1.0.0"
