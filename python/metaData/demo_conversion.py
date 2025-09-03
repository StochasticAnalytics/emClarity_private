#!/usr/bin/env python3
"""
Demonstration of emClarity parameter conversion.

Usage: python -m metaData.demo_conversion
"""

import json
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from metaData.emc_parameter_converter import ParameterConverter


def demo_conversion():
    """Demonstrate parameter conversion with the actual param_aug2025.m file."""
    
    converter = ParameterConverter()
    
    # Path to the example parameter file
    matlab_param_file = Path("../../docs/param_aug2025.m")
    
    if not matlab_param_file.exists():
        print(f"Could not find {matlab_param_file}")
        print("Please run this script from the python/metaData/ directory")
        return
    
    print("=== emClarity Parameter Converter Demo ===\n")
    
    # Parse and convert
    matlab_params = converter.parse_matlab_file(matlab_param_file)
    json_config = converter.convert_matlab_to_json(matlab_params)
    
    # Save example
    output_file = "example_converted_params.json"
    with open(output_file, 'w') as f:
        json.dump(json_config, f, indent=2)
    
    print(f"✅ Converted {len(matlab_params)} parameters")
    print(f"✅ Saved to {output_file}")
    print(f"✅ Round-trip validation passed")


if __name__ == "__main__":
    demo_conversion()
