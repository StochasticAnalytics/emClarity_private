"""
emClarity Python metaData package

This package contains Python conversions of emClarity's metadata handling functionality.

Note: The parameter conversion functionality has been moved to the unified
parameters module at the package root. The old ParameterConverter is 
available for backward compatibility but deprecated.
"""

import warnings
import sys
from pathlib import Path

# Add parent directory to path for unified parameter system access
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

try:
    from parameters import UnifiedParameterManager, ParameterDefinition, get_parameter_manager
except ImportError:
    # Fallback if parameters module not available
    UnifiedParameterManager = None
    ParameterDefinition = None
    get_parameter_manager = None

# Backward compatibility - deprecated
from .emc_parameter_converter import ParameterConverter, ParameterInfo

def deprecated_parameter_converter_warning():
    warnings.warn(
        "ParameterConverter is deprecated. Use UnifiedParameterManager from the "
        "root parameters module instead. This will be removed in version 2.0.0.",
        DeprecationWarning,
        stacklevel=3
    )

# Override to show deprecation warning
class DeprecatedParameterConverter(ParameterConverter):
    def __init__(self, *args, **kwargs):
        deprecated_parameter_converter_warning()
        super().__init__(*args, **kwargs)

# Export both old and new systems
__all__ = [
    'ParameterConverter',  # Deprecated
    'ParameterInfo'  # Deprecated
]

# Add unified system if available
if UnifiedParameterManager is not None:
    __all__.extend([
        'UnifiedParameterManager', 
        'ParameterDefinition', 
        'get_parameter_manager'
    ])

__version__ = '1.0.0'
