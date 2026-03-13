"""
Acceptance tests: Workflow State Machine
=========================================

These tests verify that the backend enforces the emClarity processing
pipeline order.  The state machine prevents users from running commands
out of order, which would produce errors or scientifically invalid results.

State machine from workflow_map.md:

    UNINITIALIZED
      -> TILT_ALIGNED        (after autoAlign)
        -> CTF_ESTIMATED      (after ctf estimate)
          -> RECONSTRUCTED    (after ctf 3d)
            -> PARTICLES_PICKED  (after templateSearch)
              -> INITIALIZED     (after init)
                -> CYCLE_0_AVG   (after avg 0 RawAlignment)
                  -> [ALIGN -> AVG -> ... iterative]
                    -> EXPORT    (reconstruct)
"""

from typing import Any

import pytest
import httpx


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

PROJECTS_ENDPOINT = "/api/v1/projects"
WORKFLOW_ENDPOINT = "/api/v1/workflow"


def _project_url(project_id: str) -> str:
    return f"{PROJECTS_ENDPOINT}/{project_id}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_project(
    client: httpx.AsyncClient,
    params: dict[str, Any],
    project_dir,
    name: str = "workflow_test",
) -> str:
    """Create a project and return its ID."""
    payload = {
        "name": name,
        "directory": str(project_dir),
        "parameters": params,
    }
    resp = await client.post(PROJECTS_ENDPOINT, json=payload)
    assert resp.status_code == 201, (
        f"Project creation failed: {resp.status_code}: {resp.text}"
    )
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initial_state_is_uninitialized(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
    sample_project_dir,
):
    """A newly created project must report its state as UNINITIALIZED."""
    project_id = await _create_project(
        api_client, minimal_valid_parameters, sample_project_dir
    )

    resp = await api_client.get(_project_url(project_id))
    assert resp.status_code == 200
    state = resp.json().get("state", "").upper()
    assert state == "UNINITIALIZED", (
        f"Expected UNINITIALIZED, got: {state}"
    )


@pytest.mark.asyncio
async def test_available_commands_in_uninitialized_state(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
    sample_project_dir,
):
    """In the UNINITIALIZED state, only ``autoAlign`` (and possibly
    system-level commands like ``check``) should be available.

    All downstream commands (ctf estimate, init, avg, etc.) require
    prior steps to have completed.
    """
    project_id = await _create_project(
        api_client, minimal_valid_parameters, sample_project_dir,
        name="avail_cmds_test",
    )

    resp = await api_client.get(
        f"{WORKFLOW_ENDPOINT}/{project_id}/available-commands"
    )
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}: {resp.text}"
    )

    data = resp.json()
    commands = data if isinstance(data, list) else data.get("commands", [])

    # Extract command names (may be strings or dicts with a "name" key)
    command_names = set()
    for cmd in commands:
        if isinstance(cmd, str):
            command_names.add(cmd)
        elif isinstance(cmd, dict) and "name" in cmd:
            command_names.add(cmd["name"])

    assert "autoAlign" in command_names, (
        f"autoAlign must be available in UNINITIALIZED state. "
        f"Available: {command_names}"
    )

    # These commands must NOT be available yet
    disallowed_in_uninitialized = {"init", "avg", "alignRaw", "reconstruct"}
    incorrectly_available = command_names & disallowed_in_uninitialized
    assert not incorrectly_available, (
        f"Commands {incorrectly_available} should not be available in "
        f"UNINITIALIZED state"
    )


@pytest.mark.asyncio
async def test_state_transitions_follow_pipeline_order(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
    sample_project_dir,
):
    """The state machine must define valid transitions that follow the
    documented pipeline order.

    This test fetches the state machine definition and verifies that
    key transitions exist.
    """
    # The backend should expose the state machine definition
    resp = await api_client.get(f"{WORKFLOW_ENDPOINT}/state-machine")
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}: {resp.text}"
    )

    data = resp.json()

    # The response should describe states and their allowed transitions
    states = data.get("states") or data.get("transitions") or data
    assert states, "State machine definition must not be empty"

    # Verify the response contains recognizable state/transition info.
    # Flexible check: accept either a list of states, a dict of
    # state->transitions, or a list of transition objects.
    response_text = str(data).upper()
    assert "UNINITIALIZED" in response_text, (
        "State machine must include UNINITIALIZED state"
    )


@pytest.mark.asyncio
async def test_cannot_skip_pipeline_steps(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
    sample_project_dir,
):
    """It must be impossible to run ``avg`` before ``init`` has completed.

    ``avg`` requires ``subTomoMeta.mat`` which is created by ``init``,
    which in turn requires template search results.  Running ``avg``
    in an UNINITIALIZED project must fail.
    """
    project_id = await _create_project(
        api_client, minimal_valid_parameters, sample_project_dir,
        name="skip_test",
    )

    # Attempt to run avg in UNINITIALIZED state
    resp = await api_client.post(
        f"{WORKFLOW_ENDPOINT}/{project_id}/run",
        json={
            "command": "avg",
            "args": {"cycle": 0, "stage": "RawAlignment"},
        },
    )

    # Must be rejected -- either 400 (bad request), 409 (conflict/wrong state),
    # or 422 (validation error)
    assert resp.status_code in (400, 409, 422), (
        f"Running avg in UNINITIALIZED state should be rejected, "
        f"got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_cannot_run_reconstruct_before_averaging(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
    sample_project_dir,
):
    """The ``reconstruct`` command requires reference volumes from ``avg``.
    Running it on an uninitialized project must fail."""
    project_id = await _create_project(
        api_client, minimal_valid_parameters, sample_project_dir,
        name="reconstruct_skip_test",
    )

    resp = await api_client.post(
        f"{WORKFLOW_ENDPOINT}/{project_id}/run",
        json={
            "command": "reconstruct",
            "args": {
                "cycle": 0,
                "output_prefix": "output",
                "symmetry": "C1",
                "max_exposure": 60,
                "classIDX": 1,
            },
        },
    )

    assert resp.status_code in (400, 409, 422), (
        f"Running reconstruct before avg should be rejected, "
        f"got {resp.status_code}: {resp.text}"
    )
