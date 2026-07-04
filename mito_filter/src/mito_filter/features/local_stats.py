"""Local dense-statistics features: score-cluster density, Hessian blobness, gold proximity.

Gold beads and vitreous-ice artifacts appear as **compact clusters of extreme CC** (SPEC §1,
§6): high local density AND an isotropic (blob-like) Hessian signature, which distinguishes
them from the extended low-curvature CC *sheets* of a membrane. All three extractors gather
the ``cc`` field memory-safely at each candidate (and shifted sample points) — the full
volume is never loaded. :class:`GoldFiducialProximity` reuses the already-computed
tilt-series bead locations (SPEC §9.4) via a ``gold_dist`` field or ``gold`` points.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from ..candidates.source import CandidateSet
from ..core.field import DenseField
from ..emclarity.constants import BACKGROUND_MEAN, BACKGROUND_STD
from .engine import FEATURE_REGISTRY, neutral_column, resolve_scalar
from .extractor import ArrayT, BlockCtx, FeatureExtractor

_EPS = 1e-6


def _sample(field: DenseField, pts: NDArray, *, reduce: str, radius: int) -> NDArray[np.float32]:
    """Sample a scalar field at ``pts`` (memory-safe), returning an ``(N,)`` fp32 array."""
    return np.asarray(field.sample_at(pts, reduce=reduce, radius=radius), dtype=np.float32).reshape(
        -1
    )


@FEATURE_REGISTRY.register("score_cluster_density")
class ScoreClusterDensity(FeatureExtractor):
    """Local CC density around each candidate (gold/ice/membrane elevation, SPEC §1, §6).

    Emits the local max and mean of the ``cc`` field over a small neighborhood and a
    background-z-scored density (``(local_mean - bg_mean) / bg_std``, background stats from
    ``ctx.meta`` or the SPEC constants). A compact gold/ice cluster or a membrane sheet reads
    a high positive z; isolated background reads ~0.

    Args:
        radius: Neighborhood radius in voxels for the local statistics.
    """

    produces = ("cc_local_max", "cc_local_mean", "cc_cluster_z")
    needs_fields = ("cc",)
    theta_dependent = False

    def __init__(self, radius: int = 2, **params: object) -> None:
        self.params: Dict[str, object] = {"radius": radius, **params}
        self.radius = int(radius)

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the local-max, local-mean, and z-scored local-density columns."""
        n = cand.n
        if "cc" in fields:
            cc_field = fields["cc"]
            local_max = _sample(cc_field, cand.coords_zyx, reduce="max", radius=self.radius)
            local_mean = _sample(cc_field, cand.coords_zyx, reduce="mean", radius=self.radius)
        else:
            attr = resolve_scalar(cand, fields, "cc", attr="cc", reduce="max", radius=1)
            local_max = attr if attr is not None else neutral_column(n)
            local_mean = neutral_column(n)
        mu = float(ctx.meta.get("bg_mean", BACKGROUND_MEAN))  # type: ignore[arg-type]
        sigma = float(ctx.meta.get("bg_std", BACKGROUND_STD))  # type: ignore[arg-type]
        sigma = sigma if sigma > _EPS else 1.0
        cluster_z = (local_mean - mu) / sigma
        return {
            "cc_local_max": local_max,
            "cc_local_mean": local_mean,
            "cc_cluster_z": cluster_z.astype(np.float32),
        }


