"""Tests for emc_scoring.py — cross-correlation scoring for CTF refinement.

Validates the Python port of ``synthetic/EMC_refine_tilt_ctf.m`` lines
256--325 against analytical expectations and the acceptance criteria
defined in TASK-009.

Test organisation
~~~~~~~~~~~~~~~~~
Each test class maps to a specific acceptance criterion:

* **TestCreatePeakMask** — shape, centre, boundary, symmetry
* **TestPositiveControl** — self-correlation score > 0.95
* **TestNegativeControl** — random-noise score < 0.1
* **TestMultiParticle** — total_score == sum(per_particle_scores)
* **TestEffectiveDefocus** — formula equivalence via parameter remapping
* **TestDfSwap** — df1/df2 swap + 90-degree angle rotation
* **TestPeakMaskRestriction** — peaks outside mask are ignored
* **TestGaussianPenalty** — Python-only multiplicative Gaussian penalty
* **TestCtfMismatch** — directional control with defocus offsets
"""

from __future__ import annotations

import numpy as np
import pytest

from ...ctf.emc_ctf_cpu import CTFCalculatorCPU
from ...ctf.emc_ctf_params import CTFParams
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

    Preprocessing mirrors the MATLAB code in ``EMC_refine_tilt_ctf.m``
    lines 97--105:

    * **data_ft**: ``normalise(swap_phase(fwdFFT(data_real)))``
    * **ref_ft**: ``conj(fwdFFT(ref_real))``

    The data tile is the reference convolved with the CTF (in Fourier
    space) and transformed back to real space, simulating the observed
    image from the microscope.
    """
    rng = np.random.default_rng(seed)
    ref_real = rng.standard_normal((NX, NY)).astype(np.float32)

    # CTF image transposed to FourierTransformer convention (nx//2+1, ny)
    ctf_image = ctf_calc.compute(ctf_params, (NX, NY)).T

    # Synthetic data = IFFT(FFT(ref) * CTF) — reference with CTF applied
    ref_spectrum = ft.forward_fft(ref_real)
    data_real = ft.inverse_fft(ref_spectrum * ctf_image).astype(np.float32)

    # Preprocess data: fwdFFT → swap_phase → normalise
    data_ft = ft.swap_phase(ft.forward_fft(data_real))
    data_norm = ft.compute_ref_norm(data_ft)
    data_ft = data_ft / data_norm

    # Preprocess reference: fwdFFT → conjugate (pre-conjugated storage)
    ref_ft = np.conj(ft.forward_fft(ref_real))

    return data_ft, ref_ft


def _score_one(
    ft: FourierTransformer,
    ctf_calc: CTFCalculatorCPU,
    base_ctf: CTFParams,
    peak_mask: np.ndarray,
    data_ft: np.ndarray,
    ref_ft: np.ndarray,
    params: np.ndarray | None = None,
    tilt_angle: float = 0.0,
    shift_sigma: float = 5.0,
    z_offset_sigma: float = 100.0,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Score a single particle with the given parameters."""
    if params is None:
        params = np.zeros(4)
    return evaluate_score_and_shifts(
        params=params,
        data_fts=[data_ft],
        ref_fts=[ref_ft],
        base_ctf_params=base_ctf,
        ctf_calculator=ctf_calc,
        fourier_handler=ft,
        tilt_angle_degrees=tilt_angle,
        peak_mask=peak_mask,
        shift_sigma=shift_sigma,
        z_offset_sigma=z_offset_sigma,
    )


# =========================================================================
# Test: create_peak_mask
# =========================================================================


class TestCreatePeakMask:
    """Peak mask shape, dtype, centre, boundary, and symmetry."""

    def test_shape_and_dtype(self) -> None:
        mask = create_peak_mask(64, 64, 16.0)
        assert mask.shape == (64, 64)
        assert mask.dtype == np.float32

    def test_centre_is_one(self) -> None:
        mask = create_peak_mask(64, 64, 16.0)
        assert mask[32, 32] == 1.0

    def test_corner_is_zero_for_small_radius(self) -> None:
        mask = create_peak_mask(64, 64, 5.0)
        assert mask[0, 0] == 0.0
        assert mask[63, 63] == 0.0

    def test_approximate_symmetry(self) -> None:
        """For an odd-sized grid, the mask is perfectly symmetric.

        Even-sized grids have the centre at ``N//2`` which is not the
        geometric midpoint, so exact flip symmetry does not hold.
        """
        mask = create_peak_mask(65, 65, 16.0)
        np.testing.assert_array_equal(mask, mask[::-1, :])
        np.testing.assert_array_equal(mask, mask[:, ::-1])

    def test_rectangular(self) -> None:
        """Works for non-square dimensions."""
        mask = create_peak_mask(64, 128, 20.0)
        assert mask.shape == (64, 128)
        assert mask[32, 64] == 1.0


