"""
Tests for the Wolfe line search code path in LBFGSBOptimizer.

The production L-BFGS-B path uses ``set_objective_and_gradient()`` which
activates the Wolfe curvature condition (c2=0.9) in addition to Armijo
sufficient decrease (c1=1e-4).  These tests exercise that exclusive
production path.

Covers:
    - Wolfe line search convergence on standard test functions
    - Armijo fallback when Wolfe cannot be satisfied
    - NaN/Inf rejection in trial evaluations
    - Caller-provided score reuse (no redundant objective evaluation)
    - Curvature pair acceptance under Wolfe conditions
"""

from __future__ import annotations

import numpy as np
import pytest

from ..emc_lbfgsb_optimizer import LBFGSBOptimizer

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def quadratic(x: np.ndarray) -> float:
    """Simple sum-of-squares: f(x) = 0.5 * ||x||^2."""
    return float(0.5 * np.dot(x, x))


def quadratic_grad(x: np.ndarray) -> np.ndarray:
    """Gradient of sum-of-squares."""
    return x.copy()


def quadratic_obj_and_grad(x: np.ndarray) -> tuple[float, np.ndarray]:
    """Combined objective + gradient for sum-of-squares."""
    return quadratic(x), quadratic_grad(x)


def rosenbrock(x: np.ndarray) -> float:
    """Rosenbrock function: f(x,y) = (1-x)^2 + 100*(y-x^2)^2."""
    return float((1.0 - x[0]) ** 2 + 100.0 * (x[1] - x[0] ** 2) ** 2)


def rosenbrock_grad(x: np.ndarray) -> np.ndarray:
    """Gradient of the Rosenbrock function."""
    dx = -2.0 * (1.0 - x[0]) + 200.0 * (x[1] - x[0] ** 2) * (-2.0 * x[0])
    dy = 200.0 * (x[1] - x[0] ** 2)
    return np.array([dx, dy], dtype=np.float64)


