"""
basic_array_ops.py

Python wrapper for basic CUDA array operations using CuPy RawKernel.
This establishes the pattern for Python ↔ CUDA integration in emClarity.

Author: emClarity Python Conversion
Date: September 2025
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

import cupy as cp
import numpy as np

logger = logging.getLogger(__name__)


class BasicArrayOps:
    """
    CUDA-accelerated basic array operations using CuPy RawKernel.

    This class demonstrates the architecture pattern for Python-CUDA integration:
    1. Load CUDA kernels from .cu files
    2. Manage GPU memory and execution
    3. Provide Python-friendly interfaces
    """

    def __init__(self):
        """Initialize CUDA kernels and set up execution parameters."""
        self._kernels = {}
        self._load_cuda_kernels()

    def _load_cuda_kernels(self):
        """Load CUDA kernels from the .cu file using CuPy RawModule."""
        try:
            # First load the utility functions
            utils_file = Path(__file__).parent / "emc_cuda_utils.cuh"
            with open(utils_file) as f:
                utils_content = f.read()

            # Remove the header guards and includes to get just the function definitions
            utils_content = utils_content.replace("#ifndef EMC_CUDA_UTILS_CUH", "")
            utils_content = utils_content.replace("#define EMC_CUDA_UTILS_CUH", "")
            utils_content = utils_content.replace("#include <cuda_runtime.h>", "")
            utils_content = utils_content.replace("#endif // EMC_CUDA_UTILS_CUH", "")

            # Get the path to the .cu file
            cu_file_path = Path(__file__).parent / "basic_array_ops.cu"

            if not cu_file_path.exists():
                raise FileNotFoundError(f"CUDA file not found: {cu_file_path}")

            # Read the CUDA source code
            with open(cu_file_path) as f:
                cuda_source = f.read()

            # Replace the include with inline content
            cuda_source = cuda_source.replace(
                '#include "emc_cuda_utils.cuh"', utils_content
            )

            # Compile the CUDA module
            self._cuda_module = cp.RawModule(code=cuda_source)

            # Get kernel functions
            self._kernels["array_add"] = self._cuda_module.get_function("array_add")
            self._kernels["array_scale"] = self._cuda_module.get_function("array_scale")
            self._kernels["transpose_2d"] = self._cuda_module.get_function(
                "transpose_2d"
            )
            self._kernels["transpose_3d_xy"] = self._cuda_module.get_function(
                "transpose_3d_xy"
            )
            self._kernels["vector_magnitude_squared"] = self._cuda_module.get_function(
                "vector_magnitude_squared"
            )

            logger.info(f"Successfully loaded {len(self._kernels)} CUDA kernels")

        except Exception as e:
            logger.error(f"Failed to load CUDA kernels: {e}")
            raise

    def _calculate_grid_size(
        self, n_elements: int, block_size: int = 256
    ) -> Tuple[int, int]:
        """
        Calculate optimal grid and block sizes for 1D kernels.

        Args:
            n_elements: Total number of elements to process
            block_size: Number of threads per block

        Returns:
            Tuple of (grid_size, block_size)
        """
        grid_size = (n_elements + block_size - 1) // block_size
        return grid_size, block_size

    def _calculate_2d_grid_size(
        self, shape: Tuple[int, int], block_size: Tuple[int, int] = (16, 16)
    ) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Calculate optimal grid and block sizes for 2D kernels.

        Args:
            shape: (rows, cols) of the 2D array
            block_size: (block_x, block_y) threads per block

        Returns:
            Tuple of ((grid_x, grid_y), (block_x, block_y))
        """
        rows, cols = shape
        block_x, block_y = block_size

        grid_x = (cols + block_x - 1) // block_x
        grid_y = (rows + block_y - 1) // block_y

        return (grid_x, grid_y), (block_x, block_y)

    def _calculate_3d_grid_size(
        self, shape: Tuple[int, int, int], block_size: Tuple[int, int, int] = (8, 8, 8)
    ) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
        """
        Calculate optimal grid and block sizes for 3D kernels.

        Args:
            shape: (nx, ny, nz) of the 3D array
            block_size: (block_x, block_y, block_z) threads per block

        Returns:
            Tuple of ((grid_x, grid_y, grid_z), (block_x, block_y, block_z))
        """
        nx, ny, nz = shape
        block_x, block_y, block_z = block_size

        grid_x = (nx + block_x - 1) // block_x
        grid_y = (ny + block_y - 1) // block_y
        grid_z = (nz + block_z - 1) // block_z

        return (grid_x, grid_y, grid_z), (block_x, block_y, block_z)

    def array_add(
        self, a: cp.ndarray, b: cp.ndarray, output: Optional[cp.ndarray] = None
    ) -> cp.ndarray:
        """
        Element-wise addition of two arrays using CUDA.

        Args:
            a: First input array
            b: Second input array
            output: Optional pre-allocated output array

        Returns:
            Result array containing a + b
        """
        if a.shape != b.shape:
            raise ValueError(f"Array shapes must match: {a.shape} vs {b.shape}")

        if a.dtype != np.float32 or b.dtype != np.float32:
            raise ValueError("Arrays must be float32")

        n_elements = a.size

        # Allocate output array if not provided
        if output is None:
            output = cp.empty_like(a)
        elif output.shape != a.shape:
            raise ValueError(
                f"Output shape {output.shape} doesn't match input {a.shape}"
            )

        # Calculate grid and block sizes
        grid_size, block_size = self._calculate_grid_size(n_elements)

        # Launch CUDA kernel
        self._kernels["array_add"](
            (grid_size,), (block_size,), (a, b, output, n_elements)
        )

        return output

    def array_scale(
        self,
        input_array: cp.ndarray,
        scale_factor: float,
        output: Optional[cp.ndarray] = None,
    ) -> cp.ndarray:
        """
        Scale array elements by a constant factor using CUDA.

        Args:
            input_array: Input array to scale
            scale_factor: Scaling factor
            output: Optional pre-allocated output array

        Returns:
            Scaled array
        """
        if input_array.dtype != np.float32:
            raise ValueError("Array must be float32")

        n_elements = input_array.size

        # Allocate output array if not provided
        if output is None:
            output = cp.empty_like(input_array)
        elif output.shape != input_array.shape:
            raise ValueError(
                f"Output shape {output.shape} doesn't match input {input_array.shape}"
            )

        # Calculate grid and block sizes
        grid_size, block_size = self._calculate_grid_size(n_elements)

        # Launch CUDA kernel
        self._kernels["array_scale"](
            (grid_size,),
            (block_size,),
            (input_array, output, np.float32(scale_factor), n_elements),
        )

        return output

    def transpose_2d(
        self, input_array: cp.ndarray, output: Optional[cp.ndarray] = None
    ) -> cp.ndarray:
        """
        Transpose a 2D array using CUDA (tests memory indexing).

        Args:
            input_array: 2D input array to transpose
            output: Optional pre-allocated output array

        Returns:
            Transposed array
        """
        if input_array.ndim != 2:
            raise ValueError(f"Array must be 2D, got {input_array.ndim}D")

        if input_array.dtype != np.float32:
            raise ValueError("Array must be float32")

        rows, cols = input_array.shape

        # Allocate output array if not provided
        if output is None:
            output = cp.empty((cols, rows), dtype=input_array.dtype)
        elif output.shape != (cols, rows):
            raise ValueError(
                f"Output shape {output.shape} doesn't match expected {(cols, rows)}"
            )

        # Calculate 2D grid and block sizes
        grid_size, block_size = self._calculate_2d_grid_size((rows, cols))

        # Launch CUDA kernel
        self._kernels["transpose_2d"](
            grid_size, block_size, (input_array, output, rows, cols)
        )

        return output

    def transpose_3d_xy(
        self, input_array: cp.ndarray, output: Optional[cp.ndarray] = None
    ) -> cp.ndarray:
        """
        Transpose X and Y dimensions of a 3D array using CUDA.

        Args:
            input_array: 3D input array (nx, ny, nz)
            output: Optional pre-allocated output array

        Returns:
            Transposed array (ny, nx, nz)
        """
        if input_array.ndim != 3:
            raise ValueError(f"Array must be 3D, got {input_array.ndim}D")

        if input_array.dtype != np.float32:
            raise ValueError("Array must be float32")

        nx, ny, nz = input_array.shape

        # Allocate output array if not provided
        if output is None:
            output = cp.empty((ny, nx, nz), dtype=input_array.dtype)
        elif output.shape != (ny, nx, nz):
            raise ValueError(
                f"Output shape {output.shape} doesn't match expected {(ny, nx, nz)}"
            )

        # Calculate 3D grid and block sizes
        grid_size, block_size = self._calculate_3d_grid_size((nx, ny, nz))

        # Launch CUDA kernel
        self._kernels["transpose_3d_xy"](
            grid_size, block_size, (input_array, output, nx, ny, nz)
        )

        return output

    def vector_magnitude_squared(
        self, input_array: cp.ndarray, output: Optional[cp.ndarray] = None
    ) -> cp.ndarray:
        """
        Compute element-wise squared magnitude using CUDA.

        Args:
            input_array: Input array
            output: Optional pre-allocated output array

        Returns:
            Array of squared magnitudes
        """
        if input_array.dtype != np.float32:
            raise ValueError("Array must be float32")

        n_elements = input_array.size

        # Allocate output array if not provided
        if output is None:
            output = cp.empty_like(input_array)
        elif output.shape != input_array.shape:
            raise ValueError(
                f"Output shape {output.shape} doesn't match input {input_array.shape}"
            )

        # Calculate grid and block sizes
        grid_size, block_size = self._calculate_grid_size(n_elements)

        # Launch CUDA kernel
        self._kernels["vector_magnitude_squared"](
            (grid_size,), (block_size,), (input_array, output, n_elements)
        )

        return output


# Convenience functions for easy access
def cuda_array_add(a: cp.ndarray, b: cp.ndarray) -> cp.ndarray:
    """Convenience function for CUDA array addition."""
    ops = BasicArrayOps()
    return ops.array_add(a, b)


def cuda_array_scale(input_array: cp.ndarray, scale_factor: float) -> cp.ndarray:
    """Convenience function for CUDA array scaling."""
    ops = BasicArrayOps()
    return ops.array_scale(input_array, scale_factor)


def cuda_transpose_2d(input_array: cp.ndarray) -> cp.ndarray:
    """Convenience function for CUDA 2D transpose."""
    ops = BasicArrayOps()
    return ops.transpose_2d(input_array)


def cuda_transpose_3d_xy(input_array: cp.ndarray) -> cp.ndarray:
    """Convenience function for CUDA 3D XY transpose."""
    ops = BasicArrayOps()
    return ops.transpose_3d_xy(input_array)
