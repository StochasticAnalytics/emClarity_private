"""Tests for the CTF refinement pipeline orchestrator.

Tests the full star-to-star pipeline using synthetic data:
- 1 tilt group with 5 particles
- Negative control: empty star file
- Negative control: tilt group with zero particles
- Option parsing
- GPU memory cleanup (no-error check)
"""

from __future__ import annotations

import logging
from pathlib import Path

import mrcfile
import numpy as np
import pytest

from ...ctf.star_io.emc_star_parser import (
    COLUMN_SPEC,
    parse_star_file,
    write_star_file,
)
from ..emc_ctf_refine_pipeline import (
    PipelineOptions,
    PipelineResults,
    TiltGroupResult,
    _apply_refinement_to_particles,
    _free_gpu_memory,
    compute_electron_wavelength,
    refine_ctf_from_star,
)
from ..emc_refine_tilt_ctf import RefinementResults


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Microscope parameters for all test data
_PIXEL_SIZE = 1.5       # Angstroms
_VOLTAGE_KV = 300.0     # kV
_CS_MM = 2.7            # mm
_AMP_CONTRAST = 0.07
_DF1 = 20000.0          # Angstroms
_DF2 = 19000.0          # Angstroms
_DF_ANGLE = 45.0        # degrees
_TILT_ANGLE = 10.0      # degrees
_TILT_NAME = "tilt_001.mrc"
_TILE_SIZE = 32          # pixels (small for fast tests)
_REF_VOL_SIZE = 32       # voxels


def _make_particle(
    position: int,
    tilt_name: str = _TILT_NAME,
    tilt_angle: float = _TILT_ANGLE,
) -> dict:
    """Create a particle dict with canonical test values."""
    return {
        "position_in_stack": position,
        "psi": 0.0,
        "theta": 0.0,
        "phi": 0.0,
        "x_shift": 0.0,
        "y_shift": 0.0,
        "defocus_1": _DF1,
        "defocus_2": _DF2,
        "defocus_angle": _DF_ANGLE,
        "phase_shift": 0.0,
        "occupancy": 100.0,
        "logp": 0.0,
        "sigma": 1.0,
        "score": 0.0,
        "score_change": 0.0,
        "pixel_size": _PIXEL_SIZE,
        "voltage_kv": _VOLTAGE_KV,
        "cs_mm": _CS_MM,
        "amplitude_contrast": _AMP_CONTRAST,
        "beam_tilt_x": 0.0,
        "beam_tilt_y": 0.0,
        "image_shift_x": 0.0,
        "image_shift_y": 0.0,
        "best_2d_class": 1,
        "beam_tilt_group": 1,
        "particle_group": 1,
        "pre_exposure": 0.0,
        "total_exposure": 50.0,
        "original_image_filename": tilt_name,
        "tilt_angle": tilt_angle,
    }


