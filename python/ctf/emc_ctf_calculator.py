"""
GPU-accelerated CTF computation using CuPy RawModule.

Loads the CUDA kernel from emc_ctf_kernels.cu and provides a Python
interface for computing 2-D CTF images.  Follows the CudaBasicOps
pattern from python/cuda_ops/emc_cuda_basic_ops.py.

The kernel replicates the exact math from mexFiles/utils/ctf.cu
lines 12-65 (basic CTF without exposure weighting).
"""

from __future__ import annotations

from pathlib import Path

import cupy as cp
import numpy as np

from .emc_ctf_params import CTFParams

__all__ = ["CTFCalculator"]


class CTFCalculator:
    """GPU-accelerated CTF calculator using custom CUDA kernels.

    Mirrors the CudaBasicOps pattern: load .cuh/.cu sources at init,
    inline the header, compile via ``cp.RawModule``, and expose a
    ``compute()`` method that launches the kernel.
    """

    def __init__(self) -> None:
        """Load and compile CUDA kernels.

        Raises:
            RuntimeError: If kernel compilation fails.  The message
                includes the .cu file path and the original compiler
                error text.
        """
        self._kernels_loaded: bool = False
        self._cuda_kernels: dict[str, cp.RawKernel] = {}
        self._load_cuda_kernels()

    def _load_cuda_kernels(self) -> None:
        """Load CUDA header and kernel source, inline, and compile."""
        cuda_dir = Path(__file__).parent / "cuda"

        header_file = cuda_dir / "emc_ctf_params.cuh"
        kernel_file = cuda_dir / "emc_ctf_kernels.cu"

        with open(header_file) as f:
            header_content = f.read()

        with open(kernel_file) as f:
            kernel_source = f.read()

        # Inline the header (same approach as CudaBasicOps)
        kernel_source = kernel_source.replace(
            '#include "emc_ctf_params.cuh"', header_content
        )

        try:
            self._cuda_module = cp.RawModule(
                code=kernel_source,
                options=("--use_fast_math",),
            )

            self._cuda_kernels = {
                "ctf_basic": self._cuda_module.get_function("ctf_basic"),
                "ctf_with_derivatives": self._cuda_module.get_function(
                    "ctf_with_derivatives"
                ),
            }
            self._kernels_loaded = True

        except cp.cuda.compiler.CompileException as exc:
            raise RuntimeError(
                f"Failed to compile CUDA CTF kernel from {kernel_file}: {exc}"
            ) from exc

    def _calculate_grid_block_2d(
        self,
        ny: int,
        nx: int,
        threads_x: int = 16,
        threads_y: int = 16,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Calculate 2-D grid and block dimensions for kernel launch.

        Args:
            ny: Number of output rows (y dimension).
            nx: Number of output columns (x dimension).
            threads_x: Threads per block in x.
            threads_y: Threads per block in y.

        Returns:
            ``(grid, block)`` tuples suitable for CuPy kernel launch.
        """
        blocks_x = (nx + threads_x - 1) // threads_x
        blocks_y = (ny + threads_y - 1) // threads_y
        return (blocks_x, blocks_y), (threads_x, threads_y)

    def compute(
        self,
        params: CTFParams,
        dims: tuple[int, int],
        centered: bool = False,
    ) -> cp.ndarray:
        """Compute a 2-D CTF image on the GPU.

        Args:
            params: Pre-computed CTF parameters (from
                ``CTFParams.from_defocus_pair``).
            dims: Real-space image dimensions ``(nx, ny)``.
            centered: If True, produce a centered (DC in the middle)
                CTF; otherwise use standard FFT ordering (DC at corner).

        Returns:
            CuPy float32 array of shape ``(ny, out_nx)`` in
            C-contiguous layout, where ``out_nx = nx//2+1`` when
            ``params.do_half_grid`` is True, else ``out_nx = nx``.

        Raises:
            RuntimeError: If CUDA kernels are not loaded.
            ValueError: If *pixel_size* or *wavelength* is zero.
        """
        if not self._kernels_loaded:
            raise RuntimeError("CUDA kernels not loaded")

        nx, ny = dims

        # Guard against degenerate parameters
        if float(params.pixel_size) == 0.0:
            raise ValueError("pixel_size must be non-zero")
        if float(params.wavelength) == 0.0:
            raise ValueError("wavelength must be non-zero")

        # Output dimensions
        out_nx = nx // 2 + 1 if params.do_half_grid else nx
        out_ny = ny

        # Origin (Nyquist indices)
        ox = nx // 2
        oy = ny // 2

        # Allocate C-contiguous output
        output = cp.empty((out_ny, out_nx), dtype=cp.float32)

        # Kernel launch configuration
        grid, block = self._calculate_grid_block_2d(out_ny, out_nx)

        # Pass pre-computed CTFParams values directly to avoid float32
        # non-associativity errors from re-deriving in the CUDA constructor.
        self._cuda_kernels["ctf_basic"](
            grid,
            block,
            (
                output,                                     # float*
                np.int32(nx),                               # int nx
                np.int32(ny),                               # int ny
                np.int32(ox),                               # int ox
                np.int32(oy),                               # int oy
                params.do_half_grid,                        # bool
                params.do_sq_ctf,                           # bool
                np.float32(params.pixel_size),              # float
                np.float32(params.wavelength),              # float
                np.float32(params.cs_internal),             # float
                np.float32(params.amplitude_phase),         # float
                np.float32(params.mean_defocus),            # float
                np.float32(params.half_astigmatism),        # float
                np.float32(params.astigmatism_angle_rad),   # float
                np.float32(params.cs_term),                 # float
                np.float32(params.df_term),                 # float
                centered,                                   # bool
            ),
        )

        return output

    def compute_with_derivatives(
        self,
        params: CTFParams,
        dims: tuple[int, int],
        centered: bool = False,
    ) -> tuple[cp.ndarray, cp.ndarray, cp.ndarray, cp.ndarray]:
        """Compute CTF and analytical derivatives on the GPU.

        Returns the CTF image and its partial derivatives with respect to
        mean_defocus (D), half_astigmatism (A), and astigmatism_angle (theta).
        The theta derivative is in per-degree units.

        Args:
            params: Pre-computed CTF parameters.
            dims: Real-space image dimensions ``(nx, ny)``.
            centered: If True, produce a centered CTF.

        Returns:
            Tuple of four CuPy float32 arrays
            ``(ctf, dctf_dD, dctf_dA, dctf_dTheta)``, each with shape
            ``(ny, out_nx)`` in C-contiguous layout.

        Raises:
            RuntimeError: If CUDA kernels are not loaded.
            ValueError: If *pixel_size* or *wavelength* is zero.
        """
        if not self._kernels_loaded:
            raise RuntimeError("CUDA kernels not loaded")

        nx, ny = dims

        if float(params.pixel_size) == 0.0:
            raise ValueError("pixel_size must be non-zero")
        if float(params.wavelength) == 0.0:
            raise ValueError("wavelength must be non-zero")

        out_nx = nx // 2 + 1 if params.do_half_grid else nx
        out_ny = ny
        ox = nx // 2
        oy = ny // 2

        # Allocate C-contiguous output arrays
        ctf_out = cp.empty((out_ny, out_nx), dtype=cp.float32)
        dctf_dD = cp.empty((out_ny, out_nx), dtype=cp.float32)
        dctf_dA = cp.empty((out_ny, out_nx), dtype=cp.float32)
        dctf_dTheta = cp.empty((out_ny, out_nx), dtype=cp.float32)

        grid, block = self._calculate_grid_block_2d(out_ny, out_nx)

        # Pass pre-computed CTFParams values directly.
        self._cuda_kernels["ctf_with_derivatives"](
            grid,
            block,
            (
                ctf_out,                                    # float*
                dctf_dD,                                    # float*
                dctf_dA,                                    # float*
                dctf_dTheta,                                # float*
                np.int32(nx),                               # int nx
                np.int32(ny),                               # int ny
                np.int32(ox),                               # int ox
                np.int32(oy),                               # int oy
                params.do_half_grid,                        # bool
                params.do_sq_ctf,                           # bool
                np.float32(params.pixel_size),              # float
                np.float32(params.wavelength),              # float
                np.float32(params.cs_internal),             # float
                np.float32(params.amplitude_phase),         # float
                np.float32(params.mean_defocus),            # float
                np.float32(params.half_astigmatism),        # float
                np.float32(params.astigmatism_angle_rad),   # float
                np.float32(params.cs_term),                 # float
                np.float32(params.df_term),                 # float
                centered,                                   # bool
            ),
        )

        return ctf_out, dctf_dD, dctf_dA, dctf_dTheta

    def is_ready(self) -> bool:
        """Check if CUDA kernels are loaded and ready."""
        return self._kernels_loaded
