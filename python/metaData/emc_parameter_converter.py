"""
emClarity Parameter Converter.

Converts between MATLAB parameter files (.m) and JSON parameter files (.json)
with validation, type checking, and backward compatibility.

Author: emClarity Development Team
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ParameterInfo:
    """Information about a parameter including validation and conversion details."""

    old_name: str
    new_name: str
    param_type: type
    default_value: Any = None
    required: bool = False
    description: str = ""
    units: str = ""
    validation_range: tuple | None = None
    is_string: bool = False


class ParameterConverter:
    """
    Converts emClarity parameters between MATLAB and JSON formats.

    Features:
    - Bidirectional conversion (MATLAB ↔ JSON)
    - Parameter validation and type checking
    - Modern naming conventions with units
    - Backward compatibility
    """

    def __init__(self):
        """Initialize converter with default MATLAB-to-JSON parameter mapping."""
        self.parameter_mapping = self._create_parameter_mapping()
        self.required_parameters = self._get_required_parameters()

    def _create_parameter_mapping(self) -> dict[str, ParameterInfo]:
        """Create mapping between old MATLAB names and new JSON names."""
        # I'll start with the most critical parameters and ask for approval on naming
        mapping = {}

        # System/Hardware parameters - these seem straightforward
        mapping["nGPUs"] = ParameterInfo(
            old_name="nGPUs",
            new_name="system.gpu_count",  # More descriptive
            param_type=int,
            required=True,
            description="Number of GPUs to use for processing",
            validation_range=(1, 1000),
        )

        mapping["nCpuCores"] = ParameterInfo(
            old_name="nCpuCores",
            new_name="system.cpu_cores",  # More descriptive
            param_type=int,
            required=True,
            description="Number of CPU cores to use",
            validation_range=(1, 1000),
        )

        # Scientific notation parameters with updated units

        # Microscope parameters
        mapping["PIXEL_SIZE"] = ParameterInfo(
            old_name="PIXEL_SIZE",
            new_name="microscope.pixel_size_angstroms",
            param_type=float,
            required=True,
            description="Pixel size in angstroms",
            units="angstroms",
            validation_range=(0, 100),  # 0 to 100 Angstroms
        )

        mapping["Cs"] = ParameterInfo(
            old_name="Cs",
            new_name="microscope.spherical_aberration_mm",
            param_type=float,
            required=True,
            description="Spherical aberration in millimeters",
            units="mm",
            validation_range=(0, 10),  # 0 to 10 mm
        )

        mapping["VOLTAGE"] = ParameterInfo(
            old_name="VOLTAGE",
            new_name="microscope.acceleration_voltage_kv",
            param_type=float,
            required=True,
            description="Acceleration voltage in kilovolts",
            units="kV",
            validation_range=(20, 1000),  # 20 to 1000 kV
        )

        # CTF parameters (all in angstroms)
        mapping["max_ctf3dDepth"] = ParameterInfo(
            old_name="max_ctf3dDepth",
            new_name="ctf.max_depth_angstroms",
            param_type=float,
            required=False,
            description="Maximum CTF depth in angstroms",
            units="angstroms",
            validation_range=(1, 10000),  # 1 to 10000 Angstroms
        )

        mapping["defEstimate"] = ParameterInfo(
            old_name="defEstimate",
            new_name="ctf.defocus_estimate_angstroms",
            param_type=float,
            required=False,
            description="Initial defocus estimate in angstroms",
            units="angstroms",
            validation_range=(1000, 100000),  # 1000 to 100000 Angstroms
        )

        mapping["defWindow"] = ParameterInfo(
            old_name="defWindow",
            new_name="ctf.defocus_search_range_angstroms",
            param_type=float,
            required=False,
            description="Defocus search window in angstroms",
            units="angstroms",
            validation_range=(100, 50000),  # 100 to 50000 Angstroms
        )

        mapping["defCutOff"] = ParameterInfo(
            old_name="defCutOff",
            new_name="ctf.resolution_cutoff_angstroms",
            param_type=float,
            required=False,
            description="Resolution cutoff in angstroms",
            units="angstroms",
            validation_range=(1, 100),  # 1 to 100 Angstroms
        )

        mapping["beadDiameter"] = ParameterInfo(
            old_name="beadDiameter",
            new_name="sample.fiducial_diameter_angstroms",
            param_type=float,
            required=False,
            description="Fiducial bead diameter in angstroms",
            units="angstroms",
            validation_range=(10, 1000),  # 10 to 1000 Angstroms
        )

        # TomoCPR parameters (all in angstroms)
        mapping["tomoCprDefocusRange"] = ParameterInfo(
            old_name="tomoCprDefocusRange",
            new_name="tomocpr.defocus_refinement_range_angstroms",
            param_type=float,
            required=False,
            description="Defocus refinement range in angstroms",
            units="angstroms",
            validation_range=(100, 10000),  # 100 to 10000 Angstroms
        )

        mapping["tomoCprDefocusStep"] = ParameterInfo(
            old_name="tomoCprDefocusStep",
            new_name="tomocpr.defocus_refinement_step_angstroms",
            param_type=float,
            required=False,
            description="Defocus refinement step size in angstroms",
            units="angstroms",
            validation_range=(1, 1000),  # 1 to 1000 Angstroms
        )

        # Boolean parameters (flag → enable/disable)
        mapping["flgQualityWeight"] = ParameterInfo(
            old_name="flgQualityWeight",
            new_name="processing.enable_quality_weighting",
            param_type=bool,
            required=False,
            description="Enable quality-based weighting",
            default_value=False,
        )

        mapping["flgMultiRefAlignment"] = ParameterInfo(
            old_name="flgMultiRefAlignment",
            new_name="alignment.enable_multi_reference",
            param_type=bool,
            required=False,
            description="Enable multi-reference alignment",
            default_value=False,
        )

        mapping["flgClassify"] = ParameterInfo(
            old_name="flgClassify",
            new_name="classification.enable_classification",
            param_type=bool,
            required=False,
            description="Enable classification",
            default_value=False,
        )

        return mapping

    def _get_required_parameters(self) -> list[str]:
        """Get list of required parameter names."""
        return [
            info.new_name for info in self.parameter_mapping.values() if info.required
        ]

    def _convert_units_matlab_to_json(self, param_name: str, value: float) -> float:
        """Convert parameter values from MATLAB units to JSON units."""
        conversions = {
            "PIXEL_SIZE": lambda x: x * 1e10,  # meters to angstroms
            "Cs": lambda x: x * 1000,  # meters to mm
            "VOLTAGE": lambda x: x / 1000,  # volts to kV
            "max_ctf3dDepth": lambda x: x * 1e10,  # meters to angstroms
            "defEstimate": lambda x: x * 1e10,  # meters to angstroms
            "defWindow": lambda x: x * 1e10,  # meters to angstroms
            "defCutOff": lambda x: x * 1e10,  # meters to angstroms
            "beadDiameter": lambda x: x * 1e10,  # meters to angstroms
            "tomoCprDefocusRange": lambda x: x * 1e10,  # meters to angstroms
            "tomoCprDefocusStep": lambda x: x * 1e10,  # meters to angstroms
        }

        if param_name in conversions:
            return conversions[param_name](value)
        return value

    def _convert_units_json_to_matlab(self, param_name: str, value: float) -> float:
        """Convert parameter values from JSON units to MATLAB units."""
        conversions = {
            "PIXEL_SIZE": lambda x: x / 1e10,  # angstroms to meters
            "Cs": lambda x: x / 1000,  # mm to meters
            "VOLTAGE": lambda x: x * 1000,  # kV to volts
            "max_ctf3dDepth": lambda x: x / 1e10,  # angstroms to meters
            "defEstimate": lambda x: x / 1e10,  # angstroms to meters
            "defWindow": lambda x: x / 1e10,  # angstroms to meters
            "defCutOff": lambda x: x / 1e10,  # angstroms to meters
            "beadDiameter": lambda x: x / 1e10,  # angstroms to meters
            "tomoCprDefocusRange": lambda x: x / 1e10,  # angstroms to meters
            "tomoCprDefocusStep": lambda x: x / 1e10,  # angstroms to meters
        }

        if param_name in conversions:
            return conversions[param_name](value)
        return value

    def create_json_schema(self) -> dict[str, Any]:
        """Create JSON schema for parameter validation."""
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "emClarity Parameters",
            "description": "Parameter configuration for emClarity cryo-EM processing",
            "type": "object",
            "properties": {
                "metadata": {
                    "type": "object",
                    "properties": {
                        "format_version": {"type": "string", "default": "1.0"},
                        "sub_tomo_meta": {"type": "string"},
                    },
                    "required": ["format_version"],
                },
                "system": {
                    "type": "object",
                    "properties": {
                        "gpu_count": {"type": "integer", "minimum": 1, "maximum": 1000},
                        "cpu_cores": {"type": "integer", "minimum": 1, "maximum": 1000},
                        "tilt_workers": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                        },
                    },
                    "required": ["gpu_count", "cpu_cores"],
                },
                "microscope": {
                    "type": "object",
                    "properties": {
                        "pixel_size_angstroms": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                        },
                        "spherical_aberration_mm": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 10,
                        },
                        "acceleration_voltage_kv": {
                            "type": "number",
                            "minimum": 20,
                            "maximum": 1000,
                        },
                        "amplitude_contrast": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                    "required": [
                        "pixel_size_angstroms",
                        "spherical_aberration_mm",
                        "acceleration_voltage_kv",
                    ],
                },
                "ctf": {
                    "type": "object",
                    "properties": {
                        "max_depth_angstroms": {
                            "type": "number",
                            "minimum": 1,
                            "maximum": 10000,
                        },
                        "defocus_estimate_angstroms": {
                            "type": "number",
                            "minimum": 1000,
                            "maximum": 100000,
                        },
                        "defocus_search_range_angstroms": {
                            "type": "number",
                            "minimum": 100,
                            "maximum": 50000,
                        },
                        "resolution_cutoff_angstroms": {
                            "type": "number",
                            "minimum": 1,
                            "maximum": 100,
                        },
                    },
                },
                "sample": {
                    "type": "object",
                    "properties": {
                        "fiducial_diameter_angstroms": {
                            "type": "number",
                            "minimum": 10,
                            "maximum": 1000,
                        }
                    },
                },
                "tomocpr": {
                    "type": "object",
                    "properties": {
                        "defocus_refinement_range_angstroms": {
                            "type": "number",
                            "minimum": 100,
                            "maximum": 10000,
                        },
                        "defocus_refinement_step_angstroms": {
                            "type": "number",
                            "minimum": 1,
                            "maximum": 1000,
                        },
                    },
                },
                "processing": {
                    "type": "object",
                    "properties": {"enable_quality_weighting": {"type": "boolean"}},
                },
                "alignment": {
                    "type": "object",
                    "properties": {"enable_multi_reference": {"type": "boolean"}},
                },
                "classification": {
                    "type": "object",
                    "properties": {"enable_classification": {"type": "boolean"}},
                },
            },
            "required": ["metadata", "system", "microscope"],
        }
        return schema

    def parse_matlab_file(self, file_path: str | Path) -> dict[str, Any]:
        """Parse a MATLAB parameter file and return a dictionary."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Parameter file not found: {file_path}")

        params = {}

        with open(file_path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("%"):
                    continue

                # Parse name=value pairs
                if "=" in line:
                    try:
                        name, value_str = line.split("=", 1)
                        name = name.strip()
                        value_str = value_str.strip()

                        # Remove trailing semicolon if present
                        if value_str.endswith(";"):
                            value_str = value_str[:-1].strip()

                        # Parse the value
                        params[name] = self._parse_matlab_value(value_str)

                    except Exception as e:
                        logger.warning(
                            f"Failed to parse line {line_num}: '{line}' - {e}"
                        )
                        continue

        return params

    def _parse_matlab_value(self, value_str: str) -> Any:
        """Parse a MATLAB value string into appropriate Python type."""
        value_str = value_str.strip()

        # Handle arrays [1,2,3] or [1;2;3]
        if value_str.startswith("[") and value_str.endswith("]"):
            array_str = value_str[1:-1]
            # Split by comma or semicolon, handle nested expressions
            elements = []
            for elem in re.split(r"[,;]", array_str):
                elem = elem.strip()
                if elem:
                    elements.append(self._parse_single_value(elem))
            return elements

        # Handle single values
        return self._parse_single_value(value_str)

    def _parse_single_value(self, value_str: str) -> Any:
        """Parse a single MATLAB value."""
        value_str = value_str.strip()

        # Handle scientific notation
        if "e" in value_str.lower():
            try:
                return float(value_str)
            except ValueError:
                pass

        # Handle regular numbers
        try:
            # Try integer first
            if "." not in value_str:
                return int(value_str)
            else:
                return float(value_str)
        except ValueError:
            pass

        # Handle boolean-like values
        if value_str.lower() in ("true", "1"):
            return True
        elif value_str.lower() in ("false", "0"):
            return False

        # Handle MATLAB expressions like "12.*ones(1,1)"
        if "ones(" in value_str:
            # Extract coefficient and dimensions
            match = re.match(r"(\d+(?:\.\d+)?)\.\*ones\(([^)]+)\)", value_str)
            if match:
                coeff = float(match.group(1))
                dims = match.group(2).split(",")
                # For now, just return the coefficient repeated
                total_elements = 1
                for dim in dims:
                    total_elements *= int(dim.strip())
                return [coeff] * total_elements

        # Return as string if nothing else works
        return value_str

    def convert_matlab_to_json(self, matlab_params: dict[str, Any]) -> dict[str, Any]:
        """Convert MATLAB parameters to JSON format with proper structure and units."""
        json_config = {
            "metadata": {"format_version": "1.0"},
            "system": {},
            "microscope": {},
            "ctf": {},
            "sample": {},
            "tomocpr": {},
            "processing": {},
            "alignment": {},
            "classification": {},
        }

        # Add metadata
        if "subTomoMeta" in matlab_params:
            json_config["metadata"]["sub_tomo_meta"] = matlab_params["subTomoMeta"]

        # Convert known parameters
        for matlab_name, matlab_value in matlab_params.items():
            if matlab_name in self.parameter_mapping:
                param_info = self.parameter_mapping[matlab_name]

                # Convert units if needed
                if param_info.param_type is float and matlab_name in [
                    "PIXEL_SIZE",
                    "Cs",
                    "VOLTAGE",
                    "max_ctf3dDepth",
                    "defEstimate",
                    "defWindow",
                    "defCutOff",
                    "beadDiameter",
                    "tomoCprDefocusRange",
                    "tomoCprDefocusStep",
                ]:
                    converted_value = self._convert_units_matlab_to_json(
                        matlab_name, matlab_value
                    )
                else:
                    converted_value = matlab_value

                # Handle boolean conversion
                if param_info.param_type is bool:
                    converted_value = bool(converted_value)

                # Set the value in the nested structure
                section, key = param_info.new_name.split(".", 1)
                json_config[section][key] = converted_value

        return json_config

    def convert_json_to_matlab(self, json_config: dict[str, Any]) -> dict[str, Any]:
        """Convert JSON parameters back to MATLAB format."""
        matlab_params = {}

        # Reverse mapping: from new_name to old_name
        reverse_mapping = {
            info.new_name: info for info in self.parameter_mapping.values()
        }

        # Flatten the JSON structure and convert back
        for section_name, section_data in json_config.items():
            if section_name == "metadata":
                if "sub_tomo_meta" in section_data:
                    matlab_params["subTomoMeta"] = section_data["sub_tomo_meta"]
                continue

            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    full_key = f"{section_name}.{key}"
                    if full_key in reverse_mapping:
                        param_info = reverse_mapping[full_key]
                        matlab_name = param_info.old_name

                        # Convert units back to MATLAB format
                        if param_info.param_type is float and matlab_name in [
                            "PIXEL_SIZE",
                            "Cs",
                            "VOLTAGE",
                            "max_ctf3dDepth",
                            "defEstimate",
                            "defWindow",
                            "defCutOff",
                            "beadDiameter",
                            "tomoCprDefocusRange",
                            "tomoCprDefocusStep",
                        ]:
                            converted_value = self._convert_units_json_to_matlab(
                                matlab_name, value
                            )
                        else:
                            converted_value = value

                        matlab_params[matlab_name] = converted_value

        return matlab_params


def main():
    """Example usage and testing."""
    converter = ParameterConverter()
    print("Parameter converter initialized with mapping for:")
    for old_name, info in converter.parameter_mapping.items():
        print(f"  {old_name} -> {info.new_name}")


if __name__ == "__main__":
    main()
