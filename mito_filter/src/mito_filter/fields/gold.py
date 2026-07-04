"""Gold-fiducial field provider: reuse the already-located beads (DESIGN §9.4).

Tilt-series alignment already found the gold beads (``fixedStacks/*.erase`` IMOD bead models) —
exactly the compact extreme-CC gold/ice clusters the gold/ice constraint hunts. This provider
rasterises those beads into a ``gold`` mask (or a ``gold_dist`` distance field) so
``GoldIceClusterConstraint`` and the §9.3 gold-halo normal exclusion get a cheap, high-precision,
already-computed prior with no re-detection.

**Frame caveat (Phase A, honest):** the ``.mod`` peak model is in the convmap voxel frame, but a
``.erase`` bead model is in the *aligned-stack* frame, not the tomogram ``.rec`` voxel frame.
Mapping erase coordinates into the convmap grid needs the reconstruction geometry, which is not
wired here yet — so availability defaults to ``MISSING`` and only flips to ``GENERATABLE`` when
the caller asserts the bead source is already in the convmap frame (``assume_convmap_frame=True``,
e.g. a ``.mod`` peak model or a pre-transformed bead list). The rasterisation + distance maths
below are complete and tested on convmap-frame points; the erase->convmap transform is a tracked
follow-up. CPU/numpy+scipy only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage as ndi

from ..core.backend import Device
from ..core.field import DenseField
from ..core.grid import VoxelGrid
from ..emclarity.templateidx import read_imod_points
from . import _tomo
from .provider import (
    DERIVE,
    Availability,
    Cost,
    FieldProvider,
    FieldRegistry,
    FieldSpec,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..datasets.base import TomogramRef

_STACK_SUFFIX_RE = re.compile(r"_\d+_bin\d+$")
"""Strips the ``_<n>_bin<N>`` convmap suffix to recover the fixedStacks stack base."""


def stack_base(convmap_base: str) -> str:
    """Recover the fixedStacks stack base from a convmap base.

    ``"H99_2_100_1_bin5" -> "H99_2_100"`` (SPEC §9.4 bead models are named by the stack base).

    Args:
        convmap_base: The convmap basename.

    Returns:
        The stack base (the convmap base if the suffix pattern does not match).
    """
    return _STACK_SUFFIX_RE.sub("", convmap_base)


def rasterize_beads(
    points_zyx: NDArray[np.floating],
    grid: VoxelGrid,
    *,
    radius_vox: float,
) -> tuple[NDArray[np.bool_], NDArray[np.float32]]:
    """Rasterise bead centres into a mask + a distance-to-nearest-bead field.

    Args:
        points_zyx: Bead centres ``(M, 3)`` in the convmap voxel frame ``(z, y, x)``.
        grid: The target voxel grid.
        radius_vox: Bead radius in voxels for the mask.

    Returns:
        ``(mask, dist)``: a boolean ``gold`` mask (within ``radius_vox`` of any bead) and the
        Euclidean distance (voxels) to the nearest bead centre, both shape ``grid.shape``.
    """
    seed = np.zeros(grid.shape, dtype=bool)
    if points_zyx.size:
        idx = np.rint(np.asarray(points_zyx, dtype=np.float64)).astype(np.int64)
        inb = grid.in_bounds(idx)
        idx = idx[inb]
        if idx.size:
            seed[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    dist = np.asarray(ndi.distance_transform_edt(~seed), dtype=np.float32)
    mask = dist <= float(radius_vox)
    if not seed.any():
        # No in-bounds beads: empty mask, +inf-like distance clamped to the diagonal.
        mask = np.zeros(grid.shape, dtype=bool)
    return mask, dist


class GoldFiducialProvider(FieldProvider):
    """Rasterise gold-bead models into a ``gold`` mask or ``gold_dist`` distance (DESIGN §9.4).

    Args:
        field: Which field to produce — ``"gold"`` (boolean mask as float 0/1) or ``"gold_dist"``
            (voxel distance to the nearest bead).
        bead_radius_A: Bead mask radius in Angstrom (default 250; ``gold`` only).
        fixedstacks_dir: Directory of ``*.erase`` bead models (defaults to the round's
            ``fixedStacks`` sibling of the convmap dir).
        erase_suffix: Preferred bead-model filename suffix under the stack base (default
            ``".erase"``; falls back to the highest ``_ali<k>.erase``).
        assume_convmap_frame: Assert the bead source is already in the convmap voxel frame
            (required to become ``GENERATABLE``; see the module frame caveat).
        apix: Physical voxel size in Angstrom.
    """

    def __init__(
        self,
        *,
        field: str = "gold",
        bead_radius_A: float = 250.0,
        fixedstacks_dir: Optional[Path] = None,
        erase_suffix: str = ".erase",
        assume_convmap_frame: bool = False,
        apix: float = 12.5,
    ) -> None:
        if field not in ("gold", "gold_dist"):
            raise ValueError(f"field must be 'gold' or 'gold_dist', got {field!r}")
        semantics = (
            "gold-bead mask (1 inside a bead radius)"
            if field == "gold"
            else "voxel distance to the nearest gold bead"
        )
        self.produces = FieldSpec(
            name=field, channels=1, dtype=np.dtype(np.float32), semantics=semantics
        )
        self.field = field
        self.bead_radius_A = float(bead_radius_A)
        self._fixedstacks_dir = Path(fixedstacks_dir) if fixedstacks_dir is not None else None
        self.erase_suffix = erase_suffix
        self.assume_convmap_frame = bool(assume_convmap_frame)
        self.apix = float(apix)

    def _fixedstacks(self, tomo: "TomogramRef") -> Path:
        if self._fixedstacks_dir is not None:
            return self._fixedstacks_dir
        attr = getattr(tomo, "fixedstacks_dir", None)
        if attr is not None:
            return Path(attr)
        # .../<round>/convmap_wedgeType_2_bin5/<base>_convmap.mrc -> .../<round>/fixedStacks
        return _tomo.dir_of(tomo).parent / "fixedStacks"

    def _bead_model(self, tomo: "TomogramRef") -> Optional[Path]:
        base = stack_base(_tomo.base_of(tomo))
        d = self._fixedstacks(tomo)
        if not d.is_dir():
            return None
        exact = d / f"{base}{self.erase_suffix}"
        if exact.exists():
            return exact
        alis = sorted(d.glob(f"{base}_ali*{self.erase_suffix}"))
        return alis[-1] if alis else None

    def available(self, tomo: "TomogramRef") -> Availability:
        if not self.assume_convmap_frame:
            # erase beads are in the aligned-stack frame; the transform is not wired (see module
            # docstring), so without an explicit convmap-frame assertion we cannot place them.
            return Availability.MISSING
        return (
            Availability.GENERATABLE if self._bead_model(tomo) is not None else Availability.MISSING
        )

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        model = self._bead_model(tomo)
        if model is None:
            raise FileNotFoundError(f"no bead model for {_tomo.base_of(tomo)}")
        pts_xyz = read_imod_points(model)
        pts_zyx = np.ascontiguousarray(pts_xyz[:, ::-1], dtype=np.float64)
        grid = VoxelGrid(shape=_tomo_shape(tomo, reg, device, self.apix), apix=self.apix)
        mask, dist = rasterize_beads(pts_zyx, grid, radius_vox=self.bead_radius_A / self.apix)
        data = mask.astype(np.float32) if self.field == "gold" else dist
        return DenseField.from_array(self.field, grid, data, channels=1, provider=self)

    def cache_key_inputs(self, tomo: "TomogramRef") -> Sequence[Path]:
        model = self._bead_model(tomo)
        return [model] if model is not None else []

    def cost_hint(self) -> Cost:
        return DERIVE


def _tomo_shape(
    tomo: "TomogramRef", reg: FieldRegistry, device: Device, apix: float
) -> tuple[int, int, int]:
    """Best-effort grid shape for the gold field: the ``cc`` grid if resolvable, else the header."""
    from ..emclarity.mrc_io import read_header

    cc = reg.try_resolve("cc", tomo, device=device)
    if cc is not None:
        return cc.grid.shape
    hdr = read_header(_tomo.convmap_path_of(tomo))
    return hdr.shape_zyx


def register_gold(
    reg: FieldRegistry,
    *,
    assume_convmap_frame: bool = False,
    fixedstacks_dir: Optional[Path] = None,
) -> List[FieldProvider]:
    """Register the ``gold`` mask + ``gold_dist`` distance providers on ``reg``.

    Args:
        reg: The registry to populate.
        assume_convmap_frame: Passed through to each provider (see the frame caveat).
        fixedstacks_dir: Optional override for the bead-model directory.

    Returns:
        The registered providers.
    """
    providers: List[FieldProvider] = [
        GoldFiducialProvider(
            field="gold",
            assume_convmap_frame=assume_convmap_frame,
            fixedstacks_dir=fixedstacks_dir,
        ),
        GoldFiducialProvider(
            field="gold_dist",
            assume_convmap_frame=assume_convmap_frame,
            fixedstacks_dir=fixedstacks_dir,
        ),
    ]
    for p in providers:
        reg.register(p)
    return providers
