"""
CPU-interface CTF computation.

When CuPy / CUDA is available, delegates to the GPU kernel and transfers
results to NumPy arrays — this guarantees bit-identical agreement with
``CTFCalculator`` since both run the same CUDA code.

When no GPU is available, falls back to a pure-NumPy implementation that
replicates mexFiles/utils/ctf.cu lines 12-65 using the pre-computed
derived quantities stored in CTFParams.

Output layout: C-contiguous float32, shape (ny, out_nx).
"""

from __future__ import annotations

import logging

import numpy as np

from .emc_ctf_params import CTFParams

logger = logging.getLogger(__name__)

try:
    from .emc_ctf_calculator import CTFCalculator as _GPUCalc

    _HAS_GPU = True
except ImportError:
    _HAS_GPU = False

__all__ = ["CTFCalculatorCPU"]


class CTFCalculatorCPU:
    """CTF calculator that returns NumPy arrays.

    When a GPU is available the computation is delegated to the same CUDA
    kernel used by ``CTFCalculator``, ensuring bit-identical results.
    Falls back to a pure-NumPy implementation otherwise.
    """

    def __init__(self) -> None:
        """Initialise calculator, optionally loading GPU delegate."""
        self._gpu = None
        if _HAS_GPU:
            try:
                self._gpu = _GPUCalc()  # type: ignore[possibly-undefined]
            except Exception as exc:
                logger.warning(
                    "GPU CTF calculator unavailable; falling back to NumPy: %s", exc
                )
                self._gpu = None

    def compute(
        self,
        params: CTFParams,
        dims: tuple[int, int],
        centered: bool = False,
    ) -> np.ndarray:
        """Compute a 2-D CTF image, returning a NumPy array.

        When a GPU is available, delegates to the CUDA kernel for
        bit-identical agreement with ``CTFCalculator``.  Falls back to
        pure-NumPy otherwise.

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
        if self._gpu is not None:
            result = self._gpu.compute(params, dims, centered)
            return np.asarray(result.get())

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

        # Scale to spatial frequency (1/Angstrom).
        # Keep fvx/fvy as np.float32 (not Python float) so the product
        # stays float32 — float() would upcast to float64.
        x_freq = x_signed.astype(np.float32) * fvx
        y_freq = y_signed.astype(np.float32) * fvy

        # Build 2-D grids: meshgrid with indexing='xy' gives
        # xv shape (out_ny, out_nx) where xv[row, col] = x_freq[col]
        xv, yv = np.meshgrid(x_freq, y_freq)

        # Azimuthal angle and squared spatial frequency
        phi = np.arctan2(yv, xv).astype(np.float32)
        radius_sq = (xv * xv + yv * yv).astype(np.float32)

        # CTF phase (matches ctf.cu formula)
        # Use float32 scalars directly from CTFParams to avoid float64 round-tripping
        cs_term = params.cs_term
        df_term = params.df_term
        mean_df = params.mean_defocus
        half_astig = params.half_astigmatism
        astig_angle = params.astigmatism_angle_rad
        amp_phase = params.amplitude_phase

        defocus_eff = mean_df + half_astig * np.cos(
            f32(2.0) * (phi - astig_angle)
        ).astype(f32)

        phase = (
            cs_term * (radius_sq * radius_sq)
            - df_term * radius_sq * defocus_eff
            - amp_phase
        ).astype(f32)

        if params.do_sq_ctf:
            ctf_val = np.sin(phase).astype(np.float32)
            result = (ctf_val * ctf_val).astype(np.float32)
        else:
            result = np.sin(phase).astype(np.float32)

        return np.ascontiguousarray(result, dtype=np.float32)

    def compute_with_derivatives(
        self,
        params: CTFParams,
        dims: tuple[int, int],
        centered: bool = False,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Compute CTF and analytical derivatives, returning NumPy arrays.

        When a GPU is available, delegates to the CUDA kernel for
        bit-identical agreement with ``CTFCalculator``.

        Args:
            params: Pre-computed CTF parameters.
            dims: Real-space image dimensions ``(nx, ny)``.
            centered: If True, DC is at the centre of the output.

        Returns:
            Tuple of four float32 arrays ``(ctf, dctf_dD, dctf_dA, dctf_dTheta)``,
            each with shape ``(ny, out_nx)`` in C-contiguous layout.

        Raises:
            ValueError: If *pixel_size* or *wavelength* is zero.
        """
        if self._gpu is not None:
            ctf, dD, dA, dT = self._gpu.compute_with_derivatives(
                params, dims, centered
            )
            return (
                np.asarray(ctf.get()),
                np.asarray(dD.get()),
                np.asarray(dA.get()),
                np.asarray(dT.get()),
            )

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
        x_freq = x_signed.astype(np.float32) * fvx
        y_freq = y_signed.astype(np.float32) * fvy

        # Build 2-D grids
        xv, yv = np.meshgrid(x_freq, y_freq)

        # Azimuthal angle and squared spatial frequency
        phi = np.arctan2(yv, xv).astype(np.float32)
        radius_sq = (xv * xv + yv * yv).astype(np.float32)

        # Extract scalar params — use float32 directly to match GPU precision
        f32 = np.float32
        cs_term = params.cs_term
        df_term = params.df_term
        mean_df = params.mean_defocus
        half_astig = params.half_astigmatism
        astig_angle = params.astigmatism_angle_rad
        amp_phase = params.amplitude_phase

        # Angle terms for astigmatism
        two_phi_theta = f32(2.0) * (phi - astig_angle)
        cos2pt = np.cos(two_phi_theta).astype(f32)
        sin2pt = np.sin(two_phi_theta).astype(f32)

        # CTF phase (identical to compute())
        defocus_eff = mean_df + half_astig * cos2pt
        phase = (
            cs_term * (radius_sq * radius_sq)
            - df_term * radius_sq * defocus_eff
            - amp_phase
        ).astype(f32)

        # Phase derivatives w.r.t. defocus parameters
        neg_df_s2 = (-df_term * radius_sq).astype(f32)
        dphase_dD = neg_df_s2
        dphase_dA = (neg_df_s2 * cos2pt).astype(f32)
        # Sign: d/dtheta[cos(2(phi-theta))] = +2*sin(2(phi-theta)),
        # multiplied by outer -df_term*s^2*A = neg_df_s2*A gives overall
        # -2*df_term*s^2*A. Since neg_df_s2 carries the minus, factor is +2.
        dphase_dTheta = (
            neg_df_s2 * half_astig
            * f32(2.0) * sin2pt
        ).astype(f32)

        # Convert theta derivative to per-degree units
        dphase_dTheta = (
            dphase_dTheta * f32(np.pi / 180.0)
        ).astype(f32)

        # CTF value and chain-rule derivatives
        sin_phase = np.sin(phase).astype(np.float32)
        cos_phase = np.cos(phase).astype(np.float32)

        if params.do_sq_ctf:
            # CTF = sin^2(phase)
            ctf_val = (sin_phase * sin_phase).astype(np.float32)
            # dCTF/dX = sin(2*phase) * dphase/dX = 2*sin*cos * dphase/dX
            sin2phase = (np.float32(2.0) * sin_phase * cos_phase).astype(
                np.float32
            )
            d_D = (sin2phase * dphase_dD).astype(np.float32)
            d_A = (sin2phase * dphase_dA).astype(np.float32)
            d_Theta = (sin2phase * dphase_dTheta).astype(np.float32)
        else:
            # CTF = sin(phase)
            ctf_val = sin_phase
            # dCTF/dX = cos(phase) * dphase/dX
            d_D = (cos_phase * dphase_dD).astype(np.float32)
            d_A = (cos_phase * dphase_dA).astype(np.float32)
            d_Theta = (cos_phase * dphase_dTheta).astype(np.float32)

        # DC pixel: all derivatives zero (radius_sq == 0 => neg_df_s2 == 0,
        # so derivatives are already zero from the multiplication)

        return (
            np.ascontiguousarray(ctf_val, dtype=np.float32),
            np.ascontiguousarray(d_D, dtype=np.float32),
            np.ascontiguousarray(d_A, dtype=np.float32),
            np.ascontiguousarray(d_Theta, dtype=np.float32),
        )

    def is_ready(self) -> bool:
        """CPU fallback is always ready."""
        return True
