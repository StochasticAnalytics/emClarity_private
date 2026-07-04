"""TemplateIDX prior constraint (DESIGN §7; SPEC §10 — a soft weak prior).

``ref_old`` (template id 1) is enriched in false positives: it is 57-62 % of round_4 hits but
survives the classification culls worst (SPEC §10). So ``templateIDX == 1`` is a usable
weak-negative prior straight from the ``.templateIDX`` file — no ``.mat`` needed. This constraint
adds a small, tunable false-positive score to ``is_ref1`` hits and is neutral otherwise.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
from numpy.typing import NDArray

from ..features.extractor import FeatureMatrix
from .base import ParamDict, ParamSpec
from .combine import _BaseConstraint, finite_mask, get_feature, register_constraint

_REF1_ALIASES = ("is_ref1",)
_TID_ALIASES = ("template_idx",)


@register_constraint("template_idx_prior")
class TemplateIdxPriorConstraint(_BaseConstraint):
    """Weak-negative prior for ``templateIDX == 1`` (``ref_old``) hits (SPEC §10).

    Reads the ``is_ref1`` indicator when present, else derives it from ``template_idx == 1``.
    Emits ``ref1_penalty`` for a ``ref_old`` hit and ``0`` otherwise (and for candidates with no
    template id).

    Args:
        ref1_penalty: The false-positive score applied to a ``templateIDX == 1`` hit (``0..1``).
    """

    name = "template_idx_prior"
    needs_features = ("is_ref1",)
    param_schema: Dict[str, ParamSpec] = {
        "ref1_penalty": ParamSpec(0.0, 1.0, 0.3),
    }

    def __init__(self, ref1_penalty: float = 0.3, **params: object) -> None:
        super().__init__(ref1_penalty=ref1_penalty, **params)

    def forward(self, feats: FeatureMatrix, theta: ParamDict) -> NDArray[np.float32]:
        """Return the per-candidate ``ref_old`` weak-negative score in ``[0, 1]``.

        Args:
            feats: The per-candidate feature matrix.
            theta: The resolved tunable parameter values.

        Returns:
            A ``(N,)`` false-positive score (``ref1_penalty`` for ``ref_old`` hits, else ``0``);
            all zeros when no template information is available.
        """
        n = feats.n
        p = self.resolved(theta)

        is_ref1: Optional[NDArray[np.float64]] = get_feature(feats, _REF1_ALIASES)
        if is_ref1 is None:
            tid = get_feature(feats, _TID_ALIASES)
            if tid is None:
                return np.zeros(n, dtype=np.float32)
            is_ref1 = (np.where(finite_mask(tid), tid, 0.0) == 1.0).astype(np.float64)

        valid = finite_mask(is_ref1)
        indicator = np.where(valid, is_ref1, 0.0)
        return np.asarray(p["ref1_penalty"] * np.clip(indicator, 0.0, 1.0), dtype=np.float32)
