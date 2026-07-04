"""matio removal sink: per-tomo, row-index-keyed apply (SPEC §9.1; finding-1 regression).

The apply must scope to a SINGLE tomo's geometry and key by ROW INDEX -- never by the csv col4
id (per-tomo 1..N, reset per tomo) against the .mat col4 (global). These tests lock that.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mito_filter.core.points import PointCloud
from mito_filter.emclarity.matio import (
    RemovalList,
    build_removal_list,
    read_removal_list,
    render_matlab_apply_script,
    write_removal_list,
)


def _cloud() -> PointCloud:
    # 4 peaks; per-tomo col4 ids 1..4 (NOT global), rows 0..3, peaks 1 and 3 inactive.
    xyz = np.zeros((4, 3), dtype=np.float64)
    attrs = {
        "active": np.array([True, False, True, False]),
        "subtomo_id": np.array([1, 2, 3, 4], dtype=np.int64),
        "row_id": np.arange(4, dtype=np.int64),
        "euler": np.array(
            [[10.0, 20.0, 0.0], [11.0, 21.0, 1.0], [12.0, 22.0, 2.0], [13.0, 23.0, 3.0]]
        ),
    }
    return PointCloud(xyz, attrs)


def test_build_removal_list_keys_by_row_not_col4() -> None:
    rl = build_removal_list(_cloud(), tomo="H99_2_100_1_bin5", dataset="ds", source="scan")
    assert rl.n == 2
    assert rl.tomo == "H99_2_100_1_bin5"
    # removed rows are 1 and 3 (0-based); their per-tomo ids 2 and 4 are provenance only.
    assert rl.row_ids.tolist() == [1, 3]
    assert rl.subtomo_ids.tolist() == [2, 4]
    assert np.allclose(rl.euler[0], [11.0, 21.0, 1.0])


def test_removal_list_roundtrip_1based_rows(tmp_path: Path) -> None:
    rl = build_removal_list(_cloud(), tomo="tomoA", dataset="ds", source="scan")
    p = tmp_path / "rem.txt"
    write_removal_list(p, rl)
    text = p.read_text()
    # rows are written 1-based for MATLAB: 0-based 1,3 -> 2,4.
    data_rows = [ln for ln in text.splitlines() if not ln.startswith("#")]
    assert data_rows[0].split()[0] == "2"
    assert data_rows[1].split()[0] == "4"
    assert "tomo=tomoA" in text
    back = read_removal_list(p)
    assert back.tomo == "tomoA"
    assert back.row_ids.tolist() == [1, 3]  # back to 0-based
    assert back.subtomo_ids.tolist() == [2, 4]
    assert np.allclose(back.euler, rl.euler)


def test_empty_removal_list_roundtrips(tmp_path: Path) -> None:
    rl = RemovalList(
        np.zeros(0, dtype=np.int64),
        np.zeros((0, 3), dtype=np.float64),
        np.zeros(0, dtype=np.int64),
        tomo="t",
    )
    p = tmp_path / "empty.txt"
    write_removal_list(p, rl)
    back = read_removal_list(p)
    assert back.n == 0 and back.tomo == "t"


def test_matlab_script_scopes_by_tomo_and_keys_by_row() -> None:
    script = render_matlab_apply_script(
        mat_path="/x/meta.mat",  # type: ignore[arg-type]
        removal_path="/x/rem.txt",  # type: ignore[arg-type]
        tomo="H99_2_100_1_bin5",
        cycle=4,
    )
    # Scoped to this tomo's geometry (dynamic field access on the tomo name).
    assert "RawAlign.('H99_2_100_1_bin5')" in script
    assert "cycle004" in script
    # Keyed by row index (R(:,1)), NOT by col4 matching.
    assert "rows = R(:,1)" in script
    assert "g(:,4)" not in script  # the buggy col4 match must be gone
    assert "find(" not in script
    # Row-order safety assert on the constant col9 + the angle-triple cross-check.
    assert "assert(all(g(:,9) == g(1,9))" in script
    assert "g(r,14:16)" in script
    assert "g(r,26) = -9999" in script
