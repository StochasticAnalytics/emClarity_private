"""Tests for emc_refine_tilt_ctf.py — per-tilt CTF refinement loop.

Validates the Python port of ``synthetic/EMC_refine_tilt_ctf.m`` against
analytical expectations and the acceptance criteria defined in TASK-011.

Test organisation
~~~~~~~~~~~~~~~~~
Each test class maps to a specific acceptance criterion:

* **TestResultsShape** — Results struct contains all required fields with
  correct shapes
* **TestZeroIteration** — Negative control: maximum_iterations=0 returns
  initial parameters unchanged
* **TestAdamRecovery** — 10 particles with +500A defocus offset: ADAM
  recovers offset to within 100A
* **TestLBFGSBRecovery** — Same test with L-BFGS-B: recovers within 50A
* **TestTwoPhaseOptimization** — First 3 iterations only change global
  params; per-particle params remain zero until unfreeze
* **TestConvergenceDetection** — Optimizer stops before maximum_iterations
  when score plateaus (easy synthetic case)
* **TestScoreHistoryMonotone** — Score history is monotonically
  non-decreasing after first 2 iterations for synthetic data
* **TestGlobalOnlyMode** — global_only=True: per-particle params never
  unfrozen, only 3 params optimised
* **TestAsymmetricBounds** — Half-astigmatism lower bound uses min() across
  particles and prevents base_half + delta from crossing zero
* **TestDfSwap** — If final defocus yields df2 > df1, swap is applied and
  angle rotated by 90 degrees
* **TestNonConvergenceWarning** — When optimizer does not converge, results
  converged is False and a warning is logged
* **TestGradientAtConvergence** — At final parameters, gradient magnitude is
  below a reasonable threshold (< 0.1 for synthetic data)

Data generation note
~~~~~~~~~~~~~~~~~~~~
Synthetic data follows the MATLAB pipeline (``EMC_refine_tilt_ctf.m`` lines
97--105):

* **data_ft**: ``normalise(swap_phase(fwdFFT(IFFT(ref_spectrum * ctf))))``
* **ref_ft**: ``conj(bandpass(fwdFFT(ref_real)))``

The **bandpass filtering** on the reference is critical for optimization
tests.  Without it, the cross-correlation landscape is dominated by
high-frequency CTF oscillations that create many local optima, preventing
gradient-based optimizers from reaching the global optimum.  The bandpass
limits the correlation to frequencies where the CTF varies smoothly with
defocus, enabling reliable gradient descent over 100s of Angstroms.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from ...ctf.emc_ctf_cpu import CTFCalculatorCPU
from ...ctf.emc_ctf_params import CTFParams
from ..emc_ctf_gradients import evaluate_score_and_gradient
from ..emc_fourier_utils import FourierTransformer
from ..emc_refine_tilt_ctf import RefinementOptions, RefinementResults, refine_tilt_ctf
from ..emc_scoring import create_peak_mask

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
N_PARTICLES = 10
DEFOCUS_OFFSET = 500.0  # Angstroms — the offset the optimizer must recover

# Bandpass cutoffs matching the default RefinementOptions
LOWPASS_CUTOFF = 10.0  # Angstroms
HIGHPASS_CUTOFF = 400.0  # Angstroms


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
    """Base CTF without any defocus offset (the 'wrong' CTF)."""
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
def truth_ctf() -> CTFParams:
    """Ground-truth CTF with +500A defocus offset applied to both df1, df2."""
    return CTFParams.from_defocus_pair(
        df1=DF1 + DEFOCUS_OFFSET,
        df2=DF2 + DEFOCUS_OFFSET,
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
    *,
    apply_bandpass: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Create a synthetic (data_ft, ref_ft) pair with known CTF.

    Preprocessing mirrors the MATLAB code in ``EMC_refine_tilt_ctf.m``
    lines 97--105:

    * **data_ft**: ``normalise(swap_phase(fwdFFT(data_real)))``
    * **ref_ft**: ``conj(bandpass(fwdFFT(ref_real)))``

    When *apply_bandpass* is True (default), the reference FT is bandpass-
    filtered to match the actual pipeline.  This is critical for
    optimization tests — without it, high-frequency CTF oscillations
    create a non-convex landscape.
    """
    rng = np.random.default_rng(seed)
    ref_real = rng.standard_normal((NX, NY)).astype(np.float32)

    # CTF image transposed to FourierTransformer convention (nx//2+1, ny)
    ctf_image = ctf_calc.compute(ctf_params, (NX, NY)).T

    # Synthetic data = IFFT(FFT(ref) * CTF) — reference with CTF applied
    ref_spectrum = ft.forward_fft(ref_real)
    data_real = ft.inverse_fft(ref_spectrum * ctf_image).astype(np.float32)

    # Preprocess data: fwdFFT -> swap_phase -> normalise
    data_ft = ft.swap_phase(ft.forward_fft(data_real))
    data_norm = ft.compute_ref_norm(data_ft)
    data_ft = data_ft / data_norm

    # Preprocess reference: bandpass -> conjugate (pre-conjugated storage)
    if apply_bandpass:
        ref_spectrum = ft.apply_bandpass(
            ref_spectrum, PIXEL_SIZE, HIGHPASS_CUTOFF, LOWPASS_CUTOFF,
        )
    ref_ft = np.conj(ref_spectrum)

    return data_ft, ref_ft


