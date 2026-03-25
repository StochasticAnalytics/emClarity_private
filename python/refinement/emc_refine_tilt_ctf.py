"""Per-tilt CTF refinement loop.

Optimises per-tilt defocus offset, astigmatism magnitude/angle, and
per-particle Z offsets using either ADAM or L-BFGS-B.  Accepts pre-computed
data and reference Fourier transforms (from :class:`FourierTransformer`),
CTF parameters, and options.

Port reference: ``synthetic/EMC_refine_tilt_ctf.m`` (406 lines).

All parameters (3 tilt-global + N per-particle) are optimised from the
first iteration.  This matches production cryo-EM software (Warp/M by
Tegunov) and eliminates the H₀ re-initialisation problem that occurred
with the previous freeze/unfreeze two-phase design.

When ``global_only=True``, per-particle parameters are permanently frozen
and only the 3 tilt-global parameters are optimised.
"""

from __future__ import annotations

import dataclasses
import logging
import warnings
from typing import TYPE_CHECKING

import numpy as np

try:
    import cupy as cp

    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False
    cp = None

if TYPE_CHECKING:
    import cupy

    NDArray = np.ndarray | cupy.ndarray
else:
    NDArray = np.ndarray

from ..ctf.emc_ctf_params import CTFParams
from ..optimizers.emc_adam_optimizer import AdamOptimizer
from ..optimizers.emc_lbfgsb_optimizer import LBFGSBOptimizer
from .emc_ctf_gradients import (
    CTFCalculatorWithDerivatives,
    evaluate_score_and_gradient,
)
from .emc_fourier_utils import FourierTransformer
from .emc_scoring import create_peak_mask

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class RefinementOptions:
    """Configuration for per-tilt CTF refinement.

    Attributes:
        optimizer_type: Optimiser algorithm — ``'adam'`` or ``'lbfgsb'``.
        defocus_search_range: Symmetric bound on delta defocus (Angstroms).
        maximum_iterations: Hard iteration cap.
        minimum_global_iterations: Deprecated — retained for backward
            compatibility but ignored.  All parameters are optimised
            from the first iteration.
        global_only: When True, per-particle parameters are permanently
            frozen; only the 3 tilt-global parameters are optimised.
        lowpass_cutoff: Low-pass cutoff in Angstroms for reference bandpass.
        highpass_cutoff: High-pass cutoff in Angstroms for reference bandpass.
        shift_sigma: Gaussian penalty sigma for X/Y shifts (pixels).
        z_offset_sigma: Gaussian penalty sigma for per-particle z-offsets
            (Angstroms).
    """

    optimizer_type: str = "adam"
    defocus_search_range: float = 5000.0
    maximum_iterations: int = 15
    minimum_global_iterations: int = 3
    global_only: bool = False
    lowpass_cutoff: float = 10.0
    highpass_cutoff: float = 400.0
    shift_sigma: float = 5.0
    z_offset_sigma: float = 100.0


@dataclasses.dataclass
class RefinementResults:
    """Results from per-tilt CTF refinement.

    Attributes:
        delta_defocus_tilt: Per-tilt defocus offset (Angstroms).
        delta_half_astigmatism: Per-tilt half-astigmatism change (Angstroms).
        delta_astigmatism_angle: Per-tilt astigmatism angle change (radians).
        delta_z: Per-particle z-offsets, shape ``(N,)`` (Angstroms).
        shift_x: Per-particle X shifts, shape ``(N,)`` (pixels).
        shift_y: Per-particle Y shifts, shape ``(N,)`` (pixels).
        per_particle_scores: Per-particle CC peak heights, shape ``(N,)``.
        score_history: Total score at each iteration.
        converged: Whether the optimiser converged before hitting
            *maximum_iterations*.
    """

    delta_defocus_tilt: float
    delta_half_astigmatism: float
    delta_astigmatism_angle: float
    delta_z: np.ndarray
    shift_x: np.ndarray
    shift_y: np.ndarray
    per_particle_scores: np.ndarray
    score_history: list[float]
    converged: bool


# ---------------------------------------------------------------------------
# Bound computation helpers
# ---------------------------------------------------------------------------


