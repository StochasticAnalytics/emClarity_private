"""CC-gated surface-curvature features (DESIGN §6, §9.3).

True targets sit in a smooth, low-curvature, normal-coherent membrane with the template ``+Z``
as the outward normal; a false positive sits in an incoherent-normal neighborhood. These
extractors compute per-candidate normal coherence, quadric surface-fit residual, and principal
curvature over each candidate's spatial neighborhood, driving them through the one
``core/surfaces`` API for **either** sparse csv normals **or** a dense normal
:class:`~mito_filter.core.field.VectorField`.

**CC-gating (DESIGN §9.3) is the load-bearing rule:** a regenerated dense normal field stores
an argmax orientation at *every* voxel, and at low-CC background voxels that argmax is the
argmax of noise -> random normals that would swamp a surface fit. So every neighborhood here
is restricted to candidates whose co-located ``cc``/``snr`` clears a gate (``bg_mean +
gate_sigma * bg_std`` by default); gated-out candidates are masked to a neutral ``NaN`` (their
normals are untrusted) and never contribute as neighbors. This is what makes the fit see the
elevated-CC membrane band and ignore the background.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

import numpy as np
from numpy.typing import NDArray

from ..candidates.source import CandidateSet
from ..core.field import DenseField
from ..core.neighbors import NeighborIndex
from ..core.surfaces import normal_coherence, surface_residuals
from ..emclarity.constants import BACKGROUND_MEAN, BACKGROUND_STD
from .engine import FEATURE_REGISTRY, neutral_column, resolve_point_normals, resolve_scalar
from .extractor import ArrayT, BlockCtx, FeatureExtractor

_EPS = 1e-9


@dataclass
class _GatedNeighborhood:
    """The CC-gated subset of candidates and its self-neighbor lists.

    Attributes:
        n: Total candidate count (for scatter-back to full length).
        gate_idx: Indices (into the full set) of the gate-passing candidates.
        pos: Gate-passing positions ``(G, 3)``.
        normals: Gate-passing normals ``(G, 3)``.
        neighbors: Per-gated-point neighbor-index lists (into the gated subset, self excluded).
    """

    n: int
    gate_idx: NDArray
    pos: NDArray
    normals: NDArray
    neighbors: List[NDArray]


def _gate_values(
    cand: CandidateSet, fields: Mapping[str, DenseField]
) -> Optional[NDArray[np.float32]]:
    """Per-candidate gate strength: ``snr`` if available, else ``cc`` (None if neither)."""
    snr = resolve_scalar(cand, fields, "snr", attr="snr", reduce="max", radius=1)
    if snr is not None:
        return snr
    return resolve_scalar(cand, fields, "cc", attr="cc", reduce="max", radius=1)


def _resolve_normals(
    cand: CandidateSet, fields: Mapping[str, DenseField], mode: str
) -> Optional[NDArray[np.float64]]:
    """Resolve normals honoring ``mode`` (``auto`` / ``attr`` / ``field``)."""
    if mode == "field":
        if "normal" in fields:
            # A dense normal is a packed-argmax field: a rounded csv coord lands on a NEIGHBOR of
            # the true argmax voxel as often as on it (SPEC §3 sub-voxel offset), and the
            # neighbor's argmax orientation is frequently the OPPOSITE normal (~30% flipped on
            # real H99_2_100). Snap to the co-located cc argmax voxel first (as the csv score
            # itself is recovered), which restores >99% agreement with the csv cols 23-25 normal.
            # Falls back to a plain center read only when cc is unavailable.
            if "cc" in fields:
                sampled = fields["normal"].sample_at_companion_argmax(
                    cand.coords_zyx, fields["cc"], radius=1
                )
            else:
                sampled = fields["normal"].sample_at(cand.coords_zyx, reduce="center", radius=0)
            return np.asarray(sampled, dtype=np.float64).reshape(-1, 3)
        return None
    if mode == "attr":
        if "normal" in cand.attrs:
            return np.asarray(cand.get("normal"), dtype=np.float64).reshape(-1, 3)
        return None
    return resolve_point_normals(cand, fields)  # auto


def _build_gated(
    cand: CandidateSet,
    fields: Mapping[str, DenseField],
    ctx: BlockCtx,
    *,
    radius_A: float,
    gate_sigma: float,
    cc_gate: Optional[float],
    normal_source: str,
) -> Optional[_GatedNeighborhood]:
    """Build the CC-gated neighborhood, or None if normals are unavailable.

    Args:
        cand: The candidates.
        fields: Materialized dense fields.
        ctx: Block/backend context (supplies ``bg_mean`` / ``bg_std`` calibration).
        radius_A: Neighborhood radius in Angstrom.
        gate_sigma: Gate threshold in background sigmas above the background mean.
        cc_gate: Absolute gate override (skips the sigma computation when given).
        normal_source: ``auto`` / ``attr`` / ``field``.

    Returns:
        A :class:`_GatedNeighborhood`, or ``None`` when no normals source exists.
    """
    normals = _resolve_normals(cand, fields, normal_source)
    if normals is None:
        return None
    pos = np.asarray(cand.coords_zyx, dtype=np.float64)
    n = pos.shape[0]

    cc = _gate_values(cand, fields)
    if cc is None:
        gate = np.ones(n, dtype=bool)
    elif cc_gate is not None:
        gate = np.asarray(cc, dtype=np.float64) >= float(cc_gate)
    else:
        mu = float(ctx.meta.get("bg_mean", BACKGROUND_MEAN))  # type: ignore[arg-type]
        sigma = float(ctx.meta.get("bg_std", BACKGROUND_STD))  # type: ignore[arg-type]
        gate = np.asarray(cc, dtype=np.float64) >= mu + float(gate_sigma) * sigma

    gate_idx = np.nonzero(gate)[0]
    gpos = pos[gate_idx]
    gnrm = normals[gate_idx]
    if gate_idx.size == 0:
        neighbors: List[NDArray] = []
    else:
        idx = NeighborIndex(gpos, apix=float(ctx.grid.apix))
        neighbors = idx.self_radius(float(radius_A))
    return _GatedNeighborhood(n=n, gate_idx=gate_idx, pos=gpos, normals=gnrm, neighbors=neighbors)


class _CurvatureBase(FeatureExtractor):
    """Shared config + gated-neighborhood construction for the curvature extractors.

    Args:
        radius_A: Neighborhood radius in Angstrom. The default (800) is sized for the SPARSE csv
            regime: csv peaks are NMS-separated by the rotated ~``[210, 210, 320] A`` erase
            cylinder, so at ~300 A (≈ the erase radius) ~44% of real peaks have zero neighbors and
            the coherence/curvature terms are inert (verified on H99_2_100); ~800 A drops the
            isolated fraction to ~2% and the underdetermined-quadric fraction to ~23%.
        gate_sigma: CC gate in background sigmas above the background mean.
        cc_gate: Absolute CC/SNR gate override (bypasses ``gate_sigma`` when set).
        normal_source: ``auto`` (attr then field), ``attr`` (sparse csv), or ``field`` (dense).
    """

    theta_dependent = False

    def __init__(
        self,
        radius_A: float = 800.0,
        gate_sigma: float = 3.0,
        cc_gate: Optional[float] = None,
        normal_source: str = "auto",
        **params: object,
    ) -> None:
        self.params: Dict[str, object] = {
            "radius_A": radius_A,
            "gate_sigma": gate_sigma,
            "cc_gate": cc_gate,
            "normal_source": normal_source,
            **params,
        }
        self.radius_A = float(radius_A)
        self.gate_sigma = float(gate_sigma)
        self.cc_gate = None if cc_gate is None else float(cc_gate)
        self.normal_source = str(normal_source)
        if normal_source == "field":
            self.needs_fields = ("normal", "cc")
        else:
            self.needs_fields = ()

    def _gated(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Optional[_GatedNeighborhood]:
        """Construct this extractor's CC-gated neighborhood."""
        return _build_gated(
            cand,
            fields,
            ctx,
            radius_A=self.radius_A,
            gate_sigma=self.gate_sigma,
            cc_gate=self.cc_gate,
            normal_source=self.normal_source,
        )


