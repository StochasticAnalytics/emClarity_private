"""CsvPeakSource tests: reproduce the real H99_2_100_1_bin5 peak set (SPEC §2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from mito_filter.candidates.csv_source import CsvPeakSource, _resolve_csv_path
from mito_filter.candidates.source import CandidateSet
from mito_filter.core.grid import VoxelGrid
from mito_filter.emclarity.constants import APIX_A, CONVMAP_SHAPE
from mito_filter.emclarity.templateidx import read_pos

_N_PEAKS = 1249
_TEMPLATE_COUNTS = (777, 275, 197)  # SPEC §2, refs 1/2/3


def _grid() -> VoxelGrid:
    return VoxelGrid(CONVMAP_SHAPE, APIX_A)


def test_real_csv_reproduces_peak_count_and_positions(real_csv_path: Path) -> None:
    cand = CsvPeakSource().read(real_csv_path, _grid())
    assert isinstance(cand, CandidateSet)
    assert cand.n == _N_PEAKS

    # Cross-check voxel positions against the sibling .pos (raw x,y,z -> z,y,x).
    pos_zyx = read_pos(real_csv_path.with_suffix(".pos"))[:, ::-1]
    assert cand.coords_zyx.shape == (_N_PEAKS, 3)
    assert np.abs(cand.coords_zyx - pos_zyx).max() < 1e-5

    # row_ids are the stable 0-based csv row index (SPEC §2 sibling alignment).
    assert cand.row_ids is not None
    np.testing.assert_array_equal(cand.row_ids, np.arange(_N_PEAKS))


def test_real_csv_attrs_present_and_consistent(real_csv_path: Path) -> None:
    cand = CsvPeakSource().read(real_csv_path, _grid())
    for key in ("cc", "normal", "euler", "subtomo_id", "active", "template_idx"):
        assert key in cand.attrs, key
    assert cand.get("normal").shape == (_N_PEAKS, 3)
    assert cand.get("euler").shape == (_N_PEAKS, 3)
    # raw TM output is all-active (SPEC §6).
    assert bool(np.asarray(cand.get("active")).all())
    # normals are unit length (C12-invariant 3rd matrix column).
    nrm = np.linalg.norm(cand.get("normal"), axis=1)
    np.testing.assert_allclose(nrm, 1.0, atol=1e-3)
    # winning-template histogram matches SPEC §2.
    counts = np.bincount(cand.get("template_idx"), minlength=4)[1:4]
    assert tuple(counts.tolist()) == _TEMPLATE_COUNTS


def test_row_id_not_leaked_as_attr(real_csv_path: Path) -> None:
    cand = CsvPeakSource().read(real_csv_path, _grid())
    assert "row_id" not in cand.attrs  # promoted to CandidateSet.row_ids


def test_candidates_via_tomo_ref(real_csv_path: Path) -> None:
    @dataclass
    class _Tomo:
        csv_path: Path

    cand = CsvPeakSource().candidates(_Tomo(real_csv_path), _grid())  # type: ignore[arg-type]
    assert cand.n == _N_PEAKS


def test_active_only_is_noop_on_raw_output(real_csv_path: Path) -> None:
    cand = CsvPeakSource(active_only=True).read(real_csv_path, _grid())
    assert cand.n == _N_PEAKS  # nothing removed: all raw rows active


def test_resolve_csv_path_variants(tmp_path: Path) -> None:
    csv = tmp_path / "H99_2_100_1_bin5.csv"
    csv.write_text("x")

    # bare path (with and without suffix)
    assert _resolve_csv_path(csv) == csv
    assert _resolve_csv_path(tmp_path / "H99_2_100_1_bin5") == csv

    @dataclass
    class _A:
        csv_path: Path

    @dataclass
    class _B:
        base: str
        dir: Path

    assert _resolve_csv_path(_A(csv)) == csv
    assert _resolve_csv_path(_B("H99_2_100_1_bin5", tmp_path)) == csv

    with pytest.raises(TypeError):
        _resolve_csv_path(object())
