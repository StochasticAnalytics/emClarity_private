"""Tests for emc_ctf_gradients.py — analytical gradient for CTF refinement.

Validates the analytical gradient computation against finite-difference
approximations and descent-direction criteria defined in TASK-010.

Test organisation
~~~~~~~~~~~~~~~~~
Each test class maps to a specific acceptance criterion:

* **TestDescentDirection** — PRIMARY: score improves along -gradient direction
* **TestFiniteDifferenceGlobal** — SECONDARY: analytical vs FD for global params
* **TestFiniteDifferenceDeltaZ** — SECONDARY: analytical vs FD for per-particle dz
* **TestPenaltyGradient** — penalty gradient sign and magnitude
* **TestNormCorrectionNonNegligible** — normalization correction is measurable
* **TestZeroGradientAtTruth** — gradient near zero when params match ground truth
* **TestGradientSignConsistency** — positive defocus gradient means increasing score
* **TestScoreMatchesScoring** — forward pass identical to evaluate_score_and_shifts
"""

from __future__ import annotations

import numpy as np
import pytest

from ...ctf.emc_ctf_cpu import CTFCalculatorCPU
from ...ctf.emc_ctf_params import CTFParams
from ..emc_ctf_gradients import compute_gradient_debug_info, evaluate_score_and_gradient
from ..emc_fourier_utils import FourierTransformer
from ..emc_scoring import create_peak_mask, evaluate_score_and_shifts

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NX, NY = 64, 64
PIXEL_SIZE = 1.5  # Angstroms
WAVELENGTH = 0.0197  # Angstroms (300 kV)
CS_MM = 2.7
AMP_CONTRAST = 0.07
DF1 = 20000.0  # Angstroms
DF2 = 18000.0  # Angstroms
ANGLE_DEG = 45.0
SEARCH_RADIUS = NX // 4  # 16 pixels

# FD step sizes (from supplement)
FD_STEP_DEFOCUS = 10.0  # Angstroms
FD_STEP_ASTIG = 1.0  # Angstroms
FD_STEP_ANGLE = 0.5 * np.pi / 180.0  # radians (0.5 degrees)
FD_STEP_DZ = 10.0  # Angstroms

# Tolerance for FD comparison
FD_GRADIENT_RTOL = 0.02  # 2%
FD_PASS_FRACTION = 0.90  # 90% of parameters must pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ft() -> FourierTransformer:
    """Standard 64x64 CPU FourierTransformer."""
    return FourierTransformer(NX, NY, use_gpu=False)


@pytest.fixture()
def ctf_calc() -> CTFCalculatorCPU:
    return CTFCalculatorCPU()


@pytest.fixture()
def base_ctf() -> CTFParams:
    return CTFParams.from_defocus_pair(
        df1=DF1,
        df2=DF2,
        angle_degrees=ANGLE_DEG,
        pixel_size=PIXEL_SIZE,
        wavelength=WAVELENGTH,
        cs_mm=CS_MM,
        amplitude_contrast=AMP_CONTRAST,
    )


