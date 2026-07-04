"""round_4_fitted_v2.yaml — the RECOMMENDED DEFAULT: the physics-fixed, validated filter head.

Guards two things the shipped default must satisfy and that the pre-fix config silently violated:

* the head that the **real scan pipeline** builds is the validated canonical
  ``[-3, -1, -0.3, -0.5]`` / bias ``+1.5`` (a *negated* fp-logit block delivered via ``theta``),
  NOT the uniform default the loader used to fall back to;
* that head is **non-degenerate** — a spread of constraint scores yields both kept and flagged
  candidates at ``tau`` (the pre-fix default ``[-1,-1,-1,-1]`` / bias 0 flagged 100% -- flag-all).

This is the regression that would have caught the shipped flag-all degeneracy.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

import mito_filter.constraints.curvature  # noqa: F401
import mito_filter.constraints.gold_ice  # noqa: F401
import mito_filter.constraints.isolation  # noqa: F401
import mito_filter.constraints.membrane  # noqa: F401
import mito_filter.constraints.template_prior  # noqa: F401
from mito_filter.config import PipelineConfig
from mito_filter.model.filter_model import FilterModel
from mito_filter.scan.context import combiner_from_block, constraints_from_specs

_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "round_4_fitted_v2.yaml"

_AXES = ["gold_ice_cluster", "surface_coherence", "isolation", "membrane_geometry"]
_VALIDATED_W = [-3.0, -1.0, -0.3, -0.5]
_VALIDATED_BIAS = 1.5


def _build_model() -> FilterModel:
    """Reproduce exactly what RunContext.from_pipeline_config does for the head."""
    cfg = PipelineConfig.load(_CONFIG)
    cons = constraints_from_specs(cfg.constraints)
    model = FilterModel(cons)
    block = combiner_from_block([c.name for c in cons], cfg.combiner)
    if block is not None:
        model.combiner = block
    if cfg.theta:
        model.set_theta(cfg.theta)
    return model


def test_fitted_v2_axes_present() -> None:
    cfg = dict(yaml.safe_load(_CONFIG.read_text()))
    names = [c["name"] for c in cfg["constraints"]]
    for axis in _AXES:
        assert axis in names, axis


def test_fitted_v2_builds_validated_canonical_head() -> None:
    model = _build_model()
    assert [c.name for c in model.constraints] == _AXES
    assert list(model.combiner.weights) == _VALIDATED_W
    assert model.combiner.bias == _VALIDATED_BIAS


def test_fitted_v2_head_is_fp_monotone() -> None:
    """Every axis is an FP axis: a higher score can only lower keep-prob (weight <= 0)."""
    model = _build_model()
    assert all(w <= 0.0 for w in model.combiner.weights)
    # gold/ice is the strongest measured axis -> largest-magnitude weight.
    w = dict(zip(_AXES, model.combiner.weights))
    assert abs(w["gold_ice_cluster"]) == max(abs(v) for v in w.values())


def test_fitted_v2_head_is_non_degenerate() -> None:
    """A spread of constraint scores yields BOTH kept and flagged candidates (not flag-all/none)."""
    model = _build_model()
    tau = PipelineConfig.load(_CONFIG).tau
    rng = np.random.default_rng(0)
    # rows: a clean hit (all axes ~0), a gold/ice hit (gold ~1), and random spreads
    scores = np.vstack(
        [
            [0.0, 0.0, 0.0, 0.0],  # clean -> keep
            [1.0, 0.0, 0.0, 0.0],  # strong gold cluster -> flag
            rng.random((50, 4)),
        ]
    )
    keep_prob = model.combiner.forward(scores)
    flagged = keep_prob < tau
    assert keep_prob[0] > tau, "clean hit must be kept"
    assert keep_prob[1] < tau, "strong gold/ice hit must be flagged"
    # non-degenerate: neither all flagged nor all kept
    assert 0 < int(flagged.sum()) < len(flagged)
