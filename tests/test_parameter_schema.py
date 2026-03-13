"""
Acceptance tests: Parameter Schema API
=======================================

These tests verify that the backend serves a valid, complete parameter schema
that the React frontend can consume to dynamically build the parameter editor.

The schema is the single source of truth for every emClarity parameter and is
derived from ``metaData/BH_parseParameterFile.m``.
"""

import pytest
import httpx


# ---------------------------------------------------------------------------
# Schema endpoint
# ---------------------------------------------------------------------------

SCHEMA_ENDPOINT = "/api/v1/parameters/schema"


@pytest.mark.asyncio
async def test_get_parameter_schema_returns_200(api_client: httpx.AsyncClient):
    """The schema endpoint must return HTTP 200 with a JSON body."""
    response = await api_client.get(SCHEMA_ENDPOINT)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert isinstance(data, dict), "Schema response must be a JSON object"


@pytest.mark.asyncio
async def test_parameter_schema_has_required_categories(
    api_client: httpx.AsyncClient,
):
    """The schema must include at least the five core parameter categories.

    These categories group parameters in the frontend UI:
      - microscope  (PIXEL_SIZE, Cs, VOLTAGE, AMPCONT)
      - hardware    (nGPUs, nCpuCores)
      - ctf         (whitenPS, filterDefocus, ...)
      - alignment   (symmetry, ccc_cutoff, ...)
      - classification (Pca_clusters, ...)
    """
    response = await api_client.get(SCHEMA_ENDPOINT)
    assert response.status_code == 200
    data = response.json()

    # The schema must expose a list of parameters, each having a "category".
    parameters = data.get("parameters", [])
    assert len(parameters) > 0, "Schema must contain at least one parameter"

    categories_present = {p["category"] for p in parameters}

    required_categories = {
        "microscope",
        "hardware",
        "ctf",
        "alignment",
        "classification",
    }
    missing = required_categories - categories_present
    assert not missing, (
        f"Schema is missing required categories: {missing}. "
        f"Found: {categories_present}"
    )


@pytest.mark.asyncio
async def test_parameter_schema_contains_pixel_size(
    api_client: httpx.AsyncClient,
):
    """PIXEL_SIZE must exist in the schema -- it is fundamental to every
    calculation in the pipeline."""
    response = await api_client.get(SCHEMA_ENDPOINT)
    data = response.json()
    param_names = {p["name"] for p in data.get("parameters", [])}
    assert "PIXEL_SIZE" in param_names, (
        "PIXEL_SIZE is missing from the parameter schema"
    )


@pytest.mark.asyncio
async def test_parameter_schema_contains_voltage(
    api_client: httpx.AsyncClient,
):
    """VOLTAGE must exist -- required for CTF calculations."""
    response = await api_client.get(SCHEMA_ENDPOINT)
    data = response.json()
    param_names = {p["name"] for p in data.get("parameters", [])}
    assert "VOLTAGE" in param_names, (
        "VOLTAGE is missing from the parameter schema"
    )


@pytest.mark.asyncio
async def test_required_parameters_marked_correctly(
    api_client: httpx.AsyncClient,
):
    """The following parameters must be marked as ``required: true`` because
    the MATLAB code throws an error if they are missing:

      PIXEL_SIZE, Cs, VOLTAGE, AMPCONT, nGPUs, nCpuCores, symmetry
    """
    response = await api_client.get(SCHEMA_ENDPOINT)
    data = response.json()

    params_by_name = {p["name"]: p for p in data.get("parameters", [])}

    must_be_required = [
        "PIXEL_SIZE",
        "Cs",
        "VOLTAGE",
        "AMPCONT",
        "nGPUs",
        "nCpuCores",
        "symmetry",
    ]

    for name in must_be_required:
        assert name in params_by_name, (
            f"Required parameter '{name}' not found in schema"
        )
        assert params_by_name[name].get("required") is True, (
            f"Parameter '{name}' must be marked required=true"
        )


@pytest.mark.asyncio
async def test_parameter_ranges_are_valid(api_client: httpx.AsyncClient):
    """For every parameter that declares a range, the range must be a
    two-element list ``[min, max]`` with ``min <= max``.

    This catches schema generation bugs that could let the frontend accept
    physically impossible values (e.g., negative voltage).
    """
    response = await api_client.get(SCHEMA_ENDPOINT)
    data = response.json()

    for param in data.get("parameters", []):
        r = param.get("range")
        if r is not None:
            assert isinstance(r, list) and len(r) == 2, (
                f"Parameter '{param['name']}' range must be a "
                f"two-element list, got: {r}"
            )
            assert r[0] <= r[1], (
                f"Parameter '{param['name']}' has invalid range: "
                f"min ({r[0]}) > max ({r[1]})"
            )


@pytest.mark.asyncio
async def test_parameter_schema_fields_are_complete(
    api_client: httpx.AsyncClient,
):
    """Every parameter object must include at minimum these fields:
    name, type, required, description, category.

    The frontend relies on these to build the dynamic form.
    """
    response = await api_client.get(SCHEMA_ENDPOINT)
    data = response.json()

    required_fields = {"name", "type", "required", "description", "category"}

    for param in data.get("parameters", []):
        missing = required_fields - set(param.keys())
        assert not missing, (
            f"Parameter '{param.get('name', '???')}' is missing "
            f"fields: {missing}"
        )


@pytest.mark.asyncio
async def test_parameter_types_are_known(api_client: httpx.AsyncClient):
    """Every parameter type must be one of the known types so the frontend
    can render the correct input widget."""
    response = await api_client.get(SCHEMA_ENDPOINT)
    data = response.json()

    known_types = {
        "numeric",
        "numeric_array",
        "string",
        "boolean",
    }

    for param in data.get("parameters", []):
        assert param["type"] in known_types, (
            f"Parameter '{param['name']}' has unknown type "
            f"'{param['type']}'. Known types: {known_types}"
        )
