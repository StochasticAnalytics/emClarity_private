"""WeakLabelSource: honest weak labels from what actually exists on disk (SPEC §10).

There are **no per-hit spatial ground-truth labels** for round_4 (SPEC §10.4). What exists,
ranked by directness:

1. **``.templateIDX`` (on disk, per hit).** ``ref_old`` (template id 1) is enriched in false
   positives (survives the culls worst: %kept 24.9 vs 48/55 for the prototypes), so
   ``templateIDX == 1`` is a usable **weak negative** prior straight from the file (SPEC §10.1).
2. **col26 active flag.** For RAW template matching every row is active (``== 1``), so col26 is
   *weak / uninformative* here — this source only yields **strong negatives** once a downstream
   cycle has stamped ``-9999`` into it. We surface it honestly: all-active => no discriminative
   label.
3. **Classification cull files** ``cycle<NNN>_ClassMods_STD.txt`` / ``_ClassKeep_STD.txt``.
   These are **class-level** (which of the N k-means classes were removed/retained + aggregate
   counts) — mapping them to individual hits needs the per-particle class assignment from the
   480 MB v7 ``.mat`` (scipy cannot read it; MATLAB-on-salina only). So on disk they give a
   dataset-level **cull context** (a confidence schedule + counts), not per-hit labels. We parse
   them faithfully and expose them as context; the objective's weak term stays primarily on the
   per-hit templateIDX prior.

Because strong per-hit labels are scarce, the tuner's **self-supervised physics objective is
primary** (:mod:`mito_filter.optimize.objective`); these weak labels only *regularise* it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Mapping, Optional, Sequence

import numpy as np
from numpy.typing import NDArray

from ..emclarity.constants import REMOVED_FLAG
from ..emclarity.templateidx import read_template_idx
from .dataset import SearchDataset

__all__ = [
    "UNKNOWN",
    "NEGATIVE",
    "POSITIVE",
    "WeakLabels",
    "ClassCull",
    "parse_class_cull",
    "find_cull_files",
    "WeakLabelSource",
]

UNKNOWN: int = -1
"""Label for a candidate with no weak evidence either way."""
NEGATIVE: int = 0
"""Weak/strong negative (likely false positive)."""
POSITIVE: int = 1
"""Weak/strong positive (likely true target)."""

_INT_LIST = re.compile(r"-?\d+")


def _parse_int_list(line: str) -> List[int]:
    """Extract the leading integer vector from a ``[a,b,c; ...]`` MATLAB-ish line.

    Only the portion **before** the first ``;`` is taken (the second row is the vestigial
    symmetry weight ``1.*ones(1,K)`` — SPEC / CLAUDE.md classification notes).

    Args:
        line: The bracketed line (e.g. ``"[1,2,3; 1.*ones(1,3)]"``).

    Returns:
        The integer class ids in the first row.
    """
    head = line.split(";", 1)[0]
    return [int(m.group()) for m in _INT_LIST.finditer(head)]


@dataclass(frozen=True)
class ClassCull:
    """A parsed class-level cull file (``ClassMods`` remove-cull or ``ClassKeep`` keep-cull).

    Args:
        cycle: The classification cycle number (from the filename ``cycle<NNN>_...``).
        kind: ``"mods"`` (RemoveClasses) or ``"keep"`` (ClassKeep).
        removed: Class ids dropped at this cull.
        retained: Class ids kept at this cull.
        n_removed: Particles removed (``removed:`` line), or None if absent.
        n_remaining: Particles remaining (``remaining:`` line), or None.
        n_orig: Particles before this cull (``orig:`` line), or None.
        path: The source file.

    Attributes:
        cycle: The cycle number.
        kind: The cull kind.
        removed: Removed class ids.
        retained: Retained class ids.
        n_removed: Particle removal count.
        n_remaining: Surviving count.
        n_orig: Pre-cull count.
        path: Source path.
    """

    cycle: int
    kind: str
    removed: List[int]
    retained: List[int]
    n_removed: Optional[int]
    n_remaining: Optional[int]
    n_orig: Optional[int]
    path: Optional[Path] = None

    @property
    def keep_fraction(self) -> Optional[float]:
        """Surviving fraction ``n_remaining / n_orig`` for this cull (None if counts absent)."""
        if self.n_remaining is None or not self.n_orig:
            return None
        return float(self.n_remaining) / float(self.n_orig)


def _cycle_from_name(path: Path) -> int:
    """Return the ``cycle<NNN>`` number embedded in a cull filename (``-1`` if none)."""
    m = re.search(r"cycle0*(\d+)", path.name)
    return int(m.group(1)) if m else -1


def parse_class_cull(path: Path) -> ClassCull:
    """Parse a ``cycle<NNN>_ClassMods_STD.txt`` or ``_ClassKeep_STD.txt`` cull file.

    Handles both header vocabularies: ``Classes removed`` / ``Classes retained`` (ClassMods)
    and ``Classes kept`` / ``Classes dropped`` (ClassKeep). The trailing ``removed:`` /
    ``remaining:`` / ``orig:`` count lines (present in ClassMods) are read when found.

    Args:
        path: Path to the cull text file.

    Returns:
        The parsed :class:`ClassCull`.

    Raises:
        ValueError: If neither a retained/kept nor a removed/dropped list can be found.
    """
    path = Path(path)
    lines = path.read_text().splitlines()
    kind = "keep" if "ClassKeep" in path.name else "mods"
    removed: List[int] = []
    retained: List[int] = []
    n_removed = n_remaining = n_orig = None
    found = False
    i = 0
    while i < len(lines):
        low = lines[i].strip().lower()
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if low.startswith("classes removed") or low.startswith("classes dropped"):
            removed = _parse_int_list(nxt)
            found = True
            i += 2
            continue
        if low.startswith("classes retained") or low.startswith("classes kept"):
            retained = _parse_int_list(nxt)
            found = True
            i += 2
            continue
        m = re.search(r"(removed|remaining|orig)\s*:\s*(\d+)", lines[i])
        if m:
            val = int(m.group(2))
            if m.group(1) == "removed":
                n_removed = val
            elif m.group(1) == "remaining":
                n_remaining = val
            else:
                n_orig = val
        i += 1
    if not found:
        raise ValueError(f"{path}: no class removed/retained/kept/dropped list found")
    return ClassCull(
        cycle=_cycle_from_name(path),
        kind=kind,
        removed=removed,
        retained=retained,
        n_removed=n_removed,
        n_remaining=n_remaining,
        n_orig=n_orig,
        path=path,
    )


def find_cull_files(round_dir: Path) -> List[Path]:
    """Return the ``cycle*_ClassMods_STD.txt`` / ``cycle*_ClassKeep_STD.txt`` files in a round.

    Args:
        round_dir: The round directory (e.g. ``six_hours_round_4``).

    Returns:
        The matching cull-file paths, sorted by name (empty if none / dir absent).
    """
    round_dir = Path(round_dir)
    if not round_dir.is_dir():
        return []
    hits = list(round_dir.glob("cycle*_ClassMods_STD.txt"))
    hits += list(round_dir.glob("cycle*_ClassKeep_STD.txt"))
    return sorted(hits, key=lambda p: p.name)


@dataclass
class WeakLabels:
    """Per-candidate weak labels + confidences, row-aligned to a :class:`SearchDataset`.

    Args:
        label: ``(N,)`` int8 in ``{-1 unknown, 0 negative, 1 positive}``.
        weight: ``(N,)`` confidence in ``[0, 1]`` (0 at unknown rows).
        sources: Human tags of the evidence that produced these labels.

    Attributes:
        label: The label array.
        weight: The confidence array.
        sources: Evidence tags.
    """

    label: NDArray[np.int8]
    weight: NDArray[np.float32]
    sources: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.label = np.asarray(self.label, dtype=np.int8).reshape(-1)
        self.weight = np.asarray(self.weight, dtype=np.float32).reshape(-1)
        if self.label.shape != self.weight.shape:
            raise ValueError("label and weight must be the same length")
        self.weight = np.where(self.label == UNKNOWN, 0.0, self.weight).astype(np.float32)

    @property
    def n(self) -> int:
        """Number of rows."""
        return int(self.label.shape[0])

    @property
    def n_pos(self) -> int:
        """Count of positive rows."""
        return int(np.count_nonzero(self.label == POSITIVE))

    @property
    def n_neg(self) -> int:
        """Count of negative rows."""
        return int(np.count_nonzero(self.label == NEGATIVE))

    @property
    def n_labeled(self) -> int:
        """Count of rows with any (non-unknown) label."""
        return int(np.count_nonzero(self.label != UNKNOWN))

    @property
    def has_both_classes(self) -> bool:
        """True iff both a positive and a negative labelled row exist (needed for PR/AUC)."""
        return self.n_pos > 0 and self.n_neg > 0

    def combine(self, other: "WeakLabels") -> "WeakLabels":
        """Merge another label set (same length); the higher-confidence label wins per row.

        Ties and agreement keep the max confidence; a disagreement resolves to whichever
        source has the larger weight (self on an exact tie).

        Args:
            other: The other :class:`WeakLabels` (must match length).

        Returns:
            The merged :class:`WeakLabels`.

        Raises:
            ValueError: If lengths differ.
        """
        if self.n != other.n:
            raise ValueError(f"cannot combine weak labels of length {self.n} and {other.n}")
        take_other = other.weight > self.weight
        label = np.where(take_other, other.label, self.label).astype(np.int8)
        weight = np.where(take_other, other.weight, self.weight).astype(np.float32)
        # Where one side is unknown, adopt the other's label outright.
        self_unknown = self.label == UNKNOWN
        label = np.where(self_unknown, other.label, label).astype(np.int8)
        weight = np.where(self_unknown, other.weight, weight).astype(np.float32)
        return WeakLabels(label, weight, sorted(set(self.sources) | set(other.sources)))


class WeakLabelSource:
    """Derive :class:`WeakLabels` for a search from the on-disk evidence (SPEC §10).

    Args:
        round_dir: The round directory holding the cull files (optional; enables
            :meth:`cull_context`).
        convmap_dir: The directory holding ``<base>.templateIDX`` siblings (optional; enables
            reading the per-hit template prior straight from disk).
        ref1_id: The template id treated as the weak-negative reference (SPEC §10.1, ``1``).
        ref1_confidence: Confidence assigned to a ``templateIDX == ref1_id`` weak negative.

    Attributes:
        round_dir: The round directory.
        convmap_dir: The convmap directory.
        ref1_id: The weak-negative template id.
        ref1_confidence: The weak-negative confidence.
    """

    def __init__(
        self,
        round_dir: Optional[Path] = None,
        convmap_dir: Optional[Path] = None,
        *,
        ref1_id: int = 1,
        ref1_confidence: float = 0.3,
    ) -> None:
        self.round_dir = Path(round_dir) if round_dir is not None else None
        self.convmap_dir = Path(convmap_dir) if convmap_dir is not None else None
        self.ref1_id = int(ref1_id)
        self.ref1_confidence = float(ref1_confidence)

    # -- dataset-level context ------------------------------------------------------
    def cull_context(self) -> List[ClassCull]:
        """Parse every cull file in :attr:`round_dir` (class-level, SPEC §10.3).

        Returns:
            The parsed :class:`ClassCull` list (empty if no round dir / no files).
        """
        if self.round_dir is None:
            return []
        return [parse_class_cull(p) for p in find_cull_files(self.round_dir)]

    # -- per-hit labels -------------------------------------------------------------
    def template_idx_labels(
        self, template_idx: NDArray[np.int64], *, active: Optional[NDArray] = None
    ) -> WeakLabels:
        """Weak-negative labels from ``templateIDX == ref1_id`` (SPEC §10.1).

        A ``ref_old`` (id 1) hit is a weak negative; every other hit is unknown. If an
        ``active`` array is given, an inactive (``-9999``) hit becomes a *strong* negative
        (confidence 1.0) regardless of template.

        Args:
            template_idx: ``(N,)`` winning template id per hit (csv row order).
            active: Optional ``(N,)`` col26 active flag.

        Returns:
            The :class:`WeakLabels`.
        """
        tix = np.asarray(template_idx, dtype=np.int64).reshape(-1)
        n = tix.shape[0]
        label = np.full(n, UNKNOWN, dtype=np.int8)
        weight = np.zeros(n, dtype=np.float32)
        ref1 = tix == self.ref1_id
        label[ref1] = NEGATIVE
        weight[ref1] = self.ref1_confidence
        sources = [f"templateIDX=={self.ref1_id}"]
        if active is not None:
            act = np.asarray(active).reshape(-1)
            removed = act == REMOVED_FLAG
            label[removed] = NEGATIVE
            weight[removed] = 1.0
            sources.append("col26")
        return WeakLabels(label, weight, sources)

    def col26_labels(self, active: NDArray) -> WeakLabels:
        """Labels from the col26 active flag alone (strong negative where ``-9999``).

        For raw template matching every row is active, so this yields *no discriminative*
        labels (all unknown) — surfaced honestly so a caller sees col26 is uninformative here.

        Args:
            active: ``(N,)`` col26 active flag.

        Returns:
            The :class:`WeakLabels` (all-unknown when nothing is removed).
        """
        act = np.asarray(active).reshape(-1)
        n = act.shape[0]
        label = np.full(n, UNKNOWN, dtype=np.int8)
        weight = np.zeros(n, dtype=np.float32)
        removed = act == REMOVED_FLAG
        label[removed] = NEGATIVE
        weight[removed] = 1.0
        return WeakLabels(label, weight, ["col26"])

    def _read_template_idx(self, base: str, n_expected: int) -> Optional[NDArray[np.int64]]:
        """Read ``<convmap_dir>/<base>.templateIDX`` (validated length), or None if absent."""
        if self.convmap_dir is None:
            return None
        p = self.convmap_dir / f"{base}.templateIDX"
        if not p.exists():
            return None
        tix = read_template_idx(p)
        if tix.shape[0] != n_expected:
            raise ValueError(
                f"{p}: {tix.shape[0]} templateIDX rows != {n_expected} feature rows for '{base}'"
            )
        return tix

    def build(
        self,
        dataset: SearchDataset,
        *,
        template_idx: Optional[Mapping[str, NDArray[np.int64]]] = None,
    ) -> WeakLabels:
        """Assemble per-row weak labels aligned to ``dataset`` (SPEC §10).

        The per-hit template prior is read from ``template_idx[base]`` if supplied, else from
        ``<convmap_dir>/<base>.templateIDX`` on disk, else from a cached ``is_ref1`` /
        ``template_idx`` feature column if the dataset carries one. Row order within each
        tomogram is the csv/geometry row order (SPEC §2), matching the feature-matrix rows.

        Args:
            dataset: The whole-search dataset the labels must align to.
            template_idx: Optional in-memory ``{base: templateIDX array}`` override.

        Returns:
            The row-aligned :class:`WeakLabels` for the combined matrix.
        """
        n = dataset.n
        label = np.full(n, UNKNOWN, dtype=np.int8)
        weight = np.zeros(n, dtype=np.float32)
        used_disk = used_feature = False
        groups = dataset.group_indices()
        for t, idx in enumerate(groups):
            base = dataset.bases[t]
            tix: Optional[NDArray[np.int64]] = None
            if template_idx is not None and base in template_idx:
                tix = np.asarray(template_idx[base], dtype=np.int64).reshape(-1)
            else:
                tix = self._read_template_idx(base, idx.size)
                used_disk = used_disk or tix is not None
            if tix is None:
                continue
            if tix.shape[0] != idx.size:
                raise ValueError(
                    f"templateIDX for '{base}' has {tix.shape[0]} rows != {idx.size} feature rows"
                )
            ref1 = tix == self.ref1_id
            label[idx[ref1]] = NEGATIVE
            weight[idx[ref1]] = self.ref1_confidence

        # Fall back to a cached is_ref1 / template_idx feature column when no ids were found.
        if not np.any(weight > 0):
            col = None
            for name in ("is_ref1", "template_idx"):
                if name in dataset:
                    col = (name, np.asarray(dataset.column(name)))
                    break
            if col is not None:
                name, values = col
                ref1 = values >= 0.5 if name == "is_ref1" else values == self.ref1_id
                label[ref1] = NEGATIVE
                weight[ref1] = self.ref1_confidence
                used_feature = True

        sources: List[str] = []
        if used_disk or template_idx is not None:
            sources.append(f"templateIDX=={self.ref1_id}")
        if used_feature:
            sources.append("is_ref1 feature")
        return WeakLabels(label, weight, sources or [f"templateIDX=={self.ref1_id}"])

    def build_from_arrays(
        self, bases: Sequence[str], template_idx: Mapping[str, NDArray[np.int64]]
    ) -> WeakLabels:
        """Assemble weak labels directly from per-base templateIDX arrays (no dataset).

        Convenience for tests / label-only inspection: concatenates the per-base arrays in
        ``bases`` order and applies the ``ref1`` weak-negative prior.

        Args:
            bases: Tomogram basenames, in row-concatenation order.
            template_idx: ``{base: templateIDX array}``.

        Returns:
            The concatenated :class:`WeakLabels`.
        """
        parts = [np.asarray(template_idx[b], dtype=np.int64).reshape(-1) for b in bases]
        tix = np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)
        return self.template_idx_labels(tix)
