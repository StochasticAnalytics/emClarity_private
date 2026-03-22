"""
Fourier-space utilities for cryo-EM refinement.

Replicates the key behaviors of the MATLAB ``fourierTransformer`` class
used in ``synthetic/EMC_refine_tilt_ctf.m``.  Provides R2C / C2R FFT
wrappers, phase-swap (fftshift-by-multiplication), bandpass filtering
with cosine-edge rolloff, and half-grid normalization.

Original MATLAB equivalent: testScripts/fourierTransformer.m

GPU/CPU dispatch
~~~~~~~~~~~~~~~~
All public methods accept both :mod:`numpy` and :mod:`cupy` arrays.
Dispatch is performed via ``isinstance(x, cp.ndarray)``; the deprecated
``cupy.get_array_module`` is **not** used.
"""

from __future__ import annotations

import logging
from typing import Union

import numpy as np

try:
    import cupy as cp

    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False
    cp = None

logger = logging.getLogger(__name__)


def _xp_for(x: Union[np.ndarray, "cp.ndarray"]) -> type:  # type: ignore[name-defined]
    """Return the array module (numpy or cupy) that owns *x*."""
    if HAS_CUPY and isinstance(x, cp.ndarray):
        return cp
    return np


class FourierTransformer:
    """Half-grid 2-D FFT handler with bandpass and normalization utilities.

    The *half-grid* convention stores only the non-redundant half of the
    Hermitian-symmetric R2C spectrum.  For a real image of shape
    ``(nx, ny)``, the spectrum has shape ``(nx // 2 + 1, ny)`` — the
    **first** axis is halved, matching the MATLAB ``fourierTransformer``
    convention where ``halfDim = 1``.

    Args:
        nx: Number of rows in the real-space image.
        ny: Number of columns in the real-space image.
        use_gpu: If *True* **and** CuPy is available, pre-allocate GPU
            helper arrays (checkerboard, frequency grids).  CPU arrays
            are used as fallback when CuPy is absent.
    """

    def __init__(self, nx: int, ny: int, use_gpu: bool = True) -> None:
        self._nx = nx
        self._ny = ny
        self._use_gpu = use_gpu and HAS_CUPY

        # Half-grid output shape: first axis halved
        self._half_nx = nx // 2 + 1

        # Number of rows to exclude from normalization sums at Nyquist.
        # For the standard half-grid R2C layout the last row corresponds
        # to the Nyquist frequency and is excluded from energy sums to
        # avoid double-counting conjugate-symmetric contributions.
        self._inv_trim = 1

        # Lazily built helpers (created on first use, cached thereafter)
        self._checkerboard: Union[np.ndarray, None] = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def inv_trim(self) -> int:
        """Rows excluded from normalization (Nyquist handling)."""
        return self._inv_trim

    @property
    def nx(self) -> int:
        return self._nx

    @property
    def ny(self) -> int:
        return self._ny

    # ------------------------------------------------------------------
    # FFT methods
    # ------------------------------------------------------------------

    def forward_fft(self, image: np.ndarray) -> np.ndarray:
        """2-D real-to-complex FFT producing half-grid layout.

        Args:
            image: Real array of shape ``(nx, ny)``.

        Returns:
            Complex array of shape ``(nx // 2 + 1, ny)``.

        Raises:
            ValueError: If *image* is not 2-D.
        """
        if image.ndim != 2:
            raise ValueError(
                f"forward_fft requires a 2-D array, got ndim={image.ndim}"
            )
        xp = _xp_for(image)
        # axes=(1, 0): full FFT along axis 1, rfft (halved) along axis 0
        return xp.fft.rfft2(image, axes=(1, 0))

    def inverse_fft(self, spectrum: np.ndarray) -> np.ndarray:
        """2-D complex-to-real inverse FFT from half-grid layout.

        Args:
            spectrum: Complex array of shape ``(nx // 2 + 1, ny)``.

        Returns:
            Real array of shape ``(nx, ny)`` with correct normalization.
        """
        xp = _xp_for(spectrum)
        # s=(ny, nx) maps to axes=(1, 0): axis 1 gets ny, axis 0 gets nx
        return xp.fft.irfft2(spectrum, s=(self._ny, self._nx), axes=(1, 0))

    # ------------------------------------------------------------------
    # Phase swap (fftshift by multiplication)
    # ------------------------------------------------------------------

    def swap_phase(self, image: np.ndarray) -> np.ndarray:
        """Multiply by ``(-1)^(i+j)`` checkerboard to center DC.

        This is the spectral-domain equivalent of ``fftshift`` for
        half-grid data.  Multiplying the R2C spectrum by the
        checkerboard before ``inverse_fft`` produces an output whose
        DC component sits at the image center rather than at ``(0, 0)``.

        The checkerboard is cached and transferred to the appropriate
        device (CPU / GPU) on first call.

        Args:
            image: Array of shape ``(nx // 2 + 1, ny)`` (half-grid spectrum)
                or ``(nx, ny)`` (real-space image before forward FFT).

        Returns:
            Element-wise product of *image* and the checkerboard.
        """
        xp = _xp_for(image)
        cb = self._get_checkerboard(xp, image.shape)
        return image * cb

    def _get_checkerboard(
        self, xp: type, shape: tuple[int, ...]
    ) -> np.ndarray:
        """Build or retrieve the cached ``(-1)^(i+j)`` checkerboard."""
        # Rebuild if shape or device changed
        if self._checkerboard is not None:
            same_xp = _xp_for(self._checkerboard) is xp
            same_shape = self._checkerboard.shape == shape
            if same_xp and same_shape:
                return self._checkerboard

        rows, cols = shape
        i = xp.arange(rows, dtype=np.float64)[:, None]
        j = xp.arange(cols, dtype=np.float64)[None, :]
        # 1 - 2*(parity) avoids float-power rounding issues
        self._checkerboard = 1.0 - 2.0 * ((i + j) % 2)
        return self._checkerboard

    # ------------------------------------------------------------------
    # Bandpass filter
    # ------------------------------------------------------------------

    def apply_bandpass(
        self,
        spectrum: np.ndarray,
        pixel_size: float,
        highpass_angstrom: float,
        lowpass_angstrom: float,
    ) -> np.ndarray:
        """Zero frequencies outside the bandpass range with soft edges.

        The filter is applied in-place as an element-wise multiplication.
        Frequencies with resolution outside
        ``[lowpass_angstrom, highpass_angstrom]`` are zeroed.  A cosine
        rolloff of width **2 frequency bins** softens both edges.

        Args:
            spectrum: Complex half-grid array ``(nx // 2 + 1, ny)``.
            pixel_size: Pixel size in Angstroms.
            highpass_angstrom: High-pass cutoff in Angstroms (large value,
                e.g. 400 A).  Frequencies with resolution **above** this
                value are removed.
            lowpass_angstrom: Low-pass cutoff in Angstroms (small value,
                e.g. 10 A).  Frequencies with resolution **below** this
                value are removed.

        Returns:
            Filtered spectrum (same shape).

        Raises:
            ValueError: If ``highpass_angstrom <= lowpass_angstrom``
                (invalid range — highpass resolution must be larger than
                lowpass resolution in Angstroms).
        """
        if highpass_angstrom <= lowpass_angstrom:
            raise ValueError(
                f"highpass_angstrom ({highpass_angstrom}) must be greater "
                f"than lowpass_angstrom ({lowpass_angstrom})"
            )

        xp = _xp_for(spectrum)
        mask = self._build_bandpass_mask(
            xp, spectrum.shape, pixel_size, highpass_angstrom, lowpass_angstrom
        )
        return spectrum * mask

    def _build_bandpass_mask(
        self,
        xp: type,
        shape: tuple[int, ...],
        pixel_size: float,
        highpass_angstrom: float,
        lowpass_angstrom: float,
    ) -> np.ndarray:
        """Construct the bandpass mask with cosine-edge rolloff."""
        half_nx, ny = shape

        # Spatial frequencies in Angstroms^-1
        # First axis (halved): 0 .. half_nx-1, freq = i / (nx * pixel_size)
        freq_x = xp.arange(half_nx, dtype=np.float64) / (self._nx * pixel_size)
        # Second axis (full FFT order): uses standard fftfreq layout
        freq_y = xp.fft.fftfreq(ny, d=pixel_size).astype(np.float64)

        freq_mag = xp.sqrt(
            freq_x[:, None] ** 2 + freq_y[None, :] ** 2
        )

        # Cutoff frequencies in Angstroms^-1
        freq_hp = 1.0 / highpass_angstrom  # low frequency edge
        freq_lp = 1.0 / lowpass_angstrom   # high frequency edge

        # Rolloff width: 2 frequency bins along the first (halved) axis
        df = 1.0 / (self._nx * pixel_size)
        rolloff = 2.0 * df

        # --- High-pass edge (ramp from 0→1 near freq_hp) ---
        hp_mask = xp.ones_like(freq_mag)
        # Below the rolloff start: fully blocked
        hp_mask[freq_mag < freq_hp - rolloff] = 0.0
        # In the transition zone
        transition = (freq_mag >= freq_hp - rolloff) & (freq_mag < freq_hp)
        t = (freq_mag[transition] - (freq_hp - rolloff)) / rolloff
        hp_mask[transition] = 0.5 * (1.0 - xp.cos(np.pi * t))

        # --- Low-pass edge (ramp from 1→0 near freq_lp) ---
        lp_mask = xp.ones_like(freq_mag)
        # Above the rolloff end: fully blocked
        lp_mask[freq_mag > freq_lp + rolloff] = 0.0
        # In the transition zone
        transition = (freq_mag >= freq_lp) & (freq_mag <= freq_lp + rolloff)
        t = (freq_mag[transition] - freq_lp) / rolloff
        lp_mask[transition] = 0.5 * (1.0 + xp.cos(np.pi * t))

        # DC component (freq_mag == 0) is blocked by the high-pass
        mask = hp_mask * lp_mask
        mask[freq_mag == 0.0] = 0.0

        return mask

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def compute_ref_norm(self, ref_with_ctf: np.ndarray) -> float:
        """Half-grid energy normalization factor.

        Computes ``sqrt(2 * sum(|ref_with_ctf[:-inv_trim, :]|^2))``.
        The factor of 2 accounts for the conjugate-symmetric half that
        is *not* stored in the half-grid representation.  The last
        ``inv_trim`` rows (Nyquist) are excluded to avoid double-counting.

        Reference: ``EMC_refine_tilt_ctf.m`` lines 300-301 (supplement
        'Normalization Convention').

        Args:
            ref_with_ctf: Complex half-grid spectrum ``(nx // 2 + 1, ny)``.

        Returns:
            Normalization scalar (float).
        """
        xp = _xp_for(ref_with_ctf)
        trimmed = ref_with_ctf[: -self._inv_trim, :]
        energy = xp.sum(xp.abs(trimmed) ** 2)
        result = xp.sqrt(2.0 * energy)
        # Return a Python float regardless of backend
        return float(result)
