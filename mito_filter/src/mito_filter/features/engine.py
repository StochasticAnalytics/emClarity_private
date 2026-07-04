"""The two-phase feature engine (DESIGN §6, §9.3).

Phase 1 (this module): run every registered :class:`~mito_filter.features.extractor.
FeatureExtractor` **once** over a tomogram's candidates + materialized dense fields, gather
per-candidate feature columns, and assemble a :class:`~mito_filter.features.extractor.
FeatureMatrix` cached to parquet. Phase 2 (the tuner, downstream) iterates on the cached
matrix and never re-reads a volume.

Dense volumes are touched **memory-safely**: the extractors gather at candidate points via
:meth:`DenseField.sample_at` (which indexes only the touched voxels — the 559 MB convmap is
never hot-loaded); halo-aware whole-volume streaming (``core/chunking``) is the *provider's*
job when it *generates* a derived field, not the extractor's. Features split
**theta-independent** (cached to parquet) vs **theta-dependent** (recomputed cheaply per
optimizer step, NOT cached) via :attr:`FeatureExtractor.theta_dependent`.

The module also hosts:

* :data:`FEATURE_REGISTRY` — the registry every extractor decorates itself into, so a
  pipeline is instantiated from YAML (``@FEATURE_REGISTRY.register("raw_score")``).
* small shared resolver helpers (:func:`resolve_scalar`, :func:`resolve_point_normals`,
  :func:`neutral_column`) used by every extractor to read a per-candidate quantity from a
  :class:`CandidateSet` attribute *or* a materialized :class:`DenseField`, and to emit a
  neutral column when a field is genuinely MISSING (DESIGN §5 mixed-availability rule).

Note:
    The DESIGN sketches ``run(tomo, ctx)`` over a ``RunContext`` / ``TomogramRef``; those
    live in ``scan/`` and ``datasets/`` (downstream, not yet built). This engine operates on
    the already-materialized inputs it actually needs — the ``CandidateSet``, the field
    mapping, and a :class:`~mito_filter.features.extractor.BlockCtx` — so it is fully
    testable on the CPU path today; the thin ``RunContext`` adapter is the integration
    agent's wiring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from numpy.typing import NDArray

from ..candidates.source import CandidateSet
from ..core.field import DenseField
from ..core.registry import Registry
from .extractor import BlockCtx, FeatureExtractor, FeatureMatrix

__all__ = [
    "FEATURE_REGISTRY",
    "FeatureEngine",
    "neutral_column",
    "resolve_scalar",
    "resolve_point_normals",
]

FEATURE_REGISTRY: Registry[FeatureExtractor] = Registry("feature-extractor")
"""Registry every concrete :class:`FeatureExtractor` registers into (YAML instantiation)."""


# --------------------------------------------------------------------------- #
# Shared resolver helpers (attr-or-field, with MISSING -> neutral).           #
# --------------------------------------------------------------------------- #
def neutral_column(n: int, fill: float = float("nan")) -> NDArray[np.float32]:
    """Return an ``(N,)`` fp32 neutral column (default all-NaN) for a MISSING feature.

    Args:
        n: Number of candidates.
        fill: The neutral fill value (``nan`` marks "not available"; ``0.0`` a soft neutral).

    Returns:
        Array ``(N,)`` filled with ``fill``.
    """
    return np.full(int(n), fill, dtype=np.float32)


def resolve_scalar(
    cand: CandidateSet,
    fields: Mapping[str, DenseField],
    field_name: str,
    *,
    attr: Optional[str] = None,
    reduce: str = "center",
    radius: int = 0,
) -> Optional[NDArray[np.float32]]:
    """Read a per-candidate scalar from a :class:`CandidateSet` attr or a dense field.

    Preference order: the candidate attribute ``attr`` (already per-hit, e.g. the csv ``cc``)
    if present, else sample the dense field ``field_name`` at the candidate coordinates, else
    ``None`` (the caller emits a neutral column).

    Args:
        cand: The candidates.
        fields: Materialized dense fields keyed by name.
        field_name: The dense-field name to sample if the attr is absent.
        attr: The candidate-attribute name to prefer (defaults to ``field_name``).
        reduce: Neighborhood reduce for the field sample (``center`` / ``max`` / ``mean``).
        radius: Neighborhood radius (voxels) for the field sample.

    Returns:
        An ``(N,)`` fp32 array, or ``None`` if neither source is available.
    """
    key = attr if attr is not None else field_name
    if key in cand.attrs:
        return np.asarray(cand.get(key), dtype=np.float32).reshape(-1)
    if field_name in fields:
        sampled = fields[field_name].sample_at(cand.coords_zyx, reduce=reduce, radius=radius)
        return np.asarray(sampled, dtype=np.float32).reshape(-1)
    return None


def resolve_point_normals(
    cand: CandidateSet,
    fields: Mapping[str, DenseField],
    *,
    attr: str = "normal",
    field_name: str = "normal",
    radius: int = 0,
) -> Optional[NDArray[np.float64]]:
    """Read per-candidate normals ``(N, 3)`` from a :class:`CandidateSet` attr or a field.

    The raw sign is preserved (SPEC §4 — the outward-vs-inward signal). Prefers the sparse
    candidate attribute, else samples the dense (CC-gated upstream) normal field.

    Args:
        cand: The candidates.
        fields: Materialized dense fields keyed by name.
        attr: Candidate normal-attribute name.
        field_name: Dense normal-field name to sample if the attr is absent.
        radius: Neighborhood radius (0 = nearest voxel) for the dense sample.

    Returns:
        An ``(N, 3)`` float64 array, or ``None`` if no normals source is available.
    """
    if attr in cand.attrs:
        return np.asarray(cand.get(attr), dtype=np.float64).reshape(-1, 3)
    if field_name in fields:
        reduce = "center" if radius == 0 else "mean"
        sampled = fields[field_name].sample_at(cand.coords_zyx, reduce=reduce, radius=radius)
        return np.asarray(sampled, dtype=np.float64).reshape(-1, 3)
    return None


# --------------------------------------------------------------------------- #
# The engine.                                                                  #
# --------------------------------------------------------------------------- #
class FeatureEngine:
    """Run extractors once over a tomogram's candidates -> cache a :class:`FeatureMatrix`.

    Args:
        extractors: The ordered extractors to run. Their :attr:`FeatureExtractor.produces`
            names must be unique across the whole set.

    Attributes:
        extractors: The extractor list.
    """

    def __init__(self, extractors: Sequence[FeatureExtractor]) -> None:
        self.extractors: List[FeatureExtractor] = list(extractors)
        seen: Dict[str, str] = {}
        for ex in self.extractors:
            for name in ex.produces:
                if name in seen:
                    raise ValueError(
                        f"duplicate feature column '{name}' "
                        f"({type(ex).__name__} vs {seen[name]})"
                    )
                seen[name] = type(ex).__name__

    @property
    def needed_fields(self) -> FrozenSet[str]:
        """Union of every extractor's :attr:`needs_fields` (drives ``FieldRegistry.plan``)."""
        out: set[str] = set()
        for ex in self.extractors:
            out.update(ex.needs_fields)
        return frozenset(out)

    @property
    def produced_columns(self) -> Tuple[str, ...]:
        """All feature column names produced, in extractor order."""
        cols: List[str] = []
        for ex in self.extractors:
            cols.extend(ex.produces)
        return tuple(cols)

    @property
    def theta_dependent_columns(self) -> Tuple[str, ...]:
        """Columns marked theta-dependent — recomputed per optimizer step, NOT cached."""
        cols: List[str] = []
        for ex in self.extractors:
            if ex.theta_dependent:
                cols.extend(ex.produces)
        return tuple(cols)

    @property
    def cached_columns(self) -> Tuple[str, ...]:
        """Theta-independent columns — the subset persisted to parquet."""
        cols: List[str] = []
        for ex in self.extractors:
            if not ex.theta_dependent:
                cols.extend(ex.produces)
        return tuple(cols)

    def _row_ids(self, cand: CandidateSet, row_id_key: Optional[str]) -> NDArray:
        """Choose the FeatureMatrix row ids: the given attr if present, else ``cand.row_ids``."""
        if row_id_key is not None and row_id_key in cand.attrs:
            return np.asarray(cand.get(row_id_key)).reshape(-1)
        assert cand.row_ids is not None  # set in CandidateSet.__post_init__
        return np.asarray(cand.row_ids).reshape(-1)

    def run(
        self,
        cand: CandidateSet,
        fields: Mapping[str, DenseField],
        ctx: BlockCtx,
        *,
        cache_path: Optional[Path] = None,
        include_theta_dependent: bool = True,
        row_id_key: Optional[str] = "subtomo_id",
    ) -> FeatureMatrix:
        """Extract all features for ``cand`` and assemble (and optionally cache) the matrix.

        Each extractor is called once. A theta-dependent extractor is skipped when
        ``include_theta_dependent`` is False (e.g. the tuner recomputes those itself). Only
        the theta-independent (:attr:`cached_columns`) subset is written to ``cache_path``.

        Args:
            cand: The candidates to featurize.
            fields: The materialized dense fields keyed by name (a superset of
                :attr:`needed_fields`; a genuinely MISSING field is simply absent and its
                extractor emits a neutral column).
            ctx: The block/backend context (grid, backend, per-tomo calibration meta).
            cache_path: If given, write the theta-independent columns to this parquet file.
            include_theta_dependent: Include theta-dependent columns in the returned matrix.
            row_id_key: Candidate attribute to use as the matrix row ids (falls back to
                ``cand.row_ids`` when absent). Defaults to ``"subtomo_id"``.

        Returns:
            The assembled :class:`FeatureMatrix` (row-aligned to ``cand``).

        Raises:
            ValueError: If an extractor returns a column of the wrong length or omits one of
                its declared :attr:`produces` names.
        """
        n = cand.n
        columns: Dict[str, NDArray[np.float32]] = {}
        for ex in self.extractors:
            if ex.theta_dependent and not include_theta_dependent:
                continue
            produced = ex.extract(cand, fields, ctx)
            for name in ex.produces:
                if name not in produced:
                    raise ValueError(f"{type(ex).__name__} declared '{name}' but did not return it")
                arr = np.asarray(produced[name], dtype=np.float32).reshape(-1)
                if arr.shape[0] != n:
                    raise ValueError(
                        f"{type(ex).__name__} column '{name}' length {arr.shape[0]} != N {n}"
                    )
                columns[name] = arr

        row_ids = self._row_ids(cand, row_id_key)
        matrix = FeatureMatrix.from_columns(columns, row_ids)

        if cache_path is not None:
            cached = tuple(c for c in self.cached_columns if c in columns)
            cache_cols = {c: columns[c] for c in cached}
            FeatureMatrix.from_columns(cache_cols, row_ids).to_parquet(Path(cache_path))
        return matrix

    def run_cached(self, cache_path: Path) -> FeatureMatrix:
        """Load the cached (theta-independent) :class:`FeatureMatrix` from parquet.

        Args:
            cache_path: Path previously written by :meth:`run` (its ``cache_path``).

        Returns:
            The cached :class:`FeatureMatrix` (theta-dependent columns are not present and
            are recomputed on demand).
        """
        return FeatureMatrix.from_parquet(Path(cache_path))