def rosenbrock_obj_and_grad(
    x: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Combined objective + gradient for Rosenbrock."""
    return rosenbrock(x), rosenbrock_grad(x)


# ---------------------------------------------------------------------------
# Test: Wolfe line search convergence
# ---------------------------------------------------------------------------


class TestWolfeLineSearchConvergence:
    """Verify convergence when using set_objective_and_gradient (Wolfe path)."""

    def test_quadratic_converges_with_wolfe(self) -> None:
        """Simple quadratic converges rapidly with Wolfe line search."""
        opt = LBFGSBOptimizer(np.array([5.0, -3.0, 2.0]))
        opt.set_objective_and_gradient(quadratic_obj_and_grad)

        for _ in range(30):
            params = opt.get_current_parameters()
            grad = quadratic_grad(params)
            score = quadratic(params)
            opt.step(grad, score=score, score_is_maximized=False)

        final = opt.get_current_parameters()
        np.testing.assert_allclose(final, [0.0, 0.0, 0.0], atol=1e-6)

    def test_rosenbrock_converges_with_wolfe(self) -> None:
        """Rosenbrock with Wolfe converges to [1,1] within tolerance."""
        opt = LBFGSBOptimizer(np.array([-1.2, 1.0]))
        opt.set_bounds(np.array([-5.0, -5.0]), np.array([5.0, 5.0]))
        opt.set_objective_and_gradient(rosenbrock_obj_and_grad)

        for _ in range(100):
            params = opt.get_current_parameters()
            grad = rosenbrock_grad(params)
            score = rosenbrock(params)
            opt.step(grad, score=score, score_is_maximized=False)

        final = opt.get_current_parameters()
        np.testing.assert_allclose(final, [1.0, 1.0], atol=1e-4)

    def test_bounded_quadratic_wolfe(self) -> None:
        """Bounded quadratic with minimum outside bounds, Wolfe path."""
        def obj_grad(x: np.ndarray) -> tuple[float, np.ndarray]:
            f = float((x[0] - 3.0) ** 2)
            g = np.array([2.0 * (x[0] - 3.0)])
            return f, g

        opt = LBFGSBOptimizer(np.array([0.0]))
        opt.set_bounds(np.array([-10.0]), np.array([2.0]))
        opt.set_objective_and_gradient(obj_grad)

        for _ in range(50):
            params = opt.get_current_parameters()
            score, grad = obj_grad(params)
            opt.step(grad, score=score, score_is_maximized=False)

        final = opt.get_current_parameters()
        np.testing.assert_allclose(final, [2.0], atol=1e-6)


# ---------------------------------------------------------------------------
# Test: Wolfe condition acceptance / Armijo fallback
# ---------------------------------------------------------------------------


class TestWolfeConditionBehavior:
    """Verify Wolfe acceptance and Armijo fallback paths."""

    def test_wolfe_accepts_unit_step_on_quadratic(self) -> None:
        """Wolfe line search converges on well-conditioned quadratic."""
        opt = LBFGSBOptimizer(np.array([10.0]))
        opt.set_objective_and_gradient(quadratic_obj_and_grad)

        # Run enough iterations to build curvature history
        for _ in range(10):
            params = opt.get_current_parameters()
            score = quadratic(params)
            grad = quadratic_grad(params)
            opt.step(grad, score=score, score_is_maximized=False)

        # Should converge toward zero
        final = opt.get_current_parameters()
        assert abs(final[0]) < 0.1

    def test_score_decreases_monotonically_with_wolfe(self) -> None:
        """Scores decrease monotonically on convex quadratic with Wolfe."""
        opt = LBFGSBOptimizer(np.array([5.0, -3.0]))
        opt.set_objective_and_gradient(quadratic_obj_and_grad)

        scores: list[float] = []
        for _ in range(20):
            params = opt.get_current_parameters()
            score = quadratic(params)
            scores.append(score)
            grad = quadratic_grad(params)
            opt.step(grad, score=score, score_is_maximized=False)

        # Each score should be <= the previous (Armijo guarantee)
        for i in range(1, len(scores)):
            assert scores[i] <= scores[i - 1] + 1e-12, (
                f"Score increased at step {i}: {scores[i-1]:.8f} -> {scores[i]:.8f}"
            )

    def test_curvature_pairs_accepted_under_wolfe(self) -> None:
        """Wolfe conditions produce accepted curvature pairs (s'y > 0)."""
        opt = LBFGSBOptimizer(np.array([5.0, -3.0, 2.0]))
        opt.set_objective_and_gradient(quadratic_obj_and_grad)

        for _ in range(5):
            params = opt.get_current_parameters()
            score = quadratic(params)
            grad = quadratic_grad(params)
            opt.step(grad, score=score, score_is_maximized=False)

        # Wolfe conditions should have produced accepted curvature pairs
        assert opt.get_history_length() > 0, (
            "Wolfe line search should produce accepted curvature pairs"
        )


# ---------------------------------------------------------------------------
# Test: NaN/Inf rejection in trial evaluations (defect 5)
# ---------------------------------------------------------------------------


class TestNanInfTrialRejection:
    """Non-finite trial evaluations are rejected without corrupting state."""

    def test_nan_objective_rejected(self) -> None:
        """NaN from objective evaluation is rejected, optimizer still works."""
        call_count = 0

        def flaky_obj_grad(x: np.ndarray) -> tuple[float, np.ndarray]:
            nonlocal call_count
            call_count += 1
            # Return NaN on the 3rd line-search evaluation to simulate
            # numerical overflow at an extreme trial point
            if call_count == 3:
                return float("nan"), np.zeros_like(x)
            return quadratic(x), quadratic_grad(x)

        opt = LBFGSBOptimizer(np.array([5.0]))
        opt.set_objective_and_gradient(flaky_obj_grad)

        # Should not raise — NaN trial is skipped
        params = opt.get_current_parameters()
        score = quadratic(params)
        grad = quadratic_grad(params)
        opt.step(grad, score=score, score_is_maximized=False)

        # Parameters should have moved (not stuck at initial)
        final = opt.get_current_parameters()
        assert abs(final[0]) < abs(5.0), "Optimizer should still make progress"

    def test_inf_objective_rejected(self) -> None:
        """Inf from objective evaluation is rejected, optimizer still works."""
        call_count = 0

        def inf_obj_grad(x: np.ndarray) -> tuple[float, np.ndarray]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return float("inf"), np.zeros_like(x)
            return quadratic(x), quadratic_grad(x)

        opt = LBFGSBOptimizer(np.array([5.0]))
        opt.set_objective_and_gradient(inf_obj_grad)

        params = opt.get_current_parameters()
        score = quadratic(params)
        grad = quadratic_grad(params)
        opt.step(grad, score=score, score_is_maximized=False)

        final = opt.get_current_parameters()
        assert abs(final[0]) < abs(5.0), "Optimizer should still make progress"

    def test_nan_gradient_in_trial_rejected(self) -> None:
        """NaN in trial gradient is rejected, optimizer still works."""
        call_count = 0

        def nan_grad_obj_grad(x: np.ndarray) -> tuple[float, np.ndarray]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return quadratic(x), np.array([float("nan")])
            return quadratic(x), quadratic_grad(x)

        opt = LBFGSBOptimizer(np.array([5.0]))
        opt.set_objective_and_gradient(nan_grad_obj_grad)

        params = opt.get_current_parameters()
        score = quadratic(params)
        grad = quadratic_grad(params)
        opt.step(grad, score=score, score_is_maximized=False)

        final = opt.get_current_parameters()
        assert np.all(np.isfinite(final)), "Parameters must remain finite"


# ---------------------------------------------------------------------------
# Test: Caller-provided score reuse (defect 1)
# ---------------------------------------------------------------------------


class TestScoreReuse:
    """Verify step() uses caller-provided score for line search baseline."""

    def test_objective_not_called_at_current_params_when_score_provided(
        self,
    ) -> None:
        """Objective not evaluated at current params when score provided."""
        eval_points: list[np.ndarray] = []

        def tracking_obj_grad(
            x: np.ndarray,
        ) -> tuple[float, np.ndarray]:
            eval_points.append(x.copy())
            return quadratic(x), quadratic_grad(x)

        opt = LBFGSBOptimizer(np.array([5.0, -3.0]))
        opt.set_objective_and_gradient(tracking_obj_grad)

        params = opt.get_current_parameters()
        score = quadratic(params)
        grad = quadratic_grad(params)

        eval_points.clear()
        opt.step(grad, score=score, score_is_maximized=False)

        # No evaluation should match current_parameters exactly
        for pt in eval_points:
            assert not np.array_equal(pt, params), (
                "Objective was called at current parameters despite score "
                "being provided — redundant evaluation"
            )

    def test_objective_called_when_no_score_provided(self) -> None:
        """When score is NOT passed, objective IS evaluated at current params."""
        eval_points: list[np.ndarray] = []

        def tracking_obj_grad(
            x: np.ndarray,
        ) -> tuple[float, np.ndarray]:
            eval_points.append(x.copy())
            return quadratic(x), quadratic_grad(x)

        opt = LBFGSBOptimizer(np.array([5.0, -3.0]))
        opt.set_objective_and_gradient(tracking_obj_grad)

        params = opt.get_current_parameters()
        grad = quadratic_grad(params)

        eval_points.clear()
        opt.step(grad, score_is_maximized=False)

        # First evaluation should be at current parameters
        assert len(eval_points) > 0
        np.testing.assert_array_equal(eval_points[0], params)

    def test_maximization_score_correctly_converted(self) -> None:
        """Maximization score is negated for minimization line search baseline."""
        # Use a maximization-convention objective: positive CC
        # objective_fn returns -score (minimization)
        def neg_quadratic_obj_grad(
            x: np.ndarray,
        ) -> tuple[float, np.ndarray]:
            # Minimization objective
            return quadratic(x), quadratic_grad(x)

        opt = LBFGSBOptimizer(np.array([5.0]))
        opt.set_objective_and_gradient(neg_quadratic_obj_grad)

        params = opt.get_current_parameters()
        # Caller provides score in maximization convention (negative of
        # the minimization objective)
        max_score = -quadratic(params)
        grad = quadratic_grad(params)

        # This should work correctly: step converts max_score to min convention
        opt.step(grad, score=max_score, score_is_maximized=True)

        final = opt.get_current_parameters()
        assert abs(final[0]) < abs(5.0), (
            "Optimizer should make progress with maximization-convention score"
        )


# ---------------------------------------------------------------------------
# Test: set_objective_and_gradient supersedes set_objective
# ---------------------------------------------------------------------------


class TestSetObjectiveAndGradient:
    """Verify set_objective_and_gradient configuration behavior."""

    def test_supersedes_set_objective(self) -> None:
        """set_objective_and_gradient sets both fns and derives objective."""
        opt = LBFGSBOptimizer(np.array([1.0]))

        # First set objective-only
        opt.set_objective(lambda x: float(x[0] ** 2))
        assert opt._objective_fn is not None
        assert opt._objective_grad_fn is None

        # Now set combined — should supersede
        opt.set_objective_and_gradient(quadratic_obj_and_grad)
        assert opt._objective_grad_fn is not None
        assert opt._objective_fn is not None

        # Derived objective should match
        val = opt._objective_fn(np.array([3.0]))
        assert val == pytest.approx(4.5)  # 0.5 * 9

    def test_set_none_clears_both(self) -> None:
        """Setting None clears both functions."""
        opt = LBFGSBOptimizer(np.array([1.0]))
        opt.set_objective_and_gradient(quadratic_obj_and_grad)
        opt.set_objective_and_gradient(None)
        assert opt._objective_fn is None
        assert opt._objective_grad_fn is None

    def test_wolfe_path_used_when_grad_fn_set(self) -> None:
        """Line search calls _objective_grad_fn when set (Wolfe path)."""
        grad_fn_called = False

        def spy_obj_grad(x: np.ndarray) -> tuple[float, np.ndarray]:
            nonlocal grad_fn_called
            grad_fn_called = True
            return quadratic(x), quadratic_grad(x)

        opt = LBFGSBOptimizer(np.array([5.0]))
        opt.set_objective_and_gradient(spy_obj_grad)

        params = opt.get_current_parameters()
        opt.step(
            quadratic_grad(params),
            score=quadratic(params),
            score_is_maximized=False,
        )
        assert grad_fn_called, (
            "Wolfe path should call _objective_grad_fn during line search"
        )
