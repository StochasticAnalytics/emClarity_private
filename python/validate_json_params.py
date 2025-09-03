#!/usr/bin/env python3
"""
JSON Schema Validator for emClarity Parameters

This script validates emClarity JSON parameter files against the schema.
"""

import json
import jsonschema
from jsonschema import validate, ValidationError
from metaData.emc_parameter_converter import ParameterConverter


def validate_json_parameters(json_file_path: str):
    """Validate a JSON parameter file against the emClarity schema."""
    
    converter = ParameterConverter()
    schema = converter.create_json_schema()
    
    try:
        # Load the JSON file
        with open(json_file_path, 'r') as f:
            config = json.load(f)
        
        # Validate against schema
        validate(instance=config, schema=schema)
        print(f"✓ {json_file_path} is valid according to the emClarity schema")
        
        # Additional checks
        print("\nValidation details:")
        
        # Check required parameters
        required_microscope = schema['properties']['microscope']['required']
        microscope_data = config.get('microscope', {})
        
        for req_param in required_microscope:
            if req_param in microscope_data:
                value = microscope_data[req_param]
                print(f"  ✓ {req_param}: {value}")
            else:
                print(f"  ✗ Missing required parameter: {req_param}")
        
        return True
        
    except FileNotFoundError:
        print(f"✗ File not found: {json_file_path}")
        return False
        
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON format: {e}")
        return False
        
    except ValidationError as e:
        print(f"✗ Schema validation failed: {e.message}")
        print(f"  Failed at: {' -> '.join(str(p) for p in e.absolute_path)}")
        return False
        
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


def main():
    """Main validation function."""
    print("=== emClarity JSON Parameter Validator ===\n")
    
    # Validate the converted file
    json_file = "converted_params.json"
    validate_json_parameters(json_file)
    
    # Also validate the sample file from tests
    sample_file = "sample_emclarity_params.json"
    if Path(sample_file).exists():
        print(f"\n" + "="*50)
        validate_json_parameters(sample_file)


if __name__ == "__main__":
    from pathlib import Path
    main()
