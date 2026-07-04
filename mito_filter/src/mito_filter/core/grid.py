"""VoxelGrid: the shared coordinate frame for all co-registered dense fields.

Domain-free. World coordinates are in Angstrom; voxel coordinates are in the convmap
``.rec`` frame ``(z, y, x)`` C-order (SPEC §1, §3). Fully implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class VoxelGrid:
    """An immutable voxel grid: shape, physical voxel size, axis order.

    Args:
        shape: Volume shape ``(nz, ny, nx)`` in C / numpy order (matches an mrc mmap,
            x fastest). For the dev-set convmap this is ``(448, 942, 662)``.
        apix: Physical voxel size in Angstrom (12.5 for the bin5 convmap). NOT the mrc
            header's cosmetic 1.0.
        order: Axis order label; always ``"zyx"`` for this codebase.

    Attributes:
        shape: The volume shape.
        apix: Angstrom per voxel.
        order: The axis-order label.
    """

    shape: Tuple[int, int, int]
    apix: float
    order: str = "zyx"

    @property
    def nz(self) -> int:
        """Number of z (slowest) voxels."""
        return self.shape[0]

    @property
    def ny(self) -> int:
        """Number of y voxels."""
        return self.shape[1]

    @property
    def nx(self) -> int:
        """Number of x (fastest) voxels."""
        return self.shape[2]

    @property
    def n_voxels(self) -> int:
        """Total voxel count."""
        return self.shape[0] * self.shape[1] * self.shape[2]

    def world(self, ijk: NDArray) -> NDArray:
        """Convert voxel coordinates to world coordinates (Angstrom).

        Args:
            ijk: Array ``(..., 3)`` of voxel coordinates in this grid's ``order``.

        Returns:
            Array ``(..., 3)`` of world coordinates in Angstrom (elementwise
            ``ijk * apix``).
        """
        return np.asarray(ijk, dtype=np.float64) * self.apix

    def voxel(self, xyz: NDArray) -> NDArray:
        """Convert world coordinates (Angstrom) to voxel coordinates.

        Args:
            xyz: Array ``(..., 3)`` of world coordinates in Angstrom.

        Returns:
            Array ``(..., 3)`` of (fractional) voxel coordinates (``xyz / apix``).
        """
        return np.asarray(xyz, dtype=np.float64) / self.apix

    def same_grid(self, other: "VoxelGrid", *, atol: float = 1e-6) -> bool:
        """Return True if ``other`` has the same shape and (near-equal) apix.

        Args:
            other: The grid to compare against.
            atol: Absolute tolerance on the apix comparison.

        Returns:
            True if shapes are identical and voxel sizes agree within ``atol``.
        """
        return tuple(self.shape) == tuple(other.shape) and abs(self.apix - other.apix) <= atol

    def in_bounds(self, ijk: NDArray) -> NDArray:
        """Return a boolean mask of which voxel coordinates lie inside the grid.

        Args:
            ijk: Array ``(N, 3)`` of voxel coordinates ``(z, y, x)``.

        Returns:
            Boolean array ``(N,)`` — True where ``0 <= coord < shape`` on every axis.
        """
        p = np.asarray(ijk)
        lo = np.all(p >= 0, axis=-1)
        hi = np.all(p < np.asarray(self.shape), axis=-1)
        return np.logical_and(lo, hi)
