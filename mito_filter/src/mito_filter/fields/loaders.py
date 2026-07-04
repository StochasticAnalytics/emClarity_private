"""Pure-load field providers: mmap an existing MRC into a :class:`DenseField` (DESIGN §5).

These are the ``CHEAP_LOAD`` tier — no derivation, no GPU. Phase A uses :class:`ConvmapProvider`
(the primary ``cc`` signal) and optionally :class:`RecProvider`; :class:`NoiseVarLoader` and
:class:`AngleIndexLoader` load the products of the SPEC §7 ``measure_noise_variance`` / angle
re-run and report ``MISSING`` until that re-run has emitted them, so their dependent constraints
go neutral on today's data.

All providers guard nothing GPU-side (mmap is host IO); ``device`` is accepted for API symmetry.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Sequence

import numpy as np

from ..core.backend import Device
from ..core.field import DenseField, IndexField
from ..core.grid import VoxelGrid
from ..emclarity.constants import APIX_A, CONVMAP_SHAPE
from ..emclarity.mrc_io import open_dense_field, open_dense_mmap
from . import _tomo
from .provider import (
    CHEAP_LOAD,
    Availability,
    Cost,
    FieldProvider,
    FieldRegistry,
    FieldSpec,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..datasets.base import TomogramRef


class ConvmapProvider(FieldProvider):
    """Load ``<base>_convmap.mrc`` as the ``cc`` field (SPEC §1) — the PRIMARY signal.

    The convmap is a dense mode-12 (fp16) per-orientation sigma-normalised CC max, memmapped
    and cast per-block to fp32 (never hot-loaded whole).

    Args:
        expected_shape: Optional ``(nz, ny, nx)`` assertion; defaults to the SPEC convmap shape.
        apix: Physical voxel size in Angstrom (default 12.5, the bin5 convmap value).
    """

    produces = FieldSpec(
        name="cc",
        channels=1,
        dtype=np.dtype(np.float32),
        semantics="per-orientation sigma-normalised cross-correlation max (SPEC §1)",
    )

    def __init__(
        self,
        *,
        expected_shape: Optional[tuple[int, int, int]] = CONVMAP_SHAPE,
        apix: float = APIX_A,
    ) -> None:
        self.apix = float(apix)
        self._expected_shape = expected_shape

    def available(self, tomo: "TomogramRef") -> Availability:
        return (
            Availability.ON_DISK if _tomo.convmap_path_of(tomo).exists() else Availability.MISSING
        )

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        field = open_dense_field(
            _tomo.convmap_path_of(tomo),
            self.produces.name,
            apix=self.apix,
            channels=1,
            expected_shape=self._expected_shape,
        )
        field.provider = self
        return field

    def cache_key_inputs(self, tomo: "TomogramRef") -> Sequence[Path]:
        """Source files whose mtimes key any downstream derive cache."""
        return [_tomo.convmap_path_of(tomo)]

    def cost_hint(self) -> Cost:
        return CHEAP_LOAD


class RecProvider(FieldProvider):
    """Load the searched reconstruction ``<base>.rec`` as the ``rec`` field (SPEC §3).

    Shares the exact voxel grid with the convmap (byte-identical size). Lives on the per-host
    ``alt_cache`` (``/scratch/salina/alt_cache`` by default).

    Args:
        rec_dir: Directory holding ``<base>.rec`` (defaults to the tomo's own ``rec_dir`` or
            :data:`mito_filter.fields._tomo.DEFAULT_REC_DIR`).
        apix: Physical voxel size in Angstrom.
    """

    produces = FieldSpec(
        name="rec",
        channels=1,
        dtype=np.dtype(np.float32),
        semantics="searched tomogram reconstruction, convmap voxel frame (SPEC §3)",
    )

    def __init__(self, *, rec_dir: Optional[Path] = None, apix: float = APIX_A) -> None:
        self.rec_dir = Path(rec_dir) if rec_dir is not None else None
        self.apix = float(apix)

    def _path(self, tomo: "TomogramRef") -> Path:
        return _tomo.rec_path_of(tomo, self.rec_dir)

    def available(self, tomo: "TomogramRef") -> Availability:
        return Availability.ON_DISK if self._path(tomo).exists() else Availability.MISSING

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        field = open_dense_field(self._path(tomo), self.produces.name, apix=self.apix, channels=1)
        field.provider = self
        return field

    def cache_key_inputs(self, tomo: "TomogramRef") -> Sequence[Path]:
        return [self._path(tomo)]

    def cost_hint(self) -> Cost:
        return CHEAP_LOAD


class NoiseVarLoader(FieldProvider):
    """Load ``<base>_noise_variance.mrc`` as ``noise_variance`` (SPEC §9.2, §11).

    Present only if the ``measure_noise_variance=1`` re-run emitted it; ``MISSING`` otherwise
    (today's data), so :class:`~mito_filter.fields.derived.SnrFieldProvider` falls back to a
    per-tomo background z-score.

    Args:
        apix: Physical voxel size in Angstrom.
    """

    produces = FieldSpec(
        name="noise_variance",
        channels=1,
        dtype=np.dtype(np.float32),
        semantics="per-voxel noise variance from measure_noise_variance=1 (SPEC §9.2)",
    )

    def __init__(self, *, apix: float = APIX_A) -> None:
        self.apix = float(apix)

    def _path(self, tomo: "TomogramRef") -> Path:
        return _tomo.sibling(tomo, "_noise_variance.mrc")

    def available(self, tomo: "TomogramRef") -> Availability:
        return Availability.ON_DISK if self._path(tomo).exists() else Availability.MISSING

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        field = open_dense_field(self._path(tomo), self.produces.name, apix=self.apix, channels=1)
        field.provider = self
        return field

    def cache_key_inputs(self, tomo: "TomogramRef") -> Sequence[Path]:
        return [self._path(tomo)]

    def cost_hint(self) -> Cost:
        return CHEAP_LOAD


class AngleIndexLoader(FieldProvider):
    """Load a regenerated ``<base>_angles.mrc`` packed-index volume as ``angle`` (SPEC §5, §7).

    The dense argmax field holds ``p = (angleIdx-1)*N_TEMPLATES + refIdx`` per voxel and MUST be
    stored fp32/int16 (2592 > fp16 integer-exact 2048); a mode-12 file is **refused** by
    :func:`~mito_filter.emclarity.mrc_io.open_dense_mmap`. Returns an :class:`IndexField` so
    ``decode_normal`` / ``decode_template`` work. ``MISSING`` until the §7 re-run emits it.

    Args:
        apix: Physical voxel size in Angstrom.
    """

    produces = FieldSpec(
        name="angle",
        channels=1,
        dtype=np.dtype(np.float32),
        semantics="packed argmax orientation+template index per voxel (SPEC §5)",
    )

    def __init__(self, *, apix: float = APIX_A) -> None:
        self.apix = float(apix)

    def _path(self, tomo: "TomogramRef") -> Path:
        return _tomo.sibling(tomo, "_angles.mrc")

    def available(self, tomo: "TomogramRef") -> Availability:
        return Availability.ON_DISK if self._path(tomo).exists() else Availability.MISSING

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        mm = open_dense_mmap(self._path(tomo), is_index=True)
        grid = VoxelGrid(shape=(mm.shape[0], mm.shape[1], mm.shape[2]), apix=self.apix)
        return IndexField(self.produces.name, grid, mm, channels=1, provider=self)

    def cache_key_inputs(self, tomo: "TomogramRef") -> Sequence[Path]:
        return [self._path(tomo)]

    def cost_hint(self) -> Cost:
        return CHEAP_LOAD


def register_loaders(
    reg: FieldRegistry,
    *,
    rec_dir: Optional[Path] = None,
    convmap_shape: Optional[tuple[int, int, int]] = CONVMAP_SHAPE,
) -> List[FieldProvider]:
    """Register the standard Phase-A loaders on ``reg`` and return them.

    Args:
        reg: The :class:`FieldRegistry` to populate.
        rec_dir: Optional override for the ``rec`` directory.
        convmap_shape: Shape the ``cc`` loader asserts the convmap against; pass the discovered
            header shape (or None to skip) so an arbitrary-shape round loads while a header/data
            mismatch on the SPEC data still fails loudly.

    Returns:
        The list of registered providers.
    """
    providers: List[FieldProvider] = [
        ConvmapProvider(expected_shape=convmap_shape),
        RecProvider(rec_dir=rec_dir),
        NoiseVarLoader(),
        AngleIndexLoader(),
    ]
    for p in providers:
        reg.register(p)
    return providers
