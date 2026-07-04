"""Unit tests for the constraint plugins + the ScoreCombiner fusion head (constraints/*).

Each test drives a synthetic :class:`FeatureMatrix` (numbers only — the constraints see
precomputed features, never volumes) and checks the three contract properties: every constraint
(a) registers, (b) is monotonic in the intended direction, and (c) is NEUTRAL (all-zero
contribution) when its features are absent or NaN. A light real-data check confirms the
``templateIDX == 1`` weak-negative prior fires on the true H99_2_100 template distribution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest
from numpy.typing import NDArray

from mito_filter.constraints.base import Constraint, ParamSpec
from mito_filter.constraints.combine import (
    COMBINER_REGISTRY,
    CONSTRAINT_REGISTRY,
    ScoreCombiner,
    sigmoid,
    soft_or,
)
from mito_filter.constraints.curvature import SurfaceCoherenceConstraint
from mito_filter.constraints.gold_ice import GoldIceClusterConstraint
from mito_filter.constraints.isolation import IsolationConstraint
from mito_filter.constraints.membrane import MembraneGeometryConstraint
from mito_filter.constraints.template_prior import TemplateIdxPriorConstraint
from mito_filter.features.extractor import FeatureMatrix

REAL_DIR = Path("/scratch/siracusa/full_enchilada_3/six_hours_round_4/convmap_wedgeType_2_bin5")
REAL_BASE = "H99_2_100_1_bin5"

_ALL_NAMES = [
    "gold_ice_cluster",
    "membrane_geometry",
    "surface_coherence",
    "isolation",
    "template_idx_prior",
]


def make_fm(**cols: NDArray[np.float64]) -> FeatureMatrix:
    """Build a synthetic FeatureMatrix from name -> ``(N,)`` column arrays."""
    first = next(iter(cols.values()))
    n = int(np.asarray(first).shape[0])
    row_ids = np.arange(n)
    return FeatureMatrix.from_columns(
        {k: np.asarray(v, dtype=np.float32) for k, v in cols.items()}, row_ids
    )


def _nondecreasing(x: NDArray[np.floating[Any]], tol: float = 1e-6) -> bool:
    """True if ``x`` is monotone non-decreasing within ``tol``."""
    return bool(np.all(np.diff(np.asarray(x, dtype=np.float64)) >= -tol))


# --------------------------------------------------------------------------- #
# helpers: numeric utilities                                                   #
# --------------------------------------------------------------------------- #
def test_sigmoid_and_soft_or() -> None:
    """sigmoid saturates without overflow; soft_or is bounded and monotone."""
    assert np.isclose(sigmoid(np.array([0.0]))[0], 0.5)
    assert sigmoid(np.array([1.0e6]))[0] == pytest.approx(1.0)
    assert sigmoid(np.array([-1.0e6]))[0] == pytest.approx(0.0)
    a = np.array([0.2, 0.8])
    b = np.array([0.5, 0.0])
    combined = soft_or([a, b], n=2)
    assert np.all(combined >= np.maximum(a, b) - 1e-9)  # OR dominates each term
    assert np.all(combined <= 1.0) and np.all(combined >= 0.0)
    assert soft_or([], n=3).tolist() == [0.0, 0.0, 0.0]


# --------------------------------------------------------------------------- #
# (a) registration                                                             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", _ALL_NAMES)
def test_constraint_registers_and_instantiates(name: str) -> None:
    """Every constraint registers and instantiates from YAML-style kwargs."""
    assert name in CONSTRAINT_REGISTRY
    cls = CONSTRAINT_REGISTRY.get(name)
    assert issubclass(cls, Constraint)
    inst = CONSTRAINT_REGISTRY.create(name)  # no kwargs -> defaults
    assert isinstance(inst, Constraint)
    assert inst.name == name
    # param_schema is a real ParamSpec map exposed to the tuner.
    assert all(isinstance(s, ParamSpec) for s in inst.param_schema.values())


def test_combiner_registers() -> None:
    """The ScoreCombiner registers in the combiner registry."""
    assert "score_combiner" in COMBINER_REGISTRY
    assert COMBINER_REGISTRY.get("score_combiner") is ScoreCombiner


def test_yaml_kwargs_override_defaults() -> None:
    """Constraints accept YAML kwargs and resolve them (config < theta)."""
    c = GoldIceClusterConstraint(cc_thresh=5.0)
    assert c.resolved(None)["cc_thresh"] == 5.0
    # theta overrides the config value.
    assert c.resolved({"cc_thresh": 9.0})["cc_thresh"] == 9.0
    # out-of-bounds theta is clipped into the ParamSpec range.
    assert c.resolved({"cc_thresh": 999.0})["cc_thresh"] == c.param_schema["cc_thresh"].hi


# --------------------------------------------------------------------------- #
# (b) monotonic behavior                                                       #
# --------------------------------------------------------------------------- #
def test_gold_ice_monotonic_in_density() -> None:
    """Higher CC-cluster density -> higher FP score (lower keep)."""
    dens = np.linspace(3.0, 14.0, 24)
    fm = make_fm(cc_cluster_density=dens, blobness=np.ones(24))
    fp = GoldIceClusterConstraint().forward(fm, {})
    assert fp.dtype == np.float32 and fp.shape == (24,)
    assert _nondecreasing(fp) and fp[-1] > fp[0]


def test_gold_ice_monotonic_in_gold_proximity() -> None:
    """Closer to a gold fiducial -> higher FP score."""
    gold = np.linspace(0.0, 600.0, 24)  # increasing distance
    fm = make_fm(gold_dist=gold)
    fp = GoldIceClusterConstraint().forward(fm, {})
    assert _nondecreasing(-fp[::-1][::-1])  # non-increasing in distance
    assert fp[0] > fp[-1]


def test_membrane_monotonic_in_closed_shell() -> None:
    """Higher closed-shell curvature (small vesicle) -> higher FP score."""
    closed = np.linspace(0.0, 0.05, 24)
    fm = make_fm(closed_shell=closed)
    fp = MembraneGeometryConstraint().forward(fm, {})
    assert _nondecreasing(fp) and fp[-1] > fp[0]


def test_membrane_wrong_side_penalized() -> None:
    """On-membrane hits on the FP side score higher than the correct side."""
    dist = np.zeros(4)  # exactly on the membrane
    side = np.array([-1.0, -1.0, 1.0, 1.0])  # inside, inside, outside, outside
    fm = make_fm(membrane_dist=dist, inside_sign=side)
    fp = MembraneGeometryConstraint(fp_side=-1.0).forward(fm, {})  # inside is FP
    assert fp[0] > fp[2] and fp[1] > fp[3]


def test_membrane_misfacing_penalized() -> None:
    """On-membrane hits whose template +Z disagrees with the membrane outward normal (low
    facing cosine) score higher than well-aligned outer-membrane hits."""
    dist = np.zeros(5)  # all exactly on the membrane
    facing = np.array([1.0, 0.9, 0.5, 0.0, -1.0])  # aligned -> anti-aligned
    fm = make_fm(membrane_dist=dist, membrane_facing=facing)
    c = MembraneGeometryConstraint(misface_weight=1.0, misface_thresh=0.7)
    fp = c.forward(fm, {})
    assert _nondecreasing(fp)  # penalty increases as facing drops (index 0=aligned .. 4=anti)
    assert fp[-1] > fp[0]  # anti-aligned wrong-side hit penalized, aligned target not


def test_membrane_misfacing_off_by_default() -> None:
    """misface_weight defaults to 0, so a low-facing hit is NOT penalized until tuned on."""
    fm = make_fm(membrane_dist=np.zeros(3), membrane_facing=np.array([-1.0, 0.0, 1.0]))
    fp = MembraneGeometryConstraint().forward(fm, {})  # default misface_weight=0.0
    assert np.allclose(fp, 0.0)


def test_surface_coherence_monotonic_in_incoherence() -> None:
    """Lower normal coherence -> higher FP score (lower keep)."""
    coh = np.linspace(1.0, 0.0, 24)  # decreasing coherence
    fm = make_fm(normal_coherence=coh)
    fp = SurfaceCoherenceConstraint().forward(fm, {})
    assert _nondecreasing(fp) and fp[-1] > fp[0]


def test_surface_coherence_monotonic_in_residual() -> None:
    """Higher surface-fit residual -> higher FP score."""
    res = np.linspace(0.0, 400.0, 24)
    fm = make_fm(surface_residual=res)
    fp = SurfaceCoherenceConstraint().forward(fm, {})
    assert _nondecreasing(fp) and fp[-1] > fp[0]


def test_isolation_monotonic_in_sparsity() -> None:
    """Lower neighbor density -> higher FP score (more isolated)."""
    dens = np.linspace(20.0, 0.0, 24)  # decreasing density
    fm = make_fm(neighbor_density=dens)
    fp = IsolationConstraint().forward(fm, {})
    assert _nondecreasing(fp) and fp[-1] > fp[0]


def test_template_prior_penalizes_ref1() -> None:
    """templateIDX == 1 (ref_old) gets the penalty; others do not."""
    fm = make_fm(is_ref1=np.array([0.0, 1.0]))
    fp = TemplateIdxPriorConstraint(ref1_penalty=0.3).forward(fm, {})
    assert fp[0] == pytest.approx(0.0)
    assert fp[1] == pytest.approx(0.3)
    # derives is_ref1 from a raw template_idx column too.
    fp2 = TemplateIdxPriorConstraint().forward(make_fm(template_idx=np.array([1.0, 2.0, 3.0])), {})
    assert fp2[0] > 0.0 and fp2[1] == 0.0 and fp2[2] == 0.0


# --------------------------------------------------------------------------- #
# (c) neutral when features absent / NaN                                       #
# --------------------------------------------------------------------------- #
def _neutral_fm(n: int = 8) -> FeatureMatrix:
    """A FeatureMatrix with a single unrelated column (no constraint's features)."""
    return make_fm(unrelated=np.linspace(0.0, 1.0, n))


@pytest.mark.parametrize("name", _ALL_NAMES)
def test_neutral_when_features_absent(name: str) -> None:
    """A constraint contributes exactly zero when none of its features is present."""
    inst = CONSTRAINT_REGISTRY.create(name)
    assert isinstance(inst, Constraint)
    fp = inst.forward(_neutral_fm(8), {})
    assert fp.shape == (8,)
    assert np.allclose(fp, 0.0)


def test_neutral_when_features_nan() -> None:
    """An all-NaN feature column (a MISSING generated field) is neutral, not a spurious hit."""
    nan = np.full(6, np.nan)
    fm = make_fm(membrane_dist=nan, inside_sign=nan, closed_shell=nan, membrane_facing=nan)
    assert np.allclose(MembraneGeometryConstraint(misface_weight=1.0).forward(fm, {}), 0.0)
    fm2 = make_fm(normal_coherence=nan, surface_residual=nan, curvature=nan)
    assert np.allclose(SurfaceCoherenceConstraint().forward(fm2, {}), 0.0)


def test_partial_nan_masked_per_candidate() -> None:
    """NaN candidates read neutral while finite candidates still score."""
    coh = np.array([np.nan, 0.0, np.nan, 0.1])
    fp = SurfaceCoherenceConstraint().forward(make_fm(normal_coherence=coh), {})
    assert fp[0] == 0.0 and fp[2] == 0.0  # untrusted -> neutral
    assert fp[1] > 0.0 and fp[3] > 0.0  # low coherence -> penalized


# --------------------------------------------------------------------------- #
# ScoreCombiner (the FilterModel head)                                         #
# --------------------------------------------------------------------------- #
def test_combiner_neutral_is_half() -> None:
    """With all constraints neutral and bias 0, keep_prob == 0.5 (logit mode)."""
    combiner = ScoreCombiner([GoldIceClusterConstraint(), IsolationConstraint()])
    keep = combiner.keep_prob(_neutral_fm(5))
    assert np.allclose(keep, 0.5, atol=1e-6)


def test_combiner_lowers_keep_for_fp() -> None:
    """Higher fused FP score -> monotonically lower keep-probability."""
    dens = np.linspace(3.0, 14.0, 20)
    fm = make_fm(cc_cluster_density=dens, blobness=np.ones(20))
    combiner = ScoreCombiner([GoldIceClusterConstraint()])
    keep = combiner.keep_prob(fm)
    assert bool(np.all(np.diff(keep) <= 1e-6))  # non-increasing
    assert keep[0] > keep[-1]
    # decide() thresholds it; the strongest FP is rejected at tau=0.5.
    mask = combiner.decide(fm, tau=0.5)
    assert mask.dtype == np.bool_ and not bool(mask[-1])


def test_combiner_weight_zero_disables_constraint() -> None:
    """A zero fusion weight removes a constraint's influence entirely."""
    dens = np.linspace(3.0, 14.0, 8)
    fm = make_fm(cc_cluster_density=dens, blobness=np.ones(8))
    combiner = ScoreCombiner([GoldIceClusterConstraint()])
    keep_full = combiner.keep_prob(fm, {"w_gold_ice_cluster": 1.0})
    keep_off = combiner.keep_prob(fm, {"w_gold_ice_cluster": 0.0})
    assert np.allclose(keep_off, 0.5, atol=1e-6)
    assert not np.allclose(keep_full, 0.5)


def test_combiner_param_schema_exposes_weights_and_bias() -> None:
    """The combiner exposes one weight per constraint + bias to the tuner."""
    combiner = ScoreCombiner([GoldIceClusterConstraint(), IsolationConstraint()])
    schema: Dict[str, ParamSpec] = combiner.param_schema
    assert "bias" in schema
    assert "w_gold_ice_cluster" in schema and "w_isolation" in schema
    assert all(isinstance(s, ParamSpec) for s in schema.values())


def test_combiner_weighted_mode() -> None:
    """Weighted mode maps fused FP directly to 1 - fp."""
    fm = make_fm(is_ref1=np.array([0.0, 1.0]))
    combiner = ScoreCombiner([TemplateIdxPriorConstraint(ref1_penalty=0.4)], mode="weighted")
    keep = combiner.keep_prob(fm)
    assert keep[0] == pytest.approx(1.0)  # no penalty
    assert keep[1] == pytest.approx(0.6)  # 1 - 0.4


# --------------------------------------------------------------------------- #
# real-data sanity: the templateIDX weak-negative prior fires on real hits     #
# --------------------------------------------------------------------------- #
def test_template_prior_on_real_templateidx() -> None:
    """The ref_old prior fires on the real H99_2_100 template distribution (SPEC §10)."""
    tid_path = REAL_DIR / f"{REAL_BASE}.templateIDX"
    if not tid_path.exists():
        pytest.skip("real dev-set templateIDX not present on this host")
    tid = np.loadtxt(tid_path).astype(np.float64)
    fm = make_fm(template_idx=tid)
    penalty = 0.3
    fp = TemplateIdxPriorConstraint(ref1_penalty=penalty).forward(fm, {})
    ref1_frac = float((tid == 1).mean())
    assert ref1_frac == pytest.approx(0.622, abs=0.01)  # SPEC: 777/1249
    # every ref_old hit gets exactly the penalty; every other hit gets zero.
    assert np.allclose(fp[tid == 1], penalty)
    assert np.allclose(fp[tid != 1], 0.0)
    assert float(fp.mean()) == pytest.approx(ref1_frac * penalty, abs=1e-6)
