"""Membrane-geometry features (DESIGN §6, §7.1; SPEC §8).

Distance to a membrane, the inside/outside sign, and a closed-shell (small interior
replication-vesicle vs extended outer mito membrane) score. These consume a membrane field
that a :class:`~mito_filter.fields.provider.FieldProvider` generates (SPEC §8 — none exists on
disk today), so **every extractor returns a neutral column when the membrane field is
MISSING** (DESIGN §5 mixed-availability rule): the dependent constraint then contributes a
neutral value instead of failing.
"""

from __future__ import annotations

from typing import Dict, List, Mapping

import numpy as np
from numpy.typing import NDArray

from ..candidates.source import CandidateSet
from ..core.field import DenseField
from .engine import FEATURE_REGISTRY, neutral_column, resolve_point_normals
from .extractor import ArrayT, BlockCtx, FeatureExtractor

_MEMBRANE_SDF = "membrane_sdf"
_EPS = 1e-9


def _sdf_gradient(field: DenseField, pts: NDArray, h: float) -> NDArray[np.float64]:
    """Central-difference gradient ``(N, 3)`` of a signed-distance field at ``pts`` (voxels).

    The gradient of a signed distance field is the **outward** unit normal of the level set
    (points toward increasing distance = away from the enclosed interior).
    """
    pts = np.asarray(pts, dtype=np.float64)
    grad = np.zeros((pts.shape[0], 3), dtype=np.float64)
    for axis in range(3):
        e = np.zeros(3, dtype=np.float64)
        e[axis] = h
        fp = _sample_center(field, pts + e[None, :]).astype(np.float64)
        fm = _sample_center(field, pts - e[None, :]).astype(np.float64)
        grad[:, axis] = (fp - fm) / (2.0 * h)
    return grad


def _sample_center(field: DenseField, pts: NDArray) -> NDArray[np.float32]:
    """Nearest-voxel sample of a scalar field at ``pts`` -> ``(N,)`` fp32."""
    return np.asarray(field.sample_at(pts, reduce="center", radius=0), dtype=np.float32).reshape(-1)


@FEATURE_REGISTRY.register("membrane_distance")
class MembraneDistance(FeatureExtractor):
    """Signed distance from each candidate to the membrane, in Angstrom (SPEC §8).

    Samples the ``membrane_sdf`` field (a signed EDT in voxels, negative inside) and scales to
    Angstrom. Neutral ``NaN`` when the field is MISSING.
    """

    produces = ("membrane_dist_A",)
    needs_fields = (_MEMBRANE_SDF,)
    theta_dependent = False

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the signed membrane-distance column (Angstrom), neutral if MISSING."""
        if _MEMBRANE_SDF not in fields:
            return {"membrane_dist_A": neutral_column(cand.n)}
        d_vox = _sample_center(fields[_MEMBRANE_SDF], cand.coords_zyx)
        return {"membrane_dist_A": (d_vox * float(ctx.grid.apix)).astype(np.float32)}


@FEATURE_REGISTRY.register("inside_outside_sign")
class InsideOutsideSign(FeatureExtractor):
    """Which side of the membrane each candidate lies on (SPEC §8).

    Sign of the signed membrane SDF: ``-1`` inside (negative SDF), ``+1`` outside, ``0`` on
    the surface. Neutral ``NaN`` when the membrane field is MISSING. Wrong-side hits are a
    membrane-lattice false-positive signal.
    """

    produces = ("inside_sign",)
    needs_fields = (_MEMBRANE_SDF,)
    theta_dependent = False

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the inside/outside sign column, neutral if the field is MISSING."""
        if _MEMBRANE_SDF not in fields:
            return {"inside_sign": neutral_column(cand.n)}
        d_vox = _sample_center(fields[_MEMBRANE_SDF], cand.coords_zyx)
        return {"inside_sign": np.sign(d_vox).astype(np.float32)}


