"""Integration: load-vs-derive provider parity + DAG resolution + content-addressed cache.

Exercises the :class:`~mito_filter.fields.provider.FieldRegistry` resolver on a small crop of the
real ``H99_2_100_1_bin5`` convmap (DESIGN §5):

* a **loaded** ``cc`` field equals a direct memmap read (byte-for-byte);
* a **derived** ``snr`` field equals a hand-computed background z-score of the same crop;
* the provider **DAG** orders dependencies first and folds a ``MISSING`` dependency up the chain;
* an unavailable field resolves to a neutral ``None`` via ``try_resolve`` but raises via
  ``resolve``;
* the opt-in **content-addressed on-disk cache** round-trips and rebuilds when a source mtime
  changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, cast

import numpy as np
import pytest

from mito_filter.core.backend import Device
from mito_filter.core.field import Block, DenseField
from mito_filter.core.grid import VoxelGrid
from mito_filter.datasets.base import TomogramRef
from mito_filter.emclarity.mrc_io import open_dense_mmap
from mito_filter.fields import _tomo
from mito_filter.fields.calibrate import BackgroundModel
from mito_filter.fields.derived import register_derived
from mito_filter.fields.loaders import register_loaders
from mito_filter.fields.provider import (
    Availability,
    Cost,
    CostTier,
    FieldProvider,
    FieldRegistry,
    FieldSpec,
    FieldUnavailable,
)

REAL = Path(
    "/scratch/siracusa/full_enchilada_3/six_hours_round_4/"
    "convmap_wedgeType_2_bin5/H99_2_100_1_bin5_convmap.mrc"
)


def _ref(
    *,
    base: str,
    convmap_path: Path,
    rec_dir: Optional[Path] = None,
    fixedstacks_dir: Optional[Path] = None,
) -> TomogramRef:
    """Build a ``_tomo.TomoRef`` typed as the ``TomogramRef`` the registry expects."""
    return cast(
        TomogramRef,
        _tomo.TomoRef(
            base=base,
            convmap_path=convmap_path,
            rec_dir=rec_dir,
            fixedstacks_dir=fixedstacks_dir,
        ),
    )


def _require_real() -> Path:
    if not REAL.exists():
        pytest.skip("real dev-set convmap not present on this host")
    return REAL


def _whole(field: DenseField) -> np.ndarray:
    nz, ny, nx = field.grid.shape
    return np.asarray(field.block(Block((0, nz), (0, ny), (0, nx))))


class _CropCcProvider(FieldProvider):
    """A stub ``cc`` provider serving an in-memory crop (so derives run on a small volume)."""

    produces = FieldSpec("cc", 1, np.dtype(np.float32), "crop cc")

    def __init__(self, field: DenseField) -> None:
        self._field = field

    def available(self, tomo: object) -> Availability:
        return Availability.ON_DISK

    def materialize(self, tomo: object, reg: FieldRegistry, *, device: Device) -> DenseField:
        return self._field


# --- real-data load / derive parity -----------------------------------------------------------


def test_convmap_load_parity() -> None:
    path = _require_real()
    tomo = _ref(base="H99_2_100_1_bin5", convmap_path=path)
    reg = FieldRegistry()
    register_loaders(reg)
    cc = reg.resolve("cc", tomo, device=Device.CPU)
    assert cc.grid.shape == (448, 942, 662)
    assert cc.grid.apix == 12.5
    mm = open_dense_mmap(path)
    direct = np.asarray(mm[120:132, 300:340, 250:300], np.float32)
    via = cc.block(Block((120, 132), (300, 340), (250, 300)))
    assert np.array_equal(direct, via)


def test_snr_derive_parity() -> None:
    path = _require_real()
    mm = open_dense_mmap(path)
    crop = np.asarray(mm[100:150, 200:300, 300:400], np.float32)
    cc_field = DenseField.from_array("cc", VoxelGrid(crop.shape, 12.5), crop, channels=1)

    reg = FieldRegistry()
    reg.register(_CropCcProvider(cc_field))
    register_derived(reg)
    tomo = _ref(base="H99_2_100_1_bin5", convmap_path=path)

    snr = reg.resolve("snr", tomo, device=Device.CPU)
    expected = BackgroundModel("mad").fit(crop).zscore(crop)
    assert np.array_equal(_whole(snr), expected)


def test_snr_memoized_within_registry() -> None:
    path = _require_real()
    mm = open_dense_mmap(path)
    crop = np.asarray(mm[100:130, 200:260, 300:360], np.float32)
    cc_field = DenseField.from_array("cc", VoxelGrid(crop.shape, 12.5), crop, channels=1)
    reg = FieldRegistry()
    reg.register(_CropCcProvider(cc_field))
    register_derived(reg)
    tomo = _ref(base="H99_2_100_1_bin5", convmap_path=path)
    a = reg.resolve("snr", tomo, device=Device.CPU)
    b = reg.resolve("snr", tomo, device=Device.CPU)
    assert a is b  # per-tomo memoization


# --- DAG / availability tri-state --------------------------------------------------------------


def test_plan_orders_dependencies_first() -> None:
    reg = FieldRegistry()
    register_loaders(reg)
    register_derived(reg)
    tomo = _ref(base="b", convmap_path=Path("/nope/b_convmap.mrc"))
    order = reg.plan({"snr"}, tomo)
    names = [p.produces.name for p in order]
    assert names.index("cc") < names.index("snr")


class _MissingProvider(FieldProvider):
    """A provider that can never produce its field (deterministic MISSING leaf)."""

    produces = FieldSpec("ghost", 1, np.dtype(np.float32), "always missing")

    def available(self, tomo: object) -> Availability:
        return Availability.MISSING

    def materialize(self, tomo: object, reg: FieldRegistry, *, device: Device) -> DenseField:
        raise AssertionError("MISSING provider must never materialize")


class _NeedsGhostProvider(FieldProvider):
    """A derive provider whose only dependency is the MISSING ``ghost`` field."""

    produces = FieldSpec("needs_ghost", 1, np.dtype(np.float32), "derived from ghost")
    requires = ("ghost",)

    def available(self, tomo: object) -> Availability:
        return Availability.GENERATABLE

    def materialize(self, tomo: object, reg: FieldRegistry, *, device: Device) -> DenseField:
        reg.resolve("ghost", cast(TomogramRef, tomo), device=device)  # raises FieldUnavailable
        raise AssertionError("unreachable")


def test_missing_dependency_folds_and_goes_neutral() -> None:
    """A MISSING leaf folds up the DAG: effective MISSING, try_resolve None, resolve raises."""
    tomo = _ref(base="b", convmap_path=Path("/nope/b_convmap.mrc"))
    reg = FieldRegistry()
    reg.register(_MissingProvider())
    reg.register(_NeedsGhostProvider())
    assert reg.effective_availability("ghost", tomo) is Availability.MISSING
    assert reg.effective_availability("needs_ghost", tomo) is Availability.MISSING
    assert reg.try_resolve("needs_ghost", tomo, device=Device.CPU) is None
    with pytest.raises(FieldUnavailable):
        reg.resolve("needs_ghost", tomo, device=Device.CPU)


def test_unregistered_optional_field_is_neutral() -> None:
    """try_resolve of a field with NO provider returns None (an optional field a config skipped)."""
    tomo = _ref(base="b", convmap_path=Path("/nope/b_convmap.mrc"))
    reg = FieldRegistry()
    assert reg.try_resolve("noise_variance", tomo, device=Device.CPU) is None


def test_angle_loader_decode_matches_csv_normal() -> None:
    """AngleIndexLoader + SPEC §5 decode reproduce the csv normal (cols 23-25) at peak voxels.

    The dense argmax lands on the integer voxel; the csv position is sub-voxel CoM-refined
    (SPEC §3), so the decoded normal matches within the ±1 neighborhood (as the score does).
    This is the dense-orientation acceptance check on real data.
    """
    from mito_filter.emclarity.angles_list import read_angles_list
    from mito_filter.emclarity.conventions import decode_index_volume_to_normal
    from mito_filter.fields.loaders import AngleIndexLoader

    d = REAL.parent
    apath = d / "H99_2_100_1_bin5_angles.mrc"
    if not apath.exists():
        pytest.skip("dense angle field not regenerated on this host (SPEC §7)")
    tomo = _ref(base="H99_2_100_1_bin5", convmap_path=REAL)
    reg = FieldRegistry()
    reg.register(AngleIndexLoader())
    angle = reg.resolve("angle", tomo, device=Device.CPU)
    assert angle.dtype == np.dtype("<f4")  # fp32 (mode-2): packed 2592 would corrupt in fp16
    mm = angle.as_memmap()
    nz, ny, nx = angle.grid.shape

    csv = np.loadtxt(d / "H99_2_100_1_bin5.csv")[:400]  # a subset keeps it fast
    pos_zyx = np.rint((csv[:, 10:13] / 5.0)[:, ::-1]).astype(int)
    nrm_xyz = csv[:, 22:25]
    inb = (
        (pos_zyx[:, 0] >= 1)
        & (pos_zyx[:, 0] < nz - 1)
        & (pos_zyx[:, 1] >= 1)
        & (pos_zyx[:, 1] < ny - 1)
        & (pos_zyx[:, 2] >= 1)
        & (pos_zyx[:, 2] < nx - 1)
    )
    pos_zyx, nrm_xyz = pos_zyx[inb], nrm_xyz[inb]
    angles = read_angles_list(d / "H99_2_100_1_bin5_angles.list")

    best = np.full(pos_zyx.shape[0], 180.0)
    for dz in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                packed = np.rint(
                    np.asarray(mm[pos_zyx[:, 0] + dz, pos_zyx[:, 1] + dy, pos_zyx[:, 2] + dx])
                ).astype(np.int64)
                dec = decode_index_volume_to_normal(packed, angles)  # (N, 3) raw (x, y, z)
                cos = np.clip(np.abs(np.sum(dec * nrm_xyz, axis=1)), 0.0, 1.0)
                best = np.minimum(best, np.degrees(np.arccos(cos)))
    assert np.median(best) < 0.5
    assert (best < 1.0).mean() > 0.98


def test_normal_field_provider_decodes_and_reverses_axes() -> None:
    """NormalFieldProvider derives a (z,y,x) VectorField matching the SPEC §5 point decode."""
    from mito_filter.core.field import IndexField
    from mito_filter.emclarity.angles_list import read_angles_list
    from mito_filter.emclarity.conventions import decode_index_volume_to_normal
    from mito_filter.fields.derived import NormalFieldProvider

    d = REAL.parent
    alist = d / "H99_2_100_1_bin5_angles.list"
    if not alist.exists():
        pytest.skip("real _angles.list not present on this host")
    angles = read_angles_list(alist)

    grid = VoxelGrid((2, 3, 4), 12.5)
    packed = (np.arange(2 * 3 * 4) % 2592 + 1).reshape(2, 3, 4).astype(np.float32)
    idx_field = IndexField("angle", grid, packed, channels=1)

    class _AngleStub(FieldProvider):
        produces = FieldSpec("angle", 1, np.dtype(np.float32), "stub angle")

        def available(self, tomo: object) -> Availability:
            return Availability.ON_DISK

        def materialize(self, tomo: object, reg: FieldRegistry, *, device: Device) -> DenseField:
            return idx_field

    reg = FieldRegistry()
    reg.register(_AngleStub())
    reg.register(NormalFieldProvider())
    tomo = _ref(base="H99_2_100_1_bin5", convmap_path=REAL)
    normal = reg.resolve("normal", tomo, device=Device.CPU)
    assert normal.channels == 3
    got = _whole(normal)  # (2,3,4,3) in (z,y,x) order
    expect_xyz = decode_index_volume_to_normal(packed.astype(np.int64), angles)
    expect_zyx = expect_xyz[..., ::-1]
    assert np.allclose(got, expect_zyx, atol=1e-5)


def _discover_angle_tomos(max_n: int = 3) -> List[str]:
    """Discover up to ``max_n`` bases with the angle/csv/list triple next to the real convmap."""
    d = REAL.parent
    bases: List[str] = []
    for ap in sorted(d.glob("*_angles.mrc")):
        base = ap.name[: -len("_angles.mrc")]
        if (d / f"{base}.csv").exists() and (d / f"{base}_angles.list").exists():
            bases.append(base)
        if len(bases) >= max_n:
            break
    return bases


def test_dense_normal_signed_matches_csv_multi_tomo() -> None:
    """Dense-decoded normal == csv cols 23-25 at the peak (±1 voxel), SIGNED, across ≥2 tomos.

    The dense argmax sits on the integer voxel while the csv position is sub-voxel CoM-refined
    (SPEC §3), so the exact rounded voxel matches only ~20-25% of the time (bimodal: near-exact
    or background-random). Searching the ±1 neighborhood recovers the true peak voxel and the
    decoded outward normal matches the csv normal to <1° on >98% of peaks. Crucially this is a
    **signed** dot (no ``abs``): a handedness / axis-order bug would flip the normal (>90° error)
    on a large fraction — here sign flips are ~0, proving the raw sign convention is correct.
    """
    from mito_filter.emclarity.angles_list import read_angles_list
    from mito_filter.emclarity.conventions import decode_index_volume_to_normal
    from mito_filter.emclarity.mrc_io import open_dense_mmap

    bases = _discover_angle_tomos(max_n=3)
    if len(bases) < 2:
        pytest.skip("need ≥2 real tomos with the angle/csv/list triple (SPEC §7 re-run)")
    d = REAL.parent
    for base in bases:
        mm = open_dense_mmap(d / f"{base}_angles.mrc", is_index=True)  # fp32; refuses fp16
        nz, ny, nx = mm.shape
        angles = read_angles_list(d / f"{base}_angles.list")
        csv = np.loadtxt(d / f"{base}.csv")
        pos_zyx = np.rint((csv[:, 10:13] / 5.0)[:, ::-1]).astype(int)
        nrm_xyz = csv[:, 22:25]
        inb = (
            (pos_zyx[:, 0] >= 1)
            & (pos_zyx[:, 0] < nz - 1)
            & (pos_zyx[:, 1] >= 1)
            & (pos_zyx[:, 1] < ny - 1)
            & (pos_zyx[:, 2] >= 1)
            & (pos_zyx[:, 2] < nx - 1)
        )
        pos_zyx, nrm_xyz = pos_zyx[inb], nrm_xyz[inb]
        nrm_xyz = nrm_xyz / np.linalg.norm(nrm_xyz, axis=1, keepdims=True)

        best = np.full(pos_zyx.shape[0], 180.0)
        for dz in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    packed = np.rint(
                        np.asarray(mm[pos_zyx[:, 0] + dz, pos_zyx[:, 1] + dy, pos_zyx[:, 2] + dx])
                    ).astype(np.int64)
                    dec = decode_index_volume_to_normal(packed, angles)  # (N,3) raw (x,y,z)
                    dec = dec / np.linalg.norm(dec, axis=1, keepdims=True)
                    cos = np.clip(np.sum(dec * nrm_xyz, axis=1), -1.0, 1.0)  # SIGNED
                    best = np.minimum(best, np.degrees(np.arccos(cos)))
        assert np.median(best) < 0.5, f"{base}: median {np.median(best):.3f}°"
        assert (best < 1.0).mean() > 0.98, f"{base}: frac<1° {(best < 1.0).mean():.4f}"
        assert (best > 90.0).mean() < 0.01, f"{base}: sign-flips {(best > 90.0).mean():.4f}"


def test_packed_index_invariants_real() -> None:
    """Real ``_angles.mrc`` is a valid packed field: fp32, all in [1, 2592], templates ⊆ {1,2,3}.

    Confirms the SPEC §5 decode split on real data: ``refIdx = (p-1) % 3 + 1`` covers exactly the
    three references and ``angleIdx = (p-1)//3 + 1`` stays in ``[1, 864]``. Also documents the
    empirical fact that the dense argmax has **no 0 (no-hit) voxels** — emClarity writes an argmax
    everywhere, which is precisely why dense-normal ops must be CC-gated.
    """
    from mito_filter.emclarity.conventions import decode_packed_index
    from mito_filter.emclarity.mrc_io import open_dense_mmap

    bases = _discover_angle_tomos(max_n=1)
    if not bases:
        pytest.skip("no real angle field present (SPEC §7 re-run)")
    d = REAL.parent
    mm = open_dense_mmap(d / f"{bases[0]}_angles.mrc", is_index=True)
    assert mm.dtype == np.dtype("<f4")  # fp32; 2592 > fp16 integer-exact 2048 would corrupt
    # A strided sub-sample keeps this fast but spans the whole volume.
    sub = np.rint(np.asarray(mm[::4, ::8, ::8])).astype(np.int64).ravel()
    assert sub.min() >= 1 and sub.max() <= 2592
    assert (sub == 0).sum() == 0  # emClarity stores an argmax at every voxel (no no-hit)
    angle_idx, ref_idx = decode_packed_index(sub)
    assert set(np.unique(ref_idx).tolist()).issubset({1, 2, 3})
    assert angle_idx.min() >= 1 and angle_idx.max() <= 864


def test_background_normals_are_random_real() -> None:
    """Dense normals at generic (mostly background) voxels are ~uniform on the sphere (SPEC §9.3).

    Peaks are sparse (~1e3 in 2.8e8 voxels), so a random voxel sample is dominated by background.
    The z-component of a uniform-on-sphere direction has mean 0 and std ``1/sqrt(3) ≈ 0.577``.
    Recovering that here is the empirical justification for CC-gating every dense-normal operation:
    off-peak the argmax orientation is meaningless noise.
    """
    from mito_filter.emclarity.angles_list import read_angles_list
    from mito_filter.emclarity.conventions import decode_index_volume_to_normal
    from mito_filter.emclarity.mrc_io import open_dense_mmap

    bases = _discover_angle_tomos(max_n=1)
    if not bases:
        pytest.skip("no real angle field present (SPEC §7 re-run)")
    d = REAL.parent
    mm = open_dense_mmap(d / f"{bases[0]}_angles.mrc", is_index=True)
    angles = read_angles_list(d / f"{bases[0]}_angles.list")
    nz, ny, nx = mm.shape
    rng = np.random.default_rng(0)
    zc = rng.integers(0, nz, 40000)
    yc = rng.integers(0, ny, 40000)
    xc = rng.integers(0, nx, 40000)
    packed = np.rint(np.asarray(mm[zc, yc, xc])).astype(np.int64)
    dec = decode_index_volume_to_normal(packed, angles)  # (N,3) raw (x,y,z)
    nz_comp = dec[:, 2]  # z-component of the raw (x,y,z) normal
    assert abs(float(nz_comp.mean())) < 0.05
    assert 0.45 < float(nz_comp.std()) < 0.62  # ~1/sqrt(3); not concentrated -> random


def test_effective_availability_ok_for_loaded_cc() -> None:
    path = _require_real()
    tomo = _ref(base="H99_2_100_1_bin5", convmap_path=path)
    reg = FieldRegistry()
    register_loaders(reg)
    register_derived(reg)
    assert reg.effective_availability("cc", tomo) is Availability.ON_DISK
    assert reg.effective_availability("snr", tomo) is Availability.GENERATABLE


# --- content-addressed on-disk cache -----------------------------------------------------------


class _CountingProvider(FieldProvider):
    """A cacheable scalar provider that counts materializations and keys on a temp source file."""

    produces = FieldSpec("toy", 1, np.dtype(np.float32), "toy scalar")

    def __init__(self, cache_dir: Path, source: Path, calls: List[int]) -> None:
        self._cache_dir = cache_dir
        self._source = source
        self._calls = calls

    def available(self, tomo: object) -> Availability:
        return Availability.GENERATABLE

    def materialize(self, tomo: object, reg: FieldRegistry, *, device: Device) -> DenseField:
        self._calls.append(1)
        grid = VoxelGrid((4, 5, 6), 12.5)
        data = np.arange(4 * 5 * 6, dtype=np.float32).reshape(4, 5, 6)
        return DenseField.from_array("toy", grid, data, channels=1, provider=self)

    def cache_path(self, tomo: object) -> Path:
        return self._cache_dir / f"{_tomo.base_of(tomo)}" / "toy.mrc"

    def cache_key_inputs(self, tomo: object) -> List[Path]:
        return [self._source]

    def cost_hint(self) -> Cost:
        return Cost(CostTier.DERIVE)


def test_ondisk_cache_roundtrip_and_staleness(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    source = tmp_path / "src.mrc"
    source.write_bytes(b"v1")
    tomo = _ref(base="toy", convmap_path=tmp_path / "toy_convmap.mrc")
    calls: List[int] = []

    # First resolve: materialize + write cache + manifest.
    reg1 = FieldRegistry()
    reg1.register(_CountingProvider(cache_dir, source, calls))
    f1 = reg1.resolve("toy", tomo, device=Device.CPU)
    assert len(calls) == 1
    cpath = cache_dir / "toy" / "toy.mrc"
    assert cpath.exists()
    assert (cache_dir / "toy" / "toy.mrc.manifest.json").exists()

    # Second resolve on a FRESH registry: served from cache, no new materialize.
    reg2 = FieldRegistry()
    reg2.register(_CountingProvider(cache_dir, source, calls))
    f2 = reg2.resolve("toy", tomo, device=Device.CPU)
    assert len(calls) == 1  # not re-materialized
    assert np.array_equal(_whole(f1), _whole(f2))

    # Change the source (new mtime/content) -> cache key changes -> rebuild.
    import os
    import time

    time.sleep(0.01)
    source.write_bytes(b"v2-longer")
    os.utime(source, None)
    reg3 = FieldRegistry()
    reg3.register(_CountingProvider(cache_dir, source, calls))
    reg3.resolve("toy", tomo, device=Device.CPU)
    assert len(calls) == 2  # re-materialized because the source changed
