"""Cross-correlation scoring function for CTF refinement.

Computes the cross-correlation-based objective that optimizers call at each
iteration.  Each evaluation applies current CTF parameters to reference
projections, cross-correlates against observed data, and measures per-particle
scores and shifts.

Port from ``synthetic/EMC_refine_tilt_ctf.m`` lines 256--325.

GPU/CPU dispatch
~~~~~~~~~~~~~~~~
All public functions accept both :mod:`numpy` and :mod:`cupy` arrays.
Dispatch is performed via ``isinstance(x, cp.ndarray)``; the deprecated
``cupy.get_array_module`` is **not** used.

Gaussian penalties (Python-only)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The MATLAB ``evaluate_score_and_shifts`` accepts sigma arguments but does not
apply penalty terms.  The Python implementation adds multiplicative Gaussian
penalties on per-particle X/Y shifts and Z offsets to improve convergence
stability.  These penalties are validatable only via finite-difference and
descent-direction tests (no MATLAB ground truth exists).
"""

from __future__ import annotations

import logging
import types as _types
from typing import TYPE_CHECKING, Protocol, Tuple, Union

import numpy as np

try:
    import cupy as cp

    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False
    cp = None

if TYPE_CHECKING:
    import cupy

    NDArray = Union[np.ndarray, cupy.ndarray]
else:
    NDArray = np.ndarray

from ..ctf.emc_ctf_params import CTFParams
from .emc_fourier_utils import FourierTransformer


class CTFCalculatorLike(Protocol):
    """Structural type for CTF calculator instances.

    Both ``CTFCalculator`` (GPU) and ``CTFCalculatorCPU`` satisfy this
    protocol via their ``compute`` method.
    """

    def compute(
        self,
        params: CTFParams,
        dims: Tuple[int, int],
        centered: bool = ...,
    ) -> NDArray: ...


def _xp_for(x: NDArray) -> _types.ModuleType:
    """Return the array module (numpy or cupy) that owns *x*."""
    if HAS_CUPY and isinstance(x, cp.ndarray):
        return cp
    return np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Peak mask helper
# ---------------------------------------------------------------------------


def create_peak_mask(nx: int, ny: int, radius: float) -> np.ndarray:
    """Create a circular binary mask centred at ``(nx//2, ny//2)``.

    Used to restrict the peak search in cross-correlation maps to a circular
    region of the given *radius* around the image centre.

    Args:
        nx: Number of rows in the real-space image.
        ny: Number of columns in the real-space image.
        radius: Search radius in pixels.

    Returns:
        Binary float32 mask of shape ``(nx, ny)``.
    """
    origin_x = nx // 2
    origin_y = ny // 2
    ix = np.arange(nx, dtype=np.float32)
    iy = np.arange(ny, dtype=np.float32)
    # indexing='ij' matches MATLAB ndgrid convention
    gx, gy = np.meshgrid(ix, iy, indexing="ij")
    dist = np.sqrt((gx - origin_x) ** 2 + (gy - origin_y) ** 2)
    return (dist <= radius).astype(np.float32)


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------


