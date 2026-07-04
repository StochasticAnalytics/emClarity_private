"""Unit tests for the whole-search feature-cache partitioner (optimize/feature_cache)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mito_filter.optimize.dataset import CACHE_SUFFIX
from mito_filter.optimize.feature_cache import cache_path_for, select_partition


def test_select_partition_covers_and_is_disjoint() -> None:
    """Over J=1..N the strides partition the whole set exactly (no overlap, no gap)."""
    bases = [f"H99_2_{i}_1_bin5" for i in range(112)]
    total = 7
    seen: list[str] = []
    for j in range(1, total + 1):
        part = select_partition(bases, j, total)
        assert part, "each partition should get at least one tomogram for 112/7"
        seen.extend(part)
    assert sorted(seen) == sorted(bases)
    assert len(seen) == len(set(seen)) == len(bases)


def test_select_partition_balanced_sizes() -> None:
    """Stride sizes differ by at most one (a good static load balance)."""
    bases = [str(i) for i in range(100)]
    total = 8
    sizes = [len(select_partition(bases, j, total)) for j in range(1, total + 1)]
    assert max(sizes) - min(sizes) <= 1
    assert sum(sizes) == 100


def test_select_partition_total_one_returns_all_sorted() -> None:
    bases = ["c", "a", "b"]
    assert select_partition(bases, 1, 1) == ["a", "b", "c"]


def test_select_partition_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        select_partition(["a", "b"], 3, 2)


def test_cache_path_for_matches_searchdataset_layout() -> None:
    """The written path is exactly what SearchDataset.from_cache_dir discovers."""
    p = cache_path_for(Path("/scratch/cache"), "H99_2_100_1_bin5")
    assert p == Path("/scratch/cache") / f"H99_2_100_1_bin5{CACHE_SUFFIX}"
    assert p.name.endswith(".features.parquet")
