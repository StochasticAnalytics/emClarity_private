"""Gold / ice cluster constraint (DESIGN §7; SPEC §1, §6, §9.4).

Gold fiducials and vitreous-ice artifacts appear as **compact clusters of extreme CC** (~8-13,
SPEC §1) and often sit near the already-known tilt-series gold beads (SPEC §9.4). This
constraint softly penalizes a candidate that (a) sits inside such an over-large, compact
(blob-like) high-CC cluster and/or (b) lies close to a known gold fiducial.

**Clusters are expected but NOT required** (DESIGN §7): a hit needs no cluster to survive, so
the two signals are combined by a probabilistic soft-OR — either one raises the false-positive
score, and neither is mandatory. When none of the features is available the constraint is
neutral (all-zero contribution).
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
from numpy.typing import NDArray

from ..features.extractor import FeatureMatrix
from .base import ParamDict, ParamSpec
from .combine import _BaseConstraint, finite_mask, get_feature, register_constraint, sigmoid

# Alias tuples bridge the DESIGN needs_features names and the engine's concrete produces names.
_DENSITY_ALIASES = ("cc_cluster_density", "cc_cluster_z", "cc_local_max", "cc_local_mean")
_BLOB_ALIASES = ("blobness",)
_GOLD_ALIASES = ("gold_dist", "gold_dist_A")


@register_constraint("gold_ice_cluster")
class GoldIceClusterConstraint(_BaseConstraint):
    """Penalize compact extreme-CC clusters (gold/ice) and near-fiducial hits (SPEC §1, §6).

    The cluster term is a sigmoid on the local CC-density elevation, optionally sharpened by
    the Hessian ``blobness`` (isotropy) so a compact gold/ice blob scores higher than a membrane
    sheet at the same density. The gold term is a sigmoid on proximity to the nearest known gold
    fiducial. The two are soft-OR'd (either suffices; neither is required).

    Args:
        cc_thresh: CC-density elevation above which a cluster starts to penalize.
        cc_sharpness: Steepness of the density sigmoid.
        blob_mix: How much the isotropy (``blobness``) modulates the cluster term (``0`` = ignore
            blobness, ``1`` = fully gate on it).
        gold_radius_A: Distance (Angstrom) under which a candidate counts as near a fiducial.
        gold_sharpness: Steepness of the gold-proximity sigmoid (per Angstrom).
    """

    name = "gold_ice_cluster"
    needs_features = ("cc_cluster_density", "blobness", "gold_dist")
    param_schema: Dict[str, ParamSpec] = {
        "cc_thresh": ParamSpec(3.0, 14.0, 8.0),
        "cc_sharpness": ParamSpec(0.05, 8.0, 1.0, log=True),
        "blob_mix": ParamSpec(0.0, 1.0, 0.5),
        "gold_radius_A": ParamSpec(0.0, 600.0, 250.0),
        "gold_sharpness": ParamSpec(1.0e-3, 0.2, 0.02, log=True),
    }

    def __init__(
        self,
        cc_thresh: float = 8.0,
        cc_sharpness: float = 1.0,
        blob_mix: float = 0.5,
        gold_radius_A: float = 250.0,
        gold_sharpness: float = 0.02,
        **params: object,
    ) -> None:
        super().__init__(
            cc_thresh=cc_thresh,
            cc_sharpness=cc_sharpness,
            blob_mix=blob_mix,
            gold_radius_A=gold_radius_A,
            gold_sharpness=gold_sharpness,
            **params,
        )

    def forward(self, feats: FeatureMatrix, theta: ParamDict) -> NDArray[np.float32]:
        """Return the per-candidate gold/ice false-positive score in ``[0, 1]``.

        Args:
            feats: The per-candidate feature matrix.
            theta: The resolved tunable parameter values.

        Returns:
            A ``(N,)`` false-positive score (higher == more gold/ice-like); all zeros when the
            required features are absent.
        """
        n = feats.n
        p = self.resolved(theta)
        out: NDArray[np.float64] = np.zeros(n, dtype=np.float64)

        density: Optional[NDArray[np.float64]] = get_feature(feats, _DENSITY_ALIASES)
        if density is not None:
            valid = finite_mask(density)
            base = sigmoid(p["cc_sharpness"] * (np.where(valid, density, 0.0) - p["cc_thresh"]))
            blob = get_feature(feats, _BLOB_ALIASES)
            if blob is not None:
                b = np.clip(np.where(finite_mask(blob), blob, 0.0), 0.0, 1.0)
                factor = (1.0 - p["blob_mix"]) + p["blob_mix"] * b
            else:
                factor = np.ones(n, dtype=np.float64)
            cluster_term = np.where(valid, base * factor, 0.0)
            out = 1.0 - (1.0 - out) * (1.0 - np.clip(cluster_term, 0.0, 1.0))

        gold: Optional[NDArray[np.float64]] = get_feature(feats, _GOLD_ALIASES)
        if gold is not None:
            # NaN -> +inf (treated as "far", no penalty); genuine +inf already means far.
            g = np.where(np.isnan(gold), np.inf, gold)
            gold_term = sigmoid(p["gold_sharpness"] * (p["gold_radius_A"] - g))
            out = 1.0 - (1.0 - out) * (1.0 - np.clip(gold_term, 0.0, 1.0))

        return np.asarray(out, dtype=np.float32)
