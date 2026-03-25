"""End-to-end CLI tests for ``python -m refinement``.

Invokes the CLI entry point via :func:`subprocess.run` to validate the
full pipeline contract: argument parsing, star file I/O, CTF refinement,
and diagnostic output.

Uses pre-generated fixtures from ``cond_001_df3000_ha50_ang5/`` (10 particles,
single tilt group at 0 degrees, 384x384 tiles) with the ribosome reference
volume.

Positive controls:
    - ``subprocess.run`` always returns a CompletedProcess (independent of
      our code).
    - Input star file always has 10 particles (verified before pipeline runs).

Negative controls:
    - Non-existent input files always produce exit code 1 (independent of
      pipeline logic).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ...ctf.star_io.emc_star_parser import parse_star_file

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "cond_001_df3000_ha50_ang5"
_REFERENCE_VOLUME = Path("/cisTEMdev/cistem_reference_images/ribo_ref.mrc")
# python/ directory — set as PYTHONPATH so that ``import refinement`` and
# ``import ctf`` resolve directly as top-level packages.
_PYTHON_DIR = Path(__file__).resolve().parents[3] / "python"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Skip marker for tests that depend on fixture data and the ribosome reference
# volume.  Applied per-class so TestCLIBadInputs (no external deps) always runs.
_needs_fixtures = pytest.mark.skipif(
    not _FIXTURE_DIR.exists() or not _REFERENCE_VOLUME.exists(),
    reason="Fixture data or ribosome reference volume not available",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_cli(*extra_args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run ``python -m python.refinement`` with the given arguments.

    The ``refinement`` package uses relative imports (``from ..ctf``) that
    require ``python/`` to be on PYTHONPATH so that ``refinement`` and ``ctf``
    resolve as top-level packages.

    Args:
        *extra_args: Additional CLI arguments appended after the base command.
        timeout: Maximum seconds before the subprocess is killed.

    Returns:
        Completed process with captured stdout/stderr.
    """
    existing = os.environ.get("PYTHONPATH", "")
    pythonpath = f"{_PYTHON_DIR}:{existing}" if existing else str(_PYTHON_DIR)
    env = {**os.environ, "PYTHONPATH": pythonpath}
    cmd = [sys.executable, "-m", "refinement", *extra_args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(_PROJECT_ROOT),
        env=env,
        check=False,
    )


def _count_data_lines(star_path: Path) -> int:
    """Count particle records in a star file using the canonical parser.

    Args:
        star_path: Path to the star file.

    Returns:
        Number of particle data lines.
    """
    particles, _ = parse_star_file(star_path)
    return len(particles)


def _parse_defocus_columns(star_path: Path) -> list[tuple[float, float, float]]:
    """Extract (defocus_1, defocus_2, defocus_angle) from each particle record.

    Args:
        star_path: Path to the star file.

    Returns:
        List of (df1, df2, angle) tuples, one per particle.
    """
    particles, _ = parse_star_file(star_path)
    return [(p["defocus_1"], p["defocus_2"], p["defocus_angle"]) for p in particles]


# ---------------------------------------------------------------------------
# Negative control: bad inputs produce exit code != 0
# ---------------------------------------------------------------------------


class TestCLIBadInputs:
    """Non-existent files produce a clean error exit, not a traceback."""

    def test_missing_files_exits_nonzero(self, tmp_path: Path) -> None:
        """Exit code 1 for non-existent input files (negative control)."""
        result = _run_cli(
            "--star", str(tmp_path / "nonexistent.star"),
            "--stack", str(tmp_path / "nonexistent.mrc"),
            "--ref", str(tmp_path / "nonexistent.mrc"),
            "--output", str(tmp_path / "output.star"),
        )
        assert result.returncode == 1


# ---------------------------------------------------------------------------
# Full pipeline run
# ---------------------------------------------------------------------------


