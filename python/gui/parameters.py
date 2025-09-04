"""
emClarity parameter definitions and management.

This module loads parameter definitions from the shared JSON configuration
and provides the EmClarityParameters class for the GUI.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from parameter_loader import parameter_config


@dataclass
class Parameter:
    """Definition of a single emClarity parameter."""

    name: str
    display_name: str
    param_type: str  # 'string', 'int', 'float', 'bool', 'choice', 'vector', 'file'
    description: str
    default: Any = None
    choices: Optional[List[str]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    required: bool = False
    vector_size: Optional[int] = None  # For vector parameters like [x,y,z]
    vector_bounds: Optional[List[tuple]] = (
        None  # Per-element bounds [(min1,max1), (min2,max2), ...]
    )
    unit: Optional[str] = None  # e.g., "Angstrom", "meters", "volts"


class EmClarityParameters:
    """Manages all emClarity parameters organized by functional category."""

    def __init__(self):
        self.parameters = self._load_from_config()

    def _load_from_config(self) -> Dict[str, List[Parameter]]:
        """Load parameters from the JSON configuration file."""
        parameters_by_category = {}

        for category in parameter_config.get_categories():
            category_params = parameter_config.get_parameters_by_category(category)
            parameters_by_category[category] = []

            for param_config in category_params:
                # Convert ParameterConfig to Parameter for compatibility
                param = Parameter(
                    name=param_config.name,
                    display_name=param_config.display_name,
                    param_type=param_config.param_type,
                    description=param_config.description,
                    default=param_config.get_gui_default(),
                    choices=param_config.choices,
                    min_value=param_config.get_gui_min(),
                    max_value=param_config.get_gui_max(),
                    required=param_config.required,
                    vector_size=param_config.vector_size,
                    vector_bounds=param_config.vector_bounds,
                    unit=param_config.gui_unit,
                )
                parameters_by_category[category].append(param)

        return parameters_by_category

    def get_parameters_for_tab(self, tab_name: str) -> List[Parameter]:
        """Get parameters for a specific tab/category."""
        return self.parameters.get(tab_name, [])

    def get_all_parameters(self) -> Dict[str, List[Parameter]]:
        """Get all parameters organized by category."""
        return self.parameters

    def get_parameter_by_name(self, name: str) -> Optional[Parameter]:
        """Get a specific parameter by name."""
        for category_params in self.parameters.values():
            for param in category_params:
                if param.name == name:
                    return param
        return None

    def generate_parameter_file(self, values: Dict[str, Any], output_path: str):
        """Generate a MATLAB parameter file from GUI values."""
        content = parameter_config.generate_parameter_file_content(values)

        with open(output_path, "w") as f:
            f.write(content)
