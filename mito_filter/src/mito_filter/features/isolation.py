"""Spatial-isolation features (DESIGN §6).

A true target is one member of a densely-tiled membrane surface; an isolated hit far from any
coherent surface is a false-positive signal. :class:`NeighborDensity` counts co-located
candidates; :class:`OffSurfaceIsolation` measures how far a candidate sits off the local plane
of its neighbors (and flags candidates with too few neighbors to define a surface at all).
Both are theta-independent (cached once).
"""

from __future__ import annotations

from typing import Dict, List, Mapping

import numpy as np

from ..candidates.source import CandidateSet
from ..core.field import DenseField
from ..core.neighbors import NeighborIndex
from .engine import FEATURE_REGISTRY
from .extractor import ArrayT, BlockCtx, FeatureExtractor

_SPHERE = 4.0 / 3.0 * np.pi


@FEATURE_REGISTRY.register("neighbor_density")
class NeighborDensity(FeatureExtractor):
    """Number and volumetric density of candidates within a radius (DESIGN §6).

    ``neighbor_count`` excludes the candidate itself; ``neighbor_density`` normalizes by the
    query-sphere volume (candidates per ``1e6`` Angstrom^3). Low density -> an isolated
    (false-positive-leaning) hit.

    Args:
        radius_A: Neighborhood radius in Angstrom.
    """

    produces = ("neighbor_count", "neighbor_density")
    needs_fields = ()
    theta_dependent = False

    def __init__(self, radius_A: float = 800.0, **params: object) -> None:
        self.params: Dict[str, object] = {"radius_A": radius_A, **params}
        self.radius_A = float(radius_A)

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the neighbor-count and volumetric-density columns."""
        n = cand.n
        if n == 0:
            return {
                "neighbor_count": np.zeros(0, dtype=np.float32),
                "neighbor_density": np.zeros(0, dtype=np.float32),
            }
        idx = NeighborIndex(cand.coords_zyx, apix=float(ctx.grid.apix))
        raw = idx.count_within(cand.coords_zyx, self.radius_A).astype(np.float64)
        count = np.maximum(raw - 1.0, 0.0)  # drop self
        vol = _SPHERE * self.radius_A**3
        density = count / max(vol, 1.0) * 1.0e6
        return {
            "neighbor_count": count.astype(np.float32),
            "neighbor_density": density.astype(np.float32),
        }


@FEATURE_REGISTRY.register("off_surface_isolation")
class OffSurfaceIsolation(FeatureExtractor):
    """Perpendicular offset of a candidate from the local plane of its neighbors (DESIGN §6).

    For each candidate a plane is fit (least-squares / SVD) to its neighbors within
    ``radius_A`` and the candidate's perpendicular distance to that plane is reported in
    Angstrom — small on a smooth surface, large for an off-surface interloper. Candidates with
    fewer than ``min_neighbors`` neighbors cannot define a surface and are flagged
    ``is_isolated = 1`` with ``off_surface_A = radius_A`` (maximally isolated).

    Args:
        radius_A: Neighborhood radius in Angstrom.
        min_neighbors: Minimum neighbors required to fit a local plane.
    """

    produces = ("off_surface_A", "is_isolated")
    needs_fields = ()
    theta_dependent = False

    def __init__(self, radius_A: float = 800.0, min_neighbors: int = 4, **params: object) -> None:
        self.params: Dict[str, object] = {
            "radius_A": radius_A,
            "min_neighbors": min_neighbors,
            **params,
        }
        self.radius_A = float(radius_A)
        self.min_neighbors = int(min_neighbors)

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the off-plane distance (Angstrom) and isolation-flag columns."""
        n = cand.n
        apix = float(ctx.grid.apix)
        off = np.full(n, self.radius_A, dtype=np.float64)
        isolated = np.ones(n, dtype=np.float64)
        if n == 0:
            return {
                "off_surface_A": off.astype(np.float32),
                "is_isolated": isolated.astype(np.float32),
            }
        pos = np.asarray(cand.coords_zyx, dtype=np.float64)
        idx = NeighborIndex(pos, apix=apix)
        neighbors = idx.self_radius(self.radius_A)
        for i, nb in enumerate(neighbors):
            nb = np.asarray(nb, dtype=np.int64)
            if nb.size < self.min_neighbors:
                continue
            pts = pos[nb]
            centroid = pts.mean(axis=0)
            _, _, vh = np.linalg.svd(pts - centroid, full_matrices=False)
            plane_normal = vh[-1]
            dist_vox = abs(float((pos[i] - centroid) @ plane_normal))
            off[i] = min(dist_vox * apix, self.radius_A)
            isolated[i] = 0.0
        return {
            "off_surface_A": off.astype(np.float32),
            "is_isolated": isolated.astype(np.float32),
        }


__all__: List[str] = ["NeighborDensity", "OffSurfaceIsolation"]