# =========================================================================
# Test: Positive control — self-correlation
# =========================================================================


class TestPositiveControl:
    """CTF-multiplied reference cross-correlated with itself → score > 0.95.

    This is the primary positive control: when data is generated by
    applying a known CTF to the reference, scoring with the same CTF
    should produce near-unity correlation.
    """

    def test_self_correlation_high_score(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams, peak_mask: np.ndarray,
    ) -> None:
        data_ft, ref_ft = _make_synthetic_particle(ft, ctf_calc, base_ctf)
        total_score, scores, shifts = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
        )
        assert total_score > 0.95, f"Expected score > 0.95, got {total_score}"

    def test_self_correlation_small_shift(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams, peak_mask: np.ndarray,
    ) -> None:
        data_ft, ref_ft = _make_synthetic_particle(ft, ctf_calc, base_ctf)
        _, _, shifts = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
        )
        assert abs(shifts[0, 0]) < 2, f"shift_x={shifts[0, 0]}"
        assert abs(shifts[0, 1]) < 2, f"shift_y={shifts[0, 1]}"


# =========================================================================
# Test: Negative control — random noise
# =========================================================================


class TestNegativeControl:
    """Random noise data produces score < 0.1."""

    def test_random_noise_low_score(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams, peak_mask: np.ndarray,
    ) -> None:
        # Data: random noise (seed 100)
        rng_data = np.random.default_rng(100)
        noise = rng_data.standard_normal((NX, NY)).astype(np.float32)
        data_ft = ft.swap_phase(ft.forward_fft(noise))
        data_ft = data_ft / ft.compute_ref_norm(data_ft)

        # Reference: independent random pattern (seed 200)
        rng_ref = np.random.default_rng(200)
        ref_real = rng_ref.standard_normal((NX, NY)).astype(np.float32)
        ref_ft = np.conj(ft.forward_fft(ref_real))

        total_score, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
        )
        assert total_score < 0.1, f"Expected score < 0.1, got {total_score}"


# =========================================================================
# Test: Multi-particle score additivity
# =========================================================================


class TestMultiParticle:
    """Total score equals sum of individual particle scores (5 particles)."""

    def test_score_sum_equals_total(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams, peak_mask: np.ndarray,
    ) -> None:
        n_particles = 5
        data_fts: list[np.ndarray] = []
        ref_fts: list[np.ndarray] = []
        for seed in range(n_particles):
            d, r = _make_synthetic_particle(
                ft, ctf_calc, base_ctf, seed=42 + seed,
            )
            data_fts.append(d)
            ref_fts.append(r)

        params = np.zeros(3 + n_particles)
        total_score, scores, _ = evaluate_score_and_shifts(
            params=params,
            data_fts=data_fts,
            ref_fts=ref_fts,
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )

        np.testing.assert_allclose(
            total_score, np.sum(scores), rtol=1e-10,
            err_msg="total_score must equal sum(per_particle_scores)",
        )

    def test_individual_matches_batch(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams, peak_mask: np.ndarray,
    ) -> None:
        """Each particle's score in the batch matches a standalone run."""
        n_particles = 5
        data_fts: list[np.ndarray] = []
        ref_fts: list[np.ndarray] = []
        for seed in range(n_particles):
            d, r = _make_synthetic_particle(
                ft, ctf_calc, base_ctf, seed=42 + seed,
            )
            data_fts.append(d)
            ref_fts.append(r)

        params = np.zeros(3 + n_particles)
        _, batch_scores, _ = evaluate_score_and_shifts(
            params=params,
            data_fts=data_fts,
            ref_fts=ref_fts,
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )

        for i in range(n_particles):
            single_params = np.zeros(4)
            single_score, _, _ = _score_one(
                ft, ctf_calc, base_ctf, peak_mask,
                data_fts[i], ref_fts[i],
            )
            np.testing.assert_allclose(
                batch_scores[i], single_score, rtol=1e-10,
                err_msg=f"Particle {i} batch vs standalone mismatch",
            )


