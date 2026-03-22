"""Tests for the NaN-sentinel guard in _apply_refinement_to_particles.

The guard at the end of the per-particle loop preserves the original
``score`` value when ``per_particle_scores[i]`` is NaN.  NaN is the
sentinel emitted by the refinement engine when ``maximum_iterations=0``
(i.e. a no-op run), signalling that no real refinement was performed and
the existing score must be kept.

Positive control  — score is a real float:   score IS overwritten.
Negative control  — score is NaN:            score is NOT overwritten.
Mixed control     — some NaN, some real:     only real-score particles update.
"""

from __future__ import annotations

import numpy as np
import pytest

from ..emc_ctf_refine_pipeline import _apply_refinement_to_particles
from ..emc_refine_tilt_ctf import RefinementResults

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_PIXEL_SIZE = 1.5   # Angstroms
_TILT_ANGLE = 10.0  # degrees
_ORIGINAL_SCORE = 0.42


def _make_particle(position: int = 1) -> dict:
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
        "occupancy": 100.0,
        "logp": 0.0,
        "sigma": 1.0,
        "score": _ORIGINAL_SCORE,
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


def _make_results(scores: np.ndarray) -> RefinementResults:
    n = len(scores)
    return RefinementResults(
        delta_defocus_tilt=0.0,
        delta_half_astigmatism=0.0,
        delta_astigmatism_angle=0.0,
        delta_z=np.zeros(n),
        shift_x=np.zeros(n),
        shift_y=np.zeros(n),
        per_particle_scores=scores,
        score_history=[],
        converged=True,
    )


# ---------------------------------------------------------------------------
# Positive control: real score IS written
# ---------------------------------------------------------------------------


class TestNaNSentinelPositiveControl:
    """Verify that a real (non-NaN) score overwrites the original value."""

    def test_real_score_overwrites(self) -> None:
        """When per_particle_scores[i] is a real float, p['score'] is updated."""
        particles = [_make_particle(1)]
        results = _make_results(np.array([0.99]))

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        assert particles[0]["score"] == pytest.approx(0.99)
        assert particles[0]["score"] != _ORIGINAL_SCORE


# ---------------------------------------------------------------------------
# Negative control: NaN sentinel preserves original score
# ---------------------------------------------------------------------------


class TestNaNSentinelNegativeControl:
    """Verify that a NaN score does NOT overwrite the original value."""

    def test_nan_score_preserves_original(self) -> None:
        """When per_particle_scores[i] is NaN, p['score'] keeps its old value."""
        particles = [_make_particle(1)]
        results = _make_results(np.array([float("nan")]))

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        assert particles[0]["score"] == pytest.approx(_ORIGINAL_SCORE)

    def test_all_nan_scores_all_preserved(self) -> None:
        """All-NaN score array leaves all original scores unchanged."""
        n = 4
        particles = [_make_particle(i + 1) for i in range(n)]
        results = _make_results(np.full(n, float("nan")))

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        for p in particles:
            assert p["score"] == pytest.approx(_ORIGINAL_SCORE)


# ---------------------------------------------------------------------------
# Mixed control: some NaN, some real — partial update
# ---------------------------------------------------------------------------


class TestNaNSentinelMixedControl:
    """Verify that only non-NaN scores overwrite; NaN entries are skipped."""

    def test_mixed_scores_partial_update(self) -> None:
        """Real scores overwrite; NaN scores are skipped."""
        particles = [_make_particle(i + 1) for i in range(4)]
        # particle 0, 2: real scores; particles 1, 3: NaN sentinels
        scores = np.array([0.80, float("nan"), 0.60, float("nan")])
        results = _make_results(scores)

        _apply_refinement_to_particles(
            particles, results, tilt_angle=_TILT_ANGLE, pixel_size=_PIXEL_SIZE,
        )

        assert particles[0]["score"] == pytest.approx(0.80)
        assert particles[1]["score"] == pytest.approx(_ORIGINAL_SCORE)
        assert particles[2]["score"] == pytest.approx(0.60)
        assert particles[3]["score"] == pytest.approx(_ORIGINAL_SCORE)
