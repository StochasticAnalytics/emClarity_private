"""Integration: a csv + cc-only scan -> verdicts -> col26 debug csv + removal JSON (DESIGN §8).

Exercises the whole Layer-1 forward path on the CPU (no torch): a
:class:`~mito_filter.candidates.csv_source.CsvPeakSource` feeds candidates, the
:class:`~mito_filter.fields.loaders.ConvmapProvider` serves the dense ``cc`` field, the
:class:`~mito_filter.features.engine.FeatureEngine` samples per-candidate features from that
convmap, a :class:`~mito_filter.model.filter_model.FilterModel` decides keep/remove at ``tau``,
and :mod:`mito_filter.scan.writeback` mirrors the decision into col26 (row order preserved) and a
subtomo-id-keyed removal JSON.

Runs both on a **tiny synthetic tomogram** (always) and on the **real H99_2_100_1_bin5** convmap
(skipped when the dev data is absent), plus focused checks of ``config.py`` and ``manifest.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, cast

import numpy as np
import pytest

from mito_filter.candidates.csv_source import CsvPeakSource
from mito_filter.config import PipelineConfig, load_yaml
from mito_filter.constraints.base import Constraint, ParamDict, ParamSpec
from mito_filter.core.backend import Device
from mito_filter.emclarity.constants import CONVMAP_SHAPE, N_CSV_COLS, REMOVED_FLAG
from mito_filter.emclarity.mrc_io import write_dense_mrc
from mito_filter.features.engine import FeatureEngine
from mito_filter.features.extractor import FeatureMatrix
from mito_filter.features.local_stats import ScoreClusterDensity
from mito_filter.fields.loaders import ConvmapProvider, register_loaders
from mito_filter.fields.provider import FieldRegistry
from mito_filter.manifest import RunManifest
from mito_filter.model.filter_model import FilterModel
from mito_filter.scan.context import RunContext
from mito_filter.scan.pipeline import ScanPipeline

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mito_filter.datasets.base import TomogramRef

REAL_DIR = Path("/scratch/siracusa/full_enchilada_3/six_hours_round_4/convmap_wedgeType_2_bin5")
REAL_BASE = "H99_2_100_1_bin5"


@dataclass
class _Tomo:
    """A duck-typed tomogram reference satisfying both ``_tomo`` and ``CsvPeakSource``.

    Exposes ``base`` + ``convmap_path`` (for :mod:`mito_filter.fields._tomo`) and ``convmap_dir``
    (for :func:`mito_filter.candidates.csv_source._resolve_csv_path`, which resolves ``<base>.csv``
    from a ``base`` + a directory attribute).
    """

    base: str
    convmap_path: Path
    convmap_dir: Path
    rec_dir: Optional[Path] = None


class _ExtremeCcGoldIce(Constraint):
    """Flag the extreme-CC tail as gold/ice false positives (SPEC §1) — a deterministic constraint.

    Reads the convmap-sampled ``cc_local_max`` feature and returns FP score ``1`` for hits above a
    within-batch quantile (gold/ice = compact extreme-CC clusters), ``0`` otherwise. A pure feature
    function, so the whole pipeline is exercised with a data-independent, reproducible split.
    """

    name = "extreme_cc_gold_ice"
    needs_features = ("cc_local_max",)
    param_schema: Dict[str, ParamSpec] = {"quantile": ParamSpec(0.0, 1.0, 0.97)}

    def __init__(self, quantile: float = 0.97, **params: object) -> None:
        super().__init__(quantile=quantile, **params)

    def forward(self, feats: FeatureMatrix, theta: ParamDict) -> np.ndarray:
        z = np.asarray(feats.column("cc_local_max"), dtype=np.float64)
        default_q = self.params.get("quantile", 0.97)
        q = float(theta.get("quantile", default_q))  # type: ignore[arg-type]
        thr = float(np.nanquantile(z, q))
        return (z > thr).astype(np.float32)


# --------------------------------------------------------------------------- #
# Synthetic fixtures.                                                          #
# --------------------------------------------------------------------------- #
def _write_synthetic_tomo(dirpath: Path, base: str) -> _Tomo:
    """Write a tiny fp32 convmap + a matching 26-column csv, return the tomo reference."""
    nz, ny, nx = 8, 10, 12
    rng = np.random.default_rng(0)
    vol = (rng.standard_normal((nz, ny, nx)).astype(np.float32) * 0.2 + 3.3).astype(np.float32)
    convmap = dirpath / f"{base}_convmap.mrc"

    # 40 peaks on a spacing-2 interior grid so no two are within a radius-1 neighborhood
    # (guarantees each peak's +/-1 max reduce equals its own stamped CC, SPEC §3).
    grid_pts = [
        (z, y, x)
        for z in range(1, nz - 1, 2)
        for y in range(1, ny - 1, 2)
        for x in range(1, nx - 1, 2)
    ]
    n = 40
    pts = np.asarray(grid_pts[:n])
    zc, yc, xc = pts[:, 0], pts[:, 1], pts[:, 2]
    # Peak CC ascending and well above the ~3.3+/-0.2 background so each peak is a true local
    # max (its +/-1 reduce equals its own value); the top tail is the gold/ice-like extreme.
    cc = np.linspace(5.0, 12.0, n)
    # Stamp the CC value into the convmap at each peak voxel so the sampled feature matches.
    vol[zc, yc, xc] = cc.astype(np.float32)
    write_dense_mrc(convmap, vol)

    rows = np.zeros((n, N_CSV_COLS), dtype=np.float64)
    rows[:, 0] = cc  # col1  CC score
    rows[:, 1] = 5  # col2  sampling rate
    rows[:, 3] = np.arange(1, n + 1)  # col4  subtomo id
    rows[:, 4:9] = 1  # cols5-9 const flags
    rows[:, 10] = 5.0 * xc  # col11 X full px
    rows[:, 11] = 5.0 * yc  # col12 Y full px
    rows[:, 12] = 5.0 * zc  # col13 Z full px
    rows[:, 13:16] = 0.0  # cols14-16 euler
    rows[:, 16] = 1.0  # identity rotation matrix (col-major)
    rows[:, 20] = 1.0
    rows[:, 24] = 1.0  # col25 = normal_z = 1
    rows[:, 25] = 1  # col26 active
    np.savetxt(dirpath / f"{base}.csv", rows, fmt="%.6g")
    return _Tomo(base=base, convmap_path=convmap, convmap_dir=dirpath)


def _synthetic_context(tomo: _Tomo, *, cache_dir: Optional[Path] = None) -> RunContext:
    """Build a csv + cc RunContext over a synthetic tomo (ConvmapProvider with no shape check)."""
    reg = FieldRegistry()
    reg.register(ConvmapProvider(expected_shape=None))
    engine = FeatureEngine([ScoreClusterDensity(radius=1)])
    model = FilterModel([_ExtremeCcGoldIce(quantile=0.9)])  # flag the top ~10 %
    return RunContext.build(
        field_registry=reg,
        candidate_source=CsvPeakSource(),
        engine=engine,
        model=model,
        device=Device.CPU,
        tau=0.5,
        dataset="synthetic",
        cache_dir=cache_dir,
    )


# --------------------------------------------------------------------------- #
# Synthetic end-to-end (always runs).                                          #
# --------------------------------------------------------------------------- #
def test_scan_end_to_end_synthetic(tmp_path: Path) -> None:
    tomo = _write_synthetic_tomo(tmp_path, "synth_1_bin5")
    ctx = _synthetic_context(tomo, cache_dir=tmp_path / "cache")
    pipe = ScanPipeline(ctx)

    verdicts = pipe.run(tomo)

    # One verdict per csv row, decisions are booleans, and some (not all) are removed.
    assert verdicts.n == 40
    assert verdicts.keep.dtype == np.bool_
    assert 0 < verdicts.n_removed < verdicts.n
    # The extreme-CC tail is flagged: every removed hit sits above the kept ones' scores.
    removed_cc = np.sort(verdicts.subtomo_ids[verdicts.removed_mask])
    assert removed_cc[-1] == 40  # the largest-CC peak (subtomo id 40) is removed

    # cc_local_max was sampled from the convmap (not the csv attr) and matches the stamped CC.
    grid = ctx.grid_for(tomo)
    matrix = ctx.engine.run(
        ctx.candidate_source.candidates(cast("TomogramRef", tomo), grid),
        pipe.resolve_fields(tomo),
        ctx.block_ctx(grid, tomo),
        row_id_key=None,
    )
    csv_cc = np.loadtxt(tomo.convmap_dir / f"{tomo.base}.csv")[:, 0]
    assert np.allclose(matrix.column("cc_local_max"), csv_cc, atol=1e-2)

    # Writeback: col26 debug csv (row order preserved) + subtomo-id-keyed removal JSON.
    result = pipe.write(verdicts, tomo, out_dir=tmp_path / "out")
    assert result.debug_csv is not None and result.debug_csv.exists()
    assert result.removal_json is not None and result.removal_json.exists()
    assert result.n_removed == verdicts.n_removed

    dbg = np.loadtxt(result.debug_csv)
    assert dbg.shape == (40, N_CSV_COLS)
    # Only col26 changed; cols 1-25 are byte-identical to the source (row order preserved).
    src = np.loadtxt(tomo.convmap_dir / f"{tomo.base}.csv")
    assert np.array_equal(dbg[:, :25], src[:, :25])
    assert int(np.count_nonzero(dbg[:, 25] == REMOVED_FLAG)) == verdicts.n_removed

    import json

    payload = json.loads(result.removal_json.read_text())
    assert payload["key"] == "subtomo_id"
    assert len(payload["removals"]) == verdicts.n_removed
    got_ids = sorted(int(r["subtomo_id"]) for r in payload["removals"])
    assert got_ids == sorted(int(x) for x in verdicts.removed_subtomo_ids())
    assert all("euler" in r for r in payload["removals"])


def test_scan_resumable_reuses_feature_cache(tmp_path: Path) -> None:
    """A resumed run reuses the cached feature matrix (per-tomo) with identical verdicts."""
    tomo = _write_synthetic_tomo(tmp_path, "synth_2_bin5")
    ctx = _synthetic_context(tomo, cache_dir=tmp_path / "cache")
    pipe = ScanPipeline(ctx)

    v1 = pipe.run(tomo)
    cache = ctx.tomo_cache_dir(tomo)
    assert cache is not None and (cache / "features.parquet").exists()

    # Destroy the convmap DATA (keep only the 1024-byte header the grid read needs): a resumed
    # run must serve cached features and never re-sample the volume.
    with tomo.convmap_path.open("r+b") as fh:
        fh.truncate(1024)
    v2 = pipe.run(tomo, resume=True)
    assert np.array_equal(v1.keep, v2.keep)
    assert v1.n_removed == v2.n_removed


# --------------------------------------------------------------------------- #
# Real-data end-to-end (skips when the dev set is absent).                     #
# --------------------------------------------------------------------------- #
def _require_real() -> _Tomo:
    convmap = REAL_DIR / f"{REAL_BASE}_convmap.mrc"
    csv = REAL_DIR / f"{REAL_BASE}.csv"
    if not (convmap.exists() and csv.exists()):
        pytest.skip("real dev-set convmap/csv not present on this host")
    return _Tomo(base=REAL_BASE, convmap_path=convmap, convmap_dir=REAL_DIR)


def test_scan_end_to_end_real(tmp_path: Path) -> None:
    tomo = _require_real()
    reg = FieldRegistry()
    register_loaders(reg)  # ConvmapProvider asserts the real CONVMAP_SHAPE
    ctx = RunContext.build(
        field_registry=reg,
        candidate_source=CsvPeakSource(),
        engine=FeatureEngine([ScoreClusterDensity(radius=1)]),
        model=FilterModel([_ExtremeCcGoldIce(quantile=0.97)]),
        device=Device.CPU,
        tau=0.5,
        dataset="full_enchilada_3_4",
    )
    pipe = ScanPipeline(ctx)
    verdicts = pipe.run(tomo)

    n_csv = sum(1 for ln in (REAL_DIR / f"{REAL_BASE}.csv").read_text().splitlines() if ln.strip())
    assert verdicts.n == n_csv
    assert 0 < verdicts.n_removed < verdicts.n
    # The dense cc field was resolved and the grid matches the SPEC convmap shape.
    assert ctx.grid_for(tomo).shape == CONVMAP_SHAPE
    assert "cc" in verdicts.provenance["fields_resolved"]

    result = pipe.write(verdicts, tomo, out_dir=tmp_path / "out")
    assert result.debug_csv is not None and result.debug_csv.exists()
    dbg = np.loadtxt(result.debug_csv)
    assert dbg.shape == (n_csv, N_CSV_COLS)
    src = np.loadtxt(REAL_DIR / f"{REAL_BASE}.csv")
    assert np.array_equal(dbg[:, :25], src[:, :25])  # only col26 changed, row order preserved
    assert int(np.count_nonzero(dbg[:, 25] == REMOVED_FLAG)) == verdicts.n_removed


# --------------------------------------------------------------------------- #
# config.py and manifest.py focused checks.                                    #
# --------------------------------------------------------------------------- #
def test_pipeline_config_include_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MITO_TAU", "0.7")
    frag = tmp_path / "constraints.yaml"
    frag.write_text("- name: extreme_cc_gold_ice\n  quantile: 0.95\n")
    main = tmp_path / "round.yaml"
    main.write_text(
        "dataset: full_enchilada_3_4\n"
        "device: cpu\n"
        "tau: ${MITO_TAU}\n"
        "candidate_source: csv_peaks\n"
        "constraints: !include constraints.yaml\n"
        "writeback: {debug_csv: true, removal_json: true}\n"
    )
    cfg = PipelineConfig.load(main)
    assert cfg.dataset == "full_enchilada_3_4"
    assert cfg.tau == pytest.approx(0.7)  # env-expanded string coerced to float
    assert cfg.candidate_source.name == "csv_peaks"
    assert len(cfg.constraints) == 1  # !include spliced the fragment
    assert cfg.constraints[0].name == "extreme_cc_gold_ice"
    assert cfg.constraints[0].params["quantile"] == 0.95
    assert cfg.writeback.debug_csv is True
    # round-trip through to_dict/from_dict is stable.
    assert PipelineConfig.from_dict(cfg.to_dict()).tau == pytest.approx(0.7)


def test_raw_yaml_include_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MITO_DS", "ds42")
    (tmp_path / "inc.yaml").write_text("value: 3\n")
    (tmp_path / "top.yaml").write_text("dataset: $MITO_DS\nsub: !include inc.yaml\n")
    data = load_yaml(tmp_path / "top.yaml")
    assert data["dataset"] == "ds42"
    assert data["sub"] == {"value": 3}


def test_run_manifest_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "input.csv"
    src.write_text("1 2 3\n")
    cfg = PipelineConfig(dataset="ds", tau=0.5)
    manifest = RunManifest.build(
        config=cfg.to_dict(),
        dataset="ds",
        backend="cpu",
        input_paths=[src, tmp_path / "absent.mrc"],
        theta={"w": 1.0},
        tau=0.5,
    )
    assert manifest.mito_filter_git  # a rev string (or "unknown")
    assert manifest.emclarity_git
    assert manifest.inputs[0].exists and manifest.inputs[0].sha256 is not None
    assert manifest.inputs[1].exists is False and manifest.inputs[1].size == -1

    path = manifest.save(tmp_path / "run_manifest.json")
    assert path.exists()
    loaded = RunManifest.load(path)
    assert loaded.dataset == "ds"
    assert loaded.tau == 0.5
    assert loaded.inputs[0].sha256 == manifest.inputs[0].sha256