def compute_half_astig_lower_bound(base_half_astigmatism: float) -> float:
    """Compute the lower bound for delta half-astigmatism.

    Prevents the effective half-astigmatism (``base + delta``) from crossing
    zero during optimisation, which would violate the ``df1 >= df2``
    convention.  A 1 Angstrom margin guards against degenerate ``df1 == df2``
    configurations.

    The constraint is::

        base_half + delta >= margin
        delta >= -(base_half - margin)

    Reference: PRD §Asymmetric Bounds, ``EMC_refine_tilt_ctf.m`` lines 122-124.

    Args:
        base_half_astigmatism: Current half-astigmatism from the base CTF
            parameters (Angstroms).  Must be >= 0 for canonical inputs.

    Returns:
        Lower bound for delta half-astigmatism (Angstroms).

    Raises:
        ValueError: If *base_half_astigmatism* is negative.
    """
    if base_half_astigmatism < 0:
        raise ValueError(
            f"base_half_astigmatism must be non-negative, "
            f"got {base_half_astigmatism}"
        )
    margin_angstroms = 1.0
    return -(base_half_astigmatism - margin_angstroms)


def _convergence_lookback(
    optimizer_type: str, global_only: bool, maximum_iterations: int,
) -> int:
    """Choose convergence lookback window based on optimizer and mode.

    ADAM oscillates during joint tilt-global + per-particle optimisation,
    so needs a longer lookback window to avoid triggering convergence on
    a transient dip.  L-BFGS-B converges monotonically and can detect
    plateaus with a shorter window.
    """
    if global_only:
        return 3
    if optimizer_type == "lbfgsb":
        return 5
    # ADAM: scale lookback with iteration budget
    return max(5, maximum_iterations // 3)


# ---------------------------------------------------------------------------
# Stagnation recovery helper
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _StagnationState:
    """Mutable state for L-BFGS-B stagnation recovery."""

    resets_remaining: int = 2
    last_reset_iter: int = 0
    cooldown: int = 5
    df_threshold: float = 20.0      # Angstroms
    ha_threshold: float = 10.0      # Angstroms
    angle_threshold: float = 0.02   # radians (~1.1 degrees)


def _reset_lbfgsb_if_stagnated(
    optimizer: AdamOptimizer | LBFGSBOptimizer,
    optimizer_type: str,
    global_only: bool,
    stag: _StagnationState,
    iteration: int,
) -> bool:
    """Check whether L-BFGS-B should reset its Hessian history.

    Returns True (and performs the reset) when the optimizer has converged
    but the tilt-global parameters indicate genuine correction is still
    underway.  Returns False if convergence should be trusted.
    """
    if optimizer_type != "lbfgsb" or global_only:
        return False
    if stag.resets_remaining <= 0:
        return False
    if not hasattr(optimizer, "reset_history"):
        return False

    cur_params = optimizer.get_current_parameters()
    params_indicate_correction = (
        abs(cur_params[0]) > stag.df_threshold
        or abs(cur_params[1]) > stag.ha_threshold
        or abs(cur_params[2]) > stag.angle_threshold
    )
    if not params_indicate_correction:
        return False

    optimizer.reset_history()  # type: ignore[attr-defined]
    stag.last_reset_iter = iteration
    stag.resets_remaining -= 1
    logger.debug(
        "L-BFGS-B history reset #%d at iter %d (params=[%.1f, %.1f, %.4f])",
        2 - stag.resets_remaining,
        iteration,
        cur_params[0], cur_params[1], cur_params[2],
    )
    return True


# ---------------------------------------------------------------------------
# Main refinement function
# ---------------------------------------------------------------------------


def refine_tilt_ctf(
    data_fts: list[NDArray],
    ref_fts: list[NDArray],
    base_ctf_params: CTFParams,
    tilt_angle_degrees: float,
    options: RefinementOptions,
    *,
    ctf_calculator: CTFCalculatorWithDerivatives | None = None,
    fourier_handler: FourierTransformer | None = None,
    peak_mask: np.ndarray | None = None,
) -> RefinementResults:
    """Run per-tilt CTF refinement loop.

    Optimises 3 global parameters (delta defocus, delta half-astigmatism,
    delta astigmatism angle) and *N* per-particle delta-z offsets using
    either ADAM or L-BFGS-B gradient descent with analytical gradients.

    All ``3 + N`` parameters are optimised jointly from the first
    iteration (matching Warp/M by Tegunov).  When ``global_only=True``,
    only the 3 tilt-global parameters are optimised; per-particle
    parameters remain frozen at zero throughout.

    After the loop, a df1/df2 canonicalisation check ensures that the
    reported defocus values maintain the ``df1 >= df2`` convention.

    Args:
        data_fts: Pre-computed, swap-phase-modulated, normalised data
            Fourier transforms.  Length *N* (one per particle).
        ref_fts: Pre-computed, pre-conjugated reference Fourier transforms.
            Length *N*.
        base_ctf_params: Base CTF parameters for this tilt.
        tilt_angle_degrees: Tilt angle of the current view (degrees).
        options: Refinement configuration.
        ctf_calculator: CTF calculator supporting
            ``compute_with_derivatives``.  If ``None``, a CPU fallback is
            created automatically.
        fourier_handler: :class:`FourierTransformer` matching the tile
            dimensions.  Inferred from *data_fts* shape if ``None``.
        peak_mask: Binary circular mask for peak search.  Created
            automatically if ``None``.

    Returns:
        :class:`RefinementResults` with optimised deltas and diagnostics.

    Raises:
        ValueError: If *data_fts* and *ref_fts* have different lengths,
            or if *optimizer_type* is not recognised.
    """
    n_particles = len(data_fts)
    if len(ref_fts) != n_particles:
        raise ValueError(
            f"data_fts ({n_particles}) and ref_fts ({len(ref_fts)}) "
            f"must have the same length."
        )

    # --- Zero-particle early return ---------------------------------------
    if n_particles == 0:
        return RefinementResults(
            delta_defocus_tilt=0.0,
            delta_half_astigmatism=0.0,
            delta_astigmatism_angle=0.0,
            delta_z=np.zeros(0, dtype=np.float64),
            shift_x=np.zeros(0, dtype=np.float64),
            shift_y=np.zeros(0, dtype=np.float64),
            per_particle_scores=np.zeros(0, dtype=np.float64),
            score_history=[],
            converged=True,
        )

    # --- Zero-iteration early return --------------------------------------
    if options.maximum_iterations <= 0:
        _dummy_params = np.zeros(3 + n_particles, dtype=np.float64)
        return RefinementResults(
            delta_defocus_tilt=0.0,
            delta_half_astigmatism=0.0,
            delta_astigmatism_angle=0.0,
            delta_z=np.zeros(n_particles, dtype=np.float64),
            shift_x=np.zeros(n_particles, dtype=np.float64),
            shift_y=np.zeros(n_particles, dtype=np.float64),
            per_particle_scores=np.zeros(n_particles, dtype=np.float64),
            score_history=[],
            converged=False,
        )

    # --- Infer / create helpers -------------------------------------------
    if ctf_calculator is None:
        from ..ctf.emc_ctf_cpu import CTFCalculatorCPU

        ctf_calculator = CTFCalculatorCPU()

    if fourier_handler is None:
        # Infer dimensions from the first data FT.
        # Half-grid layout: shape is (nx//2+1, ny).
        ft_shape = data_fts[0].shape
        if len(ft_shape) != 2:
            raise ValueError(
                f"data_fts elements must be 2-D arrays, "
                f"got {len(ft_shape)}-D with shape {ft_shape}"
            )
        half_nx, ny = ft_shape
        if half_nx < 2:
            raise ValueError(
                f"data_fts first axis ({half_nx}) too small for half-grid "
                f"convention (nx//2+1, ny); minimum is 2"
            )
        nx = (half_nx - 1) * 2
        # Validate half-grid convention: first axis should be the halved
        # axis.  For square or landscape images (nx <= ny), half_nx < ny.
        # For tall images this may not hold, so we only warn — not error.
        if half_nx > ny:
            logger.warning(
                "data_fts shape %s has first axis > second axis; verify "
                "half-grid convention (expected (nx//2+1, ny) where the "
                "first axis is halved).",
                ft_shape,
            )
        fourier_handler = FourierTransformer(nx, ny, use_gpu=False)
    else:
        nx = fourier_handler.nx
        ny = fourier_handler.ny

    if peak_mask is None:
        peak_mask = create_peak_mask(nx, ny, radius=float(nx // 4))

    # --- Parameter vector initialisation ----------------------------------
    n_params = 3 + n_particles
    initial_params = np.zeros(n_params, dtype=np.float64)

    # --- Bounds -----------------------------------------------------------
    dsr = options.defocus_search_range
    z_bound = options.z_offset_sigma * 3.0
    astig_angle_range = np.pi / 4.0  # [-45, +45] degrees

    # Asymmetric lower bound on half-astigmatism: prevent the effective
    # half-astigmatism (base + delta) from crossing zero during optimisation.
    # The 1A margin guards against degenerate df1 == df2 configurations.
    # Reference: PRD §Asymmetric Bounds, EMC_refine_tilt_ctf.m lines 122-124.
    base_half_val = float(base_ctf_params.half_astigmatism)
    half_astig_lower = compute_half_astig_lower_bound(base_half_val)

    lower_bounds = np.concatenate([
        np.array([-dsr, half_astig_lower, -astig_angle_range]),
        np.full(n_particles, -z_bound),
    ])
    upper_bounds = np.concatenate([
        np.array([dsr, dsr, astig_angle_range]),
        np.full(n_particles, z_bound),
    ])

    # --- Create optimiser -------------------------------------------------
    optimizer_type = options.optimizer_type.lower()
    if optimizer_type == "adam":
        optimizer = _create_adam_optimizer(
            initial_params, lower_bounds, upper_bounds, options, dsr,
            astig_angle_range, n_particles, n_params,
        )
    elif optimizer_type == "lbfgsb":
        optimizer = _create_lbfgsb_optimizer(
            initial_params, lower_bounds, upper_bounds, data_fts, ref_fts,
            base_ctf_params, ctf_calculator, fourier_handler,
            tilt_angle_degrees, peak_mask, options,
        )
    else:
        raise ValueError(
            f"Unknown optimizer_type '{options.optimizer_type}'. "
            f"Expected 'adam' or 'lbfgsb'."
        )

    # --- Freeze per-particle parameters if global_only --------------------
    if options.global_only:
        per_particle_indices = np.arange(3, n_params)
        optimizer.freeze_parameters(per_particle_indices)

    # --- Optimisation loop ------------------------------------------------
    score_history: list[float] = []
    per_particle_scores = np.zeros(n_particles, dtype=np.float64)
    shifts_xy = np.zeros((n_particles, 2), dtype=np.float64)
    converged = False
    nan_break = False
    convergence_n_lookback = _convergence_lookback(
        optimizer_type, options.global_only, options.maximum_iterations,
    )
    # L-BFGS-B stagnation recovery state (see _reset_lbfgsb_if_stagnated).
    stag = _StagnationState()

    for iteration in range(1, options.maximum_iterations + 1):
        params = optimizer.get_current_parameters()

        # --- Evaluate score and gradient ----------------------------------
        total_score, per_particle_scores, shifts_xy, gradient = (
            evaluate_score_and_gradient(
                params,
                data_fts,
                ref_fts,
                base_ctf_params,
                ctf_calculator,
                fourier_handler,
                tilt_angle_degrees,
                peak_mask,
                shift_sigma=options.shift_sigma,
                z_offset_sigma=options.z_offset_sigma,
            )
        )

        # Guard against non-finite scores — sanitise outputs and abort.
        if not np.isfinite(total_score):
            logger.warning(
                "Non-finite total_score (%.4g) at iteration %d — "
                "aborting optimisation.",
                total_score,
                iteration,
            )
            nan_break = True
            per_particle_scores = np.where(
                np.isfinite(per_particle_scores), per_particle_scores, 0.0,
            )
            shifts_xy = np.where(
                np.isfinite(shifts_xy), shifts_xy, 0.0,
            )
            break

        score_history.append(total_score)

        # --- Check convergence --------------------------------------------
        # score is natural positive CC; optimizer handles sign via bool
        optimizer.step(gradient, score=total_score, score_is_maximized=True)

        # After a history reset, skip convergence checking for cooldown
        # iterations so the Hessian has time to rebuild from fresh curvature.
        in_cooldown = (
            stag.last_reset_iter > 0
            and (iteration - stag.last_reset_iter) < stag.cooldown
        )
        if (
            not in_cooldown
            and optimizer.has_converged(
                n_lookback=convergence_n_lookback, threshold=0.001,
            )
            and not _reset_lbfgsb_if_stagnated(
                optimizer, optimizer_type, options.global_only,
                stag, iteration,
            )
        ):
            converged = True
            break

    # --- Final evaluation at converged parameters -------------------------
    final_params = optimizer.get_current_parameters()
    if not nan_break:
        final_score, per_particle_scores, shifts_xy, _ = (
            evaluate_score_and_gradient(
                final_params,
                data_fts,
                ref_fts,
                base_ctf_params,
                ctf_calculator,
                fourier_handler,
                tilt_angle_degrees,
                peak_mask,
                shift_sigma=options.shift_sigma,
                z_offset_sigma=options.z_offset_sigma,
            )
        )
        score_history.append(final_score)
    # --- Post-optimisation df1/df2 canonicalisation -----------------------
    delta_df = float(final_params[0])
    delta_half_astig = float(final_params[1])
    delta_angle = float(final_params[2])  # radians

    # Check if the final effective defocus yields df2 > df1.
    # Use the "worst case" particle (largest dz contribution) is not needed;
    # the swap decision is based on the tilt-global parameters only, since
    # per-particle dz affects both df1 and df2 equally (common-mode).
    eff_half_astig = base_half_val + delta_half_astig
    if eff_half_astig < 0.0:
        # df2 > df1 — swap and rotate angle by 90 degrees.
        delta_half_astig = -delta_half_astig - 2.0 * base_half_val
        delta_angle = delta_angle + np.pi / 2.0
        logger.info(
            "Post-optimisation df1/df2 swap applied: "
            "delta_half_astig=%.1f, delta_angle=%.4f rad",
            delta_half_astig,
            delta_angle,
        )

    # --- Log non-convergence warning --------------------------------------
    if not converged:
        if nan_break:
            warnings.warn(
                "CTF refinement aborted: non-finite score encountered.",
                stacklevel=2,
            )
        else:
            warnings.warn(
                f"CTF refinement did not converge within "
                f"{options.maximum_iterations} iterations.",
                stacklevel=2,
            )

    return RefinementResults(
        delta_defocus_tilt=delta_df,
        delta_half_astigmatism=delta_half_astig,
        delta_astigmatism_angle=delta_angle,
        delta_z=final_params[3:].copy(),
        shift_x=shifts_xy[:, 0].copy(),
        shift_y=shifts_xy[:, 1].copy(),
        per_particle_scores=per_particle_scores.copy(),
        score_history=score_history,
        converged=converged,
    )


# ---------------------------------------------------------------------------
# Optimiser factory helpers
# ---------------------------------------------------------------------------


def _create_adam_optimizer(
    initial_params: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    options: RefinementOptions,
    defocus_search_range: float,
    astig_angle_range: float,
    n_particles: int,
    n_params: int,
) -> AdamOptimizer:
    """Create and configure an ADAM optimiser for CTF refinement.

    Learning rates are auto-scaled from expected parameter ranges following
    the MATLAB ``adamOptimizer.auto_scale_learning_rate`` pattern.
    """
    optimizer = AdamOptimizer(initial_params)
    optimizer.set_bounds(lower_bounds, upper_bounds)

    # Expected parameter ranges for learning rate scaling.
    expected_ranges = np.zeros(n_params, dtype=np.float64)
    expected_ranges[0] = defocus_search_range              # defocus (A)
    expected_ranges[1] = defocus_search_range / 2.0        # half-astigmatism (A)
    expected_ranges[2] = astig_angle_range                 # angle (rad)
    expected_ranges[3:] = options.z_offset_sigma            # delta_z — use sigma
    optimizer.auto_scale_learning_rate(
        expected_ranges, options.maximum_iterations, safety_factor=3.0,
    )

    return optimizer


def _create_lbfgsb_optimizer(
    initial_params: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    data_fts: list[NDArray],
    ref_fts: list[NDArray],
    base_ctf_params: CTFParams,
    ctf_calculator: CTFCalculatorWithDerivatives,
    fourier_handler: FourierTransformer,
    tilt_angle_degrees: float,
    peak_mask: np.ndarray,
    options: RefinementOptions,
) -> LBFGSBOptimizer:
    """Create and configure an L-BFGS-B optimiser for CTF refinement.

    Sets the objective + gradient function for Wolfe line search, which
    evaluates the negated score and the minimisation gradient (since
    L-BFGS-B minimises).  Uses memory_size=20 to recover full BFGS
    with ~13 parameters.
    """
    optimizer = LBFGSBOptimizer(initial_params, memory_size=20)
    optimizer.set_bounds(lower_bounds, upper_bounds)

    # Objective + gradient for Wolfe line search.
    # evaluate_score_and_gradient returns (score, ..., gradient) where
    # gradient is already ∂(-score)/∂θ (negated at line 418 of
    # emc_ctf_gradients.py for minimisation).
    def objective_and_gradient(
        params: np.ndarray,
    ) -> tuple[float, np.ndarray]:
        score, _, _, grad = evaluate_score_and_gradient(
            params,
            data_fts,
            ref_fts,
            base_ctf_params,
            ctf_calculator,
            fourier_handler,
            tilt_angle_degrees,
            peak_mask,
            shift_sigma=options.shift_sigma,
            z_offset_sigma=options.z_offset_sigma,
        )
        return -score, grad

    optimizer.set_objective_and_gradient(objective_and_gradient)

    return optimizer
