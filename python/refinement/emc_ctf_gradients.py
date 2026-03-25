"""Analytical gradient computation for CTF refinement.

Extends :func:`evaluate_score_and_shifts` from :mod:`emc_scoring` by also
computing the analytical gradient of the cross-correlation score with respect
to CTF parameters.  The gradient holds the **peak position fixed** and
differentiates only the CTF contribution to the score.

For each particle and each derivative (dD, dA, dTheta):

1. Compute ``raw_grad`` — the IFFT of ``data_FT * ref_FT * dctf_dX / ref_norm``
   sampled at the peak position.
2. Compute ``norm_corr`` — the normalization correction from the
   ``1/ref_norm`` denominator in the score.
3. ``gradient[param] += raw_grad - norm_corr``.

Per-particle delta_z gradients reuse the defocus derivative scaled by
``cos(tilt_angle)``, plus a Gaussian penalty gradient term.

Port reference: ``autonomous-build/prd-ctf-python-supplement.md`` lines 189-226.

GPU/CPU dispatch
~~~~~~~~~~~~~~~~
All public functions accept both :mod:`numpy` and :mod:`cupy` arrays.
Dispatch is performed via ``isinstance(x, cp.ndarray)``; the deprecated
``cupy.get_array_module`` is **not** used.
"""

from __future__ import annotations

import logging
import types as _types
from typing import TYPE_CHECKING, Protocol, Union

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

logger = logging.getLogger(__name__)


class CTFCalculatorWithDerivatives(Protocol):
    """Structural type for CTF calculators that support derivatives.

    Both ``CTFCalculator`` (GPU) and ``CTFCalculatorCPU`` satisfy this
    protocol via their ``compute_with_derivatives`` method.
    """

    def compute_with_derivatives(
        self,
        params: CTFParams,
        dims: tuple[int, int],
        centered: bool = ...,
    ) -> tuple[NDArray, NDArray, NDArray, NDArray]:
        r"""Compute CTF image and its partial derivatives.

        Returns:
            Tuple ``(ctf, dctf_dD, dctf_dA, dctf_dTheta)`` each of shape
            ``(ny, nx//2+1)``:

            - ``ctf``: CTF image.
            - ``dctf_dD``: Partial derivative with respect to mean defocus
              (Angstroms\ :sup:`-1`).
            - ``dctf_dA``: Partial derivative with respect to half-astigmatism
              (Angstroms\ :sup:`-1`).
            - ``dctf_dTheta``: Partial derivative with respect to astigmatism
              angle **in degrees** (per degree).  Callers converting to
              per-radian units must multiply by ``180 / pi``.
        """
        ...


def _xp_for(x: NDArray) -> _types.ModuleType:
    """Return the array module (numpy or cupy) that owns *x*."""
    if HAS_CUPY and isinstance(x, cp.ndarray):
        return cp
    return np


