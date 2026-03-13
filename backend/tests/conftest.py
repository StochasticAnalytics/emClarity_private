"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory structure."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    for subdir in ["rawData", "fixedStacks", "aliStacks", "cache", "convmap", "FSC", "logFile"]:
        (project_dir / subdir).mkdir()

    return project_dir
