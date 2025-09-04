#!/usr/bin/env python3
"""
Test script to demonstrate the enhanced emClarity GUI with parameter configuration.
"""

import sys
from pathlib import Path

# Add the python package root to path for proper imports
python_root = Path(__file__).parent.parent.parent
if str(python_root) not in sys.path:
    sys.path.insert(0, str(python_root))


from gui.parameters import EmClarityParameters


def test_parameter_system():
    """Test the parameter system functionality."""
    print("Testing emClarity Parameter System")
    print("=" * 50)

    # Create parameter manager
    param_manager = EmClarityParameters()

    # Show available tabs
    print("Available parameter tabs:")
    for tab_name, params in param_manager.parameters.items():
        print(f"  {tab_name}: {len(params)} parameters")

    print("\nTesting parameter validation...")

    # Test with some example values
    test_values = {
        "subTomoMeta": "test_project",
        "nGPUs": 2,
        "nCpuCores": 8,
        "PIXEL_SIZE": 2.5e-10,
        "Cs": 2.7e-3,
        "VOLTAGE": 300e3,
        "AMPCONT": 0.04,
        "symmetry": "C6",
        "particleRadius": [100, 100, 80],
        "Ali_mRadius": [150, 150, 120],
    }

    # Validate parameters
    errors = param_manager.validate_parameters(test_values)
    if errors:
        print("Validation errors found:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("All parameters valid!")

    # Create parameter file
    print("\nGenerating parameter file...")
    content, filename = param_manager.create_parameter_file(test_values, "test")

    print(f"Generated file: {filename}")
    print("\nFirst 20 lines of parameter file:")
    print("-" * 40)
    lines = content.split("\n")
    for i, line in enumerate(lines[:20]):
        print(f"{i + 1:2d}: {line}")

    if len(lines) > 20:
        print("...")
        print(f"    (total {len(lines)} lines)")


def show_parameter_info():
    """Show detailed parameter information."""
    param_manager = EmClarityParameters()

    print("\nDetailed Parameter Information")
    print("=" * 50)

    for tab_name, params in param_manager.parameters.items():
        print(f"\n{tab_name} Parameters:")
        print("-" * (len(tab_name) + 12))

        for param in params:
            print(f"  {param.display_name} ({param.name})")
            print(f"    Type: {param.param_type}")
            if param.unit:
                print(f"    Unit: {param.unit}")
            if param.default is not None:
                print(f"    Default: {param.default}")
            if param.required:
                print("    Required: Yes")
            if param.min_value is not None or param.max_value is not None:
                range_str = "    Range: "
                if param.min_value is not None:
                    range_str += f"{param.min_value}"
                else:
                    range_str += "-∞"
                range_str += " to "
                if param.max_value is not None:
                    range_str += f"{param.max_value}"
                else:
                    range_str += "∞"
                print(range_str)
            print(f"    Description: {param.description}")
            print()


if __name__ == "__main__":
    print("emClarity GUI Parameter System Test")
    print("This demonstrates the parameter configuration functionality")
    print()

    try:
        test_parameter_system()
        show_parameter_info()

        print("\n" + "=" * 50)
        print("Parameter system test completed successfully!")
        print("You can now run 'python main.py' to see the full GUI")

    except Exception as e:
        print(f"Error during test: {e}")
        import traceback

        traceback.print_exc()
