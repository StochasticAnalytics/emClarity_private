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

**Physics sign priors (the load-bearing constraint on the combiner weights).** The fusion head is
``keep_prob = sigmoid(bias + Σ_j w_j · s_j)`` (``model/filter_model.py``), and **every** constraint
emits a *false-positive score* ``s_j ∈ [0, 1]`` that INCREASES with FP-ness (a compact extreme-CC
gold/ice cluster, an incoherent/high-residual neighbourhood, an interior/mis-facing membrane hit,
an off-surface isolated peak — all push ``s_j`` up). For such an FP axis to monotonically increase
the probability-of-being-FP (i.e. *lower* keep-prob), its weight must be **non-positive** (``w_j ≤
0``): then ``∂ keep_prob / ∂ s_j ≤ 0`` everywhere, so keep-prob is monotone non-increasing in each
axis and ``P(FP) = 1 − keep`` monotone non-decreasing. Without this prior the black-box tuner is
free to flip a weight positive and "explain" the physics backwards — exactly the counter-intuitive
``gold_ice +1.41`` / ``isolation +7.43`` head the round_4_fitted cross-tab exposed. So
:meth:`ParameterSpace.from_model` now bounds each fusion weight to its physical half-line
(``[-mag, 0]`` for an FP axis, ``[0, mag]`` for a KEEP-supporting axis, ``[-mag, mag]`` only when a
sign is explicitly waived), and seeds the init on the correct side. This is a hard search-space
constraint, not a soft penalty: the tuner *cannot* propose a sign-violating weight.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Tuple

import numpy as np

from ..model.filter_model import FilterModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    import optuna

__all__ = [
    "Dimension",
    "ParameterSpace",
    "TAU_KEY",
    "BIAS_KEY",
    "W_PREFIX",
    "FP_INCREASING_SIGN",
    "KEEP_INCREASING_SIGN",
    "SIGN_FREE",
    "signed_weight_bounds",
]

TAU_KEY: str = "tau"
"""Reserved dimension name for the keep-probability decision threshold."""
BIAS_KEY: str = "combiner::bias"
"""Flat theta key for the combiner logit bias."""
W_PREFIX: str = "combiner::w::"
"""Flat theta key prefix for the per-constraint combiner fusion weights."""

FP_INCREASING_SIGN: int = -1
"""Physics sign of an axis whose score rises with FP-ness: weight forced ``<= 0`` (higher score ->
lower keep-prob -> higher P(FP)). Every constraint in this package is such an axis, so this is the
default sign :meth:`ParameterSpace.from_model` applies to every fusion weight."""
KEEP_INCREASING_SIGN: int = +1
"""Physics sign of an axis whose score supports a TRUE target: weight forced ``>= 0`` (higher score
-> higher keep-prob). Reserved for a future keep-supporting score (e.g. coherent-in-outer-membrane
membership) — no current constraint uses it, but the mechanism is wired so one can be added."""
SIGN_FREE: int = 0
"""Explicitly waive the sign prior for one weight: bounds span ``[-mag, mag]`` (both signs). Use
only for a genuinely ambiguous axis; the default is to constrain every FP axis."""


def signed_weight_bounds(sign: int, magnitude: float) -> Tuple[float, float]:
    """Return the ``(lo, hi)`` bounds for a fusion weight given its physics sign.

    Args:
        sign: ``FP_INCREASING_SIGN`` (``-1`` -> ``[-mag, 0]``), ``KEEP_INCREASING_SIGN``
            (``+1`` -> ``[0, mag]``), or ``SIGN_FREE`` (``0`` -> ``[-mag, mag]``).
        magnitude: The non-negative bound magnitude ``mag`` (its absolute value is used).

    Returns:
        The ``(lo, hi)`` weight bounds enforcing the sign prior.
    """
    m = abs(float(magnitude))
    if sign < 0:
        return (-m, 0.0)
    if sign > 0:
        return (0.0, m)
    return (-m, m)


def _signed_weight_init(config_weight: float, sign: int, lo: float, hi: float) -> float:
    """Seed a fusion-weight init on the physically-correct side of zero, clipped to ``[lo, hi]``.

    The configured combiner weight only supplies a *magnitude*; its stored sign may be the opposite
    convention (e.g. a physics config that lists positive FP weights for a ``fp_logit`` head). So we
    take ``copysign(|config_weight|, sign)`` — magnitude preserved, physical sign forced — and clip.
    A zero magnitude seeds a mild ``sign * 1.0`` so the axis does not start inert exactly at the
    boundary.
    """
    if sign == 0:
        return float(min(hi, max(lo, config_weight)))
    mag = abs(float(config_weight))
    if mag == 0.0:
        mag = 1.0
    return float(min(hi, max(lo, math.copysign(mag, sign))))


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
        weight_signs: Optional[Mapping[str, int]] = None,
        default_weight_sign: int = FP_INCREASING_SIGN,
    ) -> "ParameterSpace":
        """Derive the search space from a :class:`FilterModel`, applying the physics sign priors.

        Every fusion weight is bounded to its physical half-line (module docstring): an FP axis
        (``default_weight_sign = FP_INCREASING_SIGN``, the default for every constraint here) gets
        ``[-mag, 0]`` so a higher FP score can only *lower* keep-prob, never raise it. ``mag`` is
        the larger absolute end of ``weight_bounds`` (the ``(-8, 8)`` default -> ``mag = 8``). Pass
        ``weight_signs`` to override individual axes (e.g. a keep-supporting score -> ``[0, mag]``)
        or ``SIGN_FREE`` to waive the prior for one axis.

        Args:
            model: The model whose constraints/combiner define the space.
            include_combiner: Include the per-constraint fusion weights.
            include_bias: Include the combiner logit bias.
            include_tau: Include the decision threshold ``tau``.
            weight_bounds: The symmetric magnitude source for the fusion weights; the sign prior
                restricts each weight to the appropriate half of ``[-mag, mag]``.
            bias_bounds: Bounds for the bias.
            tau_bounds: Bounds for ``tau``.
            weight_signs: Optional per-constraint sign overrides (``constraint.name -> {-1,0,+1}``);
                unlisted axes use ``default_weight_sign``.
            default_weight_sign: The sign applied to every fusion weight not in ``weight_signs``
                (``FP_INCREASING_SIGN`` by default — every axis is an FP axis).

        Returns:
            The assembled :class:`ParameterSpace`.
        """
        signs = dict(weight_signs or {})
        magnitude = max(abs(weight_bounds[0]), abs(weight_bounds[1]))
        dims: List[Dimension] = []
        for c in model.constraints:
            for pname, spec in c.param_schema.items():
                init = spec.init if spec.init is not None else 0.5 * (spec.lo + spec.hi)
                dims.append(
                    Dimension(f"{c.name}::{pname}", spec.lo, spec.hi, float(init), spec.log)
                )
        if include_combiner:
            for name, w in zip(model.combiner.names, model.combiner.weights):
                sign = int(signs.get(name, default_weight_sign))
                lo, hi = signed_weight_bounds(sign, magnitude)
                init = _signed_weight_init(float(w), sign, lo, hi)
                dims.append(Dimension(f"{W_PREFIX}{name}", lo, hi, init))
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
