"""SearchDataset: the whole-search unit the tuner fits over (DESIGN §8, Layer 2).

Feature extraction touches the 662x942x448 volumes ONCE per tomogram and caches a
:class:`~mito_filter.features.extractor.FeatureMatrix` to parquet (few MB/tomo, DESIGN §6).
:class:`SearchDataset` assembles those cached per-tomo matrices for **every** tomogram of a
template-matching round into ONE row-concatenated matrix, remembering which tomogram each row
came from (``tomo_ids``) so the objective can normalise/average *per convmap* while still
fitting a single global theta "jointly across all convmaps".

The class never re-reads a dense volume: it consumes the parquet caches produced by
:meth:`FeatureEngine.run`'s ``cache_path`` and loaded via
:meth:`FeatureMatrix.from_parquet`. A tomogram with no cache is simply skipped (with its base
recorded in :attr:`missing`) so a partially-featurised search is still tunable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from numpy.typing import NDArray

from ..features.extractor import FeatureMatrix

__all__ = ["SearchDataset"]

CACHE_SUFFIX: str = ".features.parquet"
"""Default cache filename suffix (``<base>.features.parquet``) under a search cache dir."""


def _concat_matrices(
    bases: Sequence[str], mats: Sequence[FeatureMatrix]
) -> Tuple[FeatureMatrix, NDArray[np.int64]]:
    """Row-concatenate per-tomo matrices with a shared column order.

    Args:
        bases: The tomogram basenames (one per matrix), defining the tomo index order.
        mats: The per-tomo :class:`FeatureMatrix` objects (any row count, same columns).

    Returns:
        A tuple ``(combined, tomo_ids)`` where ``combined`` stacks every tomo's rows in
        ``bases`` order and ``tomo_ids[i]`` is the index into ``bases`` of row ``i``.

    Raises:
        ValueError: If two matrices carry different feature-column *sets*.
    """
    if not mats:
        empty = FeatureMatrix(np.zeros((0, 0), dtype=np.float32), [], np.zeros(0, dtype=np.int64))
        return empty, np.zeros(0, dtype=np.int64)

    columns = list(mats[0].columns)
    colset = set(columns)
    for base, m in zip(bases, mats):
        if set(m.columns) != colset:
            missing = colset.symmetric_difference(m.columns)
            raise ValueError(
                f"tomo '{base}' feature columns differ from the search "
                f"(mismatched: {sorted(missing)})"
            )

    blocks: List[NDArray[np.float32]] = []
    row_ids: List[NDArray] = []
    tomo_ids: List[NDArray[np.int64]] = []
    for idx, m in enumerate(mats):
        # Reorder every tomo's columns to the canonical order before stacking.
        block = m.select(tuple(columns)) if m.columns != columns else m.matrix
        blocks.append(np.asarray(block, dtype=np.float32).reshape(m.n, len(columns)))
        row_ids.append(np.asarray(m.row_ids).reshape(-1))
        tomo_ids.append(np.full(m.n, idx, dtype=np.int64))

    matrix = np.concatenate(blocks, axis=0) if blocks else np.zeros((0, len(columns)), np.float32)
    all_row_ids = np.concatenate(row_ids) if row_ids else np.zeros(0, dtype=np.int64)
    combined = FeatureMatrix(matrix, columns, all_row_ids)
    return combined, np.concatenate(tomo_ids) if tomo_ids else np.zeros(0, dtype=np.int64)


@dataclass
class SearchDataset:
    """The row-concatenated cached feature matrix for one whole search / round.

    Args:
        matrix: The combined ``(N_total, F)`` :class:`FeatureMatrix` (all tomos stacked).
        tomo_ids: ``(N_total,)`` int index into :attr:`bases` for every row.
        bases: The tomogram basenames, in tomo-index order.
        missing: Bases whose cache was requested but absent (skipped, informational).
        meta: Free-form provenance (cache dir, counts, ...).

    Attributes:
        matrix: The combined feature matrix.
        tomo_ids: Per-row tomogram index.
        bases: Tomogram basenames.
        missing: Skipped bases.
        meta: Provenance metadata.
    """

    matrix: FeatureMatrix
    tomo_ids: NDArray[np.int64]
    bases: List[str]
    missing: List[str] = field(default_factory=list)
    meta: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tomo_ids = np.asarray(self.tomo_ids, dtype=np.int64).reshape(-1)
        self.bases = list(self.bases)
        if self.tomo_ids.shape[0] != self.matrix.n:
            raise ValueError(
                f"tomo_ids length {self.tomo_ids.shape[0]} != matrix rows {self.matrix.n}"
            )
        if self.matrix.n and self.bases and int(self.tomo_ids.max()) >= len(self.bases):
            raise ValueError("tomo_ids reference a base index beyond `bases`")

    # -- sizes ----------------------------------------------------------------------
    @property
    def n(self) -> int:
        """Total candidate rows across every tomogram."""
        return self.matrix.n

    @property
    def n_tomos(self) -> int:
        """Number of tomograms contributing rows."""
        return len(self.bases)

    @property
    def columns(self) -> List[str]:
        """The feature column names (shared across tomograms)."""
        return list(self.matrix.columns)

    def column(self, name: str) -> NDArray:
        """Return the combined ``(N_total,)`` values of feature column ``name``."""
        return self.matrix.column(name)

    def __contains__(self, name: object) -> bool:
        return name in self.matrix

    # -- per-tomo grouping ----------------------------------------------------------
    def group_indices(self) -> List[NDArray[np.int64]]:
        """Return, per tomogram (in :attr:`bases` order), the row indices it owns.

        Returns:
            A list of length :attr:`n_tomos`; entry ``t`` is the ``(n_t,)`` int array of
            rows in the combined matrix belonging to tomogram ``t``.
        """
        return [np.nonzero(self.tomo_ids == t)[0] for t in range(self.n_tomos)]

    def per_tomo(self) -> Iterator[Tuple[str, FeatureMatrix]]:
        """Iterate ``(base, FeatureMatrix)`` slices, one per tomogram (bases order)."""
        cols = tuple(self.columns)
        for t, idx in enumerate(self.group_indices()):
            sub = self.matrix.matrix[idx] if idx.size else np.zeros((0, len(cols)), np.float32)
            yield self.bases[t], FeatureMatrix(sub, list(cols), self.matrix.row_ids[idx])

    # -- constructors ---------------------------------------------------------------
    @classmethod
    def from_matrices(
        cls, matrices: Mapping[str, FeatureMatrix], *, meta: Optional[Dict[str, object]] = None
    ) -> "SearchDataset":
        """Build from an in-memory ``{base: FeatureMatrix}`` mapping (insertion order).

        Args:
            matrices: Per-tomo feature matrices keyed by basename.
            meta: Optional provenance metadata.

        Returns:
            The assembled :class:`SearchDataset`.
        """
        bases = list(matrices.keys())
        combined, tomo_ids = _concat_matrices(bases, [matrices[b] for b in bases])
        return cls(combined, tomo_ids, bases, [], dict(meta or {}))

    @classmethod
    def from_parquet_paths(
        cls, paths: Mapping[str, Path], *, meta: Optional[Dict[str, object]] = None
    ) -> "SearchDataset":
        """Load per-tomo caches from an explicit ``{base: parquet_path}`` mapping.

        Absent paths are skipped and recorded in :attr:`missing` (a partially-featurised
        search is still tunable).

        Args:
            paths: Per-tomo cache paths keyed by basename.
            meta: Optional provenance metadata.

        Returns:
            The assembled :class:`SearchDataset`.
        """
        present: Dict[str, FeatureMatrix] = {}
        missing: List[str] = []
        for base, p in paths.items():
            if Path(p).exists():
                present[base] = FeatureMatrix.from_parquet(Path(p))
            else:
                missing.append(base)
        bases = list(present.keys())
        combined, tomo_ids = _concat_matrices(bases, [present[b] for b in bases])
        return cls(combined, tomo_ids, bases, missing, dict(meta or {}))

    @classmethod
    def from_cache_dir(
        cls,
        cache_dir: Path,
        bases: Optional[Sequence[str]] = None,
        *,
        suffix: str = CACHE_SUFFIX,
        meta: Optional[Dict[str, object]] = None,
    ) -> "SearchDataset":
        """Discover ``<cache_dir>/<base><suffix>`` caches for a search.

        When ``bases`` is None every ``*<suffix>`` file in ``cache_dir`` is loaded (base =
        filename minus ``suffix``), sorted by basename; otherwise exactly those bases are
        looked up (missing ones recorded in :attr:`missing`).

        Args:
            cache_dir: Directory holding the per-tomo parquet caches.
            bases: Optional explicit tomogram basenames to load (else auto-discover).
            suffix: The cache filename suffix.
            meta: Optional provenance metadata.

        Returns:
            The assembled :class:`SearchDataset`.
        """
        cache_dir = Path(cache_dir)
        if bases is None:
            found = sorted(p.name[: -len(suffix)] for p in cache_dir.glob(f"*{suffix}"))
            bases = found
        paths = {b: cache_dir / f"{b}{suffix}" for b in bases}
        info: Dict[str, object] = {"cache_dir": str(cache_dir), "suffix": suffix}
        info.update(meta or {})
        return cls.from_parquet_paths(paths, meta=info)
