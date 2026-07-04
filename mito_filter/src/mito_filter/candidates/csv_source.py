"""CsvPeakSource: the Phase-A candidate source built from the 26-column peak csv.

Reads ``<base>.csv`` (SPEC §2) into a :class:`~mito_filter.candidates.source.CandidateSet`
by delegating the fragile column/frame conventions to
:func:`mito_filter.emclarity.csv_io.read_peaks` (positions cols 11-13 ``/SAMPLING_RATE`` and
reversed to the ``(z, y, x)`` convmap-voxel frame; outward normal cols 23-25, C12-invariant;
score col 1; ``subtomo_id`` col 4; ``template_idx`` from the sibling ``.templateIDX``; the
active flag col 26). The stable per-candidate key is the 0-based csv row index (SPEC §2: one
write loop makes csv row ``k`` == ``.pos`` / ``.templateIDX`` / subTomoMeta-geometry row ``k``),
carried as :attr:`CandidateSet.row_ids` so writeback can re-key by subtomo.

This source touches only the sparse csv (never the 559 MB convmap), so it is the day-one
candidate feed the DESIGN Phase A runs on.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Dict

import numpy as np
from numpy.typing import NDArray

from ..core.grid import VoxelGrid
from ..emclarity.csv_io import read_peaks
from .source import CandidateSet, CandidateSource

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..datasets.base import TomogramRef

# Attr carried out of ``read_peaks`` that becomes CandidateSet.row_ids (not a per-hit attr).
_ROW_ID_ATTR = "row_id"


def _resolve_csv_path(tomo: object) -> Path:
    """Best-effort resolution of a tomogram's peak-csv path (duck-typed ``TomogramRef``).

    ``datasets/base.py`` (owning ``TomogramRef``) is authored separately; this resolver
    accepts the shapes it is expected to expose, checked in order:

    1. a bare :class:`~pathlib.Path`/``str`` pointing at the ``.csv`` (or a suffix-less base);
    2. a ``csv_path`` / ``csv`` attribute (Path or str);
    3. a ``base`` name plus a directory attribute (``dir`` / ``root`` / ``convmap_dir``).

    Args:
        tomo: The tomogram reference (or a direct path).

    Returns:
        The resolved path to ``<base>.csv``.

    Raises:
        TypeError: If no csv path can be derived from ``tomo``.
    """
    if isinstance(tomo, (str, Path)):
        p = Path(tomo)
        return p if p.suffix == ".csv" else p.with_suffix(".csv")
    for attr in ("csv_path", "csv"):
        val = getattr(tomo, attr, None)
        if val is not None:
            p = Path(val)
            return p if p.suffix == ".csv" else p.with_suffix(".csv")
    base = getattr(tomo, "base", None)
    if base is not None:
        for dir_attr in ("dir", "root", "convmap_dir"):
            d = getattr(tomo, dir_attr, None)
            if d is not None:
                return Path(d) / f"{base}.csv"
    raise TypeError(
        "cannot resolve a peak-csv path from tomo "
        f"{tomo!r}: expected a Path, a 'csv_path'/'csv' attribute, or 'base' + a directory"
    )


class CsvPeakSource(CandidateSource):
    """Candidate source over the sparse 26-column peak csv (SPEC §2, DESIGN §2, §10.3).

    Args:
        load_template_idx: Attach ``template_idx`` from the sibling ``.templateIDX`` when it
            exists (default True).
        active_only: If True, drop rows whose col26 active flag is not set. Raw TM output is
            all-active (SPEC §6), so this is a no-op there; it matters only for a csv already
            annotated with ``REMOVED_FLAG``.

    Attributes:
        load_template_idx: Whether the template id is loaded.
        active_only: Whether inactive rows are dropped.
    """

    def __init__(self, *, load_template_idx: bool = True, active_only: bool = False) -> None:
        self.load_template_idx = load_template_idx
        self.active_only = active_only

    def candidates(self, tomo: "TomogramRef", grid: VoxelGrid) -> CandidateSet:
        """Return the csv peaks as a :class:`CandidateSet` (SPEC §2).

        Args:
            tomo: The tomogram to source candidates from (its ``.csv`` is located via
                :func:`_resolve_csv_path`).
            grid: The convmap voxel grid the coordinates are expressed on.

        Returns:
            The :class:`CandidateSet` of csv peaks.
        """
        return self.read(_resolve_csv_path(tomo), grid)

    def read(self, csv_path: Path, grid: VoxelGrid) -> CandidateSet:
        """Read a specific peak csv into a :class:`CandidateSet`.

        The direct entry point (used by :meth:`candidates` and by tests). Attaches every
        per-hit attr :func:`read_peaks` produces — ``cc``, ``normal`` ``(N, 3)`` in
        ``(z, y, x)``, ``euler`` ``(N, 3)``, ``subtomo_id``, ``active`` (bool),
        ``template_idx`` (if the sibling exists) — and carries the 0-based csv row index as
        :attr:`CandidateSet.row_ids`.

        Args:
            csv_path: Path to ``<base>.csv``.
            grid: The convmap voxel grid.

        Returns:
            The :class:`CandidateSet`; positions are in the ``(z, y, x)`` convmap-voxel frame.
        """
        pc = read_peaks(Path(csv_path), load_template_idx=self.load_template_idx)
        attrs: Dict[str, NDArray] = dict(pc.attrs)
        row_ids = np.asarray(attrs.pop(_ROW_ID_ATTR), dtype=np.int64)
        cand = CandidateSet(
            coords_zyx=pc.xyz,
            grid=grid,
            attrs=attrs,
            row_ids=row_ids,
        )
        if self.active_only:
            cand = cand.subset(np.asarray(cand.get("active"), dtype=bool))
        return cand
