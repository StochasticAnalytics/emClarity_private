// Basic CUDA operations for emClarity Python interface
// Array addition, multiplication, and transpose operations

#include <cuda_runtime.h>
#include "emc_cuda_utils.cuh"

extern "C" {

/**
 * CUDA kernel for element-wise array addition
 * c = a + b
 */
__global__ void cuda_add_arrays(const float* a, const float* b, float* c, int n)
{
    int idx = get_1d_idx();
    EMC_RETURN_IF_OUT_OF_BOUNDS_1D(idx, n);
    
    c[idx] = a[idx] + b[idx];
}

/**
 * CUDA kernel for element-wise array multiplication by scalar
 * b = a * scalar
 */
__global__ void cuda_multiply_scalar(const float* a, float* b, float scalar, int n)
{
    int idx = get_1d_idx();
    EMC_RETURN_IF_OUT_OF_BOUNDS_1D(idx, n);
    
    b[idx] = a[idx] * scalar;
}

/**
 * CUDA kernel for 2D matrix transpose
 * Transpose from (ny, nx) to (nx, ny) following emClarity conventions
 * Assumes standard C-contiguous (row-major) memory layout
 */
extern "C" __global__
void cuda_transpose_2d(const float* input, float* output, int nx, int ny)
{
    int2 idx = get_2d_idx();
    int2 dims = make_int2(nx, ny);
    
    EMC_RETURN_IF_OUT_OF_BOUNDS_2D(idx, dims);
    
    // Standard C-order indexing
    int in_idx = get_linear_index(idx, nx);      // input[y][x]
    int out_idx = transpose_2d_index(idx, dims); // output[x][y]
    
    output[out_idx] = input[in_idx];
}

/**
 * CUDA kernel for 3D array transpose
 * Transpose dimensions: (z,y,x) -> (x,y,z) following emClarity conventions
 */
__global__ void cuda_transpose_3d(const float* in, float* out, int nx, int ny, int nz)
{
    int3 idx = get_3d_idx();
    int3 dims = make_int3(nx, ny, nz);
    EMC_RETURN_IF_OUT_OF_BOUNDS_3D(idx, dims);

    int2 dims_xy = make_int2(nx, ny);
    int in_idx  = get_linear_index(idx, dims_xy);
    int out_idx = transpose_3d_index(idx, dims);
    out[out_idx] = in[in_idx];
}

}
