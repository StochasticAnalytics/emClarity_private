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
    _FFT_KERNEL_THRESHOLD,
    ClusterDensityProvider,
    MembraneDistanceProvider,
    _sphere_kernel,
    _sphere_kernel_size,
    _tophat_sphere_convolve,
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


def test_tophat_fft_matches_direct_for_large_kernel() -> None:
    """The FFT fast-path (large sphere kernel) is numerically identical to the exact dense
    ``ndi.convolve``. This is the perf fix for the 20-vox gold/ice radius: same physics, O(N log N)
    instead of the dense O(N*r^3) sliding window that dominated the feature cache."""
    import scipy.ndimage as ndi

    rng = np.random.default_rng(0)
    vol = (rng.random((48, 52, 50), dtype=np.float32) < 0.02).astype(np.float32)  # sparse mask
    radius_vox = 9.0  # 19^3 = 6859 elements > _FFT_KERNEL_THRESHOLD -> FFT path
    kernel = _sphere_kernel(radius_vox)
    assert kernel.size > _FFT_KERNEL_THRESHOLD
    direct = np.asarray(ndi.convolve(vol, kernel, mode="constant", cval=0.0), dtype=np.float32)
    fast = cluster_density(vol, radius_vox=radius_vox, mode="tophat")
    np.testing.assert_allclose(fast, direct, atol=1e-5)


def test_tophat_small_kernel_uses_exact_direct_path() -> None:
    """Small kernels stay on the exact direct convolution (bit-stable, no FFT), so the existing
    tiny-radius tests are unaffected by the fast-path switch."""
    import scipy.ndimage as ndi

    vol = np.zeros((16, 16, 16), dtype=np.float32)
    vol[7:9, 7:9, 7:9] = 1.0
    kernel = _sphere_kernel(2.0)  # 5^3 = 125 <= threshold
    assert kernel.size <= _FFT_KERNEL_THRESHOLD
    got = _tophat_sphere_convolve(vol, kernel)
    exact = np.asarray(ndi.convolve(vol, kernel, mode="constant", cval=0.0), dtype=np.float32)
    np.testing.assert_array_equal(got, exact)  # identical, not just close


class _FakeCcReg:
    """Minimal FieldRegistry stand-in: resolve('cc') returns a fixed synthetic convmap."""

    def __init__(self, vol: np.ndarray) -> None:
        self._field = DenseField.from_array("cc", VoxelGrid(vol.shape, 12.5), vol, channels=1)

    def resolve(self, name: str, tomo: object, *, device: Device) -> DenseField:
        assert name == "cc"
        return self._field


def _cluster_convmap() -> np.ndarray:
    """A background ~N(3.28, 0.42) volume with one compact extreme-CC (gold/ice) cluster."""
    rng = np.random.default_rng(0)
    vol = rng.normal(3.28, 0.42, size=(40, 40, 40)).astype(np.float32)
    vol[18:23, 18:23, 18:23] = 10.0  # a 5^3 gold/ice cluster at ~z=16 sigma
    return vol


def test_cluster_density_provider_thr_sigma_isolates_extreme_band() -> None:
    """thr_sigma thresholds in per-tomo robust sigmas; only the gold/ice cluster survives."""
    vol = _cluster_convmap()
    prov = ClusterDensityProvider(thr_sigma=8.0, radius_A=62.5, count=True)  # 5-voxel radius
    field = prov.materialize(
        tomo=cast(Any, object()), reg=cast(Any, _FakeCcReg(vol)), device=Device.CPU
    )
    # Threshold lands well above background (median ~3.28) and below the cluster (10).
    assert 4.0 < prov.last_threshold < 9.0
    # The count is high inside the cluster, ~0 in pure background.
    at_cluster = float(
        np.asarray(field.sample_at(np.array([[20.0, 20.0, 20.0]]), reduce="center")).reshape(-1)[0]
    )
    at_bg = float(
        np.asarray(field.sample_at(np.array([[2.0, 2.0, 2.0]]), reduce="center")).reshape(-1)[0]
    )
    assert at_cluster >= 100.0  # 5^3 = 125 extreme voxels within the radius
    assert at_bg <= 5.0


def test_cluster_density_provider_count_vs_fraction() -> None:
    """count=True yields fraction * sphere-size; the sphere size matches _sphere_kernel_size."""
    vol = _cluster_convmap()
    frac_prov = ClusterDensityProvider(thr_sigma=8.0, radius_A=62.5, count=False)
    cnt_prov = ClusterDensityProvider(thr_sigma=8.0, radius_A=62.5, count=True)
    ff = frac_prov.materialize(
        tomo=cast(Any, object()), reg=cast(Any, _FakeCcReg(vol)), device=Device.CPU
    )
    cf = cnt_prov.materialize(
        tomo=cast(Any, object()), reg=cast(Any, _FakeCcReg(vol)), device=Device.CPU
    )
    pt = np.array([[20.0, 20.0, 20.0]])
    frac = float(np.asarray(ff.sample_at(pt, reduce="center")).reshape(-1)[0])
    cnt = float(np.asarray(cf.sample_at(pt, reduce="center")).reshape(-1)[0])
    size = _sphere_kernel_size(62.5 / 12.5)
    assert cnt == pytest.approx(frac * size, rel=1e-4)
    assert size > 1


def test_cluster_density_provider_thr_precedence() -> None:
    """Absolute thr wins over thr_sigma wins over percentile."""
    vol = _cluster_convmap()
    reg = _FakeCcReg(vol)
    abs_prov = ClusterDensityProvider(thr=7.0, thr_sigma=8.0)
    abs_prov.materialize(tomo=cast(Any, object()), reg=cast(Any, reg), device=Device.CPU)
    assert abs_prov.last_threshold == pytest.approx(7.0)
    pct_prov = ClusterDensityProvider(thr=None, thr_sigma=None, thr_percentile=99.0)
    pct_prov.materialize(tomo=cast(Any, object()), reg=cast(Any, reg), device=Device.CPU)
    assert pct_prov.last_threshold == pytest.approx(float(np.percentile(vol, 99.0)), rel=1e-4)


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