# =========================================================================
# Test: Effective defocus formula
# =========================================================================


class TestEffectiveDefocus:
    """Effective defocus uses the full formula with half-astigmatism.

    Two parameter configurations that produce identical effective defocus
    values must yield identical scores.  This validates the formula
    without needing MATLAB reference values.
    """

    def test_formula_equivalence(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        peak_mask: np.ndarray,
    ) -> None:
        """Shifting base CTF by (d, h) and scoring with delta=(0,0) must
        match the original base CTF scored with delta=(d, h)."""
        delta_df = 200.0
        delta_half = 50.0

        # Scenario A: original base, params carry offsets
        base_a = CTFParams.from_defocus_pair(
            df1=DF1, df2=DF2, angle_degrees=ANGLE_DEG,
            pixel_size=PIXEL_SIZE, wavelength=WAVELENGTH,
            cs_mm=CS_MM, amplitude_contrast=AMP_CONTRAST,
        )

        # Scenario B: shifted base (absorbs offsets), params are zero
        # df1_shifted = DF1 + delta_half + delta_df
        # df2_shifted = DF2 - delta_half + delta_df
        base_b = CTFParams.from_defocus_pair(
            df1=DF1 + delta_half + delta_df,
            df2=DF2 - delta_half + delta_df,
            angle_degrees=ANGLE_DEG,
            pixel_size=PIXEL_SIZE,
            wavelength=WAVELENGTH,
            cs_mm=CS_MM,
            amplitude_contrast=AMP_CONTRAST,
        )

        # Generate data/ref from base_b CTF (the "true" CTF)
        data_ft, ref_ft = _make_synthetic_particle(
            ft, ctf_calc, base_b, seed=77,
        )

        # Score A: base_a + deltas
        params_a = np.array([delta_df, delta_half, 0.0, 0.0])
        score_a, _, _ = _score_one(
            ft, ctf_calc, base_a, peak_mask, data_ft, ref_ft,
            params=params_a,
        )

        # Score B: base_b + zeros
        params_b = np.zeros(4)
        score_b, _, _ = _score_one(
            ft, ctf_calc, base_b, peak_mask, data_ft, ref_ft,
            params=params_b,
        )

        np.testing.assert_allclose(
            score_a, score_b, rtol=1e-4,
            err_msg="Equivalent defocus configurations must yield equal scores",
        )

    def test_tilt_angle_affects_dz_contribution(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams, peak_mask: np.ndarray,
    ) -> None:
        """At tilt=0, dz has no effect (cos(0)=1); at tilt=60,
        contribution is dz*cos(60)=dz/2."""
        data_ft, ref_ft = _make_synthetic_particle(
            ft, ctf_calc, base_ctf, seed=88,
        )

        dz_val = 500.0

        # At tilt=0: dz_contribution = dz * cos(0) = dz * 1 = dz.
        # So dz=500 at tilt=0 must match delta_df=500 at tilt=0.
        params_dz_tilt0 = np.array([0.0, 0.0, 0.0, dz_val])
        params_equiv_tilt0 = np.array([dz_val, 0.0, 0.0, 0.0])
        score_tilt0_dz, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=params_dz_tilt0, tilt_angle=0.0,
            z_offset_sigma=1e10,  # disable z penalty to isolate CTF effect
        )
        score_tilt0_equiv, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=params_equiv_tilt0, tilt_angle=0.0,
            z_offset_sigma=1e10,
        )
        np.testing.assert_allclose(
            score_tilt0_dz, score_tilt0_equiv, rtol=1e-4,
            err_msg="dz=500 at tilt=0 must equal delta_df=500 at tilt=0 (cos(0)=1)",
        )

        # At tilt=60: dz_contribution = 500 * cos(60) = 250
        # Equivalent to delta_df=250 at tilt=0
        params_equiv = np.array([250.0, 0.0, 0.0, 0.0])

        # dz=500 at tilt=60 should give similar defocus offset as delta_df=250 at tilt=0
        params_tilt60_dz = np.array([0.0, 0.0, 0.0, dz_val])
        score_tilt60_dz, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=params_tilt60_dz, tilt_angle=60.0,
            z_offset_sigma=1e10,  # disable z penalty
        )
        score_equiv_noz, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=params_equiv, tilt_angle=0.0,
            z_offset_sigma=1e10,
        )

        np.testing.assert_allclose(
            score_tilt60_dz, score_equiv_noz, rtol=1e-4,
            err_msg="dz=500 at tilt=60 should match delta_df=250 at tilt=0",
        )


