# emClarity Python Documentation Standards

## Module Documentation Template

Each Python module should include the following documentation:

### 1. Module README.md

```markdown
# emClarity Python [Module Name] Module

## Purpose
Brief description of what this module does and its role in the emClarity workflow.

## Original MATLAB Equivalent
- **Original location**: `[original_matlab_path]`
- **Main functions converted**: List key functions

## Key Features
- Feature 1 with brief description
- Feature 2 with brief description
- Any improvements over MATLAB version

## Quick Start

```python
from [module_name] import [main_class_or_function]

# Basic usage example
result = main_function(input_data)
```

## API Reference

### Classes
Brief description of main classes

### Functions  
Brief description of main functions

## Testing
- Number of unit tests
- Coverage percentage
- How to run tests

## Dependencies
- Required packages
- Optional packages (GPU, etc.)

## Performance Notes
- GPU acceleration availability
- Memory requirements
- Performance comparisons vs MATLAB if available
```

### 2. Function/Class Docstrings

Use Google-style docstrings consistently:

```python
def function_name(param1: type, param2: type) -> return_type:
    """
    Brief one-line description.
    
    Longer description if needed, explaining the purpose and behavior
    of the function in more detail.
    
    Args:
        param1: Description of first parameter
        param2: Description of second parameter with details about
               acceptable values or types
               
    Returns:
        Description of return value and its type/structure
        
    Raises:
        ValueError: When parameter validation fails
        RuntimeError: When operation cannot complete
        
    Example:
        Basic usage example:
        
        >>> result = function_name("input", 42)
        >>> print(result)
        Expected output
        
    Note:
        Any important notes about usage, performance, or limitations
    """
```

### 3. Type Hints

All functions should include comprehensive type hints:

```python
from typing import Union, List, Dict, Any, Optional, Tuple
import numpy as np

def process_array(
    data: Union[np.ndarray, List[float]], 
    options: Optional[Dict[str, Any]] = None
) -> Tuple[np.ndarray, Dict[str, float]]:
    """Function with proper type hints."""
```

### 4. Error Handling Standards

```python
# Input validation
if not isinstance(data, (np.ndarray, list)):
    raise TypeError(f"Expected array or list, got {type(data)}")

if data.size == 0:
    raise ValueError("Input array cannot be empty")

# Informative error messages
try:
    result = complex_operation(data)
except CudaError as e:
    raise RuntimeError(f"CUDA operation failed: {e}. Try method='CPU'") from e
```

### 5. Test Documentation

Each test file should document:

```python
"""
Tests for [module_name].

Test categories:
- Basic functionality tests
- Edge case handling  
- Error condition testing
- Performance validation (if applicable)
- GPU vs CPU consistency (if applicable)

To run: python -m pytest test_[module_name].py -v
"""
```

## Documentation Build Process

For generating comprehensive docs:

```bash
# Install documentation dependencies
pip install -r requirements-dev.txt

# Generate API documentation
sphinx-apidoc -f -o docs/api python/

# Build HTML documentation  
cd docs && make html
```

## Example Module Documentation

See `python/metaData/README.md` for a complete example following these standards.
