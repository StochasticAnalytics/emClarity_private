"""Unit tests for cli.py (argument parsing + the wired ``scan`` subcommand)."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from mito_filter.cli import _build_combiner, build_parser, main

from .fake_round import make_fake_round

BASES = ["H99_2_100_1_bin5", "H99_2_101_1_bin5", "H99_2_102_1_bin5"]


class _NamedConstraint:
    def __init__(self, name: str) -> None:
        self.name = name


def test_build_combiner_accepts_positional_weight_list() -> None:
    """The round_4_physics.yaml combiner lists weights positionally (aligned to constraint order),
    not as a {name: w} map -- _build_combiner must accept both."""
    cons = [_NamedConstraint("gold_ice_cluster"), _NamedConstraint("surface_coherence")]
    cfg = {"combiner": {"kind": "logit", "weights": [3.0, 1.0], "bias": -1.5}}
    comb = _build_combiner(cfg, cons)
    assert list(comb.weights) == [3.0, 1.0]
    assert comb.bias == -1.5


def test_build_combiner_accepts_weight_mapping() -> None:
    cons = [_NamedConstraint("gold_ice_cluster"), _NamedConstraint("surface_coherence")]
    cfg = {"combiner": {"weights": {"surface_coherence": 2.0}}}
    comb = _build_combiner(cfg, cons)
    assert comb.weights[1] == 2.0


def test_build_combiner_rejects_mismatched_weight_list() -> None:
    import pytest

    cons = [_NamedConstraint("gold_ice_cluster"), _NamedConstraint("surface_coherence")]
    with pytest.raises(ValueError, match="weights list length"):
        _build_combiner({"combiner": {"weights": [1.0, 2.0, 3.0]}}, cons)


def test_build_parser_returns_parser() -> None:
    parser = build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    args = parser.parse_args(["scan", "--config", "c.yaml", "--dry-run"])
    assert args.command == "scan"
    assert args.dry_run is True


def test_no_command_prints_help_returns_1(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main([]) == 1
    assert "usage" in capsys.readouterr().out.lower()


def test_scan_missing_data_dir_returns_2(tmp_path: Path) -> None:
    # no --data-dir and an empty config -> configuration error
    cfg = tmp_path / "empty.yaml"
    cfg.write_text("{}\n")
    assert main(["scan", "--config", str(cfg)]) == 2


def test_scan_nonexistent_data_dir_returns_2(tmp_path: Path) -> None:
    assert main(["scan", "--data-dir", str(tmp_path / "nope")]) == 2


def test_scan_dry_run_on_fake_round(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    convdir = make_fake_round(tmp_path, BASES)
    rc = main(["scan", "--data-dir", str(convdir), "--dry-run"])
    assert rc == 0
    assert "discovered 3 tomograms" in capsys.readouterr().out


def test_scan_runs_and_is_resumable(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    convdir = make_fake_round(tmp_path, BASES)
    work = tmp_path / "work"
    rc = main(["scan", "--data-dir", str(convdir), "--work-dir", str(work)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "done=3" in out
    # sentinels written -> a rerun skips every tomo
    rc2 = main(["scan", "--data-dir", str(convdir), "--work-dir", str(work)])
    assert rc2 == 0
    assert "skipped=3" in capsys.readouterr().out


def test_scan_reads_data_dir_from_config(tmp_path: Path) -> None:
    convdir = make_fake_round(tmp_path, BASES)
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.safe_dump({"data_dir": str(convdir)}))
    assert (
        main(["scan", "--config", str(cfg), "--work-dir", str(tmp_path / "w"), "--limit", "1"]) == 0
    )


def test_unimplemented_subcommands_return_2(capsys) -> None:  # type: ignore[no-untyped-def]
    for cmd in ("optimize", "gen-field", "writeback", "validate"):
        assert main([cmd]) == 2
    assert "not yet implemented" in capsys.readouterr().out
