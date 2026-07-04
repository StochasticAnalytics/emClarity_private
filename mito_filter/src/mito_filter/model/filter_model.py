"""The single ``FilterModel`` object: constraints + a combiner head -> keep-probability.

ONE object serves all three consumers (DESIGN §7):

* **scan** — pure forward: :meth:`FilterModel.forward` maps the cached feature matrix to a
  per-candidate keep-probability, :meth:`FilterModel.decide` thresholds it at ``tau``.
* **black-box optimizers** (optuna / scipy / CMA) — :meth:`FilterModel.forward_with_theta`
  evaluates a *proposed* flat parameter dict without mutating the model.
* **autograd** — the *combiner head only* is differentiable. A pure-numpy :class:`Combiner`
  provides analytic gradients (BCE), so training + tests run with **no torch**. When torch is
  installed, :meth:`Combiner.torch_head` returns an ``nn.Module`` for the same head.

The load-bearing feature knobs (cluster thresholds, coherence radii, surface-fit tolerances)
live on the non-differentiable constraint side and are tuned by the black-box path; the
differentiable head only fuses the constraint outputs. This mirrors the DESIGN decision that
black-box optimization is primary and autograd covers the combiner weights only.

Note (integration): the DESIGN types ``FilterModel`` as ``nn.Module`` when torch is present.
torch is a deferred/optional dependency and a *dynamic* base class is not mypy-strict clean, so
``FilterModel`` is a plain class exposing the **same** ``forward`` / ``decide`` / ``theta``
interface; the differentiable head is reached through :meth:`Combiner.torch_head`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Tuple, cast

import numpy as np
from numpy.typing import NDArray

from ..constraints.base import Constraint, ParamDict

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..features.extractor import FeatureExtractor, FeatureMatrix

__all__ = [
    "Combiner",
    "FilterModel",
    "ModelRequirements",
    "required_features",
    "required_fields",
    "model_requirements",
]

# Flat-theta namespacing. "::" cannot appear in a constraint or param name here, so the
# flat keys are unambiguous and reversible.
_SEP = "::"
_W_PREFIX = f"combiner{_SEP}w{_SEP}"
_BIAS_KEY = f"combiner{_SEP}bias"


def _sigmoid(x: NDArray) -> NDArray:
    """Numerically stable logistic sigmoid.

    Args:
        x: Input array (logits).

    Returns:
        ``1 / (1 + exp(-x))`` computed without overflow, float64.
    """
    out = np.empty_like(x, dtype=np.float64)
    pos = x >= 0.0
    out[pos] = 1.0 / (1.0 + np.exp(-x[pos]))
    ex = np.exp(x[~pos])
    out[~pos] = ex / (1.0 + ex)
    return out


@dataclass
class Combiner:
    """The differentiable fusion head: constraint scores -> keep-probability.

    Computes ``keep_prob = sigmoid(bias + S @ weights)`` where ``S`` is the
    ``(N, C)`` matrix of per-candidate constraint scores. Constraint scores are
    false-positive *support* (higher = more likely a false positive), so the default
    weight is negative: a larger penalty pushes the keep-probability down.

    Args:
        names: The ``C`` constraint names, in ``weights`` column order.
        weights: The ``(C,)`` per-constraint fusion weights.
        bias: The scalar logit bias.

    Attributes:
        names: Constraint names in column order.
        weights: The fusion weights.
        bias: The logit bias.
    """

    names: List[str]
    weights: NDArray
    bias: float = 0.0

    def __post_init__(self) -> None:
        self.names = list(self.names)
        self.weights = np.asarray(self.weights, dtype=np.float64).reshape(-1)
        if self.weights.shape[0] != len(self.names):
            raise ValueError(
                f"weights length {self.weights.shape[0]} != n constraints {len(self.names)}"
            )
        self.bias = float(self.bias)

    @classmethod
    def default(
        cls, names: Sequence[str], *, weight: float = -1.0, bias: float = 0.0
    ) -> "Combiner":
        """Build a combiner with a uniform initial weight per constraint.

        Args:
            names: The constraint names (define column order).
            weight: Initial value for every fusion weight (negative -> penalty lowers keep).
            bias: Initial logit bias.

        Returns:
            An initialized :class:`Combiner`.
        """
        names = list(names)
        return cls(names, np.full(len(names), float(weight), dtype=np.float64), bias)

    def logits(self, scores: NDArray) -> NDArray:
        """Return the ``(N,)`` fusion logits for a constraint-score matrix.

        Args:
            scores: The ``(N, C)`` per-candidate constraint scores.

        Returns:
            The ``(N,)`` logits ``bias + scores @ weights``.
        """
        s = np.asarray(scores, dtype=np.float64)
        n = s.shape[0]
        if s.ndim != 2 or s.shape[1] != self.weights.shape[0]:
            raise ValueError(
                f"scores shape {s.shape} incompatible with {self.weights.shape[0]} weights"
            )
        if self.weights.shape[0] == 0:
            return np.full(n, self.bias, dtype=np.float64)
        return np.asarray(self.bias + s @ self.weights, dtype=np.float64)

    def forward(self, scores: NDArray) -> NDArray:
        """Return the ``(N,)`` keep-probability in ``(0, 1)``.

        Args:
            scores: The ``(N, C)`` per-candidate constraint scores.

        Returns:
            The ``(N,)`` keep-probabilities.
        """
        return _sigmoid(self.logits(scores))

    def bce_grad(self, scores: NDArray, targets: NDArray) -> Tuple[NDArray, float]:
        """Analytic gradient of mean binary-cross-entropy w.r.t. weights and bias.

        Loss ``L = mean( -y*log(p) - (1-y)*log(1-p) )`` with ``p = forward(scores)``.
        For a sigmoid head ``dL/dlogit = (p - y) / N`` exactly, so the head is
        differentiable in pure numpy (verified by finite differences in the unit test).

        Args:
            scores: The ``(N, C)`` constraint scores.
            targets: The ``(N,)`` keep labels in ``{0, 1}`` (1 = keep / true target).

        Returns:
            A tuple ``(grad_weights (C,), grad_bias)``.
        """
        s = np.asarray(scores, dtype=np.float64)
        y = np.asarray(targets, dtype=np.float64).reshape(-1)
        p = self.forward(s)
        n = max(p.shape[0], 1)
        resid = (p - y) / n
        grad_w = s.T @ resid if self.weights.shape[0] else np.zeros(0, dtype=np.float64)
        grad_b = float(resid.sum())
        return grad_w, grad_b

    def to_config(self) -> Dict[str, object]:
        """Serialize this head to a plain dict for :class:`FittedConfig.combiner`.

        Returns:
            ``{"kind": "logit", "names": [...], "weights": [...], "bias": float}``.
        """
        return {
            "kind": "logit",
            "names": list(self.names),
            "weights": [float(w) for w in self.weights],
            "bias": float(self.bias),
        }

    @classmethod
    def from_config(cls, cfg: Mapping[str, object]) -> "Combiner":
        """Rebuild a combiner from a :meth:`to_config` dict.

        Args:
            cfg: A mapping with ``names``, ``weights`` and optional ``bias``.

        Returns:
            The reconstructed :class:`Combiner`.
        """
        raw_names = cast(Sequence[str], cfg.get("names", []))
        names = list(raw_names)
        weights = np.asarray(cfg.get("weights", []), dtype=np.float64)
        bias = float(cast(float, cfg.get("bias", 0.0)))
        if weights.size == 0 and names:
            weights = np.full(len(names), -1.0, dtype=np.float64)
        return cls(names, weights, bias)

    def torch_head(self) -> object:  # pragma: no cover - optional dependency
        """Return an ``nn.Module`` mirroring this head (autograd path).

        Returns:
            A torch ``nn.Linear(C, 1)`` initialized from ``weights``/``bias`` whose
            ``sigmoid`` output matches :meth:`forward`.

        Raises:
            RuntimeError: If torch is not importable.
        """
        try:
            import torch
            from torch import nn
        except Exception as exc:
            raise RuntimeError("torch_head requires torch, which is not installed") from exc

        head = nn.Linear(self.weights.shape[0], 1, bias=True)
        with torch.no_grad():
            head.weight.copy_(torch.as_tensor(self.weights, dtype=torch.float32).reshape(1, -1))
            head.bias.copy_(torch.as_tensor([self.bias], dtype=torch.float32))
        return head


@dataclass(frozen=True)
class ModelRequirements:
    """The exact features + fields a constraint set needs (drives engine + planner).

    Args:
        features: Ordered union of every constraint's ``needs_features``.
        fields: Ordered union of the ``needs_fields`` of the extractors that produce
            those features (empty when no extractor set is supplied).

    Attributes:
        features: The needed feature column names.
        fields: The needed dense-field names.
    """

    features: Tuple[str, ...]
    fields: Tuple[str, ...] = ()


def _ordered_union(seqs: Sequence[Sequence[str]]) -> Tuple[str, ...]:
    """Return the order-preserving de-duplicated union of several string sequences."""
    seen: Dict[str, None] = {}
    for seq in seqs:
        for item in seq:
            seen.setdefault(item, None)
    return tuple(seen)


def required_features(constraints: Sequence[Constraint]) -> Tuple[str, ...]:
    """Return the ordered union of every constraint's ``needs_features``.

    This is the ``FeatureSpec`` the feature engine must compute (DESIGN §7): compute
    exactly these columns, no more.

    Args:
        constraints: The constraints the model fuses.

    Returns:
        The needed feature column names, de-duplicated, first-seen order.
    """
    return _ordered_union([tuple(c.needs_features) for c in constraints])


def required_fields(
    constraints: Sequence[Constraint],
    extractors: Sequence["FeatureExtractor"],
) -> Tuple[str, ...]:
    """Return the ordered union of dense-field names needed for the constraints' features.

    Maps each needed feature to the extractor(s) that ``produces`` it and unions their
    ``needs_fields`` — the exact set handed to ``FieldRegistry.plan`` (DESIGN §7). Features
    with no producing extractor are skipped (their fields simply aren't requested).

    Args:
        constraints: The constraints the model fuses.
        extractors: The available feature extractors.

    Returns:
        The needed dense-field names, de-duplicated, first-seen order.
    """
    needed = set(required_features(constraints))
    fields: List[Sequence[str]] = []
    for ex in extractors:
        if needed.intersection(ex.produces):
            fields.append(tuple(ex.needs_fields))
    return _ordered_union(fields)


def model_requirements(
    constraints: Sequence[Constraint],
    extractors: Optional[Sequence["FeatureExtractor"]] = None,
) -> ModelRequirements:
    """Bundle the needed features (+ fields, if extractors are known) for a constraint set.

    Args:
        constraints: The constraints the model fuses.
        extractors: Optional available extractors; when given, resolves dense-field names.

    Returns:
        A :class:`ModelRequirements` with ``features`` always populated and ``fields``
        populated iff ``extractors`` is supplied.
    """
    feats = required_features(constraints)
    flds = required_fields(constraints, extractors) if extractors is not None else ()
    return ModelRequirements(features=feats, fields=flds)


class FilterModel:
    """A theta-parameterized fusion of constraints -> per-candidate keep-probability.

    Holds an ordered list of :class:`~mito_filter.constraints.base.Constraint` objects and
    a :class:`Combiner`. Constraint scores are computed on the CPU (numpy) and fused by the
    differentiable head. The same object is used forward-only by scan, functionally by the
    black-box optimizers (:meth:`forward_with_theta`), and (via :meth:`Combiner.torch_head`)
    by autograd on the head weights.

    Args:
        constraints: The constraints to fuse (define combiner column order).
        combiner: The fusion head; defaults to a uniform-weight :class:`Combiner`.

    Attributes:
        constraints: The fused constraints.
        combiner: The fusion head.
    """

    def __init__(
        self,
        constraints: Sequence[Constraint],
        combiner: Optional[Combiner] = None,
    ) -> None:
        self.constraints: List[Constraint] = list(constraints)
        names = [c.name for c in self.constraints]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate constraint names: {names}")
        if combiner is None:
            combiner = Combiner.default(names)
        elif combiner.names != names:
            raise ValueError(f"combiner names {combiner.names} do not match constraints {names}")
        self.combiner: Combiner = combiner

    # -- feature / field requirements -------------------------------------------------

    @property
    def needs_features(self) -> Tuple[str, ...]:
        """The ordered union of every constraint's ``needs_features``."""
        return required_features(self.constraints)

    def requirements(
        self, extractors: Optional[Sequence["FeatureExtractor"]] = None
    ) -> ModelRequirements:
        """Return this model's :class:`ModelRequirements` (features + optional fields).

        Args:
            extractors: Optional extractors used to resolve dense-field names.

        Returns:
            The model's requirements.
        """
        return model_requirements(self.constraints, extractors)

    # -- theta round-trip ------------------------------------------------------------

    def _constraint_theta(
        self, constraint: Constraint, override: Optional[ParamDict] = None
    ) -> Dict[str, float]:
        """Resolve one constraint's current parameter values (schema init <- yaml <- override).

        Args:
            constraint: The constraint whose parameters to resolve.
            override: Optional flat theta dict supplying namespaced overrides.

        Returns:
            The resolved ``{param_name: value}`` for this constraint.
        """
        out: Dict[str, float] = {}
        for pname, spec in constraint.param_schema.items():
            value = spec.init if spec.init is not None else 0.5 * (spec.lo + spec.hi)
            if pname in constraint.params:
                value = float(constraint.params[pname])  # type: ignore[arg-type]
            if override is not None:
                key = f"{constraint.name}{_SEP}{pname}"
                if key in override:
                    value = float(override[key])
            out[pname] = spec.clip(float(value))
        return out

    @property
    def theta(self) -> Dict[str, float]:
        """The flat parameter dict: constraint params + combiner weights and bias.

        Keys are namespaced ``"<constraint>::<param>"`` for constraint parameters,
        ``"combiner::w::<constraint>"`` for fusion weights, and ``"combiner::bias"``.

        Returns:
            The flat theta mapping.
        """
        out: Dict[str, float] = {}
        for c in self.constraints:
            for pname, value in self._constraint_theta(c).items():
                out[f"{c.name}{_SEP}{pname}"] = value
        for name, w in zip(self.combiner.names, self.combiner.weights):
            out[f"{_W_PREFIX}{name}"] = float(w)
        out[_BIAS_KEY] = float(self.combiner.bias)
        return out

    def set_theta(self, theta: ParamDict) -> None:
        """Update constraint params and combiner weights from a flat theta dict.

        Unknown keys are ignored; absent keys keep their current value. Constraint values
        are clipped to their :class:`ParamSpec` bounds.

        Args:
            theta: A flat theta mapping (see :attr:`theta`).
        """
        for c in self.constraints:
            for pname, spec in c.param_schema.items():
                key = f"{c.name}{_SEP}{pname}"
                if key in theta:
                    c.params[pname] = spec.clip(float(theta[key]))
        for j, name in enumerate(self.combiner.names):
            key = f"{_W_PREFIX}{name}"
            if key in theta:
                self.combiner.weights[j] = float(theta[key])
        if _BIAS_KEY in theta:
            self.combiner.bias = float(theta[_BIAS_KEY])

    # -- forward / decide ------------------------------------------------------------

    def constraint_scores(
        self, feats: "FeatureMatrix", theta: Optional[ParamDict] = None
    ) -> NDArray:
        """Evaluate every constraint and stack into the ``(N, C)`` score matrix.

        Args:
            feats: The cached per-candidate feature matrix.
            theta: Optional flat theta overriding stored constraint parameters
                (does not mutate the model).

        Returns:
            The ``(N, C)`` constraint-score matrix (float64, column order = constraints).
        """
        n = feats.n
        if not self.constraints:
            return np.zeros((n, 0), dtype=np.float64)
        cols: List[NDArray] = []
        for c in self.constraints:
            resolved = self._constraint_theta(c, theta)
            score = np.asarray(c.forward(feats, resolved), dtype=np.float64).reshape(-1)
            if score.shape[0] != n:
                raise ValueError(
                    f"constraint '{c.name}' returned {score.shape[0]} scores, expected {n}"
                )
            cols.append(score)
        return np.stack(cols, axis=1)

    def forward(self, feats: "FeatureMatrix") -> NDArray:
        """Map the feature matrix to a per-candidate keep-probability in ``(0, 1)``.

        Args:
            feats: The cached per-candidate feature matrix.

        Returns:
            The ``(N,)`` keep-probabilities.
        """
        return self.combiner.forward(self.constraint_scores(feats))

    def forward_with_theta(self, feats: "FeatureMatrix", theta: ParamDict) -> NDArray:
        """Evaluate keep-probability under a *proposed* theta without mutating the model.

        This is the black-box-optimizer entry point: propose a flat theta, get the
        keep-probability, score it, discard. Both constraint parameters and combiner
        weights/bias in ``theta`` take effect for this call only.

        Args:
            feats: The cached per-candidate feature matrix.
            theta: A flat theta mapping (see :attr:`theta`).

        Returns:
            The ``(N,)`` keep-probabilities under ``theta``.
        """
        scores = self.constraint_scores(feats, theta)
        weights = self.combiner.weights.copy()
        for j, name in enumerate(self.combiner.names):
            key = f"{_W_PREFIX}{name}"
            if key in theta:
                weights[j] = float(theta[key])
        bias = float(theta[_BIAS_KEY]) if _BIAS_KEY in theta else self.combiner.bias
        head = Combiner(self.combiner.names, weights, bias)
        return head.forward(scores)

    def decide(self, feats: "FeatureMatrix", tau: float = 0.5) -> NDArray:
        """Return the boolean keep mask ``keep_prob >= tau``.

        Args:
            feats: The cached per-candidate feature matrix.
            tau: The keep-probability decision threshold.

        Returns:
            A ``(N,)`` boolean array; True = keep, False = flag as false positive.
        """
        return self.forward(feats) >= float(tau)
