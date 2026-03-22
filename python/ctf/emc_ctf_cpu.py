"""
Pure-NumPy CPU implementation of the CTF computation.

Serves as a fallback when CuPy / CUDA is unavailable.  The math
replicates mexFiles/utils/ctf.cu lines 12-65 exactly, using the
pre-computed derived quantities stored in CTFParams.

Output layout: C-contiguous float32, shape (ny, out_nx).
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

from .emc_ctf_params import CTFParams

__all__ = ["CTFCalculatorCPU"]


class CTFCalculatorCPU:
    """CPU-only CTF calculator using NumPy.

    Drop-in replacement for ``CTFCalculator`` when no GPU is available.
    """

    def compute(
        self,
        params: CTFParams,
        dims: Tuple[int, int],
        centered: bool = False,
    ) -> np.ndarray:
        """Compute a 2-D CTF image on the CPU.

        Args:
            params: Pre-computed CTF parameters.
            dims: Real-space image dimensions ``(nx, ny)``.
            centered: If True, DC is at the centre of the output;
                otherwise standard FFT ordering (DC at corner).

        Returns:
            NumPy float32 array of shape ``(ny, out_nx)`` in
            C-contiguous layout.

        Raises:
            ValueError: If *pixel_size* or *wavelength* is zero.
        """
        nx, ny = dims

        if float(params.pixel_size) == 0.0:
            raise ValueError("pixel_size must be non-zero")
        if float(params.wavelength) == 0.0:
            raise ValueError("wavelength must be non-zero")

        out_nx = nx // 2 + 1 if params.do_half_grid else nx
        out_ny = ny
        ox = nx // 2
        oy = ny // 2

        # Fourier-space voxel sizes (1/Angstrom per pixel)
        f32 = np.float32
        fvx = f32(1.0) / (params.pixel_size * f32(nx))
        fvy = f32(1.0) / (params.pixel_size * f32(ny))

        # Integer coordinate arrays
        x_idx = np.arange(out_nx, dtype=np.int32)
        y_idx = np.arange(out_ny, dtype=np.int32)

        # Apply coordinate wrapping (matches ctf.cu lines 31-40)
        if centered:
            y_signed = y_idx - oy
            x_signed = x_idx - ox if not params.do_half_grid else x_idx
        else:
            y_signed = np.where(y_idx > oy, y_idx - out_ny, y_idx)
            if not params.do_half_grid:
                x_signed = np.where(x_idx > ox, x_idx - out_nx, x_idx)
            else:
                x_signed = x_idx

        # Scale to spatial frequency (1/Angstrom)
        x_freq = x_signed.astype(np.float32) * float(fvx)
        y_freq = y_signed.astype(np.float32) * float(fvy)

        # Build 2-D grids: meshgrid with indexing='xy' gives
        # xv shape (out_ny, out_nx) where xv[row, col] = x_freq[col]
        xv, yv = np.meshgrid(x_freq, y_freq)

        # Azimuthal angle and squared spatial frequency
        phi = np.arctan2(yv, xv).astype(np.float32)
        radius_sq = (xv * xv + yv * yv).astype(np.float32)

        # CTF phase (matches ctf.cu formula)
        cs_term = float(params.cs_term)
        df_term = float(params.df_term)
        mean_df = float(params.mean_defocus)
        half_astig = float(params.half_astigmatism)
        astig_angle = float(params.astigmatism_angle_rad)
        amp_phase = float(params.amplitude_phase)

        defocus_eff = np.float32(mean_df) + np.float32(half_astig) * np.cos(
            np.float32(2.0) * (phi - np.float32(astig_angle))
        ).astype(np.float32)

        phase = (
            np.float32(cs_term) * (radius_sq * radius_sq)
            - np.float32(df_term) * radius_sq * defocus_eff
            - np.float32(amp_phase)
        ).astype(np.float32)

        if params.do_sq_ctf:
            ctf_val = np.sin(phase).astype(np.float32)
            result = (ctf_val * ctf_val).astype(np.float32)
        else:
            result = np.sin(phase).astype(np.float32)

        return np.ascontiguousarray(result, dtype=np.float32)

    @staticmethod
    def is_ready() -> bool:
        """CPU fallback is always ready."""
        return True
