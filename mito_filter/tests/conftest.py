"""Shared pytest fixtures for mito_filter unit tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

REAL_DATA_DIR = Path(
    "/scratch/siracusa/full_enchilada_3/six_hours_round_4/convmap_wedgeType_2_bin5"
)
REAL_BASE = "H99_2_100_1_bin5"


@pytest.fixture
def real_convmap_path() -> Path:
    """Path to a real convmap mrc; skips the test if the dev data is unavailable."""
    p = REAL_DATA_DIR / f"{REAL_BASE}_convmap.mrc"
    if not p.exists():
        pytest.skip("real dev-set convmap not present on this host")
    return p


@pytest.fixture
def real_csv_path() -> Path:
    """Path to a real peak csv; skips if unavailable."""
    p = REAL_DATA_DIR / f"{REAL_BASE}.csv"
    if not p.exists():
        pytest.skip("real dev-set csv not present on this host")
    return p


@pytest.fixture
def real_angles_mrc_path() -> Path:
    """Path to a real packed-index ``_angles.mrc``; skips if unavailable."""
    p = REAL_DATA_DIR / f"{REAL_BASE}_angles.mrc"
    if not p.exists():
        pytest.skip("real dev-set angles.mrc not present on this host")
    return p


@pytest.fixture
def real_angles_list_path() -> Path:
    """Path to a real ``_angles.list`` orientation grid; skips if unavailable."""
    p = REAL_DATA_DIR / f"{REAL_BASE}_angles.list"
    if not p.exists():
        pytest.skip("real dev-set angles.list not present on this host")
    return p


@pytest.fixture
def tiny_volume() -> np.ndarray:
    """A small deterministic fp16 volume for backend/field tests."""
    rng = np.random.default_rng(0)
    return rng.standard_normal((16, 20, 24)).astype(np.float16)
