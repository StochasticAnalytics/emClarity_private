"""Whole-search feature-cache builder — the Layer-2 producer of the tuner's inputs (DESIGN §6, §8).

The tuner (:mod:`mito_filter.optimize.tuner`) fits ONE theta over a
:class:`~mito_filter.optimize.dataset.SearchDataset` assembled from **per-tomogram cached feature
matrices**. This module builds those caches: for every tomogram of a template-matching round it
runs the :class:`~mito_filter.features.engine.FeatureEngine` once (touching the 558 MB convmap +
1.1 GB dense-angle volume) and writes the theta-independent :class:`FeatureMatrix` to
``<cache_dir>/<base>.features.parquet`` — exactly the flat layout
:meth:`SearchDataset.from_cache_dir` discovers.

The work is embarrassingly parallel across tomograms and RAM-heavy per tomogram (the angle ->
normal decode peaks at ~30 GB), so production runs fan it across the cluster: dispatch this
module's ``main`` with ``--index J --total N`` on each GPU/CPU slot (via
:class:`mito_filter.exec.cluster.SSHParallel`), and :func:`select_partition` hands slot ``J`` its
disjoint stride of the sorted basenames. Every partition writes to the SAME shared ``cache_dir``
(``/scratch`` is mounted identically on every host), so the union is the whole search. It is
resumable per-tomo: a tomogram whose parquet already exists is skipped unless ``--force``.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from ..datasets.base import TomogramRef
from ..datasets.emclarity_tm import EmclarityTMSource
from ..scan.pipeline import ScanPipeline
from .dataset import CACHE_SUFFIX

__all__ = [
    "select_partition",
    "cache_path_for",
    "build_partition",
    "main",
]


def select_partition(bases: Sequence[str], index: int, total: int) -> List[str]:
    """Return the disjoint stride of ``bases`` owned by 1-based slot ``index`` of ``total``.

    Slot ``J`` (1..N) owns ``sorted(bases)[J-1::N]``. Over ``J = 1..N`` the strides partition the
    whole set with no overlap and no gap, and each stride is roughly equal in size (a good static
    load balance when tomograms cost about the same). ``total <= 1`` returns every base.

    Args:
        bases: The tomogram basenames (any order; sorted internally for determinism).
        index: The 1-based slot index.
        total: The total number of slots.

    Returns:
        The basenames this slot should featurize.

    Raises:
        ValueError: If ``index`` is not in ``1..total``.
    """
    ordered = sorted(bases)
    if total <= 1:
        return ordered
    if not (1 <= index <= total):
        raise ValueError(f"index {index} out of range 1..{total}")
    return ordered[index - 1 :: total]


def cache_path_for(cache_dir: Path, base: str, *, suffix: str = CACHE_SUFFIX) -> Path:
    """Return the flat parquet cache path ``<cache_dir>/<base><suffix>`` for one tomogram."""
    return Path(cache_dir) / f"{base}{suffix}"


def _featurize_one(
    pipe: ScanPipeline,
    tomo: TomogramRef,
    out_path: Path,
    *,
    calibrate: str,
    force: bool,
) -> Dict[str, Any]:
    """Extract + cache one tomogram's feature matrix to ``out_path`` (flat SearchDataset layout).

    Args:
        pipe: The scan pipeline (its context carries the engine/registry/calibration).
        tomo: The tomogram to featurize.
        out_path: The destination ``<base>.features.parquet``.
        calibrate: Background-fit method (``"mad"`` / ``"truncated"`` / ``"none"``).
        force: Re-extract even when the parquet already exists.

    Returns:
        A per-tomo record: ``{base, n, status, seconds, columns}`` (``status`` in
        ``skipped|done|failed``, with ``error`` on failure).
    """
    t0 = time.time()
    if out_path.exists() and not force:
        return {"base": tomo.base, "status": "skipped", "n": None, "seconds": 0.0}
    ctx = pipe.ctx
    try:
        if calibrate and calibrate != "none":
            _calibrate(ctx, tomo, calibrate)
        grid = ctx.grid_for(tomo)
        cand = ctx.candidate_source.candidates(tomo, grid)
        fields = pipe.resolve_fields(tomo)
        block_ctx = ctx.block_ctx(grid, tomo)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        matrix = ctx.engine.run(cand, fields, block_ctx, cache_path=out_path, row_id_key=None)
    except Exception as exc:  # noqa: BLE001 - isolate one tomo's failure
        return {
            "base": tomo.base,
            "status": "failed",
            "n": None,
            "seconds": round(time.time() - t0, 1),
            "error": repr(exc),
        }
    return {
        "base": tomo.base,
        "status": "done",
        "n": int(matrix.n),
        "seconds": round(time.time() - t0, 1),
        "fields": sorted(fields),
    }


def _calibrate(ctx: Any, tomo: TomogramRef, method: str) -> None:
    """Fit + stash this tomogram's background stats into ``ctx.calibration`` (DESIGN §9.2)."""
    from ..fields.calibrate import BackgroundModel

    cc = ctx.field_registry.try_resolve("cc", tomo, device=ctx.device)
    if cc is None:
        return
    stats = BackgroundModel(method=method).fit_field(cc)
    cal = ctx.calibration
    cal[tomo.base] = {"bg_mean": stats.mean, "bg_std": stats.std}


