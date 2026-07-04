"""Constraint registry, shared helpers, and the :class:`ScoreCombiner` fusion head.

This module is the hub of the ``constraints`` subsystem (DESIGN §7). It hosts:

* :data:`CONSTRAINT_REGISTRY` / :func:`register_constraint` — every concrete
  :class:`~mito_filter.constraints.base.Constraint` decorates itself in here so a pipeline is
  built from a YAML stanza (``@register_constraint("gold_ice_cluster")``). It mirrors the
  feature engine's ``FEATURE_REGISTRY``.
* :data:`COMBINER_REGISTRY` / :func:`register_combiner` — the fusion heads.
* small shared helpers (:func:`get_feature`, :func:`sigmoid`, :func:`soft_or`,
  :class:`_BaseConstraint`) used by every constraint to read a feature column by any of its
  aliases (bridging the DESIGN feature names and the engine's concrete ``produces`` names),
  resolve tunable parameters from ``theta`` (falling back to the YAML config then the
  :class:`~mito_filter.constraints.base.ParamSpec` init), and combine soft per-term penalties.

Kept torch-free (numpy only) so it imports and runs on the CPU path. Every constraint returns
a per-candidate **false-positive score** (higher == more likely a false positive); the combiner
fuses those into a keep-probability so that a higher FP score lowers the keep-probability.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Type

import numpy as np
from numpy.typing import NDArray

from ..core.registry import Registry
from ..features.extractor import FeatureMatrix
from .base import Constraint, ConstraintResult, ParamDict, ParamSpec

__all__ = [
    "CONSTRAINT_REGISTRY",
    "COMBINER_REGISTRY",
    "register_constraint",
    "register_combiner",
    "get_feature",
    "sigmoid",
    "soft_or",
    "ScoreCombiner",
]

CONSTRAINT_REGISTRY: Registry[Constraint] = Registry("constraint")
"""Registry every concrete :class:`Constraint` registers into (YAML instantiation)."""

COMBINER_REGISTRY: Registry["ScoreCombiner"] = Registry("combiner")
"""Registry of fusion heads (the model head that maps constraint scores -> keep-prob)."""

register_constraint: Callable[[str], Callable[[Type[Constraint]], Type[Constraint]]] = (
    CONSTRAINT_REGISTRY.register
)
"""Class decorator: ``@register_constraint("name")`` records a :class:`Constraint` subclass."""

register_combiner: Callable[[str], Callable[[Type["ScoreCombiner"]], Type["ScoreCombiner"]]] = (
    COMBINER_REGISTRY.register
)
"""Class decorator: ``@register_combiner("name")`` records a :class:`ScoreCombiner` subclass."""


# --------------------------------------------------------------------------- #
# Shared numeric helpers.                                                      #
# --------------------------------------------------------------------------- #
def sigmoid(x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Numerically-stable logistic sigmoid (argument clipped to ``[-60, 60]``).

    Args:
        x: The logit array.

    Returns:
        ``1 / (1 + exp(-x))`` elementwise in ``(0, 1)``.
    """
    z = np.clip(np.asarray(x, dtype=np.float64), -60.0, 60.0)
    out: NDArray[np.float64] = 1.0 / (1.0 + np.exp(-z))
    return out


def soft_or(terms: Sequence[NDArray[np.float64]], n: int) -> NDArray[np.float64]:
    """Probabilistic soft-OR of per-candidate penalty terms in ``[0, 1]``.

    ``soft_or([a, b]) = 1 - (1 - a)(1 - b)`` — any strong term drives the result high, and the
    result is monotone non-decreasing in every term. Each term is clipped to ``[0, 1]`` first.

    Args:
        terms: The per-candidate penalty terms (each shape ``(N,)``).
        n: The candidate count (used when ``terms`` is empty).

    Returns:
        The combined ``(N,)`` penalty in ``[0, 1]``.
    """
    out: NDArray[np.float64] = np.zeros(int(n), dtype=np.float64)
    for term in terms:
        t = np.clip(np.asarray(term, dtype=np.float64), 0.0, 1.0)
        out = 1.0 - (1.0 - out) * (1.0 - t)
    return out


