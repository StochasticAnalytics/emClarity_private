"""Surface tests: coherence, curvature, quadric fit, dual sparse/dense normals feed."""

from __future__ import annotations

from typing import cast

import numpy as np

from mito_filter.core.field import VectorField
from mito_filter.core.grid import VoxelGrid
from mito_filter.core.neighbors import NeighborIndex
from mito_filter.core.points import PointCloud
from mito_filter.core.surfaces import (
    fit_surface,
    local_curvature,
    normal_coherence,
    resolve_normals,
    surface_residuals,
)


def _plane_patch(n: int = 9) -> tuple[np.ndarray, np.ndarray]:
    g = np.linspace(-4, 4, n)
    u, v = np.meshgrid(g, g)
    pos = np.stack([np.zeros(u.size), u.ravel(), v.ravel()], axis=1)  # z=0 plane
    normals = np.tile([1.0, 0.0, 0.0], (pos.shape[0], 1))
    return pos, normals


def _sphere_cap(radius: float = 20.0, half: int = 4) -> tuple[np.ndarray, np.ndarray]:
    g = np.linspace(-3, 3, 2 * half + 1)
    um, vm = np.meshgrid(g, g)
    u, v = um.ravel(), vm.ravel()
    # z as a spherical cap over the (u, v) tangent plane near the north pole.
    zz = np.sqrt(np.maximum(radius**2 - u**2 - v**2, 0.0))
    pos = np.stack([zz, u, v], axis=1)
    center = np.array([0.0, 0.0, 0.0])
    normals = pos - center
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    return pos, normals


def test_coherence_aligned_vs_random() -> None:
    pos, normals = _plane_patch()
    idx = NeighborIndex(pos, apix=1.0)
    nb = idx.self_radius(3.0)
    coh = normal_coherence(normals, nb)
    assert np.all(coh > 0.999)

    rng = np.random.default_rng(0)
    rand = rng.standard_normal(normals.shape)
    rand /= np.linalg.norm(rand, axis=1, keepdims=True)
    coh_r = normal_coherence(rand, nb)
    assert coh_r.mean() < 0.9


def test_curvature_plane_is_flat() -> None:
    pos, normals = _plane_patch()
    idx = NeighborIndex(pos, apix=1.0)
    nb = idx.self_radius(3.0)
    curv = local_curvature(normals, pos, nb, apix=1.0)
    np.testing.assert_allclose(curv, 0.0, atol=1e-9)


def test_curvature_sphere_approx_inverse_radius() -> None:
    R = 20.0
    pos, normals = _sphere_cap(radius=R)
    idx = NeighborIndex(pos, apix=1.0)
    nb = idx.self_radius(2.5)
    curv = local_curvature(normals, pos, nb, apix=1.0)
    interior = curv[curv > 0]
    # deflection-per-distance ~ 1/R for a sphere.
    assert abs(np.median(interior) - 1.0 / R) < 0.02


def test_fit_surface_plane() -> None:
    pos, normals = _plane_patch()
    residual, k1, k2 = fit_surface(pos, normals)
    assert residual < 1e-9
    assert abs(k1) < 1e-6 and abs(k2) < 1e-6


def test_fit_surface_sphere_principal_curvature() -> None:
    R = 20.0
    pos, normals = _sphere_cap(radius=R, half=5)
    residual, k1, k2 = fit_surface(pos, normals)
    # both principal curvatures ~ 1/R in magnitude for a sphere (sign follows the
    # outward-normal frame; a convex sphere reads concave in height over the tangent plane).
    assert abs(abs(k1) - 1.0 / R) < 0.02
    assert abs(abs(k2) - 1.0 / R) < 0.02
    assert k1 >= k2
    assert residual < 1.0


def test_surface_residuals_per_point() -> None:
    pos, normals = _plane_patch()
    idx = NeighborIndex(pos, apix=1.0)
    nb = idx.self_radius(4.0)
    res, k1, k2 = surface_residuals(pos, normals, nb)
    assert res.shape == (pos.shape[0],)
    assert np.all(res < 1e-6)


def test_resolve_normals_from_pointcloud() -> None:
    pos, normals = _plane_patch(3)
    pc = PointCloud(pos, {"normal": normals})
    got = resolve_normals(pc)
    np.testing.assert_allclose(got, normals)


def test_resolve_normals_from_vector_field() -> None:
    vol = np.zeros((4, 5, 6, 3), dtype=np.float32)
    vol[1, 2, 3] = [0.0, 0.6, 0.8]
    g = VoxelGrid((4, 5, 6), 12.5)
    vf = cast(VectorField, VectorField.from_array("normal", g, vol, channels=3))
    pts = np.array([[1, 2, 3]], dtype=float)
    got = resolve_normals(vf, pts)
    assert got.shape == (1, 3)
    np.testing.assert_allclose(got[0], [0.0, 0.6, 0.8], atol=1e-6)


def test_coherence_accepts_dense_and_sparse_equally() -> None:
    # Same normals through the sparse (array) and dense (VectorField) paths -> same result.
    pos, normals = _plane_patch(4)
    idx = NeighborIndex(pos, apix=1.0)
    nb = idx.self_radius(3.0)
    sparse = normal_coherence(normals, nb)

    grid_shape = (5, 20, 20)
    vol = np.zeros(grid_shape + (3,), dtype=np.float32)
    ipos = np.rint(pos).astype(int)
    ipos[:, 1:] += 8  # shift into the volume interior
    for (z, y, x), nrm in zip(ipos, normals):
        vol[z, y, x] = nrm
    vf = cast(
        VectorField, VectorField.from_array("normal", VoxelGrid(grid_shape, 1.0), vol, channels=3)
    )
    dense = normal_coherence(vf, nb, points=ipos.astype(float))
    np.testing.assert_allclose(sparse, dense, atol=1e-6)
