"""
Tests for LBFGSBOptimizer.

Validates the from-scratch L-BFGS-B implementation against acceptance
criteria covering convergence on standard test functions, bound handling,
parameter freezing/unfreezing, curvature rejection, and interface
compatibility with the OptimizerBase ABC.
"""

from __future__ import annotations

import numpy as np
import pytest

from ..emc_adam_optimizer import AdamOptimizer
from ..emc_lbfgsb_optimizer import LBFGSBOptimizer
from ..emc_optimizer_base import OptimizerBase

# ---------------------------------------------------------------------------
# Helper functions: test objectives and gradients
# ---------------------------------------------------------------------------


def rosenbrock(x: np.ndarray) -> float:
    """Rosenbrock function: f(x,y) = (1-x)^2 + 100*(y-x^2)^2."""
    return float((1.0 - x[0]) ** 2 + 100.0 * (x[1] - x[0] ** 2) ** 2)


def rosenbrock_grad(x: np.ndarray) -> np.ndarray:
    """Gradient of the Rosenbrock function."""
    dx = -2.0 * (1.0 - x[0]) + 200.0 * (x[1] - x[0] ** 2) * (-2.0 * x[0])
    dy = 200.0 * (x[1] - x[0] ** 2)
    return np.array([dx, dy], dtype=np.float64)


# ---------------------------------------------------------------------------
# Test: Abstract base class contract
# ---------------------------------------------------------------------------


class TestOptimizerBaseInterface:
    """Verify LBFGSBOptimizer satisfies the OptimizerBase interface."""

    def test_is_subclass_of_base(self) -> None:
        assert issubclass(LBFGSBOptimizer, OptimizerBase)

    def test_is_instance_of_base(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0]))
        assert isinstance(opt, OptimizerBase)

    def test_has_step_method(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0]))
        assert callable(getattr(opt, "step", None))

    def test_has_has_converged_method(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0]))
        assert callable(getattr(opt, "has_converged", None))

    def test_has_get_current_parameters_method(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0]))
        assert callable(getattr(opt, "get_current_parameters", None))

    def test_has_freeze_parameters_method(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0]))
        assert callable(getattr(opt, "freeze_parameters", None))

    def test_has_unfreeze_parameters_method(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0]))
        assert callable(getattr(opt, "unfreeze_parameters", None))

    def test_has_set_bounds_method(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0]))
        assert callable(getattr(opt, "set_bounds", None))

    def test_has_get_score_history_method(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0]))
        assert callable(getattr(opt, "get_score_history", None))

    def test_drop_in_replacement_step_signature(self) -> None:
        """step() accepts same args as AdamOptimizer.step()."""
        opt = LBFGSBOptimizer(np.array([1.0, 2.0]))
        # gradient only
        opt.step(np.array([0.1, 0.2]), score_is_maximized=True)
        # gradient + score
        opt.step(np.array([0.1, 0.2]), score=1.0, score_is_maximized=True)


# ---------------------------------------------------------------------------
# Test: Constructor validation
# ---------------------------------------------------------------------------


class TestConstructor:
    """Constructor validation and initialization."""

    def test_empty_array_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            LBFGSBOptimizer(np.array([]))

    def test_valid_initialization(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0, 2.0, 3.0]))
        np.testing.assert_array_equal(opt.get_current_parameters(), [1.0, 2.0, 3.0])

    def test_initial_params_are_copied(self) -> None:
        arr = np.array([1.0, 2.0])
        opt = LBFGSBOptimizer(arr)
        arr[0] = 999.0
        assert opt.get_current_parameters()[0] == 1.0

    def test_2d_input_is_flattened(self) -> None:
        opt = LBFGSBOptimizer(np.array([[1.0, 2.0], [3.0, 4.0]]))
        assert opt.get_current_parameters().shape == (4,)

    def test_memory_size_default(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0]))
        assert opt.get_memory_size() == 20

    def test_custom_memory_size(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0]), memory_size=3)
        assert opt.get_memory_size() == 3

    def test_memory_size_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="memory_size"):
            LBFGSBOptimizer(np.array([1.0]), memory_size=0)

    def test_memory_size_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="memory_size"):
            LBFGSBOptimizer(np.array([1.0]), memory_size=-1)


