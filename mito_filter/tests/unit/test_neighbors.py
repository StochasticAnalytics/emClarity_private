"""NeighborIndex tests: physical-Angstrom radius/knn queries."""

from __future__ import annotations

import numpy as np

from mito_filter.core.neighbors import NeighborIndex, neighbor_index

APIX = 12.5


def _line_points(n: int = 5) -> np.ndarray:
    # points along z at unit voxel spacing; physical spacing = APIX Angstrom.
    return np.stack([np.arange(n), np.zeros(n), np.zeros(n)], axis=1).astype(float)


def test_radius_is_physical_angstrom() -> None:
    pts = _line_points(5)
    idx = NeighborIndex(pts, APIX)
    # radius just above one voxel step -> self + 2 immediate neighbors for interior point.
    nb = idx.radius(pts[2:3], r_A=APIX * 1.1)
    assert set(nb[0].tolist()) == {1, 2, 3}
    # radius below one step -> only self.
    nb0 = idx.radius(pts[2:3], r_A=APIX * 0.5)
    assert nb0[0].tolist() == [2]


def test_knn_distances_in_angstrom() -> None:
    pts = _line_points(6)
    idx = NeighborIndex(pts, APIX)
    dist, nn = idx.knn(pts[0:1], k=3)
    assert dist.shape == (1, 3) and nn.shape == (1, 3)
    np.testing.assert_allclose(dist[0], [0.0, APIX, 2 * APIX], atol=1e-6)
    assert nn[0].tolist() == [0, 1, 2]


def test_knn_pads_when_k_exceeds_n() -> None:
    pts = _line_points(2)
    idx = NeighborIndex(pts, APIX)
    dist, nn = idx.knn(pts[0:1], k=5)
    assert dist.shape == (1, 5)
    assert np.isinf(dist[0, 2:]).all()
    assert (nn[0, 2:] == -1).all()


def test_self_radius_excludes_self() -> None:
    pts = _line_points(5)
    idx = NeighborIndex(pts, APIX)
    nb = idx.self_radius(APIX * 1.1)
    assert 2 not in nb[2].tolist()
    assert set(nb[2].tolist()) == {1, 3}


def test_radius_pairs_and_counts() -> None:
    pts = _line_points(4)
    idx = NeighborIndex(pts, APIX)
    pairs = idx.radius_pairs(APIX * 1.1)
    # consecutive pairs only: (0,1),(1,2),(2,3)
    got = {tuple(sorted(p)) for p in pairs.tolist()}
    assert got == {(0, 1), (1, 2), (2, 3)}
    counts = idx.count_within(pts, APIX * 1.1)
    assert counts.tolist() == [2, 3, 3, 2]


def test_neighbor_index_factory_rejects_gpu() -> None:
    pts = _line_points(3)
    assert isinstance(neighbor_index(pts, APIX), NeighborIndex)
    try:
        neighbor_index(pts, APIX, backend="grid_hash")
    except NotImplementedError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected NotImplementedError for GPU backend")
