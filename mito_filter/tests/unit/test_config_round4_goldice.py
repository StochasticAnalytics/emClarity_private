"""round_4_goldice.yaml — the FAST VALIDATED WORKHORSE (the production default).

The lean, cheap gold/ice-dominant head validated at full 112-tomo scale (gold/ice axis ROC-AUC
0.681 vs the union classification cull, 0.748 vs the round-1/cyc2 gold-ice cull it targets; fused
0.657, OR 4.06, precision 0.826). It keeps ONLY the two cheap axes (``gold_ice_cluster`` +
``isolation``) and drops the slow surface/membrane decodes, mirroring the physics head's weights
exactly on the two kept axes.

Guards, like the ``round_4_fitted_v2`` sibling, that:

* the head the **real scan pipeline** builds is the validated canonical ``[-3, -0.3]`` / bias
  ``+1.5`` (a *negated* fp-logit block delivered via ``theta``), NOT the uniform default fall-back;
* that head is **non-degenerate** — a spread of scores yields both kept and flagged candidates.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

import mito_filter.constraints.gold_ice  # noqa: F401
import mito_filter.constraints.isolation  # noqa: F401
from mito_filter.config import PipelineConfig
from mito_filter.model.filter_model import FilterModel
from mito_filter.scan.context import combiner_from_block, constraints_from_specs

_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "round_4_goldice.yaml"

_AXES = ["gold_ice_cluster", "isolation"]
_VALIDATED_W = [-3.0, -0.3]
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


def test_goldice_axes_present_and_lean() -> None:
    cfg = dict(yaml.safe_load(_CONFIG.read_text()))
    names = [c["name"] for c in cfg["constraints"]]
    assert names == _AXES, "lean head is gold/ice + isolation only"


def test_goldice_builds_validated_canonical_head() -> None:
    model = _build_model()
    assert [c.name for c in model.constraints] == _AXES
    assert list(model.combiner.weights) == _VALIDATED_W
    assert model.combiner.bias == _VALIDATED_BIAS


def test_goldice_head_is_fp_monotone() -> None:
    """Every axis is an FP axis: a higher score can only lower keep-prob (weight <= 0)."""
    model = _build_model()
    assert all(w <= 0.0 for w in model.combiner.weights)
    # gold/ice is the dominant measured axis -> largest-magnitude weight.
    w = dict(zip(_AXES, model.combiner.weights))
    assert abs(w["gold_ice_cluster"]) == max(abs(v) for v in w.values())


def test_goldice_head_is_non_degenerate() -> None:
    """A spread of constraint scores yields BOTH kept and flagged candidates (not flag-all/none)."""
    model = _build_model()
    tau = PipelineConfig.load(_CONFIG).tau
    rng = np.random.default_rng(0)
    scores = np.vstack(
        [
            [0.0, 0.0],  # clean -> keep
            [1.0, 0.0],  # strong gold cluster -> flag
            rng.random((50, 2)),
        ]
    )
    keep_prob = model.combiner.forward(scores)
    flagged = keep_prob < tau
    assert keep_prob[0] > tau, "clean hit must be kept"
    assert keep_prob[1] < tau, "strong gold/ice hit must be flagged"
    assert 0 < int(flagged.sum()) < len(flagged)
