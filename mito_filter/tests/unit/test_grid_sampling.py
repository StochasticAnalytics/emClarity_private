"""Sampling tests: neighborhood reduce, trilinear, block streaming, real csv-score parity."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mito_filter.core.chunking import BlockPlan, core_offset_in_read, iter_field_blocks
from mito_filter.core.field import DenseField, VectorField
from mito_filter.core.grid import VoxelGrid
from mito_filter.core.sampling import (
    neighborhood_reduce,
    sample_at_companion_argmax,
    sample_field,
    trilinear_sample,
)

APIX = 12.5


def _scalar_field(vol: np.ndarray) -> DenseField:
    g = VoxelGrid(tuple(vol.shape), APIX)
    return DenseField.from_array("f", g, vol)


def test_neighborhood_center_vs_max() -> None:
    vol = np.zeros((12, 12, 12), dtype=np.float32)
    vol[5, 5, 5] = 9.0
    pts = np.array([[5, 5, 6]], dtype=float)  # adjacent to the spike
    center = neighborhood_reduce(vol, pts, reduce="center", radius=1)
    mx = neighborhood_reduce(vol, pts, reduce="max", radius=1)
    mean = neighborhood_reduce(vol, pts, reduce="mean", radius=1)
    assert center[0] == 0.0
    assert mx[0] == 9.0
    assert 0.0 < mean[0] < 9.0


def test_neighborhood_clips_at_boundary() -> None:
    vol = np.arange(27, dtype=np.float32).reshape(3, 3, 3)
    pts = np.array([[0, 0, 0]], dtype=float)
    # radius reaches out of bounds; must clip, not raise.
    out = neighborhood_reduce(vol, pts, reduce="max", radius=2)
    assert out[0] == vol.max()


def test_trilinear_exact_on_linear_ramp() -> None:
    z, y, x = np.mgrid[0:8, 0:8, 0:8]
    vol = (2.0 * z + 3.0 * y + 5.0 * x).astype(np.float32)
    pts = np.array([[1.3, 2.7, 4.1], [0.0, 0.0, 0.0], [6.5, 6.5, 6.5]], dtype=float)
    got = np.asarray(trilinear_sample(vol, pts))
    expect = 2.0 * pts[:, 0] + 3.0 * pts[:, 1] + 5.0 * pts[:, 2]
    np.testing.assert_allclose(got, expect, atol=1e-4)


def test_sample_at_scalar_and_vector() -> None:
    vol = np.arange(4 * 5 * 6, dtype=np.float32).reshape(4, 5, 6)
    f = _scalar_field(vol)
    pts = np.array([[1, 2, 3], [0, 0, 0]], dtype=float)
    got = np.asarray(f.sample_at(pts, reduce="center"))
    assert got.shape == (2,)
    assert got[0] == vol[1, 2, 3]

    vecvol = np.zeros((4, 5, 6, 3), dtype=np.float32)
    vecvol[1, 2, 3] = [1.0, -2.0, 0.5]
    g = VoxelGrid((4, 5, 6), APIX)
    vf = VectorField.from_array("n", g, vecvol, channels=3)
    gotv = np.asarray(vf.sample_at(pts, reduce="center", radius=0))
    assert gotv.shape == (2, 3)
    np.testing.assert_allclose(gotv[0], [1.0, -2.0, 0.5])


def test_sample_field_matches_module() -> None:
    vol = np.random.default_rng(1).standard_normal((6, 7, 8)).astype(np.float32)
    pts = np.array([[2, 3, 4], [5, 6, 7]], dtype=float)
    a = np.asarray(sample_field(vol, pts, reduce="max", radius=1))
    b = np.asarray(neighborhood_reduce(vol, pts, reduce="max", radius=1))
    np.testing.assert_array_equal(a, b)


def test_block_plan_partitions_volume() -> None:
    shape = (10, 11, 12)
    plan = BlockPlan(shape, (4, 4, 4), halo=1)
    cover = np.zeros(shape, dtype=int)
    for blk in plan.blocks():
        cz, cy, cx = blk.core_slices()
        cover[cz, cy, cx] += 1
    # every voxel covered exactly once by a core block.
    assert cover.min() == 1 and cover.max() == 1


def test_core_offset_recovers_core() -> None:
    shape = (10, 11, 12)
    vol = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
    f = _scalar_field(vol)
    for blk, data in iter_field_blocks(f, (4, 4, 4), halo=2):
        coff = core_offset_in_read(blk, shape)
        cz, cy, cx = blk.core_slices()
        np.testing.assert_array_equal(data[coff[0], coff[1], coff[2]], vol[cz, cy, cx])


def test_iter_blocks_reassembles_volume() -> None:
    shape = (9, 10, 11)
    vol = np.random.default_rng(2).standard_normal(shape).astype(np.float16)
    f = _scalar_field(vol.astype(np.float32))
    out = np.zeros(shape, dtype=np.float32)
    for blk, data in f.iter_blocks((5, 5, 5), halo=1):
        coff = core_offset_in_read(blk, shape)
        cz, cy, cx = blk.core_slices()
        out[cz, cy, cx] = data[coff[0], coff[1], coff[2]]
    np.testing.assert_allclose(out, vol.astype(np.float32))


def test_real_convmap_csv_score_reproduced(real_convmap_path: Path, real_csv_path: Path) -> None:
    """SPEC §3: radius-1 max at round(.pos) reproduces csv col1 to < 0.02 (real data)."""
    import mrcfile

    from mito_filter.emclarity.constants import POS_COLS, SAMPLING_RATE, SCORE_COL

    m = mrcfile.mmap(str(real_convmap_path), mode="r", permissive=True)
    assert m.data.shape == (448, 942, 662)
    csv = np.loadtxt(str(real_csv_path))
    order = np.argsort(csv[:, SCORE_COL])[::-1][:15]
    x, y, z = (csv[order, POS_COLS[0]], csv[order, POS_COLS[1]], csv[order, POS_COLS[2]])
    pts_zyx = np.stack([z, y, x], axis=1) / SAMPLING_RATE  # (z, y, x) voxel frame
    got = np.asarray(sample_field(m.data, pts_zyx, reduce="max", radius=1))
    scores = csv[order, SCORE_COL]
    assert np.max(np.abs(got - scores)) < 0.02


def test_companion_argmax_snaps_to_peak_voxel_vector() -> None:
    """A rounded coord on a NEIGHBOR of the peak reads that neighbor's (flipped) vector under a
    plain center read, but snaps to the cc-argmax voxel's true vector via companion-argmax."""
    nz, ny, nx = 8, 8, 8
    cc = np.zeros((nz, ny, nx), dtype=np.float32)
    normal = np.zeros((nz, ny, nx, 3), dtype=np.float32)
    # True peak (cc max) at (4,4,4) with outward normal +z; its neighbor (4,4,5) is a low-cc
    # background voxel whose packed-argmax orientation is the OPPOSITE normal -z.
    cc[4, 4, 4] = 10.0
    cc[4, 4, 5] = 3.2
    normal[4, 4, 4] = [1.0, 0.0, 0.0]  # (z,y,x) = +z
    normal[4, 4, 5] = [-1.0, 0.0, 0.0]  # flipped background argmax
    g = VoxelGrid((nz, ny, nx), APIX)
    vf = VectorField.from_array("normal", g, normal, channels=3)
    ccf = DenseField.from_array("cc", g, cc)
    # csv coordinate rounds to the neighbor (4,4,5), NOT the true argmax (4,4,4).
    pts = np.array([[4.0, 4.0, 5.0]], dtype=float)

    center = np.asarray(vf.sample_at(pts, reduce="center", radius=0)).reshape(-1, 3)
    assert np.allclose(center[0], [-1.0, 0.0, 0.0])  # plain read = flipped background normal

    snapped = np.asarray(vf.sample_at_companion_argmax(pts, ccf, radius=1)).reshape(-1, 3)
    assert np.allclose(snapped[0], [1.0, 0.0, 0.0])  # snap to the cc peak = correct +z normal

    # radius=0 degrades to a plain center read (module-level function form).
    r0 = np.asarray(sample_at_companion_argmax(normal, cc, pts, radius=0, channels=3)).reshape(
        -1, 3
    )
    assert np.allclose(r0[0], [-1.0, 0.0, 0.0])