# ---------------------------------------------------------------------------
# Test: NaN/Inf gradient handling
# ---------------------------------------------------------------------------


class TestGradientValidation:
    """Negative control: invalid gradients must raise ValueError."""

    def test_nan_gradient_raises(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0, 2.0]))
        with pytest.raises(ValueError, match="NaN"):
            opt.step(np.array([np.nan, 0.5]), score_is_maximized=True)

    def test_inf_gradient_raises(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0]))
        with pytest.raises(ValueError, match="Inf"):
            opt.step(np.array([np.inf]), score_is_maximized=True)

    def test_length_mismatch_raises(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0, 2.0]))
        with pytest.raises(ValueError, match="Gradient length"):
            opt.step(np.array([1.0]), score_is_maximized=True)

    def test_parameters_unchanged_after_nan(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0, 2.0]))
        initial = opt.get_current_parameters().copy()
        with pytest.raises(ValueError):
            opt.step(np.array([np.nan, 0.5]), score_is_maximized=True)
        np.testing.assert_array_equal(opt.get_current_parameters(), initial)


# ---------------------------------------------------------------------------
# Test: Rosenbrock convergence
# Acceptance criterion: x0=[-1.2, 1], bounds [-5,5]^2, converge to [1,1]
#   within 1e-4 in <100 iterations.
# ---------------------------------------------------------------------------


class TestRosenbrockConvergence:
    """L-BFGS-B on the Rosenbrock function with box constraints."""

    def test_converges_to_minimum(self) -> None:
        opt = LBFGSBOptimizer(np.array([-1.2, 1.0]))
        opt.set_bounds(np.array([-5.0, -5.0]), np.array([5.0, 5.0]))
        opt.set_objective(rosenbrock)

        for _ in range(100):
            params = opt.get_current_parameters()
            grad = rosenbrock_grad(params)
            score = rosenbrock(params)
            opt.step(grad, score=score, score_is_maximized=False)

        final = opt.get_current_parameters()
        np.testing.assert_allclose(final, [1.0, 1.0], atol=1e-4)

    def test_score_decreases(self) -> None:
        """Final score is much smaller than initial."""
        opt = LBFGSBOptimizer(np.array([-1.2, 1.0]))
        opt.set_bounds(np.array([-5.0, -5.0]), np.array([5.0, 5.0]))
        opt.set_objective(rosenbrock)

        for _ in range(100):
            params = opt.get_current_parameters()
            grad = rosenbrock_grad(params)
            score = rosenbrock(params)
            # Rosenbrock is a minimisation objective, not a maximisation score
            opt.step(grad, score=score, score_is_maximized=False)

        history = opt.get_score_history()
        assert history[-1] < history[0] * 0.001


# ---------------------------------------------------------------------------
# Test: Bounded quadratic
# Acceptance criterion: f=(x-3)^2, bounds [-10, 2], solution at x=2
#   within 1e-6.
# ---------------------------------------------------------------------------


