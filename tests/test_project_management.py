"""
Acceptance tests: Project Management
=====================================

These tests verify the CRUD operations for emClarity projects.

A "project" in the GUI corresponds to an emClarity processing directory
with a parameter file and the standard directory layout (rawData/,
fixedStacks/, cache/, etc.).
"""

from typing import Any

import pytest
import httpx


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

PROJECTS_ENDPOINT = "/api/v1/projects"


def _project_url(project_id: str) -> str:
    return f"{PROJECTS_ENDPOINT}/{project_id}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_project_returns_201(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
    sample_project_dir,
):
    """Creating a new project must return HTTP 201 Created with a project ID."""
    payload = {
        "name": "test_project",
        "directory": str(sample_project_dir),
        "parameters": minimal_valid_parameters,
    }
    response = await api_client.post(PROJECTS_ENDPOINT, json=payload)
    assert response.status_code == 201, (
        f"Expected 201 Created, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "id" in data, "Response must include a project ID"
    assert data["id"], "Project ID must not be empty"


@pytest.mark.asyncio
async def test_create_project_sets_initial_state_uninitialized(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
    sample_project_dir,
):
    """A newly created project must have state ``UNINITIALIZED``.

    Per the workflow state machine (workflow_map.md section 5), no
    processing has occurred yet, so the project starts in the
    UNINITIALIZED state.
    """
    payload = {
        "name": "state_test_project",
        "directory": str(sample_project_dir),
        "parameters": minimal_valid_parameters,
    }
    response = await api_client.post(PROJECTS_ENDPOINT, json=payload)
    assert response.status_code == 201
    data = response.json()

    # The state may be returned inline or require a separate GET
    state = data.get("state")
    if state is None:
        # Fetch the project to get its state
        project_id = data["id"]
        get_resp = await api_client.get(_project_url(project_id))
        assert get_resp.status_code == 200
        state = get_resp.json().get("state")

    assert state is not None, "Project must have a 'state' field"
    assert state.upper() == "UNINITIALIZED", (
        f"New project state must be UNINITIALIZED, got: {state}"
    )


@pytest.mark.asyncio
async def test_load_project_returns_state(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
    sample_project_dir,
):
    """Loading (GET) an existing project must return its current state
    and parameters."""
    # First create the project
    payload = {
        "name": "load_test_project",
        "directory": str(sample_project_dir),
        "parameters": minimal_valid_parameters,
    }
    create_resp = await api_client.post(PROJECTS_ENDPOINT, json=payload)
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    # Now load it
    get_resp = await api_client.get(_project_url(project_id))
    assert get_resp.status_code == 200, (
        f"Expected 200, got {get_resp.status_code}: {get_resp.text}"
    )

    data = get_resp.json()
    assert "state" in data, "Loaded project must include 'state'"
    assert "name" in data, "Loaded project must include 'name'"
    assert "parameters" in data or "directory" in data, (
        "Loaded project must include 'parameters' or 'directory'"
    )


@pytest.mark.asyncio
async def test_list_tilt_series_returns_empty_for_new_project(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
    sample_project_dir,
):
    """A new project with an empty rawData/ directory must report zero
    tilt series.

    The frontend uses this endpoint to populate the tilt-series asset panel.
    """
    payload = {
        "name": "empty_tilts_project",
        "directory": str(sample_project_dir),
        "parameters": minimal_valid_parameters,
    }
    create_resp = await api_client.post(PROJECTS_ENDPOINT, json=payload)
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    # Fetch tilt series for this project
    tilt_resp = await api_client.get(
        f"{_project_url(project_id)}/tilt-series"
    )
    assert tilt_resp.status_code == 200, (
        f"Expected 200, got {tilt_resp.status_code}: {tilt_resp.text}"
    )

    data = tilt_resp.json()
    tilt_series = data if isinstance(data, list) else data.get("tilt_series", [])
    assert len(tilt_series) == 0, (
        f"New project should have 0 tilt series, got {len(tilt_series)}"
    )


@pytest.mark.asyncio
async def test_get_nonexistent_project_returns_404(
    api_client: httpx.AsyncClient,
):
    """Requesting a project that does not exist must return 404."""
    response = await api_client.get(
        _project_url("nonexistent-project-id-12345")
    )
    assert response.status_code == 404, (
        f"Expected 404, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio
async def test_create_project_without_name_fails(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
    sample_project_dir,
):
    """A project creation request without a name must be rejected."""
    payload = {
        "directory": str(sample_project_dir),
        "parameters": minimal_valid_parameters,
    }
    response = await api_client.post(PROJECTS_ENDPOINT, json=payload)
    assert response.status_code in (400, 422), (
        f"Expected 400 or 422, got {response.status_code}: {response.text}"
    )
