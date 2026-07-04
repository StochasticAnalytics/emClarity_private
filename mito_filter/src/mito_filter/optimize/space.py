"""ParameterSpace: the tunable-theta search space derived from a model's constraints (DESIGN §8).

The optimiser searches over the union of (a) every constraint's ``param_schema`` (cluster CC
thresholds, coherence radius/threshold, membrane/surface tolerances, priors — the load-bearing
non-differentiable knobs), (b) the combiner fusion **weights** + bias, and (c) the decision
threshold ``tau``. Each becomes a :class:`Dimension` with bounds/log-scale/init lifted straight
from the source :class:`~mito_filter.constraints.base.ParamSpec` (constraint params) or from
explicit bounds (weights / bias / tau). The flat dimension names are exactly the keys
:meth:`FilterModel.set_theta` / :meth:`FilterModel.forward_with_theta` understand
(``"<constraint>::<param>"``, ``"combiner::w::<name>"``, ``"combiner::bias"``), plus the reserved
``"tau"`` name the tuner consumes separately.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np

from ..model.filter_model import FilterModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    import optuna

__all__ = ["Dimension", "ParameterSpace", "TAU_KEY", "BIAS_KEY", "W_PREFIX"]

TAU_KEY: str = "tau"
"""Reserved dimension name for the keep-probability decision threshold."""
BIAS_KEY: str = "combiner::bias"
"""Flat theta key for the combiner logit bias."""
W_PREFIX: str = "combiner::w::"
"""Flat theta key prefix for the per-constraint combiner fusion weights."""


@dataclass(frozen=True)
class Dimension:
    """One tunable dimension of the search space.

    Args:
        name: The flat theta key (or ``"tau"``).
        lo: Lower bound (inclusive).
        hi: Upper bound (inclusive).
        init: Initial / reference value.
        log: Whether to search in log-space (requires ``lo > 0``).

    Attributes:
        name: The dimension name.
        lo: Lower bound.
        hi: Upper bound.
        init: Initial value.
        log: Log-scale flag.
    """

    name: str
    lo: float
    hi: float
    init: float
    log: bool = False

    def __post_init__(self) -> None:
        if self.hi < self.lo:
            raise ValueError(f"dimension '{self.name}' hi {self.hi} < lo {self.lo}")
        if self.log and self.lo <= 0.0:
            raise ValueError(f"log dimension '{self.name}' requires lo > 0")

    def clip(self, value: float) -> float:
        """Clamp ``value`` into ``[lo, hi]``."""
        return float(min(self.hi, max(self.lo, value)))


class ParameterSpace:
    """A search space over constraint params + combiner weights/bias + tau (DESIGN §8).

    Args:
        dimensions: The ordered tunable dimensions.

    Attributes:
        dimensions: The dimensions.
    """

    def __init__(self, dimensions: List[Dimension]) -> None:
        self.dimensions: List[Dimension] = list(dimensions)
        seen = set()
        for d in self.dimensions:
            if d.name in seen:
                raise ValueError(f"duplicate dimension '{d.name}'")
            seen.add(d.name)

    @property
    def names(self) -> List[str]:
        """The dimension names in order."""
        return [d.name for d in self.dimensions]

    def __len__(self) -> int:
        return len(self.dimensions)

    @classmethod
    def from_model(
        cls,
        model: FilterModel,
        *,
        include_combiner: bool = True,
        include_bias: bool = True,
        include_tau: bool = True,
        weight_bounds: Tuple[float, float] = (-8.0, 8.0),
        bias_bounds: Tuple[float, float] = (-6.0, 6.0),
        tau_bounds: Tuple[float, float] = (0.05, 0.95),
    ) -> "ParameterSpace":
        """Derive the search space from a :class:`FilterModel`.

        Args:
            model: The model whose constraints/combiner define the space.
            include_combiner: Include the per-constraint fusion weights.
            include_bias: Include the combiner logit bias.
            include_tau: Include the decision threshold ``tau``.
            weight_bounds: Bounds for every fusion weight.
            bias_bounds: Bounds for the bias.
            tau_bounds: Bounds for ``tau``.

        Returns:
            The assembled :class:`ParameterSpace`.
        """
        dims: List[Dimension] = []
        for c in model.constraints:
            for pname, spec in c.param_schema.items():
                init = spec.init if spec.init is not None else 0.5 * (spec.lo + spec.hi)
                dims.append(
                    Dimension(f"{c.name}::{pname}", spec.lo, spec.hi, float(init), spec.log)
                )
        if include_combiner:
            for name, w in zip(model.combiner.names, model.combiner.weights):
                lo, hi = weight_bounds
                dims.append(Dimension(f"{W_PREFIX}{name}", lo, hi, float(np.clip(w, lo, hi))))
        if include_bias:
            lo, hi = bias_bounds
            dims.append(Dimension(BIAS_KEY, lo, hi, float(np.clip(model.combiner.bias, lo, hi))))
        if include_tau:
            lo, hi = tau_bounds
            dims.append(Dimension(TAU_KEY, lo, hi, float(np.clip(0.5, lo, hi))))
        return cls(dims)

    def initial(self) -> Dict[str, float]:
        """Return the reference (init) point of every dimension."""
        return {d.name: d.init for d in self.dimensions}

    def clip(self, theta: Dict[str, float]) -> Dict[str, float]:
        """Clamp a theta dict to the space bounds (unknown keys passed through unchanged)."""
        by_name = {d.name: d for d in self.dimensions}
        return {k: (by_name[k].clip(v) if k in by_name else v) for k, v in theta.items()}

    def suggest_optuna(self, trial: "optuna.trial.Trial") -> Dict[str, float]:
        """Sample one point via an Optuna trial (log-uniform where ``Dimension.log``).

        Args:
            trial: The Optuna trial.

        Returns:
            A flat ``{name: value}`` theta (includes ``tau`` when present).
        """
        out: Dict[str, float] = {}
        for d in self.dimensions:
            if d.lo == d.hi:
                out[d.name] = d.lo
            else:
                out[d.name] = float(trial.suggest_float(d.name, d.lo, d.hi, log=d.log))
        return out

    def sample_random(self, rng: Optional[np.random.Generator] = None) -> Dict[str, float]:
        """Draw one uniform (log-uniform where flagged) random point.

        Args:
            rng: Optional numpy Generator (seeded default otherwise).

        Returns:
            A flat ``{name: value}`` theta.
        """
        rng = rng if rng is not None else np.random.default_rng()
        out: Dict[str, float] = {}
        for d in self.dimensions:
            if d.lo == d.hi:
                out[d.name] = d.lo
            elif d.log:
                out[d.name] = float(math.exp(rng.uniform(math.log(d.lo), math.log(d.hi))))
            else:
                out[d.name] = float(rng.uniform(d.lo, d.hi))
        return out
