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
