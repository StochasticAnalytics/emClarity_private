"""``scan.context`` combiner-block wiring (regression for the silently-dropped ``combiner:`` head).

Before this, :meth:`RunContext.from_pipeline_config` built the model with the built-in uniform
default combiner and **ignored** the config's ``combiner:`` block entirely -- so a config that set a
scalar ``bias`` (round_4/dense/membrane) silently ran at ``bias=0``, and a physically-weighted
config whose weights lived only in the block ran as a *degenerate flag-all* head. These tests pin
the fix: the scalar ``{weight, bias}`` form is materialized (canonical FilterModel convention), and
the per-axis ``weights`` list form is deferred to ``theta`` (the authoritative machine channel).
"""

from __future__ import annotations

import numpy as np

import mito_filter.constraints.gold_ice  # noqa: F401  (register constraint)
import mito_filter.constraints.isolation  # noqa: F401
from mito_filter.config import ComponentSpec, PipelineConfig
from mito_filter.model.filter_model import Combiner
from mito_filter.scan.context import combiner_from_block, constraints_from_specs

_NAMES = ["gold_ice_cluster", "isolation"]


def test_combiner_from_block_scalar_applies_weight_and_bias() -> None:
    comb = combiner_from_block(_NAMES, {"weight": -2.0, "bias": 0.7})
    assert comb is not None
    assert list(comb.weights) == [-2.0, -2.0]
    assert comb.bias == 0.7


def test_combiner_from_block_empty_or_list_returns_none() -> None:
    # empty block -> None (fall back to the caller's default head)
    assert combiner_from_block(_NAMES, {}) is None
    # list form is documentation only: weights travel via theta, not the block
    block = {"kind": "logit", "names": _NAMES, "weights": [3.0, 0.3], "bias": -1.5}
    assert combiner_from_block(_NAMES, block) is None


def test_from_pipeline_config_honors_scalar_combiner_bias() -> None:
    """The scalar combiner form now reaches the built model (was dropped to default bias=0)."""
    from mito_filter.scan.context import RunContext

    cfg = PipelineConfig(
        dataset="t",
        rec_dir=None,
        constraints=[ComponentSpec("gold_ice_cluster", {}), ComponentSpec("isolation", {})],
        combiner={"weight": -2.5, "bias": 0.9},
    )
    ctx = RunContext.from_pipeline_config(cfg, extractors=[])
    assert list(ctx.model.combiner.weights) == [-2.5, -2.5]
    assert ctx.model.combiner.bias == 0.9


def test_from_pipeline_config_theta_overrides_block() -> None:
    """theta is authoritative: it wins over whatever the block materialized."""
    from mito_filter.scan.context import RunContext

    cfg = PipelineConfig(
        dataset="t",
        rec_dir=None,
        constraints=[ComponentSpec("gold_ice_cluster", {}), ComponentSpec("isolation", {})],
        combiner={"weight": -1.0, "bias": 0.0},
        theta={
            "combiner::w::gold_ice_cluster": -3.0,
            "combiner::w::isolation": -0.3,
            "combiner::bias": 1.5,
        },
    )
    ctx = RunContext.from_pipeline_config(cfg, extractors=[])
    assert list(ctx.model.combiner.weights) == [-3.0, -0.3]
    assert ctx.model.combiner.bias == 1.5


def test_scalar_block_matches_default_combiner() -> None:
    """The materialized scalar head equals a hand-built :class:`Combiner.default`."""
    got = combiner_from_block(_NAMES, {"weight": -1.0, "bias": 0.5})
    want = Combiner.default(_NAMES, weight=-1.0, bias=0.5)
    assert got is not None
    assert np.allclose(got.weights, want.weights) and got.bias == want.bias
    # constraints_from_specs stays name-stable so column order lines up with the head
    cons = constraints_from_specs(
        [ComponentSpec("gold_ice_cluster", {}), ComponentSpec("isolation", {})]
    )
    assert [c.name for c in cons] == _NAMES