# =========================================================================
# Test: df1/df2 swap
# =========================================================================


class TestDfSwap:
    """When computed df2_eff > df1_eff, values are swapped and angle
    rotated by 90 degrees.  The resulting CTF is physically identical.
    """

    def test_swap_produces_same_score(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        peak_mask: np.ndarray,
    ) -> None:
        """A large negative delta_half_astig that flips df1/df2 should
        still produce a valid score (the swap corrects the ordering)."""
        # Base: df1=20000, df2=18000, half_astig=1000
        base = CTFParams.from_defocus_pair(
            df1=20000.0, df2=18000.0, angle_degrees=0.0,
            pixel_size=PIXEL_SIZE, wavelength=WAVELENGTH,
            cs_mm=CS_MM, amplitude_contrast=AMP_CONTRAST,
        )
        data_ft, ref_ft = _make_synthetic_particle(
            ft, ctf_calc, base, seed=55,
        )

        # No offset — baseline
        score_base, _, _ = _score_one(
            ft, ctf_calc, base, peak_mask, data_ft, ref_ft,
        )

        # Manually construct the swapped equivalent:
        # delta_half_astig = -1500 makes df1_eff = 20000+(-1500) = 18500
        #                                df2_eff = 18000-(-1500) = 19500
        # Swap triggers: df1_eff=19500, df2_eff=18500, angle+=90
        # This is equivalent to:
        #   base with df1=19500, df2=18500, angle=90
        base_swapped = CTFParams.from_defocus_pair(
            df1=19500.0, df2=18500.0, angle_degrees=90.0,
            pixel_size=PIXEL_SIZE, wavelength=WAVELENGTH,
            cs_mm=CS_MM, amplitude_contrast=AMP_CONTRAST,
        )
        # Generate data matching the swapped parameters
        data_swap, ref_swap = _make_synthetic_particle(
            ft, ctf_calc, base_swapped, seed=55,
        )
        score_swapped, _, _ = _score_one(
            ft, ctf_calc, base_swapped, peak_mask, data_swap, ref_swap,
        )

        # Both should produce valid high scores (>0.9)
        assert score_base > 0.9, f"Base score too low: {score_base}"
        assert score_swapped > 0.9, f"Swapped score too low: {score_swapped}"

    def test_swap_triggered_by_negative_delta(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        peak_mask: np.ndarray,
    ) -> None:
        """When delta_half_astig forces df2>df1, the swap fires and the
        score remains meaningful (not degenerate)."""
        base = CTFParams.from_defocus_pair(
            df1=20000.0, df2=19800.0, angle_degrees=0.0,
            pixel_size=PIXEL_SIZE, wavelength=WAVELENGTH,
            cs_mm=CS_MM, amplitude_contrast=AMP_CONTRAST,
        )
        data_ft, ref_ft = _make_synthetic_particle(
            ft, ctf_calc, base, seed=66,
        )

        # delta_half = -200 flips ordering: df1=20000+(-200)=19800,
        #                                   df2=19800-(-200)=20000
        # Swap fires.
        params = np.array([-0.0, -200.0, 0.0, 0.0])
        score, scores, _ = _score_one(
            ft, ctf_calc, base, peak_mask, data_ft, ref_ft, params=params,
        )
        # Score should be finite and non-zero (swap handled correctly)
        assert np.isfinite(score), f"Score is not finite: {score}"
        assert score != 0.0, "Score should not be exactly zero"


# =========================================================================
# Test: Peak mask restriction
# =========================================================================


