"""MRC IO for the emClarity convention adapter (mode-12 fp16 read / mode-2 fp32 write).

Quarantined here so ``core/`` never touches the fragile on-disk format. The convmap is a
dense **mode-12 (float16)** volume that is memmapped and cast per-block to fp32 (never
hot-loaded whole, SPEC §1). Writing dense fields is **mode-2 (float32)**.

Hard refusal (SPEC §5, §7): a **packed-index** field (``p = (angleIdx-1)*3 + refIdx``, max
``2592``) MUST NOT be stored as mode-12 — float16 is integer-exact only to ``2048`` so
indices ``2049..2592`` corrupt silently. :func:`assert_index_dtype`,
:func:`open_dense_mmap` and :func:`write_dense_mrc` refuse fp16/mode-12 for index fields.

Verified against the real dev-set convmap ``H99_2_100_1_bin5_convmap.mrc``: byte size
``558_750_208``, shape ``(448, 942, 662)``, mode ``12``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import mrcfile
import numpy as np
from numpy.typing import NDArray

from ..core.field import DenseField
from ..core.grid import VoxelGrid
from .constants import APIX_A, FP16_INT_EXACT_MAX

# --- MRC modes (IMOD/emClarity) ---------------------------------------------

MRC_HEADER_BYTES: int = 1024
"""Size of the standard MRC header before the (optional) extended header."""

MODE_INT16: int = 1
MODE_FLOAT32: int = 2
MODE_UINT16: int = 6
MODE_FLOAT16: int = 12

_MODE_TO_DTYPE: Dict[int, str] = {
    MODE_INT16: "<i2",
    MODE_FLOAT32: "<f4",
    MODE_UINT16: "<u2",
    MODE_FLOAT16: "<f2",
}

# dtypes a packed IndexField may legally use on disk (fp32 or int16; NEVER fp16).
_INDEX_OK_KINDS: Tuple[str, ...] = ("float32", "int16", "int32")


@dataclass(frozen=True)
class MrcHeader:
    """Minimal MRC header (little-endian) for shape / mode / data offset.

    Args:
        nx: Fastest (x) dimension.
        ny: Middle (y) dimension.
        nz: Slowest (z) dimension.
        mode: MRC data mode (1 int16, 2 float32, 6 uint16, 12 float16).
        nsymbt: Extended-header byte count (0 for the convmap).

    Attributes:
        nx: x size.
        ny: y size.
        nz: z size.
        mode: MRC mode.
        nsymbt: Extended-header size in bytes.
    """

    nx: int
    ny: int
    nz: int
    mode: int
    nsymbt: int

    @property
    def shape_zyx(self) -> Tuple[int, int, int]:
        """Numpy/C-order shape ``(nz, ny, nx)`` (x fastest), matching an mrc mmap."""
        return (self.nz, self.ny, self.nx)

    @property
    def dtype(self) -> np.dtype:
        """Numpy dtype for :attr:`mode`.

        Raises:
            ValueError: If the mode is not one of the supported modes.
        """
        try:
            return np.dtype(_MODE_TO_DTYPE[self.mode])
        except KeyError:
            raise ValueError(f"unsupported MRC mode {self.mode}") from None

    @property
    def data_offset(self) -> int:
        """Byte offset to the first data element (header + extended header)."""
        return MRC_HEADER_BYTES + self.nsymbt

    @property
    def expected_bytes(self) -> int:
        """Total on-disk byte size implied by the header (offset + data)."""
        return self.data_offset + self.nx * self.ny * self.nz * self.dtype.itemsize


def read_header(path: Path) -> MrcHeader:
    """Read the MRC header of ``path``.

    Args:
        path: MRC file path.

    Returns:
        The parsed :class:`MrcHeader`.

    Raises:
        ValueError: If the file is shorter than one MRC header.
    """
    with open(path, "rb") as fh:
        buf = fh.read(MRC_HEADER_BYTES)
    if len(buf) < MRC_HEADER_BYTES:
        raise ValueError(f"{path}: file shorter than a {MRC_HEADER_BYTES}-byte MRC header")
    nx, ny, nz, mode = struct.unpack("<4i", buf[:16])
    (nsymbt,) = struct.unpack("<i", buf[92:96])
    return MrcHeader(nx=nx, ny=ny, nz=nz, mode=mode, nsymbt=nsymbt)


def assert_index_dtype(dtype: np.dtype) -> None:
    """Refuse an unsafe dtype for a packed-index field (SPEC §5, §7).

    A packed argmax index reaches ``2592`` > the ``2048`` float16 integer-exact limit, so
    fp16 (mode-12) corrupts it. Only fp32 / int16 / int32 are allowed.

    Args:
        dtype: The candidate on-disk dtype.

    Raises:
        ValueError: If ``dtype`` is float16 (or otherwise not integer-exact to 2592).
    """
    name = np.dtype(dtype).name
    if name not in _INDEX_OK_KINDS:
        raise ValueError(
            f"refusing packed-index dtype {name!r}: indices reach 2592 > float16 "
            f"integer-exact {FP16_INT_EXACT_MAX} -> corruption; use float32 or int16"
        )


def open_dense_mmap(
    path: Path,
    *,
    expected_shape: Optional[Tuple[int, int, int]] = None,
    is_index: bool = False,
) -> np.memmap:
    """Memmap a dense MRC volume read-only in its native dtype (no fp32 cast here).

    Args:
        path: MRC file path.
        expected_shape: If given, assert the header's ``(nz, ny, nx)`` matches.
        is_index: If True, refuse a mode-12 (fp16) file — a packed-index field must be
            fp32/int16 on disk.

    Returns:
        A read-only ``np.memmap`` of shape ``(nz, ny, nx)`` in the file's native dtype.

    Raises:
        ValueError: On shape mismatch, a truncated file, or a mode-12 index field.
    """
    hdr = read_header(path)
    if is_index and hdr.mode == MODE_FLOAT16:
        raise ValueError(
            f"{path}: refusing to read a packed-index field stored as mode-12 (fp16); "
            f"indices up to 2592 corrupt above {FP16_INT_EXACT_MAX}"
        )
    if expected_shape is not None and hdr.shape_zyx != expected_shape:
        raise ValueError(f"{path}: shape {hdr.shape_zyx} != expected {expected_shape}")
    actual = path.stat().st_size
    if actual < hdr.expected_bytes:
        raise ValueError(f"{path}: truncated ({actual} B < header-implied {hdr.expected_bytes} B)")
    return np.memmap(path, dtype=hdr.dtype, mode="r", offset=hdr.data_offset, shape=hdr.shape_zyx)


def read_block(
    mm: np.memmap,
    z: Tuple[int, int],
    y: Tuple[int, int],
    x: Tuple[int, int],
) -> NDArray[np.float32]:
    """Read a sub-block from a memmap and cast to fp32.

    Args:
        mm: The memmap from :func:`open_dense_mmap`.
        z: ``(z0, z1)`` half-open slice on the slow axis.
        y: ``(y0, y1)`` half-open slice.
        x: ``(x0, x1)`` half-open slice on the fast axis.

    Returns:
        The block as a contiguous ``float32`` array.
    """
    sub = mm[z[0] : z[1], y[0] : y[1], x[0] : x[1]]
    return np.asarray(sub, dtype=np.float32)


def open_dense_field(
    path: Path,
    name: str,
    *,
    apix: float = APIX_A,
    channels: int = 1,
    is_index: bool = False,
    expected_shape: Optional[Tuple[int, int, int]] = None,
) -> DenseField:
    """Memmap a dense MRC volume and wrap it in a :class:`DenseField` on a :class:`VoxelGrid`.

    Args:
        path: MRC file path (e.g. ``<base>_convmap.mrc``).
        name: Field name (e.g. ``"cc"``).
        apix: Physical voxel size in Angstrom (default 12.5, the bin5 convmap value).
        channels: 1 scalar / 3 vector / 1 index.
        is_index: If True, refuse a mode-12 (fp16) file (see :func:`open_dense_mmap`).
        expected_shape: Optional ``(nz, ny, nx)`` assertion.

    Returns:
        A memmap-backed :class:`DenseField` on a grid of the file's shape.
    """
    mm = open_dense_mmap(path, expected_shape=expected_shape, is_index=is_index)
    grid = VoxelGrid(shape=(mm.shape[0], mm.shape[1], mm.shape[2]), apix=apix)
    return DenseField.from_array(name, grid, mm, channels=channels)


def write_dense_mrc(
    path: Path,
    array: NDArray[np.generic],
    *,
    apix: float = APIX_A,
    is_index: bool = False,
) -> None:
    """Write a dense volume to an MRC file (mode-2 fp32 for float data).

    The MRC mode is derived from ``array.dtype`` by mrcfile. This is the mode-2 fp32 write
    path for generated / decoded fields. For a packed-index field pass ``is_index=True`` so
    a float16 array is **refused** (SPEC §5, §7): store index fields as fp32 or int16.

    Args:
        path: Destination MRC path (overwritten).
        array: Volume data ``(nz, ny, nx)`` (scalar) or ``(nz, ny, nx, 3)`` (vector).
        apix: Voxel size in Angstrom stamped into the header.
        is_index: If True, assert the dtype is index-safe (fp32/int16, never fp16).

    Raises:
        ValueError: If ``is_index`` and the dtype is unsafe (e.g. float16).
    """
    arr = np.asarray(array)
    if is_index:
        assert_index_dtype(arr.dtype)
    with mrcfile.new(str(path), overwrite=True) as mrc:
        mrc.set_data(np.ascontiguousarray(arr))
        mrc.voxel_size = float(apix)


def fp16_integer_exact(values: NDArray[np.generic]) -> NDArray[np.bool_]:
    """Return, per value, whether an integer is representable exactly in float16.

    Used to demonstrate/why packed indices corrupt in mode-12: an integer round-trips
    through float16 exactly only up to :data:`FP16_INT_EXACT_MAX`.

    Args:
        values: Integer-valued array.

    Returns:
        Boolean array, True where ``float16(v) == v``.
    """
    v = np.asarray(values)
    return np.asarray(v.astype(np.float16).astype(np.float64) == v.astype(np.float64), dtype=bool)
