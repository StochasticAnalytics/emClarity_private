"""
emClarity Python utilities package

This package contains common utilities used across emClarity Python modules.
"""

from .common import (
    GPUContext, 
    gpu_context,
    validate_array_dimensions,
    validate_array_shape_compatibility,
    validate_array_dtype,
    safe_file_path,
    ensure_temp_directory,
    setup_logging,
    deprecated_warning,
    memory_info,
    HAS_CUPY,
    DEFAULT_TEMP_DIR,
    EMCLARITY_PYTHON_VERSION
)

__all__ = [
    'GPUContext',
    'gpu_context', 
    'validate_array_dimensions',
    'validate_array_shape_compatibility',
    'validate_array_dtype',
    'safe_file_path',
    'ensure_temp_directory',
    'setup_logging',
    'deprecated_warning',
    'memory_info',
    'HAS_CUPY',
    'DEFAULT_TEMP_DIR',
    'EMCLARITY_PYTHON_VERSION'
]
__version__ = '1.0.0'
