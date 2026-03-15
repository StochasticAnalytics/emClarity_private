"""Unit tests for _detect_best_resolution logic branches.

Covers the two guards added in TASK-018:
  1. Invalid-frequency branch: freq <= 0 or freq > 1.0 are skipped.
  2. Implausible-resolution branch: angstrom > 200 is discarded with a warning.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.api.v1_projects import _detect_best_resolution


class TestDetectBestResolutionInvalidFrequency:
    """Branch 1 – freq <= 0 or freq > 1.0 lines are silently skipped."""

    def test_zero_frequency_is_ignored(self, tmp_path: Path) -> None:
        """A line with freq == 0 must be discarded; no ZeroDivisionError."""
        fsc_dir = tmp_path / "FSC"
        fsc_dir.mkdir()
        fsc_file = fsc_dir / "test_fsc_GLD.txt"
        # freq=0 would cause 1/freq → ZeroDivisionError and must be skipped
        fsc_file.write_text("0.0 0.900\n")
        assert _detect_best_resolution(tmp_path) is None

    def test_negative_frequency_is_ignored(self, tmp_path: Path) -> None:
        fsc_dir = tmp_path / "FSC"
        fsc_dir.mkdir()
        (fsc_dir / "test_fsc_GLD.txt").write_text("-0.1 0.900\n")
        assert _detect_best_resolution(tmp_path) is None

    def test_frequency_above_one_is_ignored(self, tmp_path: Path) -> None:
        """freq > 1.0 corresponds to sub-1 Å resolution – reject as implausible units."""
        fsc_dir = tmp_path / "FSC"
        fsc_dir.mkdir()
        (fsc_dir / "test_fsc_GLD.txt").write_text("1.5 0.900\n")
        assert _detect_best_resolution(tmp_path) is None

    def test_valid_frequency_accepted_when_mixed_with_invalid(self, tmp_path: Path) -> None:
        """Only valid freq lines contribute; invalid freq lines are skipped."""
        fsc_dir = tmp_path / "FSC"
        fsc_dir.mkdir()
        fsc_file = fsc_dir / "test_fsc_GLD.txt"
        # invalid freq=0, then valid freq=0.1 (→ 10.0 Å), fsc >= 0.143
        fsc_file.write_text("0.0 0.900\n1.5 0.900\n0.1 0.500\n")
        result = _detect_best_resolution(tmp_path)
        assert result == pytest.approx(10.0, rel=1e-3)


class TestDetectBestResolutionImplausibleAngstrom:
    """Branch 2 – resolutions > 200 Å are discarded with a warning log."""

    def test_resolution_above_200_discarded(self, tmp_path: Path) -> None:
        """freq = 0.004 → 250 Å must be rejected; function returns None."""
        fsc_dir = tmp_path / "FSC"
        fsc_dir.mkdir()
        # 1 / 0.004 = 250 Å  → above the 200 Å upper bound
        (fsc_dir / "test_fsc_GLD.txt").write_text("0.004 0.900\n")
        assert _detect_best_resolution(tmp_path) is None

    def test_resolution_exactly_200_accepted(self, tmp_path: Path) -> None:
        """Boundary value: 1/0.005 == 200.0 Å is on the inclusive boundary and must be kept."""
        fsc_dir = tmp_path / "FSC"
        fsc_dir.mkdir()
        (fsc_dir / "test_fsc_GLD.txt").write_text("0.005 0.900\n")
        result = _detect_best_resolution(tmp_path)
        assert result == pytest.approx(200.0, rel=1e-3)

    def test_resolution_just_above_200_discarded(self, tmp_path: Path) -> None:
        """A resolution of ~200.8 Å (freq ~0.00498) is above 200 and must be discarded."""
        fsc_dir = tmp_path / "FSC"
        fsc_dir.mkdir()
        # 1 / 0.00498 ≈ 200.8 Å
        (fsc_dir / "test_fsc_GLD.txt").write_text("0.00498 0.900\n")
        assert _detect_best_resolution(tmp_path) is None

    def test_implausible_file_does_not_pollute_best_from_good_file(
        self, tmp_path: Path
    ) -> None:
        """When one FSC file has only implausible resolutions and another has valid ones,
        the valid result is returned."""
        fsc_dir = tmp_path / "FSC"
        fsc_dir.mkdir()
        # Bad file: all resolutions > 200 Å
        (fsc_dir / "bad_fsc_GLD.txt").write_text("0.004 0.900\n")
        # Good file: 0.1 → 10.0 Å (valid)
        (fsc_dir / "good_fsc_GLD.txt").write_text("0.1 0.500\n")
        result = _detect_best_resolution(tmp_path)
        assert result == pytest.approx(10.0, rel=1e-3)

    def test_implausible_warning_logged(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """A discarded implausible resolution must emit a WARNING log."""
        import logging

        fsc_dir = tmp_path / "FSC"
        fsc_dir.mkdir()
        (fsc_dir / "test_fsc_GLD.txt").write_text("0.004 0.900\n")

        with caplog.at_level(logging.WARNING, logger="backend.api.v1_projects"):
            _detect_best_resolution(tmp_path)

        assert any("200" in record.message for record in caplog.records), (
            "Expected a warning mentioning the 200 Å upper bound"
        )
