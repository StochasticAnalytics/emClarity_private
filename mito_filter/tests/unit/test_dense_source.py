"""DenseFieldPeakSource tests: oriented-NMS de-dup of the rotated erase cylinder (§9.6)."""

from __future__ import annotations

import numpy as np
import pytest

from mito_filter.candidates.dense_source import (
    DenseFieldPeakSource,
    default_erase_radii_vox,
    oriented_nms,
)
from mito_filter.core.field import DenseField, VectorField
from mito_filter.core.grid import VoxelGrid

APIX = 12.5


def test_default_erase_radii_match_spec() -> None:
    # SPEC §6: Peak_mRadius [210,210,320] A @ 12.5 A/vox -> [16, 16, 26] vox.
    assert default_erase_radii_vox() == (16.0, 26.0)


def test_oriented_nms_collapses_cluster_to_strongest() -> None:
    # A cluster of points along a tilted axis, all inside one erase cylinder, must reduce to
    # the single strongest peak.
    axis = np.array([1.0, 2.0, 2.0])  # (z, y, x); |axis| = 3
    axis = axis / np.linalg.norm(axis)
    ts = np.array([-20.0, -10.0, 0.0, 8.0, 18.0])  # axial offsets < r_axial (26)
    center = np.array([40.0, 40.0, 40.0])
    coords = center + ts[:, None] * axis[None, :]
    # strongest at t = 0 (the 3rd point); others weaker.
    scores = np.array([1.0, 2.0, 9.0, 3.0, 1.5])
    normals = np.tile(axis, (5, 1))

    keep = oriented_nms(coords, scores, normals_zyx=normals, r_radial_vox=16.0, r_axial_vox=26.0)
    assert keep.sum() == 1
    assert keep[2]  # the strongest survives


def test_oriented_nms_keeps_well_separated_peaks() -> None:
    coords = np.array([[10.0, 10.0, 10.0], [10.0, 10.0, 60.0]])  # 50 vox apart in x
    scores = np.array([5.0, 4.0])
    normals = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]])  # axis along z
    keep = oriented_nms(coords, scores, normals_zyx=normals, r_radial_vox=16.0, r_axial_vox=26.0)
    assert keep.all()


def test_oriented_nms_is_orientation_dependent() -> None:
    # Two peaks 20 vox apart along z. Axis along z -> the gap is axial (<=26) -> suppressed.
    # Axis along x -> the gap is radial (>16) -> both kept.
    coords = np.array([[40.0, 40.0, 40.0], [60.0, 40.0, 40.0]])
    scores = np.array([9.0, 5.0])

    axis_z = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    keep_axial = oriented_nms(
        coords, scores, normals_zyx=axis_z, r_radial_vox=16.0, r_axial_vox=26.0
    )
    assert keep_axial.sum() == 1 and keep_axial[0]

    axis_x = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]])
    keep_radial = oriented_nms(
        coords, scores, normals_zyx=axis_x, r_radial_vox=16.0, r_axial_vox=26.0
    )
    assert keep_radial.all()


def test_oriented_nms_isotropic_fallback_without_normals() -> None:
    # No normals -> axis-aligned ellipsoid (z long). A near point is inside; a far one is not.
    coords = np.array(
        [[40.0, 40.0, 40.0], [40.0, 40.0, 50.0], [40.0, 40.0, 80.0]]
    )  # +10 and +40 in x
    scores = np.array([9.0, 5.0, 4.0])
    keep = oriented_nms(coords, scores, r_radial_vox=16.0, r_axial_vox=26.0)
    assert keep.tolist() == [True, False, True]