def get_feature(feats: FeatureMatrix, names: Tuple[str, ...]) -> Optional[NDArray[np.float64]]:
    """Return the first present feature column among ``names`` (alias resolution).

    The DESIGN constraint ``needs_features`` names (e.g. ``cc_cluster_density``) do not always
    match the concrete extractor ``produces`` names (e.g. ``cc_cluster_z``); each constraint
    passes an alias tuple so it works against either. A genuinely absent feature returns
    ``None`` so the caller contributes a neutral (zero) term (DESIGN §5 mixed-availability).

    Args:
        feats: The per-candidate feature matrix.
        names: Candidate column names to try, in preference order.

    Returns:
        The ``(N,)`` float64 column, or ``None`` if none of ``names`` is present.
    """
    for nm in names:
        if nm in feats:
            return np.asarray(feats.column(nm), dtype=np.float64).reshape(-1)
    return None


def finite_mask(arr: NDArray[np.float64]) -> NDArray[np.bool_]:
    """Boolean mask of finite (non-NaN, non-inf) entries.

    Args:
        arr: The array to test.

    Returns:
        A boolean array; ``True`` where ``arr`` is finite (a trusted, present value).
    """
    return np.isfinite(np.asarray(arr, dtype=np.float64))


class _BaseConstraint(Constraint):
    """Shared parameter-resolution + result-wrapping for the concrete constraints.

    Subclasses set :attr:`~mito_filter.constraints.base.Constraint.name`,
    :attr:`~mito_filter.constraints.base.Constraint.needs_features`, and
    :attr:`~mito_filter.constraints.base.Constraint.param_schema`, accept their YAML
    parameters in ``__init__`` (stored on ``self.params``), and implement
    :meth:`~mito_filter.constraints.base.Constraint.forward`.
    """

    def resolved(self, theta: Optional[ParamDict]) -> Dict[str, float]:
        """Resolve every schema parameter for this call.

        Preference order per key: the value in ``theta`` (the tuner's proposal), else the YAML
        config value on ``self.params``, else the :class:`ParamSpec` init. The result is
        clipped into the spec bounds.

        Args:
            theta: The tuner-proposed parameter mapping (may be ``None`` / partial).

        Returns:
            A fully-resolved, bounds-clipped ``name -> value`` mapping.
        """
        out: Dict[str, float] = {}
        for key, spec in self.param_schema.items():
            if theta is not None and key in theta:
                value = float(theta[key])
            elif key in self.params:
                value = float(self.params[key])  # type: ignore[arg-type]
            else:
                assert spec.init is not None  # set in ParamSpec.__post_init__
                value = float(spec.init)
            out[key] = spec.clip(value)
        return out

    def result(self, feats: FeatureMatrix, theta: Optional[ParamDict] = None) -> ConstraintResult:
        """Wrap :meth:`forward` into a :class:`ConstraintResult` (convenience/diagnostics).

        Args:
            feats: The per-candidate feature matrix.
            theta: The tunable parameter values (defaults resolved when ``None``).

        Returns:
            A :class:`ConstraintResult` carrying the per-hit scores and resolved params.
        """
        score = self.forward(feats, theta or {})
        return ConstraintResult(
            per_hit_score=score, name=self.name, params_used=self.resolved(theta)
        )


