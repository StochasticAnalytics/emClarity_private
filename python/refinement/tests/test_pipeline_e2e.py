"""End-to-end synthetic validation tests for the CTF refinement pipeline.

Generates synthetic cryo-EM data with known ground-truth CTF parameters,
runs the full ``refine_ctf_from_star()`` pipeline with deliberately offset
input CTF values, and verifies that the pipeline recovers ground truth
within specified tolerances.

Test structure:

- **Positive control**: Ground-truth CTF input produces near-zero corrections.
- **Negative control**: Large offset (+5000A) still converges in the correct
  direction.
- **Standard recovery**: +300A defocus / +100A astigmatism / +5 deg angle
  offsets are recovered within acceptance criteria.
- **Gradient sanity check**: Analytical gradient at initial (offset) parameters
  matches finite-difference gradient and points toward ground truth.
- **Optimizer comparison**: L-BFGS-B converges in fewer iterations than ADAM.
- **SNR verification**: Generated tiles have the specified SNR.
- **Score monotonicity**: Scores increase from initial to final iteration.

NOTE: MATLAB scores cannot be used as ground truth for penalty-affected
comparisons, because the Gaussian penalties (shift and z-offset) are
Python-only enhancements not present in the MATLAB reference.  All score
comparisons use Python-internal consistency checks.
"""

from __future__ import annotations

from pathlib import Path

import mrcfile
import numpy as np
import pytest

