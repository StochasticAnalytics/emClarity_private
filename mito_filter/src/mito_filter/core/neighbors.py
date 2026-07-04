"""Spatial neighbor queries on sparse point sets, in physical Angstrom.

Domain-free. :class:`NeighborIndex` wraps a KD-tree (``scipy.spatial.cKDTree``) built in
**physical Angstrom** — voxel coordinates are scaled by ``apix`` at construction, so every
radius/knn query is expressed in Angstrom regardless of the grid's voxel size. The CPU
KD-tree path always works; a grid-hash GPU path is left as an optional future backend
(guarded so import never needs cupy/torch).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree


class NeighborIndex:
    """KD-tree neighbor index over voxel-frame points, queried in physical Angstrom.

    Args:
        points: Voxel coordinates ``(N, 3)`` in ``(z, y, x)``.
        apix: Physical voxel size in Angstrom; points are scaled by it so query radii are
            in Angstrom. Use ``1.0`` to query directly in voxels.

    Attributes:
        apix: The voxel size used to scale coordinates.
        n: Number of indexed points.
    """

    def __init__(self, points: NDArray, apix: float) -> None:
        pts = np.asarray(points, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[1] != 3:
            raise ValueError(f"points must be (N, 3), got {pts.shape}")
        self.apix = float(apix)
        self._points = pts
        self._scaled = pts * self.apix
        self._tree = cKDTree(self._scaled)

    @property
    def n(self) -> int:
        """Number of indexed points."""
        return int(self._points.shape[0])

    def radius(self, pts: NDArray, r_A: float) -> List[NDArray]:
        """Neighbors within ``r_A`` Angstrom of each query point.

        Args:
            pts: Query voxel coordinates ``(M, 3)`` in ``(z, y, x)``.
            r_A: Search radius in Angstrom.

        Returns:
            A length-``M`` list; entry ``m`` is an int array of indices into the indexed
            points lying within ``r_A`` of query ``m`` (sorted ascending).
        """
        q = np.atleast_2d(np.asarray(pts, dtype=np.float64)) * self.apix
        raw = self._tree.query_ball_point(q, r=float(r_A))
        return [np.sort(np.asarray(idx, dtype=np.int64)) for idx in raw]

    def knn(self, pts: NDArray, k: int) -> Tuple[NDArray, NDArray]:
        """The ``k`` nearest indexed neighbors of each query point.

        Args:
            pts: Query voxel coordinates ``(M, 3)`` in ``(z, y, x)``.
            k: Number of neighbors (capped at the number of indexed points).

        Returns:
            ``(dist_A, idx)`` each shaped ``(M, k)``; ``dist_A`` in Angstrom. Missing
            neighbors (``k`` > available) are ``inf`` distance / index ``-1``.
        """
        q = np.atleast_2d(np.asarray(pts, dtype=np.float64)) * self.apix
        kk = int(min(k, self.n))
        dist, idx = self._tree.query(q, k=kk)
        dist = np.atleast_2d(dist.astype(np.float64).reshape(q.shape[0], kk))
        idx = np.atleast_2d(idx.astype(np.int64).reshape(q.shape[0], kk))
        if kk < k:
            padd = np.full((q.shape[0], k - kk), np.inf)
            padi = np.full((q.shape[0], k - kk), -1, dtype=np.int64)
            dist = np.concatenate([dist, padd], axis=1)
            idx = np.concatenate([idx, padi], axis=1)
        return dist, idx

    def self_radius(self, r_A: float, *, exclude_self: bool = True) -> List[NDArray]:
        """Neighbors within ``r_A`` for every indexed point (self-query).

        Args:
            r_A: Search radius in Angstrom.
            exclude_self: Drop each point's own index from its neighbor list.

        Returns:
            A length-``n`` list of int neighbor-index arrays.
        """
        out = self.radius(self._points, r_A)
        if exclude_self:
            out = [nb[nb != i] for i, nb in enumerate(out)]
        return out

    def radius_pairs(self, r_A: float) -> NDArray:
        """Undirected pairs of indexed points within ``r_A`` Angstrom.

        Args:
            r_A: Search radius in Angstrom.

        Returns:
            Int array ``(P, 2)`` of ``(i, j)`` pairs with ``i < j``.
        """
        pairs = self._tree.query_pairs(r=float(r_A), output_type="ndarray")
        return np.asarray(pairs, dtype=np.int64).reshape(-1, 2)

    def count_within(self, pts: NDArray, r_A: float) -> NDArray:
        """Number of indexed neighbors within ``r_A`` of each query point.

        Args:
            pts: Query voxel coordinates ``(M, 3)``.
            r_A: Search radius in Angstrom.

        Returns:
            Int array ``(M,)`` of neighbor counts.
        """
        q = np.atleast_2d(np.asarray(pts, dtype=np.float64)) * self.apix
        counts = self._tree.query_ball_point(q, r=float(r_A), return_length=True)
        return np.asarray(counts, dtype=np.int64).reshape(q.shape[0])


def neighbor_index(points: NDArray, apix: float, *, backend: Optional[str] = None) -> NeighborIndex:
    """Construct a :class:`NeighborIndex` (CPU KD-tree; GPU grid-hash reserved).

    Args:
        points: Voxel coordinates ``(N, 3)``.
        apix: Physical voxel size in Angstrom.
        backend: Reserved for a future ``"grid_hash"`` GPU backend; only the default CPU
            KD-tree is implemented.

    Returns:
        A CPU :class:`NeighborIndex`.

    Raises:
        NotImplementedError: If a non-CPU ``backend`` is requested.
    """
    if backend not in (None, "cpu", "kdtree"):
        raise NotImplementedError(f"neighbor backend {backend!r} not implemented (CPU only)")
    return NeighborIndex(points, apix)
