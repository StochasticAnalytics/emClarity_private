"""Command-line entry point for mito_filter.

Subcommands ``scan | optimize | gen-field | writeback | validate`` (DESIGN §2). ``scan`` is wired
end-to-end here: it loads a config, discovers the round's tomograms
(:class:`~mito_filter.datasets.emclarity_tm.EmclarityTMSource`), assembles the Phase-A
:class:`~mito_filter.scan.context.RunContext` (field providers + feature extractors + the
constraint :class:`~mito_filter.model.filter_model.FilterModel`), and maps a resumable per-tomo
scan (calibrate background -> forward filter -> col26 debug csv + removal JSON) over them via
:class:`~mito_filter.exec.runner.TomogramRunner`. The remaining subcommands dispatch to their
module when present, else exit with a clear not-yet-implemented message.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import yaml

from .candidates.csv_source import CsvPeakSource
from .config import ComponentSpec, WritebackConfig

# Import the concrete plugin modules for their side effects: each @register decorator populates
# FEATURE_REGISTRY / CONSTRAINT_REGISTRY so a config can name them (the package __init__s empty).
from .constraints import curvature as _c_curvature  # noqa: F401
from .constraints import gold_ice as _c_gold_ice  # noqa: F401
from .constraints import isolation as _c_isolation  # noqa: F401
from .constraints import membrane as _c_membrane  # noqa: F401
from .constraints import template_prior as _c_template_prior  # noqa: F401
from .datasets.base import TomogramRef
from .datasets.emclarity_tm import EmclarityTMSource
from .exec.runner import TomogramRunner
from .features import curvature as _f_curvature  # noqa: F401
from .features import isolation as _f_isolation  # noqa: F401
from .features import local_stats as _f_local_stats  # noqa: F401
from .features import membrane as _f_membrane  # noqa: F401
from .features import priors as _f_priors  # noqa: F401
from .features.engine import FEATURE_REGISTRY, FeatureEngine
from .features.extractor import FeatureExtractor
from .fields.calibrate import BackgroundModel
from .model.filter_model import Combiner, FilterModel
from .scan.context import (
    RunContext,
    build_field_registry,
    constraints_from_specs,
    device_from_string,
)
from .scan.pipeline import ScanPipeline

__all__ = ["main", "build_parser"]

# Phase-A default extractor set (DESIGN §10.3) when a config lists no `features` stanzas.
_DEFAULT_FEATURES: Tuple[str, ...] = (
    "score_cluster_density",
    "blobness",
    "gold_fiducial_proximity",
    "normal_coherence",
    "surface_fit_residual",
    "principal_curvature",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with the subcommands.

    Returns:
        The configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="mito-filter", description="Cryo-ET TM false-positive filter"
    )
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="apply a fitted filter and write verdicts back")
    scan.add_argument("--config", type=Path, help="pipeline / fitted-filter config yaml")
    scan.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="convmap directory of the round to scan (overrides the config's dataset)",
    )
    scan.add_argument(
        "--work-dir",
        type=Path,
        default=Path("."),
        help="run directory for done sentinels / outputs (default: cwd)",
    )
    scan.add_argument("--limit", type=int, default=None, help="scan at most N tomograms (debug)")
    scan.add_argument("--jobs", type=int, default=1, help="local worker count (joblib)")
    scan.add_argument(
        "--force", action="store_true", help="ignore done sentinels / cache and re-run every tomo"
    )
    scan.add_argument(
        "--dry-run", action="store_true", help="discover + report only; write nothing"
    )

    for name, help_text in (
        ("optimize", "tune the filter jointly over a search"),
        ("gen-field", "materialize a dense field for tomograms"),
        ("writeback", "write verdicts to the .mat / csv col26"),
        ("validate", "run the downstream-quality validation loop"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--config", type=Path, help="config yaml")
    return parser


def _load_config(path: Optional[Path]) -> Dict[str, Any]:
    """Load a config yaml into a plain dict (empty dict if no path / empty file).

    Args:
        path: Path to the yaml config, or None.

    Returns:
        The parsed mapping (empty if absent).
    """
    if path is None:
        return {}
    with Path(path).open("r") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data)


def _resolve_convmap_dir(config: Dict[str, Any], data_dir: Optional[Path]) -> Optional[Path]:
    """Resolve the round's convmap directory from an explicit arg or the config.

    Resolution order: ``--data-dir`` arg > config ``data_dir`` > config ``dataset`` (a path string
    or a ``{convmap_dir: ...}`` mapping).

    Args:
        config: The loaded config mapping.
        data_dir: The explicit ``--data-dir`` override, or None.

    Returns:
        The resolved convmap directory, or None if it could not be determined.
    """
    if data_dir is not None:
        return Path(data_dir)
    raw = config.get("data_dir")
    if isinstance(raw, str):
        return Path(raw)
    dataset = config.get("dataset")
    if isinstance(dataset, str):
        return Path(dataset)
    if isinstance(dataset, dict):
        cd = dataset.get("convmap_dir") or dataset.get("data_dir")
        if isinstance(cd, str):
            return Path(cd)
    return None


def _build_extractors(config: Dict[str, Any]) -> List[FeatureExtractor]:
    """Instantiate the feature extractors from the config's ``features`` stanzas.

    Each stanza is a ``FEATURE_REGISTRY`` name (bare string or ``{name, **params}``); when
    ``features`` is absent the Phase-A default set (:data:`_DEFAULT_FEATURES`) is used.

    Args:
        config: The loaded config mapping.

    Returns:
        The instantiated extractors, in stanza order.
    """
    specs = config.get("features") or []
    if not specs:
        return [FEATURE_REGISTRY.create(n) for n in _DEFAULT_FEATURES]
    out: List[FeatureExtractor] = []
    for raw in specs:
        spec = ComponentSpec.from_obj(raw)
        out.append(FEATURE_REGISTRY.create(spec.name, **dict(spec.params)))
    return out


def _build_candidate_source(config: Dict[str, Any], reg: Any, device: Any) -> Any:
    """Instantiate the candidate source from the config's ``candidate_source`` stanza.

    ``csv_peaks`` (default) -> :class:`CsvPeakSource` over the sparse 26-column csv.
    ``dense_peaks`` -> :class:`~mito_filter.candidates.dense_source.DenseFieldPeakSource`,
    re-detecting local maxima from a dense field (``field_name``, default ``cc``) with the
    oriented-erase-cylinder NMS de-dup; it is handed the built :class:`FieldRegistry` + device so
    :meth:`DenseFieldPeakSource.candidates` can resolve the detection field (and the optional
    ``normal_field_name`` that orients the cylinder).

    Args:
        config: The loaded config mapping.
        reg: The already-built field registry (passed to a dense source).
        device: The compute device (passed to a dense source).

    Returns:
        The instantiated :class:`~mito_filter.candidates.source.CandidateSource`.

    Raises:
        ValueError: If the stanza names an unknown candidate source.
    """
    raw = config.get("candidate_source")
    spec = ComponentSpec.from_obj(raw) if raw is not None else ComponentSpec("csv_peaks", {})
    params = dict(spec.params)
    if spec.name == "csv_peaks":
        return CsvPeakSource(**params)
    if spec.name == "dense_peaks":
        from .candidates.dense_source import DenseFieldPeakSource

        return DenseFieldPeakSource(registry=reg, device=device, **params)
    raise ValueError(
        f"unknown candidate_source '{spec.name}' (expected 'csv_peaks' or 'dense_peaks')"
    )


def _build_combiner(config: Dict[str, Any], constraints: List[Any]) -> Combiner:
    """Build the fusion head from the config's ``combiner`` block (DESIGN §7).

    ``combiner: {bias, weight, weights: {<constraint>: w}}`` — ``weight`` is the uniform initial
    fusion weight (negative: a larger FP score lowers keep-probability), ``bias`` the global
    keep/reject offset, and ``weights`` optional per-constraint overrides. Defaults reproduce the
    uniform-weight head.

    Args:
        config: The loaded config mapping.
        constraints: The instantiated constraints (define the combiner column order).

    Returns:
        The configured :class:`Combiner`.
    """
    comb = dict(config.get("combiner", {}))
    names = [c.name for c in constraints]
    combiner = Combiner.default(
        names, weight=float(comb.get("weight", -1.0)), bias=float(comb.get("bias", 0.0))
    )
    overrides = dict(comb.get("weights", {}))
    for j, nm in enumerate(names):
        if nm in overrides:
            combiner.weights[j] = float(overrides[nm])
    return combiner


def _build_context(
    config: Dict[str, Any],
    *,
    rec_dir: Optional[str],
    convmap_shape: Optional[Tuple[int, int, int]],
) -> RunContext:
    """Assemble the Phase-A :class:`RunContext` from a config mapping (DESIGN §8, §10.3).

    Wires the standard field providers, the configured (or default) feature extractors, a
    :class:`CsvPeakSource`, and a :class:`FilterModel` over the configured constraints.

    Args:
        config: The loaded config mapping.
        rec_dir: Optional ``rec`` directory override (else the provider default).
        convmap_shape: The discovered convmap header shape the ``cc`` loader validates against
            (so any round loads; None skips the check).

    Returns:
        The assembled run context (CPU backend unless the config selects otherwise).
    """
    device = device_from_string(str(config.get("device", "cpu")))
    reg = build_field_registry(
        rec_dir=Path(rec_dir) if rec_dir else None, convmap_shape=convmap_shape
    )
    engine = FeatureEngine(_build_extractors(config))
    constraint_specs = [ComponentSpec.from_obj(c) for c in config.get("constraints", [])]
    constraints = constraints_from_specs(constraint_specs)
    model = FilterModel(constraints, _build_combiner(config, constraints))
    theta = config.get("theta") or {}
    if theta:
        model.set_theta({str(k): float(v) for k, v in dict(theta).items()})
    cache = config.get("cache_dir")
    source = _build_candidate_source(config, reg, device)
    return RunContext.build(
        field_registry=reg,
        candidate_source=source,
        engine=engine,
        model=model,
        device=device,
        tau=float(config.get("tau", 0.5)),
        dataset=str(config.get("dataset", "")),
        cache_dir=Path(cache) if cache else None,
        meta=dict(config.get("meta", {})),
    )


def _calibrate_tomo(ctx: RunContext, tomo: TomogramRef, method: str) -> None:
    """Fit and stash this tomogram's background stats into ``ctx.calibration`` (DESIGN §9.2).

    Resolves the ``cc`` field, fits a robust :class:`BackgroundModel`, and records
    ``{bg_mean, bg_std}`` under the tomo basename so every :class:`BlockCtx` z-scores against
    the tomo's own background. A no-op when the ``cc`` field cannot be resolved.

    Args:
        ctx: The run context (its ``calibration`` dict is mutated in place).
        tomo: The tomogram to calibrate.
        method: The :class:`BackgroundModel` estimator (``"mad"`` / ``"truncated"``).
    """
    cc = ctx.field_registry.try_resolve("cc", tomo, device=ctx.device)
    if cc is None:
        return
    stats = BackgroundModel(method=method).fit_field(cc)
    cal = cast(Dict[str, Dict[str, float]], ctx.calibration)
    cal[tomo.base] = {"bg_mean": stats.mean, "bg_std": stats.std}


def _cmd_scan(args: argparse.Namespace) -> int:
    """Run the ``scan`` subcommand: build the Phase-A pipeline and filter each tomogram.

    Discovers the round, assembles the :class:`RunContext` (fields + features + model) from the
    config, then per tomogram calibrates the background, runs the forward filter, and writes the
    col26 debug csv + subtomo-id-keyed removal JSON (DESIGN §8, §9.1). Resumable per-tomo via the
    :class:`TomogramRunner` done sentinels.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Process exit code (0 on success, 2 on a configuration error, 1 on tomo failures).
    """
    config = _load_config(args.config)
    convmap_dir = _resolve_convmap_dir(config, args.data_dir)
    if convmap_dir is None:
        print(
            "error: no convmap directory. Pass --data-dir or set 'data_dir'/'dataset' in --config."
        )
        return 2
    if not convmap_dir.is_dir():
        print(f"error: convmap directory does not exist: {convmap_dir}")
        return 2

    rec_dir = config.get("rec_dir")
    source = EmclarityTMSource(convmap_dir, rec_dir=Path(rec_dir) if rec_dir else None)
    search = source.discover()
    tomos: List[TomogramRef] = list(search.tomograms)
    if args.limit is not None:
        tomos = tomos[: args.limit]
    print(f"scan: discovered {search.n} tomograms in {convmap_dir} (running {len(tomos)})")

    if args.dry_run:
        incomplete = [t.base for t in tomos if not t.is_complete()]
        if incomplete:
            print(f"  warning: {len(incomplete)} incomplete seven-file set(s): {incomplete[:5]}")
        for t in tomos[:10]:
            print(f"  {t.base}: grid={t.grid.shape} rec={t.rec_path}")
        print("  dry-run: no job executed.")
        return 0

    from .exec.cluster import LocalProcess

    convmap_shape = search.grid.shape if search.grid is not None else None
    ctx = _build_context(config, rec_dir=rec_dir, convmap_shape=convmap_shape)
    pipeline = ScanPipeline(ctx)
    wb = WritebackConfig.from_dict(config.get("writeback"))
    out_dir = Path(wb.out_dir) if wb.out_dir else (Path(args.work_dir) / "scan_out")
    calibrate = str(dict(config.get("meta", {})).get("calibrate", "none"))
    resume = not args.force

    def _scan_job(tomo: TomogramRef) -> Tuple[int, int]:
        if calibrate and calibrate != "none":
            _calibrate_tomo(ctx, tomo, calibrate)
        verdicts = pipeline.run(tomo, resume=resume)
        pipeline.write(
            verdicts,
            tomo,
            out_dir=out_dir,
            debug_csv=wb.debug_csv,
            removal_json=wb.removal_json,
            removal_table=wb.removal_table,
            mat_apply=wb.mat_apply,
            mat_path=Path(wb.mat_path) if wb.mat_path else None,
            cycle=wb.cycle,
        )
        return verdicts.n, verdicts.n_removed

    job: Callable[[TomogramRef], Tuple[int, int]] = _scan_job
    runner = TomogramRunner(args.work_dir, executor=LocalProcess(n_jobs=args.jobs))
    report = runner.run(tomos, job, force=args.force)

    total = sum(v.value[0] for v in report.results if v.value is not None)
    removed = sum(v.value[1] for v in report.results if v.value is not None)
    print(f"scan: done={report.n_done} skipped={report.n_skipped} failed={report.n_failed}")
    print(f"scan: candidates={total} flagged_fp={removed} -> outputs in {out_dir}")
    if report.n_failed:
        for f in report.failures[:10]:
            print(f"  FAILED {f.base}: {f.error}")
        return 1
    return 0


def _dispatch_stub(command: str, args: argparse.Namespace) -> int:
    """Dispatch a not-yet-wired subcommand to its module, else print a clear message.

    Args:
        command: The subcommand name (``optimize`` / ``gen-field`` / ``writeback`` / ``validate``).
        args: Parsed CLI arguments.

    Returns:
        The module's exit code, or 2 with a not-implemented message.
    """
    module_name = {
        "optimize": "mito_filter.optimize.tuner",
        "gen-field": "mito_filter.fields.provider",
        "writeback": "mito_filter.scan.writeback",
        "validate": "mito_filter.validate.holdout",
    }.get(command)
    if module_name is not None:
        try:
            import importlib

            mod = importlib.import_module(module_name)
        except ImportError:
            mod = None
        entry = getattr(mod, "main", None) if mod is not None else None
        if callable(entry):
            code = entry(args)
            return int(code) if code is not None else 0
    print(f"subcommand '{command}' is not yet implemented (its driver module is a downstream stub)")
    return 2


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    command = getattr(args, "command", None)
    if not command:
        parser.print_help()
        return 1
    if command == "scan":
        return _cmd_scan(args)
    return _dispatch_stub(command, args)