def test_oriented_nms_suppresses_rim_neighbor_beyond_max_radius() -> None:
    # Regression (finding 4): a weaker peak genuinely INSIDE the tilted cylinder but farther
    # from the center than max(r_radial, r_axial) must still be suppressed. With axis along z,
    # r_axial=26, r_radial=16, a point at axial=+25, radial=+15 is inside (25<=26, 15<=16) yet
    # its center distance sqrt(25^2+15^2)=29.2 > max(16,26)=26, so a max()-reach neighbor query
    # would miss it and (wrongly) keep it. hypot reach = sqrt(16^2+26^2)=30.5 catches it.
    center = np.array([40.0, 40.0, 40.0])
    rim = center + np.array([25.0, 15.0, 0.0])  # +25 axial (z), +15 radial (y)
    dist = float(np.linalg.norm(rim - center))
    assert dist > 26.0  # beyond the old max() reach
    coords = np.array([center, rim])
    scores = np.array([9.0, 5.0])  # center stronger
    normals = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]])  # axis along z
    keep = oriented_nms(coords, scores, normals_zyx=normals, r_radial_vox=16.0, r_axial_vox=26.0)
    assert keep.tolist() == [True, False]


def test_oriented_nms_empty() -> None:
    keep = oriented_nms(np.zeros((0, 3)), np.zeros(0), r_radial_vox=16.0, r_axial_vox=26.0)
    assert keep.shape == (0,)


def _spike_field(shape: tuple[int, int, int] = (30, 40, 60)) -> tuple[DenseField, VoxelGrid]:
    grid = VoxelGrid(shape, APIX)
    vol = np.full(shape, 3.0, dtype=np.float32)
    vol[10, 10, 10] = 12.0  # peak A (strongest)
    vol[10, 10, 20] = 11.0  # near-duplicate of A: +10 vox in x -> inside erase cylinder
    vol[25, 30, 50] = 10.0  # peak C, far from A
    return DenseField.from_array("cc", grid, vol), grid


def test_detect_dedups_near_duplicate() -> None:
    field, _ = _spike_field()
    src = DenseFieldPeakSource(threshold=5.0, block_shape=(64, 64, 64))
    cand = src.detect(field)
    # Three seeds (A, near-dup, C); oriented NMS removes the near-dup of A -> 2 survivors.
    assert cand.n == 2
    kept = {tuple(np.rint(p).astype(int)) for p in cand.coords_zyx}
    assert (10, 10, 10) in kept
    assert (25, 30, 50) in kept
    assert (10, 10, 20) not in kept
    np.testing.assert_allclose(sorted(cand.get("cc")), [10.0, 12.0])


def test_detect_streams_across_block_seams() -> None:
    # A tiny block_shape forces the peaks onto/near block seams; each must be emitted once.
    field, _ = _spike_field()
    src = DenseFieldPeakSource(threshold=5.0, block_shape=(8, 8, 8))
    cand = src.detect(field)
    assert cand.n == 2  # no seam double-counting


def test_detect_uses_normal_field_orientation() -> None:
    # Two spikes 20 vox apart along z; a normal field pointing along z makes the gap axial
    # (<=26) so the weaker one is suppressed.
    shape = (60, 40, 40)
    grid = VoxelGrid(shape, APIX)
    vol = np.full(shape, 3.0, dtype=np.float32)
    vol[20, 20, 20] = 12.0
    vol[40, 20, 20] = 11.0
    field = DenseField.from_array("cc", grid, vol)

    nrm = np.zeros(shape + (3,), dtype=np.float32)
    nrm[..., 0] = 1.0  # every voxel normal = +z (zyx)
    normal_field = VectorField("normal", grid, nrm, channels=3)

    src = DenseFieldPeakSource(threshold=5.0, block_shape=(64, 64, 64))
    cand = src.detect(field, normal_field=normal_field)
    assert cand.n == 1
    assert "normal" in cand.attrs
    assert cand.get("normal").shape == (1, 3)


def test_candidates_requires_registry() -> None:
    src = DenseFieldPeakSource(threshold=5.0)
    with pytest.raises(ValueError):
        src.candidates(object(), VoxelGrid((4, 4, 4), APIX))  # type: ignore[arg-type]
