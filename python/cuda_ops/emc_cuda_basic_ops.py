"""
CUDA-accelerated basic array operations for emClarity.

This module provides GPU-accelerated implementations of basic array operations
using CuPy's RawKernel interface to load custom CUDA kernels.

All arrays use C-contiguous (row-major) memory layout for optimal
CUDA kernel performance and CuPy/NumPy compatibility.
"""

from pathlib import Path
from typing import Tuple

import cupy as cp

from .memory_utils import ensure_c, create_fortran_array

__all__ = ["CudaBasicOps"]


class CudaBasicOps:
    """
    CUDA-accelerated basic array operations.

    This class loads custom CUDA kernels and provides Python interfaces
    for GPU-accelerated array operations including addition, multiplication,
    and transposition.
    """

    def __init__(self):
        """Initialize CUDA kernels and setup GPU context."""
        self._kernels_loaded = False
        self._cuda_kernels = {}
        self._load_cuda_kernels()

    def _load_cuda_kernels(self):
        """Load CUDA kernels from the .cu file"""
        # First load the utility functions
        utils_file = Path(__file__).parent / "emc_cuda_utils.cuh"
        with open(utils_file) as f:
            utils_content = f.read()

        # Remove the header guards and includes to get just the function definitions
        utils_content = utils_content.replace("#ifndef EMC_CUDA_UTILS_CUH", "")
        utils_content = utils_content.replace("#define EMC_CUDA_UTILS_CUH", "")
        utils_content = utils_content.replace("#include <cuda_runtime.h>", "")
        utils_content = utils_content.replace("#endif // EMC_CUDA_UTILS_CUH", "")

        # Load the main CUDA file
        cuda_file = Path(__file__).parent / "emc_cuda_basic_ops.cu"
        with open(cuda_file) as f:
            cuda_source = f.read()

        # Replace the include with inline content
        cuda_source = cuda_source.replace(
            '#include "emc_cuda_utils.cuh"', utils_content
        )

        # Compile CUDA module
        try:
            self._cuda_module = cp.RawModule(code=cuda_source)

            # Load individual kernel functions
            self._cuda_kernels = {
                "add_arrays": self._cuda_module.get_function("cuda_add_arrays"),
                "multiply_scalar": self._cuda_module.get_function(
                    "cuda_multiply_scalar"
                ),
                "transpose_2d": self._cuda_module.get_function("cuda_transpose_2d"),
                "transpose_3d": self._cuda_module.get_function("cuda_transpose_3d"),
            }

            # Mark kernels as loaded
            self._kernels_loaded = True
            print(f"✅ Successfully loaded {len(self._cuda_kernels)} CUDA kernels")

        except Exception as e:
            print(f"❌ Failed to load CUDA kernels: {e}")
            self._kernels_loaded = False
            raise e

    def _calculate_grid_block(
        self, total_threads: int, block_size: int = 256
    ) -> Tuple[int, int]:
        """Calculate grid and block dimensions for 1D kernels."""
        blocks = (total_threads + block_size - 1) // block_size
        return (blocks,), (block_size,)

    def _calculate_grid_block_2d(
        self, ny: int, nx: int, threads_per_block_x: int = 16, threads_per_block_y: int = 16
    ) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Calculate launch parameters for 2D kernels.
        
        Args:
            ny: Number of elements in Y dimension
            nx: Number of elements in X dimension  
            threads_per_block_x: Threads per block in X dimension
            threads_per_block_y: Threads per block in Y dimension
            
        Returns:
            (num_blocks, threads_per_block) where:
            - num_blocks: (num_blocks_x, num_blocks_y) 
            - threads_per_block: (threads_per_block_x, threads_per_block_y)
        """
        num_blocks_x = (nx + threads_per_block_x - 1) // threads_per_block_x
        num_blocks_y = (ny + threads_per_block_y - 1) // threads_per_block_y
        
        num_blocks = (num_blocks_x, num_blocks_y)
        threads_per_block = (threads_per_block_x, threads_per_block_y)
        
        return num_blocks, threads_per_block

    def _calculate_grid_block_3d(
        self,
        nx: int,
        ny: int,
        nz: int,
        block_x: int = 8,
        block_y: int = 8,
        block_z: int = 8,
    ) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
        """Calculate grid and block dimensions for 3D kernels."""
        grid_x = (nx + block_x - 1) // block_x
        grid_y = (ny + block_y - 1) // block_y
        grid_z = (nz + block_z - 1) // block_z
        return (grid_x, grid_y, grid_z), (block_x, block_y, block_z)

    def add_arrays(self, a: cp.ndarray, b: cp.ndarray) -> cp.ndarray:
        """
        Element-wise addition of two arrays: c = a + b

        Args:
            a: First input array
            b: Second input array (must have same shape as a)

        Returns:
            Result array c = a + b

        Raises:
            ValueError: If arrays have different shapes
            RuntimeError: If CUDA kernels are not loaded
        """
        if not self._kernels_loaded:
            raise RuntimeError("CUDA kernels not loaded")

        if a.shape != b.shape:
            raise ValueError(f"Array shapes must match: {a.shape} vs {b.shape}")

                        # Ensure input is C-contiguous and proper dtype
        a = ensure_c(a, allow_copy=True, dtype=cp.float32)
        b = ensure_c(b, allow_copy=True, dtype=cp.float32)

        # Create output array - C-contiguous
        c = ensure_c(cp.empty(a.shape, dtype=cp.float32))  # C-contiguous by default

        # Calculate grid and block dimensions
        n = a.size
        grid, block = self._calculate_grid_block(n)

        # Launch kernel
        self._cuda_kernels["add_arrays"](
            grid, block, (a.data.ptr, b.data.ptr, c.data.ptr, n)
        )

        # Output is already C-contiguous, no need to ensure_c
        return c

    def multiply_scalar(self, a: cp.ndarray, scalar: float) -> cp.ndarray:
        """
        Multiply array by scalar: b = a * scalar

        Args:
            a: Input array
            scalar: Scalar value to multiply by

        Returns:
            Result array b = a * scalar

        Raises:
            RuntimeError: If CUDA kernels are not loaded
        """
        if not self._kernels_loaded:
            raise RuntimeError("CUDA kernels not loaded")

        # Ensure array is C-contiguous and float32
        a = ensure_c(a, allow_copy=False, dtype=cp.float32)

        # Create output array - C-contiguous
        b = cp.empty_like(a)

        # Calculate grid and block dimensions
        n = a.size
        grid, block = self._calculate_grid_block(n)

        # Launch kernel
        self._cuda_kernels["multiply_scalar"](
            grid, block, (a.data.ptr, b.data.ptr, cp.float32(scalar), n)
        )

        return ensure_c(b)  # Ensure output is C-contiguous

    def transpose_2d(self, a: cp.ndarray) -> cp.ndarray:
        """
        Transpose a 2D matrix.
        
        Input array shape: (ny, nx) - emClarity convention
        Output array shape: (nx, ny) - transposed

        Args:
            a: 2D input array

        Returns:
            Transposed array

        Raises:
            ValueError: If input is not 2D
            RuntimeError: If CUDA kernels are not loaded
        """
        if not self._kernels_loaded:
            raise RuntimeError("CUDA kernels not loaded")

        if a.ndim != 2:
            raise ValueError(f"Input must be 2D, got {a.ndim}D")

        # Ensure array is C-contiguous and float32
        a = ensure_c(a, allow_copy=False, dtype=cp.float32)

        ny, nx = a.shape  # emClarity convention: Y is first dim, X is second dim

        # Create output array with transposed shape - C-contiguous
        out = cp.empty((nx, ny), dtype=cp.float32)

        # Calculate kernel launch parameters based on input dimensions
        num_blocks, threads_per_block = self._calculate_grid_block_2d(ny, nx)

        # Launch kernel with (nx, ny) parameters matching cuda_transpose_2d signature
        self._cuda_kernels["transpose_2d"](
            num_blocks, threads_per_block, (a.data.ptr, out.data.ptr, nx, ny)
        )

        return ensure_c(out)  # Ensure output is C-contiguous

    def transpose_3d(self, a: cp.ndarray) -> cp.ndarray:
        """
        Transpose a 3D array following emClarity conventions.

        Input dimensions: (nz, ny, nx) - Z is slowest, X is fastest
        Output dimensions: (nx, ny, nz) - transpose (2,1,0)

        This follows the emClarity convention where:
        - X is the fastest dimension
        - Y is the second dimension
        - Z is the third/slowest dimension

        Args:
            a: 3D input array with shape (nz, ny, nx)

        Returns:
            Transposed array with shape (nx, ny, nz)

        Raises:
            ValueError: If input is not 3D
            RuntimeError: If CUDA kernels are not loaded
        """
        if not self._kernels_loaded:
            raise RuntimeError("CUDA kernels not loaded")

        if a.ndim != 3:
            raise ValueError(f"Input must be 3D, got {a.ndim}D")

        # Ensure array is contiguous and float32
        a = cp.ascontiguousarray(a, dtype=cp.float32)

        nz, ny, nx = a.shape

        # Create output array with transposed shape: (nz,ny,nx) -> (nx,ny,nz)
        out = cp.empty((nx, ny, nz), dtype=cp.float32)

        # Calculate grid and block dimensions
        grid, block = self._calculate_grid_block_3d(nx, ny, nz)

        # Launch kernel
        self._cuda_kernels["transpose_3d"](
            grid, block, (a.data.ptr, out.data.ptr, nx, ny, nz)
        )

        return out

    def is_ready(self) -> bool:
        """Check if CUDA kernels are loaded and ready to use."""
        return self._kernels_loaded
