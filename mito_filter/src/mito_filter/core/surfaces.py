"""Local surface analysis from oriented points: coherence, curvature, quadric fit.

Domain-free. These operators drive the membrane-surface discriminators (true targets sit in
a smooth, low-curvature, normal-coherent membrane). They accept normals from **either** a
sparse :class:`~mito_filter.core.points.PointCloud` attribute **or** a dense
:class:`~mito_filter.core.field.VectorField` (sampled at the given points) through one API —
:func:`resolve_normals` / :func:`resolve_positions` normalize both feeds to plain ``(N, 3)``
arrays, so every function below is pure geometry.

Neighbor lists are the per-point index arrays produced by
:meth:`~mito_filter.core.neighbors.NeighborIndex.radius` / ``self_radius``.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
from numpy.typing import NDArray

from .field import VectorField
from .points import PointCloud

NormalSource = Union[NDArray, PointCloud, VectorField]
Neighbors = Sequence[NDArray]


def _normalize(vecs: NDArray, *, eps: float = 1e-12) -> NDArray:
    """Return unit vectors along the last axis (zero-length rows pass through as zeros)."""
    v = np.asarray(vecs, dtype=np.float64)
    norm = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.asarray(v / np.maximum(norm, eps), dtype=np.float64)


def resolve_positions(source: NormalSource, points: Optional[NDArray] = None) -> NDArray:
    """Extract ``(N, 3)`` voxel positions from any normals feed.

    Args:
        source: An ``(N, 3)`` array, a :class:`PointCloud`, or a :class:`VectorField`.
        points: Explicit positions; required for a plain array or a dense field.

    Returns:
        Positions ``(N, 3)`` in ``(z, y, x)``.

    Raises:
        ValueError: If positions cannot be determined.
    """
    if isinstance(source, PointCloud):
        return np.asarray(source.xyz, dtype=np.float64)
    if points is not None:
        return np.asarray(points, dtype=np.float64)
    raise ValueError("positions required: pass `points` for an array/VectorField source")


def resolve_normals(
    source: NormalSource,
    points: Optional[NDArray] = None,
    *,
    attr: str = "normal",
    radius: int = 0,
) -> NDArray:
    """Extract per-point normals ``(N, 3)`` from any feed (sparse attr or dense field).

    Args:
        source: An ``(N, 3)`` array of normals, a :class:`PointCloud` (uses ``attr``), or a
            :class:`VectorField` (sampled at ``points``).
        points: Sampling positions ``(N, 3)``; required when ``source`` is a
            :class:`VectorField`.
        attr: PointCloud attribute name holding the normals.
        radius: Neighborhood radius for the dense-field sample (0 = nearest voxel).

    Returns:
        Normals ``(N, 3)`` (not renormalized — the raw sign is preserved; SPEC §4).

    Raises:
        ValueError: If a dense field is given without ``points``.
    """
    if isinstance(source, VectorField):
        if points is None:
            raise ValueError("a VectorField normals source requires `points`")
        sampled = source.sample_at(
            np.asarray(points), reduce="center" if radius == 0 else "mean", radius=radius
        )
        return np.asarray(sampled, dtype=np.float64).reshape(-1, 3)
    if isinstance(source, PointCloud):
        return np.asarray(source.get(attr), dtype=np.float64).reshape(-1, 3)
    return np.asarray(source, dtype=np.float64).reshape(-1, 3)


def normal_coherence(
    normals: NormalSource,
    neighbors: Neighbors,
    *,
    points: Optional[NDArray] = None,
    attr: str = "normal",
) -> NDArray:
    """Per-point normal coherence = mean-resultant length over the local neighborhood.

    For point ``i`` with neighbors ``J``, coherence is
    ``|| mean(n_i, {n_j : j in J}) ||`` of unit normals — 1.0 when all aligned, →0 when
    randomly oriented (the background argmax-of-noise regime, SPEC §9.3). Isolated points
    score 1.0 (trivially coherent with themselves).

    Args:
        normals: Any normals feed (array / PointCloud / VectorField).
        neighbors: Per-point neighbor-index lists (length ``N``).
        points: Positions for a dense/array feed.
        attr: PointCloud normal attribute name.

    Returns:
        Coherence ``(N,)`` in ``[0, 1]``.
    """
    n = _normalize(resolve_normals(normals, points, attr=attr))
    out = np.empty(n.shape[0], dtype=np.float64)
    for i, nb in enumerate(neighbors):
        idx = np.asarray(nb, dtype=np.int64)
        if idx.size == 0:
            out[i] = 1.0
            continue
        stack = np.vstack([n[i][None, :], n[idx]])
        out[i] = float(np.linalg.norm(stack.mean(axis=0)))
    return out


def local_curvature(
    normals: NormalSource,
    pos: NDArray,
    neighbors: Neighbors,
    *,
    apix: float = 1.0,
    attr: str = "normal",
    points: Optional[NDArray] = None,
) -> NDArray:
    """Per-point curvature proxy = mean normal deflection per unit distance (1/Angstrom).

    For point ``i`` and neighbor ``j``: ``||n_i - n_j|| / d_ij`` (Angstrom), averaged over
    ``J``. A flat sheet →0; a tightly curved shell →large. Independent of normal sign
    magnitude because unit normals are used.

    Args:
        normals: Any normals feed.
        pos: Voxel positions ``(N, 3)`` (also used to resolve a PointCloud's own positions).
        neighbors: Per-point neighbor-index lists.
        apix: Voxel size in Angstrom (distances are physical).
        attr: PointCloud normal attribute name.
        points: Positions for a dense/array normals feed (defaults to ``pos``).

    Returns:
        Curvature ``(N,)`` in 1/Angstrom (0.0 where a point has no neighbors).
    """
    p = np.asarray(pos, dtype=np.float64)
    n = _normalize(resolve_normals(normals, points if points is not None else p, attr=attr))
    out = np.zeros(p.shape[0], dtype=np.float64)
    for i, nb in enumerate(neighbors):
        idx = np.asarray(nb, dtype=np.int64)
        idx = idx[idx != i]
        if idx.size == 0:
            continue
        d = np.linalg.norm((p[idx] - p[i]) * float(apix), axis=1)
        d = np.maximum(d, 1e-9)
        dn = np.linalg.norm(n[idx] - n[i], axis=1)
        out[i] = float(np.mean(dn / d))
    return out


def fit_surface(pos: NDArray, normals: NDArray) -> Tuple[float, float, float]:
    """Fit a quadric (Monge) patch to a neighborhood; return residual + principal curvatures.

    A local frame is built from the mean normal; points are expressed as height ``w`` over
    tangent coordinates ``(u, v)`` and a quadric ``w = a u^2 + b uv + c v^2 + d u + e v + f``
    is least-squares fit. Principal curvatures come from the first/second fundamental forms.
    Fewer than 6 points (or a rank-deficient fit) falls back to a plane (curvatures 0).

    Args:
        pos: Neighborhood voxel positions ``(M, 3)``.
        normals: Neighborhood normals ``(M, 3)`` (used only to orient the local frame).

    Returns:
        ``(residual, k1, k2)`` — RMS height residual (voxels) and principal curvatures
        (1/voxel), with ``k1 >= k2``.
    """
    p = np.asarray(pos, dtype=np.float64)
    m = p.shape[0]
    if m < 3:
        return (0.0, 0.0, 0.0)
    c = p.mean(axis=0)
    centered = p - c

    nrm = _normalize(np.asarray(normals, dtype=np.float64))
    nbar = nrm.mean(axis=0)
    if np.linalg.norm(nbar) < 1e-8:
        # Degenerate normals: use the smallest-variance direction of the points.
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        nbar = vh[-1]
    nbar = nbar / np.maximum(np.linalg.norm(nbar), 1e-12)

    helper = np.array([1.0, 0.0, 0.0]) if abs(nbar[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    t1 = np.cross(nbar, helper)
    t1 /= np.maximum(np.linalg.norm(t1), 1e-12)
    t2 = np.cross(nbar, t1)

    u = centered @ t1
    v = centered @ t2
    w = centered @ nbar

    if m >= 6:
        design = np.stack([u * u, u * v, v * v, u, v, np.ones_like(u)], axis=1)
    else:
        design = np.stack([u, v, np.ones_like(u)], axis=1)
    coeffs, _, rank, _ = np.linalg.lstsq(design, w, rcond=None)
    fit = design @ coeffs
    residual = float(np.sqrt(np.mean((w - fit) ** 2)))

    if m < 6 or rank < 6:
        return (residual, 0.0, 0.0)

    a, b, c2, d, e, _ = coeffs
    fuu, fuv, fvv, fu, fv = 2.0 * a, b, 2.0 * c2, d, e
    denom = np.sqrt(1.0 + fu * fu + fv * fv)
    gauss = (fuu * fvv - fuv * fuv) / denom**4
    mean_h = (fuu * (1.0 + fv * fv) - 2.0 * fuv * fu * fv + fvv * (1.0 + fu * fu)) / (
        2.0 * denom**3
    )
    disc = np.sqrt(max(mean_h * mean_h - gauss, 0.0))
    k1 = float(mean_h + disc)
    k2 = float(mean_h - disc)
    return (residual, k1, k2)


def surface_residuals(
    pos: NDArray,
    normals: NormalSource,
    neighbors: Neighbors,
    *,
    attr: str = "normal",
    points: Optional[NDArray] = None,
) -> Tuple[NDArray, NDArray, NDArray]:
    """Per-point :func:`fit_surface` over each point's neighborhood.

    Args:
        pos: Voxel positions ``(N, 3)``.
        normals: Any normals feed.
        neighbors: Per-point neighbor-index lists.
        attr: PointCloud normal attribute name.
        points: Positions for a dense/array normals feed (defaults to ``pos``).

    Returns:
        ``(residual, k1, k2)`` each ``(N,)``; points with too few neighbors get 0s.
    """
    p = np.asarray(pos, dtype=np.float64)
    n = resolve_normals(normals, points if points is not None else p, attr=attr)
    res = np.zeros(p.shape[0], dtype=np.float64)
    k1 = np.zeros(p.shape[0], dtype=np.float64)
    k2 = np.zeros(p.shape[0], dtype=np.float64)
    for i, nb in enumerate(neighbors):
        idx = np.asarray(nb, dtype=np.int64)
        patch = np.unique(np.concatenate([[i], idx])) if idx.size else np.array([i])
        if patch.size < 3:
            continue
        res[i], k1[i], k2[i] = fit_surface(p[patch], n[patch])
    return res, k1, k2


__all__: List[str] = [
    "resolve_positions",
    "resolve_normals",
    "normal_coherence",
    "local_curvature",
    "fit_surface",
    "surface_residuals",
]
