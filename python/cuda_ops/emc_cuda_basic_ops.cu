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
 * out[j*cols + i] = in[i*rows + j]
 */
__global__ void cuda_transpose_2d(const float* in, float* out, int rows, int cols)
{
    int2 idx = get_2d_idx();
    int2 dims = make_int2(cols, rows);
    EMC_RETURN_IF_OUT_OF_BOUNDS_2D(idx, dims);

    int in_idx  = index_2d(idx, cols);
    int out_idx = transpose_2d_index(idx, dims);
    out[out_idx] = in[in_idx];
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
    int in_idx  = index_3d(idx, dims_xy);
    int out_idx = transpose_3d_index(idx, dims);
    out[out_idx] = in[in_idx];
}

}
