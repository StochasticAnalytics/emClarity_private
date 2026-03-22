"""
Tests for AdamOptimizer and OptimizerBase.

Validates the Python port of testScripts/adamOptimizer.m against
hand-computed values and behavioral acceptance criteria. Each test class
addresses a specific acceptance criterion or behavioral contract.
"""

from __future__ import annotations

import numpy as np
import pytest

from ..emc_adam_optimizer import AdamOptimizer
from ..emc_optimizer_base import OptimizerBase

# ---------------------------------------------------------------------------
# Test: Abstract base class contract
# ---------------------------------------------------------------------------


class TestOptimizerBaseInterface:
    """Verify OptimizerBase defines the required abstract interface."""

    def test_cannot_instantiate_abc(self) -> None:
        """OptimizerBase cannot be instantiated directly."""
        with pytest.raises(TypeError):
            OptimizerBase()  # type: ignore[abstract]

    def test_freeze_parameters_is_abstract(self) -> None:
        """Acceptance criterion: freeze_parameters is abstract in OptimizerBase."""
        assert getattr(OptimizerBase.freeze_parameters, "__isabstractmethod__", False)

    def test_unfreeze_parameters_is_abstract(self) -> None:
        """Acceptance criterion: unfreeze_parameters is abstract in OptimizerBase."""
        assert getattr(
            OptimizerBase.unfreeze_parameters, "__isabstractmethod__", False
        )

    def test_step_is_abstract(self) -> None:
        assert getattr(OptimizerBase.step, "__isabstractmethod__", False)

    def test_has_converged_is_abstract(self) -> None:
        assert getattr(OptimizerBase.has_converged, "__isabstractmethod__", False)

    def test_get_current_parameters_is_abstract(self) -> None:
        assert getattr(
            OptimizerBase.get_current_parameters, "__isabstractmethod__", False
        )

    def test_set_bounds_is_not_abstract(self) -> None:
        """set_bounds is concrete in the base class."""
        assert not getattr(OptimizerBase.set_bounds, "__isabstractmethod__", False)

    def test_get_score_history_is_not_abstract(self) -> None:
        """get_score_history is concrete in the base class."""
        assert not getattr(
            OptimizerBase.get_score_history, "__isabstractmethod__", False
        )

    def test_adam_is_subclass_of_base(self) -> None:
        """AdamOptimizer inherits from OptimizerBase."""
        assert issubclass(AdamOptimizer, OptimizerBase)

    def test_adam_is_instance_of_base(self) -> None:
        opt = AdamOptimizer(np.array([1.0]))
        assert isinstance(opt, OptimizerBase)


# ---------------------------------------------------------------------------
# Test: Constructor validation
# ---------------------------------------------------------------------------


