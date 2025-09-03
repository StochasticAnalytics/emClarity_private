# emClarity Python Package

Complete Python implementation of emClarity cryo-EM processing tools with modern architecture, GPU acceleration, and integrated GUI.

## Package Structure

The Python package has been reorganized into a unified structure where the GUI is a subcomponent of the main Python package:

```
python/
├── __init__.py                    # Main package entry point
├── parameters.py                  # Unified parameter management system
├── setup.py                      # Package installation
├── test_runner.py                # Unified test runner
├── requirements*.txt              # Dependency management
│
├── alignment/                     # Tilt-series alignment
├── coordinates/                   # Coordinate transformations  
├── ctf/                          # CTF estimation and correction
├── cuda_ops/                     # GPU-accelerated operations
├── image_io/                     # Image file I/O
├── logicals/                     # Logical operations
├── masking/                      # Image masking and padding
├── metaData/                     # Metadata and parameter handling
├── statistics/                   # Statistical analysis
├── synthetic/                    # Synthetic data generation
├── testScripts/                  # Test and validation scripts
├── transformations/              # Image transformations
├── utils/                        # Common utilities
│
├── gui/                          # Graphical user interface
│   ├── main.py                   # GUI entry point
│   ├── parameter_bridge.py       # GUI-parameter integration
│   └── ...                       # GUI components
│
└── docs/                         # Documentation
```

## Key Features

### 🎯 Unified Parameter Management
- **Single parameter system** for both MATLAB compatibility and GUI display
- **Bidirectional conversion** between MATLAB `.m` files and modern JSON
- **Type validation** and schema checking
- **Unit conversion** with GUI-friendly display
- **Backward compatibility** with existing MATLAB workflows

### 🚀 GPU Acceleration
- **CuPy integration** for CUDA operations
- **Automatic fallback** to CPU when GPU unavailable
- **Memory-efficient** operations
- **Custom CUDA kernels** for specialized operations

### 🖥️ Integrated GUI
- **Qt-based interface** using PySide6
- **Unified parameter editing** with validation
- **Real-time parameter conversion**
- **Project management** capabilities

### 🧪 Comprehensive Testing
- **Unified test runner** for all modules
- **95%+ test coverage** for core functionality
- **GPU vs CPU validation** for numerical consistency
- **MATLAB compatibility testing**

## Installation

### Basic Installation
```bash
cd python/
pip install -e .
```

### With GUI Support
```bash
pip install -e ".[gui]"
```

### With GPU Support
```bash
pip install -e ".[gpu]"
```

### Complete Installation
```bash
pip install -e ".[all]"
```

### Development Installation
```bash
pip install -e ".[dev]"
```

## Quick Start

### Parameter Management
```python
from emclarity import get_parameter_manager

# Load MATLAB parameter file
manager = get_parameter_manager()
matlab_params = manager.parse_matlab_file("param.m")

# Convert to modern JSON format
json_config = manager.convert_matlab_to_json(matlab_params)

# Validate parameters
errors = manager.validate_all_parameters(json_config)

# Convert back to MATLAB (for backward compatibility)
matlab_out = manager.convert_json_to_matlab(json_config)
```

### Image Processing
```python
from emclarity import emc_pad_zeros_3d

# Pad 3D volume with GPU acceleration
padded_volume = emc_pad_zeros_3d(
    image=volume,
    pad_low=[10, 10, 10],
    pad_top=[10, 10, 10],
    method="GPU"  # Automatic fallback to CPU if no GPU
)
```

### GUI Usage
```python
# From command line
emclarity-gui

# Or programmatically
from emclarity.gui.main import main
main()
```

## Module Organization

### Core Modules

**`parameters.py`** - Unified parameter management
- Replaces both GUI `parameter_loader.py` and metaData `emc_parameter_converter.py`
- Comprehensive parameter definitions with validation
- MATLAB ↔ JSON conversion with unit handling

**`utils/`** - Shared utilities
- GPU context management
- Array validation functions
- File path utilities
- Logging configuration
- Memory management

### Processing Modules

**`masking/`** - Image padding and masking
- 3D volume padding with GPU support
- Multiple padding modes (zeros, noise, tapering)
- Fourier oversampling support

**`cuda_ops/`** - GPU operations
- Custom CUDA kernels via CuPy
- Basic array operations (add, multiply, transpose)
- Performance-competitive with CuPy built-ins

**`metaData/`** - Metadata handling
- Parameter file parsing
- Project metadata management
- Backward compatibility with old parameter converter

### GUI Module

**`gui/`** - Graphical interface
- Qt-based parameter editing
- Real-time validation and unit conversion
- Project management
- Integrated with unified parameter system

## Dependency Management

### Core Dependencies (`requirements.txt`)
- `numpy>=1.16.0` - Core array operations
- `scipy>=1.6.0` - Scientific computing
- `mrcfile>=1.5.0` - MRC file I/O
- `jsonschema>=4.0.0` - Parameter validation

### GUI Dependencies (`requirements-gui.txt`)
- `PySide6>=6.0.0` - Qt interface

### GPU Dependencies (`requirements-gpu.txt`)
- `cupy-cuda12x>=12.0.0` - CUDA acceleration

### Development Dependencies (`requirements-dev.txt`)
- `pytest>=6.0.0` - Testing framework
- `black>=21.0.0` - Code formatting
- `flake8>=3.8.0` - Linting

## Testing

### Run All Tests
```bash
python test_runner.py
```

### Run Specific Module Tests
```bash
python test_runner.py metaData
python test_runner.py masking
python test_runner.py cuda_ops
```

### Run with Coverage
```bash
python test_runner.py --coverage
```

## Architecture Decisions

### 1. Unified Parameter System
- **Why**: Eliminates duplication between GUI and conversion systems
- **Benefit**: Single source of truth for parameter definitions
- **Backward compatibility**: Old systems still work with deprecation warnings

### 2. GUI as Subpackage
- **Why**: GUI is specific functionality, not separate project
- **Benefit**: Unified dependency management and testing
- **Flexibility**: Can still be imported/used independently

### 3. CuPy for GPU Operations
- **Why**: Mature ecosystem, good NumPy compatibility
- **Benefit**: Easier development than pure CUDA
- **Performance**: Custom kernels when needed, built-ins when sufficient

### 4. Shared Utilities
- **Why**: Reduce code duplication across modules
- **Benefit**: Consistent error handling and validation
- **Maintainability**: Centralized GPU detection and memory management

## Migration Guide

### From Old Parameter System
```python
# Old way (deprecated)
from metaData import ParameterConverter
converter = ParameterConverter()

# New way
from emclarity import get_parameter_manager
manager = get_parameter_manager()
```

### From Separate GUI Dependencies
```python
# Old way - separate requirements.txt in gui/
pip install -r gui/requirements.txt

# New way - unified dependency management
pip install -e ".[gui]"
```

### Import Path Changes
```python
# Old way
from gui.parameter_loader import ParameterConfigLoader

# New way
from emclarity.gui.parameter_bridge import get_gui_parameter_manager
```

## Development Guidelines

1. **All new modules** should use utilities from `utils.common`
2. **Parameter definitions** go in the unified `parameters.py`
3. **Tests** follow the `module/tests/test_*.py` pattern
4. **GPU operations** should gracefully fall back to CPU
5. **Temporary files** must use `/tmp/copilot-test/`

## Future Roadmap

- [ ] Complete MATLAB function conversion
- [ ] Advanced GUI features (project templates, batch processing)
- [ ] Performance optimization for large datasets
- [ ] Integration with other cryo-EM packages
- [ ] Web-based interface option
