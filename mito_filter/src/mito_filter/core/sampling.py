"""Gather dense-field values at sparse points: neighborhood reduce + trilinear.

Domain-free. Two sampling modes over a memmap/ndarray-backed volume, both **memory-safe**
(they index only the voxels a point touches; the full volume is never materialized):

* :func:`neighborhood_reduce` — read the ``(2*radius+1)^3`` integer neighborhood around each
  rounded point and reduce (``"center"`` / ``"max"`` / ``"mean"``). ``reduce="max", radius=1``
  reproduces the emClarity csv score (SPEC §3): the peak's sub-voxel CoM offset means the
  exact-argmax voxel reads low, so the score is recovered from the 3x3x3 max.
* :func:`trilinear_sample` — continuous 8-corner interpolation (map_coordinates order=1,
  boundary mode "nearest"), for smoothly-varying fields (SDF, normals).

Both accept scalar volumes ``(nz, ny, nx)`` and vector volumes ``(nz, ny, nx, C)``. The CPU
path is pure numpy; a GPU ``xp`` only converts the (host-gathered) result, so importing this
module never needs torch/cupy.
"""

from __future__ import annotations

from typing import Tuple, cast

import numpy as np
from numpy.typing import NDArray

from .field import ArrayT

_REDUCERS = ("center", "max", "mean")


def _to_xp(arr: NDArray, xp: object) -> ArrayT:
    """Return ``arr`` on backend ``xp`` (identity for numpy)."""
    if xp is np:
        return arr
    return cast(ArrayT, xp.asarray(arr))  # type: ignore[attr-defined]


def _rounded_int_coords(pts: NDArray, shape: Tuple[int, int, int]) -> NDArray:
    """Round ``(N, 3)`` voxel coords to nearest int and clip to ``[0, dim)`` per axis."""
    idx = np.rint(np.asarray(pts, dtype=np.float64)).astype(np.int64)
    hi = np.asarray(shape, dtype=np.int64) - 1
    return np.clip(idx, 0, hi)


def _neighbor_offsets(radius: int) -> NDArray:
    """Return the ``(K, 3)`` integer offsets of a ``(2*radius+1)^3`` cube (K = cube size)."""
    r = int(radius)
    rng = np.arange(-r, r + 1, dtype=np.int64)
    oz, oy, ox = np.meshgrid(rng, rng, rng, indexing="ij")
    return np.stack([oz.ravel(), oy.ravel(), ox.ravel()], axis=1)


def neighborhood_reduce(
    source: NDArray,
    pts: NDArray,
    *,
    reduce: str = "max",
    radius: int = 1,
    channels: int = 1,
    xp: object = np,
) -> ArrayT:
    """Reduce the integer neighborhood around each point (SPEC §3 csv-score recovery).

    Args:
        source: Backing volume ``(nz, ny, nx)`` (scalar) or ``(nz, ny, nx, C)`` (vector).
        pts: Voxel coordinates ``(N, 3)`` in ``(z, y, x)``.
        reduce: ``"center"`` (nearest voxel), ``"max"``, or ``"mean"`` over the neighborhood.
        radius: Neighborhood radius in voxels (ignored for ``"center"``).
        channels: 1 for a scalar field, 3 for a vector field.
        xp: Array module for the result.

    Returns:
        ``(N,)`` for a scalar field or ``(N, channels)`` for a vector field, fp32 on ``xp``.

    Raises:
        ValueError: If ``reduce`` is not one of ``center``/``max``/``mean``.
    """
    if reduce not in _REDUCERS:
        raise ValueError(f"reduce must be one of {_REDUCERS}, got {reduce!r}")
    shape = cast(Tuple[int, int, int], tuple(source.shape[:3]))
    base = _rounded_int_coords(pts, shape)  # (N, 3)

    if reduce == "center" or radius <= 0:
        gz, gy, gx = base[:, 0], base[:, 1], base[:, 2]
        vals = np.asarray(source[gz, gy, gx], dtype=np.float32)
        if channels == 1 and vals.ndim > 1:
            vals = vals[..., 0]
        return _to_xp(vals, xp)

    offs = _neighbor_offsets(radius)  # (K, 3)
    hi = np.asarray(shape, dtype=np.int64) - 1
    nbr = base[:, None, :] + offs[None, :, :]  # (N, K, 3)
    np.clip(nbr, 0, hi, out=nbr)
    gz, gy, gx = nbr[..., 0], nbr[..., 1], nbr[..., 2]
    gathered = np.asarray(source[gz, gy, gx], dtype=np.float32)  # (N,K) or (N,K,C)
    if channels == 1 and gathered.ndim == 3:
        gathered = gathered[..., 0]
    axis = 1  # neighborhood axis
    if reduce == "max":
        out = gathered.max(axis=axis)
    else:  # mean
        out = gathered.mean(axis=axis)
    return _to_xp(np.asarray(out, dtype=np.float32), xp)