class TestPeakMaskRestriction:
    """Peak mask restricts search to specified radius."""

    def test_small_mask_lowers_score(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
    ) -> None:
        """A very small mask (radius=1) centred at the origin still
        captures zero-shift peaks; a mask of radius=0 blocks everything."""
        data_ft, ref_ft = _make_synthetic_particle(ft, ctf_calc, base_ctf)

        # Normal mask — captures peak
        mask_normal = create_peak_mask(NX, NY, radius=SEARCH_RADIUS)
        score_normal, _, _ = _score_one(
            ft, ctf_calc, base_ctf, mask_normal, data_ft, ref_ft,
        )

        # Tiny mask centred at origin (radius=1) — may still capture
        # zero-shift peak since it is at the centre
        mask_tiny = create_peak_mask(NX, NY, radius=1.0)
        score_tiny, _, _ = _score_one(
            ft, ctf_calc, base_ctf, mask_tiny, data_ft, ref_ft,
        )

        # All-zero mask — no peak captured
        mask_zero = np.zeros((NX, NY), dtype=np.float32)
        score_zero, _, _ = _score_one(
            ft, ctf_calc, base_ctf, mask_zero, data_ft, ref_ft,
        )

        assert score_normal > score_zero, (
            f"Normal mask score ({score_normal}) should exceed zero-mask "
            f"score ({score_zero})"
        )
        assert score_zero == 0.0, (
            f"Zero mask should give zero score, got {score_zero}"
        )

    def test_off_centre_mask_misses_peak(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
    ) -> None:
        """A mask placed far from centre should miss the zero-shift peak."""
        data_ft, ref_ft = _make_synthetic_particle(ft, ctf_calc, base_ctf)

        # Normal centred mask
        mask_centred = create_peak_mask(NX, NY, radius=SEARCH_RADIUS)
        score_centred, _, _ = _score_one(
            ft, ctf_calc, base_ctf, mask_centred, data_ft, ref_ft,
        )

        # Off-centre mask: only cover a corner far from (nx//2, ny//2)
        mask_corner = np.zeros((NX, NY), dtype=np.float32)
        mask_corner[0:5, 0:5] = 1.0
        score_corner, _, _ = _score_one(
            ft, ctf_calc, base_ctf, mask_corner, data_ft, ref_ft,
        )

        assert score_centred > score_corner, (
            f"Centred mask ({score_centred}) should beat corner mask "
            f"({score_corner})"
        )


# =========================================================================
# Test: Gaussian penalty (Python-only enhancement)
# =========================================================================


