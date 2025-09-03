/**
 * emc_cuda_utils.cuh
 * 
 * Common CUDA device functions for emClarity Python interface
 * Provides inline indexing utilities following emClarity conventions
 * 
 * emClarity Conventions:
 * - X is the fastest dimension
 * - Y is the second dimension  
 * - Z is the slowest dimension
 * - Memory layout: row-major (C-style)
 */

#ifndef EMC_CUDA_UTILS_CUH
#define EMC_CUDA_UTILS_CUH

#include <cuda_runtime.h>

/**
 * Get 1D thread index
 */
__device__ __forceinline__ int get_1d_idx()
{
    return blockIdx.x * blockDim.x + threadIdx.x;
}

/**
 * Get 2D thread indices
 */
__device__ __forceinline__ int2 get_2d_idx()
{
    return make_int2(
        blockIdx.x * blockDim.x + threadIdx.x,
        blockIdx.y * blockDim.y + threadIdx.y
    );
}

/**
 * Get 3D thread indices
 */
__device__ __forceinline__ int3 get_3d_idx()
{
    return make_int3(
        blockIdx.x * blockDim.x + threadIdx.x,
        blockIdx.y * blockDim.y + threadIdx.y,
        blockIdx.z * blockDim.z + threadIdx.z
    );
}

/**
 * Check if 1D index is within bounds
 */
__device__ __forceinline__ bool is_valid_1d(int idx, int n)
{
    return idx < n;
}

/**
 * Check if 2D indices are within bounds
 */
__device__ __forceinline__ bool is_valid_2d(int2 idx, int2 dims)
{
    return (idx.x < dims.x) && (idx.y < dims.y);
}

/**
 * Check if 3D indices are within bounds
 */
__device__ __forceinline__ bool is_valid_3d(int3 idx, int3 dims)
{
    return (idx.x < dims.x) && (idx.y < dims.y) && (idx.z < dims.z);
}

/**
 * Convert 2D coordinates to linear index
 * For array with shape (ny, nx) - emClarity convention
 * Index: y * nx + x
 */
__device__ __forceinline__ int index_2d(int2 idx, int nx)
{
    return idx.y * nx + idx.x;
}

/**
 * Convert 3D coordinates to linear index  
 * For array with shape (nz, ny, nx) - emClarity convention
 * Index: z * (ny * nx) + y * nx + x
 */
__device__ __forceinline__ int index_3d(int3 idx, int2 dims_xy)
{
    return idx.z * (dims_xy.y * dims_xy.x) + idx.y * dims_xy.x + idx.x;
}

/**
 * Convert linear index back to 2D coordinates
 * For array with shape (ny, nx)
 */
__device__ __forceinline__ int2 linear_to_2d(int linear_idx, int nx)
{
    return make_int2(
        linear_idx % nx,        // x
        linear_idx / nx         // y
    );
}

/**
 * Convert linear index back to 3D coordinates
 * For array with shape (nz, ny, nx)
 */
__device__ __forceinline__ int3 linear_to_3d(int linear_idx, int2 dims_xy)
{
    int slice_size = dims_xy.y * dims_xy.x;
    int z = linear_idx / slice_size;
    int remainder = linear_idx % slice_size;
    int y = remainder / dims_xy.x;
    int x = remainder % dims_xy.x;
    return make_int3(x, y, z);
}

/**
 * Transpose indexing helpers
 */

/**
 * 2D transpose: (y,x) -> (x,y)
 * Input index: y * nx + x -> Output index: x * ny + y
 */
__device__ __forceinline__ int transpose_2d_index(int2 idx, int2 dims)
{
    return idx.x * dims.y + idx.y;
}

/**
 * 3D transpose: (z,y,x) -> (x,y,z)
 * Input index: z * (ny * nx) + y * nx + x -> Output index: x * (nz * ny) + y * nz + z
 */
__device__ __forceinline__ int transpose_3d_index(int3 idx, int3 dims)
{
    return idx.x * (dims.z * dims.y) + idx.y * dims.z + idx.z;
}

/**
 * Bounds checking with early return helper
 */
#define EMC_RETURN_IF_OUT_OF_BOUNDS_1D(idx, n) \
    if (idx >= n) return;

#define EMC_RETURN_IF_OUT_OF_BOUNDS_2D(idx, dims) \
    if ((idx.x >= dims.x) || (idx.y >= dims.y)) return;

#define EMC_RETURN_IF_OUT_OF_BOUNDS_3D(idx, dims) \
    if ((idx.x >= dims.x) || (idx.y >= dims.y) || (idx.z >= dims.z)) return;

#endif // EMC_CUDA_UTILS_CUH
