"""emClarity rotation / normal / packed-index conventions (quarantined, golden-locked).

Every function here returns values in the **raw emClarity axis order (x, y, z)** and the raw
sign — this module is the low-level convention layer. Higher adapters (``csv_io.py``) may
re-order to the package's ``(z, y, x)`` voxel frame; this module never does.

Key facts (SPEC §2, §4, §5), all verified empirically against ``H99_2_100_1_bin5``:

- **Rotation matrix cols 17-25 (0-idx 16:25) are COLUMN-MAJOR** — ``reshape(3, 3, order='F')``.
  On 50 real rows ``max|M Mᵀ − I| = 1.1e-6``, ``max|det − 1| = 9.1e-7``.
- **Outward normal = 3rd matrix column = cols 23-25 (0-idx 22:25)**, and is **C12-invariant**;
  cols 17-22 are scrambled by the per-peak C12 mate — NEVER use them for the normal.
- **Analytic normal from euler** ``[sinφ·sinθ, −cosφ·sinθ, cosθ]`` matches the matrix column to
  ``1.0e-6``. **Do not re-sign** — the raw sign is the outward-vs-inward signal.
- **Packed dense index** ``p = (angleIdx−1)·N_TEMPLATES + refIdx``; decode gives
  ``angleIdx = (p−1)//3 + 1``, ``refIdx = (p−1)%3 + 1``.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
from numpy.typing import ArrayLike, NDArray

from ..core.field import (
    Block,
    DenseField,
    IndexField,
    VectorField,
    register_index_decoders,
)
from .constants import N_TEMPLATES, NORMAL_COLS, ROTMAT_COLS


def matrix_from_row(row: ArrayLike) -> NDArray[np.float64]:
    """Unpack the 3x3 rotation matrix from a csv row (COLUMN-MAJOR, SPEC §2).

    Args:
        row: A csv row (length >= 25); cols 17-25 (0-idx 16:25) hold the matrix.

    Returns:
        The ``(3, 3)`` rotation matrix ``M`` with ``M · v_template = v_tomogram``. Its
        columns are cols 17-19, 20-22, 23-25 (1-idx). Column 3 is the outward normal.
    """
    r = np.asarray(row, dtype=np.float64)
    return r[list(ROTMAT_COLS)].reshape(3, 3, order="F")


def normal_from_matrix(row: ArrayLike) -> NDArray[np.float64]:
    """Return the outward normal from a csv row = matrix cols 23-25 (0-idx 22:25).

    C12-invariant (SPEC §4); the raw sign is preserved (outward-vs-inward signal). Order is
    the raw emClarity ``(nx, ny, nz)``.

    Args:
        row: A csv row (length >= 25).

    Returns:
        The unit outward normal ``(3,)`` in the tomogram voxel frame ``(x, y, z)``.
    """
    r = np.asarray(row, dtype=np.float64)
    return r[list(NORMAL_COLS)].copy()


def normal_from_euler(phi_deg: ArrayLike, theta_deg: ArrayLike) -> NDArray[np.float64]:
    """Analytic outward normal from the euler pair ``(phi, theta)`` in degrees (SPEC §4B).

    ``n = [sinφ·sinθ, −cosφ·sinθ, cosθ]``. ``psi−phi`` is unused. Vectorized: scalar inputs
    give ``(3,)``; array inputs of shape ``S`` give ``S + (3,)``.

    Args:
        phi_deg: ``phi`` in degrees (scalar or array).
        theta_deg: ``theta`` in degrees (scalar or array, broadcast with ``phi``).

    Returns:
        Outward normal(s) in the raw emClarity frame ``(nx, ny, nz)``.
    """
    phi = np.radians(np.asarray(phi_deg, dtype=np.float64))
    theta = np.radians(np.asarray(theta_deg, dtype=np.float64))
    nx = np.sin(phi) * np.sin(theta)
    ny = -np.cos(phi) * np.sin(theta)
    nz = np.cos(theta)
    return np.stack([nx, ny, nz], axis=-1)


def decode_packed_index(
    packed: ArrayLike,
) -> Tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Decode a packed argmax index into ``(angle_idx, ref_idx)`` (both 1-based, SPEC §5).

    ``angle_idx = (p−1)//N_TEMPLATES + 1``, ``ref_idx = (p−1)%N_TEMPLATES + 1``.

    Args:
        packed: Packed index ``p`` (scalar or array), 1-based.

    Returns:
        ``(angle_idx, ref_idx)`` as int64 arrays (0-d for scalar input); ``angle_idx`` is the
        1-based row into ``_angles.list``, ``ref_idx`` the winning template ``1..N_TEMPLATES``.
    """
    p = np.asarray(packed, dtype=np.int64)
    angle_idx = (p - 1) // N_TEMPLATES + 1
    ref_idx = (p - 1) % N_TEMPLATES + 1
    return angle_idx, ref_idx


