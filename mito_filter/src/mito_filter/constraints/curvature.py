"""Surface-coherence constraint (DESIGN §7, §9.3; SPEC §4).

A true target sits in a smooth, curved, normal-coherent membrane with the template ``+Z`` as the
outward normal; a false positive sits in an incoherent-normal neighborhood. This constraint
penalizes a candidate whose neighborhood is:

* **incoherent** — low ``normal_coherence`` (the argmax-of-noise regime, DESIGN §9.3);
* **not a smooth surface** — high quadric ``surface_residual``;
* (weakly) **implausibly curved** — extreme principal ``curvature``.

It consumes normals from **either** the sparse csv (a candidate attr) **or** the dense normal
field (CC-gated) through the shared ``features/curvature`` extractors, so the same constraint
serves Phase A (sparse) and Phase B (dense). Gated-out / untrusted candidates carry ``NaN``
features and are neutral here.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
from numpy.typing import NDArray

from ..features.extractor import FeatureMatrix
from .base import ParamDict, ParamSpec
from .combine import (
    _BaseConstraint,
    finite_mask,
    get_feature,
    register_constraint,
    sigmoid,
    soft_or,
)

_COH_ALIASES = ("normal_coherence",)
_RES_ALIASES = ("surface_residual", "surface_residual_A")
_CURV_ALIASES = ("curvature", "curv_mean", "curv_k1")


@register_constraint("surface_coherence")
class SurfaceCoherenceConstraint(_BaseConstraint):
    """Penalize incoherent-normal, poorly-fitting, or implausibly-curved neighborhoods (SPEC §4).

    Three soft terms, soft-OR'd: incoherence (below ``coh_thresh``), surface-fit residual (above
    ``residual_thresh_A``), and principal-curvature magnitude (above ``curv_thresh``). The
    coherence term is the primary discriminator; the residual and curvature terms are weighted
    refinements. Works identically on sparse csv normals or the dense CC-gated normal field.

    Args:
        coh_thresh: Normal-coherence below which the neighborhood is penalized (``0..1``).
        coh_sharpness: Steepness of the coherence sigmoid.
        residual_thresh_A: Surface-fit residual (Angstrom) above which to penalize.
        residual_sharpness: Steepness of the residual sigmoid (per Angstrom).
        residual_weight: Weight of the residual term (``0..1``).
        curv_thresh: Principal-curvature magnitude (``1/Angstrom``) above which to penalize.
        curv_sharpness: Steepness of the curvature sigmoid (per ``1/Angstrom``).
        curv_weight: Weight of the curvature term (``0..1``).
    """

    name = "surface_coherence"
    needs_features = ("normal_coherence", "surface_residual", "curvature")
    param_schema: Dict[str, ParamSpec] = {
        "coh_thresh": ParamSpec(0.0, 1.0, 0.5),
        "coh_sharpness": ParamSpec(1.0, 40.0, 8.0),
        "residual_thresh_A": ParamSpec(0.0, 400.0, 120.0),
        "residual_sharpness": ParamSpec(1.0e-3, 0.5, 0.03, log=True),
        "residual_weight": ParamSpec(0.0, 1.0, 1.0),
        "curv_thresh": ParamSpec(0.0, 0.05, 0.02),
        "curv_sharpness": ParamSpec(1.0, 2000.0, 200.0, log=True),
        "curv_weight": ParamSpec(0.0, 1.0, 0.3),
    }

    def __init__(
        self,
        coh_thresh: float = 0.5,
        coh_sharpness: float = 8.0,
        residual_thresh_A: float = 120.0,
        residual_sharpness: float = 0.03,
        residual_weight: float = 1.0,
        curv_thresh: float = 0.02,
        curv_sharpness: float = 200.0,
        curv_weight: float = 0.3,
        **params: object,
    ) -> None:
        super().__init__(
            coh_thresh=coh_thresh,
            coh_sharpness=coh_sharpness,
            residual_thresh_A=residual_thresh_A,
            residual_sharpness=residual_sharpness,
            residual_weight=residual_weight,
            curv_thresh=curv_thresh,
            curv_sharpness=curv_sharpness,
            curv_weight=curv_weight,
            **params,
        )

    def forward(self, feats: FeatureMatrix, theta: ParamDict) -> NDArray[np.float32]:
        """Return the per-candidate surface-coherence false-positive score in ``[0, 1]``.

        Args:
            feats: The per-candidate feature matrix.
            theta: The resolved tunable parameter values.

        Returns:
            A ``(N,)`` false-positive score (higher == less surface-coherent); zeros for
            candidates whose features are absent or NaN.
        """
        n = feats.n
        p = self.resolved(theta)
        terms: list[NDArray[np.float64]] = []

        coh: Optional[NDArray[np.float64]] = get_feature(feats, _COH_ALIASES)
        if coh is not None:
            valid = finite_mask(coh)
            incoh = sigmoid(p["coh_sharpness"] * (p["coh_thresh"] - np.where(valid, coh, 0.0)))
            terms.append(np.where(valid, incoh, 0.0))

        res: Optional[NDArray[np.float64]] = get_feature(feats, _RES_ALIASES)
        if res is not None:
            valid_r = finite_mask(res)
            r = np.where(valid_r, res, 0.0)
            res_term = sigmoid(p["residual_sharpness"] * (r - p["residual_thresh_A"]))
            terms.append(np.where(valid_r, res_term, 0.0) * p["residual_weight"])

        curv: Optional[NDArray[np.float64]] = get_feature(feats, _CURV_ALIASES)
        if curv is not None:
            valid_c = finite_mask(curv)
            c = np.abs(np.where(valid_c, curv, 0.0))
            curv_term = sigmoid(p["curv_sharpness"] * (c - p["curv_thresh"]))
            terms.append(np.where(valid_c, curv_term, 0.0) * p["curv_weight"])

        return np.asarray(soft_or(terms, n), dtype=np.float32)
