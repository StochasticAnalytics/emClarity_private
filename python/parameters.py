"""
Unified emClarity Parameter Management System

This module provides comprehensive parameter management for emClarity, supporting:
- MATLAB ↔ JSON conversion with backward compatibility
- GUI integration with unit conversion and validation
- Schema validation and type checking
- Extensible parameter definitions

This replaces both the GUI parameter_loader and metaData parameter_converter
with a single, unified system.
"""

import json
import re
import os
from pathlib import Path
from typing import Dict, Any, Union, List, Optional, Tuple, Type
from dataclasses import dataclass, field
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


@dataclass
class ParameterDefinition:
    """
    Complete parameter definition supporting both MATLAB conversion and GUI display.
    
    This replaces both ParameterInfo and ParameterConfig classes.
    """
    # Core identification
    matlab_name: str
    json_name: str
    display_name: str
    description: str
    
    # Type and validation
    param_type: str  # 'float', 'int', 'bool', 'string', 'choice', 'vector'
    required: bool = False
    
    # Value constraints
    default_value: Any = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    choices: Optional[List[str]] = None
    
    # GUI display configuration
    gui_unit: str = ""
    gui_scaling_factor: float = 1.0
    display_decimals: int = 6
    
    # Vector parameters
    vector_size: Optional[int] = None
    vector_bounds: Optional[List[Tuple[float, float]]] = None
    
    # Organization
    category: str = "General"
    subcategory: str = ""
    
    def to_gui_value(self, si_value: Union[float, List[float]]) -> Union[float, List[float]]:
        """Convert SI value to GUI display value."""
        if isinstance(si_value, (list, tuple)):
            return [v * self.gui_scaling_factor for v in si_value]
        return si_value * self.gui_scaling_factor
    
    def to_si_value(self, gui_value: Union[float, List[float]]) -> Union[float, List[float]]:
        """Convert GUI display value to SI value."""
        if isinstance(gui_value, (list, tuple)):
            return [v / self.gui_scaling_factor for v in gui_value]
        return gui_value / self.gui_scaling_factor
    
    def get_gui_default(self) -> Any:
        """Get the default value in GUI units."""
        if self.param_type in ("choice", "bool", "string"):
            return self.default_value
        if self.default_value is None:
            return None
        return self.to_gui_value(self.default_value)
    
    def validate_value(self, value: Any) -> Tuple[bool, str]:
        """
        Validate a value against this parameter's constraints.
        
        Returns:
            (is_valid, error_message)
        """
        if self.required and value is None:
            return False, f"Parameter {self.json_name} is required"
        
        if value is None:
            return True, ""
        
        # Type validation
        if self.param_type == "int" and not isinstance(value, int):
            try:
                value = int(value)
            except (ValueError, TypeError):
                return False, f"Parameter {self.json_name} must be an integer"
        
        elif self.param_type == "float" and not isinstance(value, (int, float)):
            try:
                value = float(value)
            except (ValueError, TypeError):
                return False, f"Parameter {self.json_name} must be a number"
        
        elif self.param_type == "bool" and not isinstance(value, bool):
            return False, f"Parameter {self.json_name} must be a boolean"
        
        elif self.param_type == "string" and not isinstance(value, str):
            return False, f"Parameter {self.json_name} must be a string"
        
        elif self.param_type == "choice":
            if self.choices and str(value) not in self.choices:
                return False, f"Parameter {self.json_name} must be one of: {', '.join(self.choices)}"
        
        # Range validation for numeric types
        if self.param_type in ("int", "float"):
            if self.min_value is not None and value < self.min_value:
                return False, f"Parameter {self.json_name} must be >= {self.min_value}"
            if self.max_value is not None and value > self.max_value:
                return False, f"Parameter {self.json_name} must be <= {self.max_value}"
        
        return True, ""


