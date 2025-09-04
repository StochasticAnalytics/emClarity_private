# CUDA Operations Module

GPU-accelerated array operations for emClarity Python conversion.

## Overview

This module provides CUDA-accelerated implementations of basic array operations using CuPy's RawKernel interface. It establishes the architectural pattern for Python ↔ CUDA integration throughout the emClarity conversion project.

## Features

- **Element-wise operations**: Addition, scaling, magnitude calculations
- **Memory layout testing**: 2D and 3D array transpositions 
- **Performance optimization**: Custom CUDA kernels with optimal grid/block sizing
- **Error handling**: Comprehensive input validation and meaningful error messages
- **Testing framework**: Unit tests and performance benchmarks
- **Utility functions**: Reusable indexing patterns (see [README_utilities.md](README_utilities.md))

## Architecture

The module follows a clear separation:

- `*.cu` files: CUDA kernel implementations
- `*.py` files: Python wrappers using CuPy RawKernel
- `emc_cuda_utils.cuh`: Reusable utility functions for consistent indexing
- Clear correspondence: `basic_array_ops.cu` ↔ `basic_array_ops.py`

## Utility Functions

All CUDA kernels use standardized utility functions from `emc_cuda_utils.cuh`:

- **Thread indexing**: `get_1d_idx()`, `get_2d_idx()`, `get_3d_idx()`
- **Bounds checking**: `is_valid_*()` functions and `EMC_RETURN_IF_OUT_OF_BOUNDS_*` macros
- **Linear indexing**: `get_linear_index()` overloads for 1D/2D/3D
- **Transpose operations**: Specialized indexing for memory layout changes

See [README_utilities.md](README_utilities.md) for comprehensive documentation.

## Usage

### Basic Operations

```python
import cupy as cp
from cuda_ops import BasicArrayOps

# Initialize CUDA operations
ops = BasicArrayOps()

# Create test arrays
a = cp.random.rand(1000, 1000).astype(cp.float32)
b = cp.random.rand(1000, 1000).astype(cp.float32)

# CUDA-accelerated addition
result = ops.array_add(a, b)

# CUDA-accelerated scaling  
scaled = ops.array_scale(a, 3.14159)

# 2D transpose (tests memory indexing)
transposed = ops.transpose_2d(a)
```

### Convenience Functions

```python
from cuda_ops import cuda_array_add, cuda_transpose_2d

# Direct function calls (creates BasicArrayOps instance internally)
result = cuda_array_add(a, b)
transposed = cuda_transpose_2d(a)
```

## Performance

The CUDA implementations are optimized for:

- **Grid/block sizing**: Automatic calculation based on array dimensions
- **Memory access patterns**: Coalesced memory access for optimal bandwidth
- **Kernel efficiency**: Minimal overhead and maximum occupancy

Benchmark results show competitive performance with CuPy's native operations while providing a foundation for more complex custom kernels.

## Testing

Comprehensive test suite covering:

- **Correctness**: Verification against NumPy/CuPy reference implementations
- **Edge cases**: Error handling for invalid inputs
- **Performance**: Benchmarks comparing CUDA vs reference implementations
- **Memory indexing**: Transpose operations verify correct 2D/3D memory access

Run tests:
```bash
cd python/cuda_ops
python -m pytest tests/ -v
# or
python tests/test_basic_array_ops.py
```

## Requirements

- CUDA Toolkit 11.2+
- CuPy 10.0+
- NumPy 1.20+
- Python 3.8+

## Implementation Notes

### CUDA Kernel Design

- All kernels use `extern "C"` for C linkage
- Thread indexing follows standard CUDA patterns
- Bounds checking prevents memory access violations
- Support for 1D, 2D, and 3D grid configurations

### Memory Management

- Uses CuPy's memory management for GPU allocation
- Optional pre-allocated output arrays for memory reuse
- Automatic type checking (requires float32 input)
- Efficient pointer passing to CUDA kernels

### Future Extensions

This module establishes patterns for more complex operations:

- Custom FFT implementations
- 3D convolutions and filtering
- Geometric transformations
- CTF correction kernels

## Integration with emClarity

This module serves as the foundation for converting MATLAB MEX functions to Python CUDA implementations, following the architectural patterns established in `fourierTransformer.m` and `mexFFT.cu`.
