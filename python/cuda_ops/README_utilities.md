# CUDA Utility Functions for emClarity

This document describes the reusable CUDA utility functions that provide consistent indexing patterns across all emClarity GPU kernels.

## Overview

The `emc_cuda_utils.cuh` header contains inline device functions that standardize indexing operations according to emClarity conventions. These utilities eliminate code duplication and improve maintainability.

## emClarity Conventions

- **X is the fastest dimension** (varies most rapidly in memory)
- **Y is the second dimension**
- **Z is the slowest dimension** (varies least rapidly)
- **Memory layout**: Row-major (C-style) ordering
- **Array shape notation**: `(nz, ny, nx)` for 3D arrays

## Core Utility Functions

### Thread Index Retrieval

```cuda
__device__ __forceinline__ int get_1d_idx()
__device__ __forceinline__ int2 get_2d_idx()  
__device__ __forceinline__ int3 get_3d_idx()
```

Get thread indices from CUDA grid/block coordinates. 2D and 3D functions return vector types for cleaner code.

### Bounds Checking

```cuda
__device__ __forceinline__ bool is_valid_1d(int idx, int n)
__device__ __forceinline__ bool is_valid_2d(int2 idx, int2 dims)
__device__ __forceinline__ bool is_valid_3d(int3 idx, int3 dims)
```

Check if indices are within array bounds using vector parameters.

### Linear Indexing

```cuda
__device__ __forceinline__ int get_linear_index(int2 idx, int nx)
__device__ __forceinline__ int get_linear_index(int3 idx, int2 dims_xy)
```

Convert 2D/3D coordinates to linear memory indices using emClarity conventions and vector parameters.

### Coordinate Conversion

```cuda
__device__ __forceinline__ int2 linear_to_2d(int linear_idx, int nx)
__device__ __forceinline__ int3 linear_to_3d(int linear_idx, int2 dims_xy)
```

Convert linear indices back to multidimensional coordinates, returning vector types.

### Transpose Indexing

```cuda
__device__ __forceinline__ int transpose_2d_index(int2 idx, int2 dims)
__device__ __forceinline__ int transpose_3d_index(int3 idx, int3 dims)
```

Specialized indexing for transpose operations using vector parameters.

### Early Return Macros

```cuda
#define EMC_RETURN_IF_OUT_OF_BOUNDS_1D(idx, n)
#define EMC_RETURN_IF_OUT_OF_BOUNDS_2D(idx, dims)
#define EMC_RETURN_IF_OUT_OF_BOUNDS_3D(idx, dims)
```

Convenient macros for bounds-checked early returns with vector parameters.

## Usage Examples

### Basic Array Operation

```cuda
extern "C" __global__ void cuda_add_arrays(
    const float* a, const float* b, float* c, int n)
{
    int idx = get_1d_idx();
    EMC_RETURN_IF_OUT_OF_BOUNDS_1D(idx, n);
    
    c[idx] = a[idx] + b[idx];
}
```

### 2D Array Processing

```cuda
extern "C" __global__ void cuda_process_2d(
    const float* input, float* output, int nx, int ny)
{
    int2 idx = get_2d_idx();
    int2 dims = make_int2(nx, ny);
    EMC_RETURN_IF_OUT_OF_BOUNDS_2D(idx, dims);
    
    int linear_idx = get_linear_index(idx, nx);
    output[linear_idx] = input[linear_idx] * 2.0f;
}
```

## Integration with Python

The utility functions are automatically included in CUDA kernels via the Python wrapper classes:

```python
class CudaBasicOps:
    def _load_cuda_kernels(self):
        # Load utility functions from emc_cuda_utils.cuh
        utils_file = Path(__file__).parent / "emc_cuda_utils.cuh"
        with open(utils_file, 'r') as f:
            utils_content = f.read()
        
        # Load main CUDA file
        cuda_file = Path(__file__).parent / "kernel_file.cu"
        with open(cuda_file, 'r') as f:
            cuda_source = f.read()
        
        # Replace include with inline content
        cuda_source = cuda_source.replace('#include "emc_cuda_utils.cuh"', utils_content)
        
        # Compile with CuPy
        self._cuda_module = cp.RawModule(code=cuda_source)
```

## Performance Impact

- **Zero runtime overhead**: All functions are `__forceinline__` device functions
- **Compile-time optimization**: Functions are inlined during CUDA compilation
- **Memory efficiency**: No additional function call overhead
- **Maintainability**: Consistent patterns across all kernels

## Testing Results

All refactored kernels pass comprehensive validation:

```text
=== Testing emc_cuda_basic_ops ===
✅ Addition: True | [ 6.  8. 10. 12.]
✅ Scalar multiply: True | [ 2.5  5.   7.5 10. ]
✅ 2D transpose: True
✅ 3D transpose: True | Shape: (2, 3, 4) -> (4, 3, 2)

=== Performance Testing ===
Addition (1M)       : CUDA   0.026ms | CuPy   0.013ms |  0.51x | PASS
Scalar Mult (1M)    : CUDA   0.013ms | CuPy   0.017ms |  1.30x | PASS
2D Transpose (1M)   : CUDA   0.014ms | CuPy   0.001ms |  0.06x | PASS
3D Transpose (1M)   : CUDA   0.031ms | CuPy   0.001ms |  0.03x | PASS
```

## Benefits

1. **Code Reusability**: Single implementation of indexing patterns
2. **Consistency**: All kernels follow emClarity conventions
3. **Maintainability**: Changes to indexing logic in one place
4. **Readability**: Self-documenting function names
5. **Error Reduction**: Standardized bounds checking
6. **Performance**: Zero overhead inline functions

## Future Development

All new CUDA kernels should use these utility functions for:
- Consistent indexing patterns
- Improved code maintainability  
- Reduced development time
- Standardized error handling

The utilities provide a solid foundation for the emClarity CUDA architecture.
