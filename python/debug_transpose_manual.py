#!/usr/bin/env python3
"""
Manual debugging script for 2D transpose operation
Copy of the test case with debug prints
"""

import cupy as cp
import numpy as np
from cuda_ops.emc_cuda_basic_ops import CudaBasicOps

def debug_transpose_test():
    """Manual version of test_transpose_2d with debug prints"""
    
    print("=== Manual Transpose Test Debug ===")
    
    # Create the CUDA ops object
    cuda_ops = CudaBasicOps()
    print(f"CUDA kernels ready: {cuda_ops.is_ready()}")
    
    # Create the input array - same as in the test
    a = cp.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=cp.float32)
    print(f"\nInput array:")
    print(f"  Shape: {a.shape}")
    print(f"  Data:\n{a}")
    print(f"  Strides: {a.strides}")
    print(f"  Is C-contiguous: {a.flags.c_contiguous}")
    print(f"  Is F-contiguous: {a.flags.f_contiguous}")
    print(f"  Flattened: {a.ravel()}")
    
    # Expected result - same as in the test
    expected = cp.array([[1.0, 4.0], [2.0, 5.0], [3.0, 6.0]], dtype=cp.float32)
    print(f"\nExpected result:")
    print(f"  Shape: {expected.shape}")
    print(f"  Data:\n{expected}")
    print(f"  Flattened: {expected.ravel()}")
    
    # Call the transpose function
    print(f"\n=== Calling transpose_2d ===")
    try:
        result = cuda_ops.transpose_2d(a)
        print(f"SUCCESS: transpose_2d completed")
        
        print(f"\nActual result:")
        print(f"  Shape: {result.shape}")
        print(f"  Data:\n{result}")
        print(f"  Flattened: {result.ravel()}")
        
        # Compare element by element
        print(f"\n=== Element-by-element comparison ===")
        if result.shape == expected.shape:
            for i in range(result.shape[0]):
                for j in range(result.shape[1]):
                    actual_val = result[i, j]
                    expected_val = expected[i, j]
                    match = "✓" if actual_val == expected_val else "✗"
                    print(f"  [{i},{j}]: actual={actual_val}, expected={expected_val} {match}")
        else:
            print(f"  SHAPE MISMATCH: actual={result.shape}, expected={expected.shape}")
        
        # Overall test result
        try:
            cp.testing.assert_array_equal(result, expected)
            print(f"\n✓ TEST PASSED")
        except AssertionError as e:
            print(f"\n✗ TEST FAILED: {e}")
            
    except Exception as e:
        print(f"ERROR: transpose_2d failed with: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_transpose_test()