class TestBoundedQuadratic:
    """Bounded quadratic: minimum outside bounds, solution at bound."""

    def test_converges_to_bound(self) -> None:
        def f(x: np.ndarray) -> float:
            return float((x[0] - 3.0) ** 2)

        opt = LBFGSBOptimizer(np.array([0.0]))
        opt.set_bounds(np.array([-10.0]), np.array([2.0]))
        opt.set_objective(f)

        for _ in range(50):
            params = opt.get_current_parameters()
            grad = np.array([2.0 * (params[0] - 3.0)])
            score = f(params)
            opt.step(grad, score=score, score_is_maximized=False)

        final = opt.get_current_parameters()
        np.testing.assert_allclose(final, [2.0], atol=1e-6)

    def test_respects_bounds(self) -> None:
        """Parameters never exceed bounds during optimization."""
        def f(x: np.ndarray) -> float:
            return float((x[0] - 3.0) ** 2)

        opt = LBFGSBOptimizer(np.array([0.0]))
        opt.set_bounds(np.array([-10.0]), np.array([2.0]))
        opt.set_objective(f)

        for _ in range(50):
            params = opt.get_current_parameters()
            grad = np.array([2.0 * (params[0] - 3.0)])
            opt.step(grad, score=f(params), score_is_maximized=False)
            current = opt.get_current_parameters()
            assert current[0] >= -10.0
            assert current[0] <= 2.0


# ---------------------------------------------------------------------------
# Test: 50-dim bounded random quadratic
# Acceptance criterion: random quadratic with mixed active/inactive
#   constraints, max error < 1e-4.
# ---------------------------------------------------------------------------


class TestHighDimBounded:
    """50-dim bounded random quadratic with mixed constraint activity."""

    def test_converges_within_tolerance(self) -> None:
        rng = np.random.default_rng(42)
        n = 50

        # Random positive-definite quadratic: f = sum(a_i * (x_i - b_i)^2)
        a = rng.uniform(1.0, 10.0, size=n)
        b = rng.uniform(-5.0, 5.0, size=n)

        # Bounds: some will be active (b outside bounds), some inactive
        lower = rng.uniform(-8.0, -2.0, size=n)
        upper = rng.uniform(2.0, 8.0, size=n)

        # Expected solution: clamp b to bounds
        expected = np.clip(b, lower, upper)

        def f(x: np.ndarray) -> float:
            return float(np.sum(a * (x - b) ** 2))

        def grad_f(x: np.ndarray) -> np.ndarray:
            return 2.0 * a * (x - b)

        x0 = np.clip(rng.uniform(-3.0, 3.0, size=n), lower, upper)
        opt = LBFGSBOptimizer(x0, memory_size=7)
        opt.set_bounds(lower, upper)
        opt.set_objective(f)

        for _ in range(200):
            params = opt.get_current_parameters()
            opt.step(grad_f(params), score=f(params), score_is_maximized=False)

        final = opt.get_current_parameters()
        max_error = float(np.max(np.abs(final - expected)))
        assert max_error < 1e-4, f"Max error {max_error} exceeds tolerance"


# ---------------------------------------------------------------------------
# Test: Freeze/Unfreeze
# Acceptance criterion: 5-dim, freeze dims 3:4, run 50 iters, unfreeze,
#   run 50 — frozen params unchanged, all converge after unfreeze,
#   L-BFGS history cleared on unfreeze.
# ---------------------------------------------------------------------------


