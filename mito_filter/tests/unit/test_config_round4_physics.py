"""round_4_physics.yaml — every false-positive axis LIVE + physically-directed on real data.

This config is the fix for the round_4_fitted cross-tab (ROC-AUC 0.535) where gold/ice fired on
16/133,867 hits, isolation saturated at ~1.0, and membrane was unwired. The tests assert the
STRUCTURE that makes each axis live:

* gold/ice reads the dense ``cc_cluster`` cluster-density field (``cluster_density_sample`` ->
  ``cc_cluster_density``) at a threshold inside the data range (not the dead 10.7);
* surface coherence consumes the DENSE cc-gated normal field (``normal_source: field``);
* isolation is de-saturated (threshold on the neighbor COUNT scale, not the ~0.005 density scale);
* membrane geometry (facing + interior-vesicle) is wired with ``rec``-derived ``membrane_sdf``;
* every combiner weight is POSITIVE (each axis increases FP-ness).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from mito_filter.cli import _build_extractors
from mito_filter.constraints.gold_ice import GoldIceClusterConstraint
from mito_filter.constraints.isolation import IsolationConstraint
from mito_filter.features.curvature import _CurvatureBase
from mito_filter.features.engine import FeatureEngine
from mito_filter.features.extractor import FeatureMatrix

_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "round_4_physics.yaml"


def _cfg() -> dict:
    return dict(yaml.safe_load(_CONFIG.read_text()))


def test_physics_config_all_four_axes_present() -> None:
    cfg = _cfg()
    names = [c["name"] for c in cfg["constraints"]]
    for axis in ("gold_ice_cluster", "surface_coherence", "isolation", "membrane_geometry"):
        assert axis in names, axis


def test_physics_config_goldice_reads_dense_cluster_density() -> None:
    """The cluster_density_sample extractor produces cc_cluster_density (the gold/ice primary)."""
    cfg = _cfg()
    feats = {f["name"] for f in cfg["features"]}
    assert "cluster_density_sample" in feats
    eng = FeatureEngine(_build_extractors(cfg))
    assert "cc_cluster_density" in eng.produced_columns
    assert "cc_cluster" in eng.needed_fields  # the dense field the sampler consumes


def test_physics_config_goldice_threshold_inside_data_range() -> None:
    """cc_thresh is a physically-reachable log-count (~3.5), NOT the dead round_4_fitted 10.7."""
    cfg = _cfg()
    spec = next(c for c in cfg["constraints"] if c["name"] == "gold_ice_cluster")
    assert spec["cc_thresh"] <= 6.0
    # blob_mix 0 -> density-only (point-Hessian blobness is anti-predictive on real data).
    assert spec["blob_mix"] == 0.0
    # A gold/ice-scale log-count clearly fires; an isolated peak's footprint does not.
    con = GoldIceClusterConstraint(**{k: v for k, v in spec.items() if k != "name"})
    fm = FeatureMatrix.from_columns(
        {"cc_cluster_density": np.array([0.5, 2.0, 6.0], dtype=np.float32)}, np.arange(3)
    )
    fp = con.forward(fm, {})
    assert fp[0] < 0.3 and fp[2] > 0.7  # isolated low, in-cluster high


def test_physics_config_coherence_uses_dense_normal_field() -> None:
    cfg = _cfg()
    feats = {f["name"]: f for f in cfg["features"]}
    for name in ("normal_coherence", "surface_fit_residual", "principal_curvature"):
        assert feats[name]["normal_source"] == "field", name
    surface = [e for e in _build_extractors(cfg) if isinstance(e, _CurvatureBase)]
    assert surface
    for e in surface:
        assert e.normal_source == "field"
        assert "normal" in e.needs_fields and "cc" in e.needs_fields


def test_physics_config_isolation_desaturated() -> None:
    """density_thresh is a neighbor-COUNT (~4), not the saturating ~0.005-density-scale value."""
    cfg = _cfg()
    spec = next(c for c in cfg["constraints"] if c["name"] == "isolation")
    assert 1.0 <= spec["density_thresh"] <= 40.0  # a count, not 27.4-on-a-0.005-scale
    con = IsolationConstraint(**{k: v for k, v in spec.items() if k != "name"})
    count = np.array([0.0, 4.0, 8.0, 16.0, 30.0], dtype=np.float32)
    fm = FeatureMatrix.from_columns({"neighbor_count": count}, np.arange(5))
    fp = np.asarray(con.forward(fm, {}), float)
    assert fp.min() < 0.2 and fp.max() > 0.8  # spans [0,1], not the constant ~1.0 saturation


def test_physics_config_membrane_wired() -> None:
    cfg = _cfg()
    feats = {f["name"] for f in cfg["features"]}
    for name in (
        "membrane_distance",
        "inside_outside_sign",
        "closed_shell_score",
        "membrane_facing",
    ):
        assert name in feats, name
    assert cfg["rec_dir"] == "/scratch/salina/alt_cache"
    spec = next(c for c in cfg["constraints"] if c["name"] == "membrane_geometry")
    assert spec["misface_weight"] > 0.0  # facing term ON (default 0 = off)


def test_physics_config_every_combiner_weight_is_fp_positive() -> None:
    """Each axis increases FP-ness: positive weight in the fp-logit (higher score -> lower keep)."""
    cfg = _cfg()
    comb = cfg["combiner"]
    assert comb["kind"] == "logit"
    assert set(comb["names"]) == {
        "gold_ice_cluster",
        "surface_coherence",
        "isolation",
        "membrane_geometry",
    }
    assert all(w > 0.0 for w in comb["weights"])
    # gold/ice is the strongest measured axis -> it carries the largest weight.
    wmap = dict(zip(comb["names"], comb["weights"]))
    assert wmap["gold_ice_cluster"] == max(comb["weights"])


def test_physics_config_applies_negated_canonical_head_via_theta() -> None:
    """The built model uses the canonical (negated) head from ``theta``, not the positive block.

    The ``combiner:`` block above is fp-logit documentation (positive = FP, keep = sigmoid(-fp));
    the FilterModel head is keep = sigmoid(bias + S @ w), so the authoritative ``theta`` negates it
    to ``[-3, -1, -0.3, -0.5]`` / bias ``+1.5`` (validated fused ROC-AUC 0.669 on the real cache).
    Guards against the positive block leaking into the head (which would flip the sign / keep FPs).
    """
    from mito_filter.config import PipelineConfig
    from mito_filter.model.filter_model import FilterModel
    from mito_filter.scan.context import combiner_from_block, constraints_from_specs

    cfg = PipelineConfig.load(_CONFIG)
    cons = constraints_from_specs(cfg.constraints)
    model = FilterModel(cons)
    block = combiner_from_block([c.name for c in cons], cfg.combiner)
    if block is not None:
        model.combiner = block
    if cfg.theta:
        model.set_theta(cfg.theta)
    assert list(model.combiner.weights) == [-3.0, -1.0, -0.3, -0.5]
    assert model.combiner.bias == 1.5
    assert all(w < 0.0 for w in model.combiner.weights)  # every axis is an FP (negative) weight
