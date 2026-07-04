"""Unit tests for exec/runner.py (TomogramRunner resumability)."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from mito_filter.core.grid import VoxelGrid
from mito_filter.datasets.base import TomogramRef
from mito_filter.exec.runner import TomogramRunner


def _ref(root: Path, base: str) -> TomogramRef:
    """Build a minimal TomogramRef (paths need not exist; the runner never reads them)."""
    d = root / "conv"
    grid = VoxelGrid(shape=(4, 5, 6), apix=12.5)
    return TomogramRef(
        base=base,
        convmap_path=d / f"{base}_convmap.mrc",
        csv_path=d / f"{base}.csv",
        pos_path=d / f"{base}.pos",
        templateidx_path=d / f"{base}.templateIDX",
        angles_list_path=d / f"{base}_angles.list",
        mod_path=d / f"{base}.mod",
        path_file=d / f"{base}.path",
        grid=grid,
    )


def test_sentinel_skip_on_rerun(tmp_path: Path) -> None:
    tomos = [_ref(tmp_path, f"t{i}") for i in range(3)]
    calls: List[str] = []

    def job(t: TomogramRef) -> str:
        calls.append(t.base)
        return t.base.upper()

    runner = TomogramRunner(tmp_path / "work")
    rep1 = runner.run(tomos, job)
    assert rep1.ok and rep1.n_done == 3 and rep1.n_skipped == 0
    assert sorted(calls) == ["t0", "t1", "t2"]
    assert [r.value for r in rep1.results] == ["T0", "T1", "T2"]
    assert all(runner.is_done(t) for t in tomos)

    calls.clear()
    rep2 = runner.run(tomos, job)
    assert rep2.n_skipped == 3 and rep2.n_done == 0
    assert calls == []  # nothing re-ran


def test_force_reruns_everything(tmp_path: Path) -> None:
    tomos = [_ref(tmp_path, f"t{i}") for i in range(3)]
    calls: List[str] = []

    def job(t: TomogramRef) -> str:
        calls.append(t.base)
        return t.base

    runner = TomogramRunner(tmp_path / "work")
    runner.run(tomos, job)
    calls.clear()
    rep = runner.run(tomos, job, force=True)
    assert rep.n_done == 3
    assert sorted(calls) == ["t0", "t1", "t2"]


def test_cache_probe_skips(tmp_path: Path) -> None:
    tomos = [_ref(tmp_path, f"t{i}") for i in range(3)]
    calls: List[str] = []

    def job(t: TomogramRef) -> str:
        calls.append(t.base)
        return t.base

    runner = TomogramRunner(tmp_path / "work")
    rep = runner.run(tomos, job, cache_exists=lambda t: t.base == "t1")
    assert rep.n_skipped == 1 and rep.n_done == 2
    assert "t1" not in calls and sorted(calls) == ["t0", "t2"]
    # t1 was skipped by cache, not by a sentinel
    assert not runner.is_done(tomos[1])


def test_failure_isolated_and_retried(tmp_path: Path) -> None:
    tomos = [_ref(tmp_path, f"t{i}") for i in range(3)]

    def job(t: TomogramRef) -> str:
        if t.base == "t2":
            raise ValueError("boom")
        return t.base

    runner = TomogramRunner(tmp_path / "work")
    rep = runner.run(tomos, job)
    assert rep.n_done == 2 and rep.n_failed == 1 and not rep.ok
    assert rep.failures[0].base == "t2" and "boom" in (rep.failures[0].error or "")
    # failed tomo left no sentinel -> retried next run
    assert runner.is_done(tomos[0]) and not runner.is_done(tomos[2])

    fixed_calls: List[str] = []

    def job_ok(t: TomogramRef) -> str:
        fixed_calls.append(t.base)
        return t.base

    rep2 = runner.run(tomos, job_ok)
    assert fixed_calls == ["t2"]  # only the previously-failed tomo re-runs
    assert rep2.n_done == 1 and rep2.n_skipped == 2


def test_clear_done_forces_single(tmp_path: Path) -> None:
    tomos = [_ref(tmp_path, "t0")]
    runner = TomogramRunner(tmp_path / "work")
    runner.run(tomos, lambda t: 1)
    assert runner.is_done(tomos[0])
    runner.clear_done(tomos[0])
    assert not runner.is_done(tomos[0])


def test_empty_input(tmp_path: Path) -> None:
    runner = TomogramRunner(tmp_path / "work")
    rep = runner.run([], lambda t: 1)
    assert rep.results == [] and rep.ok


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