class ParameterRegistry:
    """
    Central registry of all emClarity parameters.
    
    This replaces the separate parameter mappings in both the GUI and metaData modules.
    """
    
    def __init__(self):
        self._parameters: Dict[str, ParameterDefinition] = {}
        self._matlab_lookup: Dict[str, str] = {}
        self._json_lookup: Dict[str, str] = {}
        self._load_default_parameters()
    
    def _load_default_parameters(self):
        """Load the default parameter definitions."""
        # System parameters
        self.register_parameter(ParameterDefinition(
            matlab_name="nGPUs",
            json_name="system.gpu_count",
            display_name="GPU Count",
            description="Number of GPUs to use for processing",
            param_type="int",
            required=True,
            default_value=1,
            min_value=1,
            max_value=64,
            category="System"
        ))
        
        self.register_parameter(ParameterDefinition(
            matlab_name="nCpuCores",
            json_name="system.cpu_cores", 
            display_name="CPU Cores",
            description="Number of CPU cores to use",
            param_type="int",
            required=True,
            default_value=8,
            min_value=1,
            max_value=256,
            category="System"
        ))
        
        self.register_parameter(ParameterDefinition(
            matlab_name="fastScratchDisk",
            json_name="system.fast_scratch_disk",
            display_name="Fast Scratch Disk",
            description="Path to fast temporary storage",
            param_type="string",
            required=False,
            default_value="",
            category="System"
        ))
        
        # Microscope parameters - these use SI units internally, display units for GUI
        self.register_parameter(ParameterDefinition(
            matlab_name="PIXEL_SIZE",
            json_name="microscope.pixel_size_angstroms",
            display_name="Pixel Size",
            description="Pixel size in angstroms",
            param_type="float",
            required=True,
            default_value=1.0e-10,  # SI units (meters)
            min_value=1e-12,
            max_value=100e-10,
            gui_unit="Angstrom",
            gui_scaling_factor=1e10,  # Convert meters to angstroms
            display_decimals=4,
            category="Microscope"
        ))
        
        self.register_parameter(ParameterDefinition(
            matlab_name="Cs",
            json_name="microscope.spherical_aberration_mm",
            display_name="Spherical Aberration",
            description="Spherical aberration coefficient",
            param_type="float",
            required=True,
            default_value=2.7e-3,  # SI units (meters)
            min_value=1e-6,
            max_value=10e-3,
            gui_unit="mm",
            gui_scaling_factor=1000,  # Convert meters to mm
            display_decimals=3,
            category="Microscope"
        ))
        
        self.register_parameter(ParameterDefinition(
            matlab_name="VOLTAGE",
            json_name="microscope.acceleration_voltage_kv",
            display_name="Accelerating Voltage",
            description="Accelerating voltage in kilovolts",
            param_type="choice",
            required=True,
            default_value=300e3,  # SI units (volts)
            min_value=20e3,
            max_value=1000e3,
            choices=["100", "120", "200", "300"],
            gui_unit="keV",
            gui_scaling_factor=0.001,  # Convert volts to keV
            display_decimals=0,
            category="Microscope"
        ))
        
        # CTF parameters
        self.register_parameter(ParameterDefinition(
            matlab_name="AMPCONT",
            json_name="ctf.amplitude_contrast",
            display_name="Amplitude Contrast",
            description="Amplitude contrast fraction (0.0-1.0)",
            param_type="float",
            required=True,
            default_value=0.04,
            min_value=0.0,
            max_value=1.0,
            gui_unit="",
            display_decimals=3,
            category="CTF"
        ))
        
        # Add more parameters as needed...
    
    def register_parameter(self, param: ParameterDefinition):
        """Register a parameter definition."""
        self._parameters[param.json_name] = param
        self._matlab_lookup[param.matlab_name] = param.json_name
        self._json_lookup[param.json_name] = param.matlab_name
    
    def get_parameter(self, name: str) -> Optional[ParameterDefinition]:
        """Get parameter by JSON name or MATLAB name."""
        if name in self._parameters:
            return self._parameters[name]
        elif name in self._matlab_lookup:
            return self._parameters[self._matlab_lookup[name]]
        return None
    
    def get_all_parameters(self) -> Dict[str, ParameterDefinition]:
        """Get all registered parameters."""
        return self._parameters.copy()
    
    def get_parameters_by_category(self, category: str) -> Dict[str, ParameterDefinition]:
        """Get all parameters in a specific category."""
        return {
            name: param for name, param in self._parameters.items()
            if param.category == category
        }
    
    def get_required_parameters(self) -> List[str]:
        """Get list of required parameter names (JSON format)."""
        return [name for name, param in self._parameters.items() if param.required]


