"""Tuner: fit ONE theta jointly over the whole search, emit a portable FittedConfig (DESIGN §8).

The producer half of the two-layer design. Given a :class:`FilterModel`, an :class:`Objective`
(the primary self-supervised physics term, optionally composited with the weak-label term) and a
:class:`SearchDataset` of cached features over **every** convmap, :class:`Tuner` searches theta
with a black-box :class:`Optimizer` (optuna primary), applies the best theta to the *same* model,
chooses ``tau``, and serialises everything scan needs into a :class:`FittedConfig`. Transfer =
``fit(..., warm_start=prior_config)``: the prior theta seeds the search on a new dataset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from ..model.config import FittedConfig
from ..model.filter_model import FilterModel
from .dataset import SearchDataset
from .objective import Objective, ObjectiveValue
from .optimizers import Optimizer, OptimizeResult, OptunaOptimizer
from .report import SeparationReport, build_report
from .space import TAU_KEY, ParameterSpace

__all__ = ["Tuner", "TuneResult"]


@dataclass
class TuneResult:
    """The full outcome of a tuning run.

    Args:
        config: The emitted :class:`FittedConfig` (the portable unit scan consumes).
        result: The raw :class:`OptimizeResult` from the optimizer.
        report: The :class:`SeparationReport` of the fitted model.

    Attributes:
        config: The fitted config.
        result: The optimize result.
        report: The separation report.
    """

    config: FittedConfig
    result: OptimizeResult
    report: SeparationReport


class Tuner:
    """Fit ``model.theta`` to maximise ``objective`` over a :class:`SearchDataset`.

    Args:
        model: The filter model (mutated in place to the best theta on :meth:`fit`).
        objective: The objective to maximise (self-supervised primary, optionally composited).
        space: The search space (defaults to :meth:`ParameterSpace.from_model`).
        optimizer: The black-box optimizer (defaults to :class:`OptunaOptimizer`).

    Attributes:
        model: The model.
        objective: The objective.
        space: The parameter space.
        optimizer: The optimizer.
    """

    def __init__(
        self,
        model: FilterModel,
        objective: Objective,
        *,
        space: Optional[ParameterSpace] = None,
        optimizer: Optional[Optimizer] = None,
    ) -> None:
        self.model = model
        self.objective = objective
        self.space = space if space is not None else ParameterSpace.from_model(model)
        self.optimizer = optimizer if optimizer is not None else OptunaOptimizer()

    def _objective_fn(self, dataset: SearchDataset):  # type: ignore[no-untyped-def]
        """Return ``fn(theta) -> float`` scoring a proposed theta on ``dataset`` (tau ignored)."""

        def fn(theta: Dict[str, float]) -> float:
            return float(self.objective.evaluate(self.model, dataset, theta=theta).total)

        return fn

    def _choose_tau(
        self, best_theta: Dict[str, float], dataset: SearchDataset, tau_grid: Optional[List[float]]
    ) -> float:
        """Resolve tau: the searched value if present, else the grid point of maximal separation.

        Args:
            best_theta: The best theta (may carry a searched ``tau``).
            dataset: The dataset (for the grid keep-prob).
            tau_grid: Optional thresholds to sweep when tau was not searched.

        Returns:
            The chosen tau in ``(0, 1)``.
        """
        if TAU_KEY in best_theta:
            return float(best_theta[TAU_KEY])
        p = np.clip(np.asarray(self.model.forward(dataset.matrix), dtype=np.float64), 0.0, 1.0)
        grid = tau_grid if tau_grid is not None else list(np.linspace(0.1, 0.9, 17))
        if p.size == 0:
            return 0.5
        # Widest keep-prob gap around the threshold = the most decisive cut.
        best_tau, best_gap = 0.5, -1.0
        for t in grid:
            hi = p[p >= t]
            lo = p[p < t]
            if hi.size == 0 or lo.size == 0:
                continue
            gap = float(hi.mean() - lo.mean())
            if gap > best_gap:
                best_gap, best_tau = gap, float(t)
        return best_tau

    def fit(
        self,
        dataset: SearchDataset,
        *,
        n_trials: int = 100,
        warm_start: Optional[FittedConfig] = None,
        tau_grid: Optional[List[float]] = None,
        weak_labels: Optional[object] = None,
        dataset_name: str = "",
    ) -> TuneResult:
        """Search theta over ``dataset``, apply the best, and emit a :class:`FittedConfig`.

        Args:
            dataset: The whole-search cached-feature dataset.
            n_trials: The optimizer evaluation budget.
            warm_start: Optional prior :class:`FittedConfig` whose theta seeds the search
                (transfer / fine-tune, DESIGN §8).
            tau_grid: Optional tau sweep when tau is not in the search space.
            weak_labels: Optional row-aligned :class:`~mito_filter.optimize.labels.WeakLabels`
                for the report's PR / separation.
            dataset_name: Label recorded in the emitted config.

        Returns:
            The :class:`TuneResult` (config + raw result + report).
        """
        fn = self._objective_fn(dataset)
        warm_theta = dict(warm_start.theta) if warm_start is not None else None
        result = self.optimizer.optimize(
            fn, self.space, n_trials=n_trials, warm_start=warm_theta, direction="maximize"
        )

        # Apply the best theta to the shared model (set_theta ignores the reserved 'tau').
        self.model.set_theta(result.best_theta)
        tau = self._choose_tau(result.best_theta, dataset, tau_grid)

        final: ObjectiveValue = self.objective.evaluate(self.model, dataset)
        report = build_report(
            self.model,
            dataset,
            tau=tau,
            weak_labels=weak_labels,  # type: ignore[arg-type]
            objective_components=final.components,
            theta=self.model.theta,
        )

        config = FittedConfig(
            dataset=dataset_name or str(dataset.meta.get("cache_dir", "")),
            features=list(self.model.needs_features),
            constraints=[
                {
                    "name": c.name,
                    **{k: float(v) for k, v in self.model._constraint_theta(c).items()},
                }
                for c in self.model.constraints
            ],
            combiner=self.model.combiner.to_config(),
            theta=self.model.theta,
            tau=tau,
            meta={
                "objective_total": float(final.total),
                "objective_components": {k: float(v) for k, v in final.components.items()},
                "n_trials": result.n_trials,
                "best_value": result.best_value,
                "n_hits": dataset.n,
                "n_tomos": dataset.n_tomos,
                "report": report.to_dict(),
            },
        )
        return TuneResult(config=config, result=result, report=report)
