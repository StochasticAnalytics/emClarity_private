"""Writeback: turn :class:`~mito_filter.scan.verdicts.HitVerdicts` into runnable outputs.

Two runnable artifacts + one gated stub (DESIGN §9.1):

1. **col26 debug csv** — mirror the keep/remove decision into column 26 of a copy of the source
   csv, **preserving exact row order** (via ``mito_filter.emclarity.csv_io.write_active_column``).
   This is a human-readable diff artifact, *not* the thing that changes emClarity behaviour.
2. **removal-list JSON** — the authoritative removal set keyed by **subtomo_id** (+ euler triple
   cross-check), the runnable machine-readable output.
3. **MATLAB-on-salina apply stub** — rendered (never executed) here: scipy cannot read the v7
   ``.mat`` and positions drift, so the real ``-9999`` write runs under MATLAB on salina keyed by
   subtomo_id (:mod:`mito_filter.emclarity.matio`). ``mito_filter`` only *renders* the script.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..emclarity.matio import (
    RemovalList,
    render_matlab_apply_script,
    render_salina_apply_command,
    write_removal_list,
)
from .verdicts import HitVerdicts

__all__ = [
    "WritebackResult",
    "build_removal_list",
    "write_debug_csv",
    "write_removal_json",
    "write_removal_table",
    "render_mat_apply",
    "writeback",
]


@dataclass(frozen=True)
class WritebackResult:
    """The artifacts produced by a :func:`writeback` call.

    Args:
        n_removed: Number of hits flagged for removal.
        debug_csv: Path to the col26 debug csv (or None if not requested / no source csv).
        removal_json: Path to the subtomo-id-keyed removal JSON (or None).
        removal_table: Path to the ``matio`` text removal table (or None).
        mat_script: Path to the rendered (un-executed) MATLAB apply script (or None).
        mat_command: The salina apply shell command string (rendered, not run; or None).

    Attributes:
        n_removed: The removal count.
        debug_csv: The debug csv path.
        removal_json: The removal JSON path.
        removal_table: The removal table path.
        mat_script: The MATLAB script path.
        mat_command: The salina apply command.
    """

    n_removed: int
    debug_csv: Optional[Path] = None
    removal_json: Optional[Path] = None
    removal_table: Optional[Path] = None
    mat_script: Optional[Path] = None
    mat_command: Optional[str] = None


def build_removal_list(
    verdicts: HitVerdicts, *, dataset: Optional[str] = None, source: str = "scan"
) -> RemovalList:
    """Build a :class:`~mito_filter.emclarity.matio.RemovalList` from the flagged hits (SPEC §9.1).

    Scoped to ``verdicts.tomo`` and keyed by the csv/geometry **row index** with the euler triple
    as a cross-check — **no position** (positions drift across alignment cycles), and **not** the
    per-tomo col4 id (that is not the ``.mat`` global id; see :mod:`mito_filter.emclarity.matio`).
    When the verdicts carry no euler, a zero ``(M, 3)`` cross-check is used (the row-index key
    still applies).

    Args:
        verdicts: The scan verdicts.
        dataset: subTomoMeta project label (defaults to ``verdicts.dataset``).
        source: Provenance string stamped into the list.

    Returns:
        The :class:`RemovalList` of flagged hits (empty when nothing is removed).
    """
    ids = verdicts.removed_subtomo_ids()
    eul = verdicts.removed_euler()
    if eul is None:
        eul = np.zeros((ids.shape[0], 3), dtype=np.float64)
    rows = np.asarray(verdicts.row_ids, dtype=np.int64)[verdicts.removed_mask]
    return RemovalList(
        ids,
        eul,
        rows,
        tomo=verdicts.tomo,
        dataset=dataset if dataset is not None else verdicts.dataset,
        source=source,
    )


def write_debug_csv(verdicts: HitVerdicts, src_csv: Path, dst_csv: Path) -> Path:
    """Write a col26 debug copy of ``src_csv`` reflecting the keep/remove decisions (SPEC §2).

    Row order is preserved exactly; only column 26 changes (keep ``1`` / remove ``-9999``). The
    full-length flag vector is addressed by :attr:`HitVerdicts.row_ids`, so it stays aligned even
    if the candidate source dropped rows.

    Args:
        verdicts: The scan verdicts.
        src_csv: The source ``<base>.csv``.
        dst_csv: Destination path for the debug csv.

    Returns:
        The written debug csv path.
    """
    from ..emclarity.constants import ACTIVE_COL
    from ..emclarity.csv_io import read_csv_matrix, write_active_column

    src_csv = Path(src_csv)
    dst_csv = Path(dst_csv)
    dst_csv.parent.mkdir(parents=True, exist_ok=True)
    # Seed the flag vector from the source's EXISTING col26 so a row that was already removed
    # (REMOVED_FLAG) but dropped by the candidate source (e.g. active_only=True) stays removed
    # instead of being resurrected to 1. Scanned rows overlay their verdict at their row_id.
    base = read_csv_matrix(src_csv)[:, ACTIVE_COL].astype(np.int64)
    flags = verdicts.full_active_flags(base.shape[0], base=base)
    return write_active_column(src_csv, flags, dst_csv)


def write_removal_json(verdicts: HitVerdicts, path: Path, *, source: str = "scan") -> Path:
    """Write the subtomo-id-keyed removal list as JSON (a runnable machine-readable output).

    Args:
        verdicts: The scan verdicts.
        path: Destination ``.json`` path (parent dirs created).
        source: Provenance string.

    Returns:
        The written JSON path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = verdicts.removed_subtomo_ids()
    eul = verdicts.removed_euler()
    removals: List[Dict[str, Any]] = []
    for i, sid in enumerate(ids):
        entry: Dict[str, Any] = {"subtomo_id": int(sid)}
        if eul is not None:
            entry["euler"] = [float(x) for x in np.asarray(eul)[i]]
        removals.append(entry)
    payload: Dict[str, Any] = {
        "dataset": verdicts.dataset,
        "tomo": verdicts.tomo,
        "source": source,
        "tau": verdicts.tau,
        "n": verdicts.n,
        "n_removed": verdicts.n_removed,
        "key": "subtomo_id",
        "removals": removals,
        "provenance": dict(verdicts.provenance),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def write_removal_table(verdicts: HitVerdicts, path: Path, *, source: str = "scan") -> Path:
    """Write the ``matio`` text removal table (subtomo_id + angle triple).

    Args:
        verdicts: The scan verdicts.
        path: Destination path (parent dirs created).
        source: Provenance string.

    Returns:
        The written table path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_removal_list(path, build_removal_list(verdicts, source=source))


def render_mat_apply(
    verdicts: HitVerdicts,
    *,
    mat_path: Path,
    removal_table: Path,
    script_path: Path,
    cycle: int,
) -> str:
    """Render (and write) the gated MATLAB-on-salina apply script; return the run command.

    Nothing here runs MATLAB — the script is written to ``script_path`` for review and the
    corresponding salina command is returned (SPEC §9.1). The removal table must already have been
    written (e.g. via :func:`write_removal_table`).

    Args:
        verdicts: The scan verdicts (only its dataset/counts inform the header).
        mat_path: Path to the subTomoMeta ``.mat`` on salina.
        removal_table: Path to the written text removal table.
        script_path: Where to write the rendered ``.m`` script.
        cycle: The classification cycle whose geometry is edited.

    Returns:
        The salina apply shell command (documented stub; not executed).
    """
    script_path = Path(script_path)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script = render_matlab_apply_script(
        Path(mat_path), Path(removal_table), tomo=verdicts.tomo, cycle=cycle
    )
    script_path.write_text(script)
    return render_salina_apply_command(
        Path(mat_path), Path(removal_table), cycle=cycle, script_path=script_path
    )


def writeback(
    verdicts: HitVerdicts,
    *,
    out_dir: Path,
    src_csv: Optional[Path] = None,
    debug_csv: bool = True,
    removal_json: bool = True,
    removal_table: bool = False,
    mat_apply: bool = False,
    mat_path: Optional[Path] = None,
    cycle: Optional[int] = None,
    source: str = "scan",
) -> WritebackResult:
    """Emit all requested writeback artifacts for one tomogram's verdicts.

    Args:
        verdicts: The scan verdicts.
        out_dir: Output directory for the generated files (created if absent).
        src_csv: Source ``<base>.csv`` — required to write the col26 debug csv.
        debug_csv: Write the col26 debug csv (needs ``src_csv``).
        removal_json: Write the subtomo-id-keyed removal JSON (the runnable output).
        removal_table: Also write the ``matio`` text removal table.
        mat_apply: Render (never run) the MATLAB apply stub (needs ``mat_path`` + ``cycle``;
            forces the removal table on).
        mat_path: subTomoMeta ``.mat`` path (for the apply stub only).
        cycle: Classification cycle number (for the apply stub only).
        source: Provenance string stamped into the outputs.

    Returns:
        The :class:`WritebackResult` with the paths of every artifact written.

    Raises:
        ValueError: If ``mat_apply`` is requested without both ``mat_path`` and ``cycle``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = verdicts.tomo

    dbg: Optional[Path] = None
    if debug_csv and src_csv is not None:
        dbg = write_debug_csv(verdicts, Path(src_csv), out_dir / f"{base}_col26.csv")

    rem_json: Optional[Path] = None
    if removal_json:
        rem_json = write_removal_json(verdicts, out_dir / f"{base}_removals.json", source=source)

    rem_table: Optional[Path] = None
    mat_script: Optional[Path] = None
    mat_command: Optional[str] = None
    if mat_apply:
        if mat_path is None or cycle is None:
            raise ValueError("mat_apply requires both mat_path and cycle")
        removal_table = True
    if removal_table:
        rem_table = write_removal_table(verdicts, out_dir / f"{base}_removals.txt", source=source)
    if mat_apply and mat_path is not None and cycle is not None and rem_table is not None:
        mat_script = out_dir / f"{base}_apply_cycle{cycle:03d}.m"
        mat_command = render_mat_apply(
            verdicts,
            mat_path=Path(mat_path),
            removal_table=rem_table,
            script_path=mat_script,
            cycle=cycle,
        )

    return WritebackResult(
        n_removed=verdicts.n_removed,
        debug_csv=dbg,
        removal_json=rem_json,
        removal_table=rem_table,
        mat_script=mat_script,
        mat_command=mat_command,
    )
