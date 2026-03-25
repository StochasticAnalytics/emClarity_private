"""Tests for diagnostic output and occupancy update in the CTF refinement pipeline.

Tests:
- Occupancy column set to 100.0 for refined particles (MATLAB line 429)
- Diagnostic file written with correct 16-column tab-delimited format
- Saturation flags computed correctly at 0.99 * bound threshold
- Score change percentage calculated per MATLAB convention
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ..emc_ctf_refine_pipeline import (
    TiltGroupResult,
    _apply_refinement_to_particles,
    _write_diagnostics,
)
from ..emc_refine_tilt_ctf import RefinementResults

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PIXEL_SIZE = 1.5
_TILT_ANGLE = 10.0


def _make_particle(position: int, occupancy: float = 100.0) -> dict:
    """Create a particle dict with specified occupancy."""
    return {
        "position_in_stack": position,
        "psi": 0.0,
        "theta": 0.0,
        "phi": 0.0,
        "x_shift": 0.0,
        "y_shift": 0.0,
        "defocus_1": 20000.0,
        "defocus_2": 19000.0,
        "defocus_angle": 45.0,
        "phase_shift": 0.0,
        "occupancy": occupancy,
        "logp": 0.0,
        "sigma": 1.0,
        "score": 0.0,
        "score_change": 0.0,
        "pixel_size": _PIXEL_SIZE,
        "voltage_kv": 300.0,
        "cs_mm": 2.7,
        "amplitude_contrast": 0.07,
        "beam_tilt_x": 0.0,
        "beam_tilt_y": 0.0,
        "image_shift_x": 0.0,
        "image_shift_y": 0.0,
        "best_2d_class": 1,
        "beam_tilt_group": 1,
        "particle_group": 1,
        "pre_exposure": 0.0,
        "total_exposure": 50.0,
        "original_image_filename": "tilt_001.mrc",
        "tilt_angle": _TILT_ANGLE,
    }


def _make_results(n: int, **kwargs) -> RefinementResults:
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


def _make_tilt_group_result(
    n_particles: int = 5,
    tilt_name: str = "tilt_001.mrc",
    tilt_angle: float = 10.0,
    **results_kwargs,
) -> TiltGroupResult:
    """Create a TiltGroupResult with mock refinement data."""
    rr = _make_results(n_particles, **results_kwargs)
    return TiltGroupResult(
        tilt_name=tilt_name,
        tilt_angle=tilt_angle,
        n_particles=n_particles,
        n_iterations=len(rr.score_history),
        converged=rr.converged,
        mean_score=float(np.mean(rr.per_particle_scores)),
        refinement_results=rr,
    )


# ---------------------------------------------------------------------------
# Tests: Occupancy update
# ---------------------------------------------------------------------------


class TestOccupancyUpdate:
    """Verify occupancy is set to 100.0 for all refined particles."""

    def test_occupancy_50_updated_to_100(self) -> None:
        """Particles with occupancy=50.0 are updated to 100.0 after refinement.

        Positive control: occupancy changes from a non-100 value.
        """
        particles = [_make_particle(i + 1, occupancy=50.0) for i in range(3)]
        results = _make_results(3)

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        for p in particles:
            assert p["occupancy"] == 100.0, (
                f"Expected occupancy=100.0, got {p['occupancy']}"
            )

    def test_occupancy_already_100_stays_100(self) -> None:
        """Particles with occupancy=100.0 remain at 100.0.

        Negative control: verifies no regression for already-100 particles.
        """
        particles = [_make_particle(1, occupancy=100.0)]
        results = _make_results(1)

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        assert particles[0]["occupancy"] == 100.0

    def test_occupancy_zero_updated_to_100(self) -> None:
        """Particles with occupancy=0.0 are updated to 100.0."""
        particles = [_make_particle(1, occupancy=0.0)]
        results = _make_results(1)

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        assert particles[0]["occupancy"] == 100.0

    def test_multiple_particles_mixed_occupancy(self) -> None:
        """All particles get occupancy=100.0 regardless of initial value."""
        occupancies = [0.0, 25.0, 50.0, 75.0, 100.0]
        particles = [
            _make_particle(i + 1, occupancy=occ)
            for i, occ in enumerate(occupancies)
        ]
        results = _make_results(len(particles))

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        for p in particles:
            assert p["occupancy"] == 100.0


# ---------------------------------------------------------------------------
# Tests: Diagnostic file output
# ---------------------------------------------------------------------------


class TestDiagnosticFileOutput:
    """Verify diagnostic file format and content."""

    def test_diagnostics_file_created(self, tmp_path: Path) -> None:
        """Diagnostic file is created alongside the output star file."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")  # create dummy star file

        tgr = _make_tilt_group_result()
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        assert diag_path.exists()
        assert diag_path.name == "output_diagnostics.txt"

    def test_diagnostics_has_16_column_header(self, tmp_path: Path) -> None:
        """Header line has exactly 16 tab-separated column names."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        tgr = _make_tilt_group_result()
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        header_cols = lines[0].split("\t")
        assert len(header_cols) == 16, (
            f"Expected 16 columns, got {len(header_cols)}: {header_cols}"
        )

    def test_diagnostics_expected_column_names(self, tmp_path: Path) -> None:
        """Header column names match the specification."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        tgr = _make_tilt_group_result()
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        header_cols = lines[0].split("\t")
        expected = [
            "tilt_name", "tilt_angle", "n_particles", "n_iters", "converged",
            "delta_df", "delta_astig", "delta_angle_deg",
            "score_mean", "score_std", "score_min", "score_max",
            "score_change_pct", "df_sat", "astig_sat", "angle_sat",
        ]
        assert header_cols == expected

    def test_diagnostics_data_row_has_16_columns(self, tmp_path: Path) -> None:
        """Each data row has exactly 16 tab-separated values."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        tgr = _make_tilt_group_result()
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        assert len(lines) == 2  # header + 1 data row
        data_cols = lines[1].split("\t")
        assert len(data_cols) == 16

    def test_diagnostics_tilt_name_and_angle(self, tmp_path: Path) -> None:
        """Tilt name and angle are correctly written."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        tgr = _make_tilt_group_result(tilt_name="my_tilt.mrc", tilt_angle=25.5)
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        cols = lines[1].split("\t")
        assert cols[0] == "my_tilt.mrc"
        assert float(cols[1]) == pytest.approx(25.5, abs=0.01)

    def test_diagnostics_score_statistics(self, tmp_path: Path) -> None:
        """Score statistics (mean, std, min, max) are computed from per-particle scores."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        scores = np.array([0.7, 0.8, 0.9, 1.0, 0.6])
        tgr = _make_tilt_group_result(
            n_particles=5,
            per_particle_scores=scores,
        )
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        cols = lines[1].split("\t")
        # cols 8-11: score_mean, score_std, score_min, score_max
        assert float(cols[8]) == pytest.approx(np.mean(scores), abs=1e-5)
        assert float(cols[9]) == pytest.approx(np.std(scores, ddof=1), abs=1e-5)
        assert float(cols[10]) == pytest.approx(0.6, abs=1e-5)
        assert float(cols[11]) == pytest.approx(1.0, abs=1e-5)

    def test_diagnostics_multiple_tilt_groups(self, tmp_path: Path) -> None:
        """Multiple tilt groups produce multiple data rows."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        tgrs = [
            _make_tilt_group_result(tilt_name=f"tilt_{i:03d}.mrc")
            for i in range(3)
        ]
        diag_path = _write_diagnostics(star_path, tgrs, 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        assert len(lines) == 4  # header + 3 data rows
        for i, line in enumerate(lines[1:]):
            cols = line.split("\t")
            assert cols[0] == f"tilt_{i:03d}.mrc"


# ---------------------------------------------------------------------------
# Tests: Saturation detection
# ---------------------------------------------------------------------------


class TestSaturationDetection:
    """Verify saturation flags are set correctly at the 0.99 * bound threshold."""

    def test_df_saturation_at_bound(self, tmp_path: Path) -> None:
        """Defocus saturation flag is 1 when abs(delta_df) >= 0.99 * range."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        # delta_defocus_tilt = 4950 = 0.99 * 5000 → saturated
        tgr = _make_tilt_group_result(delta_defocus_tilt=4950.0)
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        cols = lines[1].split("\t")
        assert cols[13] == "1", f"Expected df_sat=1, got {cols[13]}"

    def test_df_no_saturation_below_bound(self, tmp_path: Path) -> None:
        """Defocus saturation flag is 0 when abs(delta_df) < 0.99 * range."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        # delta_defocus_tilt = 100 << 0.99 * 5000 → not saturated
        tgr = _make_tilt_group_result(delta_defocus_tilt=100.0)
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        cols = lines[1].split("\t")
        assert cols[13] == "0", f"Expected df_sat=0, got {cols[13]}"

    def test_astig_saturation_at_half_range(self, tmp_path: Path) -> None:
        """Astigmatism saturation uses range/2 as bound.

        For defocus_search_range=5000, astig bound = 2500, threshold = 2475.
        """
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        # delta_half_astigmatism = 2475 = 0.99 * 2500 → saturated
        tgr = _make_tilt_group_result(delta_half_astigmatism=2475.0)
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        cols = lines[1].split("\t")
        assert cols[14] == "1", f"Expected astig_sat=1, got {cols[14]}"

    def test_astig_no_saturation_below_half_range(self, tmp_path: Path) -> None:
        """Astigmatism saturation flag is 0 below threshold."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        tgr = _make_tilt_group_result(delta_half_astigmatism=50.0)
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        cols = lines[1].split("\t")
        assert cols[14] == "0"

    def test_angle_saturation_at_45_degrees(self, tmp_path: Path) -> None:
        """Angle saturation flag is 1 when abs(delta_angle) >= 0.99 * 45 deg.

        delta_astigmatism_angle is in radians; 0.99 * 45 deg = 44.55 deg ~ 0.7775 rad.
        """
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        # 44.55 degrees in radians
        angle_rad = np.radians(44.55)
        tgr = _make_tilt_group_result(delta_astigmatism_angle=angle_rad)
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        cols = lines[1].split("\t")
        assert cols[15] == "1", f"Expected angle_sat=1, got {cols[15]}"

    def test_angle_no_saturation_below_45_degrees(self, tmp_path: Path) -> None:
        """Angle saturation flag is 0 when below threshold."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        tgr = _make_tilt_group_result(delta_astigmatism_angle=0.1)
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        cols = lines[1].split("\t")
        assert cols[15] == "0"

    def test_negative_delta_triggers_saturation(self, tmp_path: Path) -> None:
        """Saturation detection uses abs() — negative deltas also saturate."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        tgr = _make_tilt_group_result(delta_defocus_tilt=-4950.0)
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        cols = lines[1].split("\t")
        assert cols[13] == "1", "Negative delta should also trigger saturation"


# ---------------------------------------------------------------------------
# Tests: Score change percentage
# ---------------------------------------------------------------------------


class TestScoreChangePercentage:
    """Verify score_change_pct follows MATLAB convention: (final-init)/final * 100."""

    def test_positive_score_improvement(self, tmp_path: Path) -> None:
        """Score improvement produces positive percentage."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        # score_history = [5.0, 7.5, 10.0] for 5 particles
        # s_init = 5.0/5 = 1.0, s_final = 10.0/5 = 2.0
        # change = 100 * (2.0 - 1.0) / 2.0 = 50.0%
        tgr = _make_tilt_group_result(
            n_particles=5,
            score_history=[5.0, 7.5, 10.0],
        )
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        cols = lines[1].split("\t")
        assert float(cols[12]) == pytest.approx(50.0, abs=0.1)

    def test_no_change_produces_zero(self, tmp_path: Path) -> None:
        """No score change produces 0.0%."""
        star_path = tmp_path / "output.star"
        star_path.write_text("")

        tgr = _make_tilt_group_result(
            n_particles=5,
            score_history=[5.0, 5.0, 5.0],
        )
        diag_path = _write_diagnostics(star_path, [tgr], 5000.0)

        lines = diag_path.read_text().strip().split("\n")
        cols = lines[1].split("\t")
        assert float(cols[12]) == pytest.approx(0.0, abs=0.1)
