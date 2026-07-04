"""Tuning report: separation / PR vs weak labels, chosen theta, keep-rate (DESIGN §8).

After the tuner fits theta, :func:`build_report` summarises the fitted model on the whole-search
dataset: the keep-probability distribution, the anchor/weak-label **separation** (mean keep-prob
of likely-targets vs likely-FPs), precision-recall / ROC-AUC against the weak labels when both
classes are present (SPEC §10 — templateIDX==1 negatives), the objective components, the chosen
``tau`` and the resulting keep rate, and the fitted theta. It is a plain dataclass with
``to_dict`` / ``render_text`` so it drops into a :class:`FittedConfig.meta` block or a log line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

import numpy as np
from numpy.typing import NDArray

from ..model.filter_model import FilterModel
from .dataset import SearchDataset
from .labels import UNKNOWN, WeakLabels
from .objective import SelfSupervisedObjective

__all__ = ["SeparationReport", "build_report"]

_EPS = 1e-9


def _safe_auc(scores: NDArray[np.float64], y: NDArray[np.int64]) -> Optional[float]:
    """ROC-AUC of ``scores`` vs binary ``y`` via the rank (Mann-Whitney) identity, or None."""
    pos = scores[y == 1]
    neg = scores[y == 0]
    if pos.size == 0 or neg.size == 0:
        return None
    order = np.argsort(np.concatenate([neg, pos]), kind="mergesort")
    ranks = np.empty(order.shape[0], dtype=np.float64)
    ranks[order] = np.arange(1, order.shape[0] + 1, dtype=np.float64)
    r_pos = ranks[neg.size :]
    auc = (r_pos.sum() - pos.size * (pos.size + 1) / 2.0) / (pos.size * neg.size)
    return float(auc)


def _average_precision(scores: NDArray[np.float64], y: NDArray[np.int64]) -> Optional[float]:
    """Average precision (area under PR) of ``scores`` vs binary ``y``, or None if degenerate."""
    if np.count_nonzero(y == 1) == 0 or np.count_nonzero(y == 0) == 0:
        return None
    order = np.argsort(-scores, kind="mergesort")
    ys = y[order]
    tp = np.cumsum(ys == 1).astype(np.float64)
    fp = np.cumsum(ys == 0).astype(np.float64)
    precision = tp / np.maximum(tp + fp, _EPS)
    total_pos = float(np.count_nonzero(y == 1))
    recall = tp / total_pos
    rec_prev = np.concatenate([[0.0], recall[:-1]])
    return float(np.sum((recall - rec_prev) * precision))


@dataclass
class SeparationReport:
    """A summary of the fitted filter on a whole-search dataset (DESIGN §8).

    Args:
        n: Total candidate rows.
        n_tomos: Number of tomograms.
        tau: The chosen decision threshold.
        keep_rate: Fraction kept at ``tau``.
        mean_keep_prob: Mean keep-probability over all rows.
        physics_separation: Mean keep-prob of target-anchor rows minus FP-anchor rows.
        weak_pos_mean_p: Mean keep-prob over weak-positive rows (None if none).
        weak_neg_mean_p: Mean keep-prob over weak-negative rows (None if none).
        weak_separation: ``weak_pos_mean_p - weak_neg_mean_p`` (None if a class is absent).
        weak_auc: ROC-AUC of keep-prob vs weak labels (None if a class is absent).
        weak_ap: Average precision vs weak labels (None if a class is absent).
        n_weak_pos: Weak-positive row count.
        n_weak_neg: Weak-negative row count.
        objective: The objective components at the fitted theta.
        theta: The fitted flat theta.

    Attributes:
        (see Args)
    """

    n: int
    n_tomos: int
    tau: float
    keep_rate: float
    mean_keep_prob: float
    physics_separation: float
    weak_pos_mean_p: Optional[float] = None
    weak_neg_mean_p: Optional[float] = None
    weak_separation: Optional[float] = None
    weak_auc: Optional[float] = None
    weak_ap: Optional[float] = None
    n_weak_pos: int = 0
    n_weak_neg: int = 0
    objective: Mapping[str, float] = field(default_factory=dict)
    theta: Mapping[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        """Return a plain-dict (yaml/json-ready) representation."""
        return {
            "n": self.n,
            "n_tomos": self.n_tomos,
            "tau": self.tau,
            "keep_rate": self.keep_rate,
            "mean_keep_prob": self.mean_keep_prob,
            "physics_separation": self.physics_separation,
            "weak_pos_mean_p": self.weak_pos_mean_p,
            "weak_neg_mean_p": self.weak_neg_mean_p,
            "weak_separation": self.weak_separation,
            "weak_auc": self.weak_auc,
            "weak_ap": self.weak_ap,
            "n_weak_pos": self.n_weak_pos,
            "n_weak_neg": self.n_weak_neg,
            "objective": dict(self.objective),
            "theta": dict(self.theta),
        }

    def render_text(self) -> str:
        """Return a concise multi-line human summary."""
        lines: List[str] = [
            f"SearchDataset: {self.n} hits over {self.n_tomos} tomos",
            f"tau={self.tau:.3f}  keep_rate={self.keep_rate:.3f}  "
            f"mean_keep_prob={self.mean_keep_prob:.3f}",
            f"physics separation (target-FP anchors): {self.physics_separation:+.3f}",
        ]
        if self.weak_separation is not None:
            lines.append(
                f"weak labels: pos={self.n_weak_pos} neg={self.n_weak_neg}  "
                f"mean_p pos={self.weak_pos_mean_p:.3f} neg={self.weak_neg_mean_p:.3f}  "
                f"sep={self.weak_separation:+.3f}"
            )
            auc = "n/a" if self.weak_auc is None else f"{self.weak_auc:.3f}"
            ap = "n/a" if self.weak_ap is None else f"{self.weak_ap:.3f}"
            lines.append(f"weak AUC={auc}  AP={ap}")
        else:
            lines.append("weak labels: not both classes present (self-supervised only)")
        if self.objective:
            comps = "  ".join(f"{k}={v:.4g}" for k, v in self.objective.items())
            lines.append(f"objective: {comps}")
        return "\n".join(lines)


def build_report(
    model: FilterModel,
    dataset: SearchDataset,
    *,
    tau: float = 0.5,
    weak_labels: Optional[WeakLabels] = None,
    objective_components: Optional[Mapping[str, float]] = None,
    theta: Optional[Mapping[str, float]] = None,
    self_sup: Optional[SelfSupervisedObjective] = None,
) -> SeparationReport:
    """Summarise the fitted model on ``dataset`` (separation / PR vs weak labels, chosen theta).

    Args:
        model: The fitted filter model.
        dataset: The whole-search dataset.
        tau: The decision threshold used for the keep-rate.
        weak_labels: Optional row-aligned weak labels for PR / AUC / separation (SPEC §10).
        objective_components: Optional objective sub-terms to record.
        theta: Optional fitted theta to record (defaults to ``model.theta``).
        self_sup: Objective used to derive the label-free physics separation (defaults to a
            fresh :class:`SelfSupervisedObjective`).

    Returns:
        The :class:`SeparationReport`.
    """
    p = np.clip(np.asarray(model.forward(dataset.matrix), dtype=np.float64).reshape(-1), 0.0, 1.0)
    keep_rate = float((p >= tau).mean()) if p.size else 0.0
    mean_p = float(p.mean()) if p.size else 0.0

    # Label-free physics separation from the anchors, averaged per tomogram.
    ss = self_sup if self_sup is not None else SelfSupervisedObjective()
    seps: List[float] = []
    ws: List[float] = []
    for _base, feats in dataset.per_tomo():
        if feats.n == 0:
            continue
        pp = np.clip(np.asarray(model.forward(feats), dtype=np.float64).reshape(-1), 0.0, 1.0)
        _a, sep, _c, _inf = ss._per_tomo(pp, feats)
        seps.append(sep)
        ws.append(float(feats.n))
    physics_sep = float(np.dot(seps, ws) / (sum(ws) or 1.0)) if seps else 0.0

    report = SeparationReport(
        n=dataset.n,
        n_tomos=dataset.n_tomos,
        tau=float(tau),
        keep_rate=keep_rate,
        mean_keep_prob=mean_p,
        physics_separation=physics_sep,
        objective=dict(objective_components or {}),
        theta=dict(theta if theta is not None else model.theta),
    )

    if weak_labels is not None and weak_labels.n == dataset.n:
        y = weak_labels.label.astype(np.int64)
        pos = p[y == 1]
        neg = p[y == 0]
        report.n_weak_pos = int(pos.size)
        report.n_weak_neg = int(neg.size)
        report.weak_pos_mean_p = float(pos.mean()) if pos.size else None
        report.weak_neg_mean_p = float(neg.mean()) if neg.size else None
        if pos.size and neg.size:
            report.weak_separation = float(pos.mean()) - float(neg.mean())
        labeled = y != UNKNOWN
        if np.any(labeled):
            report.weak_auc = _safe_auc(p[labeled], y[labeled])
            report.weak_ap = _average_precision(p[labeled], y[labeled])
    return report
