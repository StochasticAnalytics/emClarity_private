"""Spatial-isolation constraint (DESIGN §7 — a soft weak prior).

A true target is one member of a densely-tiled membrane surface; a hit that is spatially
isolated — few co-located neighbors and/or far off the local surface plane of its neighbors — is
a false-positive signal. This is a soft, weak prior: it never hard-rejects on its own, it just
nudges the fused score. Neutral when the isolation features are absent.
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

# Prefer the raw neighbor COUNT: it lives on an O(1..30) scale so a ``density_thresh`` of a few
# neighbors gives a sigmoid that SPANS [0, 1] (isolated <thresh -> ~1, in-sheet -> ~0). The
# ``neighbor_density`` fallback ("candidates per 1e6 A^3") is ~0.005 on the real data, so a
# threshold on it saturates the sigmoid at ~1 for every hit (the round_4_fitted bug: density_thresh
# 27.4 >> feature max 0.03). See ``NeighborDensity``.
_DENSITY_ALIASES = ("neighbor_count", "neighbor_density")
_OFF_ALIASES = ("off_surface_A",)


@register_constraint("isolation")
class IsolationConstraint(_BaseConstraint):
    """Penalize spatially-isolated / off-surface hits (DESIGN §6, §7).

    Two soft terms, soft-OR'd: a low-neighbor-density term (sigmoid below ``density_thresh``) and
    an off-surface term (sigmoid on the perpendicular offset above ``off_thresh_A``). Both are
    weak — a legitimately sparse but coherent region is only mildly penalized.

    Args:
        density_thresh: Minimum neighbor COUNT below which to penalize as isolated (the preferred
            ``neighbor_count`` feature; a few neighbors). Falls back to the ``neighbor_density``
            scale only when the count column is absent.
        density_sharpness: Steepness of the density sigmoid.
        off_thresh_A: Off-surface offset (Angstrom) above which to penalize.
        off_sharpness: Steepness of the off-surface sigmoid (per Angstrom).
        off_weight: Weight of the off-surface term (``0..1``).
    """

    name = "isolation"
    needs_features = ("neighbor_density", "off_surface_A")
    param_schema: Dict[str, ParamSpec] = {
        "density_thresh": ParamSpec(0.0, 50.0, 2.0),
        "density_sharpness": ParamSpec(1.0e-3, 10.0, 1.0, log=True),
        "off_thresh_A": ParamSpec(0.0, 400.0, 150.0),
        "off_sharpness": ParamSpec(1.0e-3, 0.5, 0.03, log=True),
        "off_weight": ParamSpec(0.0, 1.0, 1.0),
    }

    def __init__(
        self,
        density_thresh: float = 2.0,
        density_sharpness: float = 1.0,
        off_thresh_A: float = 150.0,
        off_sharpness: float = 0.03,
        off_weight: float = 1.0,
        **params: object,
    ) -> None:
        super().__init__(
            density_thresh=density_thresh,
            density_sharpness=density_sharpness,
            off_thresh_A=off_thresh_A,
            off_sharpness=off_sharpness,
            off_weight=off_weight,
            **params,
        )

    def forward(self, feats: FeatureMatrix, theta: ParamDict) -> NDArray[np.float32]:
        """Return the per-candidate isolation false-positive score in ``[0, 1]``.

        Args:
            feats: The per-candidate feature matrix.
            theta: The resolved tunable parameter values.

        Returns:
            A ``(N,)`` false-positive score (higher == more isolated); zeros when the isolation
            features are absent or NaN.
        """
        n = feats.n
        p = self.resolved(theta)
        terms: list[NDArray[np.float64]] = []

        dens: Optional[NDArray[np.float64]] = get_feature(feats, _DENSITY_ALIASES)
        if dens is not None:
            valid = finite_mask(dens)
            low = sigmoid(
                p["density_sharpness"] * (p["density_thresh"] - np.where(valid, dens, 0.0))
            )
            terms.append(np.where(valid, low, 0.0))

        off: Optional[NDArray[np.float64]] = get_feature(feats, _OFF_ALIASES)
        if off is not None:
            valid_o = finite_mask(off)
            o = np.where(valid_o, off, 0.0)
            off_term = sigmoid(p["off_sharpness"] * (o - p["off_thresh_A"]))
            terms.append(np.where(valid_o, off_term, 0.0) * p["off_weight"])

        return np.asarray(soft_or(terms, n), dtype=np.float32)
