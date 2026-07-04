"""Per-tomo background calibration — what makes convmap thresholds portable (DESIGN §9.2).

The convmap is a per-orientation sigma-normalised CC max, **not** a calibrated SNR, and its
background mode drifts per tomogram (SPEC §1: background ~ N(3.28, 0.48) with a heavy right
tail = the hits). Absolute thresholds (gold/ice ~8-13, membrane ~4-6) therefore do not transfer
between tomograms. :class:`BackgroundModel` robustly fits each tomogram's background
``N(mu, sigma)`` and z-scores the convmap against it, so a shared absolute threshold becomes a
dataset-portable z-score. The fitted :class:`BackgroundStats` are stored in the ``FittedConfig``
so transfer rescales rather than reusing raw thresholds.

Two robust estimators, both resistant to the right-tail hits:

* ``"mad"`` (default) — median + ``1.4826 * MAD``. 50 % breakdown; the bulk is Gaussian so this
  recovers the background sigma while ignoring the sparse extreme-CC tail.
* ``"truncated"`` — mean/std of the central ``[p_lo, p_hi]`` percentile band (drop the tail, and
  the extreme low outliers), with no truncation-bias correction (use ``"mad"`` if you need an
  unbiased sigma).

CPU/numpy only; importing this module never needs torch/cupy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..core.field import DenseField

_MAD_TO_SIGMA: float = 1.4826
"""Scale converting the median absolute deviation to a Gaussian sigma."""


@dataclass(frozen=True)
class BackgroundStats:
    """Fitted background statistics for one tomogram.

    Args:
        mean: The background location (median for ``"mad"``, truncated mean otherwise).
        std: The background scale (``1.4826*MAD`` for ``"mad"``, truncated std otherwise).
        method: The estimator used (``"mad"`` / ``"truncated"``).
        n_samples: Number of voxels the fit consumed.

    Attributes:
        mean: Background location.
        std: Background scale.
        method: Estimator name.
        n_samples: Sample size.
    """

    mean: float
    std: float
    method: str
    n_samples: int

    def zscore(self, values: NDArray[np.generic]) -> NDArray[np.float32]:
        """Z-score values against this background: ``(v - mean) / std``.

        Args:
            values: Array of convmap intensities.

        Returns:
            The z-scored array as float32 (std floored at a tiny epsilon).
        """
        denom = self.std if self.std > 1e-6 else 1e-6
        return np.asarray((np.asarray(values, dtype=np.float64) - self.mean) / denom, np.float32)

    def to_dict(self) -> dict[str, float | str | int]:
        """Return a plain dict for ``FittedConfig`` serialisation."""
        return {
            "mean": float(self.mean),
            "std": float(self.std),
            "method": self.method,
            "n_samples": int(self.n_samples),
        }


class BackgroundModel:
    """Robust per-tomo background fitter + z-scorer (DESIGN §9.2).

    Args:
        method: ``"mad"`` (median + 1.4826*MAD, default) or ``"truncated"`` (central-band
            mean/std).
        p_lo: Lower percentile of the kept band for ``"truncated"`` (ignored for ``"mad"``).
        p_hi: Upper percentile of the kept band for ``"truncated"``; also the tail cut used
            when sampling so the estimate is not dominated by extreme voxels.
        max_samples: Cap on the number of voxels used for the fit (a subsample keeps the fit
            memory-safe on the 0.5 GB convmap).
        seed: RNG seed for the subsample (reproducible fits).

    Attributes:
        method: The estimator name.
        p_lo: Lower band percentile.
        p_hi: Upper band percentile.
        max_samples: Sample cap.
        seed: RNG seed.
    """

    def __init__(
        self,
        method: str = "mad",
        *,
        p_lo: float = 1.0,
        p_hi: float = 95.0,
        max_samples: int = 2_000_000,
        seed: int = 0,
    ) -> None:
        if method not in ("mad", "truncated"):
            raise ValueError(f"method must be 'mad' or 'truncated', got {method!r}")
        if not 0.0 <= p_lo < p_hi <= 100.0:
            raise ValueError(f"require 0 <= p_lo < p_hi <= 100, got ({p_lo}, {p_hi})")
        self.method = method
        self.p_lo = p_lo
        self.p_hi = p_hi
        self.max_samples = int(max_samples)
        self.seed = int(seed)

    def fit(self, values: NDArray[np.generic]) -> BackgroundStats:
        """Fit the background statistics from a 1-D (or flattenable) sample of intensities.

        Args:
            values: Convmap intensities (any shape; flattened, NaNs dropped).

        Returns:
            The fitted :class:`BackgroundStats`.

        Raises:
            ValueError: If no finite samples are provided.
        """
        v = np.asarray(values, dtype=np.float64).ravel()
        v = v[np.isfinite(v)]
        if v.size == 0:
            raise ValueError("BackgroundModel.fit: no finite samples")
        v = self._subsample(v)
        if self.method == "mad":
            mean = float(np.median(v))
            mad = float(np.median(np.abs(v - mean)))
            std = _MAD_TO_SIGMA * mad
        else:  # truncated
            lo, hi = np.percentile(v, [self.p_lo, self.p_hi])
            band = v[(v >= lo) & (v <= hi)]
            if band.size == 0:
                band = v
            mean = float(np.mean(band))
            std = float(np.std(band))
        return BackgroundStats(mean=mean, std=max(std, 1e-6), method=self.method, n_samples=v.size)

    def fit_field(self, field: "DenseField", *, z_stride: Optional[int] = None) -> BackgroundStats:
        """Fit the background from a strided, subsampled read of a dense field (memory-safe).

        Reads every ``z_stride``-th z-slice (chosen so the strided read is near
        :attr:`max_samples` voxels) instead of hot-loading the whole 0.5 GB volume.

        Args:
            field: The convmap :class:`DenseField` to calibrate.
            z_stride: Explicit z-slice stride; if None it is derived from the volume size and
                :attr:`max_samples`.

        Returns:
            The fitted :class:`BackgroundStats`.
        """
        nz, ny, nx = field.grid.shape
        per_slice = max(ny * nx, 1)
        if z_stride is None:
            want_slices = max(1, self.max_samples // per_slice)
            z_stride = max(1, nz // max(want_slices, 1))
        sample = self._sample_slices(field, nz, z_stride)
        return self.fit(sample)

    @staticmethod
    def _sample_slices(field: "DenseField", nz: int, z_stride: int) -> NDArray[np.float32]:
        """Read a strided set of z-slices as fp32 (via the memmap when available)."""
        from ..core.field import Block

        idx = range(0, nz, max(1, z_stride))
        chunks = []
        for k in idx:
            blk = Block((k, k + 1), (0, field.grid.ny), (0, field.grid.nx))
            chunks.append(np.asarray(field.block(blk), dtype=np.float32).ravel())
        return np.concatenate(chunks) if chunks else np.zeros((0,), np.float32)

    def _subsample(self, v: NDArray[np.float64]) -> NDArray[np.float64]:
        """Randomly subsample ``v`` down to :attr:`max_samples` (reproducible)."""
        if v.size <= self.max_samples:
            return v
        rng = np.random.default_rng(self.seed)
        take = rng.choice(v.size, size=self.max_samples, replace=False)
        return v[take]
