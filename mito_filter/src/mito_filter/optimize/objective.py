"""Tuning objectives: a PRIMARY self-supervised physics objective + a SECONDARY weak-label term.

Because round_4 has **no per-hit spatial ground truth** (SPEC §10.4), the load-bearing signal is
self-supervised physics, not labels. The primary objective (:class:`SelfSupervisedObjective`)
exploits the dense physics the SPEC describes, using only the cached features:

* **Physics anchors (theta-independent).** From the raw cached feature columns we build two
  per-candidate, per-tomogram, scale-free confidences in ``[0, 1]``:
  ``fp_anchor`` — high on the false-positive physics (compact extreme-CC clusters = gold/ice via
  ``cc_cluster_density``/``blobness``; off-surface isolated hits via ``off_surface_A`` +
  incoherent normals via low ``normal_coherence``; large ``surface_residual``/``curvature``),
  and ``target_anchor`` — high on coherent low-curvature membrane-surface membership with
  consistent normals (high ``normal_coherence``, ``neighbor_density``). Anchors are **rank
  (percentile) normalised within each tomogram**, so no cross-convmap scale leaks and no label
  is used.
* **The objective (maximised).** ``J = align + w_sep * separation - w_cov * coverage`` where
  ``p = model.forward(feats)`` is the keep-probability:
  - ``align`` — a contrastive margin: confident target anchors want ``p -> 1``, confident FP
    anchors want ``p -> 0`` (a weighted log-likelihood over the confident anchor subset).
  - ``separation`` — the gap between the anchor-weighted mean ``p`` of targets and of FPs
    (rewards a bimodal, well-separated keep-probability = the two-component target/FP mixture).
  - ``coverage`` — a mild anti-degenerate barrier penalising ``p`` collapsing to all-keep or
    all-remove, so the trivial constant solution is not optimal.
  Everything is averaged **per tomogram then across tomograms** so theta is fit jointly over all
  convmaps (DESIGN §8) without a big tomogram dominating.

The secondary term (:class:`WeakLabelObjective`) is a confidence-weighted BCE against the SPEC
§10 weak labels (templateIDX==1 negative prior, any col26 ``-9999``). :class:`CompositeObjective`
fuses primary + secondary with a small secondary weight so labels only *regularise* the physics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from numpy.typing import NDArray

from ..constraints.base import ParamDict
from ..features.extractor import FeatureMatrix
from ..model.filter_model import FilterModel
from .dataset import SearchDataset
from .labels import UNKNOWN, WeakLabels

__all__ = [
    "ObjectiveValue",
    "Objective",
    "AnchorConfig",
    "SelfSupervisedObjective",
    "WeakLabelObjective",
    "CompositeObjective",
]

_EPS = 1e-6


@dataclass(frozen=True)
class ObjectiveValue:
    """A scalar objective value (to **maximise**) plus its named components.

    Args:
        total: The scalar score the optimiser maximises.
        components: Named sub-terms (for reporting / diagnostics).

    Attributes:
        total: The scalar score.
        components: The sub-terms.
    """

    total: float
    components: Mapping[str, float] = field(default_factory=dict)

    def __float__(self) -> float:
        return float(self.total)


class Objective(ABC):
    """An objective over a :class:`FilterModel` and a :class:`SearchDataset` (maximise)."""

    @abstractmethod
    def evaluate(
        self, model: FilterModel, dataset: SearchDataset, *, theta: Optional[ParamDict] = None
    ) -> ObjectiveValue:
        """Return the objective value for ``model`` (optionally under a proposed ``theta``).

        Args:
            model: The filter model.
            dataset: The whole-search dataset.
            theta: Optional proposed flat theta evaluated without mutating the model.

        Returns:
            The :class:`ObjectiveValue`.
        """
        raise NotImplementedError


def _keep_prob(
    model: FilterModel, feats: FeatureMatrix, theta: Optional[ParamDict]
) -> NDArray[np.float64]:
    """Return the model's ``(N,)`` keep-probability, honouring a proposed theta if given."""
    if feats.n == 0:
        return np.zeros(0, dtype=np.float64)
    if theta is None:
        p = model.forward(feats)
    else:
        p = model.forward_with_theta(feats, theta)
    return np.clip(np.asarray(p, dtype=np.float64).reshape(-1), _EPS, 1.0 - _EPS)


