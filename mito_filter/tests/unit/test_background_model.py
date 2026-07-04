"""Unit tests for the per-tomo background calibration (DESIGN §9.2).

The robust fit must recover the convmap background ``N(3.28, 0.48)`` (SPEC §1) despite the heavy
right-tail hits, on both synthetic Gaussian+tail data and a real convmap crop. This is what makes
absolute CC thresholds portable across tomograms.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from mito_filter.core.field import DenseField
from mito_filter.core.grid import VoxelGrid
from mito_filter.emclarity.mrc_io import open_dense_mmap
from mito_filter.fields.calibrate import BackgroundModel, BackgroundStats


def _synthetic_convmap(seed: int = 0, n: int = 400_000) -> np.ndarray:
    """N(3.28, 0.48) background plus a 2% compact extreme-CC tail (gold/ice-like hits)."""
    rng = np.random.default_rng(seed)
    bg = rng.normal(3.28, 0.48, size=n)
    n_tail = n // 50
    tail = rng.uniform(8.0, 13.0, size=n_tail)
    return np.concatenate([bg, tail]).astype(np.float32)


def test_mad_is_robust_to_the_right_tail() -> None:
    data = _synthetic_convmap()
    stats = BackgroundModel("mad").fit(data)
    # The 2% extreme tail must NOT drag the location/scale (that is the whole point of MAD).
    assert stats.mean == pytest.approx(3.28, abs=0.04)
    assert stats.std == pytest.approx(0.48, abs=0.05)
    assert stats.method == "mad"


def test_mad_ignores_tail_vs_naive_moments() -> None:
    data = _synthetic_convmap()
    naive_std = float(np.std(data))
    robust = BackgroundModel("mad").fit(data)
    # Naive std is inflated by the tail; the robust std is much closer to the true 0.48.
    assert naive_std > 0.7
    assert robust.std < 0.6


def test_truncated_method_recovers_location() -> None:
    data = _synthetic_convmap()
    stats = BackgroundModel("truncated", p_lo=1.0, p_hi=95.0).fit(data)
    assert stats.mean == pytest.approx(3.28, abs=0.05)
    assert stats.method == "truncated"


def test_zscore_roundtrip_is_standard_normal() -> None:
    rng = np.random.default_rng(1)
    bg = rng.normal(5.0, 1.3, size=200_000).astype(np.float32)
    stats = BackgroundModel("mad").fit(bg)
    z = stats.zscore(bg)
    assert float(z.mean()) == pytest.approx(0.0, abs=0.02)
    assert float(z.std()) == pytest.approx(1.0, abs=0.05)


def test_stats_zscore_and_serialization() -> None:
    stats = BackgroundStats(mean=3.2, std=0.5, method="mad", n_samples=10)
    z = stats.zscore(np.array([3.2, 3.7], dtype=np.float32))
    assert z[0] == pytest.approx(0.0, abs=1e-6)
    assert z[1] == pytest.approx(1.0, abs=1e-6)
    d = stats.to_dict()
    assert d["mean"] == 3.2 and d["std"] == 0.5 and d["method"] == "mad"


def test_zero_std_is_floored() -> None:
    stats = BackgroundStats(mean=1.0, std=0.0, method="mad", n_samples=1)
    # Must not divide by zero.
    assert np.isfinite(stats.zscore(np.array([2.0]))).all()


def test_empty_fit_raises() -> None:
    with pytest.raises(ValueError):
        BackgroundModel("mad").fit(np.array([np.nan, np.inf, -np.inf], dtype=np.float32))


def test_bad_config_raises() -> None:
    with pytest.raises(ValueError):
        BackgroundModel("nope")
    with pytest.raises(ValueError):
        BackgroundModel("truncated", p_lo=90.0, p_hi=10.0)


def test_subsample_is_capped_and_reproducible() -> None:
    data = _synthetic_convmap(n=1_000_000)
    m = BackgroundModel("mad", max_samples=50_000)
    a = m.fit(data)
    b = m.fit(data)
    assert a.n_samples == 50_000
    assert a.mean == b.mean and a.std == b.std  # deterministic subsample (seeded)


def test_fit_field_on_real_convmap_crop() -> None:
    """The strided field fit recovers the SPEC background on a real convmap crop."""
    path = Path(
        "/scratch/siracusa/full_enchilada_3/six_hours_round_4/"
        "convmap_wedgeType_2_bin5/H99_2_100_1_bin5_convmap.mrc"
    )
    if not path.exists():
        pytest.skip("real dev-set convmap not present on this host")
    mm = open_dense_mmap(path)
    crop = np.asarray(mm[80:240, 100:700, 100:560], np.float32)  # ~44 M voxels, still fast
    field = DenseField.from_array("cc", VoxelGrid(crop.shape, 12.5), crop, channels=1)
    stats = BackgroundModel("mad").fit_field(field)
    # SPEC §1: background ~ N(3.28, 0.48); median ~ 3.23. Robust fit lands in a tight band.
    assert 3.1 <= stats.mean <= 3.4
    assert 0.35 <= stats.std <= 0.55