class TestFreezeUnfreeze:
    """Parameter freezing and unfreezing with history reset."""

    def test_frozen_params_unchanged(self) -> None:
        """Frozen dimensions do not change during optimization."""
        n = 5
        a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        b = np.array([1.0, 1.0, 1.0, 1.0, 1.0])

        def f(x: np.ndarray) -> float:
            return float(np.sum(a * (x - b) ** 2))

        def grad_f(x: np.ndarray) -> np.ndarray:
            return 2.0 * a * (x - b)

        x0 = np.zeros(n)
        opt = LBFGSBOptimizer(x0)
        opt.set_bounds(-5.0 * np.ones(n), 5.0 * np.ones(n))
        opt.set_objective(f)

        # Freeze dims 3 and 4
        opt.freeze_parameters(np.array([3, 4]))
        frozen_vals = opt.get_current_parameters()[[3, 4]].copy()

        for _ in range(50):
            params = opt.get_current_parameters()
            opt.step(grad_f(params), score=f(params), score_is_maximized=False)

        after_frozen = opt.get_current_parameters()
        np.testing.assert_array_equal(after_frozen[[3, 4]], frozen_vals)

    def test_unfrozen_dims_move(self) -> None:
        """Non-frozen dimensions move toward the minimum."""
        n = 5
        a = np.ones(n)
        b = np.ones(n)

        def f(x: np.ndarray) -> float:
            return float(np.sum(a * (x - b) ** 2))

        def grad_f(x: np.ndarray) -> np.ndarray:
            return 2.0 * a * (x - b)

        x0 = np.zeros(n)
        opt = LBFGSBOptimizer(x0)
        opt.set_bounds(-5.0 * np.ones(n), 5.0 * np.ones(n))
        opt.set_objective(f)

        opt.freeze_parameters(np.array([3, 4]))

        for _ in range(50):
            params = opt.get_current_parameters()
            opt.step(grad_f(params), score=f(params), score_is_maximized=False)

        after_frozen = opt.get_current_parameters()
        # Dims 0,1,2 should have moved toward 1.0
        for i in [0, 1, 2]:
            assert abs(after_frozen[i] - 1.0) < abs(x0[i] - 1.0), \
                f"Dim {i} should move toward minimum"

    def test_all_converge_after_unfreeze(self) -> None:
        """After unfreeze, all dimensions converge to minimum."""
        n = 5
        a = np.ones(n)
        b = np.ones(n)

        def f(x: np.ndarray) -> float:
            return float(np.sum(a * (x - b) ** 2))

        def grad_f(x: np.ndarray) -> np.ndarray:
            return 2.0 * a * (x - b)

        x0 = np.zeros(n)
        opt = LBFGSBOptimizer(x0)
        opt.set_bounds(-5.0 * np.ones(n), 5.0 * np.ones(n))
        opt.set_objective(f)

        opt.freeze_parameters(np.array([3, 4]))

        for _ in range(50):
            params = opt.get_current_parameters()
            opt.step(grad_f(params), score=f(params), score_is_maximized=False)

        # Unfreeze and continue
        opt.unfreeze_parameters(np.array([3, 4]))

        for _ in range(50):
            params = opt.get_current_parameters()
            opt.step(grad_f(params), score=f(params), score_is_maximized=False)

        final = opt.get_current_parameters()
        np.testing.assert_allclose(final, b, atol=1e-3)

    def test_history_cleared_on_unfreeze(self) -> None:
        """L-BFGS history is cleared when parameters are unfrozen."""
        n = 5
        opt = LBFGSBOptimizer(np.zeros(n))
        opt.set_bounds(-5.0 * np.ones(n), 5.0 * np.ones(n))

        # Build some history
        for i in range(5):
            grad = np.random.default_rng(i).standard_normal(n)
            opt.step(grad, score_is_maximized=True)

        assert opt.get_history_length() > 0

        # Unfreeze clears history
        opt.freeze_parameters(np.array([0]))
        opt.unfreeze_parameters(np.array([0]))

        assert opt.get_history_length() == 0


# ---------------------------------------------------------------------------
# Test: H_0 initialization after unfreeze
# Acceptance criterion: H_0[i,i] = (upper[i] - lower[i])^2 / (4 * n_params)
# ---------------------------------------------------------------------------


