"""
Unit tests for emClarity Parameter Converter

Tests parameter conversion between MATLAB and JSON formats,
validation, and unit conversions.
"""

import json
import os
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Use relative import - proper Python package approach
from ..emc_parameter_converter import ParameterConverter, ParameterInfo


class TestParameterConverter(unittest.TestCase):
    """Test cases for the ParameterConverter class."""

    def setUp(self):
        """Set up test fixtures."""
        self.converter = ParameterConverter()

    def test_unit_conversions_matlab_to_json(self):
        """Test unit conversions from MATLAB to JSON format."""
        # Test pixel size: 2.50e-10 meters → 2.5 angstroms
        result = self.converter._convert_units_matlab_to_json("PIXEL_SIZE", 2.50e-10)
        self.assertAlmostEqual(result, 2.5, places=6)

        # Test Cs: 2.7e-3 meters → 2.7 mm
        result = self.converter._convert_units_matlab_to_json("Cs", 2.7e-3)
        self.assertAlmostEqual(result, 2.7, places=6)

        # Test voltage: 300000 volts → 300 kV
        result = self.converter._convert_units_matlab_to_json("VOLTAGE", 300000)
        self.assertAlmostEqual(result, 300.0, places=6)

        # Test defocus: 3.5e-6 meters → 35000 angstroms
        result = self.converter._convert_units_matlab_to_json("defEstimate", 3.5e-6)
        self.assertAlmostEqual(result, 35000.0, places=6)

    def test_unit_conversions_json_to_matlab(self):
        """Test unit conversions from JSON to MATLAB format."""
        # Test pixel size: 2.5 angstroms → 2.50e-10 meters
        result = self.converter._convert_units_json_to_matlab("PIXEL_SIZE", 2.5)
        self.assertAlmostEqual(result, 2.50e-10, places=16)

        # Test Cs: 2.7 mm → 2.7e-3 meters
        result = self.converter._convert_units_json_to_matlab("Cs", 2.7)
        self.assertAlmostEqual(result, 2.7e-3, places=9)

        # Test voltage: 300 kV → 300000 volts
        result = self.converter._convert_units_json_to_matlab("VOLTAGE", 300.0)
        self.assertAlmostEqual(result, 300000.0, places=6)

    def test_parameter_mapping(self):
        """Test parameter mapping structure."""
        mapping = self.converter.parameter_mapping

        # Test that required parameters are present
        self.assertIn("nGPUs", mapping)
        self.assertIn("PIXEL_SIZE", mapping)
        self.assertIn("Cs", mapping)

        # Test parameter info structure
        pixel_info = mapping["PIXEL_SIZE"]
        self.assertEqual(pixel_info.old_name, "PIXEL_SIZE")
        self.assertEqual(pixel_info.new_name, "microscope.pixel_size_angstroms")
        self.assertEqual(pixel_info.units, "angstroms")
        self.assertTrue(pixel_info.required)

    def test_json_schema_creation(self):
        """Test JSON schema generation."""
        schema = self.converter.create_json_schema()

        # Test schema structure
        self.assertIn("$schema", schema)
        self.assertIn("properties", schema)
        self.assertIn("required", schema)

        # Test required sections
        required_sections = schema["required"]
        self.assertIn("metadata", required_sections)
        self.assertIn("system", required_sections)
        self.assertIn("microscope", required_sections)

        # Test microscope properties
        microscope_props = schema["properties"]["microscope"]["properties"]
        self.assertIn("pixel_size_angstroms", microscope_props)
        self.assertIn("spherical_aberration_mm", microscope_props)
        self.assertIn("acceleration_voltage_kv", microscope_props)

    def test_example_conversion(self):
        """Test conversion of example parameter values."""
        # Example MATLAB values from param_aug2025.m
        matlab_params = {
            "PIXEL_SIZE": 2.50e-10,  # meters
            "Cs": 2.7e-3,  # meters
            "VOLTAGE": 300e3,  # volts
            "nGPUs": 4,  # integer
            "nCpuCores": 16,  # integer
            "max_ctf3dDepth": 100e-9,  # meters
            "defEstimate": 3.5e-6,  # meters
            "flgQualityWeight": 0,  # boolean (0/1)
        }

        # Expected JSON values with proper units
        expected_json_values = {
            "microscope.pixel_size_angstroms": 2.5,
            "microscope.spherical_aberration_mm": 2.7,
            "microscope.acceleration_voltage_kv": 300.0,
            "system.gpu_count": 4,
            "system.cpu_cores": 16,
            "ctf.max_depth_angstroms": 1000.0,  # 100e-9 * 1e10
            "ctf.defocus_estimate_angstroms": 35000.0,  # 3.5e-6 * 1e10
            "processing.enable_quality_weighting": False,
        }

        # Test individual conversions
        for matlab_name, matlab_value in matlab_params.items():
            if matlab_name in self.converter.parameter_mapping:
                param_info = self.converter.parameter_mapping[matlab_name]

                if param_info.param_type == float and matlab_name in [
                    "PIXEL_SIZE",
                    "Cs",
                    "VOLTAGE",
                    "max_ctf3dDepth",
                    "defEstimate",
                ]:
                    converted_value = self.converter._convert_units_matlab_to_json(
                        matlab_name, matlab_value
                    )
                    expected_value = expected_json_values[param_info.new_name]
                    self.assertAlmostEqual(
                        converted_value,
                        expected_value,
                        places=6,
                        msg=f"Failed for {matlab_name}: expected {expected_value}, got {converted_value}",
                    )


def create_sample_json_config():
    """Create a sample JSON configuration file for testing."""
    sample_config = {
        "metadata": {
            "format_version": "1.0",
            "sub_tomo_meta": "full_enchilada_2_1_branch_10",
        },
        "system": {"gpu_count": 4, "cpu_cores": 16, "tilt_workers": 4},
        "microscope": {
            "pixel_size_angstroms": 2.5,
            "spherical_aberration_mm": 2.7,
            "acceleration_voltage_kv": 300.0,
            "amplitude_contrast": 0.04,
        },
        "ctf": {
            "max_depth_angstroms": 1000.0,
            "defocus_estimate_angstroms": 35000.0,
            "defocus_search_range_angstroms": 17500.0,
            "resolution_cutoff_angstroms": 6.0,
        },
        "sample": {"fiducial_diameter_angstroms": 100.0},
        "tomocpr": {
            "defocus_refinement_range_angstroms": 5000.0,
            "defocus_refinement_step_angstroms": 200.0,
        },
        "processing": {"enable_quality_weighting": False},
        "alignment": {"enable_multi_reference": False},
        "classification": {"enable_classification": False},
    }
    return sample_config


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)

    # Also create a sample JSON file for demonstration
    sample_config = create_sample_json_config()

    with open("sample_emclarity_params.json", "w") as f:
        json.dump(sample_config, f, indent=2)

    print("\nSample JSON configuration created: sample_emclarity_params.json")
    print("This demonstrates the new parameter format with proper units.")
