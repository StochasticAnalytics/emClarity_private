"""
Abstract base class for parameter optimization algorithms.

Defines the interface shared by all optimizers (ADAM, L-BFGS-B, etc.)
used in cryo-EM iterative refinement. Subclasses implement the core
optimization logic while this base provides common state management
for parameter bounds and score history.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class OptimizerBase(ABC):
    """Abstract base class defining the interface for parameter optimizers.

    Provides concrete implementations for parameter bounds storage and
    score history tracking, while requiring subclasses to implement the
    core optimization step, convergence check, and parameter freeze/unfreeze
    logic (which differs per algorithm).

    Subclass contract:
        - ``step``: perform one optimization update given a gradient
        - ``has_converged``: check whether optimization should stop
        - ``get_current_parameters``: return the current parameter vector
        - ``freeze_parameters``: prevent specified parameters from updating
        - ``unfreeze_parameters``: re-enable updates for frozen parameters
    """

    def __init__(self) -> None:
        """Initialize common optimizer state."""
        self._lower_bounds: np.ndarray | None = None
        self._upper_bounds: np.ndarray | None = None
        self._score_history: list[float] = []

    @abstractmethod
    def step(self, gradient: np.ndarray, score: float | None = None) -> None:
        """Perform one optimization step given the current gradient.

        Args:
            gradient: Gradient vector with same length as parameters.
            score: Optional objective score to record for convergence tracking.
        """
        ...

    @abstractmethod
    def has_converged(self, n_lookback: int = 3, threshold: float = 0.001) -> bool:
        """Check whether optimization has converged.

        Args:
            n_lookback: Number of recent scores to compare against baseline.
            threshold: Maximum relative change to consider converged.

        Returns:
            True if relative improvement over last n_lookback scores is
            below threshold.
        """
        ...

    @abstractmethod
    def get_current_parameters(self) -> np.ndarray:
        """Return a copy of the current parameter vector."""
        ...

    @abstractmethod
    def freeze_parameters(self, indices: np.ndarray) -> None:
        """Freeze specified parameters so they are not updated during step().

        Implementation varies by optimizer: ADAM zeros learning rates;
        L-BFGS-B zeros updates and clears curvature history.

        Args:
            indices: Array of parameter indices to freeze.
        """
        ...

    @abstractmethod
    def unfreeze_parameters(self, indices: np.ndarray) -> None:
        """Unfreeze specified parameters to resume updates during step().

        Args:
            indices: Array of parameter indices to unfreeze.
        """
        ...

    def set_bounds(self, lower: np.ndarray, upper: np.ndarray) -> None:
        """Set lower and upper bounds for parameters.

        Subclasses may override to add clamping of current parameters.

        Args:
            lower: Lower bound per parameter. Use ``-np.inf`` for unconstrained.
            upper: Upper bound per parameter. Use ``np.inf`` for unconstrained.
        """
        self._lower_bounds = np.asarray(lower, dtype=np.float64).ravel()
        self._upper_bounds = np.asarray(upper, dtype=np.float64).ravel()

    def get_score_history(self) -> list[float]:
        """Return a copy of the recorded objective score history."""
        return list(self._score_history)
