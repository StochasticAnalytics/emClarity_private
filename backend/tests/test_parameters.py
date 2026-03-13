"""Tests for parameter models, service, and API endpoints."""

from __future__ import annotations

from backend.models.parameter import (
    ParameterCategory,
    ParameterDefinition,
    ParameterFile,
    ParameterType,
    ParameterValidationResult,
    ParameterValue,
)
from backend.services.parameter_service import ParameterService


class TestParameterModels:
    """Verify Pydantic model creation and serialization."""

    def test_parameter_definition_creation(self):
        defn = ParameterDefinition(
            name="PIXEL_SIZE",
            type=ParameterType.FLOAT,
            required=True,
            default=1.0,
            range=[0.1, 50.0],
            description="Pixel size in angstroms",
            category=ParameterCategory.GENERAL,
            units="angstroms",
        )
        assert defn.name == "PIXEL_SIZE"
        assert defn.type == ParameterType.FLOAT
        assert defn.required is True
        assert defn.range == [0.1, 50.0]

    def test_parameter_value_creation(self):
        pv = ParameterValue(name="GPU", value=[0, 1])
        assert pv.name == "GPU"
        assert pv.value == [0, 1]

    def test_parameter_file_creation(self):
        pf = ParameterFile(
            parameters=[
                ParameterValue(name="PIXEL_SIZE", value=1.35),
                ParameterValue(name="GPU", value=[0]),
            ],
            path="/tmp/test_param.m",
        )
        assert len(pf.parameters) == 2
        assert pf.path == "/tmp/test_param.m"

    def test_validation_result(self):
        result = ParameterValidationResult(
            valid=False,
            errors=["Missing required parameter 'PIXEL_SIZE'"],
            warnings=["Unknown parameter 'foo'"],
        )
        assert result.valid is False
        assert len(result.errors) == 1
        assert len(result.warnings) == 1


class TestParameterService:
    """Verify the parameter service logic."""

    def test_get_schema_returns_definitions(self):
        service = ParameterService()
        schema = service.get_schema()
        assert isinstance(schema, list)
        assert len(schema) > 0
        assert all(isinstance(d, ParameterDefinition) for d in schema)

    def test_parse_value_integer(self):
        assert ParameterService._parse_value("42") == 42

    def test_parse_value_float(self):
        assert ParameterService._parse_value("3.14") == 3.14

    def test_parse_value_vector(self):
        assert ParameterService._parse_value("[1, 2, 3]") == [1, 2, 3]

    def test_parse_value_string(self):
        assert ParameterService._parse_value("'hello'") == "hello"

    def test_format_value_bool(self):
        assert ParameterService._format_value(True) == "1"
        assert ParameterService._format_value(False) == "0"

    def test_format_value_list(self):
        assert ParameterService._format_value([1, 2, 3]) == "[1, 2, 3]"

    def test_save_and_load_roundtrip(self, tmp_path):
        service = ParameterService()
        path = str(tmp_path / "roundtrip.m")

        original = ParameterFile(
            parameters=[
                ParameterValue(name="PIXEL_SIZE", value=1.35),
                ParameterValue(name="GPU", value=[0, 1]),
                ParameterValue(name="Cls_className", value="myclass"),
            ],
            path=path,
        )

        service.save_parameter_file(original)
        loaded = service.load_parameter_file(path)

        assert loaded.path == path
        loaded_map = {p.name: p.value for p in loaded.parameters}
        assert loaded_map["PIXEL_SIZE"] == 1.35
        assert loaded_map["GPU"] == [0, 1]
        assert loaded_map["Cls_className"] == "myclass"

    def test_validate_missing_required(self):
        service = ParameterService()
        result = service.validate_parameters([])
        # The builtin schema has required params, so validation should flag them
        assert result.valid is False
        assert any("PIXEL_SIZE" in e for e in result.errors)

    def test_validate_unknown_parameter(self):
        service = ParameterService()
        result = service.validate_parameters([
            ParameterValue(name="PIXEL_SIZE", value=1.0),
            ParameterValue(name="GPU", value=[0]),
            ParameterValue(name="TOTALLY_FAKE", value="nope"),
        ])
        assert any("TOTALLY_FAKE" in w for w in result.warnings)


class TestParameterEndpoints:
    """Test the API endpoints via the test client."""

    def test_get_schema(self, client):
        response = client.get("/api/parameters/schema")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_load_missing_file(self, client):
        response = client.get("/api/parameters/file/nonexistent.m")
        assert response.status_code == 404

    def test_validate_endpoint(self, client):
        response = client.post(
            "/api/parameters/validate",
            json=[
                {"name": "PIXEL_SIZE", "value": 1.0},
                {"name": "GPU", "value": [0]},
            ],
        )
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data
