/*
 * basic_array_ops.cu
 * 
 * CUDA kernels for basic array operations
 * Part of emClarity Python conversion
 */

#include <cuda_runtime.h>
#include "emc_cuda_utils.cuh"

extern "C" {

// Element-wise array addition
__global__ void array_add(
    const float* a,
    const float* b, 
    float* result,
    const int n_elements
) {
    int idx = get_1d_idx();
    EMC_RETURN_IF_OUT_OF_BOUNDS_1D(idx, n_elements);
    
    result[idx] = a[idx] + b[idx];
}

// Element-wise array scaling
__global__ void array_scale(
    const float* input,
    float* output,
    const float scale_factor,
    const int n_elements
) {
    int idx = get_1d_idx();
    EMC_RETURN_IF_OUT_OF_BOUNDS_1D(idx, n_elements);
    
    output[idx] = input[idx] * scale_factor;
}

// 2D array transpose (for testing memory indexing)
__global__ void transpose_2d(
    const float* input,
    float* output,
    const int rows,
    const int cols
) {
    int2 idx = get_2d_idx();
    int2 dims = make_int2(cols, rows);
    EMC_RETURN_IF_OUT_OF_BOUNDS_2D(idx, dims);

    int input_idx  = index_2d(idx, cols);     // input[y][x]
    int output_idx = transpose_2d_index(idx, dims);  // output[x][y]
    output[output_idx] = input[input_idx];
}

// 3D array transpose (testing 3D memory indexing)
__global__ void transpose_3d_xy(
    const float* input,
    float* output,
    const int nx,
    const int ny, 
    const int nz
) {
    int3 idx = get_3d_idx();
    int3 dims = make_int3(nx, ny, nz);
    EMC_RETURN_IF_OUT_OF_BOUNDS_3D(idx, dims);

    // Transpose X and Y dimensions, keep Z
    int2 dims_xy = make_int2(nx, ny);
    int2 dims_yx = make_int2(ny, nx);
    int3 transposed_idx = make_int3(idx.y, idx.x, idx.z);
    
    int input_idx  = index_3d(idx, dims_xy);              // input[z][y][x]
    int output_idx = index_3d(transposed_idx, dims_yx);   // output[z][x][y]
    output[output_idx] = input[input_idx];
}

// Vector magnitude calculation (useful for testing reductions)
__global__ void vector_magnitude_squared(
    const float* input,
    float* output,
    const int n_elements
) {
    int idx = get_1d_idx();
    EMC_RETURN_IF_OUT_OF_BOUNDS_1D(idx, n_elements);
    
    output[idx] = input[idx] * input[idx];
}

}
