"""DenseFieldPeakSource: re-detect candidates from a dense field + oriented-NMS de-dup.

The csv is greedy NMS with a large oriented erase, so it collapses membrane sheets and
gold/ice clusters to a few sparse survivors (SPEC §6: 291,224 vox >= 6.07 vs 1249 csv peaks
for H99_2_100). Re-detecting hits straight from the dense convmap CC field recovers that
structure — but a naive local-maximum scan double-counts a single particle whose CC blob
spans several voxels. :class:`DenseFieldPeakSource` therefore reproduces the csv's rotated
erase cylinder as an **oriented non-max suppression** step (DESIGN §9.6): after accepting a
peak, every weaker peak inside that peak's oriented ``Peak_mRadius`` cylinder
(``[210, 210, 320] A`` -> bin5 ``[16, 16, 26]`` vox, SPEC §6) is suppressed.

Because the in-plane radii are equal (16 == 16), the cylinder is rotationally symmetric about
its axis, so only the peak's **axis direction (the outward normal)** is needed — exactly the
C12-invariant quantity the pipeline trusts (SPEC §4). No full rotation matrix is required. When
no per-peak normal is available (Phase A, before the dense angle field exists), an axis-aligned
ellipsoid (z = the long axis) is used as an isotropic fallback.

Detection streams the volume in halo-padded blocks (never hot-loads 559 MB) and de-duplicates
local maxima across block seams by keeping only maxima whose argmax voxel lies in the block
core.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Tuple

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from ..core.backend import Device
from ..core.chunking import core_offset_in_read
from ..core.field import DenseField
from ..core.grid import VoxelGrid
from ..emclarity.constants import APIX_A, ERASE_RADIUS_A
from .source import CandidateSet, CandidateSource

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..datasets.base import TomogramRef
    from ..fields.provider import FieldRegistry


def default_erase_radii_vox() -> Tuple[float, float]:
    """Return the bin5 oriented erase cylinder ``(r_radial, r_axial)`` in voxels (SPEC §6).

    ``Peak_mRadius = [210, 210, 320] A`` at ``APIX_A = 12.5`` gives ``floor(210/12.5) = 16``
    radial and ``floor(320/12.5) = 25`` axial; emClarity's even-box parity bumps the axial
    half-length to 26, the SPEC-verified ``[16, 16, 26]`` vox cylinder.

    Returns:
        ``(r_radial_vox, r_axial_vox)`` = ``(16.0, 26.0)``.
    """
    r_radial = float(int(ERASE_RADIUS_A[0] // APIX_A))  # 16
    r_axial = float(int(ERASE_RADIUS_A[2] // APIX_A) + 1)  # 25 + parity -> 26
    return r_radial, r_axial


def oriented_nms(
    coords_zyx: NDArray,
    scores: NDArray,
    *,
    normals_zyx: Optional[NDArray] = None,
    r_radial_vox: float,
    r_axial_vox: float,
) -> NDArray[np.bool_]:
    """Greedy oriented non-max suppression matching the csv rotated erase cylinder (§9.6).

    Peaks are accepted strongest-first. When a peak is accepted, every weaker peak that falls
    inside that peak's oriented erase cylinder is suppressed. With a per-peak ``normal`` the
    cylinder axis is the normal (radial distance ``<= r_radial``, axial ``|offset| <=
    r_axial``); without normals an axis-aligned ellipsoid (z = the long ``r_axial`` axis) is
    used. All distances are in voxels.

    Args:
        coords_zyx: Peak positions ``(N, 3)`` in the ``(z, y, x)`` voxel frame.
        scores: Peak strengths ``(N,)`` (higher = stronger; kept preferentially).
        normals_zyx: Optional per-peak outward normals ``(N, 3)`` in ``(z, y, x)``; the
            cylinder axis. If omitted, the isotropic axis-aligned ellipsoid fallback is used.
        r_radial_vox: In-plane cylinder radius in voxels.
        r_axial_vox: Cylinder half-length (along the axis) in voxels.

    Returns:
        Boolean keep mask ``(N,)`` — True for surviving (non-suppressed) peaks.
    """
    coords = np.asarray(coords_zyx, dtype=np.float64)
    n = coords.shape[0]
    scores = np.asarray(scores, dtype=np.float64).reshape(n)
    if n == 0:
        return np.zeros(0, dtype=bool)

    normals: Optional[NDArray] = None
    if normals_zyx is not None:
        normals = np.asarray(normals_zyx, dtype=np.float64).reshape(n, 3)
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = np.divide(normals, norms, out=np.zeros_like(normals), where=norms > 0)

    # Bounding-sphere radius of the oriented cylinder: a point can satisfy axial <= r_axial AND
    # radial <= r_radial while lying up to sqrt(r_radial^2 + r_axial^2) from the center, so a
    # max() reach silently misses genuinely-inside neighbors near the rim. hypot is the true
    # bound; it also covers the ellipsoid fallback (bound r_axial), whose inside-test rejects the
    # few extra candidates the wider neighbor query returns.
    reach = float(np.hypot(r_radial_vox, r_axial_vox))
    tree = cKDTree(coords)
    order = np.argsort(-scores, kind="stable")  # strongest first
    suppressed = np.zeros(n, dtype=bool)

    for i in order:
        if suppressed[i]:
            continue
        neigh = tree.query_ball_point(coords[i], reach)
        axis = normals[i] if (normals is not None) else None
        use_axis = axis is not None and float(np.dot(axis, axis)) > 0.0
        for j in neigh:
            if j == i or suppressed[j] or scores[j] > scores[i]:
                continue
            d = coords[j] - coords[i]
            if use_axis:
                assert axis is not None
                a = float(abs(np.dot(d, axis)))
                radial = float(np.sqrt(max(0.0, float(d @ d) - a * a)))
                inside = a <= r_axial_vox and radial <= r_radial_vox
            else:
                # axis-aligned ellipsoid: z is the long (axial) axis, x/y radial.
                ell = (
                    (d[0] / r_axial_vox) ** 2
                    + (d[1] / r_radial_vox) ** 2
                    + (d[2] / r_radial_vox) ** 2
                )
                inside = ell <= 1.0
            if inside:
                suppressed[j] = True
    return ~suppressed


class DenseFieldPeakSource(CandidateSource):
    """Re-detect candidates from a dense field with oriented-NMS de-dup (DESIGN §9.6).

    Args:
        field_name: Name of the scalar field to detect peaks in (default ``"cc"``).
        threshold: Minimum field value for a voxel to seed a candidate. Voxels below this are
            ignored (SPEC §1: the convmap background is ~ ``N(3.28, 0.48)``; a p99-ish floor
            keeps only the elevated-CC band).
        normal_field_name: Optional 3-channel field supplying a per-peak outward normal for the
            oriented cylinder (e.g. the decoded dense ``"normal"``); ``None`` uses the isotropic
            ellipsoid fallback.
        registry: Optional :class:`FieldRegistry` used by :meth:`candidates` to resolve the
            field(s) for a tomogram. Not needed when calling :meth:`detect` directly.
        device: Compute backend for a registry resolve (default CPU).
        peak_radius_vox: Local-maximum neighborhood radius (a voxel must be the max of its
            ``(2*r+1)^3`` neighborhood to seed).
        r_radial_vox: Oriented erase cylinder in-plane radius; defaults to the SPEC bin5 value.
        r_axial_vox: Oriented erase cylinder half-length; defaults to the SPEC bin5 value.
        block_shape: Core block size for halo-aware streaming detection.

    Attributes:
        field_name: The detected field name.
        threshold: The detection floor.
        normal_field_name: The optional normal-field name.
        r_radial_vox: The NMS in-plane radius.
        r_axial_vox: The NMS half-length.
    """

    def __init__(
        self,
        *,
        field_name: str = "cc",
        threshold: float,
        normal_field_name: Optional[str] = None,
        registry: "Optional[FieldRegistry]" = None,
        device: Device = Device.CPU,
        peak_radius_vox: int = 1,
        r_radial_vox: Optional[float] = None,
        r_axial_vox: Optional[float] = None,
        block_shape: Tuple[int, int, int] = (128, 128, 128),
    ) -> None:
        d_rad, d_ax = default_erase_radii_vox()
        self.field_name = field_name
        self.threshold = float(threshold)
        self.normal_field_name = normal_field_name
        self._registry = registry
        self._device = device
        self.peak_radius_vox = int(peak_radius_vox)
        self.r_radial_vox = float(r_radial_vox) if r_radial_vox is not None else d_rad
        self.r_axial_vox = float(r_axial_vox) if r_axial_vox is not None else d_ax
        self.block_shape = block_shape

    def candidates(self, tomo: "TomogramRef", grid: VoxelGrid) -> CandidateSet:
        """Resolve the field(s) for ``tomo`` via the registry, then detect + de-dup.

        Args:
            tomo: The tomogram to source candidates from.
            grid: The convmap voxel grid (must match the resolved field's grid).

        Returns:
            The de-duplicated :class:`CandidateSet`.

        Raises:
            ValueError: If no :class:`FieldRegistry` was provided at construction.
        """
        if self._registry is None:
            raise ValueError(
                "DenseFieldPeakSource.candidates needs a FieldRegistry; construct with "
                "registry=... or call detect(field, ...) directly"
            )
        field = self._registry.resolve(self.field_name, tomo, device=self._device)
        normal_field: Optional[DenseField] = None
        if self.normal_field_name is not None:
            normal_field = self._registry.resolve(self.normal_field_name, tomo, device=self._device)
        return self.detect(field, normal_field=normal_field)

    def detect(
        self, field: DenseField, *, normal_field: Optional[DenseField] = None
    ) -> CandidateSet:
        """Detect local-maximum peaks in ``field`` and apply oriented-NMS de-dup.

        Args:
            field: The scalar dense field to detect peaks in.
            normal_field: Optional 3-channel normal field; sampled at each seed to orient the
                erase cylinder. ``None`` uses the isotropic ellipsoid fallback.

        Returns:
            A :class:`CandidateSet` on ``field.grid`` with a ``"cc"`` attr (the peak value) and,
            when ``normal_field`` is given, a ``"normal"`` ``(N, 3)`` attr in ``(z, y, x)``.
        """
        coords, scores = self._local_maxima(field)
        normals: Optional[NDArray] = None
        if normal_field is not None and coords.shape[0] > 0:
            normals = np.asarray(
                normal_field.sample_at(coords, reduce="mean", radius=0), dtype=np.float64
            ).reshape(-1, 3)

        keep = oriented_nms(
            coords,
            scores,
            normals_zyx=normals,
            r_radial_vox=self.r_radial_vox,
            r_axial_vox=self.r_axial_vox,
        )
        coords = coords[keep]
        scores = scores[keep]
        attrs: Dict[str, NDArray] = {"cc": scores.astype(np.float64)}
        if normals is not None:
            attrs["normal"] = normals[keep]
        return CandidateSet(coords_zyx=coords, grid=field.grid, attrs=attrs)

    def _local_maxima(self, field: DenseField) -> Tuple[NDArray, NDArray]:
        """Stream halo-padded blocks and collect thresholded local maxima (seam-deduped).

        A voxel seeds a peak when it equals the maximum of its ``(2*r+1)^3`` neighborhood and
        is ``>= threshold``. Only maxima whose argmax voxel lies in the block *core* are kept,
        so a peak on a seam is emitted exactly once.

        Args:
            field: The scalar dense field.

        Returns:
            ``(coords_zyx, scores)`` — ``(M, 3)`` float64 voxel coords and ``(M,)`` peak values.
        """
        r = self.peak_radius_vox
        size = 2 * r + 1
        shape = field.grid.shape
        all_coords = []
        all_scores = []
        for blk, data in field.iter_blocks(self.block_shape, halo=r):
            data = np.asarray(data, dtype=np.float32)
            maxf = ndi.maximum_filter(data, size=size, mode="nearest")
            mask = (data >= maxf) & (data >= self.threshold)
            # Restrict to this block's core so seam peaks are not double-counted.
            cz, cy, cx = core_offset_in_read(blk, shape)
            core_mask = np.zeros_like(mask)
            core_mask[cz, cy, cx] = True
            mask &= core_mask
            if not mask.any():
                continue
            read = blk.read_slices(shape)
            z0, y0, x0 = read[0].start, read[1].start, read[2].start
            zz, yy, xx = np.nonzero(mask)
            coords = np.stack([zz + z0, yy + y0, xx + x0], axis=1).astype(np.float64)
            all_coords.append(coords)
            all_scores.append(data[zz, yy, xx].astype(np.float64))
        if not all_coords:
            return np.zeros((0, 3), dtype=np.float64), np.zeros(0, dtype=np.float64)
        return np.concatenate(all_coords, axis=0), np.concatenate(all_scores, axis=0)
