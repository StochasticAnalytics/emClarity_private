# Python Code Style Guide for emClarity

This document outlines the coding standards and linting rules for the emClarity Python codebase to maintain consistency and prevent CI failures.

## Overview

The emClarity project uses automated linting tools to enforce code quality:
- **Black** for code formatting
- **isort** for import sorting
- **flake8** for style and syntax checking  
- **mypy** for type checking

## Pre-Commit Setup

### Install Development Dependencies
```bash
pip install black isort flake8 mypy autopep8
```

### Pre-Commit Hook (Recommended)
Create `.git/hooks/pre-commit`:
```bash
#!/bin/bash
cd python/
echo "Running code quality checks..."

# Format code
black .
isort .

# Check for issues
black --check . || exit 1
isort --check-only . || exit 1
flake8 . --max-line-length=100 --ignore=E203,W503 || exit 1

echo "✅ All checks passed!"
```

## Code Style Rules

### 1. Import Organization (isort)

**✅ Correct:**
```python
# Standard library imports
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Third-party imports
import numpy as np
import pandas as pd

# Local imports
from .utils import helper_function
from .models import DataModel
```

**❌ Incorrect:**
```python
import numpy as np
import os
from .utils import helper_function
import pandas as pd
```

### 2. Code Formatting (Black)

**✅ Correct:**
```python
def long_function_name(
    parameter_one: str,
    parameter_two: int,
    parameter_three: Optional[bool] = None,
) -> Dict[str, Any]:
    """Function with properly formatted parameters."""
    result = {
        "key1": parameter_one,
        "key2": parameter_two,
        "key3": parameter_three,
    }
    return result
```

**❌ Incorrect:**
```python
def long_function_name(parameter_one: str, parameter_two: int, parameter_three: Optional[bool] = None) -> Dict[str, Any]:
    result = {"key1": parameter_one,
              "key2": parameter_two, "key3": parameter_three}
    return result
```

### 3. String Formatting

**✅ Correct:**
```python
# Simple f-strings
name = "World"
message = f"Hello, {name}!"

# Complex expressions - avoid nested f-strings
text = widget.get("text", "")
text_part = f': "{text}"' if text else ""
summary = f"- {widget_type}{text_part}"
```

**❌ Incorrect:**
```python
# Nested f-strings with backslashes (syntax error)
summary = f"- {widget_type}{f': \"{text}\"' if text else ''}"

# Backslashes in f-strings
path = f"C:\\Users\\{username}\\Documents"  # Use raw strings or Path
```

### 4. Line Length and Spacing

**✅ Correct:**
```python
# Max 100 characters per line
very_long_variable_name = some_function_with_long_name(
    parameter_one, parameter_two, parameter_three
)

# Proper spacing
class MyClass:
    """Class docstring."""

    def __init__(self):
        """Initialize the class."""
        self.value = 42

    def method(self) -> int:
        """Method with proper spacing."""
        return self.value
```

**❌ Incorrect:**
```python
# Line too long
very_long_variable_name = some_function_with_long_name(parameter_one, parameter_two, parameter_three, parameter_four)

# Improper spacing
class MyClass:
    def __init__(self):
        self.value = 42
    def method(self) -> int:
        return self.value
```

### 5. Error Handling

**✅ Correct:**
```python
try:
    result = risky_operation()
except ValueError as e:
    logger.error(f"Value error occurred: {e}")
    raise
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise
```

**❌ Incorrect:**
```python
try:
    result = risky_operation()
except:  # Bare except clause
    pass
```

### 6. Type Hints

**✅ Correct:**
```python
from typing import Any, Dict, List, Optional, Union

def process_data(
    items: List[str], 
    config: Dict[str, Any],
    timeout: Optional[int] = None
) -> Union[str, None]:
    """Process data with proper type hints."""
    if not items:
        return None
    return "processed"
```

**❌ Incorrect:**
```python
def process_data(items, config, timeout=None):  # No type hints
    if not items:
        return None
    return "processed"
```

### 7. Unused Imports and Variables

**✅ Correct:**
```python
import logging
from typing import Dict

logger = logging.getLogger(__name__)

def process_config(config: Dict[str, str]) -> bool:
    """All imports and variables are used."""
    logger.info("Processing configuration")
    return len(config) > 0
```

**❌ Incorrect:**
```python
import logging
import os  # Unused import
from typing import Dict, List  # List is unused

logger = logging.getLogger(__name__)

def process_config(config: Dict[str, str]) -> bool:
    unused_var = "not used"  # Unused variable
    logger.info("Processing configuration")
    return len(config) > 0
```

## Common Fixes

### Auto-Fix Commands
Run these before committing:
```bash
cd python/
isort .          # Fix import sorting
black .          # Fix formatting
autopep8 --in-place --recursive --max-line-length=100 .  # Additional fixes
```

### Manual Fixes Needed
- Remove unused imports and variables
- Fix undefined variable references
- Resolve type checking errors
- Add missing docstrings

## IDE Configuration

### VS Code Settings (.vscode/settings.json)
```json
{
    "python.formatting.provider": "black",
    "python.sortImports.provider": "isort",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.mypyEnabled": true,
    "python.linting.flake8Args": [
        "--max-line-length=100",
        "--ignore=E203,W503"
    ],
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    }
}
```

### PyCharm Settings
1. File → Settings → Tools → External Tools
2. Add Black, isort, and flake8 as external tools
3. Enable "Format on Save" in Code Style settings
4. Configure import optimization in Code Style → Python → Imports

## CI Integration

The CI pipeline runs these checks on every push:
```yaml
- name: Code Quality Checks
  run: |
    cd python/
    black --check --diff .
    isort --check-only --diff .
    flake8 . --max-line-length=100 --ignore=E203,W503
    mypy . --ignore-missing-imports
```

## Quick Reference

### Before Committing (Every Time)
```bash
cd python/
black . && isort . && flake8 . --max-line-length=100
```

### Common flake8 Error Codes
- `E501`: Line too long (>100 characters)
- `F401`: Imported but unused
- `F841`: Local variable assigned but never used
- `E302`: Expected 2 blank lines
- `W291`: Trailing whitespace
- `E722`: Do not use bare except

### Quick Fixes
- **Trailing whitespace**: Remove extra spaces at line ends
- **Import order**: Let isort handle it automatically
- **Line length**: Break long lines at logical points
- **Unused imports**: Remove or move to comments if needed for typing

## Resources

- [Black Documentation](https://black.readthedocs.io/)
- [isort Documentation](https://pycqa.github.io/isort/)
- [flake8 Documentation](https://flake8.pycqa.org/)
- [mypy Documentation](https://mypy.readthedocs.io/)
- [PEP 8 Style Guide](https://pep8.org/)

---

Following these guidelines will ensure your code passes CI checks and maintains consistency across the emClarity codebase.
