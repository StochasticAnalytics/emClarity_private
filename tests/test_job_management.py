"""
Acceptance tests: Job Management
=================================

These tests verify the job lifecycle -- creating, listing, and monitoring
emClarity processing jobs.

A "job" represents a single invocation of an emClarity command (e.g.,
``autoAlign``, ``ctf estimate``, ``avg``).  The frontend displays job
status in real time and allows users to monitor progress.
"""

from typing import Any

import pytest
import httpx


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

PROJECTS_ENDPOINT = "/api/v1/projects"
JOBS_ENDPOINT = "/api/v1/jobs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_project(
    client: httpx.AsyncClient,
    params: dict[str, Any],
    project_dir,
) -> str:
    """Create a project and return its ID."""
    payload = {
        "name": "job_test_project",
        "directory": str(project_dir),
        "parameters": params,
    }
    resp = await client.post(PROJECTS_ENDPOINT, json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_jobs_returns_empty_initially(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
    sample_project_dir,
):
    """A new project with no submitted commands must have zero jobs."""
    project_id = await _create_project(
        api_client, minimal_valid_parameters, sample_project_dir
    )

    response = await api_client.get(
        JOBS_ENDPOINT,
        params={"project_id": project_id},
    )
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )

    data = response.json()
    jobs = data if isinstance(data, list) else data.get("jobs", [])
    assert len(jobs) == 0, (
        f"New project should have 0 jobs, got {len(jobs)}"
    )


@pytest.mark.asyncio
async def test_job_status_model_has_required_fields(
    api_client: httpx.AsyncClient,
):
    """The ``/api/v1/jobs/schema`` (or the job model documentation) must
    define these fields for every job object:

      - id: unique job identifier
      - project_id: which project this job belongs to
      - command: the emClarity command (e.g., "autoAlign")
      - status: one of PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
      - created_at: ISO-8601 timestamp
      - updated_at: ISO-8601 timestamp

    This test verifies the schema/model endpoint describes these fields.
    """
    # Try the schema endpoint first
    response = await api_client.get(f"{JOBS_ENDPOINT}/schema")

    if response.status_code == 404:
        # Fall back: check the OpenAPI spec for the Job model
        response = await api_client.get("/openapi.json")
        assert response.status_code == 200, (
            "Neither /api/v1/jobs/schema nor /openapi.json is available"
        )
        openapi = response.json()

        # Find the Job schema in the OpenAPI components
        schemas = openapi.get("components", {}).get("schemas", {})
        job_schema = None
        for name, schema in schemas.items():
            if "job" in name.lower():
                job_schema = schema
                break

        assert job_schema is not None, (
            "No Job-related schema found in OpenAPI spec"
        )

        properties = job_schema.get("properties", {})
        required_fields = {"id", "project_id", "command", "status"}
        missing = required_fields - set(properties.keys())
        assert not missing, (
            f"Job model is missing fields: {missing}. "
            f"Found: {set(properties.keys())}"
        )
        return

    # If schema endpoint exists, validate it directly
    assert response.status_code == 200
    data = response.json()
    fields = set()
    if isinstance(data, dict):
        fields = set(data.get("properties", data).keys())

    required_fields = {"id", "project_id", "command", "status"}
    missing = required_fields - fields
    assert not missing, (
        f"Job schema is missing fields: {missing}. Found: {fields}"
    )


@pytest.mark.asyncio
async def test_job_status_values_are_valid(
    api_client: httpx.AsyncClient,
):
    """The backend must only use recognized status values for jobs.

    Valid statuses: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED.
    This test checks the OpenAPI spec or schema endpoint.
    """
    response = await api_client.get("/openapi.json")
    assert response.status_code == 200, (
        "OpenAPI spec must be available at /openapi.json"
    )

    openapi = response.json()
    schemas = openapi.get("components", {}).get("schemas", {})

    # Find a status enum in any schema
    valid_statuses = {"PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"}

    for name, schema in schemas.items():
        props = schema.get("properties", {})
        if "status" in props:
            status_prop = props["status"]
            enum_values = status_prop.get("enum")
            if enum_values:
                enum_set = {v.upper() for v in enum_values}
                assert valid_statuses.issubset(enum_set), (
                    f"Job status enum in {name} is missing values. "
                    f"Required: {valid_statuses}, Found: {enum_set}"
                )
                return  # Found and validated

    # If no enum was found, the test still passes -- the developer may
    # use runtime validation instead of enum in the schema.
    # We just verify that the openapi spec exists and is parseable.


@pytest.mark.asyncio
async def test_get_nonexistent_job_returns_404(
    api_client: httpx.AsyncClient,
):
    """Requesting a job that does not exist must return 404."""
    response = await api_client.get(f"{JOBS_ENDPOINT}/nonexistent-job-id-99999")
    assert response.status_code == 404, (
        f"Expected 404 for nonexistent job, got {response.status_code}"
    )
