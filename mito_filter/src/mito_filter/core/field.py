"""Dense fields on a shared VoxelGrid — the primary object every constraint receives.

Domain-free. A :class:`DenseField` is a lazy, memmap-backed co-registered volume that is
NEVER hot-loaded whole (the convmap is 559 MB); callers stream halo-aware :class:`Block`
reads or gather at sparse points. :class:`TomogramFields` bundles the named fields plus the
optional sparse :class:`PointCloud`.

Signatures here are FROZEN. Trivially-correct methods (``from_array``, ``as_memmap``,
``block``) are implemented; the halo-streaming / backend-sampling / index-decode bodies are
stubs whose implementations land in ``core/sampling.py``, ``core/chunking.py`` and
``emclarity/conventions.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import TYPE_CHECKING, Callable, Iterator, Mapping, Optional, Tuple, cast

import numpy as np
from numpy.typing import NDArray

from .grid import VoxelGrid
from .points import PointCloud

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..fields.provider import FieldProvider

# Backend array type. The numpy path is concrete; cupy/torch arrays are duck-typed here.
ArrayT = NDArray

# --- Packed-index decode hook -------------------------------------------------
# The angle-index -> normal / template convention is emClarity-specific (SPEC §5) and MUST
# stay out of domain-free core. ``emclarity/conventions.py`` installs the concrete decoders
# here via :func:`register_index_decoders`; ``IndexField.decode_*`` calls them. Keeping this
# a runtime hook (not an import) avoids a core->emclarity dependency and lets tests inject a
# stub decoder.
NormalDecoder = Callable[["IndexField", NDArray], "VectorField"]
TemplateDecoder = Callable[["IndexField"], "DenseField"]

_normal_decoder: Optional[NormalDecoder] = None
_template_decoder: Optional[TemplateDecoder] = None


def register_index_decoders(
    *,
    normal: Optional[NormalDecoder] = None,
    template: Optional[TemplateDecoder] = None,
) -> None:
    """Install the packed-index decoders used by :class:`IndexField` (called by emclarity/).

    Args:
        normal: Callable ``(index_field, angles_list) -> VectorField`` of outward normals.
        template: Callable ``(index_field) -> DenseField`` of winning template ids.
    """
    global _normal_decoder, _template_decoder
    if normal is not None:
        _normal_decoder = normal
    if template is not None:
        _template_decoder = template


def _load_decoders() -> None:
    """Best-effort import of the emClarity adapter so it can register its decoders."""
    try:  # pragma: no cover - exercised once the adapter exists
        import importlib

        importlib.import_module("mito_filter.emclarity.conventions")
    except Exception:
        pass


@dataclass(frozen=True)
class Block:
    """A halo-padded chunk descriptor into a volume (voxel frame ``(z, y, x)``).

    Args:
        z: ``(z0, z1)`` half-open core slice on the slow axis.
        y: ``(y0, y1)`` half-open core slice.
        x: ``(x0, x1)`` half-open core slice on the fast axis.
        halo: Symmetric halo (voxels) added on every side when reading, clipped to the
            volume bounds.

    Attributes:
        z: Core z-range.
        y: Core y-range.
        x: Core x-range.
        halo: The halo width in voxels.
    """

    z: Tuple[int, int]
    y: Tuple[int, int]
    x: Tuple[int, int]
    halo: int = 0

    def core_slices(self) -> Tuple[slice, slice, slice]:
        """Return the ``(z, y, x)`` slices of the core (halo-excluded) region."""
        return (slice(*self.z), slice(*self.y), slice(*self.x))

    def read_slices(self, shape: Tuple[int, int, int]) -> Tuple[slice, slice, slice]:
        """Return the ``(z, y, x)`` slices of the halo-padded read region, clipped to ``shape``.

        Args:
            shape: The full volume shape ``(nz, ny, nx)`` used to clip the halo.

        Returns:
            Three slices covering the core plus halo, clamped to ``[0, dim)``.
        """
        h = self.halo
        rngs = (self.z, self.y, self.x)
        out = []
        for (lo, hi), dim in zip(rngs, shape):
            out.append(slice(max(0, lo - h), min(dim, hi + h)))
        return (out[0], out[1], out[2])


class DenseField:
    """One co-registered dense volume on a :class:`VoxelGrid`.

    Lazy and memmap/array-backed; cast to fp32 on read. Construct via
    :meth:`from_array` or a :class:`~mito_filter.fields.provider.FieldProvider`.

    Args:
        name: Field name (e.g. ``"cc"``, ``"normal"``, ``"angle"``).
        grid: The shared voxel grid.
        source: The backing store — an ndarray or ``np.memmap`` of shape
            ``grid.shape`` (scalar) or ``grid.shape + (channels,)`` (vector).
        channels: 1 for scalar, 3 for a vector field, 1 for a packed index field.
        provider: The provider that materialized this field (provenance), if any.

    Attributes:
        name: The field name.
        grid: The voxel grid.
        channels: Channel count.
        provider: The originating provider.
    """

    def __init__(
        self,
        name: str,
        grid: VoxelGrid,
        source: NDArray,
        *,
        channels: int = 1,
        provider: "Optional[FieldProvider]" = None,
    ) -> None:
        self.name = name
        self.grid = grid
        self.channels = channels
        self.provider = provider
        self._source: NDArray = source

    @property
    def dtype(self) -> np.dtype:
        """The backing store dtype (on-disk / in-memory)."""
        return self._source.dtype

    @property
    def shape(self) -> Tuple[int, ...]:
        """The backing store shape."""
        return tuple(self._source.shape)

    @classmethod
    def from_array(
        cls,
        name: str,
        grid: VoxelGrid,
        array: NDArray,
        *,
        channels: int = 1,
        provider: "Optional[FieldProvider]" = None,
    ) -> "DenseField":
        """Build a DenseField wrapping an in-memory (or memmapped) array.

        Args:
            name: Field name.
            grid: The shared voxel grid; ``array``'s leading 3 dims must match ``grid.shape``.
            array: The volume data.
            channels: 1 scalar / 3 vector / 1 index.
            provider: Originating provider, if any.

        Returns:
            A DenseField wrapping ``array``.

        Raises:
            ValueError: If the array's spatial shape does not match ``grid.shape``.
        """
        arr = np.asarray(array)
        if tuple(arr.shape[:3]) != tuple(grid.shape):
            raise ValueError(f"array spatial shape {arr.shape[:3]} != grid {grid.shape}")
        return cls(name, grid, arr, channels=channels, provider=provider)

    def as_memmap(self) -> np.memmap:
        """Return the backing store as an ``np.memmap``.

        Returns:
            The underlying memmap.

        Raises:
            TypeError: If this field is not memmap-backed.
        """
        if isinstance(self._source, np.memmap):
            return self._source
        raise TypeError(f"field '{self.name}' is not memmap-backed (dtype {self.dtype})")

    def block(self, plan: "Block", *, xp: object = np) -> ArrayT:
        """Read a halo-padded block, cast to fp32, on the requested backend.

        Args:
            plan: The :class:`Block` describing the core + halo region.
            xp: Array module for the result (numpy default; cupy/torch on GPU).

        Returns:
            The block data as fp32 on ``xp`` (spatial dims first, channel dim last for
            vector fields).
        """
        sl = plan.read_slices(self.grid.shape)
        data = np.asarray(self._source[sl[0], sl[1], sl[2]], dtype=np.float32)
        if xp is np:
            return data
        return cast(ArrayT, xp.asarray(data))  # type: ignore[attr-defined]

    def iter_blocks(
        self, block_shape: Tuple[int, int, int], halo: int = 0
    ) -> Iterator[Tuple["Block", ArrayT]]:
        """Iterate halo-padded blocks tiling the whole volume.

        Args:
            block_shape: Core block size ``(bz, by, bx)``.
            halo: Symmetric halo width in voxels.

        Yields:
            ``(block, data)`` pairs; ``data`` is the fp32 halo-padded read.

        Note:
            Delegates to ``core/chunking.py`` (``BlockPlan``).
        """
        from .chunking import iter_field_blocks

        return iter_field_blocks(self, block_shape, halo)

    def sample_at(
        self,
        pts: NDArray,
        *,
        xp: object = np,
        reduce: str = "max",
        radius: int = 1,
    ) -> ArrayT:
        """Gather field values at sparse voxel points with a +/- neighborhood reduce.

        Reproduces the csv score (SPEC §3): read a ``(2*radius+1)^3`` neighborhood around
        each rounded point and reduce (``"max"`` / ``"mean"`` / ``"center"``).

        Args:
            pts: Voxel coordinates ``(N, 3)`` in ``(z, y, x)``.
            xp: Array module for the result.
            reduce: Neighborhood reduction: ``"max"``, ``"mean"``, or ``"center"``.
            radius: Neighborhood radius in voxels.

        Returns:
            Array ``(N,)`` (scalar field) or ``(N, channels)`` (vector field).

        Note:
            Delegates to ``core/sampling.py``; memory-safe (indexes only touched voxels).
        """
        from .sampling import sample_field

        return sample_field(
            self._source, pts, xp=xp, reduce=reduce, radius=radius, channels=self.channels
        )

    def sample_at_companion_argmax(
        self,
        pts: NDArray,
        companion: "DenseField",
        *,
        radius: int = 1,
        xp: object = np,
    ) -> ArrayT:
        """Sample this (vector) field at the voxel where ``companion`` peaks near each point.

        For a packed-argmax field (a normal decoded from the dense angle index) a rounded csv
        coordinate lands on a neighbor of the true argmax voxel as often as on it (SPEC §3's
        sub-voxel offset), and the neighbor's argmax orientation is frequently the OPPOSITE
        normal. This snaps to the ``companion`` (``cc``) argmax voxel in the
        ``(2*radius+1)^3`` neighborhood before reading, recovering the true per-peak normal.

        Args:
            pts: Voxel coordinates ``(N, 3)`` in ``(z, y, x)``.
            companion: The scalar field whose local argmax locates the peak voxel (e.g. ``cc``).
            radius: Neighborhood radius in voxels.
            xp: Array module for the result.

        Returns:
            ``(N, channels)`` vectors read at the companion-argmax voxel per point.

        Note:
            Delegates to ``core/sampling.py``; memory-safe (indexes only touched voxels).
        """
        from .sampling import sample_at_companion_argmax

        return sample_at_companion_argmax(
            self._source,
            companion._source,
            pts,
            radius=radius,
            channels=self.channels,
            xp=xp,
        )


class VectorField(DenseField):
    """A 3-channel dense field (e.g. a per-voxel normal). ``channels == 3``."""


class IndexField(DenseField):
    """A packed argmax-index dense field (SPEC §5).

    Stores ``p = (angleIdx - 1) * N_TEMPLATES + refIdx`` per voxel. MUST be fp32/int16
    on disk (2592 > fp16 integer-exact 2048). Decoding delegates to ``emclarity/``.
    """

    def decode_normal(self, angles_list: NDArray) -> "VectorField":
        """Decode each voxel's packed index to an outward normal (SPEC §5).

        Args:
            angles_list: The ``(864, 3)`` ``[phi, theta, psi-phi]`` degree grid.

        Returns:
            A :class:`VectorField` of per-voxel outward normals in the tomogram frame.

        Note:
            Delegates to the decoder installed by ``emclarity/conventions.py`` via
            :func:`register_index_decoders` (the convention stays quarantined there).
        """
        if _normal_decoder is None:
            _load_decoders()
        if _normal_decoder is None:
            raise NotImplementedError(
                "no packed-index normal decoder registered; "
                "emclarity/conventions.py must call register_index_decoders(normal=...)"
            )
        return _normal_decoder(self, np.asarray(angles_list))

    def decode_template(self) -> "DenseField":
        """Decode each voxel's winning template id ``refIdx = (p - 1) % N_TEMPLATES + 1``.

        Returns:
            A scalar :class:`DenseField` of per-voxel winning template ids (1..N_TEMPLATES).

        Note:
            Delegates to the decoder installed by ``emclarity/conventions.py`` via
            :func:`register_index_decoders` (the convention stays quarantined there).
        """
        if _template_decoder is None:
            _load_decoders()
        if _template_decoder is None:
            raise NotImplementedError(
                "no packed-index template decoder registered; "
                "emclarity/conventions.py must call register_index_decoders(template=...)"
            )
        return _template_decoder(self)


@dataclass
class TomogramFields:
    """Named bundle of co-registered :class:`DenseField`s + the optional sparse points.

    THE object every constraint / feature extractor receives.

    Args:
        grid: The shared voxel grid all fields live on.
        fields: Mapping field name -> :class:`DenseField`.
        points: Optional sparse candidate :class:`PointCloud`.
        meta: Free-form provenance / metadata.

    Attributes:
        grid: The voxel grid.
        fields: The named dense fields.
        points: The optional point cloud.
        meta: Metadata mapping.
    """

    grid: VoxelGrid
    fields: dict[str, DenseField] = dc_field(default_factory=dict)
    points: Optional[PointCloud] = None
    meta: Mapping[str, object] = dc_field(default_factory=dict)

    def require(self, name: str) -> DenseField:
        """Return field ``name`` or raise a helpful error if a provider was skipped.

        Args:
            name: The field name.

        Returns:
            The requested :class:`DenseField`.

        Raises:
            KeyError: If ``name`` is absent (message lists available fields).
        """
        try:
            return self.fields[name]
        except KeyError:
            avail = ", ".join(sorted(self.fields)) or "<none>"
            raise KeyError(
                f"field '{name}' not materialized (a provider was skipped?). " f"Available: {avail}"
            ) from None

    def __contains__(self, name: object) -> bool:
        return name in self.fields
