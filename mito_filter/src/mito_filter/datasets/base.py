"""Dataset abstractions: a :class:`DataSource` enumerates a search into tomogram references.

The unit of work is a single tomogram (:class:`TomogramRef`) — the convmap basename, its seven
sibling files (SPEC §1, §2), and the shared :class:`~mito_filter.core.grid.VoxelGrid`. A whole
template-matching round is a :class:`SearchRef` (an ordered bundle of tomograms sharing a convmap
directory). Concrete discovery of an emClarity round lives in
:mod:`mito_filter.datasets.emclarity_tm`.

``TomogramRef`` is authored here as the *owner* of the structural contract the rest of the package
consumes: :mod:`mito_filter.fields._tomo` duck-types ``base`` / ``convmap_path`` /
``rec_dir`` / ``fixedstacks_dir`` off it, and :mod:`mito_filter.candidates.csv_source` duck-types
``csv_path`` / ``base``. Those attributes are provided here verbatim.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional

from ..core.grid import VoxelGrid

__all__ = ["TomogramRef", "SearchRef", "DataSource"]


@dataclass(frozen=True)
class TomogramRef:
    """An immutable reference to one tomogram's template-matching output.

    Bundles the convmap basename, the paths to its seven sibling files (SPEC §2 writes them in one
    row-aligned loop), the shared voxel grid, and the resolved reconstruction / ctf-tilt paths
    parsed from ``<base>.path``. Optional generated products (``_angles.mrc`` dense orientation
    field, ``_noise_variance.mrc``) are carried when present and are ``None`` otherwise, so a
    provider can report ``MISSING`` and its constraint go neutral (DESIGN §5).

    Args:
        base: Convmap basename, e.g. ``"H99_2_100_1_bin5"``.
        convmap_path: Path to ``<base>_convmap.mrc`` (the dense CC volume, SPEC §1).
        csv_path: Path to ``<base>.csv`` (26-column peaks, SPEC §2).
        pos_path: Path to ``<base>.pos`` (bin5 voxel coords, SPEC §2).
        templateidx_path: Path to ``<base>.templateIDX`` (winning reference per peak).
        angles_list_path: Path to ``<base>_angles.list`` (864 sampled orientations).
        mod_path: Path to ``<base>.mod`` (IMOD peak model).
        path_file: Path to ``<base>.path`` (the rec / ctf-tilt manifest line).
        grid: The convmap :class:`VoxelGrid` (shape from the header, apix 12.5).
        rec_path: Resolved ``<base>.rec`` path (SPEC §3; defaults under ``rec_dir``).
        ctf_tilt_path: Resolved ctf-tilt ``.tlt`` path parsed from ``<base>.path``.
        angles_mrc_path: Path to ``<base>_angles.mrc`` if the SPEC §7 re-run emitted it, else None.
        noise_variance_path: Path to ``<base>_noise_variance.mrc`` if present, else None.
        rec_dir: Directory holding ``<base>.rec`` (for the ``fields`` provider contract).
        fixedstacks_dir: ``fixedStacks`` directory (holds ``*.erase`` gold models), or None.

    Attributes:
        base: The basename.
        convmap_path: The convmap path.
        csv_path: The peak-csv path.
        pos_path: The ``.pos`` path.
        templateidx_path: The ``.templateIDX`` path.
        angles_list_path: The ``_angles.list`` path.
        mod_path: The ``.mod`` path.
        path_file: The ``.path`` path.
        grid: The voxel grid.
        rec_path: The reconstruction path.
        ctf_tilt_path: The ctf-tilt path.
        angles_mrc_path: The dense angle-field path, or None.
        noise_variance_path: The noise-variance path, or None.
        rec_dir: The rec directory.
        fixedstacks_dir: The fixedStacks directory.
    """

    base: str
    convmap_path: Path
    csv_path: Path
    pos_path: Path
    templateidx_path: Path
    angles_list_path: Path
    mod_path: Path
    path_file: Path
    grid: VoxelGrid
    rec_path: Optional[Path] = None
    ctf_tilt_path: Optional[Path] = None
    angles_mrc_path: Optional[Path] = None
    noise_variance_path: Optional[Path] = None
    rec_dir: Optional[Path] = None
    fixedstacks_dir: Optional[Path] = None

    @property
    def convmap_dir(self) -> Path:
        """The directory containing the convmap (parent of :attr:`convmap_path`)."""
        return self.convmap_path.parent

    @property
    def core_files(self) -> List[Path]:
        """The seven always-present sibling files (SPEC §2), in a stable order."""
        return [
            self.convmap_path,
            self.csv_path,
            self.pos_path,
            self.templateidx_path,
            self.angles_list_path,
            self.mod_path,
            self.path_file,
        ]

    def sibling(self, suffix: str) -> Path:
        """Return the ``<dir>/<base><suffix>`` sibling path.

        Args:
            suffix: Suffix appended to the basename (e.g. ``".csv"``, ``"_angles.list"``).

        Returns:
            The resolved sibling path (may not exist).
        """
        return self.convmap_dir / f"{self.base}{suffix}"

    def missing_core_files(self) -> List[Path]:
        """Return any of the seven :attr:`core_files` that do not exist on disk."""
        return [p for p in self.core_files if not p.exists()]

    def is_complete(self) -> bool:
        """Return True if all seven :attr:`core_files` exist."""
        return not self.missing_core_files()


@dataclass
class SearchRef:
    """An ordered bundle of the tomograms in one template-matching search / round.

    Args:
        name: A human label for the search (e.g. the round directory name).
        convmap_dir: The directory the tomograms were discovered in.
        tomograms: The discovered :class:`TomogramRef` objects, sorted by basename.
        grid: The shared voxel grid (the first tomogram's grid; all should match).
        meta: Free-form provenance (discovery parameters, counts).

    Attributes:
        name: The search label.
        convmap_dir: The convmap directory.
        tomograms: The tomogram references.
        grid: The shared grid.
        meta: Provenance metadata.
    """

    name: str
    convmap_dir: Path
    tomograms: List[TomogramRef] = field(default_factory=list)
    grid: Optional[VoxelGrid] = None
    meta: Mapping[str, object] = field(default_factory=dict)

    @property
    def n(self) -> int:
        """Number of tomograms in the search."""
        return len(self.tomograms)

    def __len__(self) -> int:
        return self.n

    def __iter__(self) -> Iterator[TomogramRef]:
        return iter(self.tomograms)

    def by_base(self) -> Dict[str, TomogramRef]:
        """Return a ``{base: TomogramRef}`` mapping for direct lookup."""
        return {t.base: t for t in self.tomograms}

    def get(self, base: str) -> TomogramRef:
        """Return the tomogram with basename ``base``.

        Args:
            base: The convmap basename to look up.

        Returns:
            The matching :class:`TomogramRef`.

        Raises:
            KeyError: If no tomogram with that basename is present.
        """
        for t in self.tomograms:
            if t.base == base:
                return t
        raise KeyError(f"no tomogram '{base}' in search '{self.name}' ({self.n} tomos)")


class DataSource(ABC):
    """Abstract source of tomograms for one search / round.

    A concrete source knows its own location (a convmap directory, a manifest, ...) and enumerates
    it into a :class:`SearchRef`. :class:`~mito_filter.datasets.emclarity_tm.EmclarityTMSource` is
    the emClarity implementation.
    """

    @abstractmethod
    def discover(self) -> SearchRef:
        """Enumerate this source into a :class:`SearchRef`.

        Returns:
            The discovered search (its ordered tomogram references + shared grid).
        """
        raise NotImplementedError

    def tomograms(self) -> List[TomogramRef]:
        """Return just the tomogram references (convenience over :meth:`discover`)."""
        return self.discover().tomograms