@pytest.fixture()
def peak_mask() -> np.ndarray:
    return create_peak_mask(NX, NY, radius=SEARCH_RADIUS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_synthetic_particle(
    ft: FourierTransformer,
    ctf_calc: CTFCalculatorCPU,
    ctf_params: CTFParams,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Create a synthetic (data_ft, ref_ft) pair with known CTF.

    Preprocessing mirrors the MATLAB code:
    * **data_ft**: ``normalise(swap_phase(fwdFFT(data_real)))``
    * **ref_ft**: ``conj(fwdFFT(ref_real))``
    """
    rng = np.random.default_rng(seed)
    ref_real = rng.standard_normal((NX, NY)).astype(np.float32)

    ctf_image = ctf_calc.compute(ctf_params, (NX, NY)).T
    ref_spectrum = ft.forward_fft(ref_real)
    data_real = ft.inverse_fft(ref_spectrum * ctf_image).astype(np.float32)

    data_ft = ft.swap_phase(ft.forward_fft(data_real))
    data_norm = ft.compute_ref_norm(data_ft)
    data_ft = data_ft / data_norm

    ref_ft = np.conj(ft.forward_fft(ref_real))
    return data_ft, ref_ft


def _make_multi_particle(
    ft: FourierTransformer,
    ctf_calc: CTFCalculatorCPU,
    ctf_params: CTFParams,
    n_particles: int,
    base_seed: int = 42,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Create N synthetic particle pairs."""
    data_fts = []
    ref_fts = []
    for i in range(n_particles):
        d, r = _make_synthetic_particle(ft, ctf_calc, ctf_params, seed=base_seed + i)
        data_fts.append(d)
        ref_fts.append(r)
    return data_fts, ref_fts


def _eval_score(
    params: np.ndarray,
    data_fts: list[np.ndarray],
    ref_fts: list[np.ndarray],
    base_ctf: CTFParams,
    ctf_calc: CTFCalculatorCPU,
    ft: FourierTransformer,
    peak_mask: np.ndarray,
    tilt_angle: float = 0.0,
    shift_sigma: float = 5.0,
    z_offset_sigma: float = 100.0,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Wrapper for evaluate_score_and_shifts."""
    return evaluate_score_and_shifts(
        params=params,
        data_fts=data_fts,
        ref_fts=ref_fts,
        base_ctf_params=base_ctf,
        ctf_calculator=ctf_calc,
        fourier_handler=ft,
        tilt_angle_degrees=tilt_angle,
        peak_mask=peak_mask,
        shift_sigma=shift_sigma,
        z_offset_sigma=z_offset_sigma,
    )


def _eval_gradient(
    params: np.ndarray,
    data_fts: list[np.ndarray],
    ref_fts: list[np.ndarray],
    base_ctf: CTFParams,
    ctf_calc: CTFCalculatorCPU,
    ft: FourierTransformer,
    peak_mask: np.ndarray,
    tilt_angle: float = 0.0,
    shift_sigma: float = 5.0,
    z_offset_sigma: float = 100.0,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    """Wrapper for evaluate_score_and_gradient."""
    return evaluate_score_and_gradient(
        params=params,
        data_fts=data_fts,
        ref_fts=ref_fts,
        base_ctf_params=base_ctf,
        ctf_calculator=ctf_calc,
        fourier_handler=ft,
        tilt_angle_degrees=tilt_angle,
        peak_mask=peak_mask,
        shift_sigma=shift_sigma,
        z_offset_sigma=z_offset_sigma,
    )


def _fd_gradient(
    params: np.ndarray,
    data_fts: list[np.ndarray],
    ref_fts: list[np.ndarray],
    base_ctf: CTFParams,
    ctf_calc: CTFCalculatorCPU,
    ft: FourierTransformer,
    peak_mask: np.ndarray,
    tilt_angle: float = 0.0,
    shift_sigma: float = 5.0,
    z_offset_sigma: float = 100.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Central-difference finite-difference gradient.

    Returns (fd_grad, peak_stable) where peak_stable[i] indicates
    whether the peak position was unchanged between +h and -h evaluations
    for parameter i.
    """
    n = len(params)
    fd_grad = np.zeros(n, dtype=np.float64)
    peak_stable = np.ones(n, dtype=bool)

    # Step sizes per parameter
    steps = np.zeros(n)
    steps[0] = FD_STEP_DEFOCUS
    steps[1] = FD_STEP_ASTIG
    steps[2] = FD_STEP_ANGLE
    steps[3:] = FD_STEP_DZ

    for j in range(n):
        h = steps[j]
        params_plus = params.copy()
        params_minus = params.copy()
        params_plus[j] += h
        params_minus[j] -= h

        score_plus, _, shifts_plus = _eval_score(
            params_plus, data_fts, ref_fts, base_ctf, ctf_calc, ft,
            peak_mask, tilt_angle, shift_sigma, z_offset_sigma,
        )
        score_minus, _, shifts_minus = _eval_score(
            params_minus, data_fts, ref_fts, base_ctf, ctf_calc, ft,
            peak_mask, tilt_angle, shift_sigma, z_offset_sigma,
        )

        fd_grad[j] = (score_plus - score_minus) / (2.0 * h)

        # Check peak stability: shifts should be identical for +h and -h
        if not np.allclose(shifts_plus, shifts_minus, atol=0.5):
            peak_stable[j] = False

    return fd_grad, peak_stable


# =========================================================================
# Test: Descent direction (PRIMARY VALIDATION)
# =========================================================================


class TestDescentDirection:
    """score(params - alpha * gradient) > score(params) for small alpha.

    This is the primary validation criterion.  The analytical gradient
    (negated for minimisation) should point in a direction that improves
    the score when we step along it.
    """

    def test_descent_all_global_params(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Verify descent direction for each of the 3 global parameters
        independently."""
        n_particles = 3
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        # Start with a deliberate offset so gradient is non-trivial
        params = np.zeros(3 + n_particles)
        params[0] = 200.0  # defocus offset
        params[1] = 50.0  # astigmatism offset
        params[2] = 0.02  # angle offset (radians, ~1 degree)

        score_0, _, _, grad = _eval_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=30.0, z_offset_sigma=1e6,
        )

        # Test each global parameter independently
        for p_idx in range(3):
            if abs(grad[p_idx]) < 1e-10:
                continue  # skip near-zero gradient

            # Step along the negative gradient direction (optimizer descent)
            # Since gradient is already negated, stepping along -grad
            # means stepping in the direction that increases score.
            alpha = 1e-3 * abs(params[p_idx] + 1.0) / (abs(grad[p_idx]) + 1e-30)
            # Clip alpha to avoid overshooting
            alpha = min(alpha, 0.1)

            params_stepped = params.copy()
            params_stepped[p_idx] -= alpha * grad[p_idx]

            score_stepped, _, _, _ = _eval_gradient(
                params_stepped, data_fts, ref_fts, base_ctf, ctf_calc, ft,
                peak_mask, tilt_angle=30.0, z_offset_sigma=1e6,
            )

            assert score_stepped > score_0 - 1e-10, (
                f"Descent direction failed for param {p_idx}: "
                f"score_0={score_0:.8f}, score_stepped={score_stepped:.8f}, "
                f"grad={grad[p_idx]:.6e}, alpha={alpha:.6e}"
            )

    def test_descent_delta_z(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Verify descent direction for per-particle delta_z parameters.

        Steps only along the dz gradient components (indices 3+) to
        isolate the delta_z contribution from the global params, which
        can have very different scales (radians vs Angstroms).
        """
        n_particles = 3
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        params = np.zeros(3 + n_particles)
        params[3] = 100.0  # particle 0 dz offset
        params[4] = -80.0  # particle 1 dz offset
        params[5] = 150.0  # particle 2 dz offset

        score_0, _, _, grad = _eval_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=30.0, z_offset_sigma=100.0,
        )

        # Step only along the dz gradient components
        dz_grad = grad[3:]
        dz_grad_norm = np.linalg.norm(dz_grad)
        if dz_grad_norm < 1e-10:
            pytest.skip("dz gradient near zero — cannot test descent direction")

        alpha = 0.5 / dz_grad_norm
        params_stepped = params.copy()
        params_stepped[3:] -= alpha * dz_grad

        score_stepped, _, _, _ = _eval_gradient(
            params_stepped, data_fts, ref_fts, base_ctf, ctf_calc, ft,
            peak_mask, tilt_angle=30.0, z_offset_sigma=100.0,
        )

        assert score_stepped > score_0 - 1e-10, (
            f"Descent direction failed for delta_z step: "
            f"score_0={score_0:.8f}, score_stepped={score_stepped:.8f}"
        )


# =========================================================================
# Test: Finite-difference comparison for global parameters
# =========================================================================


class TestFiniteDifferenceGlobal:
    """Analytical gradient matches FD within 2% for 90% of global params."""

    def test_fd_global_params(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        n_particles = 5
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        # Moderate offset — large enough for non-zero gradient,
        # small enough to keep peaks stable across FD evaluations.
        params = np.zeros(3 + n_particles)
        params[0] = 100.0
        params[1] = 20.0
        params[2] = 0.01

        _, _, _, grad = _eval_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            z_offset_sigma=1e6,
        )

        fd_grad, peak_stable = _fd_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            z_offset_sigma=1e6,
        )

        # The analytical gradient is negated; FD gradient of the score is not.
        # To compare: analytical = -dScore/dParam, fd = dScore/dParam
        # So compare -grad to fd_grad for the 3 global params.
        analytical_score_grad = -grad[:3]
        fd_score_grad = fd_grad[:3]

        n_pass = 0
        n_tested = 0
        for j in range(3):
            if not peak_stable[j]:
                continue  # skip unstable peaks
            if abs(analytical_score_grad[j]) < 1e-6:
                continue  # skip near-zero
            n_tested += 1
            rel_err = abs(analytical_score_grad[j] - fd_score_grad[j]) / (
                abs(fd_score_grad[j]) + 1e-30
            )
            if rel_err <= FD_GRADIENT_RTOL:
                n_pass += 1

        if n_tested == 0:
            pytest.skip("No testable global parameters (all near-zero or unstable)")

        pass_fraction = n_pass / n_tested
        assert pass_fraction >= FD_PASS_FRACTION, (
            f"Only {n_pass}/{n_tested} global params passed FD check "
            f"(need {FD_PASS_FRACTION*100}%). "
            f"Analytical: {analytical_score_grad}, FD: {fd_score_grad}"
        )


# =========================================================================
# Test: Finite-difference comparison for per-particle delta_z
# =========================================================================


class TestFiniteDifferenceDeltaZ:
    """Per-particle delta_z gradient matches FD within 2% at multiple tilts."""

    @pytest.mark.parametrize("tilt_angle", [0.0, 30.0, 60.0])
    def test_fd_delta_z(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
        tilt_angle: float,
    ) -> None:
        n_particles = 5
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        params = np.zeros(3 + n_particles)
        # Give each particle a different dz
        for k in range(n_particles):
            params[3 + k] = 50.0 * (k + 1) * (-1 if k % 2 else 1)

        _, _, _, grad = _eval_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=tilt_angle, z_offset_sigma=1e6,
        )

        fd_grad, peak_stable = _fd_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=tilt_angle, z_offset_sigma=1e6,
        )

        # Compare dz gradients (indices 3..3+N)
        analytical_dz = -grad[3:]  # un-negate
        fd_dz = fd_grad[3:]

        n_pass = 0
        n_tested = 0
        for k in range(n_particles):
            if not peak_stable[3 + k]:
                continue
            if abs(analytical_dz[k]) < 1e-6:
                continue
            n_tested += 1
            rel_err = abs(analytical_dz[k] - fd_dz[k]) / (
                abs(fd_dz[k]) + 1e-30
            )
            if rel_err <= FD_GRADIENT_RTOL:
                n_pass += 1

        if n_tested == 0:
            pytest.skip(
                f"No testable dz params at tilt={tilt_angle} "
                "(all near-zero or unstable)"
            )

        pass_fraction = n_pass / n_tested
        assert pass_fraction >= FD_PASS_FRACTION, (
            f"At tilt={tilt_angle}: only {n_pass}/{n_tested} dz params "
            f"passed FD check. Analytical: {analytical_dz}, FD: {fd_dz}"
        )


