"""Cheap prior features: raw/SNR score, templateIDX prior, physical position (DESIGN §6).

These are the light, per-candidate priors read straight from the :class:`CandidateSet`
attributes (or a calibrated field): the raw convmap score, a per-tomo z-scored / SNR score,
the ``templateIDX == 1`` weak-negative prior (SPEC §10 — ``ref_old`` hits are FP-enriched),
and the physical position. All are theta-independent (cached once).
"""

from __future__ import annotations

from typing import Dict, Mapping

import numpy as np

from ..candidates.source import CandidateSet
from ..core.field import DenseField
from ..emclarity.constants import BACKGROUND_MEAN, BACKGROUND_STD
from .engine import FEATURE_REGISTRY, neutral_column, resolve_scalar
from .extractor import ArrayT, BlockCtx, FeatureExtractor


@FEATURE_REGISTRY.register("raw_score")
class RawScore(FeatureExtractor):
    """The raw convmap CC score at each candidate (SPEC §2 col 1).

    Reads the ``cc`` candidate attribute if present, else samples the ``cc`` field with a
    ``+/-1`` max reduce (SPEC §3 sub-voxel CoM recovery).
    """

    produces = ("raw_score",)
    needs_fields = ("cc",)
    theta_dependent = False

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the raw CC score column (SPEC §3 recovery via a +/-1 max reduce)."""
        cc = resolve_scalar(cand, fields, "cc", attr="cc", reduce="max", radius=1)
        if cc is None:
            cc = neutral_column(cand.n)
        return {"raw_score": cc}


@FEATURE_REGISTRY.register("snr_score")
class SnrScore(FeatureExtractor):
    """A calibrated per-tomo score (SPEC §9.2, §11).

    Uses a materialized ``snr`` field (``cc / sqrt(noise_variance)``) when present; otherwise
    z-scores the raw ``cc`` against the per-tomo background ``N(mu, sigma)`` taken from
    ``ctx.meta['bg_mean'|'bg_std']`` (falling back to the SPEC constants), so a shared
    absolute threshold transfers across tomograms.
    """

    produces = ("snr",)
    needs_fields = ("snr",)
    theta_dependent = False

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the SNR / z-scored score column."""
        snr = resolve_scalar(cand, fields, "snr", attr="snr", reduce="max", radius=1)
        if snr is not None:
            return {"snr": snr}
        cc = resolve_scalar(cand, fields, "cc", attr="cc", reduce="max", radius=1)
        if cc is None:
            return {"snr": neutral_column(cand.n)}
        mu = float(ctx.meta.get("bg_mean", BACKGROUND_MEAN))  # type: ignore[arg-type]
        sigma = float(ctx.meta.get("bg_std", BACKGROUND_STD))  # type: ignore[arg-type]
        sigma = sigma if sigma > 1e-6 else 1.0
        return {"snr": ((cc - mu) / sigma).astype(np.float32)}


@FEATURE_REGISTRY.register("template_idx_prior")
class TemplateIdxPrior(FeatureExtractor):
    """The winning-template prior (SPEC §10): ``templateIDX == 1`` is a weak FP negative.

    ``ref_old`` (id 1) is enriched in false positives (survives culls worst), so ``is_ref1``
    is a usable weak-negative straight from ``.templateIDX``. Emits the raw id too.
    """

    produces = ("template_idx", "is_ref1")
    needs_fields = ()
    theta_dependent = False

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the template id and the ``is_ref1`` weak-negative indicator."""
        if "template_idx" in cand.attrs:
            tid = np.asarray(cand.get("template_idx"), dtype=np.float32).reshape(-1)
            is_ref1 = (tid == 1.0).astype(np.float32)
        else:
            tid = neutral_column(cand.n)
            is_ref1 = neutral_column(cand.n)
        return {"template_idx": tid, "is_ref1": is_ref1}


@FEATURE_REGISTRY.register("physical_position")
class PhysicalPosition(FeatureExtractor):
    """The candidate's physical position in Angstrom + fractional tomo depth (SPEC §3).

    Position = voxel ``* APIX`` (via ``ctx.grid.world``); ``depth_frac`` is ``z / nz`` (0 at
    one surface, 1 at the other) — a cheap geometric prior for edge / carbon-film artifacts.
    """

    produces = ("pos_z_A", "pos_y_A", "pos_x_A", "depth_frac")
    needs_fields = ()
    theta_dependent = False

    def extract(
        self, cand: CandidateSet, fields: Mapping[str, DenseField], ctx: BlockCtx
    ) -> Dict[str, ArrayT]:
        """Return the three world-coordinate columns and the fractional z depth."""
        world = np.asarray(ctx.grid.world(cand.coords_zyx), dtype=np.float32).reshape(-1, 3)
        nz = max(int(ctx.grid.nz) - 1, 1)
        depth = (np.asarray(cand.coords_zyx, dtype=np.float32)[:, 0] / nz).astype(np.float32)
        return {
            "pos_z_A": world[:, 0],
            "pos_y_A": world[:, 1],
            "pos_x_A": world[:, 2],
            "depth_frac": depth,
        }
