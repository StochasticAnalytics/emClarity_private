"""
memory_utils.py

Memory layout utilities for emClarity CUDA operations.
Ensures consistent C-contiguous (row-major) memory layout for CUDA kernels.

Author: emClarity Python Conversion  
Date: September 2025
"""

import os
import inspect
from typing import Optional

import cupy as cp

# Enable strict memory layout checks by default - disable with environment variable
STRICT_CHECKS = os.getenv("EMCLARITY_NO_STRICT_CUPY_ORDERING_CHECKS", "0") != "1"


def ensure_f(x: cp.ndarray, *, allow_copy: bool = False, dtype: Optional[cp.dtype] = None) -> cp.ndarray:
    """
    Legacy: ensure array is Fortran-contiguous (column-major).

    Retained for backward compatibility with code that still needs F-order arrays.
    New CUDA kernel code should use ensure_c() for C-contiguous (row-major) layout.

    Args:
        x: Input CuPy array
        allow_copy: If True, allow copying when input is not F-contiguous
        dtype: Optional dtype conversion
        
    Returns:
        Fortran-contiguous array
        
    Raises:
        RuntimeError: If strict checks are enabled and input is not F-contiguous 
                     but call site expected F-contiguous input (allow_copy=False)
    """
    y = cp.asfortranarray(x, dtype=dtype)  # returns x if already F-contiguous
    
    if STRICT_CHECKS and not allow_copy and (y is not x):
        # Get caller information
        frame = inspect.currentframe()
        caller = frame.f_back if frame else None
        info = inspect.getframeinfo(caller) if caller else None
        
        # Format the error message with caller file, line number, and function name
        caller_info = ""
        if info:
            caller_info = f" | at {info.filename}:{info.lineno} in {info.function}"
            
        raise RuntimeError(
            f"ensure_f: input was not F-contiguous and required copying; "
            f"call site expected F-contiguous input{caller_info}"
        )
    
    # Sanity checks
    assert y.flags.f_contiguous, "ensure_f: result not F-contiguous"
    
    return y


def ensure_c(x: cp.ndarray, *, allow_copy: bool = False, dtype: Optional[cp.dtype] = None) -> cp.ndarray:
    """
    Ensure array is C-contiguous (row-major) as required by emClarity CUDA kernels.

    Args:
        x: Input CuPy array
        allow_copy: If True, allow copying when input is not C-contiguous  
        dtype: Optional dtype conversion
        
    Returns:
        C-contiguous array
        
    Raises:
        RuntimeError: If strict checks are enabled and input is not C-contiguous
                     but call site expected C-contiguous input (allow_copy=False)
    """
    y = cp.ascontiguousarray(x, dtype=dtype)  # returns x if already C-contiguous
    
    if STRICT_CHECKS and not allow_copy and (y is not x):
        # Get caller information
        frame = inspect.currentframe()
        caller = frame.f_back if frame else None
        info = inspect.getframeinfo(caller) if caller else None
        
        # Format the error message with caller file, line number, and function name
        caller_info = ""
        if info:
            caller_info = f" | at {info.filename}:{info.lineno} in {info.function}"
            
        raise RuntimeError(
            f"ensure_c: input was not C-contiguous and required copying; "
            f"call site expected C-contiguous input{caller_info}"
        )
    
    # Sanity checks  
    assert y.flags.c_contiguous, "ensure_c: result not C-contiguous"
    
    return y


def create_fortran_array(shape, dtype=cp.float32, **kwargs) -> cp.ndarray:
    """
    Legacy: create a new Fortran-contiguous (column-major) CuPy array.

    Retained for backward compatibility. New code should create C-contiguous
    arrays via cp.empty() (which defaults to C-order) or ensure_c().

    Args:
        shape: Array shape
        dtype: Data type (default: float32)
        **kwargs: Additional arguments passed to cp.empty

    Returns:
        Fortran-contiguous array (legacy layout)
    """
    # Force Fortran order
    kwargs['order'] = 'F'
    arr = cp.empty(shape, dtype=dtype, **kwargs)
    
    # Verify it's actually F-contiguous
    assert arr.flags.f_contiguous, f"Failed to create F-contiguous array with shape {shape}"
    
    return arr
