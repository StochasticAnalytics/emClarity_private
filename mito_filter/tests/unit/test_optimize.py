"""Unit tests for the OPTIMIZE layer (DESIGN §8): dataset, labels, objective, space, tuner, report.

Synthetic FeatureMatrix tests prove the tuner *improves the objective* and the self-supervised
physics term separates target-like from FP-like hits with NO labels. Real-data tests parse the
actual round_4 cull files and ``.templateIDX`` (skipped when the dev data is absent).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from mito_filter.constraints.curvature import SurfaceCoherenceConstraint
from mito_filter.constraints.gold_ice import GoldIceClusterConstraint
from mito_filter.features.extractor import FeatureMatrix
from mito_filter.model.config import FittedConfig
from mito_filter.model.filter_model import FilterModel
from mito_filter.optimize import (
    NEGATIVE,
    UNKNOWN,
    CompositeObjective,
    Dimension,
    ParameterSpace,
    RandomOptimizer,
    SearchDataset,
    SelfSupervisedObjective,
    SeparationReport,
    Tuner,
    WeakLabelObjective,
    WeakLabels,
    WeakLabelSource,
    build_report,
    find_cull_files,
    parse_class_cull,
)
from mito_filter.optimize.optimizers import OptunaOptimizer
from mito_filter.optimize.space import TAU_KEY

ROUND_DIR = Path("/scratch/siracusa/full_enchilada_3/six_hours_round_4")
CONVMAP_DIR = Path("/scratch/salina/round4_angle_rerun/convmap_wedgeType_2_bin5")
REAL_BASE = "H99_2_100_1_bin5"


# --------------------------------------------------------------------------- #
# Synthetic dataset builder: two physically-separable groups per tomogram.    #
# --------------------------------------------------------------------------- #
def _tomo(n_target: int, n_fp: int, seed: int) -> FeatureMatrix:
    """A tomogram where targets have high coherence/low cluster and FPs the reverse."""
    rng = np.random.default_rng(seed)
    cc = np.concatenate([rng.normal(3, 1, n_target), rng.normal(11, 1, n_fp)])
    coh = np.concatenate([rng.uniform(0.6, 1.0, n_target), rng.uniform(0.0, 0.4, n_fp)])
    res = np.concatenate([rng.uniform(0, 50, n_target), rng.uniform(200, 400, n_fp)])
    curv = np.concatenate([rng.uniform(0, 0.005, n_target), rng.uniform(0.02, 0.05, n_fp)])
    blob = np.concatenate([rng.uniform(0, 0.3, n_target), rng.uniform(0.7, 1.0, n_fp)])
    cols = {
        "cc_cluster_density": cc,
        "normal_coherence": coh,
        "surface_residual": res,
        "curvature": curv,
        "blobness": blob,
    }
    return FeatureMatrix.from_columns(cols, np.arange(n_target + n_fp))


def _dataset() -> SearchDataset:
    return SearchDataset.from_matrices(
        {REAL_BASE: _tomo(120, 80, 0), "H99_2_101_1_bin5": _tomo(100, 100, 1)}
    )


def _model() -> FilterModel:
    return FilterModel([GoldIceClusterConstraint(), SurfaceCoherenceConstraint()])


# --------------------------------------------------------------------------- #
# SearchDataset                                                               #
# --------------------------------------------------------------------------- #
class TestSearchDataset:
    def test_from_matrices_concatenates_with_tomo_ids(self) -> None:
        ds = _dataset()
        assert ds.n == 400
        assert ds.n_tomos == 2
        assert ds.tomo_ids.shape == (400,)
        assert int((ds.tomo_ids == 0).sum()) == 200
        assert int((ds.tomo_ids == 1).sum()) == 200
        assert set(ds.columns) == {
            "cc_cluster_density",
            "normal_coherence",
            "surface_residual",
            "curvature",
            "blobness",
        }

    def test_group_indices_and_per_tomo(self) -> None:
        ds = _dataset()
        groups = ds.group_indices()
        assert len(groups) == 2
        assert groups[0].size == 200 and groups[1].size == 200
        seen = [(b, m.n) for b, m in ds.per_tomo()]
        assert seen == [(REAL_BASE, 200), ("H99_2_101_1_bin5", 200)]
        # A per-tomo slice's column values match the combined matrix rows.
        _b, m0 = next(iter(ds.per_tomo()))
        np.testing.assert_allclose(
            m0.column("cc_cluster_density"), ds.column("cc_cluster_density")[:200]
        )

    def test_mismatched_columns_raise(self) -> None:
        a = FeatureMatrix.from_columns({"x": np.zeros(3)}, np.arange(3))
        b = FeatureMatrix.from_columns({"y": np.zeros(2)}, np.arange(2))
        with pytest.raises(ValueError, match="feature columns differ"):
            SearchDataset.from_matrices({"a": a, "b": b})

    def test_column_reorder_before_stack(self) -> None:
        a = FeatureMatrix.from_columns(
            {"x": np.array([1.0, 2.0]), "y": np.array([3.0, 4.0])}, np.array([0, 1])
        )
        b = FeatureMatrix.from_columns({"y": np.array([5.0]), "x": np.array([6.0])}, np.array([0]))
        ds = SearchDataset.from_matrices({"a": a, "b": b})
        # Canonical order from the first tomo; b's columns are reordered to match.
        assert ds.columns == ["x", "y"]
        np.testing.assert_allclose(ds.column("x"), [1.0, 2.0, 6.0])
        np.testing.assert_allclose(ds.column("y"), [3.0, 4.0, 5.0])

    def test_parquet_cache_round_trip(self, tmp_path: Path) -> None:
        ds = _dataset()
        cache = tmp_path / "cache"
        cache.mkdir()
        for base, m in ds.per_tomo():
            m.to_parquet(cache / f"{base}.features.parquet")
        loaded = SearchDataset.from_cache_dir(cache)
        assert loaded.n == ds.n
        assert loaded.n_tomos == 2
        np.testing.assert_allclose(
            np.sort(loaded.column("cc_cluster_density")),
            np.sort(ds.column("cc_cluster_density")),
            rtol=1e-5,
        )

    def test_from_parquet_paths_records_missing(self, tmp_path: Path) -> None:
        m = _tomo(5, 5, 0)
        p = tmp_path / "a.parquet"
        m.to_parquet(p)
        ds = SearchDataset.from_parquet_paths({"a": p, "b": tmp_path / "nope.parquet"})
        assert ds.bases == ["a"]
        assert ds.missing == ["b"]
        assert ds.n == 10


# --------------------------------------------------------------------------- #
# WeakLabelSource + cull parsing                                              #
# --------------------------------------------------------------------------- #
class TestWeakLabels:
    def test_template_idx_weak_negative_prior(self) -> None:
        tix = np.array([1, 2, 3, 1, 1], dtype=np.int64)
        wl = WeakLabelSource(ref1_confidence=0.3).template_idx_labels(tix)
        assert wl.n_neg == 3
        assert wl.n_pos == 0
        np.testing.assert_array_equal(wl.label, [NEGATIVE, UNKNOWN, UNKNOWN, NEGATIVE, NEGATIVE])
        np.testing.assert_allclose(wl.weight[wl.label == NEGATIVE], 0.3)
        assert wl.weight[1] == 0.0  # unknown -> zero confidence

    def test_col26_removed_is_strong_negative(self) -> None:
        active = np.array([1, 1, -9999, 1], dtype=np.float64)
        wl = WeakLabelSource().col26_labels(active)
        assert wl.n_neg == 1
        assert wl.weight[2] == pytest.approx(1.0)
        assert wl.n_labeled == 1  # all-active would be uninformative

    def test_weak_labels_combine_prefers_higher_confidence(self) -> None:
        a = WeakLabels(np.array([0, -1, 0], np.int8), np.array([0.3, 0.0, 0.3], np.float32), ["a"])
        b = WeakLabels(np.array([1, 0, -1], np.int8), np.array([0.9, 1.0, 0.0], np.float32), ["b"])
        merged = a.combine(b)
        # row0: b higher conf -> 1; row1: a unknown -> take b's 0; row2: b unknown -> keep a's 0.
        np.testing.assert_array_equal(merged.label, [1, 0, 0])
        np.testing.assert_allclose(merged.weight, [0.9, 1.0, 0.3])

    def test_parse_class_keep_headers(self, tmp_path: Path) -> None:
        p = tmp_path / "cycle007_ClassKeep_STD.txt"
        p.write_text("Classes kept:\n[3,5; 1.*ones(1,2)]\n\nClasses dropped:\n[1,2,4]\n")
        cull = parse_class_cull(p)
        assert cull.kind == "keep"
        assert cull.cycle == 7
        assert cull.retained == [3, 5]
        assert cull.removed == [1, 2, 4]

    def test_parse_class_mods_counts(self, tmp_path: Path) -> None:
        p = tmp_path / "cycle002_ClassMods_STD.txt"
        p.write_text(
            "Classes removed:\n[9,10]\n\nClasses retained:\n[1,2; 1.*ones(1,2)]\n\n"
            "removed:\t40\nremaining:60\norig:100\n"
        )
        cull = parse_class_cull(p)
        assert cull.removed == [9, 10]
        assert cull.retained == [1, 2]
        assert (cull.n_removed, cull.n_remaining, cull.n_orig) == (40, 60, 100)
        assert cull.keep_fraction == pytest.approx(0.6)

    def test_parse_missing_lists_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "cycle001_ClassMods_STD.txt"
        p.write_text("nothing useful here\n")
        with pytest.raises(ValueError, match="no class"):
            parse_class_cull(p)

    @pytest.mark.skipif(not ROUND_DIR.is_dir(), reason="real round_4 dir absent")
    def test_real_cull_files_match_spec_counts(self) -> None:
        culls = {(c.cycle, c.kind): c for c in WeakLabelSource(round_dir=ROUND_DIR).cull_context()}
        assert set(find_cull_files(ROUND_DIR))  # discovery non-empty
        c2 = culls[(2, "mods")]
        assert (c2.n_orig, c2.n_remaining) == (133867, 89767)  # SPEC §10.2
        assert len(c2.removed) == 54 and len(c2.retained) == 46
        assert culls[(5, "mods")].n_remaining == 73618
        assert culls[(8, "mods")].n_remaining == 49181
        assert culls[(5, "keep")].retained == [33, 50, 72, 85]

    @pytest.mark.skipif(
        not (CONVMAP_DIR / f"{REAL_BASE}.templateIDX").exists(),
        reason="real templateIDX absent",
    )
    def test_real_templateidx_ref1_fraction(self) -> None:
        from mito_filter.emclarity.templateidx import read_template_idx

        tix = read_template_idx(CONVMAP_DIR / f"{REAL_BASE}.templateIDX")
        wl = WeakLabelSource(convmap_dir=CONVMAP_DIR).template_idx_labels(tix)
        assert wl.n == 1249  # SPEC §6 peak count
        assert wl.n_neg == 777  # templateIDX==1 count (SPEC §10.1)
        assert wl.n_neg / wl.n == pytest.approx(0.622, abs=0.01)

    @pytest.mark.skipif(
        not (CONVMAP_DIR / f"{REAL_BASE}.templateIDX").exists(),
        reason="real templateIDX absent",
    )
    def test_build_aligns_disk_templateidx_to_dataset(self) -> None:
        n = 1249
        ds = SearchDataset.from_matrices(
            {REAL_BASE: FeatureMatrix.from_columns({"cc": np.zeros(n)}, np.arange(n))}
        )
        wl = WeakLabelSource(convmap_dir=CONVMAP_DIR).build(ds)
        assert wl.n == n
        assert wl.n_neg == 777

    def test_build_length_mismatch_raises(self) -> None:
        ds = SearchDataset.from_matrices(
            {"b": FeatureMatrix.from_columns({"cc": np.zeros(4)}, np.arange(4))}
        )
        src = WeakLabelSource()
        with pytest.raises(ValueError, match="!="):
            src.build(ds, template_idx={"b": np.array([1, 2, 3], dtype=np.int64)})


# --------------------------------------------------------------------------- #
# Objective                                                                   #
# --------------------------------------------------------------------------- #
class TestObjective:
    def test_self_sup_anchors_separate_groups(self) -> None:
        ds = _dataset()
        obj = SelfSupervisedObjective()
        _b, feats = next(iter(ds.per_tomo()))
        fp, tg, informative = obj.anchors_for(feats)
        assert informative
        # First 120 rows are targets, last 80 are FPs -> anchors reflect that.
        assert tg[:120].mean() > tg[120:].mean()
        assert fp[120:].mean() > fp[:120].mean()

    def test_uninformative_features_flagged(self) -> None:
        m = FeatureMatrix.from_columns({"unrelated": np.arange(10.0)}, np.arange(10))
        _fp, _tg, informative = SelfSupervisedObjective().anchors_for(m)
        assert not informative

    def test_weak_label_objective_bce(self) -> None:
        ds = _dataset()
        model = _model()
        n = ds.n
        labels = WeakLabels(
            np.where(np.arange(n) < 200, 1, 0).astype(np.int8),
            np.ones(n, np.float32),
            ["synthetic"],
        )
        val = WeakLabelObjective(labels).evaluate(model, ds)
        assert val.components["n_labeled"] == float(n)
        assert val.total <= 0.0  # -BCE

    def test_weak_label_all_unknown_is_neutral(self) -> None:
        ds = _dataset()
        labels = WeakLabels(np.full(ds.n, UNKNOWN, np.int8), np.zeros(ds.n, np.float32))
        val = WeakLabelObjective(labels).evaluate(_model(), ds)
        assert val.total == 0.0

    def test_composite_sums_terms(self) -> None:
        ds = _dataset()
        model = _model()
        ss = SelfSupervisedObjective()
        labels = WeakLabels(np.full(ds.n, UNKNOWN, np.int8), np.zeros(ds.n, np.float32))
        comp = CompositeObjective.physics_plus_weak(
            ss, WeakLabelObjective(labels), weak_weight=0.25
        )
        cv = comp.evaluate(model, ds)
        # weak term is neutral (0) -> composite == self-sup total.
        assert cv.total == pytest.approx(ss.evaluate(model, ds).total)


# --------------------------------------------------------------------------- #
# ParameterSpace                                                              #
# --------------------------------------------------------------------------- #
class TestParameterSpace:
    def test_from_model_includes_constraints_weights_bias_tau(self) -> None:
        model = _model()
        space = ParameterSpace.from_model(model)
        names = set(space.names)
        assert "gold_ice_cluster::cc_thresh" in names
        assert "surface_coherence::coh_thresh" in names
        assert "combiner::w::gold_ice_cluster" in names
        assert "combiner::bias" in names
        assert TAU_KEY in names

    def test_from_model_picks_up_membrane_constraint_params(self) -> None:
        """A model carrying the membrane constraint exposes every membrane param + weight to the
        tuner, so a future joint tune includes the membrane geometry (no re-run needed here)."""
        from mito_filter.constraints.membrane import MembraneGeometryConstraint

        model = FilterModel([MembraneGeometryConstraint()])
        space = ParameterSpace.from_model(model)
        names = set(space.names)
        for pname in MembraneGeometryConstraint.param_schema:
            assert f"membrane_geometry::{pname}" in names
        # the new mis-facing / vesicle knobs are tunable
        assert "membrane_geometry::misface_weight" in names
        assert "membrane_geometry::vesicle_weight" in names
        assert "combiner::w::membrane_geometry" in names
        # every membrane dimension respects its schema bounds
        by_name = {d.name: d for d in space.dimensions}
        for pname, spec in MembraneGeometryConstraint.param_schema.items():
            d = by_name[f"membrane_geometry::{pname}"]
            assert d.lo == spec.lo and d.hi == spec.hi

    def test_clip_respects_bounds(self) -> None:
        space = ParameterSpace([Dimension("a", 0.0, 1.0, 0.5), Dimension("b", 2.0, 4.0, 3.0)])
        clipped = space.clip({"a": -5.0, "b": 10.0, "unknown": 7.0})
        assert clipped["a"] == 0.0 and clipped["b"] == 4.0
        assert clipped["unknown"] == 7.0  # passthrough

    def test_suggest_optuna_within_bounds(self) -> None:
        import optuna

        space = ParameterSpace.from_model(_model())
        seen = {}

        def _obj(trial: "optuna.trial.Trial") -> float:
            theta = space.suggest_optuna(trial)
            seen.update(theta)
            return 0.0

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        optuna.create_study().optimize(_obj, n_trials=3)
        for d in space.dimensions:
            assert d.lo <= seen[d.name] <= d.hi

    def test_duplicate_dimension_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            ParameterSpace([Dimension("a", 0, 1, 0.5), Dimension("a", 0, 1, 0.5)])


class TestWeightSignPriors:
    """Physics sign priors: every FP-axis fusion weight is constrained non-positive (module
    docstring) so ``keep_prob = sigmoid(bias + Σ w_j s_j)`` is monotone non-increasing in each
    FP score -- the tuner cannot reproduce the counter-intuitive positive round_4_fitted head."""

    def test_fp_axes_bounded_non_positive_by_default(self) -> None:
        space = ParameterSpace.from_model(_model())
        by_name = {d.name: d for d in space.dimensions}
        for name in ("gold_ice_cluster", "surface_coherence"):
            d = by_name[f"combiner::w::{name}"]
            assert d.hi == 0.0, name  # weight cannot go positive
            assert d.lo == -8.0, name  # full negative magnitude available
            assert d.init <= 0.0, name  # seeded on the physical side

    def test_no_sampled_weight_is_positive(self) -> None:
        import optuna

        space = ParameterSpace.from_model(_model())
        seen: list[float] = []

        def _obj(trial: "optuna.trial.Trial") -> float:
            theta = space.suggest_optuna(trial)
            seen.extend(v for k, v in theta.items() if k.startswith("combiner::w::"))
            return 0.0

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        optuna.create_study().optimize(_obj, n_trials=25)
        assert seen and max(seen) <= 0.0

    def test_random_sampler_respects_sign(self) -> None:
        space = ParameterSpace.from_model(_model())
        rng = np.random.default_rng(0)
        for _ in range(200):
            theta = space.sample_random(rng)
            for k, v in theta.items():
                if k.startswith("combiner::w::"):
                    assert v <= 0.0

    def test_keep_sign_override_flips_half_line(self) -> None:
        from mito_filter.optimize.space import KEEP_INCREASING_SIGN, SIGN_FREE

        space = ParameterSpace.from_model(
            _model(),
            weight_signs={"gold_ice_cluster": KEEP_INCREASING_SIGN, "surface_coherence": SIGN_FREE},
        )
        by_name = {d.name: d for d in space.dimensions}
        keep = by_name["combiner::w::gold_ice_cluster"]
        assert (keep.lo, keep.hi) == (0.0, 8.0) and keep.init >= 0.0
        free = by_name["combiner::w::surface_coherence"]
        assert (free.lo, free.hi) == (-8.0, 8.0)

    def test_signed_weight_bounds_helper(self) -> None:
        from mito_filter.optimize.space import (
            FP_INCREASING_SIGN,
            KEEP_INCREASING_SIGN,
            SIGN_FREE,
            signed_weight_bounds,
        )

        assert signed_weight_bounds(FP_INCREASING_SIGN, 8.0) == (-8.0, 0.0)
        assert signed_weight_bounds(KEEP_INCREASING_SIGN, 8.0) == (0.0, 8.0)
        assert signed_weight_bounds(SIGN_FREE, 8.0) == (-8.0, 8.0)

    def test_positive_config_weight_seeds_negative_init(self) -> None:
        """A physics config that lists positive FP weights (fp_logit convention) is re-seeded on
        the physical negative side -- magnitude preserved, sign forced."""
        from mito_filter.model.filter_model import Combiner

        names = ["gold_ice_cluster", "surface_coherence"]
        model = FilterModel(_model().constraints, Combiner(names, np.array([3.0, 1.0]), bias=-1.5))
        by_name = {d.name: d for d in ParameterSpace.from_model(model).dimensions}
        assert by_name["combiner::w::gold_ice_cluster"].init == -3.0
        assert by_name["combiner::w::surface_coherence"].init == -1.0

    def test_fitted_head_is_monotone_fp(self) -> None:
        """End to end: after a real fit under the sign prior EVERY combiner weight is <= 0, so
        keep-prob is monotone non-increasing in each FP score (P(FP) monotone non-decreasing)."""
        ds = _dataset()
        model = _model()
        Tuner(model, SelfSupervisedObjective(), optimizer=OptunaOptimizer(seed=1)).fit(
            ds, n_trials=40, dataset_name="synthetic"
        )
        assert np.all(model.combiner.weights <= 1e-9)
        # Directly verify monotonicity: raising any one FP score never raises keep-prob.
        base = FeatureMatrix.from_columns(
            {
                "cc_cluster_density": np.array([2.0]),
                "normal_coherence": np.array([0.5]),
                "surface_residual": np.array([50.0]),
                "curvature": np.array([0.01]),
                "blobness": np.array([0.3]),
            },
            np.arange(1),
        )
        p0 = float(model.forward(base)[0])
        hotter = FeatureMatrix.from_columns(
            {
                "cc_cluster_density": np.array([9.0]),  # deep inside a gold/ice cluster
                "normal_coherence": np.array([0.5]),
                "surface_residual": np.array([50.0]),
                "curvature": np.array([0.01]),
                "blobness": np.array([0.3]),
            },
            np.arange(1),
        )
        assert float(model.forward(hotter)[0]) <= p0 + 1e-9


# --------------------------------------------------------------------------- #
# Optimizers + Tuner (the core "tuner improves the objective" test)           #
# --------------------------------------------------------------------------- #
class TestTuner:
    def test_optuna_tuner_improves_objective(self) -> None:
        ds = _dataset()
        model = _model()
        obj = SelfSupervisedObjective()
        before = obj.evaluate(model, ds).total
        tuner = Tuner(model, obj, optimizer=OptunaOptimizer(seed=1))
        out = tuner.fit(ds, n_trials=40, dataset_name="synthetic")
        after = obj.evaluate(model, ds).total
        assert after > before + 0.1  # meaningful improvement
        assert out.report.physics_separation > 0.5

    def test_random_optimizer_improves_objective(self) -> None:
        ds = _dataset()
        model = _model()
        obj = SelfSupervisedObjective()
        before = obj.evaluate(model, ds).total
        Tuner(model, obj, optimizer=RandomOptimizer(seed=2)).fit(ds, n_trials=60)
        assert obj.evaluate(model, ds).total > before

    def test_fit_emits_loadable_config(self, tmp_path: Path) -> None:
        ds = _dataset()
        model = _model()
        out = Tuner(model, SelfSupervisedObjective(), optimizer=OptunaOptimizer(seed=3)).fit(
            ds, n_trials=20, dataset_name="synthetic"
        )
        cfg = out.config
        assert isinstance(cfg, FittedConfig)
        assert 0.05 <= cfg.tau <= 0.95
        assert cfg.combiner["names"] == [c.name for c in model.constraints]
        assert set(cfg.features) == set(model.needs_features)
        p = tmp_path / "fit.yaml"
        cfg.save(p)
        assert FittedConfig.load(p).theta == cfg.theta

    def test_warm_start_seeds_search(self) -> None:
        ds = _dataset()
        # A good prior config from a first fit transfers to a fresh model.
        model_a = _model()
        first = Tuner(model_a, SelfSupervisedObjective(), optimizer=OptunaOptimizer(seed=1)).fit(
            ds, n_trials=30
        )
        model_b = _model()
        obj = SelfSupervisedObjective()
        warm = Tuner(model_b, obj, optimizer=OptunaOptimizer(seed=9)).fit(
            ds, n_trials=5, warm_start=first.config
        )
        # Even a tiny budget lands a good value because the warm start is enqueued first.
        assert warm.report.physics_separation > 0.5


# --------------------------------------------------------------------------- #
# Report                                                                      #
# --------------------------------------------------------------------------- #
class TestReport:
    def test_report_pr_with_both_classes(self) -> None:
        ds = _dataset()
        model = _model()
        Tuner(model, SelfSupervisedObjective(), optimizer=OptunaOptimizer(seed=1)).fit(
            ds, n_trials=40
        )
        n = ds.n
        # Targets are the first 120 of each 200-row tomo -> rows [0:120] and [200:320].
        y = np.full(n, UNKNOWN, dtype=np.int8)
        y[:120] = 1
        y[120:200] = 0
        y[200:320] = 1
        y[320:400] = 0
        labels = WeakLabels(y, np.ones(n, np.float32), ["synthetic"])
        rep = build_report(model, ds, tau=0.5, weak_labels=labels)
        assert isinstance(rep, SeparationReport)
        assert rep.weak_auc is not None and rep.weak_auc > 0.8
        assert rep.weak_ap is not None
        assert rep.weak_separation is not None and rep.weak_separation > 0.2
        assert "SearchDataset" in rep.render_text()

    def test_report_without_both_classes_is_graceful(self) -> None:
        ds = _dataset()
        model = _model()
        # Only negatives (templateIDX-style prior) -> no PR/AUC, but no crash.
        y = np.full(ds.n, UNKNOWN, dtype=np.int8)
        y[:50] = 0
        labels = WeakLabels(y, np.full(ds.n, 0.3, np.float32), ["templateIDX==1"])
        rep = build_report(model, ds, tau=0.5, weak_labels=labels)
        assert rep.weak_separation is None
        assert rep.n_weak_neg == 50 and rep.n_weak_pos == 0
        assert "self-supervised only" in rep.render_text()
