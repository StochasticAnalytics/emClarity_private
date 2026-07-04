"""Contract smoke tests: frozen public API + SPEC constants vs the real data.

These lock the fully-implemented contract surfaces (registry, grid, points,
FeatureMatrix parquet round-trip, FittedConfig yaml I/O) and cross-check the emClarity
constants against the real dev-set files.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from mito_filter.candidates.source import CandidateSet
from mito_filter.constraints.base import ConstraintResult, ParamSpec
from mito_filter.core.backend import Backend, Device
from mito_filter.core.field import Block, DenseField, TomogramFields
from mito_filter.core.grid import VoxelGrid
from mito_filter.core.points import PointCloud
from mito_filter.core.registry import Registry
from mito_filter.emclarity import constants as C
from mito_filter.features.extractor import FeatureMatrix
from mito_filter.model.config import FittedConfig


def test_constants_match_spec() -> None:
    assert C.N_TEMPLATES == 3
    assert C.APIX_A == 12.5
    assert C.SAMPLING_RATE == 5
    assert C.CONVMAP_BYTES == 558_750_208
    assert C.CONVMAP_SHAPE == (448, 942, 662)
    assert C.BACKGROUND_MEAN == 3.28
    assert C.BACKGROUND_STD == 0.48
    assert C.ERASE_RADIUS_A == (210, 210, 320)
    assert C.NORMAL_COLS == (22, 23, 24)  # 0-indexed; SPEC 1-indexed cols 23-25
    assert C.REMOVED_FLAG == -9999
    assert C.PACKED_INDEX_MAX == 2592 > C.FP16_INT_EXACT_MAX == 2048


def test_registry_roundtrip() -> None:
    reg: Registry[object] = Registry("things")

    @reg.register("a")
    class A:
        pass

    assert reg.get("a") is A
    assert isinstance(reg.create("a"), A)
    with pytest.raises(ValueError):
        reg.register_class("a", A)
    with pytest.raises(KeyError):
        reg.get("missing")


def test_grid_world_voxel() -> None:
    g = VoxelGrid(C.CONVMAP_SHAPE, C.APIX_A)
    assert g.n_voxels == 448 * 942 * 662
    ijk = np.array([[1.0, 2.0, 3.0]])
    assert np.allclose(g.voxel(g.world(ijk)), ijk)
    assert g.same_grid(VoxelGrid(C.CONVMAP_SHAPE, 12.5))
    assert not g.same_grid(VoxelGrid((10, 10, 10), 12.5))


def test_points_active_flag() -> None:
    xyz = np.zeros((3, 3))
    pc = PointCloud(xyz, {"active": np.array([True, False, True])})
    assert list(pc.to_active_flag()) == [1, C.REMOVED_FLAG, 1]
    assert pc.subset(np.array([0, 2])).n == 2
    assert pc.with_attr("cc", np.arange(3)).get("cc").shape == (3,)


def test_backend_cpu_default() -> None:
    b = Backend.cpu()
    assert b.device is Device.CPU
    assert b.xp() is np
    assert not b.is_gpu
    assert np.allclose(b.to_numpy(b.asarray([1, 2, 3])), [1, 2, 3])


def test_densefield_from_array_and_block() -> None:
    g = VoxelGrid((16, 20, 24), 12.5)
    arr = np.arange(16 * 20 * 24, dtype=np.float16).reshape(16, 20, 24)
    fld = DenseField.from_array("cc", g, arr)
    blk = Block((2, 6), (3, 9), (4, 10), halo=1)
    out = fld.block(blk)
    assert out.dtype == np.float32
    # halo=1 clipped read spans z[1:7], y[2:10], x[3:11]
    assert out.shape == (6, 8, 8)
    tf = TomogramFields(g, {"cc": fld})
    assert tf.require("cc") is fld
    with pytest.raises(KeyError):
        tf.require("nope")


def test_candidateset_and_featurematrix_parquet(tmp_path: Path) -> None:
    g = VoxelGrid((16, 20, 24), 12.5)
    cs = CandidateSet(np.zeros((4, 3)), g, {"cc": np.arange(4.0)})
    assert cs.n == 4
    assert cs.subset(np.array([True, False, True, False])).n == 2
    fm = FeatureMatrix.from_columns({"cc": np.arange(4.0), "iso": np.ones(4)}, row_ids=np.arange(4))
    assert fm.n == 4 and fm.n_features == 2
    assert np.allclose(fm.column("cc"), np.arange(4.0))
    p = tmp_path / "feat.parquet"
    fm.to_parquet(p)
    fm2 = FeatureMatrix.from_parquet(p)
    assert fm2.columns == ["cc", "iso"]
    assert np.allclose(fm2.matrix, fm.matrix)
    assert np.array_equal(fm2.row_ids, fm.row_ids)


def test_paramspec_and_result() -> None:
    ps = ParamSpec(0.0, 200.0, 50.0)
    assert ps.init == 50.0
    assert ps.clip(500.0) == 200.0
    assert ParamSpec(0.1, 10.0).init == pytest.approx(5.05)
    with pytest.raises(ValueError):
        ParamSpec(1.0, 0.0)
    res = ConstraintResult(per_hit_score=np.zeros(3), name="x")
    assert res.per_hit_flag is None and res.name == "x"


def test_fittedconfig_yaml_roundtrip(tmp_path: Path) -> None:
    fc = FittedConfig(dataset="round_4", theta={"a": 1.0}, tau=0.3, features=["cc"])
    p = tmp_path / "fit.yaml"
    fc.save(p)
    fc2 = FittedConfig.load(p)
    assert fc2.dataset == "round_4"
    assert fc2.theta == {"a": 1.0}
    assert fc2.tau == 0.3
    assert fc2.features == ["cc"]


def test_real_convmap_header(real_convmap_path: Path) -> None:
    """Cross-check the SPEC constants against the real convmap file bytes."""
    with real_convmap_path.open("rb") as f:
        hdr = f.read(1024)
    nx, ny, nz, mode = struct.unpack("<4i", hdr[:16])
    assert (nz, ny, nx) == C.CONVMAP_SHAPE
    assert mode == C.CONVMAP_MODE
    assert real_convmap_path.stat().st_size == C.CONVMAP_BYTES


def test_real_csv_conventions(real_csv_path: Path) -> None:
    """Cross-check csv width, matrix orthonormality, normal, and csv/5 == .pos frame."""
    A = np.array([ln.split() for ln in real_csv_path.read_text().splitlines()], dtype=float)
    assert A.shape[1] == C.N_CSV_COLS
    pos = np.array(
        [
            ln.split()
            for ln in (real_csv_path.parent / f"{real_csv_path.stem}.pos").read_text().splitlines()
        ],
        dtype=float,
    )
    # SPEC §3: csv positions (bin1 px) / 5 == .pos (convmap voxel frame)
    assert np.abs(A[:, list(C.POS_COLS)] / C.SAMPLING_RATE - pos).max() < 1e-5
    # SPEC §2/§4: cols 17-25 column-major -> orthonormal, 3rd column == normal cols 23-25
    for row in A[:50]:
        m = row[list(C.ROTMAT_COLS)].reshape(3, 3, order="F")
        assert np.abs(m @ m.T - np.eye(3)).max() < 5e-6
        assert abs(np.linalg.det(m) - 1.0) < 5e-6
        assert np.allclose(m[:, 2], row[list(C.NORMAL_COLS)], atol=1e-6)
    # SPEC §4 formula (B): analytic normal from euler cols 14,15
    phi, theta = np.radians(A[0, C.EULER_COLS[0]]), np.radians(A[0, C.EULER_COLS[1]])
    n = np.array([np.sin(phi) * np.sin(theta), -np.cos(phi) * np.sin(theta), np.cos(theta)])
    assert np.abs(n - A[0, list(C.NORMAL_COLS)]).max() < 1e-5
    # col26 all active (== 1) in raw TM output
    assert set(np.unique(A[:, C.ACTIVE_COL])) == {1.0}