class TestH0Initialization:
    """H0 uses identity when no curvature history, gamma_k scaling otherwise.

    Bounds-based H0 diagonal was removed in TASK-002b.  After unfreeze
    (which clears history), H0 is identity.  The two-loop recursion
    applies gamma_k = (s'y)/(y'y) * I once curvature pairs are available.
    """

    def test_h0_returns_none_after_unfreeze(self) -> None:
        """get_h0_diagonal returns None (no explicit diagonal override)."""
        n = 5
        lower = np.array([-5.0, -3.0, -1.0, 0.0, -10.0])
        upper = np.array([5.0, 3.0, 1.0, 2.0, 10.0])

        opt = LBFGSBOptimizer(np.zeros(n))
        opt.set_bounds(lower, upper)

        # Freeze and unfreeze
        opt.freeze_parameters(np.array([0]))
        opt.unfreeze_parameters(np.array([0]))

        assert opt.get_h0_diagonal() is None

    def test_h0_none_without_bounds(self) -> None:
        """H_0 diagonal is None regardless of bounds."""
        opt = LBFGSBOptimizer(np.array([1.0, 2.0]))
        opt.freeze_parameters(np.array([0]))
        opt.unfreeze_parameters(np.array([0]))
        assert opt.get_h0_diagonal() is None

    def test_convergence_after_unfreeze_uses_identity_then_gamma(self) -> None:
        """Optimizer converges after unfreeze using identity H0 then gamma_k scaling."""
        n = 3
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([1.0, 1.0, 1.0])

        def f(x: np.ndarray) -> float:
            return float(np.sum(a * (x - b) ** 2))

        def grad_f(x: np.ndarray) -> np.ndarray:
            return 2.0 * a * (x - b)

        opt = LBFGSBOptimizer(np.zeros(n))
        opt.set_bounds(-5.0 * np.ones(n), 5.0 * np.ones(n))
        opt.set_objective(f)

        # Freeze, run, unfreeze, continue — should still converge
        opt.freeze_parameters(np.array([2]))
        for _ in range(20):
            params = opt.get_current_parameters()
            opt.step(grad_f(params), score=f(params), score_is_maximized=False)

        opt.unfreeze_parameters(np.array([2]))
        for _ in range(30):
            params = opt.get_current_parameters()
            opt.step(grad_f(params), score=f(params), score_is_maximized=False)

        final = opt.get_current_parameters()
        np.testing.assert_allclose(final, b, atol=1e-3)


# ---------------------------------------------------------------------------
# Test: Curvature rejection
# Acceptance criterion: f=|x-2| (non-smooth) converges to x=2 without
#   diverging.
# ---------------------------------------------------------------------------


class TestCurvatureRejection:
    """Curvature pair rejection on non-smooth objective."""

    def test_abs_value_convergence(self) -> None:
        """F = |x - 2| converges toward x=2 without diverging."""
        def f(x: np.ndarray) -> float:
            return float(np.abs(x[0] - 2.0))

        def grad_f(x: np.ndarray) -> np.ndarray:
            d = x[0] - 2.0
            if abs(d) < 1e-12:
                return np.array([0.0])
            return np.array([1.0 if d > 0 else -1.0])

        opt = LBFGSBOptimizer(np.array([0.0]))
        opt.set_bounds(np.array([-10.0]), np.array([10.0]))
        opt.set_objective(f)

        initial_score = f(opt.get_current_parameters())

        for _ in range(100):
            params = opt.get_current_parameters()
            score = f(params)
            opt.step(grad_f(params), score=score, score_is_maximized=False)

        final = opt.get_current_parameters()
        final_score = f(final)

        # Should converge toward x=2 (not diverge)
        assert final_score < initial_score, \
            "Score should decrease, not diverge"
        assert abs(final[0] - 2.0) < 1.0, \
            f"Should converge near x=2, got {final[0]}"

    def test_does_not_diverge(self) -> None:
        """Parameters stay bounded throughout optimization."""
        def f(x: np.ndarray) -> float:
            return float(np.abs(x[0] - 2.0))

        def grad_f(x: np.ndarray) -> np.ndarray:
            d = x[0] - 2.0
            if abs(d) < 1e-12:
                return np.array([0.0])
            return np.array([1.0 if d > 0 else -1.0])

        opt = LBFGSBOptimizer(np.array([0.0]))
        opt.set_bounds(np.array([-10.0]), np.array([10.0]))
        opt.set_objective(f)

        for _ in range(100):
            params = opt.get_current_parameters()
            opt.step(grad_f(params), score=f(params), score_is_maximized=False)
            current = opt.get_current_parameters()
            assert -10.0 <= current[0] <= 10.0