def build_partition(
    data_dir: Path,
    config: Dict[str, Any],
    cache_dir: Path,
    *,
    index: int = 1,
    total: int = 1,
    force: bool = False,
    bases: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Featurize this slot's stride of a round into ``cache_dir`` (the tuner's inputs).

    Args:
        data_dir: The round's convmap directory.
        config: The loaded scan-config mapping (features/constraints/meta; the DENSE recipe here).
        cache_dir: Shared output directory for the ``<base>.features.parquet`` caches.
        index: 1-based slot index.
        total: Total slot count.
        force: Re-extract even when a parquet already exists.
        bases: Optional explicit basenames to featurize (else discover the round and stride it).

    Returns:
        A summary: ``{index, total, n_assigned, n_done, n_skipped, n_failed, records, ...}``.
    """
    from ..cli import _build_context  # local import: avoid a cli<->optimize import cycle at load

    source = EmclarityTMSource(Path(data_dir))
    search = source.discover()
    by_base = search.by_base()
    all_bases = list(by_base.keys()) if bases is None else list(bases)
    mine = select_partition(all_bases, index, total)

    convmap_shape = search.grid.shape if search.grid is not None else None
    ctx = _build_context(config, rec_dir=config.get("rec_dir"), convmap_shape=convmap_shape)
    pipe = ScanPipeline(ctx)
    calibrate = str(dict(config.get("meta", {})).get("calibrate", "none"))

    cache_dir = Path(cache_dir)
    records: List[Dict[str, Any]] = []
    for base in mine:
        out_path = cache_path_for(cache_dir, base)
        rec = _featurize_one(pipe, by_base[base], out_path, calibrate=calibrate, force=force)
        records.append(rec)
        print(
            f"[part {index}/{total}] {base}: {rec['status']} "
            f"n={rec.get('n')} t={rec.get('seconds')}s",
            flush=True,
        )
    status_of = [r["status"] for r in records]
    return {
        "index": index,
        "total": total,
        "cache_dir": str(cache_dir),
        "n_assigned": len(mine),
        "n_done": status_of.count("done"),
        "n_skipped": status_of.count("skipped"),
        "n_failed": status_of.count("failed"),
        "records": records,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the ``feature_cache`` CLI parser."""
    p = argparse.ArgumentParser(
        prog="mito-filter-feature-cache",
        description="Build per-tomogram feature-matrix parquet caches for a whole TM round.",
    )
    p.add_argument("--data-dir", type=Path, required=True, help="round convmap directory")
    p.add_argument("--config", type=Path, required=True, help="scan-config yaml (features/meta)")
    p.add_argument("--cache-dir", type=Path, required=True, help="shared parquet cache output dir")
    p.add_argument("--index", type=int, default=1, help="1-based partition index")
    p.add_argument("--total", type=int, default=1, help="total partition count")
    p.add_argument("--force", action="store_true", help="re-extract even if the parquet exists")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point: featurize this slot's stride and print a JSON summary line.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 unless a tomogram in this partition failed).
    """
    import json

    args = build_parser().parse_args(argv)
    with Path(args.config).open("r") as fh:
        config = dict(yaml.safe_load(fh) or {})
    summary = build_partition(
        args.data_dir,
        config,
        args.cache_dir,
        index=args.index,
        total=args.total,
        force=args.force,
    )
    print("SUMMARY " + json.dumps({k: v for k, v in summary.items() if k != "records"}))
    return 1 if summary["n_failed"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
