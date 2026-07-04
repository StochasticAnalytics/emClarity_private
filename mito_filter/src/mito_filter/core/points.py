"""PointCloud: a struct-of-arrays sparse point set with named per-point attributes.

Domain-free. Positions are in the convmap voxel frame ``(z, y, x)``; attrs carry scalar
or vector per-point data (cc, normal, template_idx, subtomo_id, active, ...). Fully
implemented and immutable-by-convention (``with_attr`` / ``subset`` return new clouds).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping

import numpy as np
from numpy.typing import NDArray

# Domain-free core carries NO emClarity import (DESIGN §0/§1.6: "the core never mentions
# emClarity"). The active/removed convention is a generic keep/remove sentinel; the default here
# mirrors emClarity's ``constants.REMOVED_FLAG`` (pinned equal by tests), but callers that live in
# the emClarity adapter pass it in explicitly rather than core importing it.
DEFAULT_REMOVED_FLAG: int = -9999


@dataclass
class PointCloud:
    """Sparse points (voxel frame) plus arbitrary per-point scalar & vector attrs.

    Args:
        xyz: Positions, shape ``(N, 3)``, in the convmap voxel frame ``(z, y, x)``.
        attrs: Mapping name -> array whose leading axis is ``N``. Scalar attrs are
            ``(N,)``; vector attrs (e.g. ``"normal"``) are ``(N, 3)``.

    Attributes:
        xyz: The positions array.
        attrs: The per-point attribute arrays.
    """

    xyz: NDArray
    attrs: Dict[str, NDArray] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.xyz = np.asarray(self.xyz)
        if self.xyz.ndim != 2 or self.xyz.shape[1] != 3:
            raise ValueError(f"xyz must be (N, 3), got {self.xyz.shape}")
        n = self.xyz.shape[0]
        for k, v in self.attrs.items():
            arr = np.asarray(v)
            if arr.shape[0] != n:
                raise ValueError(f"attr '{k}' leading dim {arr.shape[0]} != N {n}")
            self.attrs[k] = arr

    @property
    def n(self) -> int:
        """Number of points."""
        return int(self.xyz.shape[0])

    def __len__(self) -> int:
        return self.n

    def with_attr(self, k: str, v: NDArray) -> "PointCloud":
        """Return a copy with attribute ``k`` set to ``v``.

        Args:
            k: Attribute name.
            v: Array whose leading dim equals ``N``.

        Returns:
            A new PointCloud sharing ``xyz`` and existing attrs, plus/overriding ``k``.
        """
        arr = np.asarray(v)
        if arr.shape[0] != self.n:
            raise ValueError(f"attr '{k}' leading dim {arr.shape[0]} != N {self.n}")
        new_attrs = dict(self.attrs)
        new_attrs[k] = arr
        return PointCloud(self.xyz, new_attrs)

    def subset(self, mask: NDArray) -> "PointCloud":
        """Return the subset selected by a boolean mask or integer index array.

        Args:
            mask: Boolean array ``(N,)`` or integer index array into the points.

        Returns:
            A new PointCloud with positions and every attr sliced identically.
        """
        idx = np.asarray(mask)
        return PointCloud(self.xyz[idx], {k: v[idx] for k, v in self.attrs.items()})

    def to_active_flag(self, removed_flag: int = DEFAULT_REMOVED_FLAG) -> NDArray:
        """Return the active flag per point: 1 keep, ``removed_flag`` remove.

        Uses the boolean ``"active"`` attr if present (True -> 1, False ->
        ``removed_flag``); otherwise all points are active. The sentinel is a parameter (default
        :data:`DEFAULT_REMOVED_FLAG`) so domain-free core never imports the emClarity constant;
        emClarity callers pass ``constants.REMOVED_FLAG``.

        Args:
            removed_flag: The integer sentinel written for inactive points.

        Returns:
            Integer array ``(N,)`` of ``{1, removed_flag}``.
        """
        if "active" in self.attrs:
            active = np.asarray(self.attrs["active"]).astype(bool)
        else:
            active = np.ones(self.n, dtype=bool)
        return np.where(active, 1, int(removed_flag)).astype(np.int64)

    def get(self, k: str) -> NDArray:
        """Return attribute ``k`` (helpful KeyError if absent).

        Args:
            k: Attribute name.

        Returns:
            The attribute array.

        Raises:
            KeyError: If ``k`` is not present (message lists available attrs).
        """
        try:
            return self.attrs[k]
        except KeyError:
            avail = ", ".join(sorted(self.attrs)) or "<none>"
            raise KeyError(f"PointCloud has no attr '{k}'. Available: {avail}") from None

    @classmethod
    def from_mapping(cls, xyz: NDArray, attrs: Mapping[str, NDArray]) -> "PointCloud":
        """Build a PointCloud from positions and an attr mapping (copies the mapping)."""
        return cls(np.asarray(xyz), dict(attrs))
