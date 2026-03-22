/*
 * Standalone CTF parameter struct for CuPy kernel compilation.
 *
 * Extracted from mexFiles/include/core_headers.cuh lines 44-85.
 * All MEX dependencies removed (mex.h, mxGPUArray.h, matrix.h,
 * helper_functions.h, helper_cuda.h).
 *
 * Unit conversions in the constructor match the original C++ code exactly:
 *   CS:       mm  -> Angstrom-compatible (CS * 1e7)
 *   ampContr: ratio -> phase shift via atan(ac / sqrt(1 - ac^2))
 *   defocus:  df1, df2 -> mean_defocus, half_astigmatism
 *   angle:    degrees -> radians normalised to [-pi/2, pi/2]
 *   cs_term:  pi * 0.5 * CS_internal * wavelength^3
 *   df_term:  pi * wavelength
 */

#ifndef EMC_CTF_PARAMS_CUH
#define EMC_CTF_PARAMS_CUH

/* Provide cufftReal typedef so we don't need the full cuFFT header. */
typedef float cufftReal;

const float PI = 3.14159265358979323f;
const float PI_sq = PI * PI;
const float PI_half = 0.5f * PI;

struct ctfParams {

  bool  doHalfGrid;
  bool  doSqCTF;
  float pixelSize;       // Angstrom
  float waveLength;      // Angstrom
  float CS;              // Angstrom-compatible (after 1e7 conversion)
  float amplitudeContrast; // phase shift (after atan conversion)
  float mean_defocus;    // Angstrom
  float half_astigmatism;// Angstrom
  float astigmatism_angle; // radians, normalised to [-pi/2, pi/2]
  float cs_term;         // pre-computed Cs coefficient
  float df_term;         // pre-computed defocus coefficient

  __host__ __device__ ctfParams()
      : doHalfGrid(true), doSqCTF(false),
        pixelSize(0.0f), waveLength(0.0f),
        CS(0.0f), amplitudeContrast(0.0f),
        mean_defocus(0.0f), half_astigmatism(0.0f),
        astigmatism_angle(0.0f),
        cs_term(0.0f), df_term(0.0f) {}

  __host__ __device__ ctfParams(bool doHalfGrid, bool doSqCTF,
                                float pixelSize, float waveLength,
                                float CS, float amplitudeContrast,
                                float df1, float df2,
                                float astigmatism_angle)
      : doHalfGrid(doHalfGrid), doSqCTF(doSqCTF),
        pixelSize(pixelSize), waveLength(waveLength),
        CS(CS * 1e7f),
        amplitudeContrast(atanf(amplitudeContrast /
                                sqrtf(1.0f - powf(amplitudeContrast, 2)))),
        mean_defocus(0.5f * (df1 + df2)),
        half_astigmatism(0.5f * (df1 - df2)),
        astigmatism_angle(astigmatism_angle * PI / 180.0f
                          - (PI * (float)lrintf(astigmatism_angle / 180.0f))),
        cs_term(PI * 0.5f * CS * 1e7f * powf(waveLength, 3)),
        df_term(PI * waveLength) {}
};

#endif /* EMC_CTF_PARAMS_CUH */
