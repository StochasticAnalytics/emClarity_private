"""Service for emClarity project management.

A project is a directory on disk that follows the emClarity convention:
  rawData/       - original tilt-series stacks
  fixedStacks/   - aligned stacks and metadata
  aliStacks/     - CTF-corrected aligned stacks
  cache/         - temporary reconstructions
  convmap/       - template search results
  FSC/           - resolution curves
  logFile/       - processing logs
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.models.project import Project, ProjectState, TiltSeries


# Directories that emClarity expects inside a project
_PROJECT_SUBDIRS = [
    "rawData",
    "fixedStacks",
    "aliStacks",
    "cache",
    "convmap",
    "FSC",
    "logFile",
]


class ProjectService:
    """Create, load, and inspect emClarity projects."""

    def create_project(self, name: str, path: str) -> Project:
        """Create a new project directory structure.

        Creates the project root and all expected subdirectories.
        Returns the initial project model.
        """
        project_dir = Path(path)
        project_dir.mkdir(parents=True, exist_ok=True)

        for subdir in _PROJECT_SUBDIRS:
            (project_dir / subdir).mkdir(exist_ok=True)

        return Project(
            name=name,
            path=str(project_dir.resolve()),
            state=ProjectState.UNINITIALIZED,
            current_cycle=0,
            tilt_series=[],
        )

    def load_project(self, path: str) -> Project:
        """Load project state by inspecting the directory structure.

        Determines the current pipeline state by checking which
        directories contain processed data.
        """
        project_dir = Path(path)
        if not project_dir.exists():
            raise FileNotFoundError(f"Project directory not found: {path}")

        name = project_dir.name
        state = self._detect_state(project_dir)
        cycle = self._detect_cycle(project_dir)
        tilt_series = self._discover_tilt_series(project_dir)
        particle_count = self._count_particles(project_dir)
        best_resolution = self._detect_best_resolution(project_dir)

        # Try to find the parameter file
        param_file = None
        for candidate in project_dir.glob("*.m"):
            param_file = str(candidate)
            break

        return Project(
            name=name,
            path=str(project_dir.resolve()),
            state=state,
            current_cycle=cycle,
            tilt_series=tilt_series,
            parameter_file=param_file,
            particle_count=particle_count,
            best_resolution_angstrom=best_resolution,
        )

    def list_tilt_series(self, path: str) -> list[TiltSeries]:
        """Discover tilt series in the project's rawData/ directory."""
        project_dir = Path(path)
        return self._discover_tilt_series(project_dir)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_state(project_dir: Path) -> ProjectState:
        """Infer the pipeline state from what data exists on disk."""
        # Check in reverse order of the pipeline (most advanced first)
        fsc_dir = project_dir / "FSC"
        if fsc_dir.exists() and any(fsc_dir.iterdir()):
            return ProjectState.CYCLE_N

        convmap_dir = project_dir / "convmap"
        if convmap_dir.exists() and any(convmap_dir.iterdir()):
            return ProjectState.PARTICLES_PICKED

        ali_dir = project_dir / "aliStacks"
        if ali_dir.exists() and any(ali_dir.iterdir()):
            return ProjectState.RECONSTRUCTED

        fixed_dir = project_dir / "fixedStacks"
        if fixed_dir.exists() and any(fixed_dir.glob("*.fixed")):
            return ProjectState.CTF_ESTIMATED

        if fixed_dir.exists() and any(fixed_dir.iterdir()):
            return ProjectState.TILT_ALIGNED

        return ProjectState.UNINITIALIZED

    @staticmethod
    def _detect_cycle(project_dir: Path) -> int:
        """Detect the latest refinement cycle number."""
        cycle_dirs = sorted(project_dir.glob("cycle*"))
        if not cycle_dirs:
            return 0

        # Extract the highest cycle number
        max_cycle = 0
        for d in cycle_dirs:
            try:
                n = int(d.name.replace("cycle", ""))
                max_cycle = max(max_cycle, n)
            except ValueError:
                continue
        return max_cycle

    @staticmethod
    def _discover_tilt_series(project_dir: Path) -> list[TiltSeries]:
        """Find tilt-series stacks in rawData/ and fixedStacks/."""
        tilt_series: list[TiltSeries] = []
        seen_names: set[str] = set()

        raw_dir = project_dir / "rawData"
        if raw_dir.exists():
            for stack_file in sorted(raw_dir.glob("*.st")):
                ts_name = stack_file.stem
                if ts_name in seen_names:
                    continue
                seen_names.add(ts_name)

                rawtlt = stack_file.with_suffix(".rawtlt")
                fixed_dir = project_dir / "fixedStacks"

                tilt_series.append(
                    TiltSeries(
                        name=ts_name,
                        stack_path=str(stack_file),
                        rawtlt_path=str(rawtlt) if rawtlt.exists() else None,
                        aligned=bool(
                            fixed_dir.exists()
                            and any(fixed_dir.glob(f"{ts_name}*"))
                        ),
                        ctf_estimated=bool(
                            fixed_dir.exists()
                            and any(fixed_dir.glob(f"{ts_name}*.fixed"))
                        ),
                    )
                )

        return tilt_series

    @staticmethod
    def _count_particles(project_dir: Path) -> int:
        """Count the number of particles found during template search.

        emClarity writes one .mrc file per tilt-series into convmap/ for
        each picked particle set.  We count the number of coordinate/map
        files present as a proxy for total particle count.

        Files named like ``<tsname>_convmap.mrc`` or ``<tsname>_pts.txt``
        are considered.  If plain coordinate text files exist, each line
        (excluding blank lines) counts as one particle.  Otherwise we fall
        back to counting .mrc files as a rough proxy.
        """
        convmap_dir = project_dir / "convmap"
        if not convmap_dir.exists():
            return 0

        total = 0

        # Prefer coordinate text files (*.txt) — each non-blank line is one
        # particle position.
        txt_files = list(convmap_dir.glob("*.txt"))
        if txt_files:
            for txt_file in txt_files:
                try:
                    lines = txt_file.read_text(encoding="utf-8").splitlines()
                    total += sum(1 for line in lines if line.strip())
                except OSError:
                    continue
            return total

        # Fall back to counting .mrc map files as a rough proxy.
        return sum(1 for _ in convmap_dir.glob("*.mrc"))

    @staticmethod
    def _detect_best_resolution(project_dir: Path) -> float | None:
        """Return the best (lowest) resolution in Ångströms from the FSC directory.

        emClarity writes FSC curve files into ``FSC/``.  Two naming
        conventions are supported:

        1. Filenames that embed the resolution, e.g.
           ``fsc_2.8A_cycle4.txt`` — the numeric portion before 'A' is
           extracted.
        2. Plain text FSC tables where the last non-blank line contains a
           resolution value as its first whitespace-separated column (in
           Ångströms).

        The *minimum* (best) resolution value found across all files is
        returned.  Returns ``None`` if the FSC directory is empty or no
        parseable resolution is found.
        """
        fsc_dir = project_dir / "FSC"
        if not fsc_dir.exists():
            return None

        best: float | None = None

        # Pattern: digits (and optional decimal) followed by 'A' or 'Ang' or
        # 'angstrom' in the filename, case-insensitive.
        fname_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*[Aa]", re.IGNORECASE)

        for fsc_file in fsc_dir.iterdir():
            if not fsc_file.is_file():
                continue

            # 1. Try to extract resolution from the filename.
            match = fname_pattern.search(fsc_file.name)
            if match:
                try:
                    value = float(match.group(1))
                    if value > 0 and (best is None or value < best):
                        best = value
                    continue
                except ValueError:
                    pass

            # 2. Try to parse the last non-blank line of plain-text FSC files.
            if fsc_file.suffix in {".txt", ".fsc", ".dat", ".csv"}:
                try:
                    text = fsc_file.read_text(encoding="utf-8")
                    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                    if lines:
                        first_col = lines[-1].split()[0]
                        value = float(first_col)
                        if value > 0 and (best is None or value < best):
                            best = value
                except (OSError, ValueError, IndexError):
                    continue

        return best
