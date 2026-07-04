"""Black-box optimizers over the SAME FilterModel (DESIGN §8, primary path = optuna).

Every optimizer maps a theta-scoring callable ``fn(theta) -> float`` and a
:class:`~mito_filter.optimize.space.ParameterSpace` to an :class:`OptimizeResult`. The tuner
builds ``fn`` from the objective + model + dataset, so the load-bearing non-differentiable knobs
(cluster CC threshold, coherence radius, surface-fit tolerance) are searched globally here rather
than by autograd. :class:`OptunaOptimizer` (TPE) is the primary path; :class:`RandomOptimizer` is
a dependency-free fallback used in tests / when optuna is unavailable.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, cast

import numpy as np

from .space import ParameterSpace

__all__ = [
    "OptimizeResult",
    "Optimizer",
    "OptunaOptimizer",
    "RandomOptimizer",
]

ObjectiveFn = Callable[[Dict[str, float]], float]


@dataclass
class OptimizeResult:
    """The outcome of a black-box search.

    Args:
        best_theta: The best flat theta found.
        best_value: Its objective value (in the optimiser's ``direction``).
        n_trials: Number of trials evaluated.
        history: The objective value of every trial, in order.
        direction: ``"maximize"`` or ``"minimize"``.

    Attributes:
        best_theta: The best parameters.
        best_value: The best value.
        n_trials: Trial count.
        history: Per-trial values.
        direction: Optimisation direction.
    """

    best_theta: Dict[str, float]
    best_value: float
    n_trials: int
    history: List[float] = field(default_factory=list)
    direction: str = "maximize"


class Optimizer(ABC):
    """Abstract black-box optimizer over a :class:`ParameterSpace`."""

    @abstractmethod
    def optimize(
        self,
        fn: ObjectiveFn,
        space: ParameterSpace,
        *,
        n_trials: int,
        warm_start: Optional[Dict[str, float]] = None,
        direction: str = "maximize",
    ) -> OptimizeResult:
        """Search ``space`` to optimise ``fn``.

        Args:
            fn: The theta-scoring callable.
            space: The parameter space.
            n_trials: Evaluation budget.
            warm_start: Optional theta to seed / evaluate first.
            direction: ``"maximize"`` or ``"minimize"``.

        Returns:
            The :class:`OptimizeResult`.
        """
        raise NotImplementedError


class OptunaOptimizer(Optimizer):
    """TPE (or supplied sampler) global search — the PRIMARY optimizer (DESIGN §8).

    Args:
        seed: RNG seed for the sampler (reproducibility).
        sampler: Optional Optuna sampler (defaults to a seeded ``TPESampler``).
        verbose: If False (default), silences Optuna's per-trial logging.

    Attributes:
        seed: The sampler seed.
        sampler: The sampler (or None to build a default).
        verbose: Logging flag.
    """

    def __init__(
        self, seed: int = 0, sampler: Optional[object] = None, *, verbose: bool = False
    ) -> None:
        self.seed = int(seed)
        self.sampler = sampler
        self.verbose = bool(verbose)

    def optimize(
        self,
        fn: ObjectiveFn,
        space: ParameterSpace,
        *,
        n_trials: int,
        warm_start: Optional[Dict[str, float]] = None,
        direction: str = "maximize",
    ) -> OptimizeResult:
        """Run the Optuna study; enqueues ``warm_start`` (and the space init) as first trials."""
        import optuna

        if not self.verbose:
            optuna.logging.set_verbosity(optuna.logging.WARNING)
            logging.getLogger("optuna").setLevel(logging.WARNING)

        sampler = (
            self.sampler if self.sampler is not None else optuna.samplers.TPESampler(seed=self.seed)
        )
        study = optuna.create_study(
            direction=direction, sampler=cast("optuna.samplers.BaseSampler", sampler)
        )

        names = set(space.names)
        study.enqueue_trial({k: v for k, v in space.initial().items() if k in names})
        if warm_start is not None:
            seed_theta = {k: space.clip(warm_start)[k] for k in warm_start if k in names}
            if seed_theta:
                study.enqueue_trial(seed_theta)

        history: List[float] = []

        def _objective(trial: "optuna.trial.Trial") -> float:
            theta = space.suggest_optuna(trial)
            value = float(fn(theta))
            history.append(value)
            return value

        study.optimize(_objective, n_trials=int(n_trials))
        # Reconstruct the full best theta (constant dims are not stored as params).
        best = dict(space.initial())
        best.update(study.best_params)
        return OptimizeResult(
            best_theta=best,
            best_value=float(study.best_value),
            n_trials=int(n_trials),
            history=history,
            direction=direction,
        )


class RandomOptimizer(Optimizer):
    """Uniform random search — dependency-free fallback / baseline.

    Args:
        seed: RNG seed.

    Attributes:
        seed: The seed.
    """

    def __init__(self, seed: int = 0) -> None:
        self.seed = int(seed)

    def optimize(
        self,
        fn: ObjectiveFn,
        space: ParameterSpace,
        *,
        n_trials: int,
        warm_start: Optional[Dict[str, float]] = None,
        direction: str = "maximize",
    ) -> OptimizeResult:
        """Evaluate ``n_trials`` random points (plus warm_start/init) and keep the best."""
        rng = np.random.default_rng(self.seed)
        maximize = direction == "maximize"
        best_theta: Dict[str, float] = space.initial()
        history: List[float] = []

        def _score(theta: Dict[str, float]) -> float:
            v = float(fn(theta))
            history.append(v)
            return v

        seeds: List[Dict[str, float]] = [space.initial()]
        if warm_start is not None:
            seeds.append(space.clip({**space.initial(), **warm_start}))
        best_value = _score(seeds[0])
        best_theta = seeds[0]
        for theta in seeds[1:]:
            v = _score(theta)
            if (v > best_value) if maximize else (v < best_value):
                best_value, best_theta = v, theta
        remaining = max(0, int(n_trials) - len(seeds))
        for _ in range(remaining):
            theta = space.sample_random(rng)
            v = _score(theta)
            if (v > best_value) if maximize else (v < best_value):
                best_value, best_theta = v, theta
        return OptimizeResult(
            best_theta=dict(best_theta),
            best_value=float(best_value),
            n_trials=len(history),
            history=history,
            direction=direction,
        )
