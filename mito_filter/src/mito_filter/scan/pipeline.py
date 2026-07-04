"""ScanPipeline: the Layer-1 forward driver — one tomogram -> HitVerdicts (DESIGN §8).

For each tomogram the pipeline:

1. builds the convmap :class:`~mito_filter.core.grid.VoxelGrid` (from the header),
2. sources candidates (:class:`~mito_filter.candidates.source.CandidateSource`),
3. resolves **exactly** the dense fields the extractors need
   (:meth:`FieldRegistry.try_resolve` — a MISSING field is skipped and its feature goes neutral),
4. runs the :class:`~mito_filter.features.engine.FeatureEngine` once (cached to parquet),
5. forwards the cached matrix through the :class:`~mito_filter.model.filter_model.FilterModel` and
   thresholds at ``tau`` (:meth:`FilterModel.decide`),
6. packages the per-hit decisions into :class:`~mito_filter.scan.verdicts.HitVerdicts`.

It is a **pure forward** — no labels, no gradients — and **resumable per-tomo**: the expensive
volume-touching step (feature extraction) reuses the on-disk feature-matrix cache, so a re-run over
a tomo whose cache exists skips straight to the (cheap) model forward.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, cast

import numpy as np

from ..candidates.source import CandidateSet
from ..core.field import DenseField
from ..core.grid import VoxelGrid
from ..features.extractor import FeatureMatrix
from ..fields import _tomo
from .context import RunContext
from .verdicts import HitVerdicts
from .writeback import WritebackResult, writeback

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..datasets.base import TomogramRef

__all__ = ["ScanPipeline"]

_FEATURE_CACHE_NAME = "features.parquet"


class ScanPipeline:
    """Apply a fitted :class:`RunContext` to tomograms, forward-only (DESIGN §8).

    Args:
        ctx: The assembled run context (registry, source, engine, model, backend, tau, cache).

    Attributes:
        ctx: The run context.
    """

    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx

    # -- steps ------------------------------------------------------------------------
    def resolve_fields(self, tomo: object) -> Dict[str, DenseField]:
        """Resolve exactly the extractors' needed dense fields; skip the MISSING ones.

        Args:
            tomo: The tomogram reference.

        Returns:
            Field name -> :class:`DenseField` for every producible needed field. A field that is
            MISSING (or has no provider) is omitted, so its extractor emits a neutral column
            (DESIGN §5 mixed-availability).
        """
        fields: Dict[str, DenseField] = {}
        ref = cast("TomogramRef", tomo)
        for name in sorted(self.ctx.needed_fields):
            f = self.ctx.field_registry.try_resolve(name, ref, device=self.ctx.device)
            if f is not None:
                fields[name] = f
        return fields

    def _feature_cache_path(self, tomo: object) -> Optional[Path]:
        """Return the parquet feature-cache path for ``tomo`` (or None when caching is off)."""
        cache_dir = self.ctx.tomo_cache_dir(tomo)
        return (cache_dir / _FEATURE_CACHE_NAME) if cache_dir else None

    def feature_matrix(
        self,
        tomo: object,
        cand: CandidateSet,
        fields: Mapping[str, DenseField],
        grid: VoxelGrid,
        *,
        resume: bool = True,
    ) -> FeatureMatrix:
        """Extract (or load from cache) the per-candidate feature matrix.

        The matrix row ids are the **csv/geometry row indices** (``cand.row_ids``) so it aligns
        to the sibling files and to writeback. When ``resume`` and a cached parquet exists it is
        loaded (no volume touch); otherwise the engine runs once and writes the cache.

        Args:
            tomo: The tomogram reference.
            cand: The candidate set.
            fields: The resolved dense fields.
            grid: The convmap voxel grid.
            resume: Reuse the on-disk feature cache when present.

        Returns:
            The :class:`FeatureMatrix` (row-aligned to ``cand``).
        """
        cache_path = self._feature_cache_path(tomo)
        if resume and cache_path is not None and cache_path.exists():
            return self.ctx.engine.run_cached(cache_path)
        ctx = self.ctx.block_ctx(grid, tomo)
        return self.ctx.engine.run(cand, fields, ctx, cache_path=cache_path, row_id_key=None)

    def _provenance(
        self, matrix: FeatureMatrix, fields: Mapping[str, DenseField]
    ) -> Dict[str, Any]:
        """Assemble the per-verdict provenance record (model + fields + feature columns)."""
        resolved = sorted(fields)
        missing = sorted(set(self.ctx.needed_fields) - set(resolved))
        return {
            "dataset": self.ctx.dataset,
            "device": self.ctx.device.value,
            "tau": self.ctx.tau,
            "model_theta": dict(self.ctx.model.theta),
            "constraints": [c.name for c in self.ctx.model.constraints],
            "needed_features": list(self.ctx.needed_features),
            "feature_columns": list(matrix.columns),
            "fields_resolved": resolved,
            "fields_missing": missing,
        }

    # -- run ------------------------------------------------------------------------
    def run(self, tomo: object, *, resume: bool = True) -> HitVerdicts:
        """Score one tomogram and return its :class:`HitVerdicts` (pure forward).

        Args:
            tomo: The tomogram reference (exposes ``base`` / ``convmap_path``).
            resume: Reuse the on-disk feature cache when present.

        Returns:
            The per-hit verdicts for ``tomo``.
        """
        base = _tomo.base_of(tomo)
        grid = self.ctx.grid_for(tomo)
        cand = self.ctx.candidate_source.candidates(cast("TomogramRef", tomo), grid)

        # Resumable per-tomo: a cache hit reuses the feature matrix and skips BOTH the volume
        # sampling AND the field resolution (no convmap access beyond the header read for `grid`).
        cache_path = self._feature_cache_path(tomo)
        if resume and cache_path is not None and cache_path.exists():
            matrix = self.ctx.engine.run_cached(cache_path)
            fields: Dict[str, DenseField] = {}
        else:
            fields = self.resolve_fields(tomo)
            block_ctx = self.ctx.block_ctx(grid, tomo)
            matrix = self.ctx.engine.run(
                cand, fields, block_ctx, cache_path=cache_path, row_id_key=None
            )

        keep_prob = np.asarray(self.ctx.model.forward(matrix), dtype=np.float64).reshape(-1)
        keep = np.asarray(self.ctx.model.decide(matrix, self.ctx.tau), dtype=bool).reshape(-1)

        assert cand.row_ids is not None  # CandidateSet.__post_init__ guarantees this
        subtomo = (
            cand.get("subtomo_id")
            if "subtomo_id" in cand.attrs
            else np.asarray(cand.row_ids, dtype=np.int64)
        )
        euler = cand.get("euler") if "euler" in cand.attrs else None

        verdicts = HitVerdicts(
            tomo=base,
            row_ids=np.asarray(cand.row_ids, dtype=np.int64),
            subtomo_ids=np.asarray(subtomo, dtype=np.int64),
            keep_prob=keep_prob,
            keep=keep,
            tau=self.ctx.tau,
            euler=euler,
            dataset=self.ctx.dataset,
            provenance=self._provenance(matrix, fields),
        )
        self._write_summary(tomo, verdicts)
        return verdicts

    def run_many(self, tomos: List[object], *, resume: bool = True) -> List[HitVerdicts]:
        """Score several tomograms (resumable per-tomo).

        Args:
            tomos: The tomogram references.
            resume: Reuse each tomo's on-disk feature cache when present.

        Returns:
            The verdicts per tomogram, in input order.
        """
        return [self.run(t, resume=resume) for t in tomos]

    # -- writeback ------------------------------------------------------------------
    def write(
        self,
        verdicts: HitVerdicts,
        tomo: object,
        *,
        out_dir: Optional[Path] = None,
        **kwargs: Any,
    ) -> WritebackResult:
        """Emit writeback artifacts for a tomogram's verdicts (col26 csv + removal JSON).

        Args:
            verdicts: The verdicts to write.
            tomo: The tomogram reference (supplies the source csv path).
            out_dir: Output directory (defaults to the tomo cache dir, else the CWD).
            **kwargs: Forwarded to :func:`mito_filter.scan.writeback.writeback` (e.g.
                ``debug_csv``, ``removal_json``, ``mat_apply``, ``mat_path``, ``cycle``).

        Returns:
            The :class:`WritebackResult`.
        """
        if out_dir is None:
            out_dir = self.ctx.tomo_cache_dir(tomo) or Path.cwd()
        src_csv = self.ctx.csv_path_for(tomo)
        return writeback(verdicts, out_dir=Path(out_dir), src_csv=src_csv, **kwargs)

    def run_and_write(
        self, tomo: object, *, out_dir: Optional[Path] = None, resume: bool = True, **kwargs: Any
    ) -> WritebackResult:
        """Run one tomogram and immediately write its verdicts back.

        Args:
            tomo: The tomogram reference.
            out_dir: Output directory (defaults to the tomo cache dir, else the CWD).
            resume: Reuse the on-disk feature cache when present.
            **kwargs: Forwarded to :meth:`write` / the writeback driver.

        Returns:
            The :class:`WritebackResult`.
        """
        verdicts = self.run(tomo, resume=resume)
        return self.write(verdicts, tomo, out_dir=out_dir, **kwargs)

    # -- internal -------------------------------------------------------------------
    def _write_summary(self, tomo: object, verdicts: HitVerdicts) -> None:
        """Write a small per-tomo verdicts summary into the cache dir (best-effort provenance)."""
        cache_dir = self.ctx.tomo_cache_dir(tomo)
        if cache_dir is None:
            return
        import json

        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "verdicts_summary.json").write_text(
            json.dumps(verdicts.to_summary(), indent=2) + "\n"
        )
