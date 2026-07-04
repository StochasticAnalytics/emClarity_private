"""HitVerdicts: the per-hit scan decision (score / flag / removed) + provenance (DESIGN §8).

A :class:`HitVerdicts` is the immutable output of :class:`~mito_filter.scan.pipeline.ScanPipeline`
for one tomogram: for every candidate hit it carries the keep-probability, the boolean keep/flag
decision at ``tau``, and the stable key writeback needs — the **csv/geometry row index**
(``row_ids``; preserves csv row order for the col26 debug write AND is the ``.mat`` apply key,
SPEC §9.1) — plus the per-tomo csv col4 peak id (``subtomo_ids``; provenance/cross-reference
only) and the euler triple cross-check.

The convention is emClarity's col26: **keep -> 1, remove -> REMOVED_FLAG (-9999)** (SPEC §2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

import numpy as np
from numpy.typing import NDArray

from ..emclarity.constants import REMOVED_FLAG

__all__ = ["HitVerdicts"]


@dataclass(frozen=True)
class HitVerdicts:
    """Per-hit scan decisions for one tomogram (row-aligned struct-of-arrays).

    Args:
        tomo: The tomogram basename (e.g. ``"H99_2_100_1_bin5"``).
        row_ids: Stable csv/geometry row indices ``(N,)`` (SPEC §2 — csv row ``k`` == sibling
            row ``k`` == subTomoMeta geometry row ``k``); preserves col26 write order.
        subtomo_ids: Per-tomo csv col4 peak ids ``(N,)`` (reset per tomo) — provenance /
            cross-reference only, **NOT** the ``.mat`` key (that is the global id; the apply keys
            on ``row_ids`` scoped to the tomo, SPEC §9.1).
        keep_prob: Per-hit keep-probability ``(N,)`` in ``[0, 1]``.
        keep: Per-hit boolean keep mask ``(N,)`` (``keep_prob >= tau``); ``False`` == flagged FP.
        tau: The keep-probability decision threshold used.
        euler: Optional euler triples ``[phi, theta, psi-phi]`` degrees ``(N, 3)`` (the ``.mat``
            angle-triple cross-check); ``None`` when unavailable.
        dataset: The subTomoMeta project label (e.g. ``"full_enchilada_3_4"``).
        provenance: Free-form record of the model / fields / config that produced these verdicts.

    Attributes:
        tomo: The tomogram basename.
        row_ids: The row indices.
        subtomo_ids: The subtomo ids.
        keep_prob: The keep-probabilities.
        keep: The keep mask.
        tau: The decision threshold.
        euler: The euler cross-check (or None).
        dataset: The project label.
        provenance: The provenance mapping.
    """

    tomo: str
    row_ids: NDArray[np.int64]
    subtomo_ids: NDArray[np.int64]
    keep_prob: NDArray[np.float64]
    keep: NDArray[np.bool_]
    tau: float
    euler: Optional[NDArray[np.float64]] = None
    dataset: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        row_ids = np.asarray(self.row_ids, dtype=np.int64).reshape(-1)
        n = row_ids.shape[0]
        subtomo_ids = np.asarray(self.subtomo_ids, dtype=np.int64).reshape(-1)
        keep_prob = np.asarray(self.keep_prob, dtype=np.float64).reshape(-1)
        keep = np.asarray(self.keep, dtype=bool).reshape(-1)
        for name, arr in (("subtomo_ids", subtomo_ids), ("keep_prob", keep_prob), ("keep", keep)):
            if arr.shape[0] != n:
                raise ValueError(f"{name} length {arr.shape[0]} != N {n}")
        object.__setattr__(self, "row_ids", row_ids)
        object.__setattr__(self, "subtomo_ids", subtomo_ids)
        object.__setattr__(self, "keep_prob", keep_prob)
        object.__setattr__(self, "keep", keep)
        if self.euler is not None:
            eul = np.atleast_2d(np.asarray(self.euler, dtype=np.float64))
            if eul.shape != (n, 3):
                raise ValueError(f"euler {eul.shape} incompatible with {n} hits")
            object.__setattr__(self, "euler", eul)
        object.__setattr__(self, "tau", float(self.tau))

    @property
    def n(self) -> int:
        """Number of hits."""
        return int(self.row_ids.shape[0])

    @property
    def removed_mask(self) -> NDArray[np.bool_]:
        """Boolean ``(N,)`` mask of flagged (removed) hits (``~keep``)."""
        return ~self.keep

    @property
    def n_removed(self) -> int:
        """Number of flagged (removed) hits."""
        return int(np.count_nonzero(self.removed_mask))

    @property
    def n_kept(self) -> int:
        """Number of surviving (kept) hits."""
        return int(np.count_nonzero(self.keep))

    def active_flags(self) -> NDArray[np.int64]:
        """Return the per-hit emClarity col26 flags in verdict order (keep 1 / remove -9999)."""
        return np.where(self.keep, 1, REMOVED_FLAG).astype(np.int64)

    def full_active_flags(
        self, n_rows: Optional[int] = None, *, base: Optional[NDArray[np.int64]] = None
    ) -> NDArray[np.int64]:
        """Return a full-length col26 flag array indexed by :attr:`row_ids` (SPEC §2 order).

        Rows present in these verdicts are overlaid with their keep/remove flag at their
        ``row_id`` slot. Rows **not** scanned keep their ``base`` value; ``base`` defaults to
        all-``1`` (kept). Pass the source csv's existing col26 as ``base`` so an already-removed
        (``REMOVED_FLAG``) row that the candidate source dropped (e.g. ``active_only=True``) stays
        removed instead of being resurrected to ``1``.

        Args:
            n_rows: Total csv row count. Defaults to ``max(row_ids) + 1`` when omitted (or to
                ``len(base)`` when ``base`` is given).
            base: Optional ``(n_rows,)`` starting flag vector (e.g. the source col26); unscanned
                rows retain it. Defaults to all ``1``.

        Returns:
            An ``(n_rows,)`` int64 array of ``{1, REMOVED_FLAG}`` flags.

        Raises:
            ValueError: If ``n_rows`` is smaller than the largest ``row_id + 1``, or ``base``'s
                length disagrees with ``n_rows``.
        """
        need = int(self.row_ids.max()) + 1 if self.n else 0
        if n_rows is None:
            total = len(base) if base is not None else need
        else:
            total = int(n_rows)
        if total < need:
            raise ValueError(f"n_rows {total} < max row_id + 1 ({need})")
        if base is not None:
            base_arr = np.asarray(base, dtype=np.int64).reshape(-1)
            if base_arr.shape[0] != total:
                raise ValueError(f"base length {base_arr.shape[0]} != n_rows {total}")
            flags = base_arr.copy()
        else:
            flags = np.ones(total, dtype=np.int64)
        flags[self.row_ids] = self.active_flags()
        return flags

    def removed_subtomo_ids(self) -> NDArray[np.int64]:
        """Return the per-tomo csv col4 peak ids of the flagged (removed) hits (provenance)."""
        return self.subtomo_ids[self.removed_mask]

    def removed_euler(self) -> Optional[NDArray[np.float64]]:
        """Return the euler triples of the flagged hits, or ``None`` if no euler is carried."""
        if self.euler is None:
            return None
        return np.asarray(self.euler)[self.removed_mask]

    def to_summary(self) -> Dict[str, Any]:
        """Return a small JSON-ready summary (counts + tau + provenance, no per-hit arrays)."""
        return {
            "tomo": self.tomo,
            "dataset": self.dataset,
            "tau": self.tau,
            "n": self.n,
            "n_kept": self.n_kept,
            "n_removed": self.n_removed,
            "provenance": dict(self.provenance),
        }