def evaluate_score_and_gradient(
    params: np.ndarray,
    data_fts: list[NDArray],
    ref_fts: list[NDArray],
    base_ctf_params: CTFParams,
    ctf_calculator: CTFCalculatorWithDerivatives,
    fourier_handler: FourierTransformer,
    tilt_angle_degrees: float,
    peak_mask: np.ndarray,
    shift_sigma: float = 5.0,
    z_offset_sigma: float = 100.0,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    """Compute cross-correlation score, shifts, and analytical gradient.

    Extends :func:`evaluate_score_and_shifts` by also computing the
    analytical gradient of the total score with respect to the parameter
    vector.  The gradient holds the peak position fixed and differentiates
    only the CTF contribution.

    The parameter vector layout is ``[delta_df, delta_half_astig,
    delta_angle, dz_0, dz_1, ..., dz_{N-1}]`` where *N* is the number
    of particles.

    Args:
        params: Parameter vector of length ``3 + N``.
            ``params[0]`` = delta defocus (Angstroms),
            ``params[1]`` = delta half-astigmatism (Angstroms),
            ``params[2]`` = delta astigmatism angle (radians),
            ``params[3:]`` = per-particle delta-z (Angstroms).
        data_fts: Pre-computed, swap-phase-modulated, normalised data
            Fourier transforms.  Each element has shape ``(nx//2+1, ny)``.
        ref_fts: Pre-computed, pre-conjugated reference Fourier transforms.
            Each element has shape ``(nx//2+1, ny)``.
        base_ctf_params: Base CTF parameters for this tilt.
        ctf_calculator: CTF calculator instance supporting
            ``compute_with_derivatives``.
        fourier_handler: :class:`FourierTransformer` instance matching the
            tile dimensions.
        tilt_angle_degrees: Tilt angle of the current view (degrees).
        peak_mask: Binary circular mask for restricting the peak search,
            shape ``(nx, ny)``.
        shift_sigma: Gaussian penalty sigma for X/Y shifts (pixels).
        z_offset_sigma: Gaussian penalty sigma for z-offsets (Angstroms).

    Returns:
        Tuple ``(total_score, per_particle_scores, shifts_xy, gradient)``:

        * *total_score* -- sum of all per-particle scores (``float``).
        * *per_particle_scores* -- array of shape ``(N,)``.
        * *shifts_xy* -- array of shape ``(N, 2)`` with ``[shift_x, shift_y]``
          in pixels for each particle.
        * *gradient* -- array of shape ``(3 + N,)``, the analytical gradient
          of the total score w.r.t. the parameter vector, **negated** for
          minimisation (optimizer minimises ``-score``).
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
        return (
            0.0,
            np.zeros(0, dtype=np.float64),
            np.zeros((0, 2), dtype=np.float64),
            np.zeros(3, dtype=np.float64),
        )

    nx = fourier_handler.nx
    ny = fourier_handler.ny
    inv_trim = fourier_handler.inv_trim

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
    gradient = np.zeros(expected_len, dtype=np.float64)

    for i in range(n_particles):
        dz = float(params[3 + i])
        dz_contribution = dz * cos_tilt

        # --- Effective defocus (opposite signs for delta_half_astig) ------
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
        # When the swap fires, delta_half_astig enters df2_eff with positive
        # sign and df1_eff with negative sign — the opposite of the no-swap
        # case.  d(half_astig_ctf)/d(delta_half_astig) = -1 after the swap,
        # so the chain rule requires negating the astigmatism gradient.
        astig_sign = 1.0
        if df2_eff > df1_eff:
            df1_eff, df2_eff = df2_eff, df1_eff
            angle_eff_rad += np.pi / 2.0
            astig_sign = -1.0

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

        # --- Compute CTF image and derivatives ----------------------------
        # CTF calculator outputs (ny, nx//2+1); FourierTransformer uses
        # the transposed layout (nx//2+1, ny).
        ctf_image, dctf_dD, dctf_dA, dctf_dTheta = (
            ctf_calculator.compute_with_derivatives(particle_ctf, (nx, ny))
        )
        # Transpose to FourierTransformer layout (nx//2+1, ny)
        ctf_image = ctf_image.T
        dctf_dD = dctf_dD.T
        dctf_dA = dctf_dA.T
        dctf_dTheta = dctf_dTheta.T

        # Move to correct device when data and CTF disagree.
        if xp is not np:
            if isinstance(ctf_image, np.ndarray):
                ctf_image = xp.asarray(ctf_image)
                dctf_dD = xp.asarray(dctf_dD)
                dctf_dA = xp.asarray(dctf_dA)
                dctf_dTheta = xp.asarray(dctf_dTheta)
        elif HAS_CUPY and isinstance(ctf_image, cp.ndarray):
            ctf_image = ctf_image.get()
            dctf_dD = dctf_dD.get()
            dctf_dA = dctf_dA.get()
            dctf_dTheta = dctf_dTheta.get()

        # --- Migrate reference FT to correct device if needed ---------------
        ref_ft_i = ref_fts[i]
        if xp is not np and isinstance(ref_ft_i, np.ndarray):
            ref_ft_i = xp.asarray(ref_ft_i)

        data_ft_i = data_fts[i]

        # --- Apply CTF to reference ---------------------------------------
        ref_with_ctf = ref_ft_i * ctf_image

        # --- Normalise reference ------------------------------------------
        ref_norm = fourier_handler.compute_ref_norm(ref_with_ctf)
        if not (ref_norm >= 1e-30):
            logger.warning(
                "Particle %d skipped: degenerate CTF (ref_norm=%g < 1e-30)",
                i,
                ref_norm,
            )
            per_particle_scores[i] = 0.0
            continue
        ref_with_ctf_normed = ref_with_ctf / ref_norm

        # --- Cross-correlate (forward pass, identical to scoring) ---------
        xcf_spectrum = data_ft_i * ref_with_ctf_normed
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

        combined_weight = shift_weight * z_weight
        penalty_amount = abs(peak_height) * (1.0 - combined_weight)
        per_particle_scores[i] = peak_height - penalty_amount
        shifts[i, 0] = shift_x
        shifts[i, 1] = shift_y

        # =================================================================
        # Gradient computation
        # =================================================================
        # The penalized score for positive peaks is:
        #   score = peak_height * W,  where W = shift_weight * z_weight
        # For negative peaks:
        #   score = peak_height * (2 - W)
        #
        # The gradient of the penalized score w.r.t. CTF params is:
        #   d(score)/d(param) = d(peak_height)/d(param) * score_factor
        # where score_factor = W for positive peaks, (2-W) for negative.
        #
        # For dz, there's an additional penalty gradient term:
        #   d(score)/d(dz) = d(peak_height)/d(dz) * score_factor
        #                    - |peak_height| * W * dz / sigma_z^2
        #
        # The raw gradient of peak_height w.r.t. CTF param X is:
        #   raw_grad = real(IFFT(data_FT * ref_FT * dctf_dX / ref_norm))[peak]
        #   norm_corr = peak_height * 2 * real(sum(
        #       conj(ref_with_ctf_normed[:-trim,:]) *
        #       (ref_FT * dctf_dX / ref_norm)[:-trim,:]))
        #   d(peak_height)/d(X) = raw_grad - norm_corr

        # Score factor accounts for the penalty weight in the gradient
        score_factor = combined_weight if peak_height >= 0 else 2.0 - combined_weight

        derivative_kernels = [dctf_dD, dctf_dA, dctf_dTheta]
        # param indices: 0=defocus, 1=half_astig, 2=angle
        param_indices = [0, 1, 2]
        # dctf_dTheta is in per-degree units, but params[2] is radians.
        # Multiply the theta derivative by 180/pi to convert to per-radian.
        # astig_sign corrects for the chain rule when the df1/df2 convention
        # swap fires (see note above where astig_sign is set).
        unit_factors = [1.0, astig_sign, 180.0 / np.pi]

        # Store the defocus raw_grad and norm_corr for delta_z computation
        raw_grad_D = 0.0
        norm_corr_D = 0.0

        for k, (dctf_dX, param_idx, unit_fac) in enumerate(
            zip(derivative_kernels, param_indices, unit_factors, strict=False)
        ):
            # --- Primary gradient term -----------------------------------
            grad_spectrum = data_ft_i * ref_ft_i * dctf_dX / ref_norm
            grad_real = fourier_handler.inverse_fft(grad_spectrum) * (nx * ny)
            raw_grad = float(grad_real[px, py])

            # --- Normalization correction ---------------------------------
            ref_dctf = ref_ft_i * dctf_dX / ref_norm
            if inv_trim > 0:
                trimmed_normed = ref_with_ctf_normed[:-inv_trim, :]
                trimmed_dctf = ref_dctf[:-inv_trim, :]
            else:
                trimmed_normed = ref_with_ctf_normed
                trimmed_dctf = ref_dctf

            inner = xp.sum(xp.conj(trimmed_normed) * trimmed_dctf)
            norm_corr = peak_height * 2.0 * float(xp.real(inner))

            # Accumulate into global gradient with penalty weight factor
            # and unit conversion (per-degree → per-radian for angle)
            gradient[param_idx] += (
                (raw_grad - norm_corr) * score_factor * unit_fac
            )

            # Save defocus derivative for delta_z gradient
            if k == 0:  # defocus derivative
                raw_grad_D = raw_grad
                norm_corr_D = norm_corr

        # --- Per-particle delta_z gradient --------------------------------
        # CTF contribution: dScore/d(dz_i) through effective defocus
        gradient[3 + i] = (raw_grad_D - norm_corr_D) * cos_tilt * score_factor

        # --- Penalty gradient for delta_z ---------------------------------
        # d(score)/d(dz) includes -|peak_height| * W * dz / sigma_z^2
        # from differentiating the z_weight factor in the penalty.
        # The negative sign means the penalty gradient points toward
        # zero offset (dz=0).
        gradient[3 + i] += (
            -abs(peak_height) * combined_weight * dz / (z_offset_sigma ** 2)
        )

    total_score = float(np.sum(per_particle_scores))

    # Negate: optimizer minimizes, we maximize CC
    gradient = -gradient

    return total_score, per_particle_scores, shifts, gradient


def compute_gradient_debug_info(
    params: np.ndarray,
    data_fts: list[NDArray],
    ref_fts: list[NDArray],
    base_ctf_params: CTFParams,
    ctf_calculator: CTFCalculatorWithDerivatives,
    fourier_handler: FourierTransformer,
    tilt_angle_degrees: float,
    peak_mask: np.ndarray,
    shift_sigma: float = 5.0,
    z_offset_sigma: float = 100.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return raw_grad and norm_corr arrays for diagnostic use.

    Computes the same intermediate quantities used inside
    :func:`evaluate_score_and_gradient` but returns them without combining
    or negating, so callers can directly verify acceptance criteria such as
    ``|norm_corr| > 0.01 * |raw_grad|``.

    Note:
        ``shift_sigma`` and ``z_offset_sigma`` are accepted for API symmetry
        with :func:`evaluate_score_and_gradient` but are not applied in this
        diagnostic function.  Only the raw gradient and normalisation
        correction are returned; no penalty weighting is performed.

    Args:
        params: Parameter vector of length ``3 + N`` (same layout as
            :func:`evaluate_score_and_gradient`).
        data_fts: Pre-processed data Fourier transforms, length N.
        ref_fts: Pre-conjugated reference Fourier transforms, length N.
        base_ctf_params: Base CTF parameters for this tilt.
        ctf_calculator: CTF calculator supporting ``compute_with_derivatives``.
        fourier_handler: :class:`FourierTransformer` matching tile dimensions.
        tilt_angle_degrees: Tilt angle of the current view (degrees).
        peak_mask: Binary circular mask restricting peak search.
        shift_sigma: Accepted but unused (see Note above).
        z_offset_sigma: Accepted but unused (see Note above).

    Returns:
        Tuple ``(raw_grads, norm_corrs)`` each of shape ``(N, 3)``, where
        axis-1 indexes ``[dD, dA, dTheta]`` (defocus, half-astigmatism,
        angle).  Entries for skipped (degenerate) particles are zero.
    """
    n_particles = len(data_fts)
    raw_grads = np.zeros((n_particles, 3), dtype=np.float64)
    norm_corrs = np.zeros((n_particles, 3), dtype=np.float64)

    if n_particles == 0:
        return raw_grads, norm_corrs

    expected_len = 3 + n_particles
    if len(params) != expected_len:
        raise ValueError(
            f"params has length {len(params)} but expected {expected_len}"
        )

    nx = fourier_handler.nx
    ny = fourier_handler.ny
    inv_trim = fourier_handler.inv_trim

    delta_df = float(params[0])
    delta_half_astig = float(params[1])
    delta_angle = float(params[2])

    base_mean = float(base_ctf_params.mean_defocus)
    base_half = float(base_ctf_params.half_astigmatism)
    base_angle_rad = float(base_ctf_params.astigmatism_angle_rad)
    pixel_size = float(base_ctf_params.pixel_size)
    wavelength = float(base_ctf_params.wavelength)
    cs_mm = float(base_ctf_params.cs_mm)
    amplitude_contrast = float(base_ctf_params.amplitude_contrast)

    cos_tilt = np.cos(np.radians(tilt_angle_degrees))

    xp = _xp_for(data_fts[0])
    if xp is not np and isinstance(peak_mask, np.ndarray):
        peak_mask_dev = xp.asarray(peak_mask)
    else:
        peak_mask_dev = peak_mask

    for i in range(n_particles):
        dz = float(params[3 + i])
        dz_contribution = dz * cos_tilt

        df1_eff = (base_mean + base_half) + delta_half_astig + delta_df + dz_contribution
        df2_eff = (base_mean - base_half) - delta_half_astig + delta_df + dz_contribution
        angle_eff_rad = base_angle_rad + delta_angle

        if df2_eff > df1_eff:
            df1_eff, df2_eff = df2_eff, df1_eff
            angle_eff_rad += np.pi / 2.0

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

        ctf_image, dctf_dD, dctf_dA, dctf_dTheta = (
            ctf_calculator.compute_with_derivatives(particle_ctf, (nx, ny))
        )
        ctf_image = ctf_image.T
        dctf_dD = dctf_dD.T
        dctf_dA = dctf_dA.T
        dctf_dTheta = dctf_dTheta.T

        if xp is not np:
            if isinstance(ctf_image, np.ndarray):
                ctf_image = xp.asarray(ctf_image)
                dctf_dD = xp.asarray(dctf_dD)
                dctf_dA = xp.asarray(dctf_dA)
                dctf_dTheta = xp.asarray(dctf_dTheta)
        elif HAS_CUPY and isinstance(ctf_image, cp.ndarray):
            ctf_image = ctf_image.get()
            dctf_dD = dctf_dD.get()
            dctf_dA = dctf_dA.get()
            dctf_dTheta = dctf_dTheta.get()

        ref_ft_i = ref_fts[i]
        if xp is not np and isinstance(ref_ft_i, np.ndarray):
            ref_ft_i = xp.asarray(ref_ft_i)

        data_ft_i = data_fts[i]
        ref_with_ctf = ref_ft_i * ctf_image
        ref_norm = fourier_handler.compute_ref_norm(ref_with_ctf)
        if not (ref_norm >= 1e-30):
            continue
        ref_with_ctf_normed = ref_with_ctf / ref_norm

        xcf_masked = peak_mask_dev * fourier_handler.inverse_fft(
            data_ft_i * ref_with_ctf_normed
        ) * (nx * ny)
        if xp is not np:
            max_idx = int(xp.argmax(xcf_masked))
            peak_height = float(xcf_masked.ravel()[max_idx])
        else:
            max_idx = int(np.argmax(xcf_masked))
            peak_height = float(xcf_masked.ravel()[max_idx])

        px, py = np.unravel_index(max_idx, (nx, ny))

        for k, dctf_dX in enumerate([dctf_dD, dctf_dA, dctf_dTheta]):
            grad_spectrum = data_ft_i * ref_ft_i * dctf_dX / ref_norm
            grad_real = fourier_handler.inverse_fft(grad_spectrum) * (nx * ny)
            raw_grad = float(grad_real[px, py])

            ref_dctf = ref_ft_i * dctf_dX / ref_norm
            if inv_trim > 0:
                trimmed_normed = ref_with_ctf_normed[:-inv_trim, :]
                trimmed_dctf = ref_dctf[:-inv_trim, :]
            else:
                trimmed_normed = ref_with_ctf_normed
                trimmed_dctf = ref_dctf

            inner = xp.sum(xp.conj(trimmed_normed) * trimmed_dctf)
            norm_corr = peak_height * 2.0 * float(xp.real(inner))

            raw_grads[i, k] = raw_grad
            norm_corrs[i, k] = norm_corr

    return raw_grads, norm_corrs
