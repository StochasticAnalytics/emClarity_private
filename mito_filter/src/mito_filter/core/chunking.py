"""Halo-aware tiling of large volumes into :class:`~mito_filter.core.field.Block`s.

Domain-free. A :class:`BlockPlan` tiles a ``(nz, ny, nx)`` volume into non-overlapping
*core* blocks, each read with a symmetric *halo* so that neighborhood operators (cluster
connectivity, coherence radius, the oriented erase cylinder) see enough context at block
seams. The halo must be at least the largest constraint reach; a 3x3x3 connectivity needs
only ``halo=1``.

The plan never touches pixel data — it emits descriptors. :func:`iter_field_blocks` pairs
each descriptor with the fp32 halo-padded read from a :class:`~mito_filter.core.field.DenseField`,
which is what ``DenseField.iter_blocks`` delegates to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator, List, Tuple

import numpy as np

from .field import ArrayT, Block

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .field import DenseField


def _axis_starts(dim: int, block: int) -> List[int]:
    """Return the core start offsets tiling ``[0, dim)`` in strides of ``block``.

    Args:
        dim: Axis length.
        block: Core block length on this axis (clamped to at least 1).

    Returns:
        Sorted list of start offsets ``0, block, 2*block, ...`` below ``dim``.
    """
    step = max(1, int(block))
    return list(range(0, max(1, dim), step))


@dataclass(frozen=True)
class BlockPlan:
    """A halo-aware tiling of a volume into core :class:`Block`s.

    Args:
        volume_shape: Full volume shape ``(nz, ny, nx)``.
        block_shape: Core block size ``(bz, by, bx)``; each axis is clamped to at least 1
            and capped at the volume extent.
        halo: Symmetric halo width (voxels) added on every side when a block is read.

    Attributes:
        volume_shape: The volume shape.
        block_shape: The core block size.
        halo: The halo width.
    """

    volume_shape: Tuple[int, int, int]
    block_shape: Tuple[int, int, int]
    halo: int = 0

    def blocks(self) -> List[Block]:
        """Enumerate the core blocks tiling the volume (row-major z, y, x).

        Returns:
            A list of :class:`Block`s whose core slices exactly partition the volume.
        """
        nz, ny, nx = self.volume_shape
        bz, by, bx = self.block_shape
        out: List[Block] = []
        for z0 in _axis_starts(nz, bz):
            z1 = min(nz, z0 + max(1, bz))
            for y0 in _axis_starts(ny, by):
                y1 = min(ny, y0 + max(1, by))
                for x0 in _axis_starts(nx, bx):
                    x1 = min(nx, x0 + max(1, bx))
                    out.append(Block((z0, z1), (y0, y1), (x0, x1), halo=self.halo))
        return out

    def __iter__(self) -> Iterator[Block]:
        return iter(self.blocks())

    def __len__(self) -> int:
        return len(self.blocks())


def core_offset_in_read(block: Block, shape: Tuple[int, int, int]) -> Tuple[slice, slice, slice]:
    """Slices selecting a block's *core* out of its halo-padded *read* window.

    When a block is read with its halo (:meth:`Block.read_slices`), the core region sits at
    an offset inside that window (0 at the volume edge, ``halo`` in the interior). This
    returns the ``(z, y, x)`` slices that recover the core from the read array.

    Args:
        block: The block descriptor.
        shape: Full volume shape ``(nz, ny, nx)`` (used to clip the halo like the read).

    Returns:
        Three slices mapping the read window to the core region.
    """
    read = block.read_slices(shape)
    core = block.core_slices()
    out = []
    for r, c in zip(read, core):
        lo = c.start - r.start
        out.append(slice(lo, lo + (c.stop - c.start)))
    return (out[0], out[1], out[2])


def iter_field_blocks(
    field: "DenseField",
    block_shape: Tuple[int, int, int],
    halo: int = 0,
    *,
    xp: object = np,
) -> Iterator[Tuple[Block, ArrayT]]:
    """Stream ``(block, data)`` pairs over a field, fp32, halo-padded.

    Args:
        field: The dense field to tile.
        block_shape: Core block size ``(bz, by, bx)``.
        halo: Symmetric halo width in voxels.
        xp: Array module for the emitted data (numpy default).

    Yields:
        ``(block, data)`` where ``data`` is the fp32 halo-padded read on ``xp``.
    """
    plan = BlockPlan(field.grid.shape, block_shape, halo)
    for blk in plan.blocks():
        yield blk, field.block(blk, xp=xp)
