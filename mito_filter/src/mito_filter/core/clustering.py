"""Clustering of dense volumes (connected components) and sparse points (DBSCAN).

Domain-free.

* :func:`dense_clusters` — thresholded connected-components of a dense volume. It can run
  whole-volume (``scipy.ndimage.label``) or **block-streamed** with a halo, merging labels
  that straddle a block seam via **union-find**. The block path never materializes the fp32
  volume: it reads one halo-padded block at a time and commits int32 labels incrementally,
  unioning a block's local labels with any already-committed neighbor labels found in its
  halo. Block and whole-volume results are identical up to relabeling.
* :func:`point_clusters` — DBSCAN over a sparse point set, ``eps`` in physical Angstrom.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage

from .chunking import BlockPlan, core_offset_in_read
from .field import DenseField

SourceT = Union[DenseField, NDArray]


class _UnionFind:
    """Integer union-find with path compression + union by rank (for label merging)."""

    def __init__(self) -> None:
        self._parent: Dict[int, int] = {}
        self._rank: Dict[int, int] = {}

    def add(self, x: int) -> None:
        """Add ``x`` as its own singleton set if unseen."""
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0

    def find(self, x: int) -> int:
        """Return the canonical root of ``x`` (with path compression)."""
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        """Merge the sets containing ``a`` and ``b``."""
        self.add(a)
        self.add(b)
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1


@dataclass
class ClusterResult:
    """Result of a dense connected-components pass.

    Args:
        labels: Int32 label volume ``(nz, ny, nx)``; 0 is background, clusters are
            ``1..n_clusters`` (compact, size-filtered).
        sizes: Voxel count per cluster, shape ``(n_clusters + 1,)`` with ``sizes[0] == 0``.
        centroids: Voxel-frame centroid ``(z, y, x)`` per cluster, shape
            ``(n_clusters + 1, 3)`` (row 0 is nan).
        n_clusters: Number of retained clusters.

    Attributes:
        labels: The label volume.
        sizes: Per-label voxel counts.
        centroids: Per-label centroids.
        n_clusters: Retained cluster count.
    """

    labels: NDArray
    sizes: NDArray
    centroids: NDArray
    n_clusters: int


def _as_ndarray(source: SourceT) -> NDArray:
    """Return the backing array of a :class:`DenseField` or pass an ndarray through."""
    if isinstance(source, DenseField):
        return source.as_memmap() if _is_memmap(source) else np.asarray(source._source)
    return np.asarray(source)


def _is_memmap(field: DenseField) -> bool:
    """True if the field wraps an ``np.memmap`` (avoids copying it)."""
    return isinstance(field._source, np.memmap)


def _structure(connectivity: int) -> NDArray:
    """3D binary structuring element for a 1/2/3 connectivity."""
    return np.asarray(ndimage.generate_binary_structure(3, int(connectivity)))


def _finalize(labels: NDArray, min_size: int, shape: Tuple[int, int, int]) -> ClusterResult:
    """Compact labels, drop clusters below ``min_size``, compute sizes + centroids."""
    max_lab = int(labels.max())
    if max_lab == 0:
        return ClusterResult(
            labels,
            np.zeros(1, np.int64),
            np.full((1, 3), np.nan),
            0,
        )
    counts = np.bincount(labels.ravel(), minlength=max_lab + 1)
    keep = counts >= _min_size_floor(min_size)
    keep[0] = False
    old_ids = np.nonzero(keep)[0]
    remap = np.zeros(max_lab + 1, dtype=np.int32)
    remap[old_ids] = np.arange(1, len(old_ids) + 1, dtype=np.int32)
    new_labels = remap[labels]

    n = len(old_ids)
    sizes = np.zeros(n + 1, dtype=np.int64)
    centroids = np.full((n + 1, 3), np.nan, dtype=np.float64)
    if n:
        coords = np.array(np.nonzero(new_labels)).T  # (P, 3) z,y,x
        lab_at = new_labels[coords[:, 0], coords[:, 1], coords[:, 2]]
        sizes[1:] = np.bincount(lab_at, minlength=n + 1)[1:]
        for axis in range(3):
            sums = np.bincount(lab_at, weights=coords[:, axis], minlength=n + 1)
            centroids[1:, axis] = sums[1:] / np.maximum(sizes[1:], 1)
    return ClusterResult(new_labels.astype(np.int32), sizes, centroids, n)


def _min_size_floor(min_size: int) -> int:
    """Return the effective minimum cluster size (at least 1)."""
    return max(1, int(min_size))


def dense_clusters(
    source: SourceT,
    thr: float,
    *,
    min_size: int = 1,
    connectivity: int = 1,
    block_shape: Optional[Tuple[int, int, int]] = None,
) -> ClusterResult:
    """Connected components of ``source >= thr`` (whole-volume or block-streamed).

    Args:
        source: A scalar :class:`DenseField` or ndarray ``(nz, ny, nx)``.
        thr: Inclusive threshold; voxels ``>= thr`` are foreground.
        min_size: Drop clusters with fewer than this many voxels.
        connectivity: 1 (6-face), 2 (18-edge), or 3 (26-corner) neighborhood.
        block_shape: If given, stream the volume in halo-padded blocks of this core size
            (union-find seam merge). If ``None``, run whole-volume ``ndimage.label``.

    Returns:
        A :class:`ClusterResult` with a compact, size-filtered int32 label volume.
    """
    arr = _as_ndarray(source)
    shape = (int(arr.shape[0]), int(arr.shape[1]), int(arr.shape[2]))
    struct = _structure(connectivity)

    if block_shape is None:
        mask = np.asarray(arr, dtype=np.float32) >= thr
        labels, _ = ndimage.label(mask, structure=struct)
        return _finalize(labels.astype(np.int32), min_size, shape)

    labels = np.zeros(shape, dtype=np.int32)
    uf = _UnionFind()
    next_id = 1
    plan = BlockPlan(shape, block_shape, halo=1)
    for blk in plan.blocks():
        read = blk.read_slices(shape)
        data = np.asarray(arr[read[0], read[1], read[2]], dtype=np.float32)
        mask = data >= thr
        if not mask.any():
            continue
        loc, nloc = ndimage.label(mask, structure=struct)
        # Assign a fresh global id to each local label.
        gid = np.zeros(nloc + 1, dtype=np.int64)
        for lab in range(1, nloc + 1):
            gid[lab] = next_id
            uf.add(next_id)
            next_id += 1
        gread = gid[loc]  # global labels over the read window (0 = bg)

        # Union with any neighbor labels already committed in this read window
        # (halo voxels overlapping already-processed blocks).
        committed = labels[read[0], read[1], read[2]]
        overlap = (committed > 0) & (gread > 0)
        if overlap.any():
            a = committed[overlap].astype(np.int64)
            b = gread[overlap].astype(np.int64)
            for ia, ib in zip(a.tolist(), b.tolist()):
                uf.union(ia, ib)

        # Commit this block's CORE labels into the global volume.
        coff = core_offset_in_read(blk, shape)
        core_glob = gread[coff[0], coff[1], coff[2]]
        core = blk.core_slices()
        labels[core[0], core[1], core[2]] = core_glob

    # Resolve union-find: relabel every committed id to its canonical root.
    if next_id > 1:
        lut = np.arange(next_id, dtype=np.int64)
        for gid_i in range(1, next_id):
            lut[gid_i] = uf.find(gid_i)
        labels = lut[labels].astype(np.int32)
    return _finalize(labels, min_size, shape)


def point_clusters(
    points: NDArray,
    eps_A: float,
    min_pts: int,
    *,
    apix: float = 1.0,
) -> NDArray:
    """DBSCAN cluster labels for a sparse point set (``eps`` in Angstrom).

    Args:
        points: Voxel coordinates ``(N, 3)`` in ``(z, y, x)``.
        eps_A: Neighborhood radius in Angstrom.
        min_pts: DBSCAN ``min_samples`` (core-point threshold).
        apix: Physical voxel size; points are scaled by it so ``eps_A`` is in Angstrom.

    Returns:
        Int array ``(N,)`` of cluster labels; ``-1`` marks noise (DBSCAN convention).
    """
    from sklearn.cluster import DBSCAN

    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] == 0:
        return np.zeros(0, dtype=np.int64)
    scaled = pts * float(apix)
    db = DBSCAN(eps=float(eps_A), min_samples=int(min_pts))
    labels: NDArray = db.fit_predict(scaled)
    return labels.astype(np.int64)


def cluster_of_points(labels: NDArray, points: NDArray) -> NDArray:
    """Look up the dense cluster label at each sparse point (0 = background).

    Args:
        labels: Int label volume ``(nz, ny, nx)`` from :func:`dense_clusters`.
        points: Voxel coordinates ``(N, 3)`` in ``(z, y, x)``.

    Returns:
        Int array ``(N,)`` of the label under each rounded point.
    """
    shape = labels.shape
    idx = np.rint(np.asarray(points, dtype=np.float64)).astype(np.int64)
    hi = np.asarray(shape, dtype=np.int64) - 1
    idx = np.clip(idx, 0, hi)
    return np.asarray(labels[idx[:, 0], idx[:, 1], idx[:, 2]], dtype=np.int64)