def decode_index_volume_to_normal(
    packed: NDArray[np.generic], angles_list: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Decode a dense packed-index volume to a per-voxel outward-normal volume (SPEC §5).

    The dense field stores the raw argmax, so **no C12 symmetry correction is needed**.

    Args:
        packed: Packed-index volume of any shape ``S`` (fp32/int, never fp16 on disk).
        angles_list: The ``(N_ANGLES, 3)`` ``[phi, theta, psi−phi]`` degree grid.

    Returns:
        Normal volume of shape ``S + (3,)`` in the raw emClarity frame ``(nx, ny, nz)``.
    """
    angle_idx, _ = decode_packed_index(packed)
    rows = np.asarray(angles_list, dtype=np.float64)[angle_idx - 1]
    return normal_from_euler(rows[..., 0], rows[..., 1])


def decode_index_volume_to_template(packed: NDArray[np.generic]) -> NDArray[np.int64]:
    """Decode a dense packed-index volume to a per-voxel winning template id (SPEC §5).

    Args:
        packed: Packed-index volume of any shape ``S``.

    Returns:
        Template-id volume of shape ``S`` with values ``1..N_TEMPLATES``.
    """
    _, ref_idx = decode_packed_index(packed)
    return ref_idx


# --- IndexField decode seam (installed into domain-free core, SPEC §5) -------
# ``core.field.IndexField.decode_normal`` / ``decode_template`` are pure hooks; the emClarity
# convention stays here. Importing this module installs the concrete decoders so the production
# path works (``derived.NormalFieldProvider`` imports this module, and ``core.field._load_decoders``
# imports it lazily). Both these wrappers and ``NormalFieldProvider.materialize`` route through the
# same ``decode_index_volume_to_*`` above, so the sparse and dense paths cannot diverge.


def _read_whole_packed(index_field: "IndexField") -> NDArray[np.int64]:
    """Read an :class:`IndexField`'s entire packed-index volume as int64 (one halo-free block)."""
    nz, ny, nx = index_field.grid.shape
    data = index_field.block(Block((0, nz), (0, ny), (0, nx)))
    return np.rint(np.asarray(data)).astype(np.int64)


def _decode_normal_field(index_field: "IndexField", angles_list: NDArray) -> "VectorField":
    """Decode an IndexField to a per-voxel outward-normal :class:`VectorField` in ``(z, y, x)``.

    Matches :class:`~mito_filter.fields.derived.NormalFieldProvider`: raw ``(x, y, z)`` normals
    from :func:`decode_index_volume_to_normal`, reversed to the package ``(z, y, x)`` frame, fp32.
    """
    packed = _read_whole_packed(index_field)
    normal_xyz = decode_index_volume_to_normal(packed, np.asarray(angles_list, dtype=np.float64))
    normal_zyx = np.ascontiguousarray(normal_xyz[..., ::-1], dtype=np.float32)
    return VectorField("normal", index_field.grid, normal_zyx, channels=3)


def _decode_template_field(index_field: "IndexField") -> "DenseField":
    """Decode an IndexField to a per-voxel winning-template-id :class:`DenseField` (1..N)."""
    packed = _read_whole_packed(index_field)
    ref = decode_index_volume_to_template(packed).astype(np.float32)
    return DenseField.from_array("template", index_field.grid, ref, channels=1)


register_index_decoders(normal=_decode_normal_field, template=_decode_template_field)