# --------------------------------------------------------------------------- #
# The fusion head.                                                             #
# --------------------------------------------------------------------------- #
@register_combiner("score_combiner")
class ScoreCombiner:
    """Fuse per-constraint false-positive scores into a keep-probability (DESIGN §7).

    Two modes:

    * ``logit`` (default) — ``fp_logit = bias + sum_i w_i * s_i`` and ``keep_prob =
      sigmoid(-fp_logit)``, so a higher fused FP score gives a lower keep-probability. With all
      constraints neutral (``s_i == 0``) and ``bias == 0`` the keep-probability is ``0.5``.
    * ``weighted`` — ``fp = clip(bias + sum_i w_i * s_i, 0, 1)`` and ``keep_prob = 1 - fp``.

    This is the head of the ``FilterModel`` (``model/filter_model.py`` wraps it as an
    ``nn.Module``); kept numpy-only here so scan runs on the CPU path.

    Args:
        constraints: The constraint instances to fuse (evaluated in order).
        weights: Optional per-constraint weight overrides keyed by ``constraint.name``
            (default weight ``1.0``).
        bias: The fusion bias (a global keep/reject offset).
        mode: ``"logit"`` or ``"weighted"``.

    Attributes:
        constraints: The fused constraints.
        weights: The per-constraint weight overrides.
        bias: The fusion bias.
        mode: The fusion mode.
    """

    def __init__(
        self,
        constraints: Sequence[Constraint],
        *,
        weights: Optional[Mapping[str, float]] = None,
        bias: float = 0.0,
        mode: str = "logit",
    ) -> None:
        self.constraints: List[Constraint] = list(constraints)
        self.weights: Dict[str, float] = {k: float(v) for k, v in (weights or {}).items()}
        self.bias: float = float(bias)
        if mode not in ("logit", "weighted"):
            raise ValueError(f"unknown combiner mode '{mode}' (logit|weighted)")
        self.mode: str = mode

    @property
    def param_schema(self) -> Dict[str, ParamSpec]:
        """Tunable fusion parameters: one non-negative weight per constraint + ``bias``."""
        schema: Dict[str, ParamSpec] = {"bias": ParamSpec(-6.0, 6.0, 0.0)}
        for c in self.constraints:
            schema[f"w_{c.name}"] = ParamSpec(0.0, 6.0, 1.0)
        return schema

    def _weight(self, name: str, theta: Optional[ParamDict]) -> float:
        """Resolve constraint ``name``'s fusion weight from ``theta`` / config / default 1.0."""
        key = f"w_{name}"
        if theta is not None and key in theta:
            return float(theta[key])
        return self.weights.get(name, 1.0)

    def _bias(self, theta: Optional[ParamDict]) -> float:
        """Resolve the fusion bias from ``theta`` / config."""
        if theta is not None and "bias" in theta:
            return float(theta["bias"])
        return self.bias

    def per_constraint_scores(
        self, feats: FeatureMatrix, theta: Optional[ParamDict] = None
    ) -> Dict[str, NDArray[np.float64]]:
        """Return each constraint's per-candidate FP score, keyed by constraint name.

        Args:
            feats: The per-candidate feature matrix.
            theta: The tunable parameter values (defaults resolved when ``None``).

        Returns:
            Mapping ``constraint.name -> (N,)`` FP-score array.
        """
        return {
            c.name: np.asarray(c.forward(feats, theta or {}), dtype=np.float64).reshape(-1)
            for c in self.constraints
        }

    def fp_logit(
        self, feats: FeatureMatrix, theta: Optional[ParamDict] = None
    ) -> NDArray[np.float64]:
        """Return the fused false-positive logit ``bias + sum_i w_i * s_i``.

        Args:
            feats: The per-candidate feature matrix.
            theta: The tunable parameter values.

        Returns:
            The ``(N,)`` fused FP logit (higher == more likely a false positive).
        """
        n = feats.n
        total: NDArray[np.float64] = np.full(n, self._bias(theta), dtype=np.float64)
        for name, score in self.per_constraint_scores(feats, theta).items():
            total = total + self._weight(name, theta) * score
        return total

    def keep_prob(
        self, feats: FeatureMatrix, theta: Optional[ParamDict] = None
    ) -> NDArray[np.float32]:
        """Return the per-candidate keep-probability in ``(0, 1)``.

        Args:
            feats: The per-candidate feature matrix.
            theta: The tunable parameter values.

        Returns:
            The ``(N,)`` keep-probability (higher == more likely a true positive).
        """
        logit = self.fp_logit(feats, theta)
        if self.mode == "weighted":
            keep = 1.0 - np.clip(logit, 0.0, 1.0)
        else:
            keep = sigmoid(-logit)
        return np.asarray(keep, dtype=np.float32)

    def decide(
        self, feats: FeatureMatrix, tau: float, theta: Optional[ParamDict] = None
    ) -> NDArray[np.bool_]:
        """Return the boolean keep mask ``keep_prob >= tau``.

        Args:
            feats: The per-candidate feature matrix.
            tau: The keep-probability decision threshold.
            theta: The tunable parameter values.

        Returns:
            A ``(N,)`` boolean array; ``True`` keeps the candidate.
        """
        return np.asarray(self.keep_prob(feats, theta) >= float(tau), dtype=np.bool_)