class TestConstructor:
    """Constructor validation and initialization."""

    def test_empty_array_raises_value_error(self) -> None:
        """Negative control: empty parameter vector must raise ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            AdamOptimizer(np.array([]))

    def test_empty_list_raises_value_error(self) -> None:
        """Negative control: empty list also raises."""
        with pytest.raises(ValueError, match="non-empty"):
            AdamOptimizer(np.array([], dtype=np.float64))

    def test_valid_initialization(self) -> None:
        """Parameters are stored correctly after construction."""
        opt = AdamOptimizer(np.array([1.0, 2.0, 3.0]))
        params = opt.get_current_parameters()
        np.testing.assert_array_equal(params, [1.0, 2.0, 3.0])

    def test_initial_params_are_copied(self) -> None:
        """Mutating the input array does not affect the optimizer."""
        arr = np.array([1.0, 2.0])
        opt = AdamOptimizer(arr)
        arr[0] = 999.0
        assert opt.get_current_parameters()[0] == 1.0

    def test_scalar_input_becomes_1d(self) -> None:
        """Scalar input is treated as single-parameter vector."""
        opt = AdamOptimizer(np.array([5.0]))
        assert opt.get_current_parameters().shape == (1,)

    def test_2d_input_is_flattened(self) -> None:
        """2D input is flattened to 1D."""
        opt = AdamOptimizer(np.array([[1.0, 2.0], [3.0, 4.0]]))
        assert opt.get_current_parameters().shape == (4,)

    def test_custom_hyperparameters(self) -> None:
        """Custom beta1, beta2, epsilon are accepted."""
        opt = AdamOptimizer(
            np.array([0.0]), beta1=0.8, beta2=0.99, epsilon=1e-7
        )
        assert opt.get_current_parameters()[0] == 0.0


# ---------------------------------------------------------------------------
# Test: NaN gradient handling
# ---------------------------------------------------------------------------


class TestNaNGradient:
    """Negative control: NaN gradients must raise ValueError."""

    def test_nan_gradient_raises(self) -> None:
        opt = AdamOptimizer(np.array([1.0, 2.0]))
        with pytest.raises(ValueError, match="NaN"):
            opt.step(np.array([np.nan, 0.5]))

    def test_all_nan_gradient_raises(self) -> None:
        opt = AdamOptimizer(np.array([1.0]))
        with pytest.raises(ValueError, match="NaN"):
            opt.step(np.array([np.nan]))

    def test_parameters_unchanged_after_nan_rejection(self) -> None:
        """Parameters are not modified when NaN gradient is rejected."""
        opt = AdamOptimizer(np.array([1.0, 2.0]))
        initial = opt.get_current_parameters().copy()
        with pytest.raises(ValueError):
            opt.step(np.array([np.nan, 0.5]))
        np.testing.assert_array_equal(opt.get_current_parameters(), initial)

    def test_timestep_unchanged_after_nan_rejection(self) -> None:
        """Timestep does not increment on rejected NaN gradient."""
        opt = AdamOptimizer(np.array([1.0]))
        with pytest.raises(ValueError):
            opt.step(np.array([np.nan]))
        assert opt.get_timestep() == 0


# ---------------------------------------------------------------------------
# Test: Single ADAM step (hand-computed)
# ---------------------------------------------------------------------------


class TestSingleStep:
    """Verify one ADAM step against hand-computed values.

    For params=[0,0], gradient=[2,-4], alpha=0.001, beta1=0.9, beta2=0.999:

    t=1:
      m = 0.1 * [2, -4] = [0.2, -0.4]
      v = 0.001 * [4, 16] = [0.004, 0.016]
      m_hat = [0.2, -0.4] / 0.1 = [2.0, -4.0]
      v_hat = [0.004, 0.016] / 0.001 = [4.0, 16.0]
      update = 0.001 * [2/-4] / [sqrt(4)+1e-8, sqrt(16)+1e-8]
             = 0.001 * [1.0, -1.0]  (approximately)
      params = [0,0] - [0.001, -0.001] = [-0.001, 0.001]
    """

    def test_first_step_hand_computed(self) -> None:
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        opt.step(np.array([2.0, -4.0]))

        params = opt.get_current_parameters()
        np.testing.assert_allclose(params, [-0.001, 0.001], atol=1e-10)

    def test_timestep_increments(self) -> None:
        opt = AdamOptimizer(np.array([0.0]))
        assert opt.get_timestep() == 0
        opt.step(np.array([1.0]))
        assert opt.get_timestep() == 1
        opt.step(np.array([1.0]))
        assert opt.get_timestep() == 2


# ---------------------------------------------------------------------------
# Test: Quadratic convergence
# ---------------------------------------------------------------------------


class TestQuadraticConvergence:
    """Minimize f(x,y) = (x-3)^2 + (y+2)^2 from [0,0] to [3,-2].

    Acceptance criterion: converge within 0.01 of [3, -2].
    """

    def test_converges_to_minimum(self) -> None:
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        opt.set_alpha(0.05)

        for _ in range(500):
            params = opt.get_current_parameters()
            grad = np.array([
                2.0 * (params[0] - 3.0),
                2.0 * (params[1] + 2.0),
            ])
            opt.step(grad)

        final = opt.get_current_parameters()
        np.testing.assert_allclose(final, [3.0, -2.0], atol=0.01)

    def test_convergence_with_auto_lr(self) -> None:
        """Auto-scaled learning rate also reaches the minimum."""
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        opt.auto_scale_learning_rate(
            expected_range=5.0, n_iterations=500, safety_factor=3.0
        )

        for _ in range(500):
            params = opt.get_current_parameters()
            grad = np.array([
                2.0 * (params[0] - 3.0),
                2.0 * (params[1] + 2.0),
            ])
            opt.step(grad)

        final = opt.get_current_parameters()
        np.testing.assert_allclose(final, [3.0, -2.0], atol=0.01)

    def test_convergence_monotonic_score_decrease(self) -> None:
        """Score generally decreases over optimization (not strictly)."""
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        opt.set_alpha(0.05)

        for _ in range(200):
            params = opt.get_current_parameters()
            grad = np.array([
                2.0 * (params[0] - 3.0),
                2.0 * (params[1] + 2.0),
            ])
            score = (params[0] - 3.0) ** 2 + (params[1] + 2.0) ** 2
            opt.step(grad, score=score)

        history = opt.get_score_history()
        # Final score should be much smaller than initial
        assert history[-1] < history[0] * 0.01


# ---------------------------------------------------------------------------
# Test: Bounds clamping
# ---------------------------------------------------------------------------


class TestBoundsClamping:
    """After set_bounds, parameters never exceed bounds.

    Acceptance criterion: with bounds [0,0]-[2,2], params stay in bounds.
    """

    def test_bounds_clamp_during_step(self) -> None:
        opt = AdamOptimizer(np.array([1.0, 1.0]))
        opt.set_bounds(np.array([0.0, 0.0]), np.array([2.0, 2.0]))
        opt.set_alpha(0.1)

        for _ in range(200):
            params = opt.get_current_parameters()
            # Gradient pointing toward [3, -2] which is outside bounds
            grad = np.array([
                2.0 * (params[0] - 3.0),
                2.0 * (params[1] + 2.0),
            ])
            opt.step(grad)
            current = opt.get_current_parameters()
            assert np.all(current >= 0.0), f"Below lower bound: {current}"
            assert np.all(current <= 2.0), f"Above upper bound: {current}"

    def test_bounds_clamp_on_set(self) -> None:
        """Setting bounds clamps current parameters immediately."""
        opt = AdamOptimizer(np.array([5.0, -3.0]))
        opt.set_bounds(np.array([0.0, 0.0]), np.array([2.0, 2.0]))
        params = opt.get_current_parameters()
        np.testing.assert_array_equal(params, [2.0, 0.0])

    def test_bounds_length_mismatch_raises(self) -> None:
        opt = AdamOptimizer(np.array([1.0, 2.0]))
        with pytest.raises(ValueError):
            opt.set_bounds(np.array([0.0]), np.array([1.0, 2.0]))

    def test_inf_bounds_are_unconstrained(self) -> None:
        """Using inf bounds does not restrict parameters."""
        opt = AdamOptimizer(np.array([0.0]))
        opt.set_bounds(np.array([-np.inf]), np.array([np.inf]))
        opt.set_alpha(1.0)
        opt.step(np.array([1.0]))
        # Parameter should move freely
        assert opt.get_current_parameters()[0] != 0.0


# ---------------------------------------------------------------------------
# Test: Freeze / Unfreeze
# ---------------------------------------------------------------------------


class TestFreezeUnfreeze:
    """Frozen parameters remain unchanged; unfrozen resume moving.

    Acceptance criterion: frozen param does not change after step();
    unfrozen parameters resume moving.
    """

    def test_frozen_parameter_unchanged(self) -> None:
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        opt.set_alpha(0.01)

        # Freeze parameter 0
        opt.freeze_parameters(np.array([0]))

        for _ in range(10):
            opt.step(np.array([1.0, 1.0]))

        params = opt.get_current_parameters()
        assert params[0] == 0.0, "Frozen parameter should not change"
        assert params[1] != 0.0, "Unfrozen parameter should change"

    def test_unfreeze_resumes_movement(self) -> None:
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        opt.set_alpha(0.01)

        # Freeze, step, unfreeze, step
        opt.freeze_parameters(np.array([0]))

        for _ in range(5):
            opt.step(np.array([1.0, 1.0]))

        assert opt.get_current_parameters()[0] == 0.0

        # Unfreeze with default lr
        opt.unfreeze_parameters(np.array([0]))

        for _ in range(5):
            opt.step(np.array([1.0, 1.0]))

        assert opt.get_current_parameters()[0] != 0.0, \
            "Unfrozen parameter should resume moving"

    def test_unfreeze_with_explicit_lr(self) -> None:
        """Unfreeze with explicit learning rate values."""
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        opt.set_alpha(0.01)

        opt.freeze_parameters(np.array([0]))
        opt.unfreeze_parameters(np.array([0]), lr_values=np.array([0.05]))

        lr = opt.get_learning_rates()
        assert lr[0] == 0.05

    def test_freeze_initializes_learning_rates(self) -> None:
        """Freezing before setting per-param LRs initializes them from alpha."""
        opt = AdamOptimizer(np.array([0.0, 0.0, 0.0]))
        opt.set_alpha(0.02)

        opt.freeze_parameters(np.array([1]))

        lr = opt.get_learning_rates()
        assert lr[0] == 0.02
        assert lr[1] == 0.0
        assert lr[2] == 0.02

    def test_multiple_freeze_unfreeze_cycles(self) -> None:
        """Parameters can be frozen and unfrozen repeatedly."""
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        opt.set_alpha(0.01)

        # First freeze/unfreeze cycle
        opt.freeze_parameters(np.array([0]))
        opt.step(np.array([1.0, 1.0]))
        val_after_frozen = opt.get_current_parameters()[0]
        assert val_after_frozen == 0.0

        opt.unfreeze_parameters(np.array([0]))
        opt.step(np.array([1.0, 1.0]))
        val_after_unfreeze = opt.get_current_parameters()[0]
        assert val_after_unfreeze != 0.0

        # Second freeze cycle
        opt.freeze_parameters(np.array([0]))
        opt.step(np.array([1.0, 1.0]))
        val_after_refreeze = opt.get_current_parameters()[0]
        assert val_after_refreeze == val_after_unfreeze


# ---------------------------------------------------------------------------
# Test: AMSGrad
# ---------------------------------------------------------------------------


class TestAMSGrad:
    """AMSGrad ensures monotonically non-decreasing v_hat_max.

    Acceptance criterion: v_hat_max values are monotonically non-decreasing
    across iterations.
    """

    def test_v_hat_max_monotonic(self) -> None:
        opt = AdamOptimizer(np.array([0.0, 0.0, 0.0]))
        opt.set_amsgrad(True)
        opt.set_alpha(0.01)

        rng = np.random.default_rng(42)
        prev_v_hat_max = np.zeros(3)

        for _ in range(50):
            # Varying gradient magnitudes to exercise v_hat_max tracking
            grad = rng.standard_normal(3) * rng.uniform(0.1, 10.0)
            opt.step(grad)

            current_v_hat_max = opt._v_hat_max.copy()
            assert np.all(current_v_hat_max >= prev_v_hat_max - 1e-15), \
                "v_hat_max must be monotonically non-decreasing"
            prev_v_hat_max = current_v_hat_max

    def test_amsgrad_toggle(self) -> None:
        """Can enable and disable AMSGrad."""
        opt = AdamOptimizer(np.array([0.0]))
        opt.set_amsgrad(True)
        assert opt._use_amsgrad is True
        opt.set_amsgrad(False)
        assert opt._use_amsgrad is False

    def test_amsgrad_produces_different_trajectory(self) -> None:
        """AMSGrad and vanilla ADAM diverge with varying gradients."""
        rng = np.random.default_rng(123)
        grads = [rng.standard_normal(2) * rng.uniform(0.5, 5.0) for _ in range(30)]

        opt_vanilla = AdamOptimizer(np.array([0.0, 0.0]))
        opt_vanilla.set_alpha(0.01)

        opt_amsgrad = AdamOptimizer(np.array([0.0, 0.0]))
        opt_amsgrad.set_alpha(0.01)
        opt_amsgrad.set_amsgrad(True)

        for g in grads:
            opt_vanilla.step(g)
            opt_amsgrad.step(g)

        # With varying gradient magnitudes, trajectories should differ
        vanilla_params = opt_vanilla.get_current_parameters()
        amsgrad_params = opt_amsgrad.get_current_parameters()
        assert not np.allclose(vanilla_params, amsgrad_params, atol=1e-10)


# ---------------------------------------------------------------------------
# Test: auto_scale_learning_rate
# ---------------------------------------------------------------------------


class TestAutoScaleLearningRate:
    """Learning rate auto-scaling from expected parameter range.

    Acceptance criterion: for range=10, n_iter=100, safety=3, decay_power=0,
    alpha = safety * range / sum(1/t^0 for t=1..100) = 3 * 10 / 100 = 0.3
    """

    def test_formula_decay_power_zero(self) -> None:
        """step_sum = sum(1) for 100 terms = 100; alpha = 30/100 = 0.3."""
        opt = AdamOptimizer(np.array([0.0]))
        opt.auto_scale_learning_rate(
            expected_range=10.0, n_iterations=100, safety_factor=3.0
        )
        assert abs(opt._alpha - 0.3) < 1e-12

    def test_formula_with_decay_half(self) -> None:
        """With decay_power=0.5, step_sum = sum(1/sqrt(t) for t=1..100)."""
        opt = AdamOptimizer(np.array([0.0]))
        opt.set_lr_decay_power(0.5)
        opt.auto_scale_learning_rate(
            expected_range=10.0, n_iterations=100, safety_factor=3.0
        )
        expected_step_sum = sum(1.0 / (t ** 0.5) for t in range(1, 101))
        expected_alpha = 3.0 * 10.0 / expected_step_sum
        assert abs(opt._alpha - expected_alpha) < 1e-12

    def test_formula_with_decay_one(self) -> None:
        """With decay_power=1.0, step_sum = harmonic series sum(1/t)."""
        opt = AdamOptimizer(np.array([0.0]))
        opt.set_lr_decay_power(1.0)
        opt.auto_scale_learning_rate(
            expected_range=5.0, n_iterations=50, safety_factor=2.0
        )
        expected_step_sum = sum(1.0 / t for t in range(1, 51))
        expected_alpha = 2.0 * 5.0 / expected_step_sum
        assert abs(opt._alpha - expected_alpha) < 1e-12

    def test_per_parameter_range(self) -> None:
        """Vector expected_range sets per-parameter learning rates."""
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        opt.auto_scale_learning_rate(
            expected_range=np.array([10.0, 20.0]),
            n_iterations=100,
            safety_factor=3.0,
        )
        expected_lr = 3.0 * np.array([10.0, 20.0]) / 100.0
        np.testing.assert_allclose(opt._learning_rates, expected_lr, atol=1e-12)

    def test_range_length_mismatch_raises(self) -> None:
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        with pytest.raises(ValueError):
            opt.auto_scale_learning_rate(
                expected_range=np.array([1.0, 2.0, 3.0]),
                n_iterations=100,
            )

    def test_default_safety_factor(self) -> None:
        """Default safety_factor is 3."""
        opt = AdamOptimizer(np.array([0.0]))
        opt.auto_scale_learning_rate(expected_range=10.0, n_iterations=100)
        # 3 * 10 / 100 = 0.3
        assert abs(opt._alpha - 0.3) < 1e-12


# ---------------------------------------------------------------------------
# Test: Score history and convergence
# ---------------------------------------------------------------------------


class TestScoreHistory:
    """Score recording and convergence detection.

    Acceptance criterion: score history records via step(gradient, score);
    has_converged returns True when last 3 scores differ by less than
    0.001 relative.
    """

    def test_score_recorded_via_step(self) -> None:
        opt = AdamOptimizer(np.array([0.0]))
        opt.step(np.array([1.0]), score=10.0)
        opt.step(np.array([1.0]), score=5.0)
        opt.step(np.array([1.0]), score=2.5)

        history = opt.get_score_history()
        assert history == [10.0, 5.0, 2.5]

    def test_no_score_not_recorded(self) -> None:
        """Steps without score don't add to history."""
        opt = AdamOptimizer(np.array([0.0]))
        opt.step(np.array([1.0]))
        opt.step(np.array([1.0]), score=5.0)
        opt.step(np.array([1.0]))

        assert opt.get_score_history() == [5.0]

    def test_has_converged_true(self) -> None:
        """Returns True when last 3 scores differ < 0.001 relative.

        baseline = 10.0, recent = [10.005, 10.003, 10.004]
        max_change = max(0.005, 0.003, 0.004) / 10.0 = 0.0005 < 0.001
        """
        opt = AdamOptimizer(np.array([0.0]))
        scores = [10.0, 10.005, 10.003, 10.004]
        for s in scores:
            opt.step(np.array([0.0]), score=s)

        assert opt.has_converged(n_lookback=3, threshold=0.001)

    def test_has_converged_false_insufficient_scores(self) -> None:
        """Not enough scores means not converged."""
        opt = AdamOptimizer(np.array([0.0]))
        opt.step(np.array([0.0]), score=10.0)
        opt.step(np.array([0.0]), score=9.5)

        assert not opt.has_converged(n_lookback=3)

    def test_has_converged_false_large_change(self) -> None:
        """Large relative change means not converged."""
        opt = AdamOptimizer(np.array([0.0]))
        scores = [10.0, 8.0, 7.0, 6.0]
        for s in scores:
            opt.step(np.array([0.0]), score=s)

        assert not opt.has_converged(n_lookback=3, threshold=0.001)

    def test_has_converged_zero_baseline(self) -> None:
        """Zero baseline returns False (avoid division by zero)."""
        opt = AdamOptimizer(np.array([0.0]))
        scores = [0.0, 0.0001, 0.0001, 0.0001]
        for s in scores:
            opt.step(np.array([0.0]), score=s)

        assert not opt.has_converged(n_lookback=3)

    def test_has_converged_with_default_params(self) -> None:
        """Default n_lookback=3 and threshold=0.001 work correctly."""
        opt = AdamOptimizer(np.array([0.0]))
        # 5 scores, last 3 nearly identical to the one before
        for s in [100.0, 100.0, 100.05, 100.03, 100.04]:
            opt.step(np.array([0.0]), score=s)

        assert opt.has_converged()


