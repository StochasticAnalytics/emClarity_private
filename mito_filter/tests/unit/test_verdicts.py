"""HitVerdicts col26 flag assembly (finding-5 regression) + writeback base-seeding."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from mito_filter.emclarity.constants import ACTIVE_COL, N_CSV_COLS, REMOVED_FLAG
from mito_filter.scan.verdicts import HitVerdicts
from mito_filter.scan.writeback import build_removal_list, write_debug_csv


def _verdicts(row_ids: Sequence[int], keep: Sequence[bool]) -> HitVerdicts:
    n = len(row_ids)
    return HitVerdicts(
        tomo="t",
        row_ids=np.asarray(row_ids, dtype=np.int64),
        subtomo_ids=np.arange(n, dtype=np.int64) + 1,  # per-tomo ids 1..N (NOT global)
        keep_prob=np.where(np.asarray(keep), 1.0, 0.0),
        keep=np.asarray(keep, dtype=bool),
        tau=0.5,
    )


def test_full_active_flags_default_all_ones() -> None:
    v = _verdicts([0, 2], [True, False])
    flags = v.full_active_flags(4)
    # rows 0,2 scanned; 2 removed. rows 1,3 unscanned -> default 1.
    assert flags.tolist() == [1, 1, REMOVED_FLAG, 1]


def test_full_active_flags_base_preserves_already_removed() -> None:
    # Regression (finding 5): a row absent from the verdicts that is ALREADY removed in the
    # source (base=REMOVED_FLAG) must stay removed, not be resurrected to 1.
    v = _verdicts([0, 2], [True, False])  # only rows 0 and 2 scanned
    base = np.array([1, REMOVED_FLAG, 1, 1], dtype=np.int64)  # row 1 already removed upstream
    flags = v.full_active_flags(4, base=base)
    assert flags.tolist() == [1, REMOVED_FLAG, REMOVED_FLAG, 1]


def _make_csv(path: Path, col26: Sequence[int]) -> None:
    rows = []
    for i, flag in enumerate(col26):
        r = [f"{i}.0"] * N_CSV_COLS
        r[ACTIVE_COL] = str(int(flag))
        rows.append(" ".join(r))
    path.write_text("\n".join(rows) + "\n")


def test_write_debug_csv_keeps_source_removed_rows(tmp_path: Path) -> None:
    # A source csv with row 1 already removed; verdicts only scanned rows 0 and 2 (row 2 flagged).
    src = tmp_path / "src.csv"
    _make_csv(src, [1, REMOVED_FLAG, 1, 1])
    v = _verdicts([0, 2], [True, False])
    dst = tmp_path / "dbg.csv"
    write_debug_csv(v, src, dst)
    out = np.loadtxt(dst)
    assert out[:, ACTIVE_COL].tolist() == [1.0, float(REMOVED_FLAG), float(REMOVED_FLAG), 1.0]


def test_writeback_build_removal_list_threads_rows_and_tomo() -> None:
    # Regression (finding 1): the RemovalList must carry the csv ROW INDEX + tomo (the .mat key),
    # not just the per-tomo col4 id. rows [1,3] flagged -> row_ids [1,3], tomo threaded.
    v = _verdicts([0, 1, 2, 3], [True, False, True, False])
    rl = build_removal_list(v, source="scan")
    assert rl.tomo == "t"
    assert rl.row_ids.tolist() == [1, 3]
    assert rl.subtomo_ids.tolist() == [2, 4]  # per-tomo provenance, not the key