# ---------------------------------------------------------------------------
# Test: Anisotropic scaling
# Acceptance criterion: 2D quadratic with eigenvalues [1, 10000]
#   converges in <50 iterations.
# ---------------------------------------------------------------------------


class TestAnisotropicScaling:
    """L-BFGS-B adapts to highly anisotropic curvature."""

    def test_ill_conditioned_quadratic(self) -> None:
        """Converges in <50 iters despite condition number 10000."""
        eigenvalues = np.array([1.0, 10000.0])
        minimum = np.array([3.0, -2.0])

        def f(x: np.ndarray) -> float:
            d = x - minimum
            return float(0.5 * np.dot(eigenvalues * d, d))

        def grad_f(x: np.ndarray) -> np.ndarray:
            return eigenvalues * (x - minimum)

        x0 = np.array([0.0, 0.0])
        opt = LBFGSBOptimizer(x0)
        opt.set_objective(f)

        for _i in range(50):
            params = opt.get_current_parameters()
            opt.step(grad_f(params), score=f(params), score_is_maximized=False)

        final = opt.get_current_parameters()
        np.testing.assert_allclose(final, minimum, atol=1e-4)


# ---------------------------------------------------------------------------
# Test: has_converged matches AdamOptimizer
# Acceptance criterion: identical behavior on same score histories.
# ---------------------------------------------------------------------------


class TestHasConvergedMatchesAdam:
    """has_converged produces identical results to AdamOptimizer."""

    @pytest.mark.parametrize("scores,n_lookback,threshold,expected", [
        # Converged: last 3 scores close to baseline
        ([10.0, 10.005, 10.003, 10.004], 3, 0.001, True),
        # Not converged: large changes
        ([10.0, 8.0, 7.0, 6.0], 3, 0.001, False),
        # Insufficient scores
        ([10.0, 9.5], 3, 0.001, False),
        # Zero baseline
        ([0.0, 0.0001, 0.0001, 0.0001], 3, 0.001, False),
        # Converged with default params
        ([100.0, 100.0, 100.05, 100.03, 100.04], 3, 0.001, True),
        # Above threshold: max_change = 0.02/10 = 0.002 > 0.001
        ([10.0, 10.02, 10.02, 10.02], 3, 0.001, False),
    ])
    def test_matches_adam(
        self,
        scores: list[float],
        n_lookback: int,
        threshold: float,
        expected: bool,
    ) -> None:
        """Both optimizers return the same convergence result."""
        adam = AdamOptimizer(np.array([0.0]))
        lbfgsb = LBFGSBOptimizer(np.array([0.0]))

        for s in scores:
            adam.step(np.array([0.0]), score=s, score_is_maximized=True)
            lbfgsb.step(np.array([0.0]), score=s, score_is_maximized=True)

        adam_result = adam.has_converged(n_lookback, threshold)
        lbfgsb_result = lbfgsb.has_converged(n_lookback, threshold)

        assert adam_result == lbfgsb_result == expected

    def test_n_lookback_zero_raises(self) -> None:
        """Negative control: n_lookback=0 raises ValueError."""
        opt = LBFGSBOptimizer(np.array([0.0]))
        with pytest.raises(ValueError, match="n_lookback"):
            opt.has_converged(n_lookback=0)


# ---------------------------------------------------------------------------
# Test: Bounds clamping
# ---------------------------------------------------------------------------


