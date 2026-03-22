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

/*
 * CTF computation WITH analytical partial derivatives.
 *
 * Computes the CTF image and its derivatives with respect to:
 *   D     = mean_defocus       (dctf_dD)
 *   A     = half_astigmatism   (dctf_dA)
 *   theta = astigmatism_angle  (dctf_dTheta, in per-degree units)
 *
 * Phase formula (same as ctf_basic):
 *   phase = cs_term * s^4 - df_term * s^2 * (D + A*cos(2*(phi-theta))) - amp_phase
 *
 * Phase derivatives (only the defocus-dependent term contributes):
 *   d(phase)/dD     = -df_term * s^2
 *   d(phase)/dA     = -df_term * s^2 * cos(2*(phi - theta))
 *   d(phase)/dTheta = -2 * df_term * s^2 * A * sin(2*(phi - theta))  [radians]
 *
 * CTF derivatives via chain rule:
 *   Non-squared: dCTF/dX = cos(phase) * d(phase)/dX
 *   Squared:     dCTF/dX = sin(2*phase) * d(phase)/dX
 *
 * The theta derivative is converted to per-degree units by multiplying
 * by PI/180.
 */
extern "C" __global__ void ctf_with_derivatives(
    float* ctf_out, float* dctf_dD, float* dctf_dA, float* dctf_dTheta,
    int nx, int ny, int ox, int oy,
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
    if (calc_centered) {
        y -= oy;
        if (!do_half_grid) { x -= ox; }
    } else {
        if (y > oy) { y = y - out_ny; }
        if (!do_half_grid && x > ox) { x = x - out_nx; }
    }

    /* --- Scale to spatial frequency (1/Angstrom) --- */
    float y_freq = (float)y * fvy;
    float x_freq = (float)x * fvx;

    /* --- Azimuthal angle and squared spatial frequency --- */
    float phi = atan2f(y_freq, x_freq);
    float radius_sq = x_freq * x_freq + y_freq * y_freq;

    /* --- DC pixel: CTF = -sin(amp_phase), all derivatives zero --- */
    if (radius_sq == 0.0f) {
        float sin_amp, cos_amp;
        sincosf(params.amplitudeContrast, &sin_amp, &cos_amp);
        if (params.doSqCTF) {
            ctf_out[output_IDX] = sin_amp * sin_amp;
        } else {
            ctf_out[output_IDX] = -sin_amp;
        }
        dctf_dD[output_IDX]     = 0.0f;
        dctf_dA[output_IDX]     = 0.0f;
        dctf_dTheta[output_IDX] = 0.0f;
        return;
    }

    /* --- Angle terms for astigmatism --- */
    float two_phi_theta = 2.0f * (phi - params.astigmatism_angle);
    float sin2pt, cos2pt;
    sincosf(two_phi_theta, &sin2pt, &cos2pt);

    /* --- CTF phase (identical to ctf_basic) --- */
    float phase = params.cs_term * powf(radius_sq, 2)
                  - params.df_term * radius_sq
                    * (params.mean_defocus
                       + params.half_astigmatism * cos2pt)
                  - params.amplitudeContrast;

    /* --- Phase derivatives w.r.t. defocus parameters --- */
    float neg_df_s2 = -params.df_term * radius_sq;
    float dphase_dD     = neg_df_s2;
    float dphase_dA     = neg_df_s2 * cos2pt;
    /* Sign: d/dtheta[cos(2(phi-theta))] = +2*sin(2(phi-theta)),
     * multiplied by outer factor -df_term*s^2*A gives -2*df_term coefficient.
     * Since neg_df_s2 already contains the minus sign (-df_term*s^2),
     * the factor here is +2. */
    float dphase_dTheta = neg_df_s2 * params.half_astigmatism
                          * 2.0f * sin2pt;

    /* --- Convert theta derivative to per-degree units --- */
    dphase_dTheta *= (PI / 180.0f);

    /* --- CTF value and chain-rule derivatives --- */
    float sin_phase, cos_phase;
    sincosf(phase, &sin_phase, &cos_phase);

    if (params.doSqCTF) {
        /* CTF = sin^2(phase), dCTF/dX = sin(2*phase) * dphase/dX
         * sin(2*phase) = 2*sin(phase)*cos(phase) */
        float sin2phase = 2.0f * sin_phase * cos_phase;
        ctf_out[output_IDX]     = sin_phase * sin_phase;
        dctf_dD[output_IDX]     = sin2phase * dphase_dD;
        dctf_dA[output_IDX]     = sin2phase * dphase_dA;
        dctf_dTheta[output_IDX] = sin2phase * dphase_dTheta;
    } else {
        /* CTF = sin(phase), dCTF/dX = cos(phase) * dphase/dX */
        ctf_out[output_IDX]     = sin_phase;
        dctf_dD[output_IDX]     = cos_phase * dphase_dD;
        dctf_dA[output_IDX]     = cos_phase * dphase_dA;
        dctf_dTheta[output_IDX] = cos_phase * dphase_dTheta;
    }
}
