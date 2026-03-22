"""
L-BFGS-B optimizer for bounded parameter optimization.

Implements Limited-memory BFGS with Bounds from scratch for full control
over history reset and curvature rejection. This is critical for cryo-EM
iterative refinement where discrete cross-correlation peak jumps create
negative curvature that corrupts standard quasi-Newton updates.

Algorithm references:
    Nocedal & Wright, "Numerical Optimization", 2nd ed., Algorithm 7.4
    Byrd, Lu, Nocedal & Zhu, 1995. "A limited memory algorithm for
    bound constrained optimization."
"""

from __future__ import annotations

from collections import deque
from typing import Callable

import numpy as np

from .emc_optimizer_base import OptimizerBase


class LBFGSBOptimizer(OptimizerBase):
    """L-BFGS-B optimizer with curvature rejection and parameter freezing.

    Maintains a limited-memory approximation to the inverse Hessian using
    the last *m* correction pairs (s_k, y_k). Handles box constraints via
    projected gradient with generalized Cauchy point computation and
    subspace minimization.

    Key features for cryo-EM:
        - Curvature pair rejection guards against negative curvature from
          discrete peak jumps in cross-correlation landscapes.
        - Parameter freezing/unfreezing with automatic history reset
          prevents stale curvature from corrupting the search direction
          after the active parameter set changes.
        - Bounds-based diagonal scaling for H_0 after history reset
          provides a reasonable initial inverse Hessian from parameter
          range information.

    Args:
        initial_params: Starting parameter vector. Must be non-empty.
        memory_size: Number of correction pairs to store (default 7).

    Raises:
        ValueError: If initial_params is empty or memory_size < 1.
    """

    def __init__(
        self,
        initial_params: np.ndarray,
        memory_size: int = 7,
    ) -> None:
        """Initialize L-BFGS-B optimizer."""
        super().__init__()

        params = np.asarray(initial_params, dtype=np.float64).ravel()
        if params.size == 0:
            raise ValueError("Initial parameters must be a non-empty vector.")
        if memory_size < 1:
            raise ValueError(
                f"memory_size must be at least 1, got {memory_size}."
            )

        self._memory_size: int = memory_size
        self._current_parameters: np.ndarray = params.copy()
        self._n_params: int = params.size

        # L-BFGS history: correction pairs (s_k, y_k)
        self._s_history: deque[np.ndarray] = deque(maxlen=memory_size)
        self._y_history: deque[np.ndarray] = deque(maxlen=memory_size)

        # Previous gradient for computing y_k = g_{k+1} - g_k
        self._prev_gradient: np.ndarray | None = None
        self._prev_parameters: np.ndarray | None = None

        # Frozen parameter mask (True = frozen, not updated)
        self._frozen_mask: np.ndarray = np.zeros(self._n_params, dtype=bool)

        # Initial inverse Hessian diagonal scaling (set by unfreeze)
        self._h0_diag: np.ndarray | None = None

        # Curvature rejection threshold
        self._curvature_epsilon: float = 1e-10

        # Line search parameters
        self._c1: float = 1e-4  # Armijo sufficient decrease
        self._max_linesearch_steps: int = 20
        self._linesearch_factor: float = 0.5

        # Objective function for line search (optional)
        self._objective_fn: Callable[[np.ndarray], float] | None = None

        # Iteration counter
        self._t: int = 0

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_objective(self, fn: Callable[[np.ndarray], float] | None) -> None:
        """Set the objective function for backtracking line search.

        When set, ``step()`` performs backtracking Armijo line search by
        evaluating the objective at trial step sizes. When ``None``
        (default), ``step()`` uses unit step size — the standard choice
        for quasi-Newton methods when the Hessian approximation is good.

        Args:
            fn: Callable taking a parameter vector and returning the
                scalar objective value, or ``None`` to disable line search.
        """
        self._objective_fn = fn

    # ------------------------------------------------------------------
    # Core interface (OptimizerBase abstract methods)
    # ------------------------------------------------------------------

    def step(self, gradient: np.ndarray, score: float | None = None) -> None:
        """Perform one L-BFGS-B update step.

        Computes a search direction using two-loop recursion on the L-BFGS
        history, projects it onto the feasible region, then performs
        backtracking line search with Armijo condition (when an objective
        function is available).

        **Ordering invariant when ``set_objective`` is active:** ``score``
        must equal ``objective_fn(get_current_parameters())`` — that is,
        the objective evaluated at the current parameter values *before*
        this call mutates them. The Armijo line search uses ``score`` as
        the baseline ``f(x_k)``; a stale or mismatched value will cause
        the sufficient-decrease check to accept or reject step sizes
        against the wrong reference.

        Args:
            gradient: Gradient vector with same length as parameters.
            score: Optional objective score to record for convergence
                tracking. When ``set_objective`` is active, also serves
                as the baseline ``f(x_k)`` for the Armijo line search
                and must therefore be evaluated at the current parameters
                before calling ``step()``.

        Raises:
            ValueError: If gradient contains NaN or Inf values, or has
                wrong length.
        """
        grad = np.asarray(gradient, dtype=np.float64).ravel()

        if grad.size != self._n_params:
            raise ValueError(
                f"Gradient length ({grad.size}) must match parameter count "
                f"({self._n_params})."
            )
        if np.any(np.isnan(grad)):
            raise ValueError("Gradient contains NaN values.")
        if np.any(np.isinf(grad)):
            raise ValueError("Gradient contains Inf values.")

        if score is not None:
            self._score_history.append(float(score))

        # Zero out gradient for frozen parameters
        grad_active = grad.copy()
        grad_active[self._frozen_mask] = 0.0

        # Update L-BFGS history with curvature pair from previous step
        if self._prev_gradient is not None and self._prev_parameters is not None:
            s_k = self._current_parameters - self._prev_parameters
            y_k = grad_active - self._prev_gradient

            # Curvature pair rejection: skip when s'*y <= epsilon * s'*s
            sy = float(np.dot(s_k, y_k))
            ss = float(np.dot(s_k, s_k))
            if sy > self._curvature_epsilon * ss and ss > 0.0:
                self._s_history.append(s_k.copy())
                self._y_history.append(y_k.copy())

        # Store current state for next iteration's curvature pair
        self._prev_parameters = self._current_parameters.copy()
        self._prev_gradient = grad_active.copy()

        # Compute search direction using two-loop recursion
        direction = self._two_loop_recursion(grad_active)

        # Project direction for bound constraints
        if self._lower_bounds is not None or self._upper_bounds is not None:
            direction = self._project_direction(direction)

        # Zero direction for frozen parameters
        direction[self._frozen_mask] = 0.0

        # Verify descent direction; fall back to projected steepest descent
        dd = float(np.dot(grad_active, direction))
        grad_norm = float(np.linalg.norm(grad_active))
        if dd >= 0.0 and grad_norm > 0.0:
            direction = -grad_active.copy()
            direction[self._frozen_mask] = 0.0
            if self._lower_bounds is not None or self._upper_bounds is not None:
                direction = self._project_direction(direction)

        # Backtracking line search with Armijo condition
        if self._objective_fn is not None:
            current_value = (
                score
                if score is not None
                else self._objective_fn(self._current_parameters)
            )
            # When no curvature info, start with a smaller initial step
            # (standard heuristic: 1/||grad|| for the first L-BFGS step)
            if len(self._s_history) == 0:
                dir_norm = float(np.linalg.norm(direction))
                initial_alpha = min(1.0, 1.0 / max(dir_norm, 1e-10))
            else:
                initial_alpha = 1.0
            step_size = self._backtracking_line_search(
                grad_active, direction, current_value, initial_alpha
            )
        else:
            step_size = 1.0

        # Update parameters
        new_params = self._current_parameters + step_size * direction

        # Enforce frozen parameters
        new_params[self._frozen_mask] = self._current_parameters[self._frozen_mask]

        # Clamp to bounds
        if self._lower_bounds is not None:
            new_params = np.maximum(new_params, self._lower_bounds)
        if self._upper_bounds is not None:
            new_params = np.minimum(new_params, self._upper_bounds)

        self._current_parameters = new_params
        self._t += 1

    def has_converged(self, n_lookback: int = 3, threshold: float = 0.001) -> bool:
        """Check convergence based on relative improvement of recent scores.

        Identical behavior to AdamOptimizer.has_converged: compares the last
        ``n_lookback`` scores against the score immediately preceding them.
        If the maximum relative change is below threshold, returns True.

        Args:
            n_lookback: Number of recent scores to examine.
            threshold: Maximum relative change considered converged.

        Returns:
            True if converged, False otherwise.
        """
        if n_lookback <= 0:
            raise ValueError(
                f"n_lookback must be a positive integer, got {n_lookback}."
            )
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
        """Freeze specified parameters so they are not updated during step().

        Frozen parameters have their gradient zeroed and their positions
        locked. Unlike ADAM which zeros learning rates, L-BFGS-B uses a
        boolean mask since the search direction is computed globally.

        Args:
            indices: Array of parameter indices to freeze.
        """
        idx = np.asarray(indices).ravel()
        self._frozen_mask[idx] = True

    def unfreeze_parameters(
        self,
        indices: np.ndarray,
        lr_values: np.ndarray | None = None,
    ) -> None:
        """Unfreeze parameters and clear L-BFGS history.

        Re-enables updates for the specified dimensions AND clears the
        entire L-BFGS history (s_k, y_k lists). Stale curvature from
        the frozen regime would corrupt optimization in the newly unfrozen
        subspace.

        After history reset, initializes H_0 using bounds-based diagonal
        scaling: ``H_0[i,i] = (upper[i] - lower[i])^2 / (4 * n_params)``.

        Args:
            indices: Array of parameter indices to unfreeze.
            lr_values: Accepted for interface compatibility with
                AdamOptimizer but ignored. L-BFGS-B does not use
                per-parameter learning rates.
        """
        idx = np.asarray(indices).ravel()
        self._frozen_mask[idx] = False

        # Clear L-BFGS history — stale curvature from frozen regime
        self._s_history.clear()
        self._y_history.clear()
        self._prev_gradient = None
        self._prev_parameters = None

        # Initialize H_0 from bounds-based diagonal scaling
        if self._lower_bounds is not None and self._upper_bounds is not None:
            bound_range = self._upper_bounds - self._lower_bounds
            # For infinite bounds, use a default scale of 1.0
            finite_mask = np.isfinite(bound_range)
            h0 = np.ones(self._n_params, dtype=np.float64)
            h0[finite_mask] = (
                bound_range[finite_mask] ** 2 / (4.0 * self._n_params)
            )
            self._h0_diag = h0

    # ------------------------------------------------------------------
    # Bounds (override base to add immediate clamping)
    # ------------------------------------------------------------------

    def set_bounds(self, lower: np.ndarray, upper: np.ndarray) -> None:
        """Set parameter bounds and clamp current parameters immediately.

        Args:
            lower: Lower bound per parameter. Use ``-np.inf`` for unconstrained.
            upper: Upper bound per parameter. Use ``np.inf`` for unconstrained.

        Raises:
            ValueError: If bound vector lengths don't match parameter count.
        """
        lb = np.asarray(lower, dtype=np.float64).ravel()
        ub = np.asarray(upper, dtype=np.float64).ravel()

        if lb.size != self._n_params or ub.size != self._n_params:
            raise ValueError(
                f"Bound vectors must have the same length as parameter vector "
                f"({self._n_params})."
            )

        self._lower_bounds = lb
        self._upper_bounds = ub

        # Clamp current parameters to bounds immediately
        self._current_parameters = np.maximum(self._current_parameters, lb)
        self._current_parameters = np.minimum(self._current_parameters, ub)

    # ------------------------------------------------------------------
    # L-BFGS two-loop recursion (Nocedal & Wright, Algorithm 7.4)
    # ------------------------------------------------------------------

    def _two_loop_recursion(self, grad: np.ndarray) -> np.ndarray:
        """Compute search direction via L-BFGS two-loop recursion.

        Uses the stored correction pairs (s, y) to approximate the
        inverse Hessian-gradient product without forming the full matrix.

        When no history is available, falls back to scaled steepest
        descent using the H_0 diagonal (bounds-based scaling if set,
        identity otherwise).

        When history is available, uses Shanno-Phua scaling
        (gamma = s'y / y'y from the most recent pair) for the initial
        H_0 in the recursion.

        Args:
            grad: Current gradient vector.

        Returns:
            Search direction (negative of H*grad for descent).
        """
        q = grad.copy()
        m = len(self._s_history)

        if m == 0:
            # No history: use h0_diag or identity for steepest descent
            h0 = self._get_h0_diagonal()
            return -(h0 * q)

        # Backward pass: compute alpha coefficients
        alphas = np.zeros(m)
        rhos = np.zeros(m)

        for i in range(m - 1, -1, -1):
            s_i = self._s_history[i]
            y_i = self._y_history[i]
            sy = float(np.dot(y_i, s_i))
            if abs(sy) < 1e-30:
                rhos[i] = 0.0
                alphas[i] = 0.0
            else:
                rhos[i] = 1.0 / sy
                alphas[i] = rhos[i] * float(np.dot(s_i, q))
            q = q - alphas[i] * y_i

        # Shanno-Phua scaling from most recent pair: gamma = s'y / y'y
        s_last = self._s_history[-1]
        y_last = self._y_history[-1]
        yy = float(np.dot(y_last, y_last))
        if yy > 0.0:
            gamma = float(np.dot(s_last, y_last)) / yy
        else:
            gamma = 1.0
        r = gamma * q

        # Forward pass: recover search direction
        for i in range(m):
            s_i = self._s_history[i]
            y_i = self._y_history[i]
            beta = rhos[i] * float(np.dot(y_i, r))
            r = r + (alphas[i] - beta) * s_i

        return -r

    def _get_h0_diagonal(self) -> np.ndarray:
        """Get the initial inverse Hessian diagonal.

        If bounds-based scaling has been set (after unfreeze), use that.
        Otherwise, use identity scaling.

        Returns:
            Diagonal of the initial inverse Hessian approximation.
        """
        if self._h0_diag is not None:
            return self._h0_diag
        return np.ones(self._n_params, dtype=np.float64)

    # ------------------------------------------------------------------
    # Projected gradient for bound handling
    # ------------------------------------------------------------------

    def _project_direction(self, direction: np.ndarray) -> np.ndarray:
        """Project search direction to respect bound constraints.

        Implements a simplified Generalized Cauchy Point approach:
        identifies variables that would violate bounds if moved along
        the search direction, and zeros out those components to keep
        the iterate feasible.

        Args:
            direction: Raw search direction.

        Returns:
            Projected search direction respecting bound constraints.
        """
        proj = direction.copy()
        x = self._current_parameters

        if self._lower_bounds is not None:
            # At lower bound and direction would push below: active
            at_lower = x <= self._lower_bounds + 1e-15
            proj[at_lower & (proj < 0.0)] = 0.0

        if self._upper_bounds is not None:
            # At upper bound and direction would push above: active
            at_upper = x >= self._upper_bounds - 1e-15
            proj[at_upper & (proj > 0.0)] = 0.0

        return proj

    # ------------------------------------------------------------------
    # Backtracking line search with Armijo condition
    # ------------------------------------------------------------------

    def _backtracking_line_search(
        self,
        grad: np.ndarray,
        direction: np.ndarray,
        current_value: float,
        initial_alpha: float = 1.0,
    ) -> float:
        """Backtracking line search with Armijo sufficient decrease.

        Starts with ``initial_alpha`` and halves until the Armijo condition
        ``f(x + alpha*d) <= f(x) + c1 * alpha * g'd`` is satisfied
        or the maximum number of steps is reached.

        Args:
            grad: Current gradient vector.
            direction: Search direction (descent direction).
            current_value: Current objective value f(x_k).
            initial_alpha: Starting step size. Use 1.0 (standard for
                quasi-Newton) when curvature info is available; smaller
                when starting from steepest descent.

        Returns:
            Step size satisfying the Armijo condition.
        """
        dd = float(np.dot(grad, direction))

        # If not a descent direction, return a safe small step
        if dd >= 0.0:
            return initial_alpha / (1.0 + self._t)

        alpha = initial_alpha
        for _ in range(self._max_linesearch_steps):
            trial = self._current_parameters + alpha * direction

            # Clamp trial point to bounds
            if self._lower_bounds is not None:
                trial = np.maximum(trial, self._lower_bounds)
            if self._upper_bounds is not None:
                trial = np.minimum(trial, self._upper_bounds)

            trial_value = self._objective_fn(trial)

            # Armijo sufficient decrease condition using the *effective*
            # step after bounds clamping.  The unclamped directional
            # derivative ``alpha * dd`` overestimates the step length
            # near active constraints, causing excessive backtracking.
            effective_step = trial - self._current_parameters
            effective_dd = float(np.dot(grad, effective_step))
            # Guard: bound-clamping can flip effective_dd positive when a
            # negative-contributing dimension hits its bound while a
            # positive-contributing dimension moves freely.  A positive
            # effective_dd would make the RHS exceed current_value, allowing
            # objective increases through the Armijo check.  Clamp to 0 so
            # that, in the degenerate case, we require strict non-increase.
            armijo_slope = min(effective_dd, 0.0)
            if trial_value <= current_value + self._c1 * armijo_slope:
                return alpha

            alpha *= self._linesearch_factor

        return alpha

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_timestep(self) -> int:
        """Return the current optimization timestep."""
        return self._t

    def get_memory_size(self) -> int:
        """Return the configured L-BFGS memory size."""
        return self._memory_size

    def get_history_length(self) -> int:
        """Return the number of stored correction pairs."""
        return len(self._s_history)

    def get_h0_diagonal(self) -> np.ndarray | None:
        """Return the current H_0 diagonal scaling, or None if not set.

        This is set after ``unfreeze_parameters`` when bounds are available,
        using the formula ``H_0[i,i] = (upper[i] - lower[i])^2 / (4 * n)``.
        """
        if self._h0_diag is not None:
            return self._h0_diag.copy()
        return None
