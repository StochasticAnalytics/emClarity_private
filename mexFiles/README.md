# mexFiles — GPU memory ownership in the CUDA MEX routines

These MEX functions exchange `gpuArray` data with MATLAB through the
**mxGPUArray** C API (`gpu/mxGPUArray.h`). The data buffers are **shared and
reference-counted**: an `mxGPUArray` is a *handle/wrapper* around a device
buffer, not the buffer itself, and several handles (plus the MATLAB-side
`mxArray`) can reference the same device memory. Getting the ownership right is
the difference between a correct routine and one that silently returns zeros or
leaks. This note records the mechanisms in use and why they work.

## The shared-pointer model

Three calls and one rule:

- `mxGPUCreateFromMxArray(prhs[i])` → a **read-only** handle that *shares* the
  caller's input device buffer (no copy). Read its data with
  `mxGPUGetDataReadOnly`. **Do not write through it** — it aliases the caller's
  variable, and the writable pointer you can cast out of it is not guaranteed to
  reach the MATLAB variable. Destroy the handle when done (`mxGPUDestroyGPUArray`);
  that only drops this reference, it does not free the caller's data.

- `mxGPUCreateGPUArray(ndim, dims, class, complexity, MX_GPU_DO_NOT_INITIALIZE)`
  → **allocates a new device buffer** that this MEX owns. Get a writable pointer
  with `mxGPUGetData` and run the kernel into it. (`MX_GPU_DO_NOT_INITIALIZE`
  skips the zero-fill when the kernel writes every element.)

- `plhs[0] = mxGPUCreateMxArrayOnGPU(outGPU)` → wraps that buffer in an `mxArray`
  for return. **An `mxArray` now references the buffer.**

The rule that makes it all safe (per the MathWorks docs for
`mxGPUDestroyGPUArray`): destroying the handle *"clears memory on the GPU,
**unless some other mxArray holds a reference to the same data** … if the
mxGPUArray was extracted from an input mxArray, or wrapped in an mxArray for an
output, then the data remains on the GPU."*

So the canonical lifecycle is:

```c
mxGPUArray* outGPU = mxGPUCreateGPUArray(ndim, dims, cls, mxREAL, MX_GPU_DO_NOT_INITIALIZE);
kernel<<<...>>>( ..., (T*)mxGPUGetData(outGPU), N);   // fill the owned buffer
plhs[0] = mxGPUCreateMxArrayOnGPU(outGPU);            // hand a reference to MATLAB
mxGPUDestroyGPUArray(outGPU);                         // drop OUR handle; data lives on via plhs[0]
```

After this the returned value is an ordinary MATLAB `gpuArray`: MATLAB
reference-counts and frees it when the capturing variable is cleared,
overwritten, or goes out of scope — identical to `new = gpuArray(x)`, no manual
free, no leak (as long as the `CreateMxArrayOnGPU` + `DestroyGPUArray` pair is
honored), no double free. Pair every `mxGPUCreateFromMxArray` and
`mxGPUCreateGPUArray` with a `mxGPUDestroyGPUArray`. Call `mxInitGPU()` once
before any other mxGPU call.

### The anti-pattern (what to avoid)

Do **not** write results into a buffer obtained from `mxGPUCreateFromMxArray`
(a read-only, shared input view) and rely on the write being visible to the
caller — and do not skip allocating/returning an owned output. A routine that
does this computes into a buffer MATLAB never sees; the caller's
pre-allocated output stays at its initialized value (all zeros), which then
propagates to NaNs downstream. `mexFP16` had exactly this defect and was
rewritten to the canonical create-and-return pattern above.

### Persistent handles (a separate mechanism)

cuFFT plans, CUDA texture/`cudaArray` objects, and cuBLAS handles are *not*
device data arrays. They are returned as small numeric `mxArray`s holding the
handle and kept alive across calls with `mexMakeArrayPersistent`, then reused
(and explicitly destroyed) on later invocations. This is orthogonal to the data
ownership above.

## Which file currently uses which mechanism

| File | GPU input | Owned output alloc | Returns to MATLAB | Other |
|------|-----------|--------------------|-------------------|-------|
| `mexFFT.cu`     | read-only view (`FromMxArray` + `GetDataReadOnly`) | `mxGPUCreateGPUArray` | `plhs[0]` gpu data | persistent cuFFT plans in `plhs[1..2]` (`mexMakeArrayPersistent`) |
| `mexCTF.cu`     | none — built from scalar params | `mxGPUCreateGPUArray` | `plhs[0]` gpu data | `mxInitGPU`; output-only create-and-return |
| `mexXform3d.cu` | read-only view | `mxGPUCreateGPUArray` | `plhs[0]` gpu data | persistent texture/`cudaArray` handles; raw `cudaMalloc3DArray` for the texture |
| `mexXform2d.cu` | read-only view (two entry points) | `mxGPUCreateGPUArray` | `plhs[0]` gpu data | persistent texture handles; raw `cudaMallocArray` |
| `mexSF3D.cu`    | none — built from params | `mxGPUCreateGPUArray` | `plhs[0]` gpu data | `mxInitGPU`; raw `cudaMalloc`/`cudaMallocArray` scratch (freed internally) |
| `mexCuBlas.cu`  | none | none | `plhs[0]` = persistent cuBLAS handle | handle factory only; raw `cudaMalloc` scratch; `mxInitGPU` |
| `mexFP16.cu`    | read-only view *or* host array | `mxGPUCreateGPUArray` (gpu out) / `mxCreateNumericArray` (host out) | `plhs[0]` gpu or host | `mxInitGPU`; raw `cudaMalloc` host↔device staging; converts on the GPU |

Common pattern across the data-transform routines (`mexFFT`, `mexCTF`,
`mexXform2d/3d`, `mexSF3D`, `mexFP16`): **read inputs read-only, allocate the
output with `mxGPUCreateGPUArray`, return it with `mxGPUCreateMxArrayOnGPU`, and
destroy only the handles.** `mexCuBlas` is the odd one out — it just manufactures
a persistent cuBLAS handle and does no data transform.

## Build

`mexCompile('<name>')` compiles `mexFiles/<name>.cu` with `mexcuda` and moves the
resulting `.mexa64` into `mexFiles/compiled/`. `mexCompile()` with no args builds
the default set `{mexCTF, mexFFT, mexXform3d, mexSF3D, mexFP16}`.
