"""Readers for the sparse sibling files: ``.templateIDX`` / ``.pos`` / ``.mod`` / ``.path``
and the ``fixedStacks/*.erase`` IMOD bead models (SPEC §2, §9.4).

All of these share the csv row order (one write loop; SPEC §2), so row ``k`` of
``.templateIDX`` / ``.pos`` is the same peak as csv row ``k``. Positions in ``.pos`` and in
the IMOD models are the bin5 **convmap-voxel** frame in raw ``(x, y, z)`` order.

The ``.mod`` (peaks) and ``.erase`` (gold beads) files are IMOD binary models; a pragmatic
contour-point extractor pulls every contour's ``(x, y, z)`` points (validated on the real
``H99_2_100_1_bin5.mod``: 1249 contours == the 1249 ``.pos`` rows, byte-exact).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
from numpy.typing import NDArray

_IMOD_MAGIC: bytes = b"IMODV1.2"
_IMOD_HEADER_BYTES: int = 8 + 128  # magic + 128-byte name, then the model-header ints
_CONT_TAG: bytes = b"CONT"
_MAX_CONTOUR_POINTS: int = 5_000_000  # sanity bound to reject false 'CONT' byte matches


def read_template_idx(path: Path) -> NDArray[np.int64]:
    """Read ``<base>.templateIDX`` (one winning template id per peak, SPEC §2).

    Args:
        path: Path to the ``.templateIDX`` file.

    Returns:
        Int64 array ``(N,)`` of template ids ``1..N_TEMPLATES`` in csv row order.
    """
    return np.loadtxt(path, dtype=np.int64).reshape(-1)


def read_pos(path: Path) -> NDArray[np.float64]:
    """Read ``<base>.pos`` (bin5 convmap-voxel coords, raw ``(x, y, z)``, SPEC §3).

    Args:
        path: Path to the ``.pos`` file.

    Returns:
        Array ``(N, 3)`` of ``(x, y, z)`` voxel coordinates in csv row order.

    Raises:
        ValueError: If the file is not ``(*, 3)``.
    """
    arr = np.loadtxt(path, dtype=np.float64)
    arr = np.atleast_2d(arr)
    if arr.shape[1] != 3:
        raise ValueError(f"{path}: expected (*, 3) positions, got {arr.shape}")
    return arr


@dataclass(frozen=True)
class PathFile:
    """Parsed ``<base>.path`` line (SPEC §2).

    Args:
        base: Tomogram basename.
        cache_dir: The ``./cache`` token.
        rec_ext: The ``.rec`` extension token.
        tlt: The ctf/tilt geometry path token.

    Attributes:
        base: Tomogram basename.
        cache_dir: Cache-dir token.
        rec_ext: Rec-extension token.
        tlt: Tilt-geometry path token.
    """

    base: str
    cache_dir: str
    rec_ext: str
    tlt: str


def read_path_file(path: Path) -> PathFile:
    """Parse ``<base>.path`` (a single comma-separated line, SPEC §2).

    Args:
        path: Path to the ``.path`` file.

    Returns:
        The parsed :class:`PathFile`.

    Raises:
        ValueError: If the line does not have four comma-separated fields.
    """
    parts = path.read_text().strip().split(",")
    if len(parts) != 4:
        raise ValueError(f"{path}: expected 4 comma-separated fields, got {len(parts)}")
    return PathFile(base=parts[0], cache_dir=parts[1], rec_ext=parts[2], tlt=parts[3])


def read_imod_contours(path: Path) -> List[NDArray[np.float32]]:
    """Extract every contour's ``(x, y, z)`` points from an IMOD binary model.

    Pragmatic extractor for ``.mod`` (peaks) and ``.erase`` (gold beads): scans past the
    model header for ``CONT`` chunks, reads ``psize / flags / time / surf`` then ``psize``
    big-endian ``float32`` triples, and validates ``psize`` to reject spurious byte matches.

    Args:
        path: Path to an IMOD model file (``IMODV1.2`` magic).

    Returns:
        A list of ``(psize_i, 3)`` float32 arrays, one per contour.

    Raises:
        ValueError: If the file is not an IMOD model.
    """
    raw = path.read_bytes()
    if raw[:8] != _IMOD_MAGIC:
        raise ValueError(f"{path}: not an IMOD model (magic {raw[:8]!r})")
    contours: List[NDArray[np.float32]] = []
    search = _IMOD_HEADER_BYTES
    pos = raw.find(_CONT_TAG, search)
    while pos != -1:
        head = pos + 4
        if head + 16 > len(raw):
            break
        psize, _flags, _time, _surf = struct.unpack(">iIii", raw[head : head + 16])
        data_start = head + 16
        data_end = data_start + psize * 12
        if 0 < psize <= _MAX_CONTOUR_POINTS and data_end <= len(raw):
            pts = np.frombuffer(raw[data_start:data_end], dtype=">f4").reshape(-1, 3)
            if np.isfinite(pts).all():
                contours.append(np.ascontiguousarray(pts, dtype=np.float32))
                pos = raw.find(_CONT_TAG, data_end)
                continue
        pos = raw.find(_CONT_TAG, pos + 4)
    return contours


def read_imod_points(path: Path) -> NDArray[np.float32]:
    """Read all IMOD model points as one ``(N, 3)`` array (raw ``(x, y, z)``).

    Concatenates every contour from :func:`read_imod_contours`. For ``.mod`` peak models
    this returns the peak positions; for ``.erase`` bead models the gold-bead trace points.

    Args:
        path: Path to an IMOD model file.

    Returns:
        Array ``(N, 3)`` of ``(x, y, z)`` points (empty ``(0, 3)`` if none).
    """
    contours = read_imod_contours(path)
    if not contours:
        return np.zeros((0, 3), dtype=np.float32)
    return np.concatenate(contours, axis=0)


def read_erase_txt(path: Path) -> NDArray[np.float64]:
    """Read a ``*.erase_txt`` companion (per-tilt bead: ``x  y  view``).

    Args:
        path: Path to the ``.erase_txt`` file (IMOD ``model2point`` output).

    Returns:
        Array ``(N, 3)`` of ``(x, y, view)`` rows.
    """
    arr = np.loadtxt(path, dtype=np.float64)
    return np.atleast_2d(arr)
