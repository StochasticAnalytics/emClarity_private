"""
Acceptance tests: Parameter Validation
=======================================

These tests verify that the backend correctly validates parameter values
before they are used to launch emClarity commands.

Validation is critical for scientific integrity -- out-of-range values
can produce silently wrong reconstructions.
"""

from typing import Any

import pytest
import httpx


# ---------------------------------------------------------------------------
# Validation endpoint
# ---------------------------------------------------------------------------

VALIDATE_ENDPOINT = "/api/v1/parameters/validate"


@pytest.mark.asyncio
async def test_validate_valid_parameters_passes(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
):
    """A complete set of valid parameters must pass validation."""
    response = await api_client.post(
        VALIDATE_ENDPOINT,
        json={"parameters": minimal_valid_parameters},
    )
    assert response.status_code == 200, (
        f"Valid parameters should pass validation, got {response.status_code}: "
        f"{response.text}"
    )
    data = response.json()
    assert data.get("valid") is True, (
        f"Expected valid=True, got: {data}"
    )


@pytest.mark.asyncio
async def test_validate_missing_required_parameter_fails(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
):
    """Omitting a required parameter (PIXEL_SIZE) must fail validation.

    The backend must return a clear error identifying the missing parameter.
    """
    params = dict(minimal_valid_parameters)
    del params["PIXEL_SIZE"]

    response = await api_client.post(
        VALIDATE_ENDPOINT,
        json={"parameters": params},
    )
    # Accept 200 with valid=False or 422 Unprocessable Entity
    if response.status_code == 200:
        data = response.json()
        assert data.get("valid") is False, (
            "Missing required parameter should fail validation"
        )
        # The error message should mention the missing parameter
        errors = data.get("errors", [])
        error_text = str(errors).lower()
        assert "pixel_size" in error_text or "PIXEL_SIZE" in str(errors), (
            f"Error should mention PIXEL_SIZE, got: {errors}"
        )
    else:
        assert response.status_code == 422, (
            f"Expected 200 or 422, got {response.status_code}"
        )


@pytest.mark.asyncio
async def test_validate_out_of_range_value_fails(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
):
    """A value outside the declared range must fail validation.

    VOLTAGE has range [20000, 1000000].  A value of 100 (100 V) is
    physically unreasonable and must be rejected.
    """
    params = dict(minimal_valid_parameters)
    params["VOLTAGE"] = 100  # Way below minimum of 20000

    response = await api_client.post(
        VALIDATE_ENDPOINT,
        json={"parameters": params},
    )
    if response.status_code == 200:
        data = response.json()
        assert data.get("valid") is False, (
            "Out-of-range VOLTAGE=100 should fail validation"
        )
        errors = data.get("errors", [])
        error_text = str(errors).upper()
        assert "VOLTAGE" in error_text, (
            f"Error should mention VOLTAGE, got: {errors}"
        )
    else:
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_validate_wrong_type_fails(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
):
    """Passing a string where a numeric is expected must fail validation.

    PIXEL_SIZE is numeric; passing "not_a_number" must be rejected.
    """
    params = dict(minimal_valid_parameters)
    params["PIXEL_SIZE"] = "not_a_number"

    response = await api_client.post(
        VALIDATE_ENDPOINT,
        json={"parameters": params},
    )
    if response.status_code == 200:
        data = response.json()
        assert data.get("valid") is False, (
            "String value for numeric PIXEL_SIZE should fail validation"
        )
    else:
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_deprecated_parameter_name_accepted(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
):
    """The old parameter name ``flgCCCcutoff`` must be accepted as an alias
    for the current name ``ccc_cutoff``.

    Many existing parameter files use the deprecated name.  The backend
    must silently translate it to the modern name.
    """
    params = dict(minimal_valid_parameters)
    # Use the deprecated name instead of the current name
    params["flgCCCcutoff"] = 0.5

    response = await api_client.post(
        VALIDATE_ENDPOINT,
        json={"parameters": params},
    )
    assert response.status_code in (200, 201), (
        f"Deprecated name flgCCCcutoff should be accepted, "
        f"got {response.status_code}: {response.text}"
    )
    if response.status_code == 200:
        data = response.json()
        assert data.get("valid") is True, (
            f"Deprecated name flgCCCcutoff should pass validation: {data}"
        )


@pytest.mark.asyncio
async def test_validate_negative_gpu_count_fails(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
):
    """nGPUs has range [1, 1000].  A value of 0 or negative must be rejected."""
    params = dict(minimal_valid_parameters)
    params["nGPUs"] = 0

    response = await api_client.post(
        VALIDATE_ENDPOINT,
        json={"parameters": params},
    )
    if response.status_code == 200:
        data = response.json()
        assert data.get("valid") is False, (
            "nGPUs=0 is below the minimum of 1 and should fail"
        )
    else:
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_validate_ampcont_out_of_unit_range_fails(
    api_client: httpx.AsyncClient,
    minimal_valid_parameters: dict[str, Any],
):
    """AMPCONT must be in [0.0, 1.0].  A value of 7.0 (common user error
    from confusing fraction with percentage) must be rejected."""
    params = dict(minimal_valid_parameters)
    params["AMPCONT"] = 7.0  # User meant 0.07

    response = await api_client.post(
        VALIDATE_ENDPOINT,
        json={"parameters": params},
    )
    if response.status_code == 200:
        data = response.json()
        assert data.get("valid") is False, (
            "AMPCONT=7.0 is above maximum of 1.0 and should fail"
        )
    else:
        assert response.status_code == 422
