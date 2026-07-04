"""Two-phase feature engine API: extractors, the cached FeatureMatrix, and BlockCtx.

Dense volumes are touched ONCE: an extractor gathers per-candidate feature columns from
the named dense fields, and the engine concatenates them into a :class:`FeatureMatrix`
cached to parquet. The tuner then iterates on the cached matrix and never re-reads a volume.

:class:`FeatureMatrix` is FULLY implemented (including parquet round-trip). :class:`BlockCtx`
and :class:`FeatureSpec` are real; :class:`FeatureExtractor` is the frozen ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Mapping, Tuple

import numpy as np
from numpy.typing import NDArray

from ..core.backend import Backend
from ..core.grid import VoxelGrid

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..candidates.source import CandidateSet
    from ..core.field import DenseField

ArrayT = NDArray

ROW_ID_COL = "__row_id__"
"""Reserved parquet column name holding the per-candidate stable row id."""


@dataclass(frozen=True)
class FeatureSpec:
    """Static description of a feature column.

    Args:
        name: The column name.
        theta_dependent: True if recomputed per optimizer step (not cached).
        description: One-line human description.

    Attributes:
        name: The column name.
        theta_dependent: Whether it is theta-dependent.
        description: The description string.
    """

    name: str
    theta_dependent: bool = False
    description: str = ""


@dataclass
class BlockCtx:
    """Context handed to :meth:`FeatureExtractor.extract`.

    Args:
        grid: The tomogram's voxel grid.
        backend: The array backend (CPU/cupy/torch).
        meta: Free-form per-run metadata (calibration stats, provenance, ...).

    Attributes:
        grid: The voxel grid.
        backend: The backend.
        meta: Metadata mapping.
    """

    grid: VoxelGrid
    backend: Backend = field(default_factory=Backend.cpu)
    meta: Mapping[str, object] = field(default_factory=dict)

    @property
    def xp(self) -> object:
        """The array module for this context's backend (numpy / cupy / torch)."""
        return self.backend.xp()


@dataclass
class FeatureMatrix:
    """A cached ``(N_candidates, N_features)`` matrix + column index + row ids.

    Args:
        matrix: The feature values, shape ``(N, F)``, float32.
        columns: The ``F`` feature column names, in matrix-column order.
        row_ids: Stable per-candidate ids ``(N,)`` (the csv/geometry row index).

    Attributes:
        matrix: The feature values.
        columns: The column names.
        row_ids: The row ids.
    """

    matrix: NDArray
    columns: List[str]
    row_ids: NDArray

    def __post_init__(self) -> None:
        self.matrix = np.asarray(self.matrix, dtype=np.float32)
        if self.matrix.ndim != 2:
            raise ValueError(f"matrix must be 2-D (N, F), got {self.matrix.shape}")
        n, f = self.matrix.shape
        if len(self.columns) != f:
            raise ValueError(f"columns length {len(self.columns)} != n_features {f}")
        self.row_ids = np.asarray(self.row_ids)
        if self.row_ids.shape[0] != n:
            raise ValueError(f"row_ids length {self.row_ids.shape[0]} != N {n}")
        self._col_index: Dict[str, int] = {c: i for i, c in enumerate(self.columns)}
        if len(self._col_index) != len(self.columns):
            raise ValueError("duplicate feature column names")

    @property
    def n(self) -> int:
        """Number of candidate rows."""
        return int(self.matrix.shape[0])

    @property
    def n_features(self) -> int:
        """Number of feature columns."""
        return int(self.matrix.shape[1])

    def column(self, name: str) -> NDArray:
        """Return the ``(N,)`` values of feature column ``name``.

        Args:
            name: The feature column name.

        Returns:
            The column values.

        Raises:
            KeyError: If ``name`` is not a column (message lists available columns).
        """
        try:
            j = self._col_index[name]
        except KeyError:
            avail = ", ".join(self.columns) or "<none>"
            raise KeyError(f"no feature column '{name}'. Available: {avail}") from None
        return self.matrix[:, j]

    def select(self, names: Tuple[str, ...]) -> NDArray:
        """Return a ``(N, len(names))`` view stacking the named columns in order.

        Args:
            names: The feature column names to stack.

        Returns:
            A 2-D array of the selected columns.
        """
        idx = [self._col_index[n] for n in names]
        return self.matrix[:, idx]

    def __contains__(self, name: object) -> bool:
        return name in self._col_index

    @classmethod
    def from_columns(cls, columns: Mapping[str, NDArray], row_ids: NDArray) -> "FeatureMatrix":
        """Build a FeatureMatrix from a name -> ``(N,)`` array mapping.

        Args:
            columns: Ordered mapping of feature name to its ``(N,)`` values.
            row_ids: The ``(N,)`` stable row ids.

        Returns:
            The assembled :class:`FeatureMatrix`.
        """
        names = list(columns.keys())
        if names:
            mat = np.stack([np.asarray(columns[k], dtype=np.float32) for k in names], axis=1)
        else:
            mat = np.zeros((len(np.asarray(row_ids)), 0), dtype=np.float32)
        return cls(mat, names, np.asarray(row_ids))

    def to_parquet(self, path: Path) -> None:
        """Write the matrix (+ row ids) to a parquet file.

        Args:
            path: Destination ``.parquet`` path (parent dirs created).
        """
        import pandas as pd

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {ROW_ID_COL: np.asarray(self.row_ids)}
        for j, c in enumerate(self.columns):
            data[c] = self.matrix[:, j]
        pd.DataFrame(data).to_parquet(path, index=False)

    @classmethod
    def from_parquet(cls, path: Path) -> "FeatureMatrix":
        """Read a FeatureMatrix previously written by :meth:`to_parquet`.

        Args:
            path: Source ``.parquet`` path.

        Returns:
            The reconstructed :class:`FeatureMatrix`.
        """
        import pandas as pd

        df = pd.read_parquet(path)
        row_ids = np.asarray(df[ROW_ID_COL])
        cols = [c for c in df.columns if c != ROW_ID_COL]
        if cols:
            mat = np.stack([np.asarray(df[c], dtype=np.float32) for c in cols], axis=1)
        else:
            mat = np.zeros((len(row_ids), 0), dtype=np.float32)
        return cls(mat, cols, row_ids)


class FeatureExtractor(ABC):
    """Extracts one or more per-candidate feature columns from dense fields.

    Subclasses set :attr:`produces`, :attr:`needs_fields`, and (optionally)
    :attr:`theta_dependent`, then implement :meth:`extract`.

    Attributes:
        produces: The feature column names this extractor yields.
        needs_fields: Field names required (drives ``FieldRegistry.plan``).
        theta_dependent: True -> recomputed per optimizer step, NOT cached.
    """

    produces: Tuple[str, ...] = ()
    needs_fields: Tuple[str, ...] = ()
    theta_dependent: bool = False

    @abstractmethod
    def extract(
        self,
        cand: "CandidateSet",
        fields: Mapping[str, "DenseField"],
        ctx: BlockCtx,
    ) -> Dict[str, ArrayT]:
        """Compute this extractor's feature columns for every candidate.

        Args:
            cand: The candidates to featurize.
            fields: The materialized dense fields keyed by name (superset of
                :attr:`needs_fields`).
            ctx: The block/backend context.

        Returns:
            Mapping feature-name -> ``(N,)`` array, one entry per name in
            :attr:`produces`.
        """
        raise NotImplementedError