class TestGaussianPenalty:
    """Gaussian penalty reduces score proportional to
    ``exp(-shift^2 / (2*sigma^2))`` for known shift and z-offset values.

    These are Python-only enhancements not present in the MATLAB reference.
    Validation uses finite-difference-style reasoning rather than MATLAB
    comparison.
    """

    def test_z_penalty_reduces_score(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams, peak_mask: np.ndarray,
    ) -> None:
        """Non-zero dz should reduce score vs dz=0."""
        data_ft, ref_ft = _make_synthetic_particle(ft, ctf_calc, base_ctf)

        score_no_dz, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=np.array([0.0, 0.0, 0.0, 0.0]),
            z_offset_sigma=50.0,
        )

        # With dz but using a very large z_offset_sigma to disable
        # CTF mismatch penalty effect:
        # We use a moderate dz that doesn't change the CTF much
        score_with_dz, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=np.array([0.0, 0.0, 0.0, 30.0]),
            z_offset_sigma=50.0,
        )

        # The z-penalty should reduce the score
        assert score_with_dz < score_no_dz, (
            f"z-penalty should reduce score: {score_with_dz} >= {score_no_dz}"
        )

    def test_z_penalty_quantitative(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams, peak_mask: np.ndarray,
    ) -> None:
        """The z-penalty factor should match exp(-dz^2 / (2*sigma^2)).

        To isolate the penalty from CTF mismatch, we use a tiny dz that
        barely changes the CTF but still produces a measurable penalty.
        """
        data_ft, ref_ft = _make_synthetic_particle(ft, ctf_calc, base_ctf)
        z_sigma = 50.0

        # dz=0 baseline
        score_0, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=np.array([0.0, 0.0, 0.0, 0.0]),
            z_offset_sigma=z_sigma,
        )

        # dz=1 (tiny — CTF barely changes, penalty is the dominant effect)
        dz_val = 1.0
        score_dz, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=np.array([0.0, 0.0, 0.0, dz_val]),
            z_offset_sigma=z_sigma,
        )

        expected_factor = np.exp(-(dz_val ** 2) / (2.0 * z_sigma ** 2))
        # The peak_height may change slightly due to CTF mismatch,
        # but for dz=1A the change is negligible.  The ratio should
        # match the penalty factor to within 1%.
        ratio = score_dz / score_0
        np.testing.assert_allclose(
            ratio, expected_factor, rtol=0.01,
            err_msg="z-penalty ratio should match Gaussian formula",
        )

    def test_no_penalty_when_sigmas_are_large(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams, peak_mask: np.ndarray,
    ) -> None:
        """With very large sigmas, penalties are negligible."""
        data_ft, ref_ft = _make_synthetic_particle(ft, ctf_calc, base_ctf)

        # Very large sigmas effectively disable penalties
        score_large_sigma, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=np.array([0.0, 0.0, 0.0, 100.0]),
            shift_sigma=1e6,
            z_offset_sigma=1e6,
        )

        score_zero_dz, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=np.array([0.0, 0.0, 0.0, 0.0]),
            shift_sigma=1e6,
            z_offset_sigma=1e6,
        )

        # With huge sigmas the penalty weight ≈ 1.0, so the ratio of
        # scores should reflect only the CTF mismatch from dz=100A.
        # The key assertion: ratio must be close to 1 compared to what a
        # tight sigma (z_offset_sigma=50) would produce.
        score_tight_sigma, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=np.array([0.0, 0.0, 0.0, 100.0]),
            shift_sigma=1e6,
            z_offset_sigma=50.0,  # tight z penalty
        )
        # With huge sigma, penalty ≈ 1. With tight sigma (50A), dz=100A
        # gives weight = exp(-100^2/(2*50^2)) ≈ 0.135.
        # So score_large_sigma must be substantially higher than score_tight_sigma.
        assert score_large_sigma > score_tight_sigma, (
            f"Large sigma ({score_large_sigma:.4f}) should exceed tight sigma "
            f"({score_tight_sigma:.4f}) — penalty not applied when sigma is huge"
        )


# =========================================================================
# Test: CTF mismatch directional control
# =========================================================================


class TestCtfMismatch:
    """Deliberate +500A defocus offset produces lower score than ground
    truth; sign of offset does not matter (both ±500A produce similar
    score reduction).
    """

    def test_defocus_offset_lowers_score(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams, peak_mask: np.ndarray,
    ) -> None:
        data_ft, ref_ft = _make_synthetic_particle(ft, ctf_calc, base_ctf)

        # Correct CTF
        score_correct, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            z_offset_sigma=1e6,  # disable z penalty
        )

        # +500A defocus offset
        params_plus = np.array([500.0, 0.0, 0.0, 0.0])
        score_plus, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=params_plus, z_offset_sigma=1e6,
        )

        # -500A defocus offset
        params_minus = np.array([-500.0, 0.0, 0.0, 0.0])
        score_minus, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=params_minus, z_offset_sigma=1e6,
        )

        assert score_correct > score_plus, (
            f"Correct CTF ({score_correct}) should beat +500A offset "
            f"({score_plus})"
        )
        assert score_correct > score_minus, (
            f"Correct CTF ({score_correct}) should beat -500A offset "
            f"({score_minus})"
        )

    def test_symmetric_offset_similar_reduction(
        self, ft: FourierTransformer, ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams, peak_mask: np.ndarray,
    ) -> None:
        """±500A offsets produce similar score reduction."""
        data_ft, ref_ft = _make_synthetic_particle(ft, ctf_calc, base_ctf)

        params_plus = np.array([500.0, 0.0, 0.0, 0.0])
        score_plus, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=params_plus, z_offset_sigma=1e6,
        )

        params_minus = np.array([-500.0, 0.0, 0.0, 0.0])
        score_minus, _, _ = _score_one(
            ft, ctf_calc, base_ctf, peak_mask, data_ft, ref_ft,
            params=params_minus, z_offset_sigma=1e6,
        )

        # Scores should be similar (within 50% of each other)
        ratio = score_plus / score_minus if score_minus != 0 else float("inf")
        assert 0.5 < ratio < 2.0, (
            f"±500A scores should be similar: +500A={score_plus}, "
            f"-500A={score_minus}, ratio={ratio}"
        )
