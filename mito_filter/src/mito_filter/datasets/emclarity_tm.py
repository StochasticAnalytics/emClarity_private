"""EmclarityTMSource: discover an emClarity template-matching round into tomogram references.

A round's convmap directory (e.g.
``/scratch/siracusa/full_enchilada_3/six_hours_round_4/convmap_wedgeType_2_bin5``) holds, per
tomogram, the seven sibling files described in SPEC §1-§2 keyed by a common basename
``H99_2_<NNN>_1_bin5``. :class:`EmclarityTMSource` globs the ``*_convmap.mrc`` files, resolves each
basename's siblings, reads the convmap header for the shared grid, and parses ``<base>.path`` for
the reconstruction and ctf-tilt locations (SPEC §2, the ``.path`` manifest line).

The searched ``<base>.rec`` actually lives on the per-host ``alt_cache`` (SPEC §3), not the relative
``./cache`` the ``.path`` records, so the rec path is resolved against ``rec_dir``
(default :data:`mito_filter.fields._tomo.DEFAULT_REC_DIR`) while the ctf-tilt path is resolved
relative to the round directory (the convmap directory's parent).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from ..core.grid import VoxelGrid
from ..emclarity.constants import APIX_A, CONVMAP_SHAPE
from ..emclarity.mrc_io import read_header
from ..fields._tomo import DEFAULT_REC_DIR
from .base import DataSource, SearchRef, TomogramRef

__all__ = ["EmclarityTMSource", "discover_round"]

CONVMAP_SUFFIX: str = "_convmap.mrc"
"""The sibling suffix that marks a tomogram (one per basename in a round)."""


def _basename_of(convmap_path: Path) -> str:
    """Return the convmap basename by stripping :data:`CONVMAP_SUFFIX`.

    Args:
        convmap_path: Path ending in ``<base>_convmap.mrc``.

    Returns:
        The basename ``<base>`` (e.g. ``"H99_2_100_1_bin5"``).
    """
    name = convmap_path.name
    return name[: -len(CONVMAP_SUFFIX)]


def _parse_path_file(path_file: Path, round_dir: Path) -> Tuple[Optional[str], Optional[Path]]:
    """Parse ``<base>.path`` into (rec-extension, resolved ctf-tilt path).

    The single line is ``<base>,<cache_rel_dir>,<rec_ext>,<ctf_tilt_rel>`` (SPEC §2). The rec
    extension (``.rec``) is returned for basename resolution; the ctf-tilt path is resolved
    relative to ``round_dir`` (the convmap directory's parent, where ``fixedStacks/`` lives).

    Args:
        path_file: Path to ``<base>.path``.
        round_dir: The round directory the ctf-tilt path is relative to.

    Returns:
        ``(rec_ext, ctf_tilt_path)``; either element is ``None`` if the file is absent/malformed.
    """
    try:
        text = path_file.read_text().strip()
    except OSError:
        return None, None
    parts = [p.strip() for p in text.split(",")]
    rec_ext = parts[2] if len(parts) > 2 and parts[2] else None
    ctf_tilt: Optional[Path] = None
    if len(parts) > 3 and parts[3]:
        rel = parts[3]
        ctf_tilt = (round_dir / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
    return rec_ext, ctf_tilt


class EmclarityTMSource(DataSource):
    """Discover an emClarity TM round's per-tomogram seven-file sets (SPEC §1, §2, §9).

    Args:
        convmap_dir: The round's ``convmap_wedgeType_2_bin<N>`` directory.
        name: Optional label for the resulting :class:`SearchRef` (defaults to the round dir name,
            i.e. the convmap directory's parent name, else the convmap directory name).
        rec_dir: Directory holding ``<base>.rec`` (default
            :data:`mito_filter.fields._tomo.DEFAULT_REC_DIR`, ``/scratch/salina/alt_cache``).
        fixedstacks_dir: Directory holding ``*.erase`` gold models (default
            ``<round_dir>/fixedStacks``).
        apix: Physical voxel size in Angstrom for the grid (default 12.5).
        read_grid_from_header: If True (default), read each convmap header to build its own grid;
            if False, use ``expected_shape`` for every tomogram (avoids 112 header reads).
        expected_shape: Fallback / assertion grid shape ``(nz, ny, nx)`` (default the SPEC convmap
            shape). Used when ``read_grid_from_header`` is False.

    Attributes:
        convmap_dir: The convmap directory.
        name: The search label.
        rec_dir: The rec directory.
        fixedstacks_dir: The fixedStacks directory.
        apix: Angstrom per voxel.
    """

    def __init__(
        self,
        convmap_dir: Path,
        *,
        name: Optional[str] = None,
        rec_dir: Optional[Path] = None,
        fixedstacks_dir: Optional[Path] = None,
        apix: float = APIX_A,
        read_grid_from_header: bool = True,
        expected_shape: Tuple[int, int, int] = CONVMAP_SHAPE,
    ) -> None:
        self.convmap_dir = Path(convmap_dir)
        self.round_dir = self.convmap_dir.parent
        self.name = name if name is not None else (self.round_dir.name or self.convmap_dir.name)
        self.rec_dir = Path(rec_dir) if rec_dir is not None else DEFAULT_REC_DIR
        self.fixedstacks_dir = (
            Path(fixedstacks_dir) if fixedstacks_dir is not None else self.round_dir / "fixedStacks"
        )
        self.apix = float(apix)
        self._read_grid_from_header = read_grid_from_header
        self._expected_shape = expected_shape

    def _build_ref(self, convmap_path: Path) -> TomogramRef:
        """Resolve one basename's siblings, grid, rec, and ctf-tilt into a :class:`TomogramRef`.

        Args:
            convmap_path: Path to ``<base>_convmap.mrc``.

        Returns:
            The fully-resolved tomogram reference.
        """
        base = _basename_of(convmap_path)
        d = convmap_path.parent

        def sib(suffix: str) -> Path:
            return d / f"{base}{suffix}"

        if self._read_grid_from_header:
            hdr = read_header(convmap_path)
            grid = VoxelGrid(shape=hdr.shape_zyx, apix=self.apix)
        else:
            grid = VoxelGrid(shape=self._expected_shape, apix=self.apix)

        path_file = sib(".path")
        rec_ext, ctf_tilt = _parse_path_file(path_file, self.round_dir)
        rec_ext = rec_ext or ".rec"
        rec_path = self.rec_dir / f"{base}{rec_ext}"

        angles_mrc = sib("_angles.mrc")
        noise_var = sib("_noise_variance.mrc")

        return TomogramRef(
            base=base,
            convmap_path=convmap_path,
            csv_path=sib(".csv"),
            pos_path=sib(".pos"),
            templateidx_path=sib(".templateIDX"),
            angles_list_path=sib("_angles.list"),
            mod_path=sib(".mod"),
            path_file=path_file,
            grid=grid,
            rec_path=rec_path,
            ctf_tilt_path=ctf_tilt,
            angles_mrc_path=angles_mrc if angles_mrc.exists() else None,
            noise_variance_path=noise_var if noise_var.exists() else None,
            rec_dir=self.rec_dir,
            fixedstacks_dir=self.fixedstacks_dir,
        )

    def discover(self) -> SearchRef:
        """Enumerate the round into a :class:`SearchRef` (sorted by basename).

        Globs ``*_convmap.mrc`` in :attr:`convmap_dir`, builds a :class:`TomogramRef` per basename,
        and bundles them with the shared grid.

        Returns:
            The discovered :class:`SearchRef`.

        Raises:
            FileNotFoundError: If :attr:`convmap_dir` does not exist.
        """
        if not self.convmap_dir.is_dir():
            raise FileNotFoundError(f"convmap dir not found: {self.convmap_dir}")
        convmaps = sorted(self.convmap_dir.glob(f"*{CONVMAP_SUFFIX}"))
        tomos: List[TomogramRef] = [self._build_ref(p) for p in convmaps]
        grid = tomos[0].grid if tomos else None
        return SearchRef(
            name=self.name,
            convmap_dir=self.convmap_dir,
            tomograms=tomos,
            grid=grid,
            meta={
                "n_tomograms": len(tomos),
                "rec_dir": str(self.rec_dir),
                "apix": self.apix,
            },
        )


def discover_round(convmap_dir: Path, **kwargs: object) -> SearchRef:
    """Convenience: discover a round's convmap directory directly.

    Equivalent to ``EmclarityTMSource(convmap_dir, **kwargs).discover()``.

    Args:
        convmap_dir: The round's convmap directory.
        **kwargs: Forwarded to :class:`EmclarityTMSource`.

    Returns:
        The discovered :class:`SearchRef`.
    """
    return EmclarityTMSource(Path(convmap_dir), **kwargs).discover()  # type: ignore[arg-type]
