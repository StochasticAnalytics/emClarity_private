"""Tests for convergence health warnings and debug mode filtering.

TASK-011: Tests for check_convergence_health() and debug tilt filtering.

Positive controls:
    - A healthy result (small corrections, improving score) always returns
      an empty warning list regardless of implementation details.
    - debug_tilt_list filtering always preserves unmatched particle occupancy
      regardless of the refinement outcome.

Negative controls:
    - A result with delta_df=100A always returns empty (below the 2000A
      threshold) regardless of other parameter values.
    - A result with score_history=[1.0, 2.0] (improving) never triggers
      the score-decrease warning.
"""

from __future__ import annotations

from pathlib import Path

import mrcfile
import numpy as np
import pytest

from ..emc_ctf_refine_pipeline import (
    PipelineOptions,
    check_convergence_health,
)
from ..emc_refine_tilt_ctf import RefinementResults

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_results(n: int = 5, **kwargs) -> RefinementResults:
    """Create synthetic RefinementResults for n particles.

    Keyword args override default field values.
    """
    defaults = dict(
        delta_defocus_tilt=100.0,
        delta_half_astigmatism=50.0,
        delta_astigmatism_angle=0.1,
        delta_z=np.full(n, 10.0),
        shift_x=np.full(n, 2.0),
        shift_y=np.full(n, -1.0),
        per_particle_scores=np.full(n, 0.85),
        score_history=[0.5, 0.7, 0.85],
        converged=True,
    )
    defaults.update(kwargs)
    return RefinementResults(**defaults)


def _default_options(**kwargs) -> PipelineOptions:
    """Create PipelineOptions with overrides."""
    return PipelineOptions(**kwargs)


# ---------------------------------------------------------------------------
# Tests: check_convergence_health — healthy results
# ---------------------------------------------------------------------------