def evaluate_score_and_shifts(
    params: np.ndarray,
    data_fts: list[NDArray],
    ref_fts: list[NDArray],
    base_ctf_params: CTFParams,
    ctf_calculator: CTFCalculatorLike,
    fourier_handler: FourierTransformer,
    tilt_angle_degrees: float,
    peak_mask: np.ndarray,
    shift_sigma: float = 5.0,
    z_offset_sigma: float = 100.0,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Compute cross-correlation score and per-particle shifts.

    For each particle, applies the current CTF parameters to the reference
    projection, cross-correlates with the observed data, and measures the
    peak height and position.  Multiplicative Gaussian penalties on shift
    magnitude and z-offset are applied (**Python-only enhancement**, not
    present in the MATLAB reference).

    ``ref_fts`` are **pre-conjugated**: cross-correlation is computed as
    ``IFFT(data_FT * ref_with_ctf)`` without an explicit ``conj()`` call.

    Data FTs carry a spectral-domain ``swap_phase`` (checkerboard
    modulation) applied during preprocessing while reference FTs do not.
    This single checkerboard factor shifts the inverse-FFT output so that
    the zero-lag cross-correlation peak appears at the image centre
    ``(nx//2, ny//2)`` rather than at ``(0, 0)``.

    Args:
        params: Parameter vector of length ``3 + N`` where *N* is the number
            of particles.  ``params[0]`` = delta defocus (Angstroms),
            ``params[1]`` = delta half-astigmatism (Angstroms),
            ``params[2]`` = delta astigmatism angle (radians),
            ``params[3:]`` = per-particle delta-z (Angstroms).
        data_fts: Pre-computed, swap-phase-modulated, normalised data
            Fourier transforms.  Each element has shape ``(nx//2+1, ny)``.
        ref_fts: Pre-computed, pre-conjugated reference Fourier transforms.
            Each element has shape ``(nx//2+1, ny)``.
        base_ctf_params: Base CTF parameters for this tilt.
        ctf_calculator: CTF calculator instance (GPU ``CTFCalculator`` or
            CPU ``CTFCalculatorCPU``).
        fourier_handler: :class:`FourierTransformer` instance matching the
            tile dimensions.
        tilt_angle_degrees: Tilt angle of the current view (degrees).
        peak_mask: Binary circular mask for restricting the peak search,
            shape ``(nx, ny)``.
        shift_sigma: Gaussian penalty sigma for X/Y shifts (pixels).
        z_offset_sigma: Gaussian penalty sigma for z-offsets (Angstroms).

    Returns:
        Tuple ``(total_score, per_particle_scores, shifts_xy)``:

        * *total_score* -- sum of all per-particle scores (``float``).
        * *per_particle_scores* -- array of shape ``(N,)``.
        * *shifts_xy* -- array of shape ``(N, 2)`` with ``[shift_x, shift_y]``
          in pixels for each particle.
    """
    n_particles = len(data_fts)

    # --- Validate params length ------------------------------------------
    expected_len = 3 + n_particles
    if len(params) != expected_len:
        raise ValueError(
            f"params has length {len(params)} but expected {expected_len} "
            f"(3 global deltas + {n_particles} per-particle delta-z values)"
        )

    # --- Early return for zero-particle input ----------------------------
    if n_particles == 0:
        return 0.0, np.zeros(0, dtype=np.float64), np.zeros((0, 2), dtype=np.float64)

    nx = fourier_handler.nx
    ny = fourier_handler.ny

    # --- Extract global deltas from the parameter vector -----------------
    delta_df = float(params[0])
    delta_half_astig = float(params[1])
    delta_angle = float(params[2])  # radians

    # --- Base CTF scalar properties --------------------------------------
    base_mean = float(base_ctf_params.mean_defocus)
    base_half = float(base_ctf_params.half_astigmatism)
    base_angle_rad = float(base_ctf_params.astigmatism_angle_rad)
    pixel_size = float(base_ctf_params.pixel_size)
    wavelength = float(base_ctf_params.wavelength)
    cs_mm = float(base_ctf_params.cs_mm)
    amplitude_contrast = float(base_ctf_params.amplitude_contrast)

    cos_tilt = np.cos(np.radians(tilt_angle_degrees))

    # Origin for shift measurement (image centre, 0-indexed).
    # Matches MATLAB ``emc_get_origin_index(N)`` = floor(N/2)+1 (1-indexed).
    origin_x = nx // 2
    origin_y = ny // 2

    # Determine array backend (numpy or cupy)
    xp = _xp_for(data_fts[0])

    # Move peak mask to the correct device if needed
    if xp is not np and isinstance(peak_mask, np.ndarray):
        peak_mask_dev = xp.asarray(peak_mask)
    else:
        peak_mask_dev = peak_mask

    per_particle_scores = np.zeros(n_particles, dtype=np.float64)
    shifts = np.zeros((n_particles, 2), dtype=np.float64)

    for i in range(n_particles):
        dz = float(params[3 + i])
        dz_contribution = dz * cos_tilt

        # --- Effective defocus (opposite signs for delta_half_astig) ------
        # df1_eff = (base_mean + base_half) + delta_half_astig
        #           + delta_df + dz * cos(tilt)
        # df2_eff = (base_mean - base_half) - delta_half_astig
        #           + delta_df + dz * cos(tilt)
        df1_eff = (
            (base_mean + base_half)
            + delta_half_astig
            + delta_df
            + dz_contribution
        )
        df2_eff = (
            (base_mean - base_half)
            - delta_half_astig
            + delta_df
            + dz_contribution
        )
        angle_eff_rad = base_angle_rad + delta_angle

        # --- Enforce df1 >= df2 convention --------------------------------
        if df2_eff > df1_eff:
            df1_eff, df2_eff = df2_eff, df1_eff
            angle_eff_rad += np.pi / 2.0

        # --- Build per-particle CTFParams ---------------------------------
        angle_eff_deg = np.degrees(angle_eff_rad)
        particle_ctf = CTFParams.from_defocus_pair(
            df1=df1_eff,
            df2=df2_eff,
            angle_degrees=angle_eff_deg,
            pixel_size=pixel_size,
            wavelength=wavelength,
            cs_mm=cs_mm,
            amplitude_contrast=amplitude_contrast,
            do_half_grid=True,
            do_sq_ctf=False,
        )

        # --- Compute CTF image --------------------------------------------
        # CTF calculator outputs (ny, nx//2+1); FourierTransformer uses
        # the transposed layout (nx//2+1, ny).
        ctf_image = ctf_calculator.compute(particle_ctf, (nx, ny))
        ctf_image = ctf_image.T  # now (nx//2+1, ny)

        # Move to correct device when data lives on GPU but CTF is on CPU
        if xp is not np and isinstance(ctf_image, np.ndarray):
            ctf_image = xp.asarray(ctf_image)

        # --- Migrate reference FT to correct device if needed ---------------
        ref_ft_i = ref_fts[i]
        if xp is not np and isinstance(ref_ft_i, np.ndarray):
            ref_ft_i = xp.asarray(ref_ft_i)

        # --- Apply CTF to reference ---------------------------------------
        # ref_fts are pre-conjugated — no conj() needed.
        ref_with_ctf = ref_ft_i * ctf_image

        # --- Normalise reference ------------------------------------------
        ref_norm = fourier_handler.compute_ref_norm(ref_with_ctf)
        if ref_norm < 1e-30:
            logger.warning(
                "Particle %d skipped: degenerate CTF (ref_norm=%g < 1e-30)",
                i,
                ref_norm,
            )
            per_particle_scores[i] = 0.0
            continue
        ref_with_ctf = ref_with_ctf / ref_norm

        # --- Cross-correlate ----------------------------------------------
        # data_fts carry swap_phase (spectral checkerboard); ref does not.
        # The single checkerboard factor shifts the IFFT output so the
        # zero-lag peak sits at (nx//2, ny//2).
        xcf_spectrum = data_fts[i] * ref_with_ctf
        # Scale by nx*ny to match MATLAB convention: mexFFT (cuFFT) does
        # NOT normalise the inverse transform, whereas numpy.fft.irfft2
        # divides by N.  The score magnitudes must be consistent with the
        # energy-based spectrum normalisation used by compute_ref_norm.
        xcf = fourier_handler.inverse_fft(xcf_spectrum) * (nx * ny)

        # --- Peak search within mask --------------------------------------
        xcf_masked = peak_mask_dev * xcf

        if xp is not np:
            max_idx = int(xp.argmax(xcf_masked))
            peak_height = float(xcf_masked.ravel()[max_idx])
        else:
            max_idx = int(np.argmax(xcf_masked))
            peak_height = float(xcf_masked.ravel()[max_idx])

        px, py = np.unravel_index(max_idx, (nx, ny))

        # Shift relative to centre (pixels)
        shift_x = float(px - origin_x)
        shift_y = float(py - origin_y)

        # --- Gaussian penalties (Python-only enhancement) -----------------
        shift_mag_sq = shift_x ** 2 + shift_y ** 2
        shift_weight = float(np.exp(-shift_mag_sq / (2.0 * shift_sigma ** 2)))
        z_weight = float(np.exp(-(dz ** 2) / (2.0 * z_offset_sigma ** 2)))

        # Subtractive penalty: always reduces the score regardless of peak
        # sign.  For positive peaks this is equivalent to multiplicative
        # weighting (peak * w).  For negative peaks, multiplicative
        # weighting would make the score *less* negative (i.e. better in a
        # maximisation objective), inverting the intended penalty direction.
        combined_weight = shift_weight * z_weight
        penalty_amount = abs(peak_height) * (1.0 - combined_weight)
        per_particle_scores[i] = peak_height - penalty_amount
        shifts[i, 0] = shift_x
        shifts[i, 1] = shift_y

    total_score = float(np.sum(per_particle_scores))
    return total_score, per_particle_scores, shifts
