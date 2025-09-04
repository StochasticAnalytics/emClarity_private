"""
Bridge module connecting emClarity GUI and Python backend.

This module provides a clean interface for the GUI to access Python functionality
without creating tight coupling between the GUI and internal Python modules.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Union

from masking import emc_pad_zeros_3d
from metaData import ParameterConverter

# Add python directory to path for imports
python_dir = Path(__file__).parent.parent / "python"
if str(python_dir) not in sys.path:
    sys.path.insert(0, str(python_dir))


# Optional CUDA support
try:
    from cuda_ops import CudaBasicOps

    HAS_CUDA = True
except ImportError:
    HAS_CUDA = False
    CudaBasicOps = None


class EmClarityPythonBridge:
    """
    Bridge class providing clean GUI access to Python functionality.

    This class encapsulates Python module interactions and provides
    a stable API for the GUI, protecting against internal changes.
    """

    def __init__(self):
        self.parameter_converter = ParameterConverter()
        self.cuda_ops = CudaBasicOps() if HAS_CUDA else None

    # Parameter management
    def convert_matlab_to_json(
        self, matlab_file_path: Union[str, Path]
    ) -> Dict[str, Any]:
        """Convert MATLAB parameter file to JSON format."""
        matlab_params = self.parameter_converter.parse_matlab_file(matlab_file_path)
        return self.parameter_converter.convert_matlab_to_json(matlab_params)

    def convert_json_to_matlab(self, json_config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert JSON parameters back to MATLAB format."""
        return self.parameter_converter.convert_json_to_matlab(json_config)

    def validate_parameters(self, json_config: Dict[str, Any]) -> List[str]:
        """Validate parameters and return list of errors."""
        schema = self.parameter_converter.create_json_schema()
        try:
            import jsonschema

            jsonschema.validate(json_config, schema)
            return []
        except ImportError:
            return ["jsonschema not available for validation"]
        except jsonschema.ValidationError as e:
            return [str(e)]

    # Image processing
    def pad_image_3d(self, image, pad_low, pad_top=None, method="CPU", **kwargs):
        """Pad 3D image with options for GPU acceleration."""
        return emc_pad_zeros_3d(image, pad_low, pad_top, method=method, **kwargs)

    # CUDA operations (if available)
    def has_cuda_support(self) -> bool:
        """Check if CUDA operations are available."""
        return HAS_CUDA and self.cuda_ops is not None

    def cuda_array_add(self, a, b):
        """GPU array addition (if CUDA available)."""
        if not self.has_cuda_support():
            raise RuntimeError("CUDA operations not available")
        return self.cuda_ops.array_add(a, b)

    # System information
    def get_system_info(self) -> Dict[str, Any]:
        """Get information about available Python modules and capabilities."""
        return {
            "cuda_available": HAS_CUDA,
            "python_version": sys.version,
            "python_path": str(python_dir),
            "modules": {
                "parameter_converter": True,
                "image_padding": True,
                "cuda_ops": HAS_CUDA,
            },
        }


# Singleton instance for GUI use
_bridge_instance = None


def get_python_bridge() -> EmClarityPythonBridge:
    """Get singleton instance of the Python bridge."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = EmClarityPythonBridge()
    return _bridge_instance
