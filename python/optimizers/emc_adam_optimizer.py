"""
ADAM optimizer for iterative parameter refinement.

Port of testScripts/adamOptimizer.m (271 lines). ADAM (Adaptive Moment
Estimation) maintains per-parameter adaptive learning rates using
exponential moving averages of gradient first and second moments.

References:
    Kingma & Ba, 2015. "Adam: A Method for Stochastic Optimization."
    Reddi et al., 2018. "On the Convergence of Adam and Beyond." (AMSGrad)
"""

from __future__ import annotations

import numpy as np

from .emc_optimizer_base import OptimizerBase


class AdamOptimizer(OptimizerBase):
    """ADAM optimizer with optional AMSGrad and learning rate decay.

    Ports the MATLAB ``adamOptimizer`` class with:

    - Per-parameter learning rates with freeze/unfreeze support
    - Configurable learning rate decay: ``lr_t = lr / t^decay_power``
    - AMSGrad variant for guaranteed convergence on convex problems
    - Automatic learning rate scaling based on expected parameter range
    - Parameter bounds with clamping

    Args:
        initial_params: Starting parameter vector. Must be non-empty.
        beta1: Exponential decay rate for first moment estimates.
        beta2: Exponential decay rate for second moment estimates.
        epsilon: Small constant preventing division by zero.

    Raises:
        ValueError: If initial_params is empty.
    """

    def __init__(
        self,
        initial_params: np.ndarray,
        beta1: float = 0.9,
        beta2: float = 0.999,
        epsilon: float = 1e-8,
    ) -> None:
        """Initialize ADAM optimizer with given parameters and hyperparameters."""
        super().__init__()

        params = np.asarray(initial_params, dtype=np.float64).ravel()
        if params.size == 0:
            raise ValueError("Initial parameters must be a non-empty vector.")

        self._alpha: float = 0.001
        self._beta1: float = beta1
        self._beta2: float = beta2
        self._epsilon: float = epsilon
        self._use_amsgrad: bool = False
        self._lr_decay_power: float = 0.0

        n = params.size
        self._m: np.ndarray = np.zeros(n, dtype=np.float64)
        self._v: np.ndarray = np.zeros(n, dtype=np.float64)
        self._v_hat_max: np.ndarray = np.zeros(n, dtype=np.float64)
        self._t: int = 0

        self._initial_parameters: np.ndarray = params.copy()
        self._current_parameters: np.ndarray = params.copy()
        self._learning_rates: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Core interface (OptimizerBase abstract methods)
    # ------------------------------------------------------------------

    def step(self, gradient: np.ndarray, score: float | None = None) -> None:
        """Perform one ADAM update step.

        Applies bias-corrected first and second moment estimates to update
        parameters. Clamps to bounds if set. Records score if provided.

        Reference: adamOptimizer.m lines 38-86 (``update`` method).

        Args:
            gradient: Gradient vector with same length as parameters.
            score: Optional objective score to record.

        Raises:
            ValueError: If gradient contains NaN values.
        """
        grad = np.asarray(gradient, dtype=np.float64).ravel()

        if np.any(np.isnan(grad)):
            raise ValueError("Gradient contains NaN values.")

        if score is not None:
            self._score_history.append(float(score))

        self._t += 1

        # Update biased first moment estimate
        self._m = self._beta1 * self._m + (1.0 - self._beta1) * grad

        # Update biased second raw moment estimate
        self._v = self._beta2 * self._v + (1.0 - self._beta2) * (grad ** 2)

        # Bias-corrected moment estimates
        m_hat = self._m / (1.0 - self._beta1 ** self._t)
        v_hat = self._v / (1.0 - self._beta2 ** self._t)

        # AMSGrad: running max of v_hat ensures non-increasing effective
        # learning rate, guaranteeing convergence on convex problems
        if self._use_amsgrad:
            self._v_hat_max = np.maximum(self._v_hat_max, v_hat)
            v_hat = self._v_hat_max.copy()

        # Per-parameter or scalar learning rate
        if self._learning_rates is not None:
            lr = self._learning_rates.copy()
        else:
            lr = self._alpha

        # Learning rate decay: lr_t = lr / t^decay_power
        if self._lr_decay_power > 0:
            lr = lr / (self._t ** self._lr_decay_power)

        # Parameter update
        self._current_parameters = (
            self._current_parameters - lr * m_hat / (np.sqrt(v_hat) + self._epsilon)
        )

        # Clamp to bounds if set
        if self._lower_bounds is not None:
            self._current_parameters = np.maximum(
                self._current_parameters, self._lower_bounds
            )
        if self._upper_bounds is not None:
            self._current_parameters = np.minimum(
                self._current_parameters, self._upper_bounds
            )

    def has_converged(self, n_lookback: int = 3, threshold: float = 0.001) -> bool:
        """Check convergence based on relative improvement of recent scores.

        Compares the last ``n_lookback`` scores against the score immediately
        preceding them. If the maximum relative change is below threshold,
        returns True.

        Reference: adamOptimizer.m lines 220-241.

        Args:
            n_lookback: Number of recent scores to examine.
            threshold: Maximum relative change considered converged.

        Returns:
            True if converged, False otherwise.
        """
        if len(self._score_history) < n_lookback + 1:
            return False

        recent = self._score_history[-n_lookback:]
        baseline = self._score_history[-(n_lookback + 1)]

        if baseline == 0.0:
            return False

        max_change = max(abs(s - baseline) for s in recent) / abs(baseline)
        return max_change < threshold

    def get_current_parameters(self) -> np.ndarray:
        """Return a copy of the current parameter vector."""
        return self._current_parameters.copy()

    def freeze_parameters(self, indices: np.ndarray) -> None:
        """Freeze parameters by zeroing their learning rates.

        If per-parameter learning rates have not been set, they are
        initialized to the base alpha before zeroing the requested indices.

        Reference: adamOptimizer.m lines 251-257.

        Args:
            indices: Array of parameter indices to freeze.
        """
        if self._learning_rates is None:
            n = self._current_parameters.size
            self._learning_rates = np.full(n, self._alpha, dtype=np.float64)

        idx = np.asarray(indices).ravel()
        self._learning_rates[idx] = 0.0

    def unfreeze_parameters(
        self,
        indices: np.ndarray,
        lr_values: np.ndarray | None = None,
    ) -> None:
        """Restore learning rates for previously frozen parameters.

        Reference: adamOptimizer.m lines 259-266.

        Args:
            indices: Array of parameter indices to unfreeze.
            lr_values: Learning rate values to restore. If None, restores
                to the base alpha value.
        """
        if self._learning_rates is None:
            n = self._current_parameters.size
            self._learning_rates = np.full(n, self._alpha, dtype=np.float64)

        idx = np.asarray(indices).ravel()
        if lr_values is not None:
            values = np.asarray(lr_values, dtype=np.float64).ravel()
        else:
            values = np.full(idx.size, self._alpha, dtype=np.float64)

        self._learning_rates[idx] = values

    # ------------------------------------------------------------------
    # Bounds (override base to add immediate clamping)
    # ------------------------------------------------------------------

    def set_bounds(self, lower: np.ndarray, upper: np.ndarray) -> None:
        """Set parameter bounds and clamp current parameters immediately.

        Reference: adamOptimizer.m lines 118-131.

        Args:
            lower: Lower bound per parameter. Use ``-np.inf`` for unconstrained.
            upper: Upper bound per parameter. Use ``np.inf`` for unconstrained.

        Raises:
            ValueError: If bound vector lengths don't match parameter count.
        """
        lb = np.asarray(lower, dtype=np.float64).ravel()
        ub = np.asarray(upper, dtype=np.float64).ravel()
        n = self._current_parameters.size

        if lb.size != n or ub.size != n:
            raise ValueError(
                f"Bound vectors must have the same length as parameter vector ({n})."
            )

        self._lower_bounds = lb
        self._upper_bounds = ub

        # Clamp current parameters to bounds immediately
        self._current_parameters = np.maximum(self._current_parameters, lb)
        self._current_parameters = np.minimum(self._current_parameters, ub)

    # ------------------------------------------------------------------
    # Learning rate configuration
    # ------------------------------------------------------------------

    def auto_scale_learning_rate(
        self,
        expected_range: np.ndarray | float,
        n_iterations: int,
        safety_factor: float = 3.0,
    ) -> None:
        """Compute learning rate from expected parameter travel distance.

        ADAM normalizes each step to approximately alpha. With
        ``lr_decay_power`` p, the total travel in N steps is
        ``alpha * sum(1/t^p for t=1..N)``. This method sets alpha so that
        ``total_travel = safety_factor * expected_range``.

        The formula:
            ``alpha = safety_factor * expected_range / step_sum``
        where ``step_sum = sum(1/t^decay_power for t in 1..n_iterations)``.

        If expected_range is a vector, per-parameter learning rates are set
        proportional to each dimension's range.

        Reference: adamOptimizer.m lines 141-198.

        Args:
            expected_range: Scalar or per-parameter expected travel distance.
            n_iterations: Planned number of update steps.
            safety_factor: Multiplier on range for step budget.
        """
        expected_range_arr = np.asarray(expected_range, dtype=np.float64).ravel()

        # Compute exact step sum for the current decay schedule
        p = self._lr_decay_power
        step_sum = sum(1.0 / (t ** p) for t in range(1, n_iterations + 1))

        if expected_range_arr.size == 1:
            # Scalar range: set scalar alpha
            self._alpha = float(safety_factor * expected_range_arr[0] / step_sum)
        else:
            # Per-parameter ranges: set per-parameter learning rates
            n = self._current_parameters.size
            if expected_range_arr.size != n:
                raise ValueError(
                    f"expected_range vector must have {n} elements "
                    f"(one per parameter)."
                )
            self._learning_rates = safety_factor * expected_range_arr / step_sum

    def set_amsgrad(self, enabled: bool) -> None:
        """Enable or disable AMSGrad variant.

        AMSGrad uses the running maximum of bias-corrected second moment
        estimates, ensuring monotonically non-decreasing effective learning
        rate denominators. This guarantees convergence on convex problems.

        Reference: Reddi et al., 2018.

        Args:
            enabled: True to enable AMSGrad, False to disable.
        """
        self._use_amsgrad = enabled

    def set_lr_decay_power(self, power: float) -> None:
        """Set learning rate decay schedule: ``lr_t = lr / t^power``.

        power=0 means no decay (default). power=0.5 gives 1/sqrt(t) decay.
        Decay breaks ADAM's limit cycles on convex problems by ensuring
        the step size vanishes, guaranteeing convergence.

        Args:
            power: Decay exponent. 0 disables decay.
        """
        self._lr_decay_power = power

    def set_alpha(self, alpha: float) -> None:
        """Set the base scalar learning rate.

        ADAM normalizes each step to approximately alpha regardless of
        gradient magnitude, so alpha should be tuned to the expected
        parameter scale, not the gradient scale.

        Args:
            alpha: Base learning rate (default 0.001).
        """
        self._alpha = alpha

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_learning_rates(self) -> np.ndarray:
        """Get current per-parameter learning rates.

        Returns the per-parameter vector if set, otherwise ``alpha * ones``.
        """
        if self._learning_rates is not None:
            return self._learning_rates.copy()
        return np.full(self._current_parameters.size, self._alpha, dtype=np.float64)

    def get_timestep(self) -> int:
        """Return the current optimization timestep."""
        return self._t