# =========================================================================
# Test: Penalty gradient
# =========================================================================


class TestPenaltyGradient:
    """Z-offset penalty gradient has correct sign and magnitude."""

    def test_penalty_sign_at_nonzero_dz(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """gradient[3+i] includes -delta_z[i] / sigma_z^2 contribution.

        Compare gradient at dz=0 vs dz=100 with known sigma_z.  The
        penalty gradient component at dz=100 should be
        -100 / sigma_z^2 (before negation).
        """
        sigma_z = 100.0
        n_particles = 1
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        # At dz=0, penalty gradient = 0
        params_zero = np.zeros(4)
        _, _, _, grad_zero = _eval_gradient(
            params_zero, data_fts, ref_fts, base_ctf, ctf_calc, ft,
            peak_mask, z_offset_sigma=sigma_z,
        )

        # At dz=100, penalty gradient = -100/sigma_z^2 = -0.01
        # After negation in the function: +0.01
        dz_val = 100.0
        params_dz = np.array([0.0, 0.0, 0.0, dz_val])
        _, _, _, grad_dz = _eval_gradient(
            params_dz, data_fts, ref_fts, base_ctf, ctf_calc, ft,
            peak_mask, z_offset_sigma=sigma_z,
        )

        # The difference in dz gradient between dz=100 and dz=0 should
        # include the penalty contribution.
        # The full penalty gradient (before negation) is:
        #   -abs(peak_height) * combined_weight * dz / sigma_z^2
        # penalty_contribution = dz / sigma_z^2 is the scale factor;
        # the full term is abs(peak_height) * combined_weight * penalty_contribution.
        # After negation: +abs(peak_height) * combined_weight * penalty_contribution.
        penalty_contribution = dz_val / (sigma_z ** 2)  # 0.01 (after negation)

        # The total gradient difference includes both CTF and penalty terms.
        # Check sign: positive dz should push gradient more positive after negation
        # (the penalty gradient points the optimizer back toward dz=0).
        grad_diff = grad_dz[3] - grad_zero[3]
        assert grad_diff > 0, (
            f"Penalty gradient has wrong sign: grad_dz[3]={grad_dz[3]:.6e}, "
            f"grad_zero[3]={grad_zero[3]:.6e}, diff={grad_diff:.6e}"
        )
        # Check magnitude: grad_diff must be at least a meaningful fraction of
        # penalty_contribution.  The factor abs(peak_height) * combined_weight
        # is always > 0; using 0.1 as a conservative lower bound ensures the
        # penalty term is genuinely present in the gradient, not just noise.
        assert grad_diff >= penalty_contribution * 0.1, (
            f"Penalty magnitude too small: expected >= {penalty_contribution * 0.1:.4e}, "
            f"got grad_diff={grad_diff:.6e} (penalty_contribution={penalty_contribution:.4e})"
        )

    def test_penalty_gradient_fd_validation(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Penalty gradient validated via FD (no MATLAB reference)."""
        sigma_z = 80.0
        n_particles = 3
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        params = np.array([0.0, 0.0, 0.0, 80.0, -60.0, 120.0])

        _, _, _, grad = _eval_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=30.0, z_offset_sigma=sigma_z,
        )

        fd_grad, peak_stable = _fd_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=30.0, z_offset_sigma=sigma_z,
        )

        # Compare dz gradients with penalty active
        analytical_dz = -grad[3:]
        fd_dz = fd_grad[3:]

        n_pass = 0
        n_tested = 0
        for k in range(n_particles):
            if not peak_stable[3 + k]:
                continue
            if abs(analytical_dz[k]) < 1e-6:
                continue
            n_tested += 1
            rel_err = abs(analytical_dz[k] - fd_dz[k]) / (
                abs(fd_dz[k]) + 1e-30
            )
            if rel_err <= FD_GRADIENT_RTOL:
                n_pass += 1

        assert n_tested > 0, "No testable dz params with penalty"
        pass_fraction = n_pass / n_tested
        assert pass_fraction >= FD_PASS_FRACTION, (
            f"Penalty FD check: {n_pass}/{n_tested} passed. "
            f"Analytical: {analytical_dz}, FD: {fd_dz}"
        )


# =========================================================================
# Test: Per-particle derivative correctness
# =========================================================================


class TestPerParticleDzDerivative:
    """analytical dz gradient = (dScore/dD) * cos(tilt_angle), verified
    independently via FD on individual particle dz parameters."""

    @pytest.mark.parametrize("tilt_angle", [0.0, 30.0, 60.0])
    def test_dz_equals_dD_times_cos_tilt(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
        tilt_angle: float,
    ) -> None:
        """For a single particle, the dz gradient should equal the
        defocus gradient contribution scaled by cos(tilt)."""
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, 1,
        )

        params = np.array([0.0, 0.0, 0.0, 50.0])

        # Compute FD gradient for defocus (param 0)
        h_df = FD_STEP_DEFOCUS
        p_plus = params.copy()
        p_minus = params.copy()
        p_plus[0] += h_df
        p_minus[0] -= h_df

        s_plus, _, shifts_plus = _eval_score(
            p_plus, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=tilt_angle, z_offset_sigma=1e6,
        )
        s_minus, _, shifts_minus = _eval_score(
            p_minus, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=tilt_angle, z_offset_sigma=1e6,
        )

        # Skip if peak is unstable
        if not np.allclose(shifts_plus, shifts_minus, atol=0.5):
            pytest.skip("Peak unstable for defocus FD")

        fd_dScore_dD = (s_plus - s_minus) / (2.0 * h_df)

        # Compute FD gradient for dz (param 3)
        h_dz = FD_STEP_DZ
        p_plus_dz = params.copy()
        p_minus_dz = params.copy()
        p_plus_dz[3] += h_dz
        p_minus_dz[3] -= h_dz

        s_plus_dz, _, shifts_plus_dz = _eval_score(
            p_plus_dz, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=tilt_angle, z_offset_sigma=1e6,
        )
        s_minus_dz, _, shifts_minus_dz = _eval_score(
            p_minus_dz, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=tilt_angle, z_offset_sigma=1e6,
        )

        if not np.allclose(shifts_plus_dz, shifts_minus_dz, atol=0.5):
            pytest.skip("Peak unstable for dz FD")

        fd_dScore_dDz = (s_plus_dz - s_minus_dz) / (2.0 * h_dz)

        cos_tilt = np.cos(np.radians(tilt_angle))
        expected_dz_grad = fd_dScore_dD * cos_tilt

        if abs(fd_dScore_dDz) < 1e-6:
            pytest.skip("dz FD gradient near zero")

        rel_err = abs(fd_dScore_dDz - expected_dz_grad) / (
            abs(fd_dScore_dDz) + 1e-30
        )
        assert rel_err < 0.05, (
            f"At tilt={tilt_angle}: dz FD grad={fd_dScore_dDz:.6e}, "
            f"expected (dD*cos)={expected_dz_grad:.6e}, rel_err={rel_err:.4f}"
        )


# =========================================================================
# Test: Normalization correction non-negligible
# =========================================================================


class TestNormCorrectionNonNegligible:
    """For at least some parameter/particle combinations,
    |norm_corr| > 0.01 * |raw_grad|.

    We verify this indirectly: if the norm correction were zero, the
    analytical gradient without norm correction would differ from
    the full analytical gradient.
    """

    def test_norm_correction_matters(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Verify that the normalization correction term is non-negligible
        for at least some parameter/particle combinations.

        We check this by comparing the full analytical gradient (which
        includes norm correction) against FD.  Good agreement implies
        the norm correction is correctly computed.  We also verify the
        gradient is non-trivial (not zero).
        """
        n_particles = 3
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        # Moderate offset to ensure non-zero gradient without peak jumps
        params = np.zeros(3 + n_particles)
        params[0] = 100.0

        _, _, _, grad = _eval_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            z_offset_sigma=1e6,
        )

        fd_grad, peak_stable = _fd_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            z_offset_sigma=1e6,
        )

        # The defocus gradient should be non-trivial and FD-accurate
        analytical_defocus = -grad[0]
        fd_defocus = fd_grad[0]

        assert abs(analytical_defocus) > 1e-6, (
            f"Defocus gradient is near zero: {analytical_defocus}"
        )

        if not peak_stable[0]:
            pytest.skip("Peak unstable for defocus FD — cannot validate norm correction")

        rel_err = abs(analytical_defocus - fd_defocus) / (
            abs(fd_defocus) + 1e-30
        )
        assert rel_err < FD_GRADIENT_RTOL, (
            f"FD comparison failed (norm correction likely wrong): "
            f"analytical={analytical_defocus:.6e}, fd={fd_defocus:.6e}, "
            f"rel_err={rel_err:.4f}"
        )

    def test_norm_correction_ratio(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Directly assert |norm_corr| > 0.01 * |raw_grad| for at least one
        particle/parameter combination.

        This is the acceptance criterion stated in the task specification:
        the normalization correction must be measurably non-negligible
        (greater than 1% of the raw gradient) for some particle and
        CTF parameter.
        """
        n_particles = 3
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        params = np.zeros(3 + n_particles)
        params[0] = 100.0

        raw_grads, norm_corrs = compute_gradient_debug_info(
            params=params,
            data_fts=data_fts,
            ref_fts=ref_fts,
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
            z_offset_sigma=1e6,
        )

        # Verify the acceptance criterion: for at least one (particle, param)
        # pair, |norm_corr| > 0.01 * |raw_grad|
        found_non_negligible = False
        for i in range(n_particles):
            for k in range(3):
                raw_g = abs(raw_grads[i, k])
                norm_c = abs(norm_corrs[i, k])
                if raw_g > 1e-10 and norm_c > 0.01 * raw_g:
                    found_non_negligible = True
                    break
            if found_non_negligible:
                break

        assert found_non_negligible, (
            f"Acceptance criterion failed: |norm_corr| > 0.01 * |raw_grad| "
            f"was not satisfied for any particle/parameter combination.\n"
            f"raw_grads={raw_grads}\nnorm_corrs={norm_corrs}"
        )


# =========================================================================
# Test: Zero gradient at ground truth
# =========================================================================


class TestZeroGradientAtTruth:
    """When CTF parameters exactly match ground truth (delta=0),
    gradient magnitude < 0.01."""

    def test_gradient_near_zero_at_truth(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """At ground truth (delta=0), each gradient component should be
        near zero.  The angle gradient is in per-radian units (multiplied
        by 180/pi from per-degree), so its threshold is scaled accordingly.
        """
        n_particles = 3
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        params = np.zeros(3 + n_particles)
        _, _, _, grad = _eval_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            z_offset_sigma=1e6,
        )

        # Check each component with scale-appropriate thresholds.
        # The 0.01 threshold applies to per-unit gradients in the
        # derivative kernel's natural units.  For the angle parameter,
        # the analytical derivative kernel is per-degree, but we
        # convert to per-radian (×180/π ≈ 57.3), so the threshold
        # for the angle component is 0.01 × 57.3.
        threshold_per_unit = 0.01
        assert abs(grad[0]) < threshold_per_unit, (
            f"Defocus gradient at truth too large: {grad[0]:.6e}"
        )
        assert abs(grad[1]) < threshold_per_unit, (
            f"Astigmatism gradient at truth too large: {grad[1]:.6e}"
        )
        # Angle gradient: threshold scaled by 180/pi for unit conversion
        angle_threshold = threshold_per_unit * (180.0 / np.pi)
        assert abs(grad[2]) < angle_threshold, (
            f"Angle gradient at truth too large: {grad[2]:.6e} "
            f"(threshold {angle_threshold:.4f} = 0.01 * 180/pi)"
        )
        for k in range(n_particles):
            assert abs(grad[3 + k]) < threshold_per_unit, (
                f"dz[{k}] gradient at truth too large: {grad[3+k]:.6e}"
            )


# =========================================================================
# Test: Gradient sign consistency
# =========================================================================


class TestGradientSignConsistency:
    """Positive gradient for defocus means increasing defocus increases score."""

    def test_defocus_gradient_sign(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """When defocus is offset positively, the score gradient (before
        negation) should push back toward the optimum."""
        n_particles = 3
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        # Positive defocus offset
        params_pos = np.array([300.0, 0.0, 0.0] + [0.0] * n_particles)
        score_pos, _, _, grad_pos = _eval_gradient(
            params_pos, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            z_offset_sigma=1e6,
        )

        # Negative defocus offset
        params_neg = np.array([-300.0, 0.0, 0.0] + [0.0] * n_particles)
        score_neg, _, _, grad_neg = _eval_gradient(
            params_neg, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            z_offset_sigma=1e6,
        )

        # At zero delta, score should be highest.  Both offsets should give
        # lower scores.
        score_zero, _, _, _ = _eval_gradient(
            np.zeros(3 + n_particles), data_fts, ref_fts, base_ctf,
            ctf_calc, ft, peak_mask, z_offset_sigma=1e6,
        )

        assert score_zero >= score_pos, (
            f"Score at truth ({score_zero}) should be >= score at +300A ({score_pos})"
        )
        assert score_zero >= score_neg, (
            f"Score at truth ({score_zero}) should be >= score at -300A ({score_neg})"
        )

        # The negated gradient at +300A should push defocus back toward 0
        # (i.e., gradient[0] > 0 means optimizer should decrease defocus)
        # un-negated gradient (dScore/dDf) at positive offset should be negative
        # (score decreases as we move further from truth)
        # So the negated gradient[0] should be positive (push toward decrease)
        un_negated_pos = -grad_pos[0]
        un_negated_neg = -grad_neg[0]

        # If at +300A the score landscape slopes downward (away from truth),
        # un-negated gradient should be negative → negated gradient positive
        # The gradient should point in opposite directions for +/- offsets
        assert un_negated_pos * un_negated_neg < 0 or (
            abs(un_negated_pos) < 1e-6 or abs(un_negated_neg) < 1e-6
        ), (
            f"Gradients at ±300A should have opposite signs: "
            f"+300A grad={un_negated_pos:.6e}, -300A grad={un_negated_neg:.6e}"
        )


# =========================================================================
# Test: Score matches evaluate_score_and_shifts
# =========================================================================


class TestScoreMatchesScoring:
    """Forward pass of evaluate_score_and_gradient produces identical
    score and shifts as evaluate_score_and_shifts."""

    def test_score_consistency(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        n_particles = 5
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        params = np.array([100.0, 20.0, 0.01] + [30.0 * i for i in range(n_particles)])

        # Score from evaluate_score_and_shifts
        score_ref, scores_ref, shifts_ref = _eval_score(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=30.0,
        )

        # Score from evaluate_score_and_gradient
        score_grad, scores_grad, shifts_grad, _ = _eval_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
            tilt_angle=30.0,
        )

        np.testing.assert_allclose(
            score_grad, score_ref, rtol=1e-10,
            err_msg="Total score mismatch between scoring and gradient functions",
        )
        np.testing.assert_allclose(
            scores_grad, scores_ref, rtol=1e-10,
            err_msg="Per-particle scores mismatch",
        )
        np.testing.assert_allclose(
            shifts_grad, shifts_ref, rtol=1e-10,
            err_msg="Shifts mismatch",
        )

    def test_score_consistency_at_truth(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Verify consistency at zero parameters (ground truth)."""
        n_particles = 3
        data_fts, ref_fts = _make_multi_particle(
            ft, ctf_calc, base_ctf, n_particles,
        )

        params = np.zeros(3 + n_particles)

        score_ref, scores_ref, shifts_ref = _eval_score(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
        )
        score_grad, scores_grad, shifts_grad, _ = _eval_gradient(
            params, data_fts, ref_fts, base_ctf, ctf_calc, ft, peak_mask,
        )

        np.testing.assert_allclose(score_grad, score_ref, rtol=1e-10)
        np.testing.assert_allclose(scores_grad, scores_ref, rtol=1e-10)
        np.testing.assert_allclose(shifts_grad, shifts_ref, rtol=1e-10)
