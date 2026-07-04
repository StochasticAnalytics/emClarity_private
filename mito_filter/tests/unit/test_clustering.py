"""Clustering tests: union-find seam merge across block boundaries + DBSCAN."""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from mito_filter.core.clustering import (
    cluster_of_points,
    dense_clusters,
    point_clusters,
)


def _relabel_signature(labels: np.ndarray) -> set:
    """Return the set of frozenset voxel-groups, invariant to label numbering."""
    groups: dict[int, list[tuple[int, int, int]]] = {}
    nz, ny, nx = labels.shape
    coords = np.array(np.nonzero(labels)).T
    for z, y, x in coords:
        groups.setdefault(int(labels[z, y, x]), []).append((int(z), int(y), int(x)))
    return {frozenset(v) for v in groups.values()}


def test_straddling_cluster_seam_merge() -> None:
    """A bar crossing a block seam must be ONE cluster, matching whole-volume labeling."""
    vol = np.zeros((16, 8, 8), dtype=np.float32)
    # A z-oriented bar spanning z=5..10 crosses the z=8 block boundary.
    vol[5:11, 4, 4] = 10.0
    # A separate blob fully inside the second block.
    vol[12:14, 1:3, 1:3] = 10.0

    whole = dense_clusters(vol, thr=5.0, connectivity=1)
    blocked = dense_clusters(vol, thr=5.0, connectivity=1, block_shape=(8, 8, 8))

    assert whole.n_clusters == 2
    assert blocked.n_clusters == 2
    # The straddling bar is a single connected component in the block path.
    bar_labels = blocked.labels[5:11, 4, 4]
    assert np.all(bar_labels == bar_labels[0])
    assert bar_labels[0] != 0
    # Same partition (up to relabeling) as whole-volume ndimage.label.
    assert _relabel_signature(whole.labels) == _relabel_signature(blocked.labels)


def test_block_matches_whole_random() -> None:
    rng = np.random.default_rng(7)
    vol = rng.standard_normal((20, 18, 22)).astype(np.float32)
    for conn in (1, 2, 3):
        whole = dense_clusters(vol, thr=1.2, connectivity=conn)
        blocked = dense_clusters(vol, thr=1.2, connectivity=conn, block_shape=(7, 6, 9))
        assert whole.n_clusters == blocked.n_clusters
        assert _relabel_signature(whole.labels) == _relabel_signature(blocked.labels)


def test_min_size_filter() -> None:
    vol = np.zeros((10, 10, 10), dtype=np.float32)
    vol[1, 1, 1] = 10.0  # size-1 speck
    vol[5:8, 5:8, 5:8] = 10.0  # size-27 blob
    res = dense_clusters(vol, thr=5.0, min_size=2)
    assert res.n_clusters == 1
    assert res.sizes[1] == 27


def test_matches_ndimage_reference() -> None:
    vol = np.zeros((6, 6, 6), dtype=np.float32)
    vol[1:3, 1:3, 1:3] = 9.0
    vol[4:6, 4:6, 4:6] = 9.0
    res = dense_clusters(vol, thr=5.0)
    ref, nref = ndimage.label(vol >= 5.0)
    assert res.n_clusters == nref
    np.testing.assert_array_equal(np.sort(res.sizes[1:]), np.sort(np.bincount(ref.ravel())[1:]))


def test_centroid_and_lookup() -> None:
    vol = np.zeros((10, 10, 10), dtype=np.float32)
    vol[4:7, 4:7, 4:7] = 9.0  # centroid at (5,5,5)
    res = dense_clusters(vol, thr=5.0)
    np.testing.assert_allclose(res.centroids[1], [5.0, 5.0, 5.0])
    pts = np.array([[5.0, 5.0, 5.0], [0.0, 0.0, 0.0]])
    lab = cluster_of_points(res.labels, pts)
    assert lab[0] == 1 and lab[1] == 0


def test_point_clusters_dbscan() -> None:
    rng = np.random.default_rng(3)
    a = rng.normal(0, 0.5, size=(30, 3))
    b = rng.normal(50, 0.5, size=(30, 3))
    pts = np.vstack([a, b])
    labels = point_clusters(pts, eps_A=3.0, min_pts=4, apix=1.0)
    n_clusters = len({int(x) for x in labels if x >= 0})
    assert n_clusters == 2
    # The two groups get different labels.
    assert labels[0] != labels[-1]


def test_point_clusters_empty() -> None:
    labels = point_clusters(np.zeros((0, 3)), eps_A=3.0, min_pts=4)
    assert labels.shape == (0,)