@_needs_fixtures
class TestCLIFullPipeline:
    """Run the pipeline via subprocess and verify output artifacts."""

    @pytest.fixture()
    def output_dir(self, tmp_path: Path) -> Path:
        """Provide a clean temporary output directory."""
        return tmp_path

    def test_pipeline_exits_zero(self, output_dir: Path) -> None:
        """Pipeline with --maximum-iterations 5 exits successfully."""
        output_star = output_dir / "refined.star"
        result = _run_cli(
            "--star", str(_FIXTURE_DIR / "offset_small.star"),
            "--stack", str(_FIXTURE_DIR / "particles.mrc"),
            "--ref", str(_REFERENCE_VOLUME),
            "--output", str(output_star),
            "--maximum-iterations", "5",
            "--cpu",
        )
        assert result.returncode == 0, (
            f"CLI exited with code {result.returncode}.\n"
            f"stderr:\n{result.stderr}"
        )

    def test_output_star_exists_with_same_particle_count(
        self, output_dir: Path,
    ) -> None:
        """Output star file has the same number of particles as input."""
        output_star = output_dir / "refined.star"
        result = _run_cli(
            "--star", str(_FIXTURE_DIR / "offset_small.star"),
            "--stack", str(_FIXTURE_DIR / "particles.mrc"),
            "--ref", str(_REFERENCE_VOLUME),
            "--output", str(output_star),
            "--maximum-iterations", "5",
            "--cpu",
        )
        assert result.returncode == 0, f"stderr:\n{result.stderr}"

        assert output_star.exists(), "Output star file was not created"
        input_count = _count_data_lines(_FIXTURE_DIR / "offset_small.star")
        output_count = _count_data_lines(output_star)
        assert output_count == input_count, (
            f"Particle count mismatch: input={input_count}, output={output_count}"
        )

    def test_diagnostics_file_exists(self, output_dir: Path) -> None:
        """Diagnostics file is created alongside the output star file."""
        output_star = output_dir / "refined.star"
        result = _run_cli(
            "--star", str(_FIXTURE_DIR / "offset_small.star"),
            "--stack", str(_FIXTURE_DIR / "particles.mrc"),
            "--ref", str(_REFERENCE_VOLUME),
            "--output", str(output_star),
            "--maximum-iterations", "5",
            "--cpu",
        )
        assert result.returncode == 0, f"stderr:\n{result.stderr}"

        diag_path = output_star.with_name(f"{output_star.stem}_diagnostics.txt")
        assert diag_path.exists(), (
            f"Diagnostics file not found at {diag_path}"
        )

    def test_defocus_values_changed(self, output_dir: Path) -> None:
        """Refinement modifies defocus values from the input offsets."""
        output_star = output_dir / "refined.star"
        result = _run_cli(
            "--star", str(_FIXTURE_DIR / "offset_small.star"),
            "--stack", str(_FIXTURE_DIR / "particles.mrc"),
            "--ref", str(_REFERENCE_VOLUME),
            "--output", str(output_star),
            "--maximum-iterations", "5",
            "--cpu",
        )
        assert result.returncode == 0, f"stderr:\n{result.stderr}"

        input_defocus = _parse_defocus_columns(_FIXTURE_DIR / "offset_small.star")
        output_defocus = _parse_defocus_columns(output_star)

        assert len(output_defocus) == len(input_defocus)

        # At least one particle must have a changed defocus_1 value,
        # confirming the optimizer actually ran and modified parameters.
        any_changed = any(
            abs(out[0] - inp[0]) > 0.01
            for inp, out in zip(input_defocus, output_defocus, strict=True)
        )
        assert any_changed, (
            "No defocus values changed — refinement may not have run. "
            f"Input df1 values: {[d[0] for d in input_defocus]}, "
            f"Output df1 values: {[d[0] for d in output_defocus]}"
        )


# ---------------------------------------------------------------------------
# Debug option: --exit-after-n-tilts
# ---------------------------------------------------------------------------


@_needs_fixtures
class TestExitAfterNTilts:
    """Verify --exit-after-n-tilts limits processing."""

    def test_exit_after_one_tilt(self, tmp_path: Path) -> None:
        """With a single-tilt fixture, --exit-after-n-tilts 1 still exits 0.

        The cond_001 fixture has exactly 1 tilt group (tilt_+000.0.mrc),
        so --exit-after-n-tilts 1 should process that one group and exit.
        The diagnostics file should contain exactly 1 data row.
        """
        output_star = tmp_path / "refined_1tilt.star"
        result = _run_cli(
            "--star", str(_FIXTURE_DIR / "offset_small.star"),
            "--stack", str(_FIXTURE_DIR / "particles.mrc"),
            "--ref", str(_REFERENCE_VOLUME),
            "--output", str(output_star),
            "--maximum-iterations", "5",
            "--exit-after-n-tilts", "1",
            "--cpu",
        )
        assert result.returncode == 0, (
            f"CLI exited with code {result.returncode}.\n"
            f"stderr:\n{result.stderr}"
        )

        # Diagnostics file should have exactly 1 tilt group row
        diag_path = output_star.with_name("refined_1tilt_diagnostics.txt")
        assert diag_path.exists(), f"Diagnostics not found at {diag_path}"

        diag_lines = [
            line for line in diag_path.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert len(diag_lines) >= 2, (
            f"Diagnostics file has fewer than 2 lines (header + data); "
            f"content:\n{diag_path.read_text()!r}"
        )
        # First line is the header row, rest are data
        header_line = diag_lines[0]
        data_lines = diag_lines[1:]
        assert len(data_lines) == 1, (
            f"Expected 1 tilt group in diagnostics, got {len(data_lines)}. "
            f"Header: {header_line}"
        )
