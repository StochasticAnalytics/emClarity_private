#!/usr/bin/env python3
"""
Proof-of-concept demonstration of emClarity parameter conversion.

This script shows how to convert between MATLAB and JSON parameter formats.
"""

import json
import sys
from pathlib import Path

# Import our converter
from metaData.emc_parameter_converter import ParameterConverter


def demo_conversion():
    """Demonstrate parameter conversion with the actual param_aug2025.m file."""
    
    converter = ParameterConverter()
    
    # Path to the example parameter file
    matlab_param_file = Path("../docs/param_aug2025.m")
    
    if not matlab_param_file.exists():
        print(f"Could not find {matlab_param_file}")
        print("Please run this script from the python/ directory")
        return
    
    print("=== emClarity Parameter Converter Demo ===\n")
    
    # Step 1: Parse the MATLAB file
    print("1. Parsing MATLAB parameter file...")
    try:
        matlab_params = converter.parse_matlab_file(matlab_param_file)
        print(f"   Parsed {len(matlab_params)} parameters")
        
        # Show some examples of parsed values
        examples = ['PIXEL_SIZE', 'Cs', 'VOLTAGE', 'nGPUs', 'max_ctf3dDepth']
        for param in examples:
            if param in matlab_params:
                print(f"   {param} = {matlab_params[param]}")
    
    except Exception as e:
        print(f"   Error parsing MATLAB file: {e}")
        return
    
    # Step 2: Convert to JSON format
    print("\n2. Converting to JSON format with proper units...")
    try:
        json_config = converter.convert_matlab_to_json(matlab_params)
        
        # Show the converted values with units
        print("   Converted parameters:")
        if 'microscope' in json_config:
            for key, value in json_config['microscope'].items():
                print(f"   microscope.{key} = {value}")
        
        if 'system' in json_config:
            for key, value in json_config['system'].items():
                print(f"   system.{key} = {value}")
                
        if 'ctf' in json_config:
            for key, value in json_config['ctf'].items():
                print(f"   ctf.{key} = {value}")
    
    except Exception as e:
        print(f"   Error converting to JSON: {e}")
        return
    
    # Step 3: Save JSON file
    json_output_file = "converted_params.json"
    print(f"\n3. Saving JSON configuration to {json_output_file}...")
    try:
        with open(json_output_file, 'w') as f:
            json.dump(json_config, f, indent=2)
        print(f"   JSON file saved successfully")
    except Exception as e:
        print(f"   Error saving JSON file: {e}")
        return
    
    # Step 4: Convert back to MATLAB format (round-trip test)
    print("\n4. Converting back to MATLAB format (round-trip test)...")
    try:
        matlab_params_roundtrip = converter.convert_json_to_matlab(json_config)
        
        # Compare some key values
        print("   Round-trip comparison:")
        test_params = ['PIXEL_SIZE', 'Cs', 'VOLTAGE', 'nGPUs']
        for param in test_params:
            if param in matlab_params and param in matlab_params_roundtrip:
                original = matlab_params[param]
                roundtrip = matlab_params_roundtrip[param]
                
                if isinstance(original, float):
                    diff = abs(original - roundtrip) / original if original != 0 else abs(roundtrip)
                    status = "✓" if diff < 1e-10 else "✗"
                    print(f"   {param}: {original} → {roundtrip} {status}")
                else:
                    status = "✓" if original == roundtrip else "✗"
                    print(f"   {param}: {original} → {roundtrip} {status}")
    
    except Exception as e:
        print(f"   Error in round-trip conversion: {e}")
        return
    
    # Step 5: Show JSON schema
    print("\n5. JSON Schema for validation:")
    schema = converter.create_json_schema()
    print(f"   Schema includes {len(schema['properties'])} main sections:")
    for section in schema['properties']:
        print(f"   - {section}")
    
    print("\n=== Demo completed successfully! ===")
    print(f"\nNext steps:")
    print(f"1. Review the generated {json_output_file}")
    print(f"2. Validate it against the JSON schema")
    print(f"3. Test with your own parameter files")
    print(f"4. Integrate into the emClarity GUI")


if __name__ == "__main__":
    demo_conversion()