@FEATURE_REGISTRY.register("normal_coherence")
class NormalCoherence(_CurvatureBase):
    """Per-candidate normal coherence over the CC-gated neighborhood (DESIGN §9.3).

    Coherence is the mean-resultant length of the unit normals in the gate-passing
    neighborhood: ~1 on a coherent membrane surface, ->0 in the incoherent argmax-of-noise
    regime. Gated-out (low-CC) candidates read ``NaN`` (untrusted normals).
    """

    produces = ("normal_coherence",)

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the CC-gated per-candidate normal-coherence column."""
        g = self._gated(cand, fields, ctx)
        if g is None:
            return {"normal_coherence": neutral_column(cand.n)}
        out = neutral_column(g.n)
        if g.gate_idx.size:
            coh = normal_coherence(g.normals, g.neighbors)
            out[g.gate_idx] = coh.astype(np.float32)
        return {"normal_coherence": out}


@FEATURE_REGISTRY.register("surface_fit_residual")
class SurfaceFitResidual(_CurvatureBase):
    """Quadric surface-fit residual over each CC-gated neighborhood (DESIGN §6).

    A smooth membrane patch fits a local quadric with a low RMS height residual; a false
    positive in an incoherent neighborhood fits poorly. Residual is reported in Angstrom
    (voxel residual ``* apix``). Gated-out candidates read ``NaN``.
    """

    produces = ("surface_residual_A",)

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the CC-gated per-candidate surface-fit residual column (Angstrom)."""
        g = self._gated(cand, fields, ctx)
        if g is None:
            return {"surface_residual_A": neutral_column(cand.n)}
        out = neutral_column(g.n)
        if g.gate_idx.size:
            res, _k1, _k2 = surface_residuals(g.pos, g.normals, g.neighbors)
            out[g.gate_idx] = (res * float(ctx.grid.apix)).astype(np.float32)
        return {"surface_residual_A": out}


