"""Unit tests for the derived numeric kernels: cluster density, blobness, EDT, bead raster.

These back the gold/ice discriminators (SPEC §1: gold/ice = compact clusters of extreme CC).
Tests run on synthetic volumes (deterministic ground truth) plus a real convmap crop for the
end-to-end derive.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple, cast

import numpy as np
import pytest

from mito_filter.core.backend import Device
from mito_filter.core.field import DenseField
from mito_filter.core.grid import VoxelGrid
from mito_filter.emclarity.mrc_io import open_dense_mmap
from mito_filter.fields.derived import (
    MembraneDistanceProvider,
    blobness,
    cluster_density,
    hessian_membraneness,
    membrane_segmentation,
    signed_edt,
)
from mito_filter.fields.gold import rasterize_beads, stack_base
from mito_filter.fields.provider import Availability


def test_cluster_density_tophat_is_local_fraction() -> None:
    """A compact block of set voxels yields high local density at its centre, ~0 far away."""
    vol = np.zeros((40, 40, 40), dtype=np.float32)
    vol[18:22, 18:22, 18:22] = 1.0  # a 4^3 compact cluster
    dens = cluster_density(vol, radius_vox=5.0, mode="tophat")
    assert dens.shape == vol.shape
    assert dens[20, 20, 20] > 0.05  # centre sees a chunk of the cluster within the sphere
    assert dens[20, 20, 20] == dens.max()
    assert dens[0, 0, 0] == pytest.approx(0.0)


def test_cluster_density_gaussian_peaks_at_cluster() -> None:
    vol = np.zeros((30, 30, 30), dtype=np.float32)
    vol[15, 15, 15] = 1.0
    dens = cluster_density(vol, radius_vox=4.0, mode="gaussian")
    assert tuple(int(x) for x in np.unravel_index(int(dens.argmax()), dens.shape)) == (15, 15, 15)


def test_cluster_density_bad_mode_raises() -> None:
    with pytest.raises(ValueError):
        cluster_density(np.zeros((4, 4, 4), np.float32), radius_vox=1.0, mode="nope")


def test_blobness_log_detects_a_bright_blob() -> None:
    """A single Gaussian bump gives a blob response peaked at its centre."""
    n = 41
    ax = np.arange(n) - n // 2
    zz, yy, xx = np.meshgrid(ax, ax, ax, indexing="ij")
    vol = np.exp(-(zz**2 + yy**2 + xx**2) / (2 * 3.0**2)).astype(np.float32)
    resp = blobness(vol, sigma_vox=3.0, method="log")
    assert resp.min() >= 0.0  # LoG response is clipped at 0
    peak = tuple(int(x) for x in np.unravel_index(int(resp.argmax()), resp.shape))
    assert peak == (n // 2, n // 2, n // 2)


def test_blobness_bad_method_raises() -> None:
    with pytest.raises(ValueError):
        blobness(np.zeros((4, 4, 4), np.float32), sigma_vox=1.0, method="nope")


def test_signed_edt_sign_and_magnitude() -> None:
    mask = np.zeros((21, 21, 21), dtype=bool)
    mask[6:15, 6:15, 6:15] = True
    sdf = signed_edt(mask)
    assert sdf[10, 10, 10] < 0.0  # deep inside is negative
    assert sdf[0, 0, 0] > 0.0  # far outside is positive
    # A voxel just outside the face is ~1 voxel from the surface.
    assert sdf[5, 10, 10] == pytest.approx(1.0, abs=1e-4)


def test_rasterize_beads_mask_and_distance() -> None:
    grid = VoxelGrid((30, 30, 30), 12.5)
    pts = np.array([[15.0, 15.0, 15.0]], dtype=np.float64)  # one bead, (z, y, x)
    mask, dist = rasterize_beads(pts, grid, radius_vox=3.0)
    assert dist[15, 15, 15] == pytest.approx(0.0)
    assert mask[15, 15, 15]
    assert not mask[15, 15, 25]  # >3 vox away
    assert dist[15, 15, 20] == pytest.approx(5.0, abs=1e-4)


def test_rasterize_beads_drops_out_of_bounds() -> None:
    grid = VoxelGrid((10, 10, 10), 12.5)
    pts = np.array([[100.0, 100.0, 100.0]], dtype=np.float64)  # outside the grid
    mask, _ = rasterize_beads(pts, grid, radius_vox=2.0)
    assert not mask.any()


def test_stack_base_strips_convmap_suffix() -> None:
    assert stack_base("H99_2_100_1_bin5") == "H99_2_100"
    assert stack_base("already_stack") == "already_stack"


def test_cluster_density_on_real_convmap_crop() -> None:
    """End-to-end: a thresholded high-CC mask + density on a real crop is finite and in [0, 1]."""
    path = Path(
        "/scratch/siracusa/full_enchilada_3/six_hours_round_4/"
        "convmap_wedgeType_2_bin5/H99_2_100_1_bin5_convmap.mrc"
    )
    if not path.exists():
        pytest.skip("real dev-set convmap not present on this host")
    mm = open_dense_mmap(path)
    crop = np.asarray(mm[100:180, 200:400, 200:400], np.float32)
    thr = float(np.percentile(crop, 99.0))
    mask = (crop >= thr).astype(np.float32)
    dens = cluster_density(mask, radius_vox=250.0 / 12.5, mode="tophat")
    assert np.isfinite(dens).all()
    assert dens.min() >= 0.0 and dens.max() <= 1.0
    # The extreme-CC voxels are clustered, so the max local density is meaningfully > mean.
    assert dens.max() > dens.mean()


# --------------------------------------------------------------------------- #
# membrane segmentation from a tomogram (DESIGN §5, §7; SPEC §8)               #
# --------------------------------------------------------------------------- #
def _bright_ball(
    shape: Tuple[int, int, int] = (44, 44, 44),
    center: Tuple[int, int, int] = (22, 22, 22),
    radius: float = 13.0,
    thick: float = 1.5,
) -> np.ndarray:
    """A bright (positive-density) spherical membrane SHELL — a closed bright bilayer ridge."""
    zz, yy, xx = np.mgrid[0 : shape[0], 0 : shape[1], 0 : shape[2]].astype(np.float64)
    rr = np.sqrt((zz - center[0]) ** 2 + (yy - center[1]) ** 2 + (xx - center[2]) ** 2)
    vol = np.zeros(shape, dtype=np.float32)
    vol[np.abs(rr - radius) <= thick] = 5.0
    return vol


def test_hessian_membraneness_fires_on_bright_sheet() -> None:
    """A bright planar sheet gives high membraneness with NEGATIVE dominant-curvature sign."""
    vol = np.zeros((32, 32, 32), dtype=np.float32)
    vol[15:17, :, :] = 5.0  # a bright slab (sheet normal along z)
    membr, sign = hessian_membraneness(vol, sigma_vox=1.6)
    assert membr.shape == vol.shape
    on = membr[16, 16, 16]
    off = membr[2, 2, 2]
    assert on > off and on > 0.0  # the sheet lights up, empty background does not
    assert sign[16, 16, 16] < 0.0  # bright density ridge -> negative dominant eigenvalue


def test_membrane_segmentation_recovers_closed_shell() -> None:
    """Segmenting a bright spherical shell yields a non-empty, single-component closed surface."""
    vol = _bright_ball()
    seg = membrane_segmentation(
        vol, sigma_vox=1.6, percentile=95.0, bright=True, min_component_vox=20
    )
    assert seg.dtype == bool and seg.sum() > 100
    # The shell is hollow: its centre is NOT part of the membrane sheet itself.
    assert not seg[22, 22, 22]
    # Filling the closed shell + signed EDT makes the enclosed centre negative (inside), which is
    # exactly what the provider does so inside_sign flags interior compartments.
    from scipy import ndimage as ndi

    sdf = signed_edt(ndi.binary_fill_holes(seg))
    assert sdf[22, 22, 22] < 0.0


class _FakeRecReg:
    """Minimal FieldRegistry stand-in: resolve('rec') returns a fixed synthetic volume."""

    def __init__(self, vol: np.ndarray) -> None:
        self._field = DenseField.from_array("rec", VoxelGrid(vol.shape, 12.5), vol, channels=1)

    def resolve(self, name: str, tomo: object, *, device: Device) -> DenseField:
        assert name == "rec"
        return self._field


def test_membrane_provider_derives_sdf_from_rec() -> None:
    """MembraneDistanceProvider is GENERATABLE from `rec` and produces an inside-negative SDF."""
    prov = MembraneDistanceProvider(from_rec=True, percentile=95.0, min_component_vox=20)
    assert prov.requires == ("rec",)
    # No seg file and from_rec -> GENERATABLE (not MISSING).
    assert prov.available(tomo=cast(Any, object())) is Availability.GENERATABLE
    reg = _FakeRecReg(_bright_ball())
    field = prov.materialize(tomo=cast(Any, object()), reg=cast(Any, reg), device=Device.CPU)
    assert field.name == "membrane_sdf"
    center = field.sample_at(np.array([[22.0, 22.0, 22.0]]), reduce="center", radius=0)
    assert float(np.asarray(center).reshape(-1)[0]) < 0.0  # enclosed interior is negative


def test_membrane_provider_missing_without_rec_or_seg() -> None:
    """With from_rec=False and no seg-file suffix, the provider reports MISSING."""
    prov = MembraneDistanceProvider(from_rec=False, segmentation_suffix=None)
    assert prov.available(tomo=cast(Any, object())) is Availability.MISSING


def test_membraneness_on_real_rec_crop() -> None:
    """On a real reconstruction crop the Hessian membraneness segments non-empty membrane sheets."""
    path = Path("/scratch/salina/alt_cache/H99_2_100_1_bin5.rec")
    if not path.exists():
        pytest.skip("real rec not present on this host")
    mm = open_dense_mmap(path)
    crop = np.asarray(mm[180:300, 380:620, 260:520], np.float32)  # interior slab with membranes
    membr, sign = hessian_membraneness(crop, sigma_vox=1.6)
    assert np.isfinite(membr).all() and membr.min() >= 0.0
    seg = membrane_segmentation(crop, sigma_vox=1.6, percentile=99.3, bright=True)
    frac = float(seg.mean())
    # Membranes are thin sheets: a small but non-trivial fraction of the crop, not everything.
    assert 0.0 < frac < 0.05