@FEATURE_REGISTRY.register("closed_shell_score")
class ClosedShellScore(FeatureExtractor):
    """Closed-shell (small vesicle) vs extended-membrane score (SPEC §8).

    The Laplacian of a signed distance field equals the sum of principal curvatures of the
    level set (``2/r`` for a sphere of radius ``r``): large for a small closed interior
    replication vesicle, ~0 for the extended low-curvature outer mito membrane. Estimated by
    central differences on ``membrane_sdf`` (step ``h`` voxels), reported in ``1/Angstrom``.
    Neutral ``NaN`` when the field is MISSING.

    Args:
        step: Central-difference step ``h`` in voxels.
    """

    produces = ("closed_shell",)
    needs_fields = (_MEMBRANE_SDF,)
    theta_dependent = False

    def __init__(self, step: int = 2, **params: object) -> None:
        self.params: Dict[str, object] = {"step": step, **params}
        self.step = max(1, int(step))

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the closed-shell curvature-magnitude column (1/Angstrom), neutral if MISSING."""
        if _MEMBRANE_SDF not in fields:
            return {"closed_shell": neutral_column(cand.n)}
        field = fields[_MEMBRANE_SDF]
        pts = np.asarray(cand.coords_zyx, dtype=np.float64)
        h = float(self.step)
        f0 = _sample_center(field, pts).astype(np.float64)
        lap = np.zeros(pts.shape[0], dtype=np.float64)
        for axis in range(3):
            e = np.zeros(3, dtype=np.float64)
            e[axis] = h
            fp = _sample_center(field, pts + e[None, :]).astype(np.float64)
            fm = _sample_center(field, pts - e[None, :]).astype(np.float64)
            lap += (fp - 2.0 * f0 + fm) / (h * h)
        closed = np.abs(lap) / max(float(ctx.grid.apix), _EPS)
        return {"closed_shell": closed.astype(np.float32)}


@FEATURE_REGISTRY.register("membrane_facing")
class MembraneFacing(FeatureExtractor):
    """Alignment of the template ``+Z`` outward normal with the local membrane outward normal.

    The template's ``+Z`` axis is the modelled *outward* mitochondrial-membrane normal (SPEC §4),
    carried per candidate as the ``normal`` attribute ``(z, y, x)``. The membrane's own local
    outward normal is the gradient of ``membrane_sdf`` (which increases away from the enclosed
    interior). Their cosine (``membrane_facing`` in ``[-1, 1]``) is:

    * near ``+1`` for a genuine target embedded in the outer membrane facing outward (correct side);
    * near ``0`` / negative for a wrong-side membrane-lattice ghost or a hit on an interior
      replication vesicle whose modelled outward normal disagrees with the local surface.

    On a real ``H99_2_100_1_bin5`` tomogram the median facing is ``0.89`` for hits on the extended
    outer membrane vs ``0.54`` for hits on small interior closed shells (see the derived-field
    validation), so it is the strongest per-hit outer-vs-interior discriminator. Neutral ``NaN``
    when the membrane field is MISSING or the candidate has no template normal.
    """

    produces = ("membrane_facing",)
    needs_fields = (_MEMBRANE_SDF,)
    theta_dependent = False

    def __init__(self, step: int = 2, **params: object) -> None:
        self.params: Dict[str, object] = {"step": step, **params}
        self.step = max(1, int(step))

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the template-vs-membrane facing cosine, neutral if MISSING/no normal."""
        if _MEMBRANE_SDF not in fields:
            return {"membrane_facing": neutral_column(cand.n)}
        tpl = resolve_point_normals(cand, fields, attr="normal", field_name="normal")
        if tpl is None:
            return {"membrane_facing": neutral_column(cand.n)}
        field = fields[_MEMBRANE_SDF]
        grad = _sdf_gradient(field, cand.coords_zyx, float(self.step))
        gn = np.linalg.norm(grad, axis=1)
        tn = np.linalg.norm(tpl, axis=1)
        denom = gn * tn
        cos = np.einsum("ij,ij->i", tpl, grad)
        with np.errstate(invalid="ignore", divide="ignore"):
            facing = np.where(denom > _EPS, cos / denom, np.nan)
        return {"membrane_facing": facing.astype(np.float32)}


__all__: List[str] = [
    "MembraneDistance",
    "InsideOutsideSign",
    "ClosedShellScore",
    "MembraneFacing",
]
