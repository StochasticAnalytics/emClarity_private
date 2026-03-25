#!/usr/bin/env python3

import cupy as cp
from cuda_ops.memory_utils import ensure_c


def debug_transpose_memory_layout():
    """Debug the memory layout issues with transpose."""
    print("=== Memory Layout Analysis ===")

    # Create test array
    a_py = cp.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=cp.float32)
    ensure_c(a_py)  # Ensure C-contiguous


    # Expected transpose


    # Manual transpose to understand indexing
    print("\n=== Manual transpose analysis ===")
    ny, nx = a_py.shape  # (2, 3)
    print(f"Input shape: ny={ny}, nx={nx}")
    print(f"Output shape should be: nx={nx}, ny={ny}")

    print("\nInput memory (C-order linear indices):")
    for y in range(ny):
        for x in range(nx):
            linear_idx = y * nx + x
            value = a_py[y, x]
            print(f"  ({y},{x}) -> linear[{linear_idx}] = {value}")

    print("\nExpected output memory (C-order linear indices):")
    for x in range(nx):
        for y in range(ny):
            linear_idx = x * ny + y
            value = a_py[y, x]  # Original value at (y,x)
            print(f"  ({x},{y}) -> linear[{linear_idx}] = {value}")

    print("\nFortran memory layout analysis:")
    print("Input memory (F-order linear indices):")
    a_c_flat = a_c.ravel(order='F')
    for i, val in enumerate(a_c_flat):
        print(f"  F-linear[{i}] = {val}")

    print("\nMapping (x,y) threads to memory locations:")
    for y in range(ny):
        for x in range(nx):
            # What our kernel does:
            in_idx = y * nx + x  # index_2d assumes C-layout
            out_idx = x * ny + y  # transpose_2d_index for (x,y) -> (y,x)
            value = a_c_flat[in_idx] if in_idx < len(a_c_flat) else "OOB"
            print(f"  Thread({x},{y}): in_idx={in_idx} -> out_idx={out_idx}, value={value}")

if __name__ == "__main__":
    debug_transpose_memory_layout()
