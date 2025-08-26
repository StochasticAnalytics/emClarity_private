"""
Parameter configuration loader for emClarity GUI.

This module loads parameter definitions from the shared JSON configuration
file and provides utility functions for converting between SI units and GUI units.
"""

import json
import os
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass


@dataclass
class ParameterConfig:
    """Configuration for a single parameter loaded from JSON."""
    name: str
    display_name: str
    description: str
    param_type: str
    si_default: Any
    si_min: Optional[float] = None
    si_max: Optional[float] = None
    gui_unit: str = ""
    gui_scaling_factor: float = 1.0
    display_decimals: int = 6
    choices: Optional[List[str]] = None
    vector_size: Optional[int] = None
    vector_bounds: Optional[List[List[float]]] = None
    required: bool = False
    category: str = "General"
    
    def to_gui_value(self, si_value: Union[float, List[float]]) -> Union[float, List[float]]:
        """Convert SI value to GUI display value."""
        if isinstance(si_value, list):
            return [v * self.gui_scaling_factor for v in si_value]
        return si_value * self.gui_scaling_factor
    
    def to_si_value(self, gui_value: Union[float, List[float]]) -> Union[float, List[float]]:
        """Convert GUI display value to SI value."""
        if isinstance(gui_value, list):
            return [v / self.gui_scaling_factor for v in gui_value]
        return gui_value / self.gui_scaling_factor
    
    def get_gui_default(self) -> Any:
        """Get the default value in GUI units."""
        if self.param_type == "choice" or self.param_type == "bool":
            return self.si_default
        return self.to_gui_value(self.si_default)
    
    def get_gui_min(self) -> Optional[float]:
        """Get minimum value in GUI units."""
        if self.si_min is not None:
            return self.to_gui_value(self.si_min)
        return None
    
    def get_gui_max(self) -> Optional[float]:
        """Get maximum value in GUI units."""
        if self.si_max is not None:
            return self.to_gui_value(self.si_max)
        return None


class ParameterConfigLoader:
    """Loads and manages parameter configurations from JSON."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the parameter config loader.
        
        Args:
            config_path: Path to the JSON config file. If None, uses default location.
        """
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'parameter_config.json')
        
        self.config_path = config_path
        self.config_data = self._load_config()
        self.parameters = self._parse_parameters()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load the JSON configuration file."""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Parameter configuration file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
    
    def _parse_parameters(self) -> Dict[str, ParameterConfig]:
        """Parse parameter definitions from the loaded config."""
        parameters = {}
        
        for name, config in self.config_data.get('parameters', {}).items():
            param_config = ParameterConfig(
                name=name,
                display_name=config.get('display_name', name),
                description=config.get('description', ''),
                param_type=config.get('param_type', 'string'),
                si_default=config.get('si_default'),
                si_min=config.get('si_min'),
                si_max=config.get('si_max'),
                gui_unit=config.get('gui_unit', ''),
                gui_scaling_factor=config.get('gui_scaling_factor', 1.0),
                display_decimals=config.get('display_decimals', 6),
                choices=config.get('choices'),
                vector_size=config.get('vector_size'),
                vector_bounds=config.get('vector_bounds'),
                required=config.get('required', False),
                category=config.get('category', 'General')
            )
            parameters[name] = param_config
        
        return parameters
    
    def get_parameter(self, name: str) -> Optional[ParameterConfig]:
        """Get parameter configuration by name."""
        return self.parameters.get(name)
    
    def get_parameters_by_category(self, category: str) -> List[ParameterConfig]:
        """Get all parameters for a specific category."""
        return [param for param in self.parameters.values() if param.category == category]
    
    def get_categories(self) -> List[str]:
        """Get list of all categories."""
        return self.config_data.get('categories', [])
    
    def get_all_parameters(self) -> Dict[str, ParameterConfig]:
        """Get all parameter configurations."""
        return self.parameters.copy()
    
    def generate_parameter_file_content(self, values: Dict[str, Any]) -> str:
        """Generate MATLAB parameter file content from GUI values.
        
        Args:
            values: Dictionary of parameter names to GUI values
            
        Returns:
            String content for the MATLAB parameter file
        """
        lines = []
        lines.append("% emClarity parameter file generated by GUI")
        lines.append("% Values are in SI units for MATLAB compatibility")
        lines.append("")
        
        # Group by category
        by_category = {}
        for name, value in values.items():
            param_config = self.get_parameter(name)
            if param_config:
                category = param_config.category
                if category not in by_category:
                    by_category[category] = []
                by_category[category].append((name, value, param_config))
        
        # Write parameters by category
        for category in self.get_categories():
            if category in by_category:
                lines.append(f"% {category} Parameters")
                for name, gui_value, param_config in by_category[category]:
                    # Convert GUI value to SI for MATLAB
                    if param_config.param_type in ["choice", "bool"]:
                        si_value = gui_value
                    else:
                        si_value = param_config.to_si_value(gui_value)
                    
                    # Format the value
                    if param_config.param_type == "vector":
                        if isinstance(si_value, list):
                            value_str = f"[{', '.join(map(str, si_value))}]"
                        else:
                            value_str = str(si_value)
                    elif param_config.param_type == "bool":
                        value_str = "true" if si_value else "false"
                    else:
                        value_str = str(si_value)
                    
                    lines.append(f"{name}={value_str}")
                lines.append("")
        
        return '\n'.join(lines)


# Global instance for easy access
parameter_config = ParameterConfigLoader()
