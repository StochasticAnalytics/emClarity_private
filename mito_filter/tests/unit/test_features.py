"""Unit tests for the two-phase feature engine + extractors (features/*).

Synthetic fields exercise every extractor's physics; a real ``H99_2_100_1_bin5`` crop verifies
the CC-gating rule (DESIGN §9.3) actually excludes background candidates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

import numpy as np
import pytest

from mito_filter.candidates.source import CandidateSet
from mito_filter.core.field import DenseField, VectorField
from mito_filter.core.grid import VoxelGrid
from mito_filter.emclarity.constants import APIX_A
from mito_filter.features.curvature import (
    NormalCoherence,
    PrincipalCurvature,
    SurfaceFitResidual,
)
from mito_filter.features.engine import FEATURE_REGISTRY, FeatureEngine
from mito_filter.features.extractor import ArrayT, BlockCtx, FeatureExtractor
from mito_filter.features.isolation import NeighborDensity, OffSurfaceIsolation
from mito_filter.features.local_stats import (
    Blobness,
    GoldFiducialProximity,
    ScoreClusterDensity,
)
from mito_filter.features.membrane import (
    ClosedShellScore,
    InsideOutsideSign,
    MembraneDistance,
    MembraneFacing,
)
from mito_filter.features.priors import (
    PhysicalPosition,
    RawScore,
    SnrScore,
    TemplateIdxPrior,
)

REAL_DIR = Path("/scratch/siracusa/full_enchilada_3/six_hours_round_4/convmap_wedgeType_2_bin5")
REAL_BASE = "H99_2_100_1_bin5"


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _grid(shape: Tuple[int, int, int] = (40, 40, 40), apix: float = APIX_A) -> VoxelGrid:
    return VoxelGrid(shape, apix)


def _ctx(grid: VoxelGrid, **meta: object) -> BlockCtx:
    return BlockCtx(grid=grid, meta=meta)


def _cand(coords: Any, grid: VoxelGrid, **attrs: Any) -> CandidateSet:
    return CandidateSet(np.asarray(coords, dtype=float), grid, dict(attrs))


# --------------------------------------------------------------------------- #
# priors                                                                       #
# --------------------------------------------------------------------------- #
def test_raw_score_from_attr() -> None:
    g = _grid()
    cc = np.array([6.0, 12.0, 4.0], dtype=float)
    c = _cand([[1, 1, 1], [2, 2, 2], [3, 3, 3]], g, cc=cc)
    out = RawScore().extract(c, {}, _ctx(g))
    np.testing.assert_allclose(out["raw_score"], cc.astype(np.float32))


def test_snr_score_zscore_fallback() -> None:
    g = _grid()
    cc = np.array([3.28, 4.24, 5.20], dtype=float)  # mu, mu+2s, mu+4s at s=0.48
    c = _cand([[1, 1, 1], [2, 2, 2], [3, 3, 3]], g, cc=cc)
    out = SnrScore().extract(c, {}, _ctx(g, bg_mean=3.28, bg_std=0.48))
    np.testing.assert_allclose(out["snr"], [0.0, 2.0, 4.0], atol=1e-4)


def test_template_idx_prior_ref1_negative() -> None:
    g = _grid()
    tid = np.array([1, 2, 3, 1], dtype=float)
    c = _cand(np.zeros((4, 3)), g, template_idx=tid)
    out = TemplateIdxPrior().extract(c, {}, _ctx(g))
    np.testing.assert_array_equal(out["is_ref1"], [1.0, 0.0, 0.0, 1.0])
    np.testing.assert_array_equal(out["template_idx"], tid.astype(np.float32))


def test_physical_position_world_and_depth() -> None:
    g = _grid(shape=(41, 40, 40))
    c = _cand([[0, 0, 0], [40, 8, 16]], g)
    out = PhysicalPosition().extract(c, {}, _ctx(g))
    np.testing.assert_allclose(out["pos_z_A"], [0.0, 40 * APIX_A], atol=1e-3)
    np.testing.assert_allclose(out["pos_x_A"], [0.0, 16 * APIX_A], atol=1e-3)
    np.testing.assert_allclose(out["depth_frac"], [0.0, 1.0], atol=1e-6)


# --------------------------------------------------------------------------- #
# local_stats                                                                  #
# --------------------------------------------------------------------------- #
def test_score_cluster_density_elevated() -> None:
    g = _grid()
    vol = np.full(g.shape, 3.28, dtype=np.float32)
    vol[18:23, 18:23, 18:23] = 10.0  # a compact elevated cluster
    f = DenseField.from_array("cc", g, vol)
    c = _cand([[20, 20, 20], [5, 5, 5]], g)
    out = ScoreClusterDensity(radius=2).extract(c, {"cc": f}, _ctx(g))
    assert out["cc_cluster_z"][0] > out["cc_cluster_z"][1]
    assert out["cc_local_max"][0] == pytest.approx(10.0)


def test_blobness_blob_vs_sheet() -> None:
    g = _grid()
    zz, yy, xx = np.mgrid[0:40, 0:40, 0:40].astype(np.float32)
    vol = np.full(g.shape, 3.0, dtype=np.float32)
    # isotropic bright blob at (12,12,12)
    vol += 8.0 * np.exp(-((zz - 12) ** 2 + (yy - 12) ** 2 + (xx - 12) ** 2) / (2 * 3.0**2))
    # a bright thin sheet (thin in z, extended in y,x) around z=28
    vol += 8.0 * np.exp(-((zz - 28) ** 2) / (2 * 1.5**2))
    f = DenseField.from_array("cc", g, vol.astype(np.float32))
    c = _cand([[12, 12, 12], [28, 20, 20]], g)
    out = Blobness(step=2).extract(c, {"cc": f}, _ctx(g))
    blob, sheet = 0, 1
    assert out["blobness"][blob] > out["blobness"][sheet]
    assert out["plateness"][sheet] > out["plateness"][blob]


def test_gold_proximity_points_and_missing() -> None:
    g = _grid()
    c = _cand([[10, 10, 10], [30, 30, 30]], g)
    gold = np.array([[10, 10, 12]], dtype=float)  # near candidate 0 (2 vox = 25 A)
    out = GoldFiducialProximity(near_A=100.0).extract(c, {}, _ctx(g, gold_points_zyx=gold))
    assert out["gold_dist_A"][0] == pytest.approx(2 * APIX_A, rel=1e-4)
    assert out["near_gold"][0] == 1.0 and out["near_gold"][1] == 0.0
    # MISSING -> neutral (inf distance, 0 proximity)
    miss = GoldFiducialProximity().extract(c, {}, _ctx(g))
    assert np.isinf(miss["gold_dist_A"]).all()
    np.testing.assert_array_equal(miss["near_gold"], [0.0, 0.0])


# --------------------------------------------------------------------------- #
# membrane                                                                     #
# --------------------------------------------------------------------------- #
def _sphere_sdf_field(grid: VoxelGrid, center: Sequence[float], r_vox: float) -> DenseField:
    zz, yy, xx = np.mgrid[0 : grid.nz, 0 : grid.ny, 0 : grid.nx].astype(np.float64)
    d = np.sqrt((zz - center[0]) ** 2 + (yy - center[1]) ** 2 + (xx - center[2]) ** 2) - r_vox
    return DenseField.from_array("membrane_sdf", grid, d.astype(np.float32))


def test_membrane_distance_and_sign() -> None:
    g = _grid()
    f = _sphere_sdf_field(g, (20, 20, 20), 15.0)
    c = _cand([[20, 20, 20], [20, 20, 35], [20, 20, 39]], g)  # inside, on-surface, outside
    dist = MembraneDistance().extract(c, {"membrane_sdf": f}, _ctx(g))["membrane_dist_A"]
    assert dist[0] == pytest.approx(-15 * APIX_A, rel=1e-3)
    assert abs(dist[1]) < APIX_A
    sign = InsideOutsideSign().extract(c, {"membrane_sdf": f}, _ctx(g))["inside_sign"]
    np.testing.assert_array_equal(sign, [-1.0, 0.0, 1.0])


def test_closed_shell_curvature_matches_two_over_r() -> None:
    g = _grid()
    r_vox = 15.0
    f = _sphere_sdf_field(g, (20, 20, 20), r_vox)
    c = _cand([[20, 20, 35]], g)  # on the +x surface
    out = ClosedShellScore(step=2).extract(c, {"membrane_sdf": f}, _ctx(g))
    r_A = r_vox * APIX_A
    assert out["closed_shell"][0] == pytest.approx(2.0 / r_A, rel=0.25)


def test_membrane_missing_is_neutral() -> None:
    g = _grid()
    c = _cand([[10, 10, 10]], g)
    assert np.isnan(MembraneDistance().extract(c, {}, _ctx(g))["membrane_dist_A"]).all()
    assert np.isnan(InsideOutsideSign().extract(c, {}, _ctx(g))["inside_sign"]).all()
    assert np.isnan(ClosedShellScore().extract(c, {}, _ctx(g))["closed_shell"]).all()
    assert np.isnan(MembraneFacing().extract(c, {}, _ctx(g))["membrane_facing"]).all()


def test_membrane_facing_aligns_with_outward_normal() -> None:
    """Template +Z along the membrane OUTWARD normal -> facing ~+1; anti-aligned -> ~-1."""
    g = _grid()
    f = _sphere_sdf_field(g, (20, 20, 20), 15.0)
    # On the +x surface the membrane outward normal is +x = (0, 0, 1) in (z, y, x).
    out_n = np.array([0.0, 0.0, 1.0])
    c = _cand([[20, 20, 35], [20, 20, 35], [20, 20, 35]], g, normal=[out_n, -out_n, [0, 1, 0]])
    facing = MembraneFacing(step=2).extract(c, {"membrane_sdf": f}, _ctx(g))["membrane_facing"]
    assert facing[0] == pytest.approx(1.0, abs=0.05)  # outward-aligned target
    assert facing[1] == pytest.approx(-1.0, abs=0.05)  # wrong-side / inward-facing
    assert abs(facing[2]) < 0.2  # tangent normal is neither in nor out


def test_membrane_facing_neutral_without_template_normal() -> None:
    g = _grid()
    f = _sphere_sdf_field(g, (20, 20, 20), 15.0)
    c = _cand([[20, 20, 35]], g)  # no 'normal' attr, no dense normal field
    out = MembraneFacing().extract(c, {"membrane_sdf": f}, _ctx(g))
    assert np.isnan(out["membrane_facing"]).all()


# --------------------------------------------------------------------------- #
# curvature (CC-gated)                                                         #
# --------------------------------------------------------------------------- #
def _membrane_patch(
    z: float = 20.0, span: int = 5, cc: float = 10.0
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    g = np.linspace(-span, span, 2 * span + 1)
    yy, xx = np.meshgrid(g, g)
    coords = np.stack([np.full(yy.size, z), yy.ravel() + 20, xx.ravel() + 20], axis=1)
    normals = np.tile([1.0, 0.0, 0.0], (coords.shape[0], 1))  # coherent, all +z
    ccv = np.full(coords.shape[0], cc)
    return coords, normals, ccv


def test_normal_coherence_gating_excludes_background() -> None:
    g = _grid()
    mem_xyz, mem_n, mem_cc = _membrane_patch()
    rng = np.random.default_rng(0)
    m = 60
    bg_xyz = rng.uniform([16, 15, 15], [24, 25, 25], size=(m, 3))
    bg_n = rng.standard_normal((m, 3))
    bg_cc = np.full(m, 3.3)  # background CC, below the gate
    coords = np.vstack([mem_xyz, bg_xyz])
    normals = np.vstack([mem_n, bg_n])
    ccv = np.concatenate([mem_cc, bg_cc])
    c = _cand(coords, g, cc=ccv, normal=normals)
    n_mem = mem_xyz.shape[0]

    gated = NormalCoherence(radius_A=400.0, cc_gate=5.0).extract(c, {}, _ctx(g))
    coh = gated["normal_coherence"]
    # background rows are gated out -> NaN; membrane rows finite and coherent.
    assert np.isnan(coh[n_mem:]).all()
    assert np.isfinite(coh[:n_mem]).all()
    assert np.nanmedian(coh[:n_mem]) > 0.99

    # WITHOUT the gate the random background normals swamp the membrane coherence.
    ungated = NormalCoherence(radius_A=400.0, cc_gate=0.0).extract(c, {}, _ctx(g))
    assert np.median(ungated["normal_coherence"][:n_mem]) < np.median(coh[:n_mem])


def test_surface_residual_and_curvature_on_plane() -> None:
    g = _grid()
    mem_xyz, mem_n, mem_cc = _membrane_patch(span=6)
    c = _cand(mem_xyz, g, cc=mem_cc, normal=mem_n)
    res = SurfaceFitResidual(radius_A=400.0, cc_gate=5.0).extract(c, {}, _ctx(g))
    assert np.nanmax(res["surface_residual_A"]) < 1.0  # a flat plane fits with ~0 residual
    curv = PrincipalCurvature(radius_A=400.0, cc_gate=5.0).extract(c, {}, _ctx(g))
    assert np.nanmax(np.abs(curv["curv_mean"])) < 1e-3  # ~0 curvature for a plane


def test_curvature_dense_normal_field_path() -> None:
    g = _grid()
    mem_xyz, mem_n, mem_cc = _membrane_patch(span=4)
    vol = np.zeros(g.shape + (3,), dtype=np.float32)
    ipos = np.rint(mem_xyz).astype(int)
    for (z, y, x), nrm in zip(ipos, mem_n):
        vol[z, y, x] = nrm
    ccvol = np.full(g.shape, 3.0, dtype=np.float32)
    for z, y, x in ipos:
        ccvol[z, y, x] = 10.0
    fields: Mapping[str, DenseField] = {
        "normal": VectorField.from_array("normal", g, vol, channels=3),
        "cc": DenseField.from_array("cc", g, ccvol),
    }
    c = _cand(mem_xyz.astype(float), g)  # no attrs -> must use the fields
    ex = NormalCoherence(radius_A=400.0, cc_gate=5.0, normal_source="field")
    assert set(ex.needs_fields) == {"normal", "cc"}
    out = ex.extract(c, fields, _ctx(g))
    assert np.nanmedian(out["normal_coherence"]) > 0.99


# --------------------------------------------------------------------------- #
# isolation                                                                    #
# --------------------------------------------------------------------------- #
def test_neighbor_density_dense_vs_isolated() -> None:
    g = _grid()
    cluster = np.array([[20, 20 + i, 20 + j] for i in range(-2, 3) for j in range(-2, 3)], float)
    loner = np.array([[5, 5, 5]], float)
    c = _cand(np.vstack([cluster, loner]), g)
    out = NeighborDensity(radius_A=200.0).extract(c, {}, _ctx(g))
    assert out["neighbor_count"][:-1].mean() > 3
    assert out["neighbor_count"][-1] == 0.0


def test_off_surface_isolation_plane_vs_off() -> None:
    g = _grid()
    grid_1d = np.linspace(-4, 4, 9)
    yy, xx = np.meshgrid(grid_1d, grid_1d)
    plane = np.stack([np.full(yy.size, 20.0), yy.ravel() + 20, xx.ravel() + 20], axis=1)
    off = np.array([[26.0, 20.0, 20.0]])  # 6 vox off the plane, but with plane neighbors
    c = _cand(np.vstack([plane, off]), g)
    out = OffSurfaceIsolation(radius_A=400.0, min_neighbors=4).extract(c, {}, _ctx(g))
    on_plane = out["off_surface_A"][:-1]
    assert np.median(on_plane) < 1.0
    assert out["off_surface_A"][-1] == pytest.approx(6.0 * APIX_A, rel=0.2)
    assert out["is_isolated"][-1] == 0.0


# --------------------------------------------------------------------------- #
# engine                                                                       #
# --------------------------------------------------------------------------- #
class _ThetaDep(FeatureExtractor):
    produces = ("theta_col",)
    needs_fields = ()
    theta_dependent = True

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        return {"theta_col": np.arange(cand.n, dtype=np.float32)}


def test_engine_assemble_cache_and_theta(tmp_path: Path) -> None:
    g = _grid()
    cc = np.array([6.0, 12.0], dtype=float)
    sid = np.array([101, 102], dtype=np.int64)
    c = _cand([[1, 1, 1], [2, 2, 2]], g, cc=cc, template_idx=np.array([1, 2.0]), subtomo_id=sid)
    eng = FeatureEngine([RawScore(), TemplateIdxPrior(), _ThetaDep()])

    assert "theta_col" in eng.theta_dependent_columns
    assert "raw_score" in eng.cached_columns

    cache = tmp_path / "feat.parquet"
    fm = eng.run(c, {}, _ctx(g), cache_path=cache)
    # full matrix has the theta-dependent column; row ids are the subtomo ids.
    assert "theta_col" in fm and "raw_score" in fm
    np.testing.assert_array_equal(fm.row_ids, sid)
    np.testing.assert_allclose(fm.column("raw_score"), cc.astype(np.float32))

    # cache holds ONLY theta-independent columns.
    cached = eng.run_cached(cache)
    assert "theta_col" not in cached
    assert "raw_score" in cached and "is_ref1" in cached
    np.testing.assert_array_equal(cached.row_ids, sid)


def test_engine_rejects_duplicate_columns() -> None:
    with pytest.raises(ValueError, match="duplicate feature column"):
        FeatureEngine([RawScore(), RawScore()])


def test_engine_skip_theta_dependent() -> None:
    g = _grid()
    c = _cand([[1, 1, 1]], g, cc=np.array([6.0]))
    eng = FeatureEngine([RawScore(), _ThetaDep()])
    fm = eng.run(c, {}, _ctx(g), include_theta_dependent=False)
    assert "theta_col" not in fm
    assert "raw_score" in fm


def test_registry_has_all_extractors() -> None:
    for name in (
        "raw_score",
        "snr_score",
        "template_idx_prior",
        "physical_position",
        "score_cluster_density",
        "blobness",
        "gold_fiducial_proximity",
        "membrane_distance",
        "inside_outside_sign",
        "closed_shell_score",
        "membrane_facing",
        "normal_coherence",
        "surface_fit_residual",
        "principal_curvature",
        "neighbor_density",
        "off_surface_isolation",
    ):
        assert name in FEATURE_REGISTRY


# --------------------------------------------------------------------------- #
# real data: CC-gating on an H99_2_100_1_bin5 crop                             #
# --------------------------------------------------------------------------- #
@pytest.fixture
def real_files() -> Tuple[Path, Path]:
    # The dev-set dir can be mid-regeneration (a live dense-angle re-run), so discover any
    # tomo that currently has BOTH a peak csv and its convmap rather than hardcoding one.
    if not REAL_DIR.is_dir():
        pytest.skip("real dev-set dir not present on this host")
    for conv in sorted(REAL_DIR.glob("*_convmap.mrc")):
        csv = REAL_DIR / conv.name.replace("_convmap.mrc", ".csv")
        if csv.exists():
            return csv, conv
    pytest.skip("no real dev-set tomo with both csv + convmap available right now")


def test_cc_gating_excludes_background_on_real_crop(real_files: Tuple[Path, Path]) -> None:
    import mrcfile

    from mito_filter.emclarity.csv_io import read_peaks

    csv, conv = real_files
    pc = read_peaks(csv)
    m = mrcfile.mmap(str(conv), mode="r", permissive=True)
    sh = m.data.shape
    grid = VoxelGrid((int(sh[0]), int(sh[1]), int(sh[2])), APIX_A)

    # Real peaks (all CC >= 6.07) restricted to a spatial crop.
    xyz = np.asarray(pc.xyz, dtype=float)
    keep = (xyz[:, 0] < 224) & (xyz[:, 1] < 471) & (xyz[:, 2] < 331)
    peak_xyz = xyz[keep][:150]
    peak_cc = np.asarray(pc.get("cc"))[keep][:150]
    peak_nrm = np.asarray(pc.get("normal"))[keep][:150]
    n_peak = peak_xyz.shape[0]
    assert n_peak > 20

    # Synthetic background candidates at random interior voxels; CC read from the REAL
    # convmap (background ~N(3.28,0.48), well below the gate) + random normals.
    rng = np.random.default_rng(1)
    bg = np.stack(
        [rng.uniform(60, 200, 200), rng.uniform(300, 460, 200), rng.uniform(320, 500, 200)],
        axis=1,
    )
    ccf = DenseField.from_array("cc", grid, np.asarray(m.data))
    bg_cc = np.asarray(ccf.sample_at(bg, reduce="center", radius=0), dtype=float)[:120]
    bg = bg[:120]
    bg_nrm = rng.standard_normal((bg.shape[0], 3))

    coords = np.vstack([peak_xyz, bg])
    ccv = np.concatenate([peak_cc, bg_cc])
    nrm = np.vstack([peak_nrm, bg_nrm])
    cand = CandidateSet(coords, grid, {"cc": ccv, "normal": nrm})

    gate = 5.0
    out = NormalCoherence(radius_A=500.0, cc_gate=gate).extract(cand, {}, _ctx(grid))
    coh = out["normal_coherence"]

    # The CC-gating guarantee on REAL values: a coherence is finite EXACTLY where the
    # co-located CC clears the gate; every below-gate (background-CC) candidate is masked.
    expect_finite = ccv >= gate
    np.testing.assert_array_equal(np.isfinite(coh), expect_finite)
    assert np.isfinite(coh[:n_peak]).all()  # all real peaks (CC >= 6.07) retained
    # the low-CC synthetic background is materially rejected, not a no-op gate.
    n_bg_rejected = int(np.isnan(coh[n_peak:]).sum())
    assert n_bg_rejected >= int(0.5 * (coords.shape[0] - n_peak))
