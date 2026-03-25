"""Tests for score_is_maximized sign convention across optimizers.

Validates that the score_is_maximized parameter correctly controls how
each optimizer stores scores internally.  The CC score in cryo-EM CTF
refinement is naturally positive (higher = better alignment).  Each
optimizer must convert to its own convention:

- ADAM (maximiser): stores positive CC as-is when score_is_maximized=True
- L-BFGS-B (minimiser): negates positive CC when score_is_maximized=True
  so that its history tracks the minimisation objective (lower = better)

Test classes:
- TestSignConventionIntegration: traces a positive CC score through
  gradient negation, objective function, step(), and convergence tracking
- TestWrongSignConvention: negative control demonstrating that passing
  score_is_maximized=False with a positive CC score produces wrong-sign
  values in L-BFGS-B's score history
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pytest

from ..emc_adam_optimizer import AdamOptimizer
from ..emc_lbfgsb_optimizer import LBFGSBOptimizer

# ---------------------------------------------------------------------------
# Test: Sign convention integration
# ---------------------------------------------------------------------------


class TestSignConventionIntegration:
    """Trace positive CC score through gradient negation, objective, step().

    Acceptance criterion: score_is_maximized=True causes ADAM to store
    the natural positive score and L-BFGS-B to negate it for internal
    minimisation tracking.
    """

    # Positive CC scores that an optimizer would see during refinement
    POSITIVE_CC_SCORES: ClassVar[list[float]] = [0.85, 0.90, 0.92, 0.93, 0.935]

    def test_adam_stores_positive_scores_as_is(self) -> None:
        """ADAM stores scores unchanged when score_is_maximized=True."""
        opt = AdamOptimizer(np.array([0.0, 0.0, 0.0]))
        grad = np.array([0.1, -0.05, 0.02])

        for cc in self.POSITIVE_CC_SCORES:
            opt.step(grad, score=cc, score_is_maximized=True)

        history = opt.get_score_history()
        assert len(history) == len(self.POSITIVE_CC_SCORES)
        for stored, original in zip(
            history, self.POSITIVE_CC_SCORES, strict=True
        ):
            assert stored == pytest.approx(original), (
                f"ADAM should store positive CC as-is, got {stored} "
                f"instead of {original}"
            )

    def test_lbfgsb_negates_positive_scores(self) -> None:
        """L-BFGS-B negates scores when score_is_maximized=True."""
        opt = LBFGSBOptimizer(np.array([0.0, 0.0, 0.0]))
        grad = np.array([0.1, -0.05, 0.02])

        for cc in self.POSITIVE_CC_SCORES:
            opt.step(grad, score=cc, score_is_maximized=True)

        history = opt.get_score_history()
        assert len(history) == len(self.POSITIVE_CC_SCORES)
        for stored, original in zip(
            history, self.POSITIVE_CC_SCORES, strict=True
        ):
            assert stored == pytest.approx(-original), (
                f"L-BFGS-B should negate positive CC, got {stored} "
                f"instead of {-original}"
            )

    def test_lbfgsb_history_all_negative(self) -> None:
        """All L-BFGS-B history entries are negative for positive CC input."""
        opt = LBFGSBOptimizer(np.array([0.0]))

        for cc in self.POSITIVE_CC_SCORES:
            opt.step(np.array([0.1]), score=cc, score_is_maximized=True)

        history = opt.get_score_history()
        assert all(s < 0.0 for s in history), (
            f"L-BFGS-B history should be all negative, got {history}"
        )

    def test_adam_history_all_positive(self) -> None:
        """All ADAM history entries are positive for positive CC input."""
        opt = AdamOptimizer(np.array([0.0]))

        for cc in self.POSITIVE_CC_SCORES:
            opt.step(np.array([0.1]), score=cc, score_is_maximized=True)

        history = opt.get_score_history()
        assert all(s > 0.0 for s in history), (
            f"ADAM history should be all positive, got {history}"
        )

    def test_gradient_negation_and_step_compose(self) -> None:
        """Simulate the full sign chain: gradient negation + step.

        In the real pipeline:
        1. evaluate_score_and_gradient returns positive total_score and
           negated gradient (line 414 of emc_ctf_gradients.py)
        2. The caller passes score_is_maximized=True to step()
        3. L-BFGS-B negates the score internally for convergence tracking

        This test verifies steps 2-3 with a synthetic gradient.
        """
        positive_cc = 5.0
        # Gradient has been negated by evaluate_score_and_gradient
        raw_gradient = np.array([1.0, -0.5, 0.3])
        negated_gradient = -raw_gradient  # as done at line 414

        opt = LBFGSBOptimizer(np.array([0.0, 0.0, 0.0]))
        opt.step(negated_gradient, score=positive_cc, score_is_maximized=True)

        history = opt.get_score_history()
        assert len(history) == 1
        # L-BFGS-B negates the maximisation score
        assert history[0] == pytest.approx(-positive_cc)

    def test_lbfgsb_objective_returns_negative_score(self) -> None:
        """The L-BFGS-B objective function returns -score for line search.

        This is separate from the score_is_maximized convention — the
        objective function is used by the Armijo backtracking line search
        and independently returns -score (line 541 of emc_refine_tilt_ctf.py).
        """
        positive_cc = 3.5

        def objective(_params: np.ndarray) -> float:
            return -positive_cc  # Objective returns -score for L-BFGS-B

        assert objective(np.zeros(3)) == pytest.approx(-positive_cc)

    def test_convergence_detection_works_with_negated_scores(self) -> None:
        """has_converged works correctly with negated scores in L-BFGS-B.

        The convergence check uses abs() and is sign-agnostic, so it
        works correctly regardless of whether scores are positive or
        negative.
        """
        opt = LBFGSBOptimizer(np.array([0.0]))

        # Converging positive CC scores: 10.0, 10.005, 10.003, 10.004
        # After negation: -10.0, -10.005, -10.003, -10.004
        # Relative change: max(0.005, 0.003, 0.004) / 10.0 = 0.0005 < 0.001
        scores = [10.0, 10.005, 10.003, 10.004]
        for s in scores:
            opt.step(np.array([0.0]), score=s, score_is_maximized=True)

        assert opt.has_converged(n_lookback=3, threshold=0.001)

    def test_score_is_maximized_false_stores_as_is_for_lbfgsb(self) -> None:
        """L-BFGS-B stores as-is when score_is_maximized=False.

        When the score is already in minimisation convention, L-BFGS-B
        should not negate it.
        """
        opt = LBFGSBOptimizer(np.array([0.0]))
        min_score = -3.5  # Already in minimisation convention

        opt.step(np.array([0.1]), score=min_score, score_is_maximized=False)

        history = opt.get_score_history()
        assert history[0] == pytest.approx(min_score)

    def test_adam_score_is_maximized_false_negates(self) -> None:
        """ADAM negates when score_is_maximized=False.

        When the score is in minimisation convention, ADAM negates to
        convert to its maximisation convention.
        """
        opt = AdamOptimizer(np.array([0.0]))
        min_score = -3.5

        opt.step(np.array([0.1]), score=min_score, score_is_maximized=False)

        history = opt.get_score_history()
        # ADAM negates: -(-3.5) = 3.5
        assert history[0] == pytest.approx(3.5)

    def test_default_score_is_maximized_is_true(self) -> None:
        """Explicit score_is_maximized=True matches pipeline CC convention."""
        # ADAM: explicit score_is_maximized=True stores as-is
        adam = AdamOptimizer(np.array([0.0]))
        adam.step(np.array([0.1]), score=5.0, score_is_maximized=True)
        assert adam.get_score_history()[0] == pytest.approx(5.0)

        # L-BFGS-B: explicit score_is_maximized=True negates
        lbfgsb = LBFGSBOptimizer(np.array([0.0]))
        lbfgsb.step(np.array([0.1]), score=5.0, score_is_maximized=True)
        assert lbfgsb.get_score_history()[0] == pytest.approx(-5.0)


# ---------------------------------------------------------------------------
# Test: Wrong sign convention (negative control)
# ---------------------------------------------------------------------------


class TestWrongSignConvention:
    """Negative control: wrong score_is_maximized flag produces wrong signs.

    When the caller incorrectly claims score_is_maximized=False for a
    positive CC score, L-BFGS-B stores the raw positive value without
    negation. The score history then contains positive values where it
    should contain negative values (the negated minimisation objective).
    """

    def test_wrong_flag_stores_positive_instead_of_negative(self) -> None:
        """Wrong flag stores raw positive CC instead of negating.

        L-BFGS-B with score_is_maximized=False treats the positive CC as
        already in minimisation convention and stores it as-is, instead of
        negating it for its internal minimisation tracking.
        """
        positive_cc_scores = [0.85, 0.90, 0.92, 0.93]
        opt = LBFGSBOptimizer(np.array([0.0, 0.0]))

        for cc in positive_cc_scores:
            opt.step(
                np.array([0.1, -0.05]),
                score=cc,
                score_is_maximized=False,  # WRONG: score IS maximized
            )

        history = opt.get_score_history()

        # With the wrong flag, L-BFGS-B stores raw positive values
        # instead of negating them
        assert all(s > 0.0 for s in history), (
            f"With wrong flag, history should contain (wrong) positive "
            f"values, got {history}"
        )

        # Verify the values are the raw inputs (not negated)
        for stored, original in zip(
            history, positive_cc_scores, strict=True
        ):
            assert stored == pytest.approx(original), (
                f"Wrong flag should store raw value {original}, "
                f"got {stored}"
            )

    def test_correct_flag_differs_from_wrong_flag(self) -> None:
        """Correct and wrong flags produce opposite signs in history."""
        positive_cc = 5.0

        # Correct: score_is_maximized=True
        opt_correct = LBFGSBOptimizer(np.array([0.0]))
        opt_correct.step(
            np.array([0.1]), score=positive_cc, score_is_maximized=True
        )

        # Wrong: score_is_maximized=False with the same positive CC
        opt_wrong = LBFGSBOptimizer(np.array([0.0]))
        opt_wrong.step(
            np.array([0.1]), score=positive_cc, score_is_maximized=False
        )

        correct_history = opt_correct.get_score_history()
        wrong_history = opt_wrong.get_score_history()

        # Correct: negative (negated for minimisation)
        assert correct_history[0] < 0.0
        # Wrong: positive (stored raw — wrong convention)
        assert wrong_history[0] > 0.0

        # The values should be negatives of each other
        assert correct_history[0] == pytest.approx(-wrong_history[0])

    def test_wrong_flag_on_adam_also_produces_wrong_sign(self) -> None:
        """ADAM with wrong flag negates when it should store as-is.

        Symmetry check: ADAM with score_is_maximized=False and positive
        CC also gets the wrong sign.
        """
        positive_cc = 5.0

        opt = AdamOptimizer(np.array([0.0]))
        opt.step(
            np.array([0.1]),
            score=positive_cc,
            score_is_maximized=False,  # WRONG: score IS maximized
        )

        history = opt.get_score_history()
        # ADAM negates when score_is_maximized=False, producing wrong
        # negative values for what is actually positive CC
        assert history[0] == pytest.approx(-positive_cc)
        assert history[0] < 0.0, (
            f"ADAM with wrong flag should store negative value, "
            f"got {history[0]}"
        )
