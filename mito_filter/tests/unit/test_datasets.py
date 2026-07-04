"""Unit tests for datasets/base.py + datasets/emclarity_tm.py (discovery)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mito_filter.datasets.base import SearchRef, TomogramRef
from mito_filter.datasets.emclarity_tm import EmclarityTMSource, discover_round
from mito_filter.fields._tomo import DEFAULT_REC_DIR

from .fake_round import make_fake_round

SAMPLE_BASE = "H99_2_100_1_bin5"
REAL_SHAPE = (448, 942, 662)
# round_4's authentic full 112-tomo set (its live convmap dir is mid-regeneration).
ROUND4_ORIG = Path(
    "/scratch/siracusa/full_enchilada_3/six_hours_round_4/convmap_wedgeType_2_bin5.orig"
)
ROUND4_LIVE = Path("/scratch/siracusa/full_enchilada_3/six_hours_round_4/convmap_wedgeType_2_bin5")


# --------------------------------------------------------------------------- offline (fake) tests


def test_discover_fake_round_structure(tmp_path: Path) -> None:
    convdir = make_fake_round(tmp_path, [SAMPLE_BASE, "H99_2_101_1_bin5"], shape=(4, 5, 6))
    search = discover_round(convdir)
    assert isinstance(search, SearchRef)
    assert search.n == 2
    assert [t.base for t in search] == ["H99_2_100_1_bin5", "H99_2_101_1_bin5"]  # sorted
    assert search.grid is not None and search.grid.shape == (4, 5, 6)
    assert search.grid.apix == 12.5


def test_tomogram_ref_siblings_and_path_parse(tmp_path: Path) -> None:
    convdir = make_fake_round(tmp_path, [SAMPLE_BASE])
    t: TomogramRef = discover_round(convdir).get(SAMPLE_BASE)
    # seven core files all resolve + exist
    assert t.convmap_path.name == f"{SAMPLE_BASE}_convmap.mrc"
    assert t.csv_path.name == f"{SAMPLE_BASE}.csv"
    assert t.templateidx_path.name == f"{SAMPLE_BASE}.templateIDX"
    assert t.angles_list_path.name == f"{SAMPLE_BASE}_angles.list"
    assert t.is_complete()
    assert t.missing_core_files() == []
    # .path parsing: rec -> alt_cache (not the recorded ./cache); ctf tilt -> round dir relative
    assert t.rec_path == DEFAULT_REC_DIR / f"{SAMPLE_BASE}.rec"
    assert t.ctf_tilt_path is not None
    assert t.ctf_tilt_path.name == f"{SAMPLE_BASE}_ali1_ctf.tlt"
    assert t.ctf_tilt_path.exists()
    # csv_source duck-typing surface
    assert t.convmap_dir == convdir


def test_optional_angles_mrc_detection(tmp_path: Path) -> None:
    convdir_no = make_fake_round(tmp_path / "a", [SAMPLE_BASE], with_angles_mrc=False)
    convdir_yes = make_fake_round(tmp_path / "b", [SAMPLE_BASE], with_angles_mrc=True)
    assert discover_round(convdir_no).get(SAMPLE_BASE).angles_mrc_path is None
    got = discover_round(convdir_yes).get(SAMPLE_BASE).angles_mrc_path
    assert got is not None and got.name == f"{SAMPLE_BASE}_angles.mrc"


def test_read_grid_from_header_false_uses_expected_shape(tmp_path: Path) -> None:
    convdir = make_fake_round(tmp_path, [SAMPLE_BASE], shape=(4, 5, 6))
    src = EmclarityTMSource(convdir, read_grid_from_header=False, expected_shape=(448, 942, 662))
    assert src.discover().get(SAMPLE_BASE).grid.shape == (448, 942, 662)


def test_discover_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        EmclarityTMSource(tmp_path / "nope").discover()


def test_get_unknown_base_raises(tmp_path: Path) -> None:
    convdir = make_fake_round(tmp_path, [SAMPLE_BASE])
    with pytest.raises(KeyError):
        discover_round(convdir).get("not_a_tomo")


# --------------------------------------------------------------------------- real-data tests


@pytest.mark.skipif(not ROUND4_ORIG.is_dir(), reason="real round_4 full set not present")
def test_discover_round4_full_is_112() -> None:
    search = EmclarityTMSource(ROUND4_ORIG).discover()
    assert search.n == 112
    t = search.get(SAMPLE_BASE)
    assert t.grid.shape == REAL_SHAPE
    assert t.grid.apix == 12.5
    assert t.is_complete()
    assert t.rec_path == DEFAULT_REC_DIR / f"{SAMPLE_BASE}.rec"
    assert t.ctf_tilt_path is not None
    assert t.ctf_tilt_path.name == "H99_2_100_ali1_ctf.tlt"


@pytest.mark.skipif(not ROUND4_LIVE.is_dir(), reason="real round_4 live dir not present")
def test_discover_round4_live_matches_glob() -> None:
    search = EmclarityTMSource(ROUND4_LIVE).discover()
    n_glob = len(list(ROUND4_LIVE.glob("*_convmap.mrc")))
    assert search.n == n_glob
    assert n_glob >= 1
    t = search.get(SAMPLE_BASE)
    assert t.grid.shape == REAL_SHAPE
    # the live re-run emits the dense angle field (SPEC §7)
    assert t.angles_mrc_path is not None
