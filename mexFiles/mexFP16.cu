
#include "include/core_headers.cuh"
#include <memory>

// #define mexFP16_DEBUG_PRINT(args) mexPrintf("%s\n", args)
#define mexFP16_DEBUG_PRINT(...)

// Element-wise conversion kernels (grid-stride).
__global__ void convert_fp16_to_fp32(const uint16_t* __restrict__ input_half, float* __restrict__ output_single, const int N) {
  for (int idx = blockIdx.x * blockDim.x + threadIdx.x;  idx < N; idx += gridDim.x * blockDim.x)
    output_single[idx] = __half2float(__ushort_as_half(input_half[idx]));
}

__global__ void convert_fp32_to_fp16(const float* __restrict__ input_single, uint16_t* __restrict__ output_half, const int N) {
  for (int idx = blockIdx.x * blockDim.x + threadIdx.x;  idx < N; idx += gridDim.x * blockDim.x)
     output_half[idx] = __half_as_ushort(__float2half_rn(input_single[idx]));
}

// out = mexFP16(input, to_half, output_on_gpu, n_elements)
//
//   input         : single or uint16 array, on the host or a gpuArray
//   to_half       : logical. true  -> single -> uint16 (FP16 bit pattern)
//                            false -> uint16 (FP16) -> single
//   output_on_gpu : logical. true  -> returned array is a gpuArray
//                            false -> returned array is on the host
//   n_elements    : int64, numel(input)
//
// The returned array is freshly allocated and OWNED BY MATLAB (gpuArray via
// mxGPUCreateGPUArray + mxGPUCreateMxArrayOnGPU, or host via mxCreateNumericArray).
// MATLAB reference-counts and frees it like the result of gpuArray(x); this mex
// keeps nothing alive. Behaves like new = gpuArray(x) but the precision
// conversion happens on the GPU, so converting host-uint16 -> gpu-single moves
// only the (smaller) uint16 bytes across PCIe and never materializes a single
// copy on the host.
void mexFunction(int nlhs, mxArray *plhs[], int nrhs, mxArray const *prhs[]) {

  if (nrhs != 4) {
    mexErrMsgIdAndTxt("MATLAB:mexFP16:rhs",
                      "Usage: out = mexFP16(input, to_half(logical), output_on_gpu(logical), n_elements(int64)).");
  }
  if (!mxIsLogical(prhs[1]) || !mxIsLogical(prhs[2])) {
    mexErrMsgIdAndTxt("MATLAB:mexFP16:rhs", "Arguments 2 (to_half) and 3 (output_on_gpu) must be logical.");
  }
  if (!mxIsInt64(prhs[3])) {
    mexErrMsgIdAndTxt("MATLAB:mexFP16:rhs", "Argument 4 (n_elements) must be int64.");
  }
  if (mxInitGPU() != MX_GPU_SUCCESS) {
    mexErrMsgIdAndTxt("MATLAB:mexFP16:gpu", "Could not initialize the MathWorks GPU API.");
  }

  const bool   to_half    = mxIsLogicalScalarTrue(prhs[1]);
  const bool   out_on_gpu = mxIsLogicalScalarTrue(prhs[2]);
  const bool   in_on_gpu  = mxIsGPUArray(prhs[0]);
  const size_t N          = (size_t)(*((int64_t*)mxGetData(prhs[3])));
  const int    Ni         = (int)N;

  // grid-stride launch config (the kernels loop, so the grid need not cover N).
  const int threadsPerBlock = 256;
  long long want_blocks = ((long long)N + threadsPerBlock - 1) / threadsPerBlock;
  if (want_blocks < 1)     want_blocks = 1;
  if (want_blocks > 65535) want_blocks = 65535;
  const int numBlocks = (int)want_blocks;

  // --- acquire the input read-only, plus its shape (output is element-wise) ---
  mxGPUArray const* inGPU = NULL;
  mwSize            ndim;
  mwSize const*     dims  = NULL;   // heap (mxFree) when in_on_gpu; else owned by prhs[0]
  const void*       in_host = NULL;
  const void*       in_dev  = NULL;

  if (in_on_gpu) {
    inGPU  = mxGPUCreateFromMxArray(prhs[0]);
    ndim   = mxGPUGetNumberOfDimensions(inGPU);
    dims   = mxGPUGetDimensions(inGPU);
    in_dev = mxGPUGetDataReadOnly(inGPU);
  } else {
    ndim    = mxGetNumberOfDimensions(prhs[0]);
    dims    = mxGetDimensions(prhs[0]);
    in_host = mxGetData(prhs[0]);
  }

  const mxClassID out_class = to_half ? mxUINT16_CLASS : mxSINGLE_CLASS;

  if (out_on_gpu) {
    // -------------------- owned gpuArray output: convert on the GPU --------------------
    mxGPUArray* outGPU = mxGPUCreateGPUArray(ndim, dims, out_class, mxREAL, MX_GPU_DO_NOT_INITIALIZE);
    void* out_dev = mxGPUGetData(outGPU);

    if (to_half) {
      const float* src; float* tmp = NULL;
      if (in_on_gpu) { src = (const float*)in_dev; }
      else {
        checkCudaErrors(cudaMallocAsync(&tmp, N * sizeof(float), cudaStreamPerThread));
        checkCudaErrors(cudaMemcpyAsync(tmp, in_host, N * sizeof(float), cudaMemcpyHostToDevice, cudaStreamPerThread));
        src = tmp;
      }
      convert_fp32_to_fp16<<<numBlocks, threadsPerBlock, 0, cudaStreamPerThread>>>(src, (uint16_t*)out_dev, Ni);
      checkCudaErrors(cudaPeekAtLastError());
      if (tmp) checkCudaErrors(cudaFreeAsync(tmp, cudaStreamPerThread));
    } else {
      const uint16_t* src; uint16_t* tmp = NULL;
      if (in_on_gpu) { src = (const uint16_t*)in_dev; }
      else {
        checkCudaErrors(cudaMallocAsync(&tmp, N * sizeof(uint16_t), cudaStreamPerThread));
        checkCudaErrors(cudaMemcpyAsync(tmp, in_host, N * sizeof(uint16_t), cudaMemcpyHostToDevice, cudaStreamPerThread));
        src = tmp;
      }
      convert_fp16_to_fp32<<<numBlocks, threadsPerBlock, 0, cudaStreamPerThread>>>(src, (float*)out_dev, Ni);
      checkCudaErrors(cudaPeekAtLastError());
      if (tmp) checkCudaErrors(cudaFreeAsync(tmp, cudaStreamPerThread));
    }
    checkCudaErrors(cudaStreamSynchronize(cudaStreamPerThread));

    plhs[0] = mxGPUCreateMxArrayOnGPU(outGPU);   // hand the data to MATLAB
    mxGPUDestroyGPUArray(outGPU);                // wrapper only; data persists via plhs[0]
  } else {
    // -------------------- owned host output: convert on the CPU --------------------
    plhs[0] = mxCreateNumericArray(ndim, dims, out_class, mxREAL);
    void* out_host = mxGetData(plhs[0]);

    if (to_half) {
      const float* src; float* tmp = NULL;
      if (in_on_gpu) {
        checkCudaErrors(cudaMallocHost(&tmp, N * sizeof(float)));
        checkCudaErrors(cudaMemcpy(tmp, in_dev, N * sizeof(float), cudaMemcpyDeviceToHost));
        src = tmp;
      } else { src = (const float*)in_host; }
      half_float::half* dst = (half_float::half*)out_host;
      for (size_t i = 0; i < N; ++i) dst[i] = half_float::half(src[i]);
      if (tmp) checkCudaErrors(cudaFreeHost(tmp));
    } else {
      const uint16_t* src; uint16_t* tmp = NULL;
      if (in_on_gpu) {
        checkCudaErrors(cudaMallocHost(&tmp, N * sizeof(uint16_t)));
        checkCudaErrors(cudaMemcpy(tmp, in_dev, N * sizeof(uint16_t), cudaMemcpyDeviceToHost));
        src = tmp;
      } else { src = (const uint16_t*)in_host; }
      const half_float::half* src_h = (const half_float::half*)src;
      float* dst = (float*)out_host;
      for (size_t i = 0; i < N; ++i) dst[i] = half_float::half_cast<float>(src_h[i]);
      if (tmp) checkCudaErrors(cudaFreeHost(tmp));
    }
  }

  if (in_on_gpu) {
    mxFree((void*)dims);                       // mxGPUGetDimensions allocates this
    mxGPUDestroyGPUArray((mxGPUArray*)inGPU);  // release the read-only input view
  }

  return;
}
