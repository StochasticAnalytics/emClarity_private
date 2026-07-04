"""CandidateSource: where the hits to be filtered come from.

A candidate is one TM hit (or a dense-field re-detection). The csv peaks are one source
(:class:`~mito_filter.candidates.csv_source.CsvPeakSource`); dense-field peaks are another
(:class:`~mito_filter.candidates.dense_source.DenseFieldPeakSource`). :class:`CandidateSet`
is the fully-real struct-of-arrays every feature extractor consumes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Optional

import numpy as np
from numpy.typing import NDArray

from ..core.grid import VoxelGrid
from ..core.points import PointCloud

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..datasets.base import TomogramRef


@dataclass
class CandidateSet:
    """A set of candidate hits for one tomogram (struct-of-arrays).

    Args:
        coords_zyx: Candidate positions, shape ``(N, 3)``, in the convmap voxel frame
            ``(z, y, x)`` (float, sub-voxel allowed).
        grid: The voxel grid the coordinates live on.
        attrs: Per-candidate arrays (leading dim ``N``): ``"cc"``, ``"normal"`` ``(N, 3)``,
            ``"template_idx"``, ``"subtomo_id"``, ``"active"``, ``"euler"`` ``(N, 3)``, ...
        row_ids: Stable per-candidate ids ``(N,)`` — the csv/geometry row index (SPEC §2),
            used to key writeback by subtomo. Defaults to ``arange(N)`` if omitted.

    Attributes:
        coords_zyx: The positions.
        grid: The voxel grid.
        attrs: The per-candidate attributes.
        row_ids: The stable row ids.
    """

    coords_zyx: NDArray
    grid: VoxelGrid
    attrs: Dict[str, NDArray] = field(default_factory=dict)
    row_ids: Optional[NDArray] = None

    def __post_init__(self) -> None:
        self.coords_zyx = np.asarray(self.coords_zyx, dtype=np.float64)
        if self.coords_zyx.ndim != 2 or self.coords_zyx.shape[1] != 3:
            raise ValueError(f"coords_zyx must be (N, 3), got {self.coords_zyx.shape}")
        n = self.coords_zyx.shape[0]
        for k, v in self.attrs.items():
            arr = np.asarray(v)
            if arr.shape[0] != n:
                raise ValueError(f"attr '{k}' leading dim {arr.shape[0]} != N {n}")
            self.attrs[k] = arr
        if self.row_ids is None:
            self.row_ids = np.arange(n, dtype=np.int64)
        else:
            self.row_ids = np.asarray(self.row_ids)
            if self.row_ids.shape[0] != n:
                raise ValueError(f"row_ids length {self.row_ids.shape[0]} != N {n}")

    @property
    def n(self) -> int:
        """Number of candidates."""
        return int(self.coords_zyx.shape[0])

    def __len__(self) -> int:
        return self.n

    def get(self, k: str) -> NDArray:
        """Return attribute ``k`` (helpful KeyError if absent).

        Args:
            k: Attribute name.

        Returns:
            The attribute array.

        Raises:
            KeyError: If ``k`` is not present.
        """
        try:
            return self.attrs[k]
        except KeyError:
            avail = ", ".join(sorted(self.attrs)) or "<none>"
            raise KeyError(f"CandidateSet has no attr '{k}'. Available: {avail}") from None

    def subset(self, mask: NDArray) -> "CandidateSet":
        """Return the subset selected by a boolean mask or integer index array.

        Args:
            mask: Boolean ``(N,)`` or integer index array.

        Returns:
            A new CandidateSet with coords, attrs, and row_ids sliced identically.
        """
        idx = np.asarray(mask)
        assert self.row_ids is not None  # set in __post_init__
        return CandidateSet(
            self.coords_zyx[idx],
            self.grid,
            {k: v[idx] for k, v in self.attrs.items()},
            self.row_ids[idx],
        )

    def to_point_cloud(self) -> PointCloud:
        """Return these candidates as a :class:`PointCloud` (shares coords + attrs)."""
        return PointCloud(self.coords_zyx.copy(), dict(self.attrs))


class CandidateSource(ABC):
    """Produces a :class:`CandidateSet` for a tomogram."""

    @abstractmethod
    def candidates(self, tomo: "TomogramRef", grid: VoxelGrid) -> CandidateSet:
        """Return the candidate hits for ``tomo``.

        Args:
            tomo: The tomogram to source candidates from.
            grid: The voxel grid the candidates must be expressed in.

        Returns:
            The :class:`CandidateSet`.
        """
        raise NotImplementedError