class UnifiedParameterManager:
    """
    Unified parameter management for emClarity.
    
    This class combines the functionality of both the GUI parameter loader
    and the metaData parameter converter into a single, comprehensive system.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.registry = ParameterRegistry()
        self.config_path = config_path
        
        # Load extended configuration if provided
        if config_path and os.path.exists(config_path):
            self._load_extended_config(config_path)
    
    def _load_extended_config(self, config_path: str):
        """Load additional parameter definitions from JSON config."""
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            # TODO: Implement loading additional parameters from JSON
            # This would extend the default registry with user-defined parameters
            pass
            
        except Exception as e:
            logger.warning(f"Could not load extended config from {config_path}: {e}")
    
    # MATLAB conversion methods (from original parameter_converter)
    def parse_matlab_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Parse MATLAB parameter file into dictionary."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"MATLAB parameter file not found: {file_path}")
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Remove comments and extract assignments
        content = re.sub(r'%.*', '', content)  # Remove comments
        
        parameters = {}
        
        # Find all parameter assignments (name = value;)
        pattern = r'(\w+)\s*=\s*([^;]+);'
        matches = re.findall(pattern, content)
        
        for name, value in matches:
            parsed_value = self._parse_matlab_value(value.strip())
            parameters[name] = parsed_value
        
        return parameters
    
    def _parse_matlab_value(self, value_str: str) -> Any:
        """Parse a MATLAB value string into appropriate Python type."""
        value_str = value_str.strip()
        
        # Handle strings (enclosed in quotes)
        if (value_str.startswith("'") and value_str.endswith("'")) or \
           (value_str.startswith('"') and value_str.endswith('"')):
            return value_str[1:-1]
        
        # Handle arrays [1, 2, 3]
        if value_str.startswith('[') and value_str.endswith(']'):
            array_content = value_str[1:-1].strip()
            if not array_content:
                return []
            
            elements = [self._parse_matlab_value(elem.strip()) 
                       for elem in array_content.split(',')]
            return elements
        
        # Handle scientific notation and numbers
        try:
            if 'e' in value_str.lower() or '.' in value_str:
                return float(value_str)
            else:
                return int(value_str)
        except ValueError:
            pass
        
        # Handle boolean-like values
        if value_str.lower() in ['true', '1']:
            return True
        elif value_str.lower() in ['false', '0']:
            return False
        
        # Return as string if nothing else matches
        return value_str
    
    def convert_matlab_to_json(self, matlab_params: Dict[str, Any]) -> Dict[str, Any]:
        """Convert MATLAB parameters to modern JSON format."""
        json_config = {}
        
        for matlab_name, value in matlab_params.items():
            param_def = self.registry.get_parameter(matlab_name)
            if param_def:
                # Use the defined JSON name and validate
                is_valid, error = param_def.validate_value(value)
                if not is_valid:
                    logger.warning(f"Parameter validation failed: {error}")
                    continue
                
                # Create nested structure
                keys = param_def.json_name.split('.')
                current = json_config
                for key in keys[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[keys[-1]] = value
            else:
                # Unknown parameter - keep with warning
                logger.warning(f"Unknown parameter: {matlab_name}")
                json_config[matlab_name] = value
        
        return json_config
    
    def convert_json_to_matlab(self, json_config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert JSON parameters back to MATLAB format."""
        matlab_params = {}
        
        def flatten_dict(d: Dict[str, Any], prefix: str = '') -> Dict[str, Any]:
            """Flatten nested dictionary to dot notation."""
            items = {}
            for key, value in d.items():
                new_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    items.update(flatten_dict(value, new_key))
                else:
                    items[new_key] = value
            return items
        
        flat_json = flatten_dict(json_config)
        
        for json_name, value in flat_json.items():
            param_def = self.registry.get_parameter(json_name)
            if param_def:
                matlab_params[param_def.matlab_name] = value
            else:
                # Unknown parameter - use JSON name
                matlab_params[json_name] = value
        
        return matlab_params
    
    # GUI integration methods (from original parameter_loader)
    def get_parameter_config(self, name: str) -> Optional[ParameterDefinition]:
        """Get parameter configuration for GUI use."""
        return self.registry.get_parameter(name)
    
    def get_all_gui_parameters(self) -> Dict[str, ParameterDefinition]:
        """Get all parameters formatted for GUI use."""
        return self.registry.get_all_parameters()
    
    def get_parameters_by_category(self, category: str) -> Dict[str, ParameterDefinition]:
        """Get parameters by category for GUI organization."""
        return self.registry.get_parameters_by_category(category)
    
    def validate_all_parameters(self, config: Dict[str, Any]) -> List[str]:
        """Validate all parameters in a configuration."""
        errors = []
        flat_config = self._flatten_dict(config)
        
        # Check required parameters
        required = self.registry.get_required_parameters()
        for req_param in required:
            if req_param not in flat_config:
                errors.append(f"Required parameter missing: {req_param}")
        
        # Validate each parameter
        for name, value in flat_config.items():
            param_def = self.registry.get_parameter(name)
            if param_def:
                is_valid, error = param_def.validate_value(value)
                if not is_valid:
                    errors.append(error)
        
        return errors
    
    def _flatten_dict(self, d: Dict[str, Any], prefix: str = '') -> Dict[str, Any]:
        """Flatten nested dictionary to dot notation."""
        items = {}
        for key, value in d.items():
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                items.update(self._flatten_dict(value, new_key))
            else:
                items[new_key] = value
        return items
    
    def create_json_schema(self) -> Dict[str, Any]:
        """Create JSON schema for validation."""
        # TODO: Implement JSON schema generation
        return {}


# Global instance for easy access
_parameter_manager = None

def get_parameter_manager() -> UnifiedParameterManager:
    """Get the global parameter manager instance."""
    global _parameter_manager
    if _parameter_manager is None:
        _parameter_manager = UnifiedParameterManager()
    return _parameter_manager
