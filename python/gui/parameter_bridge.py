"""
GUI Parameter Bridge.

This module provides a simplified interface for the GUI to access
the unified parameter management system.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add the python package root to path for proper imports
python_root = Path(__file__).parent.parent
if str(python_root) not in sys.path:
    sys.path.insert(0, str(python_root))

from parameters import (
    ParameterDefinition,
    get_parameter_manager,
)


class GUIParameterManager:
    """
    Simplified parameter manager interface for GUI use.

    This wraps the UnifiedParameterManager to provide GUI-specific
    convenience methods while maintaining access to the full functionality.
    """

    def __init__(self):
        self.manager = get_parameter_manager()

    def get_parameter_for_gui(self, name: str) -> Optional[ParameterDefinition]:
        """Get parameter definition with GUI-friendly access."""
        return self.manager.get_parameter_config(name)

    def get_categories(self) -> List[str]:
        """Get list of all parameter categories."""
        all_params = self.manager.get_all_gui_parameters()
        return list(set(param.category for param in all_params.values()))

    def get_parameters_by_category(
        self, category: str
    ) -> Dict[str, ParameterDefinition]:
        """Get all parameters in a category."""
        return self.manager.get_parameters_by_category(category)

    def load_from_matlab_file(self, matlab_file_path: str) -> Dict[str, Any]:
        """Load parameters from MATLAB file and convert to JSON format."""
        matlab_params = self.manager.parse_matlab_file(matlab_file_path)
        return self.manager.convert_matlab_to_json(matlab_params)

    def save_to_matlab_file(self, json_config: Dict[str, Any], output_path: str):
        """Convert JSON config to MATLAB format and save."""
        matlab_params = self.manager.convert_json_to_matlab(json_config)

        with open(output_path, "w") as f:
            f.write("% emClarity parameter file\n")
            f.write("% Generated from GUI configuration\n\n")

            for name, value in matlab_params.items():
                if isinstance(value, str):
                    f.write(f"{name} = '{value}';\n")
                elif isinstance(value, (list, tuple)):
                    value_str = ", ".join(str(v) for v in value)
                    f.write(f"{name} = [{value_str}];\n")
                else:
                    f.write(f"{name} = {value};\n")

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate a configuration and return any errors."""
        return self.manager.validate_all_parameters(config)

    def get_default_config(self) -> Dict[str, Any]:
        """Get a configuration with all default values."""
        config = {}
        all_params = self.manager.get_all_gui_parameters()

        for json_name, param_def in all_params.items():
            if param_def.default_value is not None:
                # Create nested structure
                keys = json_name.split(".")
                current = config
                for key in keys[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[keys[-1]] = param_def.default_value

        return config


# Singleton for GUI use
_gui_manager = None


def get_gui_parameter_manager() -> GUIParameterManager:
    """Get singleton GUI parameter manager."""
    global _gui_manager
    if _gui_manager is None:
        _gui_manager = GUIParameterManager()
    return _gui_manager