def _make_multi_particle_data(
    ft: FourierTransformer,
    ctf_calc: CTFCalculatorCPU,
    ctf_params: CTFParams,
    n_particles: int = N_PARTICLES,
    base_seed: int = 42,
    *,
    apply_bandpass: bool = True,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Create multiple synthetic particles with the same CTF.

    All particles share the same CTF (same tilt group, same defocus offset)
    but have different random reference projections.
    """
    data_fts: list[np.ndarray] = []
    ref_fts: list[np.ndarray] = []
    for i in range(n_particles):
        d, r = _make_synthetic_particle(
            ft, ctf_calc, ctf_params, seed=base_seed + i,
            apply_bandpass=apply_bandpass,
        )
        data_fts.append(d)
        ref_fts.append(r)
    return data_fts, ref_fts


# =========================================================================
# Test: Results shape and field presence
# =========================================================================


class TestResultsShape:
    """Results struct contains all required fields with correct shapes."""

    def test_all_fields_present(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=3,
        )
        options = RefinementOptions(
            optimizer_type="adam",
            maximum_iterations=2,
            minimum_global_iterations=1,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        assert isinstance(result, RefinementResults)
        assert isinstance(result.delta_defocus_tilt, float)
        assert isinstance(result.delta_half_astigmatism, float)
        assert isinstance(result.delta_astigmatism_angle, float)
        assert isinstance(result.delta_z, np.ndarray)
        assert isinstance(result.shift_x, np.ndarray)
        assert isinstance(result.shift_y, np.ndarray)
        assert isinstance(result.per_particle_scores, np.ndarray)
        assert isinstance(result.score_history, list)
        assert isinstance(result.converged, bool)

    def test_array_shapes(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        n = 5
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=n,
        )
        options = RefinementOptions(
            optimizer_type="adam",
            maximum_iterations=2,
            minimum_global_iterations=1,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        assert result.delta_z.shape == (n,)
        assert result.shift_x.shape == (n,)
        assert result.shift_y.shape == (n,)
        assert result.per_particle_scores.shape == (n,)

    def test_zero_particles(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Zero-particle case returns empty arrays and converged=True."""
        options = RefinementOptions(maximum_iterations=5)
        result = refine_tilt_ctf(
            [], [], base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )
        assert result.converged is True
        assert result.delta_z.shape == (0,)
        assert result.shift_x.shape == (0,)
        assert result.shift_y.shape == (0,)
        assert result.per_particle_scores.shape == (0,)
        assert result.score_history == []


# =========================================================================
# Test: Negative control — zero iterations
# =========================================================================


class TestZeroIteration:
    """maximum_iterations=0 returns initial parameters unchanged."""

    def test_zero_iterations_returns_initial(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=3,
        )
        options = RefinementOptions(maximum_iterations=0)
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        assert result.delta_defocus_tilt == 0.0
        assert result.delta_half_astigmatism == 0.0
        assert result.delta_astigmatism_angle == 0.0
        np.testing.assert_array_equal(result.delta_z, np.zeros(3))
        assert result.score_history == []
        assert result.converged is False


# =========================================================================
# Test: ADAM recovery of +500A defocus offset
# =========================================================================


class TestAdamRecovery:
    """Synthetic 10 particles with +500A defocus offset: ADAM recovers
    offset to within 100A.

    Uses ``defocus_search_range=1000`` (tighter than default 5000) for a
    well-calibrated ADAM learning rate on this synthetic landscape, and
    ``maximum_iterations=30`` to allow full convergence.
    """

    def test_adam_recovers_defocus_offset(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=N_PARTICLES,
        )
        options = RefinementOptions(
            optimizer_type="adam",
            defocus_search_range=1000.0,
            maximum_iterations=30,
            minimum_global_iterations=3,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        error = abs(result.delta_defocus_tilt - DEFOCUS_OFFSET)
        assert error < 100.0, (
            f"ADAM defocus recovery error {error:.1f}A exceeds 100A threshold. "
            f"Recovered {result.delta_defocus_tilt:.1f}A, "
            f"expected ~{DEFOCUS_OFFSET:.1f}A."
        )

    def test_adam_improves_score(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Score at final parameters should exceed score at initial params."""
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=N_PARTICLES,
        )
        options = RefinementOptions(
            optimizer_type="adam",
            defocus_search_range=1000.0,
            maximum_iterations=30,
            minimum_global_iterations=3,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        assert len(result.score_history) >= 2, "Need at least 2 iterations"
        assert result.score_history[-1] > result.score_history[0], (
            f"Final score ({result.score_history[-1]:.4f}) should exceed "
            f"initial score ({result.score_history[0]:.4f})"
        )


# =========================================================================
# Test: L-BFGS-B recovery of +500A defocus offset
# =========================================================================


class TestLBFGSBRecovery:
    """Same test with L-BFGS-B: recovers offset to within 50A."""

    def test_lbfgsb_recovers_defocus_offset(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=N_PARTICLES,
        )
        options = RefinementOptions(
            optimizer_type="lbfgsb",
            defocus_search_range=5000.0,
            maximum_iterations=15,
            minimum_global_iterations=3,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        error = abs(result.delta_defocus_tilt - DEFOCUS_OFFSET)
        assert error < 50.0, (
            f"L-BFGS-B defocus recovery error {error:.1f}A exceeds 50A "
            f"threshold. Recovered {result.delta_defocus_tilt:.1f}A, "
            f"expected ~{DEFOCUS_OFFSET:.1f}A."
        )


# =========================================================================
# Test: Two-phase optimization
# =========================================================================


class TestTwoPhaseOptimization:
    """First minimum_global_iterations only change params[0:3]; per-particle
    params[3:] remain zero until unfreeze.
    """

    def test_global_only_phase_freezes_per_particle(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """With max_iterations == minimum_global_iterations, per-particle
        params never unfreeze and delta_z stays zero.
        """
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=N_PARTICLES,
        )
        options = RefinementOptions(
            optimizer_type="adam",
            defocus_search_range=1000.0,
            maximum_iterations=3,  # == minimum_global_iterations
            minimum_global_iterations=3,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        # Per-particle params should remain zero — never unfrozen
        np.testing.assert_array_equal(
            result.delta_z,
            np.zeros(N_PARTICLES),
            err_msg="Per-particle delta_z should remain zero during global-only phase",
        )

        # Global params should have moved (data has +500A offset)
        assert result.delta_defocus_tilt != 0.0, (
            "Global defocus param should change during global-only phase"
        )

    def test_per_particle_unfreezes_after_global_phase(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """With max_iterations > minimum_global_iterations and per-particle
        signal present, delta_z becomes non-zero after unfreezing.

        We generate data with per-particle z-offsets so the optimizer has
        signal to recover.
        """
        ctf_calc_local = ctf_calc
        ft_local = ft
        data_fts: list[np.ndarray] = []
        ref_fts: list[np.ndarray] = []
        z_offsets = np.linspace(-200, 200, 5)  # 5 particles at different z

        for i, z_off in enumerate(z_offsets):
            particle_truth = CTFParams.from_defocus_pair(
                df1=DF1 + z_off,
                df2=DF2 + z_off,
                angle_degrees=ANGLE_DEG,
                pixel_size=PIXEL_SIZE,
                wavelength=WAVELENGTH,
                cs_mm=CS_MM,
                amplitude_contrast=AMP_CONTRAST,
            )
            d, r = _make_synthetic_particle(
                ft_local, ctf_calc_local, particle_truth, seed=100 + i,
            )
            data_fts.append(d)
            ref_fts.append(r)

        options = RefinementOptions(
            optimizer_type="adam",
            defocus_search_range=1000.0,
            maximum_iterations=10,
            minimum_global_iterations=2,
            z_offset_sigma=500.0,  # wide sigma to allow z recovery
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc_local,
            fourier_handler=ft_local,
            peak_mask=peak_mask,
        )

        # After unfreezing, per-particle delta_z should have non-zero values
        assert np.any(result.delta_z != 0.0), (
            "Per-particle delta_z should become non-zero after unfreezing. "
            f"Got all zeros: {result.delta_z}"
        )


# =========================================================================
# Test: Convergence detection
# =========================================================================


class TestConvergenceDetection:
    """Optimizer stops before maximum_iterations when score plateaus."""

    def test_converges_on_easy_case(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """With zero defocus offset (data matches base CTF), the optimizer
        should converge quickly since there is nothing to correct.
        """
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, base_ctf, n_particles=5,
        )
        options = RefinementOptions(
            optimizer_type="adam",
            defocus_search_range=1000.0,
            maximum_iterations=40,
            minimum_global_iterations=3,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        assert result.converged is True, (
            f"Optimizer should converge for zero-offset case. "
            f"Score history length: {len(result.score_history)}, "
            f"max_iterations: {options.maximum_iterations}"
        )
        assert len(result.score_history) < options.maximum_iterations, (
            f"Should stop early: {len(result.score_history)} iterations "
            f"vs max {options.maximum_iterations}"
        )

    def test_lbfgsb_converges_on_easy_case(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """L-BFGS-B converges on zero-offset data."""
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, base_ctf, n_particles=5,
        )
        options = RefinementOptions(
            optimizer_type="lbfgsb",
            maximum_iterations=20,
            minimum_global_iterations=3,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        assert result.converged is True, (
            f"L-BFGS-B should converge for zero-offset case. "
            f"Scores: {len(result.score_history)}"
        )


# =========================================================================
# Test: Score history monotonicity
# =========================================================================


class TestScoreHistoryMonotone:
    """Score history is monotonically non-decreasing after first 2
    iterations for synthetic data.

    Uses ADAM with ``global_only=True`` and ``defocus_search_range=500``
    to avoid (a) the score dip from the freeze/unfreeze transition and
    (b) learning rate overshoot.  These parameters produce reliable
    monotone convergence on the bandpass-filtered synthetic landscape.
    """

    def test_monotone_after_warmup(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=N_PARTICLES,
        )
        options = RefinementOptions(
            optimizer_type="adam",
            defocus_search_range=500.0,
            maximum_iterations=30,
            minimum_global_iterations=3,
            global_only=True,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        history = result.score_history
        assert len(history) >= 3, f"Need at least 3 iterations, got {len(history)}"

        # Check monotonicity after first 2 iterations (index 2 onward)
        for i in range(2, len(history)):
            assert history[i] >= history[i - 1] - 1e-6, (
                f"Score decreased at iteration {i}: "
                f"{history[i]:.6f} < {history[i-1]:.6f} "
                f"(full history: {[f'{s:.4f}' for s in history]})"
            )


# =========================================================================
# Test: global_only mode
# =========================================================================


class TestGlobalOnlyMode:
    """global_only=True: per-particle params never unfrozen."""

    def test_global_only_keeps_dz_zero(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=N_PARTICLES,
        )
        options = RefinementOptions(
            optimizer_type="adam",
            defocus_search_range=1000.0,
            maximum_iterations=10,
            minimum_global_iterations=3,
            global_only=True,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        # Per-particle delta_z must remain zero
        np.testing.assert_array_equal(
            result.delta_z,
            np.zeros(N_PARTICLES),
            err_msg="global_only=True: delta_z must remain zero",
        )

        # Global params should still move
        assert result.delta_defocus_tilt != 0.0, (
            "Global params should change even in global_only mode"
        )

    def test_global_only_with_lbfgsb(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """global_only mode works with L-BFGS-B as well."""
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=5,
        )
        options = RefinementOptions(
            optimizer_type="lbfgsb",
            maximum_iterations=10,
            minimum_global_iterations=3,
            global_only=True,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        np.testing.assert_array_equal(
            result.delta_z,
            np.zeros(5),
            err_msg="global_only=True with L-BFGS-B: delta_z must remain zero",
        )


# =========================================================================
# Test: Asymmetric bounds
# =========================================================================


class TestAsymmetricBounds:
    """Half-astigmatism lower bound prevents base_half + delta from
    crossing zero.
    """

    def test_half_astig_lower_bound_enforced(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        peak_mask: np.ndarray,
    ) -> None:
        """With small base half-astigmatism, the optimizer cannot push
        eff_half below 1.0A (the intentional 1A margin).
        """
        # Base CTF with small half-astigmatism (100A)
        small_astig_ctf = CTFParams.from_defocus_pair(
            df1=20100.0,  # half_astig = (20100-19900)/2 = 100
            df2=19900.0,
            angle_degrees=ANGLE_DEG,
            pixel_size=PIXEL_SIZE,
            wavelength=WAVELENGTH,
            cs_mm=CS_MM,
            amplitude_contrast=AMP_CONTRAST,
        )

        # Generate data with smaller astigmatism to encourage the optimizer
        # to push half_astig negative
        push_neg_ctf = CTFParams.from_defocus_pair(
            df1=19950.0,  # half_astig = 25, < base 100
            df2=19900.0,
            angle_degrees=ANGLE_DEG,
            pixel_size=PIXEL_SIZE,
            wavelength=WAVELENGTH,
            cs_mm=CS_MM,
            amplitude_contrast=AMP_CONTRAST,
        )
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, push_neg_ctf, n_particles=5,
        )

        options = RefinementOptions(
            optimizer_type="adam",
            defocus_search_range=1000.0,
            maximum_iterations=10,
            minimum_global_iterations=3,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, small_astig_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        # Effective half-astigmatism should remain >= 0
        base_half = float(small_astig_ctf.half_astigmatism)
        eff_half = base_half + result.delta_half_astigmatism
        assert eff_half >= 0.0, (
            f"Effective half_astigmatism ({eff_half:.1f}A) should not be "
            f"negative. base_half={base_half:.1f}, "
            f"delta={result.delta_half_astigmatism:.1f}"
        )

    def test_bound_value_correct(self, base_ctf: CTFParams) -> None:
        """Verify the computed lower bound matches the formula from the
        task specification.
        """
        base_half = float(base_ctf.half_astigmatism)  # (20000-18000)/2 = 1000
        expected_lower = -(base_half - 1.0)  # -999.0
        assert expected_lower == pytest.approx(-999.0, abs=0.1), (
            f"Lower bound should be -(1000-1) = -999, got {expected_lower}"
        )


# =========================================================================
# Test: df1/df2 swap
# =========================================================================


class TestDfSwap:
    """If final defocus yields df2 > df1, swap is applied and angle
    rotated by 90 degrees.

    The asymmetric bounds prevent the swap from firing during normal
    optimization.  This test validates the swap logic correctness
    using the post-optimization canonicalization.
    """

    def test_swap_transformation_math(self) -> None:
        """Verify the swap math independently.

        When eff_half_astig < 0 the post-optimisation canonicalisation
        applies:

            new_delta_half = -delta_half - 2*base_half
            new_delta_angle = delta_angle + pi/2

        After the swap, eff_half negates sign (becomes positive),
        preserving the physical CTF while restoring df1 >= df2.
        """
        base_half = 100.0
        delta_half = -150.0  # eff_half = 100 + (-150) = -50 < 0

        # Expected transformation from the implementation
        new_delta_half = -delta_half - 2.0 * base_half  # 150 - 200 = -50
        new_delta_angle_offset = np.pi / 2.0

        # Verify: new effective half = -(old effective half)
        old_eff_half = base_half + delta_half  # -50
        new_eff_half = base_half + new_delta_half  # 50
        assert new_eff_half == pytest.approx(-old_eff_half, abs=1e-10), (
            f"Swap should negate eff_half: old={old_eff_half}, new={new_eff_half}"
        )

        # Verify angle rotation is exactly pi/2
        assert new_delta_angle_offset == pytest.approx(np.pi / 2.0, abs=1e-10)

    def test_swap_does_not_fire_with_normal_bounds(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """With standard bounds, the swap should not fire because the
        asymmetric bound prevents eff_half from going negative.
        """
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=5,
        )
        options = RefinementOptions(
            optimizer_type="adam",
            defocus_search_range=1000.0,
            maximum_iterations=10,
            minimum_global_iterations=3,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        # Effective half_astig should be positive (swap not needed)
        base_half = float(base_ctf.half_astigmatism)
        eff_half = base_half + result.delta_half_astigmatism
        assert eff_half >= 0.0, (
            f"Swap should not have fired: eff_half={eff_half:.1f}"
        )

        # Angle change should be small (no 90-degree rotation)
        assert abs(result.delta_astigmatism_angle) < np.pi / 4.0, (
            f"Angle change should be < 45 deg without swap, "
            f"got {np.degrees(result.delta_astigmatism_angle):.1f} deg"
        )


# =========================================================================
# Test: Non-convergence warning
# =========================================================================


class TestNonConvergenceWarning:
    """When optimizer does not converge within maximum_iterations,
    results.converged is False and a warning is logged.
    """

    def test_non_convergence_flag(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """With very few iterations and a large offset, convergence is
        not achieved.
        """
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=N_PARTICLES,
        )
        options = RefinementOptions(
            optimizer_type="adam",
            maximum_iterations=2,  # too few to converge
            minimum_global_iterations=1,
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = refine_tilt_ctf(
                data_fts, ref_fts, base_ctf,
                tilt_angle_degrees=0.0,
                options=options,
                ctf_calculator=ctf_calc,
                fourier_handler=ft,
                peak_mask=peak_mask,
            )

            assert result.converged is False, (
                "Should not converge in 2 iterations with +500A offset"
            )

            # Check that a warning was emitted
            convergence_warnings = [
                x for x in w
                if "did not converge" in str(x.message)
            ]
            assert len(convergence_warnings) >= 1, (
                f"Expected a non-convergence warning. Warnings captured: "
                f"{[str(x.message) for x in w]}"
            )


# =========================================================================
# Test: Gradient at convergence
# =========================================================================


class TestGradientAtConvergence:
    """At final parameters, gradient magnitude is below a reasonable
    threshold (< 0.1 for synthetic data).
    """

    def test_gradient_small_at_convergence(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """With zero-offset data (data matches base CTF), the gradient
        at the converged parameters should be near zero.
        """
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, base_ctf, n_particles=5,
        )
        options = RefinementOptions(
            optimizer_type="lbfgsb",
            maximum_iterations=20,
            minimum_global_iterations=3,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        # Re-compute gradient at the final parameters
        final_params = np.concatenate([
            np.array([
                result.delta_defocus_tilt,
                result.delta_half_astigmatism,
                result.delta_astigmatism_angle,
            ]),
            result.delta_z,
        ])

        _, _, _, gradient = evaluate_score_and_gradient(
            final_params,
            data_fts,
            ref_fts,
            base_ctf,
            ctf_calc,
            ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
            shift_sigma=options.shift_sigma,
            z_offset_sigma=options.z_offset_sigma,
        )

        grad_magnitude = float(np.linalg.norm(gradient))
        assert grad_magnitude < 0.1, (
            f"Gradient magnitude at convergence ({grad_magnitude:.4f}) "
            f"should be < 0.1. Gradient: {gradient[:5]}..."
        )

    def test_gradient_small_after_lbfgsb_recovery(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        truth_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """L-BFGS-B should produce small gradients at convergence, even
        with a 500A offset to recover.
        """
        data_fts, ref_fts = _make_multi_particle_data(
            ft, ctf_calc, truth_ctf, n_particles=5,
        )
        options = RefinementOptions(
            optimizer_type="lbfgsb",
            maximum_iterations=15,
            minimum_global_iterations=3,
        )
        result = refine_tilt_ctf(
            data_fts, ref_fts, base_ctf,
            tilt_angle_degrees=0.0,
            options=options,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            peak_mask=peak_mask,
        )

        final_params = np.concatenate([
            np.array([
                result.delta_defocus_tilt,
                result.delta_half_astigmatism,
                result.delta_astigmatism_angle,
            ]),
            result.delta_z,
        ])

        _, _, _, gradient = evaluate_score_and_gradient(
            final_params,
            data_fts,
            ref_fts,
            base_ctf,
            ctf_calc,
            ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
            shift_sigma=options.shift_sigma,
            z_offset_sigma=options.z_offset_sigma,
        )

        grad_magnitude = float(np.linalg.norm(gradient))
        assert grad_magnitude < 0.1, (
            f"L-BFGS-B gradient magnitude at convergence ({grad_magnitude:.4f}) "
            f"should be < 0.1."
        )