# ---------------------------------------------------------------------------
# Test: Learning rate decay
# ---------------------------------------------------------------------------


class TestLRDecay:
    """Learning rate decay schedule."""

    def test_no_decay_by_default(self) -> None:
        """Default decay power is 0 (no decay)."""
        opt = AdamOptimizer(np.array([0.0]))
        assert opt._lr_decay_power == 0.0

    def test_decay_reduces_step_size(self) -> None:
        """With decay, later steps move less than without decay."""
        opt_no_decay = AdamOptimizer(np.array([0.0]))
        opt_no_decay.set_alpha(0.01)

        opt_decay = AdamOptimizer(np.array([0.0]))
        opt_decay.set_alpha(0.01)
        opt_decay.set_lr_decay_power(0.5)

        for _ in range(20):
            opt_no_decay.step(np.array([1.0]))
            opt_decay.step(np.array([1.0]))

        dist_no_decay = abs(opt_no_decay.get_current_parameters()[0])
        dist_decay = abs(opt_decay.get_current_parameters()[0])
        assert dist_decay < dist_no_decay


# ---------------------------------------------------------------------------
# Test: Return value isolation
# ---------------------------------------------------------------------------


class TestReturnValueIsolation:
    """get_current_parameters and get_score_history return copies."""

    def test_parameter_mutation_does_not_affect_optimizer(self) -> None:
        opt = AdamOptimizer(np.array([1.0, 2.0]))
        params = opt.get_current_parameters()
        params[0] = 999.0
        assert opt.get_current_parameters()[0] == 1.0

    def test_score_history_is_copy(self) -> None:
        opt = AdamOptimizer(np.array([0.0]))
        opt.step(np.array([1.0]), score=5.0)
        history = opt.get_score_history()
        history.append(999.0)
        assert len(opt.get_score_history()) == 1

    def test_learning_rates_is_copy(self) -> None:
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        opt.freeze_parameters(np.array([0]))  # initializes LRs
        lr = opt.get_learning_rates()
        lr[1] = 999.0
        assert opt.get_learning_rates()[1] != 999.0


# ---------------------------------------------------------------------------
# Test: set_alpha and get_learning_rates
# ---------------------------------------------------------------------------


class TestAlphaAndLearningRates:
    """Base learning rate and per-parameter learning rate accessors."""

    def test_set_alpha(self) -> None:
        opt = AdamOptimizer(np.array([0.0]))
        opt.set_alpha(0.05)
        lr = opt.get_learning_rates()
        assert lr[0] == 0.05

    def test_default_alpha(self) -> None:
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        lr = opt.get_learning_rates()
        np.testing.assert_array_equal(lr, [0.001, 0.001])

    def test_per_param_lr_overrides_alpha(self) -> None:
        """After auto_scale with vector range, per-param LRs are used."""
        opt = AdamOptimizer(np.array([0.0, 0.0]))
        opt.auto_scale_learning_rate(
            expected_range=np.array([5.0, 10.0]),
            n_iterations=100,
            safety_factor=3.0,
        )
        lr = opt.get_learning_rates()
        np.testing.assert_allclose(lr, [0.15, 0.30], atol=1e-12)