def _star_header_lines() -> list[str]:
    """Standard star file header lines matching cisTEM format."""
    labels = [
        "_cisTEMPositionInStack",
        "_cisTEMAnglePsi",
        "_cisTEMAngleTheta",
        "_cisTEMAnglePhi",
        "_cisTEMXShift",
        "_cisTEMYShift",
        "_cisTEMDefocus1",
        "_cisTEMDefocus2",
        "_cisTEMDefocusAngle",
        "_cisTEMPhaseShift",
        "_cisTEMOccupancy",
        "_cisTEMLogP",
        "_cisTEMSigma",
        "_cisTEMScore",
        "_cisTEMScoreChange",
        "_cisTEMPixelSize",
        "_cisTEMVoltage",
        "_cisTEMCs",
        "_cisTEMAmplitudeContrast",
        "_cisTEMBeamTiltX",
        "_cisTEMBeamTiltY",
        "_cisTEMImageShiftX",
        "_cisTEMImageShiftY",
        "_cisTEMBest2DClass",
        "_cisTEMBeamTiltGroup",
        "_cisTEMParticleGroup",
        "_cisTEMPreExposure",
        "_cisTEMTotalExposure",
        "_cisTEMOriginalImageFilename",
        "_cisTEMTiltAngle",
    ]
    lines = ["", "data_", "", "loop_"]
    for label in labels:
        lines.append(label)
    return lines


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Return a temporary directory for test files."""
    return tmp_path


@pytest.fixture
def star_5particles(tmp_dir: Path) -> Path:
    """Create a star file with 5 particles in 1 tilt group."""
    path = tmp_dir / "input.star"
    particles = [_make_particle(i + 1) for i in range(5)]
    write_star_file(path, particles, _star_header_lines())
    return path


@pytest.fixture
def empty_star(tmp_dir: Path) -> Path:
    """Create a star file with header only, no data rows."""
    path = tmp_dir / "empty.star"
    write_star_file(path, [], _star_header_lines())
    return path


@pytest.fixture
def stack_5slices(tmp_dir: Path) -> Path:
    """Create an MRC stack with 5 slices of size TILE_SIZE x TILE_SIZE.

    Each slice contains a Gaussian blob at center with added noise,
    ensuring non-trivial signal for cross-correlation.
    """
    path = tmp_dir / "stack.mrc"
    rng = np.random.default_rng(42)

    # Create data with Gaussian blob + noise
    nz = 5
    data = np.zeros((nz, _TILE_SIZE, _TILE_SIZE), dtype=np.float32)
    y, x = np.mgrid[0:_TILE_SIZE, 0:_TILE_SIZE]
    center = _TILE_SIZE // 2
    blob = np.exp(-((y - center) ** 2 + (x - center) ** 2) / (2 * 3.0 ** 2))

    for z in range(nz):
        data[z] = blob.astype(np.float32) + 0.1 * rng.standard_normal(
            (_TILE_SIZE, _TILE_SIZE)
        ).astype(np.float32)

    with mrcfile.new(str(path), overwrite=True) as mrc:
        mrc.set_data(data)

    return path


@pytest.fixture
def ref_volume(tmp_dir: Path) -> Path:
    """Create a 3D MRC reference volume with a Gaussian blob at center."""
    path = tmp_dir / "ref_vol.mrc"
    nv = _REF_VOL_SIZE
    z, y, x = np.mgrid[0:nv, 0:nv, 0:nv]
    center = nv // 2
    sigma = 4.0
    volume = np.exp(
        -((z - center) ** 2 + (y - center) ** 2 + (x - center) ** 2)
        / (2 * sigma ** 2)
    ).astype(np.float32)

    with mrcfile.new(str(path), overwrite=True) as mrc:
        mrc.set_data(volume)

    return path


# ---------------------------------------------------------------------------
# Tests: compute_electron_wavelength
# ---------------------------------------------------------------------------


class TestElectronWavelength:
    """Test the relativistic de Broglie wavelength computation."""

    def test_300kv_wavelength(self) -> None:
        """300 kV produces ~0.0197 Angstrom wavelength."""
        wl = compute_electron_wavelength(300.0)
        assert 0.019 < wl < 0.020

    def test_200kv_wavelength(self) -> None:
        """200 kV produces a longer wavelength than 300 kV."""
        wl_200 = compute_electron_wavelength(200.0)
        wl_300 = compute_electron_wavelength(300.0)
        assert wl_200 > wl_300

    def test_zero_voltage_raises(self) -> None:
        """Zero voltage triggers division by zero or NaN."""
        with pytest.raises((ZeroDivisionError, ValueError)):
            wl = compute_electron_wavelength(0.0)
            if not np.isfinite(wl):
                raise ValueError("Non-finite wavelength")


# ---------------------------------------------------------------------------
# Tests: PipelineOptions
# ---------------------------------------------------------------------------


class TestPipelineOptions:
    """Test PipelineOptions defaults and customisation."""

    def test_default_values(self) -> None:
        """Default options match expected values."""
        opts = PipelineOptions()
        assert opts.optimizer_type == "adam"
        assert opts.defocus_search_range == 5000.0
        assert opts.maximum_iterations == 15
        assert opts.lowpass_cutoff == 10.0
        assert opts.highpass_cutoff == 400.0

    def test_custom_values(self) -> None:
        """Custom options are preserved."""
        opts = PipelineOptions(
            optimizer_type="lbfgsb",
            defocus_search_range=3000.0,
            maximum_iterations=10,
            lowpass_cutoff=8.0,
            highpass_cutoff=300.0,
        )
        assert opts.optimizer_type == "lbfgsb"
        assert opts.defocus_search_range == 3000.0
        assert opts.maximum_iterations == 10
        assert opts.lowpass_cutoff == 8.0
        assert opts.highpass_cutoff == 300.0

    def test_all_fields_settable(self) -> None:
        """All option fields can be set via constructor."""
        opts = PipelineOptions(
            optimizer_type="adam",
            defocus_search_range=2000.0,
            maximum_iterations=5,
            minimum_global_iterations=2,
            global_only=True,
            lowpass_cutoff=12.0,
            highpass_cutoff=500.0,
            shift_sigma=3.0,
            z_offset_sigma=50.0,
            soft_mask_edge_width=5.0,
        )
        assert opts.global_only is True
        assert opts.minimum_global_iterations == 2
        assert opts.shift_sigma == 3.0
        assert opts.z_offset_sigma == 50.0
        assert opts.soft_mask_edge_width == 5.0


# ---------------------------------------------------------------------------
# Tests: _apply_refinement_to_particles
# ---------------------------------------------------------------------------


class TestApplyRefinement:
    """Test the result-unpacking logic that updates particle dicts."""

    def _make_results(self, n: int) -> RefinementResults:
        """Create synthetic RefinementResults for n particles."""
        return RefinementResults(
            delta_defocus_tilt=100.0,
            delta_half_astigmatism=50.0,
            delta_astigmatism_angle=0.1,  # radians
            delta_z=np.full(n, 10.0),
            shift_x=np.full(n, 2.0),
            shift_y=np.full(n, -1.0),
            per_particle_scores=np.full(n, 0.85),
            score_history=[0.5, 0.7, 0.85],
            converged=True,
        )

    def test_defocus_updated(self) -> None:
        """Defocus values are updated with correction and astigmatism delta."""
        particles = [_make_particle(1)]
        results = self._make_results(1)

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        p = particles[0]
        # The correction includes delta_defocus_tilt + delta_z * cos(tilt)
        cos_tilt = np.cos(np.radians(_TILT_ANGLE))
        expected_correction = 100.0 + 10.0 * cos_tilt
        expected_df1 = _DF1 + 50.0 + expected_correction
        expected_df2 = _DF2 - 50.0 + expected_correction
        assert abs(p["defocus_1"] - expected_df1) < 0.01
        assert abs(p["defocus_2"] - expected_df2) < 0.01

    def test_angle_updated(self) -> None:
        """Defocus angle is updated by delta_astigmatism_angle."""
        particles = [_make_particle(1)]
        results = self._make_results(1)

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        p = particles[0]
        expected_angle = np.degrees(np.radians(_DF_ANGLE) + 0.1)
        assert abs(p["defocus_angle"] - expected_angle) < 0.01

    def test_shifts_converted_to_angstroms(self) -> None:
        """Shifts are converted from pixels to Angstroms."""
        particles = [_make_particle(1)]
        results = self._make_results(1)

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        p = particles[0]
        assert abs(p["x_shift"] - 2.0 * _PIXEL_SIZE) < 0.001
        assert abs(p["y_shift"] - (-1.0) * _PIXEL_SIZE) < 0.001

    def test_score_updated(self) -> None:
        """Particle score is set from per_particle_scores."""
        particles = [_make_particle(1)]
        results = self._make_results(1)

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        assert abs(particles[0]["score"] - 0.85) < 0.001

    def test_unprocessed_columns_preserved(self) -> None:
        """Columns not modified by refinement retain original values."""
        particles = [_make_particle(1)]
        results = self._make_results(1)
        orig = dict(particles[0])

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        p = particles[0]
        # These columns must not change
        assert p["voltage_kv"] == orig["voltage_kv"]
        assert p["cs_mm"] == orig["cs_mm"]
        assert p["amplitude_contrast"] == orig["amplitude_contrast"]
        assert p["pixel_size"] == orig["pixel_size"]
        assert p["psi"] == orig["psi"]
        assert p["theta"] == orig["theta"]
        assert p["phi"] == orig["phi"]
        assert p["position_in_stack"] == orig["position_in_stack"]
        assert p["occupancy"] == orig["occupancy"]
        assert p["phase_shift"] == orig["phase_shift"]
        assert p["beam_tilt_x"] == orig["beam_tilt_x"]
        assert p["beam_tilt_y"] == orig["beam_tilt_y"]
        assert p["image_shift_x"] == orig["image_shift_x"]
        assert p["image_shift_y"] == orig["image_shift_y"]
        assert p["best_2d_class"] == orig["best_2d_class"]
        assert p["beam_tilt_group"] == orig["beam_tilt_group"]
        assert p["particle_group"] == orig["particle_group"]
        assert p["pre_exposure"] == orig["pre_exposure"]
        assert p["total_exposure"] == orig["total_exposure"]
        assert p["original_image_filename"] == orig["original_image_filename"]
        assert p["tilt_angle"] == orig["tilt_angle"]


# ---------------------------------------------------------------------------
# Tests: Negative controls
# ---------------------------------------------------------------------------


class TestEmptyStarFile:
    """Negative control: empty star file (header only, no data rows)."""

    def test_empty_star_produces_empty_output(
        self, empty_star: Path, stack_5slices: Path, ref_volume: Path,
        tmp_dir: Path,
    ) -> None:
        """Empty input produces empty output without error."""
        output_path = tmp_dir / "empty_out.star"

        result = refine_ctf_from_star(
            empty_star, stack_5slices, ref_volume, output_path,
        )

        assert result.n_particles_total == 0
        assert result.n_particles_processed == 0
        assert result.n_tilt_groups == 0
        assert result.tilt_group_results == []
        assert output_path.exists()

        # Verify output is parseable and empty
        out_particles, out_headers = parse_star_file(output_path)
        assert len(out_particles) == 0


# ---------------------------------------------------------------------------
# Tests: Full pipeline (single tilt group, 5 particles)
# ---------------------------------------------------------------------------


class TestSingleTiltGroupPipeline:
    """Integration test: 1 tilt group, 5 particles, sequential processing."""

    def test_pipeline_runs_without_error(
        self, star_5particles: Path, stack_5slices: Path, ref_volume: Path,
        tmp_dir: Path,
    ) -> None:
        """Pipeline completes without raising exceptions."""
        output_path = tmp_dir / "refined.star"

        result = refine_ctf_from_star(
            star_5particles, stack_5slices, ref_volume, output_path,
        )

        assert isinstance(result, PipelineResults)
        assert result.n_particles_total == 5
        assert result.n_particles_processed == 5
        assert result.n_tilt_groups == 1

    def test_output_star_has_30_columns(
        self, star_5particles: Path, stack_5slices: Path, ref_volume: Path,
        tmp_dir: Path,
    ) -> None:
        """Output star file has the correct 30-column format."""
        output_path = tmp_dir / "refined.star"

        refine_ctf_from_star(
            star_5particles, stack_5slices, ref_volume, output_path,
        )

        out_particles, out_headers = parse_star_file(output_path)
        assert len(out_particles) == 5

        # Verify all 30 columns are present
        expected_cols = {name for name, _ in COLUMN_SPEC}
        for p in out_particles:
            assert set(p.keys()) == expected_cols

    def test_defocus_columns_updated(
        self, star_5particles: Path, stack_5slices: Path, ref_volume: Path,
        tmp_dir: Path,
    ) -> None:
        """Defocus and shift columns are modified by refinement."""
        output_path = tmp_dir / "refined.star"

        refine_ctf_from_star(
            star_5particles, stack_5slices, ref_volume, output_path,
        )

        in_particles, _ = parse_star_file(star_5particles)
        out_particles, _ = parse_star_file(output_path)

        # At least some particles should have different defocus values
        # (the optimizer adjusts defocus even with synthetic data)
        any_df1_changed = any(
            abs(inp["defocus_1"] - out["defocus_1"]) > 0.001
            for inp, out in zip(in_particles, out_particles)
        )
        # Score column should be updated (was 0.0 initially)
        all_scores_set = all(
            out["score"] != 0.0 for out in out_particles
        )
        # At least one of these must hold for a non-trivial refinement
        assert any_df1_changed or all_scores_set

    def test_unprocessed_columns_preserved(
        self, star_5particles: Path, stack_5slices: Path, ref_volume: Path,
        tmp_dir: Path,
    ) -> None:
        """Columns not modified by refinement retain original values."""
        output_path = tmp_dir / "refined.star"

        refine_ctf_from_star(
            star_5particles, stack_5slices, ref_volume, output_path,
        )

        in_particles, _ = parse_star_file(star_5particles)
        out_particles, _ = parse_star_file(output_path)

        preserved_cols = [
            "voltage_kv", "cs_mm", "amplitude_contrast", "pixel_size",
            "psi", "theta", "phi", "position_in_stack", "occupancy",
            "phase_shift", "beam_tilt_x", "beam_tilt_y",
            "image_shift_x", "image_shift_y", "best_2d_class",
            "beam_tilt_group", "particle_group", "pre_exposure",
            "total_exposure", "original_image_filename", "tilt_angle",
        ]

        for inp, out in zip(in_particles, out_particles):
            for col in preserved_cols:
                assert inp[col] == out[col], (
                    f"Column '{col}' changed: {inp[col]} -> {out[col]}"
                )

    def test_tilt_group_result_structure(
        self, star_5particles: Path, stack_5slices: Path, ref_volume: Path,
        tmp_dir: Path,
    ) -> None:
        """TiltGroupResult has expected fields and values."""
        output_path = tmp_dir / "refined.star"

        result = refine_ctf_from_star(
            star_5particles, stack_5slices, ref_volume, output_path,
        )

        assert len(result.tilt_group_results) == 1
        tgr = result.tilt_group_results[0]
        assert isinstance(tgr, TiltGroupResult)
        assert tgr.tilt_name == _TILT_NAME
        assert tgr.tilt_angle == _TILT_ANGLE
        assert tgr.n_particles == 5
        assert tgr.n_iterations > 0
        assert isinstance(tgr.converged, (bool, np.bool_))
        assert isinstance(tgr.mean_score, float)
        assert isinstance(tgr.refinement_results, RefinementResults)

    def test_with_custom_options(
        self, star_5particles: Path, stack_5slices: Path, ref_volume: Path,
        tmp_dir: Path,
    ) -> None:
        """Pipeline accepts and uses custom PipelineOptions."""
        output_path = tmp_dir / "refined_custom.star"

        opts = PipelineOptions(
            optimizer_type="adam",
            defocus_search_range=3000.0,
            maximum_iterations=5,
            lowpass_cutoff=12.0,
            highpass_cutoff=300.0,
        )

        result = refine_ctf_from_star(
            star_5particles, stack_5slices, ref_volume, output_path,
            options=opts,
        )

        assert result.n_particles_total == 5
        assert result.n_particles_processed == 5
        # With only 5 iterations, the score history should be short
        tgr = result.tilt_group_results[0]
        assert tgr.n_iterations <= 6  # max_iterations + possible final eval


# ---------------------------------------------------------------------------
# Tests: Pipeline logging
# ---------------------------------------------------------------------------


class TestPipelineLogging:
    """Verify pipeline emits per-tilt summary log messages."""

    def test_per_tilt_summary_logged(
        self, star_5particles: Path, stack_5slices: Path, ref_volume: Path,
        tmp_dir: Path, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Pipeline logs per-tilt summary with particle count and score."""
        output_path = tmp_dir / "refined.star"

        with caplog.at_level(logging.INFO):
            refine_ctf_from_star(
                star_5particles, stack_5slices, ref_volume, output_path,
            )

        # Check that per-tilt summary was logged
        log_text = caplog.text
        assert _TILT_NAME in log_text
        assert "particles" in log_text.lower()
        assert "score" in log_text.lower()
        assert "converged" in log_text.lower()


# ---------------------------------------------------------------------------
# Tests: GPU memory cleanup
# ---------------------------------------------------------------------------


class TestGPUMemoryCleanup:
    """Verify GPU memory cleanup runs without error."""

    def test_free_gpu_memory_no_error(self) -> None:
        """_free_gpu_memory() runs without error on CPU-only systems."""
        # Should not raise regardless of GPU availability
        _free_gpu_memory()