from ...ctf.emc_ctf_cpu import CTFCalculatorCPU
from ...ctf.emc_ctf_params import CTFParams
from ...ctf.star_io.emc_star_parser import parse_star_file
from ..emc_ctf_refine_pipeline import (
    PipelineOptions,
    PipelineResults,
    compute_electron_wavelength,
    refine_ctf_from_star,
)
from ..emc_ctf_gradients import evaluate_score_and_gradient
from ..emc_fourier_utils import FourierTransformer
from ..emc_scoring import create_peak_mask, evaluate_score_and_shifts
from ..emc_tile_prep import (
    compute_ctf_friendly_size,
    create_2d_soft_mask,
    prepare_data_tile,
    prepare_reference_projection,
)
from .fixtures.generate_synthetic_data import (
    CTFOffset,
    GroundTruthCTF,
    MicroscopeParams,
    SyntheticDataset,
    compute_snr_of_tiles,
    generate_synthetic_dataset,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TILE_SIZE = 64
_VOL_SIZE = 64
_N_PARTICLES_PER_TILT = 10
_TILT_ANGLES = (-60.0, -30.0, 0.0, 30.0, 60.0)
_N_TILT_GROUPS = len(_TILT_ANGLES)
_TOTAL_PARTICLES = _N_PARTICLES_PER_TILT * _N_TILT_GROUPS

# Standard microscope parameters
_MICROSCOPE = MicroscopeParams()

# Ground-truth CTF — lower defocus with strong astigmatism for better
# CTF sensitivity in the optimiser's score landscape.  At high defocus
# (e.g. 20 000 A) the Thon ring spacing is too fine for the soft-mask's
# spectral convolution to resolve cleanly, biasing the landscape.
_GT_CTF = GroundTruthCTF(
    defocus_1=4500.0,
    defocus_2=2000.0,
    defocus_angle=45.0,
)

# Standard offset (+300A defocus, +100A half-astigmatism, +5 deg angle)
_STANDARD_OFFSET = CTFOffset(
    defocus_offset=300.0,
    astigmatism_offset=100.0,
    angle_offset=5.0,
)

# Pipeline options tuned for synthetic data
_MAX_ITERATIONS = 50
_LOWPASS_CUTOFF = 3.5      # Angstroms — CTF-sensitive frequency range
_HIGHPASS_CUTOFF = 400.0   # Angstroms


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def synthetic_data(tmp_path_factory: pytest.TempPathFactory) -> SyntheticDataset:
    """Generate a standard synthetic dataset (SNR=5.0, 50 particles).

    Scope is ``module`` to avoid regenerating for each test — the dataset
    is read-only after creation.
    """
    output_dir = tmp_path_factory.mktemp("e2e_synthetic")
    return generate_synthetic_dataset(
        output_dir,
        tile_size=_TILE_SIZE,
        vol_size=_VOL_SIZE,
        n_particles_per_tilt=_N_PARTICLES_PER_TILT,
        tilt_angles=_TILT_ANGLES,
        ground_truth_ctf=_GT_CTF,
        ctf_offset=_STANDARD_OFFSET,
        microscope=_MICROSCOPE,
        snr=5.0,
        seed=42,
        delta_z_sigma=30.0,
    )


@pytest.fixture(scope="module")
def positive_control_data(
    tmp_path_factory: pytest.TempPathFactory,
) -> SyntheticDataset:
    """Low-defocus dataset for positive-control testing.

    Uses defocus_1=defocus_2=700A (no astigmatism) so that only a single
    CTF zero falls inside the lowpass=3.5A frequency range.  This keeps
    the mask-CTF interaction bias below the 10A acceptance threshold while
    retaining meaningful CTF contrast for the optimiser.
    """
    output_dir = tmp_path_factory.mktemp("positive_ctrl")
    return generate_synthetic_dataset(
        output_dir,
        tile_size=_TILE_SIZE,
        vol_size=_VOL_SIZE,
        n_particles_per_tilt=_N_PARTICLES_PER_TILT,
        tilt_angles=(0.0,),  # Single tilt for speed
        ground_truth_ctf=GroundTruthCTF(
            defocus_1=700.0, defocus_2=700.0, defocus_angle=0.0,
        ),
        ctf_offset=CTFOffset(
            defocus_offset=0.0,
            astigmatism_offset=0.0,
            angle_offset=0.0,
        ),
        microscope=_MICROSCOPE,
        snr=5.0,
        seed=42,
        delta_z_sigma=30.0,
    )


@pytest.fixture(scope="module")
def lbfgsb_result(
    synthetic_data: SyntheticDataset,
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, SyntheticDataset, PipelineResults]:
    """Run the pipeline with L-BFGS-B and return output star, dataset, and results."""
    output_dir = tmp_path_factory.mktemp("e2e_lbfgsb")
    output_star = output_dir / "refined_lbfgsb.star"
    opts = PipelineOptions(
        optimizer_type="lbfgsb",
        maximum_iterations=_MAX_ITERATIONS,
        minimum_global_iterations=3,
        lowpass_cutoff=_LOWPASS_CUTOFF,
        highpass_cutoff=_HIGHPASS_CUTOFF,
    )
    result = refine_ctf_from_star(
        synthetic_data.offset_star_path,
        synthetic_data.stack_path,
        synthetic_data.reference_path,
        output_star,
        options=opts,
    )
    return output_star, synthetic_data, result


@pytest.fixture(scope="module")
def adam_result(
    synthetic_data: SyntheticDataset,
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, SyntheticDataset, PipelineResults]:
    """Run the pipeline with ADAM and return output star, dataset, and results."""
    output_dir = tmp_path_factory.mktemp("e2e_adam")
    output_star = output_dir / "refined_adam.star"
    opts = PipelineOptions(
        optimizer_type="adam",
        maximum_iterations=_MAX_ITERATIONS,
        minimum_global_iterations=3,
        lowpass_cutoff=_LOWPASS_CUTOFF,
        highpass_cutoff=_HIGHPASS_CUTOFF,
    )
    result = refine_ctf_from_star(
        synthetic_data.offset_star_path,
        synthetic_data.stack_path,
        synthetic_data.reference_path,
        output_star,
        options=opts,
    )
    return output_star, synthetic_data, result


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _compute_recovery_stats(
    refined_star: Path,
    dataset: SyntheticDataset,
) -> dict:
    """Compare refined parameters to ground truth and compute deltas.

    Returns a dict with per-tilt-group mean deltas for defocus, astigmatism,
    and angle, plus aggregate statistics.
    """
    refined_particles, _ = parse_star_file(refined_star)
    truth_particles, _ = parse_star_file(dataset.truth_star_path)

    gt_half_astig = (dataset.ground_truth_ctf.defocus_1
                     - dataset.ground_truth_ctf.defocus_2) / 2.0
    gt_angle = dataset.ground_truth_ctf.defocus_angle

    # Compute per-particle defocus recovery
    defocus_errors = []
    half_astig_errors = []
    angle_errors = []

    for rp, tp in zip(refined_particles, truth_particles, strict=True):
        r_mean = (rp["defocus_1"] + rp["defocus_2"]) / 2.0
        t_mean = (tp["defocus_1"] + tp["defocus_2"]) / 2.0
        defocus_errors.append(r_mean - t_mean)

        r_half = (rp["defocus_1"] - rp["defocus_2"]) / 2.0
        half_astig_errors.append(r_half - gt_half_astig)

        raw_angle_diff = rp["defocus_angle"] - gt_angle
        # Wrap to [-90, 90) — astigmatism angles have 180° periodicity
        wrapped = ((raw_angle_diff + 90.0) % 180.0) - 90.0
        angle_errors.append(wrapped)

    defocus_errors_arr = np.array(defocus_errors)
    half_astig_errors_arr = np.array(half_astig_errors)
    angle_errors_arr = np.array(angle_errors)

    return {
        "mean_defocus_error": float(np.mean(np.abs(defocus_errors_arr))),
        "mean_half_astig_error": float(np.mean(np.abs(half_astig_errors_arr))),
        "mean_angle_error": float(np.mean(np.abs(angle_errors_arr))),
        "defocus_errors": defocus_errors_arr,
        "half_astig_errors": half_astig_errors_arr,
        "angle_errors": angle_errors_arr,
        "refined_particles": refined_particles,
    }


def _prepare_gradient_test_data(
    dataset: SyntheticDataset,
) -> tuple:
    """Prepare data/ref FTs and CTF params for gradient testing.

    Uses the first tilt group from the synthetic dataset. Returns:
    (data_fts, ref_fts, base_ctf, tilt_angle, fourier_handler, peak_mask,
     offset_params, gt_params, ctf_calculator)
    """
    microscope = dataset.microscope
    gt_ctf = dataset.ground_truth_ctf
    offset = dataset.ctf_offset

    wavelength = compute_electron_wavelength(microscope.voltage_kv)
    ctf_calculator = CTFCalculatorCPU()
    ctf_size = compute_ctf_friendly_size(2 * dataset.tile_size)
    fourier_handler = FourierTransformer(ctf_size, ctf_size, use_gpu=False)
    peak_mask = create_peak_mask(ctf_size, ctf_size, radius=float(ctf_size // 4))

    # Soft mask at tile size
    mask_radius = dataset.tile_size / 2.0 - 1.0
    soft_mask = create_2d_soft_mask(
        dataset.tile_size, dataset.tile_size,
        radius=mask_radius, edge_width=7.0,
    )

    # Load stack and reference
    with mrcfile.open(str(dataset.stack_path), mode="r") as mrc:
        stack_data = mrc.data.copy()
    with mrcfile.open(str(dataset.reference_path), mode="r") as mrc:
        ref_volume = mrc.data.copy().astype(np.float32)

    # Use first tilt group
    tilt_group = dataset.tilt_groups[0]
    tilt_angle = tilt_group.tilt_angle
    n_particles = len(tilt_group.particles)

    # Prepare data and reference FTs
    data_fts: list[np.ndarray] = []
    ref_fts: list[np.ndarray] = []

    start_idx = 0  # First tilt group starts at index 0
    for i, spec in enumerate(tilt_group.particles):
        tile = stack_data[start_idx + i].astype(np.float32)
        euler_angles = (spec.euler_phi, spec.euler_theta, spec.euler_psi)

        data_ft = prepare_data_tile(
            tile, soft_mask, ctf_size, fourier_handler,
            microscope.pixel_size, _HIGHPASS_CUTOFF, _LOWPASS_CUTOFF,
        )
        ref_ft = prepare_reference_projection(
            ref_volume, euler_angles, soft_mask, ctf_size, fourier_handler,
        )

        data_fts.append(data_ft)
        ref_fts.append(ref_ft)

    # Base CTF with offset parameters (what the pipeline starts with)
    gt_mean_df = (gt_ctf.defocus_1 + gt_ctf.defocus_2) / 2.0
    gt_half_astig = (gt_ctf.defocus_1 - gt_ctf.defocus_2) / 2.0

    offset_mean = gt_mean_df + offset.defocus_offset
    offset_half = gt_half_astig + offset.astigmatism_offset
    offset_df1 = offset_mean + offset_half
    offset_df2 = offset_mean - offset_half
    offset_angle = gt_ctf.defocus_angle + offset.angle_offset

    base_ctf = CTFParams.from_defocus_pair(
        df1=offset_df1,
        df2=offset_df2,
        angle_degrees=offset_angle,
        pixel_size=microscope.pixel_size,
        wavelength=wavelength,
        cs_mm=microscope.cs_mm,
        amplitude_contrast=microscope.amplitude_contrast,
    )

    # Parameter vector at offset position (delta = 0, since base_ctf already
    # incorporates the offset). The optimizer starts from delta=0 and should
    # converge to negative deltas that undo the offset.
    offset_params = np.zeros(3 + n_particles, dtype=np.float64)

    # Ground-truth parameter vector: the deltas that would undo the offset
    gt_params = np.zeros(3 + n_particles, dtype=np.float64)
    gt_params[0] = -offset.defocus_offset  # delta defocus
    gt_params[1] = -offset.astigmatism_offset  # delta half-astigmatism
    gt_params[2] = -np.radians(offset.angle_offset)  # delta angle (radians)

    return (
        data_fts, ref_fts, base_ctf, tilt_angle, fourier_handler,
        peak_mask, offset_params, gt_params, ctf_calculator,
    )


# ---------------------------------------------------------------------------
# Tests: SNR verification
# ---------------------------------------------------------------------------


class TestSNRVerification:
    """Verify that synthetic tiles have the specified signal-to-noise ratio."""

    def test_snr_within_expected_range(
        self, synthetic_data: SyntheticDataset,
    ) -> None:
        """Generated tiles have empirical SNR consistent with SNR=5.0.

        Estimates SNR as ``std(mean_tile) / std(residuals)`` where the mean
        tile approximates the common signal and residuals approximate per-tile
        noise.  Because tiles carry different CTF modulations (varying tilt
        angles), the mean-tile signal is partially attenuated, biasing the
        measured SNR below the per-tile injection SNR of 5.0.  We therefore
        use generous bounds [0.5, 10.0] that catch gross generation errors
        (e.g. zero noise or pure noise) while accommodating CTF-induced
        signal averaging.
        """
        with mrcfile.open(str(synthetic_data.stack_path), mode="r") as mrc:
            data = mrc.data.copy()

        n_tiles = data.shape[0]
        assert n_tiles == _TOTAL_PARTICLES

        # Signal estimate: mean tile (noise averages out over N tiles)
        mean_tile = np.mean(data, axis=0)
        signal_std = float(np.std(mean_tile))
        assert signal_std > 0, "Mean tile has zero variance — no signal"

        # Noise estimate: per-tile residuals from the mean
        residuals = data - mean_tile[np.newaxis, :, :]
        noise_std = float(np.std(residuals))
        assert noise_std > 0, "Residuals have zero variance — no noise"

        # Compute empirical SNR
        snr_empirical = signal_std / noise_std

        assert 0.5 < snr_empirical < 10.0, (
            f"Empirical SNR {snr_empirical:.2f} outside expected range "
            f"[0.5, 10.0] for injection SNR=5.0 with {n_tiles} tiles"
        )

    def test_snr_matches_specified_value(
        self, synthetic_data: SyntheticDataset,
    ) -> None:
        """compute_snr_of_tiles estimate is consistent with specified SNR.

        Exercises the ``compute_snr_of_tiles`` utility and checks that the
        returned estimate is positive, finite, and within an order of
        magnitude of the specified injection SNR.  The ensemble estimator
        underestimates per-tile SNR due to CTF variation across tilt angles,
        so bounds are generous while still catching gross generation errors.
        """
        # Verify dataset records the expected SNR
        assert synthetic_data.snr == 5.0, (
            f"Dataset SNR is {synthetic_data.snr}, expected 5.0"
        )

        measured_snr = compute_snr_of_tiles(
            synthetic_data.stack_path,
        )

        assert np.isfinite(measured_snr), (
            f"compute_snr_of_tiles returned non-finite value: {measured_snr}"
        )
        assert measured_snr > 0, (
            f"compute_snr_of_tiles returned non-positive value: {measured_snr}"
        )
        # Ensemble SNR is biased low by CTF diversity but should be
        # within one order of magnitude of the injection SNR
        assert 0.5 < measured_snr < 50.0, (
            f"compute_snr_of_tiles returned {measured_snr:.2f}, outside "
            f"expected range [0.5, 50.0] for injection SNR={synthetic_data.snr}"
        )


# ---------------------------------------------------------------------------
# Tests: Gradient sanity check
# ---------------------------------------------------------------------------


class TestGradientSanityCheck:
    """Verify gradient validity at the initial (offset) parameters.

    Before running the optimizer, the gradient at the offset parameters
    should be non-zero (the offset creates a gradient), point toward
    ground truth (descent direction reduces offset), and match finite
    differences within 5%.
    """

    def test_gradient_magnitude_nonzero(
        self, synthetic_data: SyntheticDataset,
    ) -> None:
        """Gradient at offset parameters has non-zero magnitude."""
        (
            data_fts, ref_fts, base_ctf, tilt_angle, fourier_handler,
            peak_mask, offset_params, gt_params, ctf_calculator,
        ) = _prepare_gradient_test_data(synthetic_data)

        _, _, _, gradient = evaluate_score_and_gradient(
            offset_params, data_fts, ref_fts, base_ctf,
            ctf_calculator, fourier_handler, tilt_angle, peak_mask,
        )

        # Gradient is negated for minimization; check absolute magnitude
        grad_magnitude = float(np.linalg.norm(gradient[:3]))
        assert grad_magnitude > 0, (
            f"Gradient magnitude is zero at offset parameters; "
            f"gradient[:3] = {gradient[:3]}"
        )

    def test_gradient_direction_toward_truth(
        self, synthetic_data: SyntheticDataset,
    ) -> None:
        """Gradient descent direction points toward ground truth.

        The negated gradient (ascent direction for score) should have
        the same sign as the ground-truth delta for each global parameter.
        Since the optimizer minimizes -score, the gradient already carries
        the negation. Moving in the -gradient direction should reduce the
        offset.
        """
        (
            data_fts, ref_fts, base_ctf, tilt_angle, fourier_handler,
            peak_mask, offset_params, gt_params, ctf_calculator,
        ) = _prepare_gradient_test_data(synthetic_data)

        _, _, _, gradient = evaluate_score_and_gradient(
            offset_params, data_fts, ref_fts, base_ctf,
            ctf_calculator, fourier_handler, tilt_angle, peak_mask,
        )

        # gradient is -d(score)/d(param), so -gradient = d(score)/d(param)
        # = ascent direction for score.
        # gt_params has the target deltas (negative of offset).
        # The ascent direction should correlate positively with gt_params.
        ascent_direction = -gradient[:3]
        gt_direction = gt_params[:3]

        # Check that the dot product is positive (same general direction)
        dot_product = float(np.dot(ascent_direction, gt_direction))
        assert dot_product > 0, (
            f"Gradient ascent direction does not point toward ground truth. "
            f"ascent[:3]={ascent_direction}, gt[:3]={gt_direction}, "
            f"dot={dot_product}"
        )

    def test_analytical_gradient_matches_fd(
        self, synthetic_data: SyntheticDataset,
    ) -> None:
        """Analytical gradient matches finite-difference gradient within 5%.

        Uses central differences with a step size of 1.0 Angstrom for
        defocus parameters and 0.001 radians for angle.  Both the
        analytical and FD evaluations use a fixed peak mask, so this
        comparison validates the gradient under a fixed-peak approximation
        (i.e. the cross-correlation peak position is held constant across
        parameter perturbations rather than re-located per step).
        """
        (
            data_fts, ref_fts, base_ctf, tilt_angle, fourier_handler,
            peak_mask, offset_params, gt_params, ctf_calculator,
        ) = _prepare_gradient_test_data(synthetic_data)

        # Compute analytical gradient
        score_0, _, _, analytical_grad = evaluate_score_and_gradient(
            offset_params, data_fts, ref_fts, base_ctf,
            ctf_calculator, fourier_handler, tilt_angle, peak_mask,
        )

        # Compute finite-difference gradient for global params (indices 0-2)
        step_sizes = np.array([1.0, 1.0, 0.001])  # A, A, radians
        fd_grad = np.zeros(3, dtype=np.float64)

        for j in range(3):
            params_plus = offset_params.copy()
            params_minus = offset_params.copy()
            params_plus[j] += step_sizes[j]
            params_minus[j] -= step_sizes[j]

            # Use the scoring function (not gradient) for FD
            score_plus, _, _ = evaluate_score_and_shifts(
                params_plus, data_fts, ref_fts, base_ctf,
                ctf_calculator, fourier_handler, tilt_angle, peak_mask,
            )
            score_minus, _, _ = evaluate_score_and_shifts(
                params_minus, data_fts, ref_fts, base_ctf,
                ctf_calculator, fourier_handler, tilt_angle, peak_mask,
            )

            # FD gradient of -score (to match the negated analytical gradient)
            fd_grad[j] = -(score_plus - score_minus) / (2.0 * step_sizes[j])

        # Compare analytical to FD within 5% relative error
        for j in range(3):
            if abs(fd_grad[j]) < 1e-10:
                # Skip parameters with negligible FD gradient
                continue
            rel_error = abs(analytical_grad[j] - fd_grad[j]) / abs(fd_grad[j])
            assert rel_error < 0.05, (
                f"Parameter {j}: analytical={analytical_grad[j]:.6e}, "
                f"FD={fd_grad[j]:.6e}, relative error={rel_error:.4f} "
                f"(exceeds 5% threshold)"
            )


# ---------------------------------------------------------------------------
# Tests: Standard CTF recovery (L-BFGS-B)
# ---------------------------------------------------------------------------


class TestCTFRecoveryLBFGSB:
    """Verify L-BFGS-B recovers CTF parameters from +300A/+100A/+5deg offset."""

    def test_defocus_recovery(
        self, lbfgsb_result: tuple[Path, SyntheticDataset, PipelineResults],
    ) -> None:
        """Pipeline recovers defocus offset to within 100A of ground truth."""
        output_star, dataset, _ = lbfgsb_result
        stats = _compute_recovery_stats(output_star, dataset)
        assert stats["mean_defocus_error"] < 100.0, (
            f"Mean defocus error {stats['mean_defocus_error']:.1f}A "
            f"exceeds 100A threshold"
        )

    def test_half_astigmatism_recovery(
        self, lbfgsb_result: tuple[Path, SyntheticDataset, PipelineResults],
    ) -> None:
        """Pipeline recovers half-astigmatism to within 50A of ground truth."""
        output_star, dataset, _ = lbfgsb_result
        stats = _compute_recovery_stats(output_star, dataset)
        assert stats["mean_half_astig_error"] < 50.0, (
            f"Mean half-astigmatism error {stats['mean_half_astig_error']:.1f}A "
            f"exceeds 50A threshold"
        )

    def test_astigmatism_angle_recovery(
        self, lbfgsb_result: tuple[Path, SyntheticDataset, PipelineResults],
    ) -> None:
        """Pipeline recovers astigmatism angle to within 2 degrees."""
        output_star, dataset, _ = lbfgsb_result
        stats = _compute_recovery_stats(output_star, dataset)
        assert stats["mean_angle_error"] < 2.0, (
            f"Mean angle error {stats['mean_angle_error']:.2f} degrees "
            f"exceeds 2 degree threshold"
        )

    def test_score_increases(
        self, lbfgsb_result: tuple[Path, SyntheticDataset, PipelineResults],
    ) -> None:
        """Scores increase from initial to final iteration."""
        _, _, result = lbfgsb_result

        # Check that all tilt groups with sufficient history show score increase
        for tgr in result.tilt_group_results:
            history = tgr.refinement_results.score_history
            if len(history) >= 2:
                assert history[-1] >= history[0], (
                    f"Score did not increase for tilt {tgr.tilt_name}: "
                    f"initial={history[0]:.4f}, final={history[-1]:.4f}"
                )


# ---------------------------------------------------------------------------
# Tests: Standard CTF recovery (ADAM)
# ---------------------------------------------------------------------------


class TestCTFRecoveryADAM:
    """Verify ADAM recovers CTF parameters from +300A/+100A/+5deg offset."""

    def test_defocus_recovery(
        self, adam_result: tuple[Path, SyntheticDataset, PipelineResults],
    ) -> None:
        """Pipeline recovers defocus offset to within 100A of ground truth."""
        output_star, dataset, _ = adam_result
        stats = _compute_recovery_stats(output_star, dataset)
        assert stats["mean_defocus_error"] < 100.0, (
            f"Mean defocus error {stats['mean_defocus_error']:.1f}A "
            f"exceeds 100A threshold"
        )

    def test_half_astigmatism_recovery(
        self, adam_result: tuple[Path, SyntheticDataset, PipelineResults],
    ) -> None:
        """Pipeline recovers half-astigmatism to within 50A of ground truth."""
        output_star, dataset, _ = adam_result
        stats = _compute_recovery_stats(output_star, dataset)
        assert stats["mean_half_astig_error"] < 50.0, (
            f"Mean half-astigmatism error {stats['mean_half_astig_error']:.1f}A "
            f"exceeds 50A threshold"
        )

    def test_astigmatism_angle_recovery(
        self, adam_result: tuple[Path, SyntheticDataset, PipelineResults],
    ) -> None:
        """Pipeline recovers astigmatism angle to within 2 degrees."""
        output_star, dataset, _ = adam_result
        stats = _compute_recovery_stats(output_star, dataset)
        assert stats["mean_angle_error"] < 2.0, (
            f"Mean angle error {stats['mean_angle_error']:.2f} degrees "
            f"exceeds 2 degree threshold"
        )

    def test_score_increases(
        self, adam_result: tuple[Path, SyntheticDataset, PipelineResults],
    ) -> None:
        """Scores increase from initial to final iteration."""
        _, _, result = adam_result

        for tgr in result.tilt_group_results:
            history = tgr.refinement_results.score_history
            if len(history) >= 2:
                assert history[-1] >= history[0], (
                    f"Score did not increase for tilt {tgr.tilt_name}: "
                    f"initial={history[0]:.4f}, final={history[-1]:.4f}"
                )


# ---------------------------------------------------------------------------
# Tests: Optimizer comparison
# ---------------------------------------------------------------------------


class TestOptimizerComparison:
    """Compare L-BFGS-B and ADAM convergence on the same synthetic data."""

    def test_lbfgsb_fewer_iterations(
        self,
        lbfgsb_result: tuple[Path, SyntheticDataset, PipelineResults],
        adam_result: tuple[Path, SyntheticDataset, PipelineResults],
    ) -> None:
        """L-BFGS-B converges in fewer iterations than ADAM.

        Both optimizers are run with the same maximum iteration budget
        (via module-scoped fixtures).  L-BFGS-B, being a quasi-Newton
        method, should achieve comparable or better score in fewer
        iterations.
        """
        _, _, lbfgsb_pipeline = lbfgsb_result
        _, _, adam_pipeline = adam_result

        # Compare total iterations across all tilt groups
        lbfgsb_total_iters = sum(
            tgr.n_iterations for tgr in lbfgsb_pipeline.tilt_group_results
        )
        adam_total_iters = sum(
            tgr.n_iterations for tgr in adam_pipeline.tilt_group_results
        )

        assert lbfgsb_total_iters <= adam_total_iters, (
            f"L-BFGS-B used {lbfgsb_total_iters} total iterations vs "
            f"ADAM's {adam_total_iters} — expected L-BFGS-B to converge "
            f"in fewer or equal iterations"
        )


# ---------------------------------------------------------------------------
# Tests: Per-particle delta_z
# ---------------------------------------------------------------------------


class TestPerParticleDeltaZ:
    """Verify per-particle z-offset refinement on well-posed synthetic data."""

    def test_delta_z_mean_magnitude(
        self, lbfgsb_result: tuple[Path, SyntheticDataset, PipelineResults],
    ) -> None:
        """Mean magnitude of per-particle delta_z offsets < 50A."""
        _, _, result = lbfgsb_result

        all_dz = np.concatenate([
            tgr.refinement_results.delta_z
            for tgr in result.tilt_group_results
        ])
        mean_mag = float(np.mean(np.abs(all_dz)))
        assert mean_mag < 50.0, (
            f"Mean |delta_z| = {mean_mag:.1f}A exceeds 50A threshold"
        )

    def test_delta_z_std(
        self, lbfgsb_result: tuple[Path, SyntheticDataset, PipelineResults],
    ) -> None:
        """Standard deviation of per-particle delta_z < 200A."""
        _, _, result = lbfgsb_result

        all_dz = np.concatenate([
            tgr.refinement_results.delta_z
            for tgr in result.tilt_group_results
        ])
        dz_std = float(np.std(all_dz))
        assert dz_std < 200.0, (
            f"Std dev of delta_z = {dz_std:.1f}A exceeds 200A threshold"
        )


# ---------------------------------------------------------------------------
# Tests: Positive control
# ---------------------------------------------------------------------------


class TestPositiveControl:
    """Positive control: ground-truth CTF input produces near-zero corrections.

    When the pipeline is given the correct CTF parameters (no offset),
    the optimizer should make negligible corrections.
    """

    def test_ground_truth_produces_small_corrections(
        self, positive_control_data: SyntheticDataset,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """Running with ground-truth CTF yields delta_defocus < 10A.

        Uses a dedicated low-defocus dataset (700A, no astigmatism) where
        the mask-CTF interaction bias is < 10A.  At defocus=700A only one
        CTF zero falls inside the lowpass=3.5A frequency range, limiting
        the spectral phase mixing that would otherwise bias the landscape.
        """
        output_dir = tmp_path_factory.mktemp("positive_control")
        output_star = output_dir / "refined_gt.star"
        opts = PipelineOptions(
            optimizer_type="lbfgsb",
            maximum_iterations=_MAX_ITERATIONS,
            minimum_global_iterations=3,
            lowpass_cutoff=_LOWPASS_CUTOFF,
            highpass_cutoff=_HIGHPASS_CUTOFF,
        )

        result = refine_ctf_from_star(
            positive_control_data.truth_star_path,  # Ground truth input
            positive_control_data.stack_path,
            positive_control_data.reference_path,
            output_star,
            options=opts,
        )

        # Check that corrections are small
        for tgr in result.tilt_group_results:
            rr = tgr.refinement_results
            assert abs(rr.delta_defocus_tilt) < 10.0, (
                f"Positive control: delta_defocus={rr.delta_defocus_tilt:.1f}A "
                f"for tilt {tgr.tilt_name} (expected < 10A)"
            )


# ---------------------------------------------------------------------------
# Tests: Negative control
# ---------------------------------------------------------------------------


class TestNegativeControl:
    """Negative control: large offset (+5000A) converges in correct direction.

    With a large defocus offset, the pipeline should at least converge
    in the correct direction (delta_defocus has the correct sign).
    """

    def test_large_offset_correct_direction(
        self, tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """Running with +5000A offset yields delta_defocus with correct sign."""
        output_dir = tmp_path_factory.mktemp("negative_control")

        # Generate dataset with large offset
        large_offset = CTFOffset(
            defocus_offset=5000.0,
            astigmatism_offset=100.0,
            angle_offset=5.0,
        )
        dataset = generate_synthetic_dataset(
            output_dir / "data",
            tile_size=_TILE_SIZE,
            vol_size=_VOL_SIZE,
            n_particles_per_tilt=_N_PARTICLES_PER_TILT,
            tilt_angles=(0.0,),  # Single tilt for speed
            ground_truth_ctf=_GT_CTF,
            ctf_offset=large_offset,
            microscope=_MICROSCOPE,
            snr=5.0,
            seed=99,
            delta_z_sigma=30.0,
        )

        output_star = output_dir / "refined_large.star"
        opts = PipelineOptions(
            optimizer_type="lbfgsb",
            maximum_iterations=_MAX_ITERATIONS,
            minimum_global_iterations=3,
            lowpass_cutoff=_LOWPASS_CUTOFF,
            highpass_cutoff=_HIGHPASS_CUTOFF,
        )

        result = refine_ctf_from_star(
            dataset.offset_star_path,
            dataset.stack_path,
            dataset.reference_path,
            output_star,
            options=opts,
        )

        # delta_defocus_tilt should be negative (correcting the +5000A offset)
        for tgr in result.tilt_group_results:
            rr = tgr.refinement_results
            assert rr.delta_defocus_tilt < 0, (
                f"Negative control: delta_defocus={rr.delta_defocus_tilt:.1f}A "
                f"should be negative to correct +5000A offset"
            )


# ---------------------------------------------------------------------------
# Tests: Dataset integrity
# ---------------------------------------------------------------------------


class TestDatasetIntegrity:
    """Verify the synthetic dataset is well-formed."""

    def test_particle_count(
        self, synthetic_data: SyntheticDataset,
    ) -> None:
        """Dataset has the expected number of particles (50+)."""
        truth_particles, _ = parse_star_file(synthetic_data.truth_star_path)
        assert len(truth_particles) >= 50, (
            f"Expected >= 50 particles, got {len(truth_particles)}"
        )

    def test_tilt_group_count(
        self, synthetic_data: SyntheticDataset,
    ) -> None:
        """Dataset has 3+ tilt groups."""
        assert len(synthetic_data.tilt_groups) >= 3, (
            f"Expected >= 3 tilt groups, got {len(synthetic_data.tilt_groups)}"
        )

    def test_stack_dimensions(
        self, synthetic_data: SyntheticDataset,
    ) -> None:
        """MRC stack has correct dimensions."""
        with mrcfile.open(str(synthetic_data.stack_path), mode="r") as mrc:
            data = mrc.data
            assert data.shape[0] == _TOTAL_PARTICLES
            assert data.shape[1] == _TILE_SIZE
            assert data.shape[2] == _TILE_SIZE

    def test_reference_volume_dimensions(
        self, synthetic_data: SyntheticDataset,
    ) -> None:
        """Reference volume has correct dimensions."""
        with mrcfile.open(str(synthetic_data.reference_path), mode="r") as mrc:
            data = mrc.data
            assert data.shape == (_VOL_SIZE, _VOL_SIZE, _VOL_SIZE)

    def test_offset_star_has_offset_ctf(
        self, synthetic_data: SyntheticDataset,
    ) -> None:
        """Offset star file has CTF parameters shifted from ground truth."""
        offset_particles, _ = parse_star_file(synthetic_data.offset_star_path)
        truth_particles, _ = parse_star_file(synthetic_data.truth_star_path)

        assert len(offset_particles) == len(truth_particles)

        for idx, (op, tp) in enumerate(
            zip(offset_particles, truth_particles, strict=True),
        ):
            offset_mean = (op["defocus_1"] + op["defocus_2"]) / 2.0
            truth_mean = (tp["defocus_1"] + tp["defocus_2"]) / 2.0

            # Verify the offset is approximately +300A
            assert abs(
                (offset_mean - truth_mean) - _STANDARD_OFFSET.defocus_offset
            ) < 1.0, (
                f"Particle {idx}: defocus offset is "
                f"{offset_mean - truth_mean:.1f}A, "
                f"expected ~{_STANDARD_OFFSET.defocus_offset}A"
            )

            # Verify angle offset matches _STANDARD_OFFSET
            expected_angle_offset = _STANDARD_OFFSET.angle_offset
            assert abs(
                (op["defocus_angle"] - tp["defocus_angle"])
                - expected_angle_offset
            ) < 0.1, (
                f"Particle {idx}: angle offset is "
                f"{op['defocus_angle'] - tp['defocus_angle']:.2f} deg, "
                f"expected ~{expected_angle_offset} deg"
            )
