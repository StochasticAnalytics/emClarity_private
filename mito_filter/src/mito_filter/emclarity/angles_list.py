"""Parse ``<base>_angles.list`` — the 864x3 sampled orientation grid (SPEC §2, §5).

Each row is ``[phi, theta, psi−phi]`` in degrees (``Tmp_angleSearch=[180,12,180,12]``); the
same 864 rows for every tomo. Rows are 1-based when referenced by a packed ``angle_idx``
(SPEC §5). Verified: shape ``(864, 3)`` and the 2-decimal rounding limits the reconstructed
normal to ``6.4e-5`` vs the csv.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .constants import N_ANGLES
from .conventions import normal_from_euler


def read_angles_list(path: Path) -> NDArray[np.float64]:
    """Read the sampled orientation grid.

    Args:
        path: Path to ``<base>_angles.list`` (tab/space separated, 3 columns).

    Returns:
        Array ``(N_ANGLES, 3)`` of ``[phi, theta, psi−phi]`` in degrees.

    Raises:
        ValueError: If the row count is not :data:`N_ANGLES` or width is not 3.
    """
    arr = np.loadtxt(path, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise ValueError(f"{path}: expected (*, 3) angles, got {arr.shape}")
    if arr.shape[0] != N_ANGLES:
        raise ValueError(f"{path}: expected {N_ANGLES} rows, got {arr.shape[0]}")
    return arr


def euler_for_angle_idx(
    angles_list: NDArray[np.float64], angle_idx: ArrayLike
) -> NDArray[np.float64]:
    """Look up ``[phi, theta, psi−phi]`` for a **1-based** ``angle_idx`` (SPEC §5).

    Args:
        angles_list: The ``(N_ANGLES, 3)`` grid from :func:`read_angles_list`.
        angle_idx: 1-based angle index (scalar or array).

    Returns:
        The euler triple(s): ``(3,)`` for scalar input, ``S + (3,)`` for array input.
    """
    idx = np.asarray(angle_idx, dtype=np.int64) - 1
    return np.asarray(angles_list, dtype=np.float64)[idx]


def normal_for_angle_idx(
    angles_list: NDArray[np.float64], angle_idx: ArrayLike
) -> NDArray[np.float64]:
    """Outward normal for a **1-based** ``angle_idx`` (SPEC §5).

    The dense field stores the raw argmax, so no C12 correction is applied.

    Args:
        angles_list: The ``(N_ANGLES, 3)`` grid.
        angle_idx: 1-based angle index (scalar or array).

    Returns:
        Outward normal(s) in the raw emClarity frame ``(nx, ny, nz)``.
    """
    eul = euler_for_angle_idx(angles_list, angle_idx)
    return normal_from_euler(eul[..., 0], eul[..., 1])