class TestBoundsClamping:
    """Bounds are clamped immediately and respected during optimization."""

    def test_clamp_on_set(self) -> None:
        opt = LBFGSBOptimizer(np.array([5.0, -3.0]))
        opt.set_bounds(np.array([0.0, 0.0]), np.array([2.0, 2.0]))
        np.testing.assert_array_equal(opt.get_current_parameters(), [2.0, 0.0])

    def test_length_mismatch_raises(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0, 2.0]))
        with pytest.raises(ValueError):
            opt.set_bounds(np.array([0.0]), np.array([1.0, 2.0]))

    def test_inf_bounds_unconstrained(self) -> None:
        opt = LBFGSBOptimizer(np.array([0.0]))
        opt.set_bounds(np.array([-np.inf]), np.array([np.inf]))
        opt.step(np.array([1.0]), score_is_maximized=True)
        assert opt.get_current_parameters()[0] != 0.0


# ---------------------------------------------------------------------------
# Test: Score history
# ---------------------------------------------------------------------------


class TestScoreHistory:
    """Score recording through step()."""

    def test_scores_recorded(self) -> None:
        opt = LBFGSBOptimizer(np.array([0.0]))
        # Pass score_is_maximized=False since these are raw test values,
        # not maximisation scores — stored as-is.
        opt.step(np.array([1.0]), score=10.0, score_is_maximized=False)
        opt.step(np.array([1.0]), score=5.0, score_is_maximized=False)
        assert opt.get_score_history() == [10.0, 5.0]

    def test_no_score_not_recorded(self) -> None:
        opt = LBFGSBOptimizer(np.array([0.0]))
        opt.step(np.array([1.0]), score_is_maximized=True)
        opt.step(np.array([1.0]), score=5.0, score_is_maximized=False)
        opt.step(np.array([1.0]), score_is_maximized=True)
        assert opt.get_score_history() == [5.0]

    def test_history_is_copy(self) -> None:
        opt = LBFGSBOptimizer(np.array([0.0]))
        opt.step(np.array([1.0]), score=5.0, score_is_maximized=True)
        history = opt.get_score_history()
        history.append(999.0)
        assert len(opt.get_score_history()) == 1


# ---------------------------------------------------------------------------
# Test: Return value isolation
# ---------------------------------------------------------------------------


class TestReturnValueIsolation:
    """Returned arrays are copies, not references to internal state."""

    def test_parameter_mutation_safe(self) -> None:
        opt = LBFGSBOptimizer(np.array([1.0, 2.0]))
        params = opt.get_current_parameters()
        params[0] = 999.0
        assert opt.get_current_parameters()[0] == 1.0

    def test_h0_diagonal_returns_none(self) -> None:
        """get_h0_diagonal returns None (no bounds-based H₀ after TASK-002b)."""
        opt = LBFGSBOptimizer(np.array([1.0, 2.0]))
        opt.set_bounds(np.array([-5.0, -5.0]), np.array([5.0, 5.0]))
        opt.freeze_parameters(np.array([0]))
        opt.unfreeze_parameters(np.array([0]))
        assert opt.get_h0_diagonal() is None


# ---------------------------------------------------------------------------
# Test: Accessors
# ---------------------------------------------------------------------------


class TestAccessors:
    """Verify accessor methods return correct values."""

    def test_timestep_increments(self) -> None:
        opt = LBFGSBOptimizer(np.array([0.0]))
        assert opt.get_timestep() == 0
        opt.step(np.array([1.0]), score_is_maximized=True)
        assert opt.get_timestep() == 1
        opt.step(np.array([1.0]), score_is_maximized=True)
        assert opt.get_timestep() == 2

    def test_history_length(self) -> None:
        opt = LBFGSBOptimizer(np.array([0.0, 0.0]))
        assert opt.get_history_length() == 0

    def test_history_bounded_by_memory(self) -> None:
        """History length does not exceed memory_size."""
        opt = LBFGSBOptimizer(np.array([0.0]), memory_size=3)
        opt.set_objective(lambda x: float(x[0] ** 2))
        for _i in range(20):
            x = opt.get_current_parameters()
            opt.step(np.array([2.0 * x[0]]), score=float(x[0] ** 2), score_is_maximized=False)
        assert opt.get_history_length() <= 3