@FEATURE_REGISTRY.register("blobness")
class Blobness(FeatureExtractor):
    """Hessian (Frangi-style) blob vs sheet signature of the ``cc`` field (SPEC §1, §6).

    At each candidate the ``cc`` field's ``3x3`` Hessian is estimated by central differences
    (step ``h`` voxels, each sample lightly box-smoothed) and its eigenvalues taken. A bright
    local structure (blob/sheet/line) has a negative strongest response; with ``|lambda1| <=
    |lambda2| <= |lambda3|``:

    * ``blobness`` = ``|lambda1| / |lambda3|`` — isotropy: ~1 for a compact gold/ice blob,
      ~0 for a membrane sheet or an edge line.
    * ``plateness`` = ``1 - |lambda2| / |lambda3|`` — one dominant eigenvalue -> a sheet
      (elevated-CC membrane bilayer).
    * ``hessian_strength`` = ``|lambda3|`` — overall structureness.

    All three are gated to bright structure (most-negative eigenvalue < 0); flat background
    reads 0. Weight by ``hessian_strength`` to suppress low-magnitude background responses.

    Args:
        step: Central-difference step ``h`` in voxels.
    """

    produces = ("blobness", "plateness", "hessian_strength")
    needs_fields = ("cc",)
    theta_dependent = False

    def __init__(self, step: int = 2, **params: object) -> None:
        self.params: Dict[str, object] = {"step": step, **params}
        self.step = max(1, int(step))

    def _hessian_eigs(self, field: DenseField, pts: NDArray) -> NDArray[np.float64]:
        """Return ascending eigenvalues ``(N, 3)`` of the field Hessian at ``pts``."""
        h = float(self.step)
        offs = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)

        def s(shift: NDArray) -> NDArray[np.float32]:
            return _sample(field, pts + shift[None, :], reduce="mean", radius=1)

        f0 = _sample(field, pts, reduce="mean", radius=1)
        n = pts.shape[0]
        hess = np.zeros((n, 3, 3), dtype=np.float64)
        for a in range(3):
            fp = s(h * offs[a])
            fm = s(-h * offs[a])
            hess[:, a, a] = (fp - 2.0 * f0 + fm) / (h * h)
        for a, b in ((0, 1), (0, 2), (1, 2)):
            fpp = s(h * offs[a] + h * offs[b])
            fpm = s(h * offs[a] - h * offs[b])
            fmp = s(-h * offs[a] + h * offs[b])
            fmm = s(-h * offs[a] - h * offs[b])
            cross = (fpp - fpm - fmp + fmm) / (4.0 * h * h)
            hess[:, a, b] = cross
            hess[:, b, a] = cross
        return np.linalg.eigvalsh(hess)  # ascending per row

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return blobness / plateness / structureness columns from the Hessian eigenvalues."""
        n = cand.n
        if "cc" not in fields:
            return {k: neutral_column(n) for k in self.produces}
        eig = self._hessian_eigs(fields["cc"], np.asarray(cand.coords_zyx, dtype=np.float64))
        # ascending eigenvalues: eig[:, 0] is the most negative. A bright local structure
        # (blob/sheet/line) has a negative strongest response in >= 1 direction; blobness vs
        # plateness (below) then separate the *type* via the |eigenvalue| ratios.
        bright = (eig[:, 0] < 0.0).astype(np.float64)
        mag = np.sort(np.abs(eig), axis=1)  # a <= b <= c
        a, b, c = mag[:, 0], mag[:, 1], mag[:, 2]
        blobness = bright * (a / (c + _EPS))
        plateness = bright * (1.0 - b / (c + _EPS))
        return {
            "blobness": blobness.astype(np.float32),
            "plateness": plateness.astype(np.float32),
            "hessian_strength": c.astype(np.float32),
        }


@FEATURE_REGISTRY.register("gold_fiducial_proximity")
class GoldFiducialProximity(FeatureExtractor):
    """Distance from each candidate to the nearest gold fiducial (SPEC §9.4).

    Gold beads were already located during tilt-series alignment. This reads a ``gold_dist``
    field (an EDT in voxels, sampled and converted to Angstrom) when present; otherwise it
    computes the nearest-neighbor distance to explicit gold points supplied in
    ``ctx.meta['gold_points_zyx']`` ``(G, 3)``. When neither exists the field is MISSING and
    the columns are neutral (``inf`` distance / ``0`` proximity).

    Args:
        near_A: Distance (Angstrom) under which a candidate counts as "near gold".
    """

    produces = ("gold_dist_A", "near_gold")
    needs_fields = ("gold_dist",)
    theta_dependent = False

    def __init__(self, near_A: float = 250.0, **params: object) -> None:
        self.params: Dict[str, object] = {"near_A": near_A, **params}
        self.near_A = float(near_A)

    def _dist_A(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Optional[NDArray[np.float32]]:
        """Nearest-gold distance in Angstrom, or None if no gold source is available."""
        if "gold_dist" in fields:
            d_vox = _sample(fields["gold_dist"], cand.coords_zyx, reduce="center", radius=0)
            return (np.abs(d_vox) * float(ctx.grid.apix)).astype(np.float32)
        gold = ctx.meta.get("gold_points_zyx")
        if gold is not None:
            gpts = np.asarray(gold, dtype=np.float64).reshape(-1, 3)
            if gpts.shape[0] == 0:
                return None
            tree = cKDTree(gpts * float(ctx.grid.apix))
            d, _ = tree.query(np.asarray(cand.coords_zyx, dtype=np.float64) * float(ctx.grid.apix))
            return np.asarray(d, dtype=np.float32).reshape(-1)
        return None

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the gold-distance (Angstrom) and near-gold indicator columns."""
        dist = self._dist_A(cand, fields, ctx)
        if dist is None:
            inf = neutral_column(cand.n, fill=float("inf"))
            return {"gold_dist_A": inf, "near_gold": neutral_column(cand.n, fill=0.0)}
        near = (dist < self.near_A).astype(np.float32)
        return {"gold_dist_A": dist, "near_gold": near}


__all__: List[str] = ["ScoreClusterDensity", "Blobness", "GoldFiducialProximity"]
