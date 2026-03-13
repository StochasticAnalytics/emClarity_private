"""
Shared pytest fixtures for emClarity GUI acceptance tests.

These fixtures provide:
- An async HTTP client pointing at the FastAPI backend
- A loaded parameter schema from the phase0 artifacts
- A temporary project directory with mock emClarity structure
"""

import json
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Any

import httpx
import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The backend URL can be overridden via environment variable for CI.
BACKEND_URL = os.environ.get("EMCLARITY_BACKEND_URL", "http://localhost:8000")

# Path to the golden parameter schema extracted from BH_parseParameterFile.m
SCHEMA_PATH = Path(__file__).resolve().parent.parent / (
    "autonomous-build/templates/phase0-artifacts/parameter_schema.json"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Yield an async HTTP client pointed at the running backend.

    The base URL is ``http://localhost:8000`` unless overridden by the
    ``EMCLARITY_BACKEND_URL`` environment variable.
    """
    async with httpx.AsyncClient(
        base_url=BACKEND_URL,
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture
def sample_parameter_schema() -> dict[str, Any]:
    """Load and return the golden parameter schema as a Python dict.

    The schema lives at
    ``autonomous-build/templates/phase0-artifacts/parameter_schema.json``
    and was extracted from the MATLAB ``BH_parseParameterFile.m``.
    """
    assert SCHEMA_PATH.exists(), (
        f"Parameter schema not found at {SCHEMA_PATH}. "
        "Ensure phase0 artifacts have been generated."
    )
    with open(SCHEMA_PATH, "r") as fh:
        return json.load(fh)


@pytest.fixture
def sample_project_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with the standard emClarity project layout.

    Returns the path to the project root.  The directory tree mirrors what
    emClarity expects (see workflow_map.md section 6):

        project_root/
            rawData/
            fixedStacks/
            aliStacks/
            cache/
            convmap/
            FSC/
            logFile/
    """
    dirs = [
        "rawData",
        "fixedStacks",
        "aliStacks",
        "cache",
        "convmap",
        "FSC",
        "logFile",
    ]
    for d in dirs:
        (tmp_path / d).mkdir()

    return tmp_path


@pytest.fixture
def minimal_valid_parameters() -> dict[str, Any]:
    """Return a minimal dict of valid parameter values.

    These satisfy every required parameter from the schema and use physically
    realistic values for a 300 kV cryo-EM experiment.
    """
    return {
        "PIXEL_SIZE": 1.35e-10,
        "Cs": 2.7e-3,
        "VOLTAGE": 300_000,
        "AMPCONT": 0.07,
        "nGPUs": 1,
        "nCpuCores": 4,
        "symmetry": "C1",
        "Pca_clusters": 4,
        "subTomoMeta": "test_project",
    }
