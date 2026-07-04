"""Constraint plugin API: ParamSpec, ConstraintResult, and the Constraint ABC.

A :class:`Constraint` maps the per-candidate :class:`~mito_filter.features.extractor.
FeatureMatrix` plus a tuned parameter dict to a per-candidate false-positive support/penalty.
Combinatorial pieces (cluster labels, RANSAC fits) are precomputed as features, so
:meth:`Constraint.forward` sees numbers. :class:`ParamSpec` and :class:`ConstraintResult`
are FULLY implemented; the concrete physics constraints live in sibling modules.

Kept torch-free so it imports on the CPU path; ``forward`` returns an array (numpy on the
CPU path, a torch tensor when a differentiable head is used).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Mapping, Optional, Tuple

from numpy.typing import NDArray

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..features.extractor import FeatureMatrix

ParamDict = Mapping[str, float]
"""A resolved parameter mapping name -> value handed to :meth:`Constraint.forward`."""


@dataclass(frozen=True)
class ParamSpec:
    """A tunable parameter's bounds, initial value, and scale.

    Args:
        lo: Lower bound (inclusive).
        hi: Upper bound (inclusive).
        init: Initial value; defaults to the midpoint if omitted.
        log: If True, the optimizer samples/searches this parameter in log-space.

    Attributes:
        lo: The lower bound.
        hi: The upper bound.
        init: The initial value.
        log: Whether the parameter is log-scaled.
    """

    lo: float
    hi: float
    init: Optional[float] = None
    log: bool = False

    def __post_init__(self) -> None:
        if self.hi < self.lo:
            raise ValueError(f"ParamSpec hi {self.hi} < lo {self.lo}")
        if self.log and self.lo <= 0:
            raise ValueError("log-scaled ParamSpec requires lo > 0")
        if self.init is None:
            object.__setattr__(self, "init", 0.5 * (self.lo + self.hi))
        elif not (self.lo <= self.init <= self.hi):
            raise ValueError(f"ParamSpec init {self.init} outside [{self.lo}, {self.hi}]")

    def clip(self, value: float) -> float:
        """Clamp ``value`` into ``[lo, hi]``.

        Args:
            value: The value to clamp.

        Returns:
            The clamped value.
        """
        return min(self.hi, max(self.lo, value))


@dataclass
class ConstraintResult:
    """The per-candidate output of a constraint.

    Args:
        per_hit_score: ``(N,)`` continuous false-positive-likelihood contribution.
        per_hit_flag: Optional ``(N,)`` boolean hard-reject mask.
        diagnostics: Free-form per-constraint diagnostics for reporting.
        params_used: The resolved parameter values that produced this result.
        name: The constraint's name.

    Attributes:
        per_hit_score: The continuous scores.
        per_hit_flag: The optional hard-reject mask.
        diagnostics: Diagnostics mapping.
        params_used: Parameters used.
        name: The constraint name.
    """

    per_hit_score: NDArray
    name: str
    per_hit_flag: Optional[NDArray] = None
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    params_used: Mapping[str, float] = field(default_factory=dict)


class Constraint(ABC):
    """A pluggable false-positive discriminator over the cached feature matrix.

    Subclasses set :attr:`name`, :attr:`needs_features`, and :attr:`param_schema`, accept
    their YAML parameters via ``__init__``, and implement :meth:`forward`.

    Attributes:
        name: The constraint's registry/report name.
        needs_features: Feature column names this constraint consumes (drives the engine).
        param_schema: Tunable-parameter schema name -> :class:`ParamSpec` exposed to the tuner.
    """

    name: str = ""
    needs_features: Tuple[str, ...] = ()
    param_schema: Dict[str, ParamSpec] = {}

    def __init__(self, **params: object) -> None:
        """Store constraint configuration (a YAML stanza).

        Args:
            **params: Constraint-specific configuration values.
        """
        self.params: Dict[str, object] = dict(params)

    @abstractmethod
    def forward(self, feats: "FeatureMatrix", theta: ParamDict) -> NDArray:
        """Compute this constraint's per-candidate penalty/support.

        Args:
            feats: The cached per-candidate feature matrix (superset of
                :attr:`needs_features`).
            theta: The resolved tunable parameter values for this call.

        Returns:
            A ``(N,)`` array of per-candidate contributions (torch-diffable where the
            combiner head needs gradients; numpy on the CPU path).
        """
        raise NotImplementedError