def test_real_dense_normal_matches_csv_via_companion_argmax(
    real_convmap_path: Path,
    real_angles_mrc_path: Path,
    real_angles_list_path: Path,
    real_csv_path: Path,
) -> None:
    """SPEC §5: on real data a rounded csv coord flips ~30% of dense normals under a plain center
    read; snapping to the cc-argmax voxel restores >95% agreement with csv cols 23-25."""
    from mito_filter.core.field import IndexField
    from mito_filter.core.grid import VoxelGrid as VG
    from mito_filter.emclarity import conventions  # noqa: F401  (installs decoders)
    from mito_filter.emclarity.angles_list import read_angles_list
    from mito_filter.emclarity.constants import APIX_A
    from mito_filter.emclarity.csv_io import read_peaks
    from mito_filter.emclarity.mrc_io import open_dense_field, open_dense_mmap

    def _unit(a: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(a, axis=1, keepdims=True)
        return np.asarray(np.divide(a, n, out=np.zeros_like(a), where=n > 0))

    pc = read_peaks(real_csv_path)
    csv_n = _unit(np.asarray(pc.get("normal"), dtype=float))
    coords = np.asarray(pc.xyz, dtype=float)
    cc = open_dense_field(real_convmap_path, "cc", channels=1)
    mm = open_dense_mmap(real_angles_mrc_path, is_index=True)
    grid = VG(shape=(mm.shape[0], mm.shape[1], mm.shape[2]), apix=APIX_A)
    idx = IndexField("angle", grid, mm, channels=1)
    normal = idx.decode_normal(read_angles_list(real_angles_list_path))

    old = _unit(np.asarray(normal.sample_at(coords, reduce="center", radius=0)).reshape(-1, 3))
    new = _unit(np.asarray(normal.sample_at_companion_argmax(coords, cc, radius=1)).reshape(-1, 3))
    dot_old = np.sum(csv_n * old, axis=1)
    dot_new = np.sum(csv_n * new, axis=1)
    # The bug: a large flipped fraction under the plain center read.
    assert np.mean(dot_old < 0.0) > 0.15
    # The fix: near-perfect agreement, almost no flips.
    assert np.median(dot_new) > 0.999
    assert np.mean(dot_new < 0.0) < 0.02
