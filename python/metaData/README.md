# emClarity Python metaData Module

This directory contains Python conversions of emClarity's metadata handling functionality, originally found in the MATLAB `metaData/` directory.

## Purpose

The metaData module handles parameter parsing, project metadata management, and configuration file processing for emClarity workflows.

## Modules

### emc_parameter_converter.py

**Original MATLAB equivalent**: `BH_parseParameterFile.m`

Provides bidirectional conversion between MATLAB parameter files (.m) and modern JSON parameter files (.json) with improved naming conventions and clear units.

#### Key Features:
- **Bidirectional conversion**: MATLAB ↔ JSON formats
- **Unit conversion**: Automatic conversion from scientific notation to readable units
- **Type validation**: Proper handling of integers, floats, booleans, and arrays
- **JSON schema validation**: Ensures parameter correctness
- **Modernized naming**: Clear, descriptive parameter names with units

#### Usage:

```python
from emc_parameter_converter import ParameterConverter

# Initialize converter
converter = ParameterConverter()

# Parse MATLAB parameter file
matlab_params = converter.parse_matlab_file("param.m")

# Convert to JSON format with modern naming and units
json_config = converter.convert_matlab_to_json(matlab_params)

# Convert back to MATLAB format (for backward compatibility)
matlab_params_back = converter.convert_json_to_matlab(json_config)

# Validate JSON parameters against schema
schema = converter.create_json_schema()
# Use with jsonschema.validate(json_config, schema)
```

#### Parameter Naming Modernization:

**System Parameters:**
- `nGPUs` → `system.gpu_count`
- `nCpuCores` → `system.cpu_cores`

**Microscope Parameters (with unit conversions):**
- `PIXEL_SIZE=2.50e-10` → `microscope.pixel_size_angstroms` (2.5)
- `Cs=2.7e-3` → `microscope.spherical_aberration_mm` (2.7)
- `VOLTAGE=300e3` → `microscope.acceleration_voltage_kv` (300.0)

**CTF Parameters (all in angstroms):**
- `defEstimate=3.5e-6` → `ctf.defocus_estimate_angstroms` (35000.0)
- `max_ctf3dDepth=100e-9` → `ctf.max_depth_angstroms` (1000.0)

**Boolean Parameters:**
- `flgClassify` → `classification.enable_classification`
- `flgQualityWeight` → `processing.enable_quality_weighting`

## Testing

Unit tests are located in `tests/test_emc_parameter_converter.py`. Run tests with:

```bash
cd metaData/tests
python test_emc_parameter_converter.py
```

All tests include:
- Unit conversion validation
- Round-trip conversion testing
- JSON schema validation
- Parameter mapping verification

## Dependencies

- `json` (standard library)
- `re` (standard library) 
- `pathlib` (standard library)
- `jsonschema` (for validation)

## JSON Schema Structure

The JSON format organizes parameters into logical sections:

```json
{
  "metadata": { "format_version": "1.0", "sub_tomo_meta": "..." },
  "system": { "gpu_count": 4, "cpu_cores": 16 },
  "microscope": { "pixel_size_angstroms": 2.5, ... },
  "ctf": { "defocus_estimate_angstroms": 35000.0, ... },
  "sample": { "fiducial_diameter_angstroms": 100.0 },
  "processing": { "enable_quality_weighting": false },
  "alignment": { "enable_multi_reference": false },
  "classification": { "enable_classification": false }
}
```

## Future Development

This module serves as the foundation for parameter management in the emClarity Python conversion. Future modules in this directory will handle:

- Project metadata management
- Geometry calculations
- Alignment parameter handling
- Classification metadata
