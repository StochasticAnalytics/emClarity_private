"""
Tests for the lr_values keyword on LBFGSBOptimizer.unfreeze_parameters.

Verifies that lr_values is accepted for interface compatibility with
AdamOptimizer but does not alter L-BFGS-B behavior.
"""

from __future__ import annotations

import numpy as np

from ..emc_lbfgsb_optimizer import LBFGSBOptimizer


class TestUnfreezeLrValues:
    """Verify lr_values keyword on unfreeze_parameters."""

    def _make_optimizer(self, n: int = 5) -> LBFGSBOptimizer:
        """Create a bounded optimizer with frozen dim 0."""
        opt = LBFGSBOptimizer(np.zeros(n))
        opt.set_bounds(-5.0 * np.ones(n), 5.0 * np.ones(n))
        opt.freeze_parameters(np.array([0]))
        return opt

    def test_lr_values_accepted_without_error(self) -> None:
        """Passing lr_values does not raise."""
        opt = self._make_optimizer()
        opt.unfreeze_parameters(np.array([0]), lr_values=np.array([0.01]))

    def test_lr_values_none_accepted(self) -> None:
        """Explicit lr_values=None is accepted (default path)."""
        opt = self._make_optimizer()
        opt.unfreeze_parameters(np.array([0]), lr_values=None)

    def test_lr_values_does_not_change_behavior(self) -> None:
        """Optimizer state is identical with and without lr_values."""
        n = 5

        # Path A: unfreeze without lr_values
        opt_a = LBFGSBOptimizer(np.zeros(n))
        opt_a.set_bounds(-5.0 * np.ones(n), 5.0 * np.ones(n))
        opt_a.freeze_parameters(np.array([0, 1]))
        opt_a.unfreeze_parameters(np.array([0, 1]))

        # Path B: unfreeze with lr_values
        opt_b = LBFGSBOptimizer(np.zeros(n))
        opt_b.set_bounds(-5.0 * np.ones(n), 5.0 * np.ones(n))
        opt_b.freeze_parameters(np.array([0, 1]))
        opt_b.unfreeze_parameters(np.array([0, 1]), lr_values=np.array([0.1, 0.2]))

        # Both should have identical state
        np.testing.assert_array_equal(
            opt_a.get_current_parameters(),
            opt_b.get_current_parameters(),
        )
        assert opt_a.get_history_length() == opt_b.get_history_length() == 0
        np.testing.assert_array_equal(opt_a.get_h0_diagonal(), opt_b.get_h0_diagonal())

    def test_history_cleared_with_lr_values(self) -> None:
        """L-BFGS history is cleared even when lr_values is provided."""
        n = 3
        opt = LBFGSBOptimizer(np.zeros(n))
        opt.set_bounds(-5.0 * np.ones(n), 5.0 * np.ones(n))

        # Build some history
        rng = np.random.default_rng(42)
        for _i in range(5):
            opt.step(rng.standard_normal(n), score_is_maximized=True)
        assert opt.get_history_length() > 0

        # Freeze, then unfreeze with lr_values
        opt.freeze_parameters(np.array([0]))
        opt.unfreeze_parameters(np.array([0]), lr_values=np.array([0.05]))
        assert opt.get_history_length() == 0

    def test_h0_set_with_lr_values(self) -> None:
        """Bounds-based H_0 is set after unfreeze with lr_values."""
        n = 3
        lower = np.array([-5.0, -3.0, -1.0])
        upper = np.array([5.0, 3.0, 1.0])

        opt = LBFGSBOptimizer(np.zeros(n))
        opt.set_bounds(lower, upper)
        opt.freeze_parameters(np.array([0]))
        opt.unfreeze_parameters(np.array([0]), lr_values=np.array([0.1]))

        h0 = opt.get_h0_diagonal()
        assert h0 is not None
        expected = (upper - lower) ** 2 / (4.0 * n)
        np.testing.assert_allclose(h0, expected, rtol=1e-12)

    def test_optimization_unaffected_by_lr_values(self) -> None:
        """Full optimization trajectory is identical with lr_values."""
        n = 3
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([1.0, 1.0, 1.0])

        def f(x: np.ndarray) -> float:
            return float(np.sum(a * (x - b) ** 2))

        def grad_f(x: np.ndarray) -> np.ndarray:
            return 2.0 * a * (x - b)

        results = []
        for use_lr in [False, True]:
            opt = LBFGSBOptimizer(np.zeros(n))
            opt.set_bounds(-5.0 * np.ones(n), 5.0 * np.ones(n))
            opt.set_objective(f)
            opt.freeze_parameters(np.array([2]))

            for _ in range(20):
                params = opt.get_current_parameters()
                opt.step(grad_f(params), score=f(params), score_is_maximized=False)

            if use_lr:
                opt.unfreeze_parameters(
                    np.array([2]), lr_values=np.array([0.5])
                )
            else:
                opt.unfreeze_parameters(np.array([2]))

            for _ in range(20):
                params = opt.get_current_parameters()
                opt.step(grad_f(params), score=f(params), score_is_maximized=False)

            results.append(opt.get_current_parameters())

        np.testing.assert_array_equal(results[0], results[1])