@FEATURE_REGISTRY.register("principal_curvature")
class PrincipalCurvature(_CurvatureBase):
    """Principal curvatures of the fitted quadric over each CC-gated neighborhood (DESIGN §6).

    ``k1``, ``k2`` (``k1 >= k2``) and their mean, in ``1/Angstrom`` (voxel curvature ``/
    apix``). The extended outer mito membrane is low-curvature; a small closed interior
    replication vesicle is high-curvature — the discriminator. Gated-out candidates read
    ``NaN``.
    """

    produces = ("curv_k1", "curv_k2", "curv_mean")

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the CC-gated principal-curvature columns (1/Angstrom)."""
        g = self._gated(cand, fields, ctx)
        if g is None:
            return {k: neutral_column(cand.n) for k in self.produces}
        k1 = neutral_column(g.n)
        k2 = neutral_column(g.n)
        kmean = neutral_column(g.n)
        if g.gate_idx.size:
            _res, kk1, kk2 = surface_residuals(g.pos, g.normals, g.neighbors)
            apix = float(ctx.grid.apix)
            kk1_A = kk1 / max(apix, _EPS)
            kk2_A = kk2 / max(apix, _EPS)
            k1[g.gate_idx] = kk1_A.astype(np.float32)
            k2[g.gate_idx] = kk2_A.astype(np.float32)
            kmean[g.gate_idx] = (0.5 * (kk1_A + kk2_A)).astype(np.float32)
        return {"curv_k1": k1, "curv_k2": k2, "curv_mean": kmean}