def _rank01(x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Percentile-rank ``x`` into ``[0, 1]`` (scale-free); NaN -> neutral 0.5, constant -> 0.5.

    Args:
        x: The values to rank.

    Returns:
        The ``(N,)`` percentile ranks in ``[0, 1]``.
    """
    v = np.asarray(x, dtype=np.float64).reshape(-1)
    n = v.shape[0]
    if n == 0:
        return v
    finite = np.isfinite(v)
    out = np.full(n, 0.5, dtype=np.float64)
    if np.count_nonzero(finite) <= 1:
        return out
    fv = v[finite]
    order = np.argsort(fv, kind="mergesort")
    ranks = np.empty(fv.shape[0], dtype=np.float64)
    ranks[order] = np.arange(fv.shape[0], dtype=np.float64)
    if fv.shape[0] > 1:
        ranks /= fv.shape[0] - 1
    out[finite] = ranks
    return out


@dataclass
class AnchorConfig:
    """Which cached feature columns drive the physics anchors, and their signs (DESIGN §8).

    Each entry is ``(alias_tuple, weight)``: the first present column among the aliases is
    percentile-ranked and contributes ``weight`` to the anchor. ``fp_high`` columns push the
    false-positive anchor up when large; ``target_high`` push the target anchor up when large.
    A column present in neither list, or absent, simply does not contribute.

    Args:
        fp_high: Aliases whose *high* values indicate a false positive (+ weight).
        target_high: Aliases whose *high* values indicate a true target (+ weight).
        target_from_low: Aliases whose *low* values indicate a true target (contribute
            ``1 - rank``, e.g. ``surface_residual``) — used to enrich the target anchor.

    Attributes:
        fp_high: FP-high alias/weight pairs.
        target_high: Target-high alias/weight pairs.
        target_from_low: Target-from-low alias/weight pairs.
    """

    fp_high: Sequence[Tuple[Tuple[str, ...], float]] = (
        (("cc_cluster_density", "cc_cluster_z", "cc_local_max"), 1.0),
        (("blobness",), 1.0),
        (("off_surface_A", "off_surface"), 1.0),
        (("surface_residual", "surface_residual_A"), 0.7),
        (("curvature", "curv_mean"), 0.7),
    )
    target_high: Sequence[Tuple[Tuple[str, ...], float]] = (
        (("normal_coherence",), 1.0),
        (("neighbor_density",), 0.5),
    )
    target_from_low: Sequence[Tuple[Tuple[str, ...], float]] = (
        (("off_surface_A", "off_surface"), 0.7),
        (("surface_residual", "surface_residual_A"), 0.5),
    )


def _first_present(feats: FeatureMatrix, aliases: Tuple[str, ...]) -> Optional[NDArray[np.float64]]:
    """Return the first present column among ``aliases`` (float64), else None."""
    for nm in aliases:
        if nm in feats:
            return np.asarray(feats.column(nm), dtype=np.float64).reshape(-1)
    return None


def _weighted_anchor(
    feats: FeatureMatrix,
    entries: Sequence[Tuple[Tuple[str, ...], float]],
    *,
    invert: bool = False,
) -> Tuple[NDArray[np.float64], float]:
    """Build a ``[0, 1]`` anchor as a weighted mean of percentile-ranked columns.

    Args:
        feats: The per-candidate feature matrix.
        entries: ``(aliases, weight)`` contributions.
        invert: If True, use ``1 - rank`` (low values -> high anchor).

    Returns:
        A tuple ``(anchor (N,), total_weight)``; ``anchor`` is neutral 0.5 when total weight is 0.
    """
    n = feats.n
    acc = np.zeros(n, dtype=np.float64)
    wsum = 0.0
    for aliases, w in entries:
        col = _first_present(feats, aliases)
        if col is None or w <= 0.0:
            continue
        r = _rank01(col)
        acc += w * ((1.0 - r) if invert else r)
        wsum += w
    if wsum <= 0.0:
        return np.full(n, 0.5, dtype=np.float64), 0.0
    return acc / wsum, wsum


class SelfSupervisedObjective(Objective):
    """The PRIMARY, label-free physics objective (DESIGN §8, graft from the ml proposal).

    Args:
        anchors: The :class:`AnchorConfig` selecting the physics feature columns.
        confidence_quantile: Only anchor scores above this within-tomo quantile act as
            contrastive targets (the "confident subset"); e.g. 0.6 keeps the top 40%.
        sep_weight: Weight on the target-vs-FP separation term.
        coverage_weight: Weight on the anti-degenerate coverage barrier.
        target_keep_rate: The keep-rate the coverage barrier is centred on (soft, wide band).
        coverage_band: Half-width of the coverage dead-band (no penalty inside it).

    Attributes:
        anchors: The anchor configuration.
        confidence_quantile: The confident-subset quantile.
        sep_weight: Separation weight.
        coverage_weight: Coverage weight.
        target_keep_rate: Coverage centre.
        coverage_band: Coverage dead-band half-width.
    """

    def __init__(
        self,
        anchors: Optional[AnchorConfig] = None,
        *,
        confidence_quantile: float = 0.6,
        sep_weight: float = 1.0,
        coverage_weight: float = 0.5,
        target_keep_rate: float = 0.5,
        coverage_band: float = 0.35,
    ) -> None:
        self.anchors = anchors if anchors is not None else AnchorConfig()
        self.confidence_quantile = float(confidence_quantile)
        self.sep_weight = float(sep_weight)
        self.coverage_weight = float(coverage_weight)
        self.target_keep_rate = float(target_keep_rate)
        self.coverage_band = float(coverage_band)

    def anchors_for(
        self, feats: FeatureMatrix
    ) -> Tuple[NDArray[np.float64], NDArray[np.float64], bool]:
        """Return ``(fp_anchor, target_anchor, informative)`` for one tomogram's features.

        Args:
            feats: The per-candidate feature matrix.

        Returns:
            The FP anchor and target anchor (each ``[0, 1]``), and whether *any* anchor
            feature was present (else the anchors are neutral and carry no signal).
        """
        fp, wfp = _weighted_anchor(feats, self.anchors.fp_high)
        tg_hi, w_hi = _weighted_anchor(feats, self.anchors.target_high)
        tg_lo, w_lo = _weighted_anchor(feats, self.anchors.target_from_low, invert=True)
        if w_hi + w_lo > 0.0:
            tg = (w_hi * tg_hi + w_lo * tg_lo) / (w_hi + w_lo)
        else:
            tg = tg_hi
        return fp, tg, (wfp + w_hi + w_lo) > 0.0

    def _confident_weights(self, anchor: NDArray[np.float64]) -> NDArray[np.float64]:
        """Soft weights selecting the top ``(1 - q)`` of an anchor (0 below the quantile).

        Args:
            anchor: A ``[0, 1]`` anchor confidence.

        Returns:
            Per-row weights: ``relu(anchor - q) / (1 - q)`` (0 outside the confident subset).
        """
        q = float(np.clip(self.confidence_quantile, 0.0, 0.999))
        return np.clip((anchor - q) / max(1.0 - q, _EPS), 0.0, 1.0)

    def _per_tomo(
        self, p: NDArray[np.float64], feats: FeatureMatrix
    ) -> Tuple[float, float, float, bool]:
        """Return ``(align, separation, coverage, informative)`` for one tomogram."""
        fp, tg, informative = self.anchors_for(feats)
        w_fp = self._confident_weights(fp)
        w_tg = self._confident_weights(tg)
        logp = np.log(p)
        log1p = np.log(1.0 - p)
        denom = float(w_tg.sum() + w_fp.sum())
        if denom <= _EPS:
            align = 0.0
        else:
            align = float((w_tg * logp + w_fp * log1p).sum() / denom)
        if w_tg.sum() > _EPS and w_fp.sum() > _EPS:
            mean_tg = float((w_tg * p).sum() / w_tg.sum())
            mean_fp = float((w_fp * p).sum() / w_fp.sum())
            separation = mean_tg - mean_fp
        else:
            separation = 0.0
        keep_rate = float(p.mean()) if p.size else self.target_keep_rate
        dev = abs(keep_rate - self.target_keep_rate)
        coverage = max(0.0, dev - self.coverage_band) ** 2
        return align, separation, coverage, informative

    def evaluate(
        self, model: FilterModel, dataset: SearchDataset, *, theta: Optional[ParamDict] = None
    ) -> ObjectiveValue:
        """Evaluate the self-supervised objective, averaged per tomogram (DESIGN §8).

        Args:
            model: The filter model.
            dataset: The whole-search dataset.
            theta: Optional proposed flat theta.

        Returns:
            The :class:`ObjectiveValue` (``total`` to maximise) with ``align`` / ``separation``
            / ``coverage`` / ``keep_rate`` components.
        """
        aligns: List[float] = []
        seps: List[float] = []
        covs: List[float] = []
        weights: List[float] = []
        keep_rates: List[float] = []
        for _base, feats in dataset.per_tomo():
            if feats.n == 0:
                continue
            p = _keep_prob(model, feats, theta)
            align, sep, cov, informative = self._per_tomo(p, feats)
            w = float(feats.n)
            aligns.append(align)
            seps.append(sep)
            covs.append(cov)
            keep_rates.append(float(p.mean()))
            weights.append(w if informative else 0.0)
        if not weights or sum(weights) <= 0.0:
            # No informative tomogram: fall back to unweighted so coverage still applies.
            weights = [float(f.n) for _b, f in dataset.per_tomo() if f.n]
        wsum = sum(weights) or 1.0
        wa = float(np.dot(aligns, weights) / wsum) if aligns else 0.0
        ws = float(np.dot(seps, weights) / wsum) if seps else 0.0
        wc = float(np.dot(covs, weights) / wsum) if covs else 0.0
        wk = float(np.dot(keep_rates, weights) / wsum) if keep_rates else 0.0
        total = wa + self.sep_weight * ws - self.coverage_weight * wc
        return ObjectiveValue(
            total,
            {
                "align": wa,
                "separation": ws,
                "coverage": wc,
                "keep_rate": wk,
                "n_tomos": float(len([w for w in weights if w > 0])),
            },
        )


class WeakLabelObjective(Objective):
    """The SECONDARY, regularising weak-label term: confidence-weighted BCE (SPEC §10).

    Args:
        labels: Per-row :class:`WeakLabels` aligned to the dataset's combined matrix.

    Attributes:
        labels: The weak labels.
    """

    def __init__(self, labels: WeakLabels) -> None:
        self.labels = labels

    def evaluate(
        self, model: FilterModel, dataset: SearchDataset, *, theta: Optional[ParamDict] = None
    ) -> ObjectiveValue:
        """Return ``-BCE`` (to maximise) over the labelled rows only.

        Args:
            model: The filter model.
            dataset: The whole-search dataset.
            theta: Optional proposed flat theta.

        Returns:
            The :class:`ObjectiveValue`; ``total = -weighted_BCE`` with ``bce`` / ``n_labeled``
            components. Zero (neutral) when no row is labelled.
        """
        if self.labels.n != dataset.n:
            raise ValueError(f"weak labels length {self.labels.n} != dataset rows {dataset.n}")
        p = _keep_prob(model, dataset.matrix, theta)
        y = self.labels.label.astype(np.float64)
        w = self.labels.weight.astype(np.float64)
        mask = self.labels.label != UNKNOWN
        wm = w * mask
        denom = float(wm.sum())
        if denom <= _EPS:
            return ObjectiveValue(0.0, {"bce": 0.0, "n_labeled": 0.0})
        bce = -(wm * (y * np.log(p) + (1.0 - y) * np.log(1.0 - p))).sum() / denom
        return ObjectiveValue(
            -float(bce), {"bce": float(bce), "n_labeled": float(np.count_nonzero(mask))}
        )


class CompositeObjective(Objective):
    """Weighted sum of objectives — primary self-supervised + secondary weak-label (DESIGN §8).

    Args:
        terms: ``(objective, weight)`` pairs; the total is ``Σ weight * term.total``.

    Attributes:
        terms: The weighted objective terms.
    """

    def __init__(self, terms: Sequence[Tuple[Objective, float]]) -> None:
        self.terms: List[Tuple[Objective, float]] = list(terms)

    @classmethod
    def physics_plus_weak(
        cls,
        self_sup: SelfSupervisedObjective,
        weak: Optional[WeakLabelObjective],
        *,
        weak_weight: float = 0.25,
    ) -> "CompositeObjective":
        """Build the standard primary(1.0) + secondary(``weak_weight``) composite.

        Args:
            self_sup: The primary self-supervised objective.
            weak: The secondary weak-label objective, or None to omit it.
            weak_weight: Weight on the weak-label term (small: it only regularises).

        Returns:
            The :class:`CompositeObjective`.
        """
        terms: List[Tuple[Objective, float]] = [(self_sup, 1.0)]
        if weak is not None:
            terms.append((weak, float(weak_weight)))
        return cls(terms)

    def evaluate(
        self, model: FilterModel, dataset: SearchDataset, *, theta: Optional[ParamDict] = None
    ) -> ObjectiveValue:
        """Evaluate every term and return their weighted sum.

        Args:
            model: The filter model.
            dataset: The whole-search dataset.
            theta: Optional proposed flat theta.

        Returns:
            The composite :class:`ObjectiveValue` (component keys prefixed ``t{i}.``).
        """
        total = 0.0
        components: Dict[str, float] = {}
        for i, (obj, weight) in enumerate(self.terms):
            val = obj.evaluate(model, dataset, theta=theta)
            total += weight * val.total
            components[f"t{i}.total"] = float(val.total)
            components[f"t{i}.weight"] = float(weight)
            for k, v in val.components.items():
                components[f"t{i}.{k}"] = float(v)
        return ObjectiveValue(total, components)
