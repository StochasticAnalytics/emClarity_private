"""Integration: the Phase-B DENSE-orientation scan path end-to-end (SPEC §5; DESIGN §6, §9.3).

The dense path swaps the sparse csv normals for a per-voxel normal field decoded from the packed
``<base>_angles.mrc`` argmax index (via ``<base>_angles.list``): the ``angle`` loader ->
``normal`` derive DAG materialises the field, and the CC-gated surface features
(``normal_source: field``) sample it at each candidate. This exercises the whole chain through
:class:`~mito_filter.scan.pipeline.ScanPipeline`:

* a **synthetic** small round with a real *decodable* angle volume + 864-row angles.list (always
  runs, offline) — asserts angle->normal resolves, the field-mode surface features are finite at
  gate-passing candidates, and a coherent-normal region reads coherence ~1; and
* a **real crop** of ``H99_2_100_1_bin5`` (skipped when the dev data is absent) — crops the real
  convmap + angle volume to a small box, keeps the csv peaks inside it, and runs the field-mode
  pipeline end-to-end on genuine bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple, cast

import numpy as np
import pytest

from mito_filter.candidates.csv_source import CsvPeakSource

# Import the feature + constraint plugin modules for their @register side effects (populate the
# FEATURE_REGISTRY / CONSTRAINT_REGISTRY so the names below resolve).
from mito_filter.constraints import curvature as _c_curvature  # noqa: F401
from mito_filter.constraints.curvature import SurfaceCoherenceConstraint
from mito_filter.core.backend import Device
from mito_filter.emclarity.angles_list import read_angles_list
from mito_filter.emclarity.constants import N_ANGLES, N_CSV_COLS
from mito_filter.emclarity.mrc_io import open_dense_mmap, read_header, write_dense_mrc
from mito_filter.features import curvature as _f_curvature  # noqa: F401
from mito_filter.features import isolation as _f_isolation  # noqa: F401
from mito_filter.features import local_stats as _f_local_stats  # noqa: F401
from mito_filter.features.engine import FEATURE_REGISTRY, FeatureEngine
from mito_filter.fields.calibrate import BackgroundModel
from mito_filter.fields.provider import Availability
from mito_filter.model.filter_model import FilterModel
from mito_filter.scan.context import RunContext, build_field_registry
from mito_filter.scan.pipeline import ScanPipeline

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mito_filter.datasets.base import TomogramRef

REAL_DIR = Path("/scratch/siracusa/full_enchilada_3/six_hours_round_4/convmap_wedgeType_2_bin5")
REAL_BASE = "H99_2_100_1_bin5"


@dataclass
class _Tomo:
    """Duck-typed tomogram ref satisfying ``_tomo`` (base/convmap_path) + csv resolution."""

    base: str
    convmap_path: Path
    convmap_dir: Path
    rec_dir: Optional[Path] = None


def _surface_engine(normal_source: str) -> FeatureEngine:
    """The three CC-gated surface extractors, parameterised by normal source."""
    return FeatureEngine(
        [
            FEATURE_REGISTRY.create(
                "normal_coherence", radius_A=800, normal_source=normal_source, gate_sigma=3.0
            ),
            FEATURE_REGISTRY.create(
                "surface_fit_residual", radius_A=800, normal_source=normal_source, gate_sigma=3.0
            ),
            FEATURE_REGISTRY.create(
                "principal_curvature", radius_A=800, normal_source=normal_source, gate_sigma=3.0
            ),
        ]
    )


def _angles_list_864() -> np.ndarray:
    """An 864x3 [phi, theta, psi-phi] grid; row 0 = [0,0,0] -> outward normal (z,y,x)=[1,0,0]."""
    rng = np.random.default_rng(0)
    ang = np.zeros((N_ANGLES, 3), dtype=np.float64)
    # Distinct non-degenerate rows for indices > 1 (so a non-coherent region reads varied normals).
    ang[1:, 0] = rng.uniform(0.0, 180.0, size=N_ANGLES - 1)  # phi
    ang[1:, 1] = rng.uniform(10.0, 80.0, size=N_ANGLES - 1)  # theta
    return ang


def _write_dense_round(dirpath: Path, base: str) -> Tuple[_Tomo, np.ndarray]:
    """Write a small convmap + decodable angle volume + angles.list + csv; return (tomo, peakvox).

    A coherent membrane patch: a block of elevated-CC voxels all carrying packed index 1 (angle
    row 0 -> normal (z,y,x)=[1,0,0]); the csv peaks sit on those voxels so the field-mode surface
    features see a coherent neighborhood. The background carries a varied (>1) packed index so a
    gated-out voxel would read an incoherent normal.
    """
    nz, ny, nx = 24, 30, 36
    rng = np.random.default_rng(1)
    vol = (rng.standard_normal((nz, ny, nx)).astype(np.float32) * 0.2 + 3.3).astype(np.float32)

    # A coherent patch of peaks on a z-plane (so 800 A @ 12.5 A/vox = 64 vox radius links them).
    zc = nz // 2
    pk = [(zc, y, x) for y in range(6, 24, 3) for x in range(6, 30, 3)]
    pk_arr = np.asarray(pk, dtype=np.int64)
    zz, yy, xx = pk_arr[:, 0], pk_arr[:, 1], pk_arr[:, 2]
    cc = np.linspace(6.0, 9.0, len(pk)).astype(np.float32)  # well above the ~3.3 background gate
    vol[zz, yy, xx] = cc
    write_dense_mrc(dirpath / f"{base}_convmap.mrc", vol)

    # Packed index volume: coherent (1) on the patch, varied (>1) elsewhere. int16 (index-safe).
    packed = rng.integers(2, 2593, size=(nz, ny, nx)).astype(np.int16)
    packed[zz, yy, xx] = 1
    write_dense_mrc(dirpath / f"{base}_angles.mrc", packed, is_index=True)
    np.savetxt(dirpath / f"{base}_angles.list", _angles_list_864(), fmt="%.4f")

    # A 26-column csv with one peak per patch voxel; identity rotation -> csv normal (z,y,x)=[1,0,0]
    # (matches the coherent dense normal, so auto and field agree on this synthetic patch).
    n = len(pk)
    rows = np.zeros((n, N_CSV_COLS), dtype=np.float64)
    rows[:, 0] = cc
    rows[:, 1] = 5
    rows[:, 3] = np.arange(1, n + 1)
    rows[:, 4:9] = 1
    rows[:, 10] = 5.0 * xx
    rows[:, 11] = 5.0 * yy
    rows[:, 12] = 5.0 * zz
    rows[:, 16] = 1.0
    rows[:, 20] = 1.0
    rows[:, 24] = 1.0  # col25 normal_z == 1
    rows[:, 25] = 1
    np.savetxt(dirpath / f"{base}.csv", rows, fmt="%.6g")
    return (
        _Tomo(base=base, convmap_path=dirpath / f"{base}_convmap.mrc", convmap_dir=dirpath),
        pk_arr,
    )


def _dense_context(tomo: _Tomo, normal_source: str) -> RunContext:
    reg = build_field_registry(convmap_shape=None)
    return RunContext.build(
        field_registry=reg,
        candidate_source=CsvPeakSource(),
        engine=_surface_engine(normal_source),
        model=FilterModel(
            [SurfaceCoherenceConstraint(coh_thresh=0.35, coh_sharpness=12.0, residual_weight=0.5)]
        ),
        device=Device.CPU,
        tau=0.5,
        dataset="synthetic_dense",
    )


# --------------------------------------------------------------------------- #
# Synthetic dense end-to-end (always runs).                                    #
# --------------------------------------------------------------------------- #
def test_dense_normal_field_resolves_and_decodes(tmp_path: Path) -> None:
    tomo, _pk = _write_dense_round(tmp_path, "synth_1_bin5")
    reg = build_field_registry(convmap_shape=None)
    tref = cast("TomogramRef", tomo)

    # angle loads from disk; normal is a derive whose dep (angle) exists -> GENERATABLE.
    assert reg.effective_availability("angle", tref) is Availability.ON_DISK
    assert reg.effective_availability("normal", tref) is Availability.GENERATABLE

    normal = reg.resolve("normal", tref, device=Device.CPU)
    assert normal.channels == 3
    assert normal.grid.shape == read_header(tomo.convmap_path).shape_zyx
    # A packed-index-1 voxel decodes to (z,y,x) = [1,0,0] (angles row 0 = [0,0,0]).
    s = np.asarray(normal.sample_at(np.array([[12.0, 12.0, 12.0]]), reduce="center", radius=0))
    # (12,12,12) is background (varied index); just assert a unit vector came back.
    assert np.isfinite(s).all() and abs(np.linalg.norm(s[0]) - 1.0) < 1e-3


def test_dense_scan_end_to_end_field_mode(tmp_path: Path) -> None:
    tomo, _pk = _write_dense_round(tmp_path, "synth_2_bin5")
    ctx = _dense_context(tomo, normal_source="field")
    pipe = ScanPipeline(ctx)

    verdicts = pipe.run(tomo, resume=False)

    n_csv = sum(
        1 for ln in (tomo.convmap_dir / f"{tomo.base}.csv").read_text().splitlines() if ln.strip()
    )
    assert verdicts.n == n_csv
    # The dense normal field was resolved through the angle->normal DAG.
    assert "normal" in verdicts.provenance["fields_resolved"]
    assert "cc" in verdicts.provenance["fields_resolved"]

    # Field-mode surface features are finite at the gate-passing coherent patch, and coherence is
    # high there (the patch shares packed index 1 -> a single dense normal -> coherence ~1).
    grid = ctx.grid_for(tomo)
    cand = CsvPeakSource().candidates(cast("TomogramRef", tomo), grid)
    fields = pipe.resolve_fields(tomo)
    matrix = ctx.engine.run(cand, fields, ctx.block_ctx(grid, tomo), row_id_key=None)
    coh = np.asarray(matrix.column("normal_coherence"))
    assert np.isfinite(coh).any()
    assert np.nanmedian(coh) > 0.9  # coherent patch

    result = pipe.write(verdicts, tomo, out_dir=tmp_path / "out")
    assert result.debug_csv is not None and result.debug_csv.exists()


def test_dense_vs_sparse_normal_source_same_candidates(tmp_path: Path) -> None:
    """Same csv candidates through auto (csv normal) and field (dense normal) both score cleanly."""
    tomo, _pk = _write_dense_round(tmp_path, "synth_3_bin5")
    ctx_field = _dense_context(tomo, normal_source="field")
    ctx_auto = _dense_context(tomo, normal_source="auto")
    g = ctx_field.grid_for(tomo)
    cand = CsvPeakSource().candidates(cast("TomogramRef", tomo), g)

    pipe_f = ScanPipeline(ctx_field)
    pipe_a = ScanPipeline(ctx_auto)
    mf = ctx_field.engine.run(
        cand, pipe_f.resolve_fields(tomo), ctx_field.block_ctx(g, tomo), row_id_key=None
    )
    ma = ctx_auto.engine.run(
        cand, pipe_a.resolve_fields(tomo), ctx_auto.block_ctx(g, tomo), row_id_key=None
    )
    # On this synthetic coherent patch the csv identity normal == the dense index-1 normal, so both
    # sources agree that the neighborhood is coherent.
    assert np.nanmedian(np.asarray(mf.column("normal_coherence"))) > 0.9
    assert np.nanmedian(np.asarray(ma.column("normal_coherence"))) > 0.9


# --------------------------------------------------------------------------- #
# Real crop dense end-to-end (skips when the dev set is absent).               #
# --------------------------------------------------------------------------- #
def _require_real_dense() -> Path:
    conv = REAL_DIR / f"{REAL_BASE}_convmap.mrc"
    ang = REAL_DIR / f"{REAL_BASE}_angles.mrc"
    lst = REAL_DIR / f"{REAL_BASE}_angles.list"
    csv = REAL_DIR / f"{REAL_BASE}.csv"
    if not all(p.exists() for p in (conv, ang, lst, csv)):
        pytest.skip("real dense dev-set (convmap+angles.mrc+angles.list+csv) not present")
    return REAL_DIR


def test_dense_scan_real_crop_end_to_end(tmp_path: Path) -> None:
    """Crop the real convmap + angle volume to a small box and run the field-mode dense pipeline."""
    _require_real_dense()
    # Crop box (z,y,x) — a modest sub-volume so the test stays fast and low-memory.
    z0, z1 = 120, 300
    y0, y1 = 300, 660
    x0, x1 = 150, 512

    conv_mm = open_dense_mmap(REAL_DIR / f"{REAL_BASE}_convmap.mrc")
    ang_mm = open_dense_mmap(REAL_DIR / f"{REAL_BASE}_angles.mrc", is_index=True)
    cc_crop = np.asarray(conv_mm[z0:z1, y0:y1, x0:x1], dtype=np.float32)
    ang_crop = np.rint(np.asarray(ang_mm[z0:z1, y0:y1, x0:x1])).astype(np.int16)

    base = "H99crop_1_bin5"
    write_dense_mrc(tmp_path / f"{base}_convmap.mrc", cc_crop)
    write_dense_mrc(tmp_path / f"{base}_angles.mrc", ang_crop, is_index=True)
    # The angles.list is tomo-independent (same 864 rows for every tomo) — copy the real one.
    ang_list = read_angles_list(REAL_DIR / f"{REAL_BASE}_angles.list")
    np.savetxt(tmp_path / f"{base}_angles.list", ang_list, fmt="%.6f")

    # Keep the real csv peaks that fall inside the crop; re-express positions in the crop frame.
    real_csv = np.loadtxt(REAL_DIR / f"{REAL_BASE}.csv")
    xf = real_csv[:, 10] / 5.0
    yf = real_csv[:, 11] / 5.0
    zf = real_csv[:, 12] / 5.0
    inside = (zf >= z0) & (zf < z1) & (yf >= y0) & (yf < y1) & (xf >= x0) & (xf < x1)
    sub = real_csv[inside].copy()
    if sub.shape[0] < 3:
        pytest.skip("crop box holds too few real peaks")
    sub[:, 10] = (xf[inside] - x0) * 5.0
    sub[:, 11] = (yf[inside] - y0) * 5.0
    sub[:, 12] = (zf[inside] - z0) * 5.0
    np.savetxt(tmp_path / f"{base}.csv", sub, fmt="%.6g")

    tomo = _Tomo(base=base, convmap_path=tmp_path / f"{base}_convmap.mrc", convmap_dir=tmp_path)
    reg = build_field_registry(convmap_shape=None)
    cc_field = reg.resolve("cc", cast("TomogramRef", tomo), device=Device.CPU)
    st = BackgroundModel(method="mad").fit_field(cc_field)
    ctx = RunContext.build(
        field_registry=reg,
        candidate_source=CsvPeakSource(),
        engine=_surface_engine("field"),
        model=FilterModel([SurfaceCoherenceConstraint()]),
        device=Device.CPU,
        tau=0.5,
        dataset="full_enchilada_3_4",
        calibration={base: {"bg_mean": st.mean, "bg_std": st.std}},
    )
    pipe = ScanPipeline(ctx)
    verdicts = pipe.run(tomo, resume=False)

    assert verdicts.n == sub.shape[0]
    assert "normal" in verdicts.provenance["fields_resolved"]
    # The field-mode surface features produced at least some finite (gate-passing) values on the
    # real crop — the dense normal decode + CC-gated fit ran end-to-end on genuine bytes.
    grid = ctx.grid_for(tomo)
    cand = CsvPeakSource().candidates(cast("TomogramRef", tomo), grid)
    matrix = ctx.engine.run(
        cand, pipe.resolve_fields(tomo), ctx.block_ctx(grid, tomo), row_id_key=None
    )
    assert np.isfinite(np.asarray(matrix.column("normal_coherence"))).any()