class TestConvergenceHealthHealthy:
    """Positive control: healthy results produce no warnings."""

    def test_healthy_result_no_warnings(self) -> None:
        """Small corrections and improving score → empty warning list."""
        results = _make_results(
            delta_defocus_tilt=100.0,
            delta_half_astigmatism=50.0,
            delta_astigmatism_angle=0.1,
            score_history=[0.5, 0.7, 0.85],
        )
        options = _default_options()
        warnings = check_convergence_health(results, options)
        assert warnings == []

    def test_zero_delta_no_warnings(self) -> None:
        """Zero deltas and flat score → no warnings."""
        results = _make_results(
            delta_defocus_tilt=0.0,
            delta_half_astigmatism=0.0,
            delta_astigmatism_angle=0.0,
            score_history=[1.0, 1.0, 1.0],
        )
        options = _default_options()
        warnings = check_convergence_health(results, options)
        assert warnings == []

    def test_delta_df_100_no_warning(self) -> None:
        """Negative control: delta_df=100A is well below the 2000A threshold."""
        results = _make_results(delta_defocus_tilt=100.0)
        options = _default_options()
        warnings = check_convergence_health(results, options)
        # No defocus warning expected
        assert not any("defocus correction" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Tests: check_convergence_health — score decrease warning
# ---------------------------------------------------------------------------


class TestScoreDecreaseWarning:
    """Check (a): score decreased between first and last iteration."""

    def test_score_decrease_flagged(self) -> None:
        """Score going down triggers a warning."""
        results = _make_results(score_history=[1.0, 0.8, 0.5])
        options = _default_options()
        warnings = check_convergence_health(results, options)
        assert any("score decreased" in w.lower() for w in warnings)

    def test_score_increase_not_flagged(self) -> None:
        """Negative control: improving score never triggers the warning."""
        results = _make_results(score_history=[1.0, 2.0])
        options = _default_options()
        warnings = check_convergence_health(results, options)
        assert not any("score decreased" in w.lower() for w in warnings)

    def test_single_score_no_warning(self) -> None:
        """Single-element score history cannot have a decrease."""
        results = _make_results(score_history=[1.0])
        options = _default_options()
        warnings = check_convergence_health(results, options)
        assert not any("score decreased" in w.lower() for w in warnings)

    def test_empty_score_history_no_warning(self) -> None:
        """Empty score history produces no score-related warning."""
        results = _make_results(score_history=[])
        options = _default_options()
        warnings = check_convergence_health(results, options)
        assert not any("score decreased" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Tests: check_convergence_health — large defocus correction
# ---------------------------------------------------------------------------


class TestLargeDefocusWarning:
    """Check (b): abs(delta_defocus_tilt) >= 2000 A."""

    def test_delta_df_2000_flagged(self) -> None:
        """Exactly 2000A triggers the warning."""
        results = _make_results(delta_defocus_tilt=2000.0)
        options = _default_options()
        warnings = check_convergence_health(results, options)
        assert any("defocus correction" in w.lower() for w in warnings)

    def test_delta_df_negative_2500_flagged(self) -> None:
        """Negative delta with abs >= 2000A triggers the warning."""
        results = _make_results(delta_defocus_tilt=-2500.0)
        options = _default_options()
        warnings = check_convergence_health(results, options)
        assert any("defocus correction" in w.lower() for w in warnings)

    def test_delta_df_1999_not_flagged(self) -> None:
        """Just below 2000A does not trigger."""
        results = _make_results(delta_defocus_tilt=1999.0)
        options = _default_options()
        warnings = check_convergence_health(results, options)
        assert not any("defocus correction" in w.lower() for w in warnings)

    def test_delta_df_100_not_flagged(self) -> None:
        """Acceptance criterion: delta_df=100A → empty list for this check."""
        results = _make_results(delta_defocus_tilt=100.0)
        options = _default_options()
        warnings = check_convergence_health(results, options)
        assert not any("defocus correction" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Tests: check_convergence_health — parameter saturation
# ---------------------------------------------------------------------------


class TestParameterSaturation:
    """Check (c): parameter at >= 99% of search range bound."""

    def test_defocus_saturated(self) -> None:
        """delta_df at 99% of range triggers saturation warning."""
        results = _make_results(delta_defocus_tilt=4950.0)
        options = _default_options(defocus_search_range=5000.0)
        warnings = check_convergence_health(results, options)
        assert any("defocus at search bound" in w.lower() for w in warnings)

    def test_half_astig_saturated(self) -> None:
        """delta_half_astig at 99% of range/2 triggers saturation."""
        # range/2 = 2500, 99% = 2475
        results = _make_results(delta_half_astigmatism=2475.0)
        options = _default_options(defocus_search_range=5000.0)
        warnings = check_convergence_health(results, options)
        assert any("half-astigmatism at search bound" in w.lower() for w in warnings)

    def test_angle_saturated(self) -> None:
        """delta_angle at 99% of 45 degrees triggers saturation."""
        # 99% of 45 deg = 44.55 deg
        angle_rad = np.radians(44.55)
        results = _make_results(delta_astigmatism_angle=angle_rad)
        options = _default_options()
        warnings = check_convergence_health(results, options)
        assert any("astigmatism angle at search bound" in w.lower() for w in warnings)

    def test_no_saturation_below_threshold(self) -> None:
        """Small parameters produce no saturation warnings."""
        results = _make_results(
            delta_defocus_tilt=100.0,
            delta_half_astigmatism=50.0,
            delta_astigmatism_angle=0.1,
        )
        options = _default_options(defocus_search_range=5000.0)
        warnings = check_convergence_health(results, options)
        assert not any("search bound" in w.lower() for w in warnings)

    def test_negative_saturated_defocus(self) -> None:
        """Negative saturated defocus also triggers."""
        results = _make_results(delta_defocus_tilt=-4950.0)
        options = _default_options(defocus_search_range=5000.0)
        warnings = check_convergence_health(results, options)
        assert any("defocus at search bound" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Tests: check_convergence_health — multiple warnings
# ---------------------------------------------------------------------------


class TestMultipleWarnings:
    """Multiple issues can be flagged simultaneously."""

    def test_all_three_checks_triggered(self) -> None:
        """Score decrease + large defocus + saturation all at once."""
        results = _make_results(
            delta_defocus_tilt=4950.0,
            score_history=[2.0, 1.0],
        )
        options = _default_options(defocus_search_range=5000.0)
        warnings = check_convergence_health(results, options)
        # Should have score decrease, large defocus, and saturation
        assert any("score decreased" in w.lower() for w in warnings)
        assert any("defocus correction" in w.lower() for w in warnings)
        assert any("defocus at search bound" in w.lower() for w in warnings)
        assert len(warnings) >= 3


# ---------------------------------------------------------------------------
# Tests: check_convergence_health — pipeline integration
# ---------------------------------------------------------------------------


class TestConvergenceHealthReturnValues:
    """Verify check_convergence_health returns correct warning strings."""

    def test_warnings_returned_for_unhealthy_tilt(self) -> None:
        """Unhealthy tilt returns warning strings; caller is responsible for logging."""
        results = _make_results(delta_defocus_tilt=3000.0)
        options = _default_options()
        warnings = check_convergence_health(results, options)
        # The function itself returns strings; logging is done by the caller.
        # Verify the function returns the right warnings.
        assert any("defocus correction" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Tests: Debug mode filtering — unprocessed particle occupancy
# ---------------------------------------------------------------------------


_PIXEL_SIZE = 1.5
_VOLTAGE_KV = 300.0
_CS_MM = 2.7
_AMP_CONTRAST = 0.07
_DF1 = 20000.0
_DF2 = 19000.0
_DF_ANGLE = 45.0
_TILT_ANGLE = 10.0
_TILE_SIZE = 32
_REF_VOL_SIZE = 32


def _make_particle(
    position: int,
    tilt_name: str = "tilt_001.mrc",
    tilt_angle: float = _TILT_ANGLE,
    occupancy: float = 75.0,
) -> dict:
    """Create a particle dict with specified occupancy."""
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
        "occupancy": occupancy,
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


class TestDebugTiltListOccupancy:
    """Verify unprocessed particles retain original occupancy when using debug_tilt_list."""

    @pytest.fixture
    def two_tilt_star(self, tmp_path: Path) -> Path:
        """Create a star file with 2 tilt groups (3 particles each)."""
        from ...ctf.star_io.emc_star_parser import write_star_file

        particles = []
        for i in range(3):
            particles.append(
                _make_particle(i + 1, tilt_name="tilt_001.mrc", occupancy=75.0)
            )
        for i in range(3):
            particles.append(
                _make_particle(i + 4, tilt_name="tilt_002.mrc", occupancy=50.0)
            )
        path = tmp_path / "two_tilts.star"
        write_star_file(path, particles, _star_header_lines())
        return path

    @pytest.fixture
    def stack_6slices(self, tmp_path: Path) -> Path:
        """Create an MRC stack with 6 slices."""
        path = tmp_path / "stack.mrc"
        rng = np.random.default_rng(42)
        data = rng.standard_normal((6, _TILE_SIZE, _TILE_SIZE)).astype(np.float32)
        with mrcfile.new(str(path), overwrite=True) as mrc:
            mrc.set_data(data)
        return path

    @pytest.fixture
    def ref_volume(self, tmp_path: Path) -> Path:
        """Create a 3D MRC reference volume."""
        path = tmp_path / "ref_vol.mrc"
        nv = _REF_VOL_SIZE
        volume = np.random.default_rng(42).standard_normal(
            (nv, nv, nv)
        ).astype(np.float32)
        with mrcfile.new(str(path), overwrite=True) as mrc:
            mrc.set_data(volume)
        return path

    def test_unprocessed_particles_retain_occupancy(
        self,
        two_tilt_star: Path,
        stack_6slices: Path,
        ref_volume: Path,
        tmp_path: Path,
    ) -> None:
        """Filter to tilt_001; tilt_002 particles retain occupancy=50.0.

        When debug_tilt_list filters to tilt_001 only, tilt_002 particles
        retain their original occupancy (50.0), NOT set to 100.
        """
        from ...ctf.star_io.emc_star_parser import parse_star_file
        from ..emc_ctf_refine_pipeline import refine_ctf_from_star

        output_path = tmp_path / "filtered.star"
        options = PipelineOptions(
            debug_tilt_list="tilt_001.mrc",
            maximum_iterations=2,
        )

        result = refine_ctf_from_star(
            two_tilt_star, stack_6slices, ref_volume, output_path,
            options=options,
        )

        # Only tilt_001 should be processed
        assert result.n_tilt_groups == 1
        assert result.n_particles_processed == 3

        # Read back the output
        out_particles, _ = parse_star_file(output_path)
        assert len(out_particles) == 6

        # tilt_002 particles should retain original occupancy
        tilt_002_particles = [
            p for p in out_particles
            if p["original_image_filename"] == "tilt_002.mrc"
        ]
        for p in tilt_002_particles:
            assert p["occupancy"] == 50.0, (
                f"Unprocessed particle should retain occupancy=50.0, "
                f"got {p['occupancy']}"
            )

        # tilt_001 particles should have occupancy=100.0 (refined)
        tilt_001_particles = [
            p for p in out_particles
            if p["original_image_filename"] == "tilt_001.mrc"
        ]
        for p in tilt_001_particles:
            assert p["occupancy"] == 100.0

    def test_exit_after_n_tilts_preserves_occupancy(
        self,
        two_tilt_star: Path,
        stack_6slices: Path,
        ref_volume: Path,
        tmp_path: Path,
    ) -> None:
        """exit_after_n_tilts=1 processes only 1 group; other retains occupancy."""
        from ...ctf.star_io.emc_star_parser import parse_star_file
        from ..emc_ctf_refine_pipeline import refine_ctf_from_star

        output_path = tmp_path / "limited.star"
        options = PipelineOptions(
            exit_after_n_tilts=1,
            maximum_iterations=2,
        )

        result = refine_ctf_from_star(
            two_tilt_star, stack_6slices, ref_volume, output_path,
            options=options,
        )

        assert result.n_tilt_groups == 1

        # Build tilt-name → original occupancy map from the input star file
        in_particles, _ = parse_star_file(two_tilt_star)
        original_occupancy: dict[str, float] = {
            p["original_image_filename"]: p["occupancy"] for p in in_particles
        }

        out_particles, _ = parse_star_file(output_path)
        assert len(out_particles) == 6

        # The processed group's particles get occupancy=100
        processed_tilt = result.tilt_group_results[0].tilt_name
        processed_particles = [
            p for p in out_particles
            if p["original_image_filename"] == processed_tilt
        ]
        for p in processed_particles:
            assert p["occupancy"] == 100.0

        # The unprocessed group retains its original occupancy (keyed by tilt name)
        unprocessed_particles = [
            p for p in out_particles
            if p["original_image_filename"] != processed_tilt
        ]
        for p in unprocessed_particles:
            tilt_name = p["original_image_filename"]
            expected = original_occupancy[tilt_name]
            assert p["occupancy"] == expected, (
                f"Unprocessed particle should retain original occupancy={expected}, "
                f"got {p['occupancy']}"
            )
