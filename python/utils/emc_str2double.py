#!/usr/bin/env python3
"""
Python equivalent of EMC_str2double.m

Converts string to double with error handling.
"""

import numpy as np
from typing import Union


def emc_str2double(value: Union[str, float, int]) -> float:
    """
    Convert string to double (float) with error handling.
    
    Args:
        value: String, float, or int to convert
        
    Returns:
        Float value
        
    Raises:
        ValueError: If conversion fails
        
    Note:
        This is the Python equivalent of EMC_str2double.m
    """
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            raise ValueError(f"Cannot convert '{value}' to float")
    
    raise ValueError(f"Cannot convert {type(value)} to float")


def emc_str2int(value: Union[str, int, float]) -> int:
    """
    Convert string to integer with error handling.
    
    Args:
        value: String, int, or float to convert
        
    Returns:
        Integer value
        
    Raises:
        ValueError: If conversion fails
    """
    if isinstance(value, int):
        return value
    
    if isinstance(value, float):
        return int(value)
    
    if isinstance(value, str):
        try:
            return int(float(value))  # Handle strings like "3.0"
        except ValueError:
            raise ValueError(f"Cannot convert '{value}' to int")
    
    raise ValueError(f"Cannot convert {type(value)} to int")


def test_emc_str2double():
    """Test the conversion functions."""
    print("Testing emc_str2double:")
    
    # Test cases
    test_cases = [
        ("3.14", 3.14),
        ("42", 42.0),
        (3.14, 3.14),
        (42, 42.0),
        ("0", 0.0),
        ("-1.5", -1.5)
    ]
    
    for input_val, expected in test_cases:
        result = emc_str2double(input_val)
        print(f"  {input_val} -> {result} (expected {expected})")
        assert abs(result - expected) < 1e-10, f"Failed for {input_val}"
    
    print("  All tests passed!")


if __name__ == "__main__":
    test_emc_str2double()
