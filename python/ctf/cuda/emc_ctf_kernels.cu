/*
 * CUDA CTF computation kernel for CuPy RawModule compilation.
 *
 * Ported from mexFiles/utils/ctf.cu lines 12-65 (basic CTF kernel).
 * The kernel takes flat parameters rather than the ctfParams struct
 * directly, since CuPy passes individual arguments.  Internally it
 * constructs ctfParams to perform the unit conversions and then
 * evaluates the CTF formula.
 *
 * Output layout: C-contiguous (row-major), shape (ny, out_nx) where
 *   out_nx = nx/2+1  when do_half_grid is true
 *   out_nx = nx       when do_half_grid is false
 *
 * Memory indexing: output[y * out_nx + x]  (y = row, x = column).
 */

#include "emc_ctf_params.cuh"

extern "C" __global__ void ctf_basic(
    float* output, int nx, int ny, int ox, int oy,
    bool do_half_grid, bool do_sq_ctf,
    float pixel_size, float wavelength, float cs_mm,
    float amp_contrast, float df1, float df2, float angle_deg,
    bool calc_centered)
{
    /* --- Derive output dimensions from real-space dims --- */
    int out_nx = do_half_grid ? nx / 2 + 1 : nx;
    int out_ny = ny;

    /* --- Thread-to-pixel mapping (x = column, y = row) --- */
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    if (x >= out_nx) return;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    if (y >= out_ny) return;

    /* --- Construct ctfParams (unit conversions happen here) --- */
    ctfParams params(do_half_grid, do_sq_ctf,
                     pixel_size, wavelength, cs_mm,
                     amp_contrast, df1, df2, angle_deg);

    /* --- Fourier-space voxel sizes (1 / (pixel_size * N)) --- */
    float fvx = 1.0f / (pixel_size * (float)nx);
    float fvy = 1.0f / (pixel_size * (float)ny);

    /* --- Output index in row-major order --- */
    long output_IDX = (long)y * out_nx + x;

    /* --- Convert grid indices to signed frequency coordinates --- */
    /* Matches ctf.cu lines 31-40 exactly. */
    if (calc_centered) {
        y -= oy;
        if (!do_half_grid) { x -= ox; }
    } else {
        if (y > oy) { y = y - out_ny; }
        if (!do_half_grid && x > ox) { x = x - out_nx; }
    }

    /* --- Scale to spatial frequency (1/Angstrom) --- */
    float tmp_coord = (float)y * fvy;
    float radius_sq = (float)x * fvx;

    /* --- Azimuthal angle and squared radius --- */
    float phi = atan2f(tmp_coord, radius_sq);
    radius_sq = radius_sq * radius_sq + tmp_coord * tmp_coord;

    /* --- CTF evaluation (matches ctf.cu lines 56-63) --- */
    if (params.doSqCTF) {
        tmp_coord = sinf(
            params.cs_term * powf(radius_sq, 2)
            - params.df_term * radius_sq
              * (params.mean_defocus
                 + params.half_astigmatism
                   * cosf(2.0f * (phi - params.astigmatism_angle)))
            - params.amplitudeContrast);
        output[output_IDX] = tmp_coord * tmp_coord;
    } else {
        output[output_IDX] = sinf(
            params.cs_term * powf(radius_sq, 2)
            - params.df_term * radius_sq
              * (params.mean_defocus
                 + params.half_astigmatism
                   * cosf(2.0f * (phi - params.astigmatism_angle)))
            - params.amplitudeContrast);
    }
}
