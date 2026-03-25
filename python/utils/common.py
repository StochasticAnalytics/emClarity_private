"""
Common utilities for emClarity Python modules.

This module provides shared functionality used across multiple emClarity
Python modules to reduce code duplication and ensure consistency.
"""

import logging
import warnings
from pathlib import Path
from typing import Any

import numpy as np

# GPU support detection
try:
    import cupy as cp

    HAS_CUPY = True

    # Test if CUDA is actually functional
    try:
        cp.cuda.runtime.getDeviceCount()
    except Exception:
        HAS_CUPY = False
        cp = None

except ImportError:
    HAS_CUPY = False
    cp = None

logger = logging.getLogger(__name__)


class GPUContext:
    """Manages GPU context and provides fallback to CPU when needed."""

    def __init__(self):
        """Initialize GPU context and detect available devices."""
        self.has_gpu = HAS_CUPY
        self.device_count = 0
        self.current_device = 0

        if self.has_gpu:
            try:
                self.device_count = cp.cuda.runtime.getDeviceCount()
                self.current_device = cp.cuda.runtime.getDevice()
                logger.info(
                    f"CUDA available with {self.device_count} device(s), using device {self.current_device}"
                )
            except Exception as e:
                logger.warning(f"CUDA detected but not functional: {e}")
                self.has_gpu = False

    def get_array_module(self, array: Any):
        """Get appropriate array module (numpy or cupy) for given array."""
        if self.has_gpu and hasattr(array, "__cuda_array_interface__"):
            return cp
        return np

    def ensure_array_type(
        self, array: Any, prefer_gpu: bool = False
    ) -> tuple[Any, Any]:
        """
        Ensure array is proper type and return (array, array_module).

        Args:
            array: Input array (numpy or cupy)
            prefer_gpu: Try to move to GPU if available

        Returns:
            (processed_array, array_module)
        """
        if not self.has_gpu:
            return np.asarray(array), np

        if prefer_gpu and not hasattr(array, "__cuda_array_interface__"):
            try:
                return cp.asarray(array), cp
            except Exception as e:
                logger.warning(f"Could not move array to GPU: {e}")
                return np.asarray(array), np

        # Return as-is with appropriate module
        xp = self.get_array_module(array)
        return array, xp

    def set_device(self, device_id: int):
        """Set the current CUDA device."""
        if self.has_gpu and 0 <= device_id < self.device_count:
            cp.cuda.runtime.setDevice(device_id)
            self.current_device = device_id
            logger.info(f"Set CUDA device to {device_id}")
        else:
            logger.warning(
                f"Cannot set device {device_id} (available: 0-{self.device_count - 1})"
            )


def validate_array_dimensions(
    array: Any, expected_dims: int, name: str = "array"
) -> None:
    """Validate array has expected number of dimensions."""
    if array.ndim != expected_dims:
        raise ValueError(
            f"{name} must be {expected_dims}D, got {array.ndim}D array with shape {array.shape}"
        )


def validate_array_shape_compatibility(
    arr1: Any, arr2: Any, operation: str = "operation"
) -> None:
    """Validate two arrays have compatible shapes for element-wise operations."""
    if arr1.shape != arr2.shape:
        raise ValueError(
            f"Array shapes incompatible for {operation}: {arr1.shape} vs {arr2.shape}"
        )


def validate_array_dtype(
    array: Any, expected_dtypes: type | tuple[type, ...], name: str = "array"
) -> None:
    """Validate array has expected data type."""
    if isinstance(expected_dtypes, type):
        expected_dtypes = (expected_dtypes,)

    if array.dtype not in expected_dtypes:
        expected_str = " or ".join(str(dt) for dt in expected_dtypes)
        raise ValueError(f"{name} must have dtype {expected_str}, got {array.dtype}")


def safe_file_path(
    path: str | Path, must_exist: bool = True, create_parent: bool = False
) -> Path:
    """
    Safely convert and validate file path.

    Args:
        path: File path as string or Path object
        must_exist: Whether file must already exist
        create_parent: Create parent directory if it doesn't exist

    Returns:
        Validated Path object
    """
    path_obj = Path(path).expanduser().resolve()

    if create_parent:
        path_obj.parent.mkdir(parents=True, exist_ok=True)

    if must_exist and not path_obj.exists():
        raise FileNotFoundError(f"File not found: {path_obj}")

    return path_obj


def ensure_temp_directory(temp_dir: Path | None = None) -> Path:
    """
    Ensure temporary directory exists and return its path.

    Args:
        temp_dir: Custom temporary directory, or None for default

    Returns:
        Path to temporary directory
    """
    if temp_dir is None:
        temp_dir = DEFAULT_TEMP_DIR

    temp_dir = Path(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def setup_logging(
    level: int = logging.INFO,
    format_string: str | None = None,
    include_cuda_info: bool = True,
) -> None:
    """Setup consistent logging for emClarity modules."""
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(level=level, format=format_string)

    if include_cuda_info:
        logger = logging.getLogger(__name__)
        if HAS_CUPY:
            try:
                device_count = cp.cuda.runtime.getDeviceCount()
                current_device = cp.cuda.runtime.getDevice()
                logger.info(
                    f"CUDA initialized: {device_count} device(s), current device: {current_device}"
                )
            except Exception as e:
                logger.warning(f"CUDA available but not functional: {e}")
        else:
            logger.info("CUDA not available, using CPU-only mode")


def deprecated_warning(old_name: str, new_name: str, version: str = "2.0.0") -> None:
    """Issue deprecation warning for old function names."""
    warnings.warn(
        f"{old_name} is deprecated and will be removed in version {version}. "
        f"Use {new_name} instead.",
        DeprecationWarning,
        stacklevel=3,
    )


def memory_info() -> dict[str, Any]:
    """Get memory information for debugging."""
    info = {"cpu_memory_available": True, "gpu_memory_available": HAS_CUPY}

    if HAS_CUPY:
        try:
            mempool = cp.get_default_memory_pool()
            info.update(
                {
                    "gpu_memory_used": mempool.used_bytes(),
                    "gpu_memory_total": mempool.total_bytes(),
                    "gpu_device_count": cp.cuda.runtime.getDeviceCount(),
                    "gpu_current_device": cp.cuda.runtime.getDevice(),
                }
            )
        except Exception as e:
            info["gpu_memory_error"] = str(e)

    return info


# Shared constants
DEFAULT_TEMP_DIR = Path("/tmp/copilot-test")
EMCLARITY_PYTHON_VERSION = "1.0.0"

# Ensure temp directory exists
DEFAULT_TEMP_DIR.mkdir(exist_ok=True)

# Global GPU context instance
gpu_context = GPUContext()
