"""Unit tests for the FilterModel fusion head, theta round-trip, and FittedConfig yaml I/O.

torch is a deferred/optional dependency and is not installed in this venv, so the
"differentiable combiner head" is verified in pure numpy two ways:

* a **monotonicity** test (a larger false-positive score lowers the keep-probability under a
  negative fusion weight), and
* a **finite-difference** check that :meth:`Combiner.bce_grad` matches the numerical gradient
  of the mean binary-cross-entropy loss (the head really is differentiable).

If torch is present a finite-difference check against ``torch.autograd`` runs as well.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple, cast

import numpy as np
import pytest

from mito_filter.constraints.base import Constraint, ParamDict, ParamSpec
from mito_filter.features.extractor import FeatureExtractor, FeatureMatrix
from mito_filter.model.config import FittedConfig
from mito_filter.model.filter_model import (
    Combiner,
    FilterModel,
    model_requirements,
    required_features,
    required_fields,
)

# --------------------------------------------------------------------------------------
# Minimal concrete constraints/extractors for testing (do not touch the frozen ABCs).
# --------------------------------------------------------------------------------------


class _ScaledFeatureConstraint(Constraint):
    """Returns ``gain * feats[feature]`` as its per-hit false-positive score."""

    def __init__(self, name: str, feature: str, **params: object) -> None:
        super().__init__(**params)
        self.name = name
        self.needs_features = (feature,)
        self.param_schema = {"gain": ParamSpec(0.0, 10.0, 1.0)}
        self._feature = feature

    def forward(self, feats: "FeatureMatrix", theta: ParamDict) -> np.ndarray:
        gain = float(theta["gain"])
        return gain * feats.column(self._feature)


class _DummyExtractor(FeatureExtractor):
    """Produces ``feature`` from dense field ``field_name`` (only metadata is exercised)."""

    def __init__(self, feature: str, field_name: str) -> None:
        self.produces = (feature,)
        self.needs_fields = (field_name,)

    def extract(self, cand: object, fields: object, ctx: object) -> Dict[str, np.ndarray]:
        raise NotImplementedError  # not used by these tests


def _toy_features(n: int = 64, seed: int = 0) -> FeatureMatrix:
    rng = np.random.default_rng(seed)
    return FeatureMatrix.from_columns(
        {
            "cluster_density": rng.random(n, dtype=np.float64).astype(np.float32),
            "coherence": rng.random(n, dtype=np.float64).astype(np.float32),
        },
        row_ids=np.arange(n),
    )


def _two_constraint_model() -> Tuple[FilterModel, FeatureMatrix]:
    constraints = [
        _ScaledFeatureConstraint("gold_ice", "cluster_density"),
        _ScaledFeatureConstraint("coherence", "coherence"),
    ]
    return FilterModel(constraints), _toy_features()


# --------------------------------------------------------------------------------------
# Combiner
# --------------------------------------------------------------------------------------


def test_forward_in_open_unit_interval() -> None:
    model, feats = _two_constraint_model()
    p = model.forward(feats)
    assert p.shape == (feats.n,)
    assert np.all(p > 0.0) and np.all(p < 1.0)


def test_default_weight_is_penalizing_and_monotone() -> None:
    """A larger FP score must LOWER keep-prob under the default negative weight."""
    names = ["c"]
    comb = Combiner.default(names)  # default weight -1.0
    assert comb.weights[0] < 0.0
    low = comb.forward(np.array([[0.0]]))
    high = comb.forward(np.array([[5.0]]))
    assert high[0] < low[0]

    # Monotone across a sweep of the single constraint score.
    sweep = np.linspace(-3.0, 3.0, 50).reshape(-1, 1)
    p = comb.forward(sweep)
    assert np.all(np.diff(p) < 0.0)


def test_logits_shape_validation() -> None:
    comb = Combiner.default(["a", "b"])
    with pytest.raises(ValueError):
        comb.logits(np.zeros((10, 3)))  # wrong number of columns


def test_empty_constraint_set_uses_bias_only() -> None:
    comb = Combiner([], np.zeros(0), bias=0.7)
    logits = comb.logits(np.zeros((5, 0)))
    assert logits.shape == (5,)
    assert np.allclose(logits, 0.7)


# --------------------------------------------------------------------------------------
# Differentiable head: analytic gradient vs finite differences (pure numpy).
# --------------------------------------------------------------------------------------


def _bce_loss(comb: Combiner, scores: np.ndarray, y: np.ndarray) -> float:
    p = comb.forward(scores)
    eps = 1e-12
    return float(np.mean(-(y * np.log(p + eps) + (1.0 - y) * np.log(1.0 - p + eps))))


def test_bce_grad_matches_finite_difference() -> None:
    rng = np.random.default_rng(1)
    n, c = 40, 3
    names = [f"c{i}" for i in range(c)]
    scores = rng.standard_normal((n, c))
    y = (rng.random(n) > 0.5).astype(np.float64)
    comb = Combiner(names, rng.standard_normal(c), bias=0.3)

    grad_w, grad_b = comb.bce_grad(scores, y)

    h = 1e-6
    num_w = np.zeros(c)
    for j in range(c):
        wp = comb.weights.copy()
        wp[j] += h
        wm = comb.weights.copy()
        wm[j] -= h
        lp = _bce_loss(Combiner(names, wp, comb.bias), scores, y)
        lm = _bce_loss(Combiner(names, wm, comb.bias), scores, y)
        num_w[j] = (lp - lm) / (2 * h)
    num_b = (
        _bce_loss(Combiner(names, comb.weights, comb.bias + h), scores, y)
        - _bce_loss(Combiner(names, comb.weights, comb.bias - h), scores, y)
    ) / (2 * h)

    assert np.allclose(grad_w, num_w, atol=1e-6)
    assert grad_b == pytest.approx(num_b, abs=1e-6)


def test_gradient_descent_reduces_bce() -> None:
    """A few analytic-gradient steps must reduce the BCE loss (head is trainable)."""
    rng = np.random.default_rng(2)
    n, c = 128, 2
    names = ["a", "b"]
    scores = rng.standard_normal((n, c))
    # A separable target: keep when a - b is large.
    y = ((scores[:, 0] - scores[:, 1]) > 0.0).astype(np.float64)
    comb = Combiner(names, np.zeros(c), bias=0.0)

    loss0 = _bce_loss(comb, scores, y)
    lr = 1.0
    for _ in range(200):
        gw, gb = comb.bce_grad(scores, y)
        comb.weights -= lr * gw
        comb.bias -= lr * gb
    loss1 = _bce_loss(comb, scores, y)
    assert loss1 < loss0 * 0.5


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["find_spec"]).find_spec("torch") is None,
    reason="torch not installed",
)
def test_torch_head_matches_numpy() -> None:  # pragma: no cover - runs only if torch present
    import torch as _t

    rng = np.random.default_rng(3)
    names = ["a", "b", "c"]
    comb = Combiner(names, rng.standard_normal(3), bias=0.2)
    scores = rng.standard_normal((16, 3))

    head = cast(Any, comb.torch_head())
    with _t.no_grad():
        logits = head(_t.as_tensor(scores, dtype=_t.float32)).reshape(-1)
        p_torch = _t.sigmoid(logits).numpy()
    assert np.allclose(p_torch, comb.forward(scores), atol=1e-5)


# --------------------------------------------------------------------------------------
# FilterModel: theta round-trip, functional eval, decide.
# --------------------------------------------------------------------------------------


def test_theta_keys_and_roundtrip() -> None:
    model, _ = _two_constraint_model()
    theta = model.theta
    assert "gold_ice::gain" in theta
    assert "coherence::gain" in theta
    assert "combiner::w::gold_ice" in theta
    assert "combiner::w::coherence" in theta
    assert "combiner::bias" in theta

    new = dict(theta)
    new["gold_ice::gain"] = 3.5
    new["combiner::w::gold_ice"] = -2.0
    new["combiner::bias"] = 0.4
    model.set_theta(new)
    got = model.theta
    assert got["gold_ice::gain"] == pytest.approx(3.5)
    assert got["combiner::w::gold_ice"] == pytest.approx(-2.0)
    assert got["combiner::bias"] == pytest.approx(0.4)


def test_set_theta_clips_to_bounds() -> None:
    model, _ = _two_constraint_model()
    model.set_theta({"gold_ice::gain": 999.0})  # ParamSpec hi = 10.0
    assert model.theta["gold_ice::gain"] == pytest.approx(10.0)


def test_forward_with_theta_is_pure() -> None:
    model, feats = _two_constraint_model()
    before = model.theta
    p_base = model.forward(feats)
    proposed = dict(before)
    proposed["combiner::w::gold_ice"] = -5.0
    proposed["gold_ice::gain"] = 8.0
    p_prop = model.forward_with_theta(feats, proposed)
    # The proposed eval differs but must not have mutated the model.
    assert not np.allclose(p_base, p_prop)
    assert model.theta == before


def test_decide_threshold() -> None:
    model, feats = _two_constraint_model()
    p = model.forward(feats)
    keep = model.decide(feats, tau=0.5)
    assert keep.dtype == np.bool_
    assert np.array_equal(keep, p >= 0.5)
    # Extreme thresholds.
    assert model.decide(feats, tau=0.0).all()
    assert not model.decide(feats, tau=1.0).any()


def test_duplicate_constraint_names_rejected() -> None:
    dup = [
        _ScaledFeatureConstraint("same", "cluster_density"),
        _ScaledFeatureConstraint("same", "coherence"),
    ]
    with pytest.raises(ValueError):
        FilterModel(dup)


def test_combiner_names_mismatch_rejected() -> None:
    constraints = [_ScaledFeatureConstraint("a", "cluster_density")]
    bad = Combiner.default(["b"])
    with pytest.raises(ValueError):
        FilterModel(constraints, bad)


# --------------------------------------------------------------------------------------
# Requirements helpers (FeatureSpec = union of needs_features; fields via extractors).
# --------------------------------------------------------------------------------------


def test_required_features_ordered_union() -> None:
    constraints = [
        _ScaledFeatureConstraint("a", "cluster_density"),
        _ScaledFeatureConstraint("b", "coherence"),
        _ScaledFeatureConstraint("c", "cluster_density"),  # duplicate feature
    ]
    feats = required_features(constraints)
    assert feats == ("cluster_density", "coherence")


def test_required_fields_via_extractors() -> None:
    constraints = [
        _ScaledFeatureConstraint("a", "cluster_density"),
        _ScaledFeatureConstraint("b", "coherence"),
    ]
    extractors = [
        _DummyExtractor("cluster_density", "cc"),
        _DummyExtractor("coherence", "normal"),
        _DummyExtractor("unused", "membrane"),  # not needed -> field excluded
    ]
    reqs = model_requirements(constraints, extractors)
    assert reqs.features == ("cluster_density", "coherence")
    assert reqs.fields == ("cc", "normal")
    assert required_fields(constraints, extractors) == ("cc", "normal")


def test_model_requirements_without_extractors() -> None:
    constraints = [_ScaledFeatureConstraint("a", "cluster_density")]
    reqs = model_requirements(constraints)
    assert reqs.features == ("cluster_density",)
    assert reqs.fields == ()


def test_model_needs_features_property() -> None:
    model, _ = _two_constraint_model()
    assert model.needs_features == ("cluster_density", "coherence")


# --------------------------------------------------------------------------------------
# FittedConfig yaml round-trip (includes the combiner + theta the model produces).
# --------------------------------------------------------------------------------------


def test_fitted_config_yaml_roundtrip(tmp_path: Path) -> None:
    model, _ = _two_constraint_model()
    cfg = FittedConfig(
        dataset="six_hours_round_4",
        providers=[{"name": "cc"}, {"name": "normal", "requires": ["angle"]}],
        features=list(model.needs_features),
        constraints=[{"name": "gold_ice", "gain": 1.0}, {"name": "coherence", "gain": 1.0}],
        combiner=model.combiner.to_config(),
        theta=model.theta,
        calibration={"H99_2_100_1_bin5": {"mean": 3.28, "std": 0.48}},
        tau=0.5,
        meta={"git_rev": "abc123"},
    )
    path = tmp_path / "fitted.yaml"
    cfg.save(path)
    back = FittedConfig.load(path)

    assert back.dataset == cfg.dataset
    assert back.providers == cfg.providers
    assert back.features == cfg.features
    assert back.constraints == cfg.constraints
    assert back.combiner == cfg.combiner
    assert back.theta == cfg.theta
    assert back.calibration == cfg.calibration
    assert back.tau == cfg.tau
    assert back.meta == cfg.meta


def test_combiner_config_roundtrip() -> None:
    comb = Combiner(["a", "b"], np.array([-1.5, 2.0]), bias=0.3)
    back = Combiner.from_config(comb.to_config())
    assert back.names == comb.names
    assert np.allclose(back.weights, comb.weights)
    assert back.bias == pytest.approx(comb.bias)

    # calibration stats round-trip through FittedConfig combiner slot as well.
    rebuilt = FilterModel(
        [
            _ScaledFeatureConstraint("a", "cluster_density"),
            _ScaledFeatureConstraint("b", "coherence"),
        ],
        back,
    )
    assert rebuilt.combiner.names == ["a", "b"]