def sample_at_companion_argmax(
    vector_source: NDArray,
    companion_source: NDArray,
    pts: NDArray,
    *,
    radius: int = 1,
    channels: int = 3,
    xp: object = np,
) -> ArrayT:
    """Sample ``vector_source`` at the voxel where ``companion_source`` peaks near each point.

    The emClarity peak csv stores a peak at its integer argmax voxel, but the recorded position
    (full-tomo px / ``SAMPLING_RATE``, then rounded) lands on a *neighbor* of that argmax as often
    as on it (the sub-voxel CoM offset, SPEC §3 — the same reason the csv score is recovered with
    ``reduce="max", radius=1``). A packed-index (argmax-orientation) field is discontinuous across
    that one-voxel slip: the neighbor's argmax orientation is frequently the OPPOSITE normal. So a
    plain ``reduce="center"`` read of a dense normal field at a rounded csv coord returns a flipped
    normal for a large fraction of real peaks (~30% on H99_2_100). This snaps to the ``companion``
    (``cc``) argmax voxel in the ``(2*radius+1)^3`` neighborhood FIRST, then reads the vector there
    — recovering the true per-peak normal (>99% agreement with the csv cols 23-25 normal).

    Args:
        vector_source: The vector volume ``(nz, ny, nx, C)`` to sample (e.g. the normal field).
        companion_source: The scalar volume ``(nz, ny, nx)`` whose argmax locates the peak voxel
            (e.g. the ``cc`` convmap).
        pts: Voxel coordinates ``(N, 3)`` in ``(z, y, x)``.
        radius: Neighborhood radius in voxels (``0`` degrades to a plain center read).
        channels: Vector channel count (3 for a normal).
        xp: Array module for the result.

    Returns:
        ``(N, channels)`` fp32 vectors on ``xp``, read at the companion-argmax voxel per point.
    """
    shape = cast(Tuple[int, int, int], tuple(vector_source.shape[:3]))
    base = _rounded_int_coords(pts, shape)  # (N, 3)
    if radius <= 0:
        gz, gy, gx = base[:, 0], base[:, 1], base[:, 2]
        vals = np.asarray(vector_source[gz, gy, gx], dtype=np.float32)
        return _to_xp(vals.reshape(base.shape[0], channels), xp)

    offs = _neighbor_offsets(radius)  # (K, 3)
    hi = np.asarray(shape, dtype=np.int64) - 1
    nbr = base[:, None, :] + offs[None, :, :]  # (N, K, 3)
    np.clip(nbr, 0, hi, out=nbr)
    gz, gy, gx = nbr[..., 0], nbr[..., 1], nbr[..., 2]  # (N, K)
    comp = np.asarray(companion_source[gz, gy, gx], dtype=np.float32)  # (N, K) or (N, K, 1)
    if comp.ndim == 3:
        comp = comp[..., 0]
    amax = np.argmax(comp, axis=1)  # (N,)
    rows = np.arange(nbr.shape[0])
    sz, sy, sx = gz[rows, amax], gy[rows, amax], gx[rows, amax]
    vals = np.asarray(vector_source[sz, sy, sx], dtype=np.float32)  # (N, C)
    return _to_xp(vals.reshape(rows.shape[0], channels), xp)


def trilinear_sample(
    source: NDArray,
    pts: NDArray,
    *,
    channels: int = 1,
    xp: object = np,
) -> ArrayT:
    """Trilinearly interpolate a volume at fractional voxel points (boundary = nearest).

    Args:
        source: Backing volume ``(nz, ny, nx)`` (scalar) or ``(nz, ny, nx, C)`` (vector).
        pts: Fractional voxel coordinates ``(N, 3)`` in ``(z, y, x)``.
        channels: 1 for a scalar field, 3 for a vector field.
        xp: Array module for the result.

    Returns:
        ``(N,)`` (scalar) or ``(N, channels)`` (vector), fp32 on ``xp``.
    """
    shape = cast(Tuple[int, int, int], tuple(source.shape[:3]))
    hi = np.asarray(shape, dtype=np.int64) - 1
    p = np.asarray(pts, dtype=np.float64)
    p = np.clip(p, 0.0, hi.astype(np.float64))
    lo = np.floor(p).astype(np.int64)
    frac = p - lo  # (N, 3) in [0, 1]

    is_vec = channels != 1 and np.asarray(source).ndim == 4
    n = p.shape[0]
    acc = np.zeros((n, channels) if is_vec else (n,), dtype=np.float64)
    for cz in (0, 1):
        for cy in (0, 1):
            for cx in (0, 1):
                gz = np.clip(lo[:, 0] + cz, 0, hi[0])
                gy = np.clip(lo[:, 1] + cy, 0, hi[1])
                gx = np.clip(lo[:, 2] + cx, 0, hi[2])
                wz = frac[:, 0] if cz else 1.0 - frac[:, 0]
                wy = frac[:, 1] if cy else 1.0 - frac[:, 1]
                wx = frac[:, 2] if cx else 1.0 - frac[:, 2]
                w = wz * wy * wx
                vals = np.asarray(source[gz, gy, gx], dtype=np.float64)
                if is_vec:
                    acc += w[:, None] * vals
                else:
                    if vals.ndim > 1:
                        vals = vals[..., 0]
                    acc += w * vals
    return _to_xp(np.asarray(acc, dtype=np.float32), xp)


def sample_field(
    source: NDArray,
    pts: NDArray,
    *,
    xp: object = np,
    reduce: str = "max",
    radius: int = 1,
    channels: int = 1,
) -> ArrayT:
    """Backing implementation of ``DenseField.sample_at`` (neighborhood reduce).

    Args:
        source: The field's backing volume.
        pts: Voxel coordinates ``(N, 3)`` in ``(z, y, x)``.
        xp: Array module for the result.
        reduce: ``"center"`` / ``"max"`` / ``"mean"``.
        radius: Neighborhood radius in voxels.
        channels: 1 scalar / 3 vector.

    Returns:
        ``(N,)`` or ``(N, channels)`` fp32 on ``xp``.
    """
    return neighborhood_reduce(source, pts, reduce=reduce, radius=radius, channels=channels, xp=xp)
