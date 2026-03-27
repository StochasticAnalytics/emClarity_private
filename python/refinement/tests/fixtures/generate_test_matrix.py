#!/usr/bin/env python3
"""Generate CTF refinement test matrix fixtures using real ribosome data.

Uses the Baxter et al. (2009) two-stage noise model:
  1. Project → normalize(0,1)
  2. Add structural noise N(0,1) → SNR_structural = 1 (power ratio)
  3. FFT → apply CTF → iFFT
  4. Renormalize to (0,1)
  5. Add shot noise → SNR_final (power ratio: Var(signal)/Var(noise))

Test matrix: 4 defocus x 2 astigmatism x 3 angles = 24 CTF conditions.
Each condition gets 10 particles at one tilt angle (0°) with per-particle dz.

Saves pre-shot-noise images to /tmp/claude-1000/ctf_visual/ for inspection.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import mrcfile
import numpy as np

# Imports: python/ is a package with sub-packages ctf/, refinement/.
# Run with: PYTHONPATH=<project_root> python3 /tmp/claude-1000/generate_test_matrix.py
PROJECT_ROOT = "/sa_shared/git/emClarity_private/worktrees/build_command_center_dashboard"
sys.path.insert(0, PROJECT_ROOT)

from python.ctf.emc_ctf_cpu import CTFCalculatorCPU
from python.ctf.emc_ctf_params import CTFParams
from python.ctf.star_io.emc_star_parser import write_star_file
from python.refinement.emc_ctf_refine_pipeline import compute_electron_wavelength
from python.refinement.emc_fourier_utils import FourierTransformer
from python.refinement.emc_tile_prep import (
    center_crop_or_pad,
    compute_ctf_friendly_size,
    rotate_volume_trilinear,
    spider_zyz_inverse_matrix,
)

# ---------------------------------------------------------------------------
# Test matrix parameters (PI-approved)
# ---------------------------------------------------------------------------

DEFOCUS_MEANS = [3000.0, 9000.0, 18000.0, 36000.0]  # Angstroms
HALF_ASTIGS = [50.0, 500.0]                            # Angstroms
ANGLES = [5.0, 50.0, 95.0]                            # degrees (off symmetry axes)

# Microscope (matches ribosome data: 300kV, Cs=2.7mm, ac=0.07)
PIXEL_SIZE = 1.2       # Angstroms (from ribo_ref.mrc voxel_size)
VOLTAGE_KV = 300.0
CS_MM = 2.7
AMP_CONTRAST = 0.07

# Noise model (Baxter et al. 2009)
SNR_STRUCTURAL = 1.0   # Pre-CTF structural noise (power ratio)
SNR_SHOT = 0.1          # Post-CTF shot noise (power ratio)

# Particles
N_PARTICLES_PER_CONDITION = 10
TILT_ANGLE = 0.0        # Single tilt for simplicity
DELTA_Z_SIGMA = 30.0    # Per-particle z-offset std (Angstroms)

# Perturbation sizes for optimizer recovery testing
PERTURBATIONS = {
    "small": {"defocus": 100.0, "astig": 30.0, "angle": 2.0},
    "large": {"defocus": 500.0, "astig": 150.0, "angle": 8.0},
}

SEED = 42
RIBOSOME_PATH = Path("/cisTEMdev/cistem_reference_images/ribo_ref.mrc")


# ---------------------------------------------------------------------------
# Baxter et al. noise pipeline
# ---------------------------------------------------------------------------

def apply_baxter_noise(
    projection: np.ndarray,
    ctf_params: CTFParams,
    fourier_handler: FourierTransformer,
    ctf_calculator: CTFCalculatorCPU,
    rng: np.random.Generator,
    snr_structural: float = 1.0,
    snr_shot: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply Baxter et al. two-stage noise model.

    Returns (noisy_tile, pre_shot_tile) where pre_shot_tile has CTF
    applied but no shot noise (for visual CTF inspection).

    SNR is power ratio: Var(signal) / Var(noise).
    """
    nx = fourier_handler.nx
    ny = fourier_handler.ny

    # Step 1-2: Normalize projection to (0, 1)
    tile = projection.copy().astype(np.float32)
    tile_mean = float(np.mean(tile))
    tile_std = float(np.std(tile))
    if tile_std > 1e-30:
        tile = (tile - tile_mean) / tile_std

    # Step 3: Add structural noise pre-CTF (SNR = power ratio)
    # Var(signal) = 1.0, Var(noise) = 1/SNR_structural
    struct_noise_std = 1.0 / np.sqrt(snr_structural)
    structural_noise = rng.standard_normal(tile.shape).astype(np.float32)
    tile = tile + struct_noise_std * structural_noise

    # Step 4: Pad to CTF size
    padded = center_crop_or_pad(tile, (nx, ny))

    # Step 5: FFT → apply CTF → iFFT
    spectrum = fourier_handler.forward_fft(padded)
    ctf_image = ctf_calculator.compute(ctf_params, (nx, ny))
    # CPU calculator returns (ny, nx//2+1); FourierTransformer uses (nx//2+1, ny)
    ctf_image = ctf_image.T
    spectrum_ctf = spectrum * ctf_image
    result = fourier_handler.inverse_fft(spectrum_ctf)

    # Crop back to tile size
    result = center_crop_or_pad(result, projection.shape).astype(np.float32)

    # Step 6: Renormalize to (0, 1) — makes shot noise SNR well-defined
    result_mean = float(np.mean(result))
    result_std = float(np.std(result))
    if result_std > 1e-30:
        result = (result - result_mean) / result_std

    # Save pre-shot-noise copy for visual inspection
    pre_shot = result.copy()

    # Step 7: Add shot noise (SNR = power ratio)
    # Var(signal) = 1.0 (renormalized), Var(noise) = 1/SNR_shot
    shot_noise_std = 1.0 / np.sqrt(snr_shot)
    shot_noise = rng.standard_normal(result.shape).astype(np.float32)
    result = result + shot_noise_std * shot_noise

    return result, pre_shot


# ---------------------------------------------------------------------------
# Star file helpers
# ---------------------------------------------------------------------------

def make_star_header() -> list[str]:
    """Standard 30-column cisTEM star header."""
    labels = [
        "_cisTEMPositionInStack", "_cisTEMAnglePsi", "_cisTEMAngleTheta",
        "_cisTEMAnglePhi", "_cisTEMXShift", "_cisTEMYShift",
        "_cisTEMDefocus1", "_cisTEMDefocus2", "_cisTEMDefocusAngle",
        "_cisTEMPhaseShift", "_cisTEMOccupancy", "_cisTEMLogP",
        "_cisTEMSigma", "_cisTEMScore", "_cisTEMScoreChange",
        "_cisTEMPixelSize", "_cisTEMVoltage", "_cisTEMCs",
        "_cisTEMAmplitudeContrast", "_cisTEMBeamTiltX", "_cisTEMBeamTiltY",
        "_cisTEMImageShiftX", "_cisTEMImageShiftY", "_cisTEMBest2DClass",
        "_cisTEMBeamTiltGroup", "_cisTEMParticleGroup", "_cisTEMPreExposure",
        "_cisTEMTotalExposure", "_cisTEMOriginalImageFilename", "_cisTEMTiltAngle",
    ]
    return ["", "data_", "", "loop_", *labels]


def make_particle_dict(
    position: int, euler: tuple[float, float, float],
    df1: float, df2: float, df_angle: float,
    tilt_name: str, tilt_angle: float,
) -> dict:
    """Create a 30-column particle dict."""
    return {
        "position_in_stack": position,
        "psi": euler[2], "theta": euler[1], "phi": euler[0],
        "x_shift": 0.0, "y_shift": 0.0,
        "defocus_1": df1, "defocus_2": df2,
        "defocus_angle": df_angle, "phase_shift": 0.0,
        "occupancy": 100.0, "logp": 0.0, "sigma": 1.0,
        "score": 0.0, "score_change": 0.0,
        "pixel_size": PIXEL_SIZE, "voltage_kv": VOLTAGE_KV,
        "cs_mm": CS_MM, "amplitude_contrast": AMP_CONTRAST,
        "beam_tilt_x": 0.0, "beam_tilt_y": 0.0,
        "image_shift_x": 0.0, "image_shift_y": 0.0,
        "best_2d_class": 1, "beam_tilt_group": 1,
        "particle_group": 1, "pre_exposure": 0.0,
        "total_exposure": 50.0,
        "original_image_filename": tilt_name,
        "tilt_angle": tilt_angle,
    }


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def main():
    output_base = Path("/tmp/claude-1000/ctf_test_matrix")
    visual_dir = Path("/tmp/claude-1000/ctf_visual")
    output_base.mkdir(parents=True, exist_ok=True)
    visual_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(SEED)
    wavelength = compute_electron_wavelength(VOLTAGE_KV)

    # ── Load ribosome reference ──────────────────────────────────────────
    print(f"Loading ribosome reference from {RIBOSOME_PATH}...")
    with mrcfile.open(str(RIBOSOME_PATH), mode='r') as mrc:
        volume = mrc.data.copy().astype(np.float32)
    vol_size = volume.shape[0]
    tile_size = vol_size  # Use full 384x384 tiles
    print(f"  Volume: {volume.shape}, pixel_size={PIXEL_SIZE}A")

    # ── Generate one projection (sufficient per PI) ──────────────────────
    # Use a non-trivial orientation
    euler = (37.0, 22.0, 158.0)  # phi, theta, psi — arbitrary, off-axis
    rot = spider_zyz_inverse_matrix(*euler)
    rotated = rotate_volume_trilinear(volume, rot)
    base_projection = np.sum(rotated, axis=0).astype(np.float32)
    print(f"  Projection: {base_projection.shape}, "
          f"range=[{base_projection.min():.4e}, {base_projection.max():.4e}]")

    # Save raw projection for reference
    with mrcfile.new(str(visual_dir / "raw_projection.mrc"), overwrite=True) as mrc:
        mrc.set_data(base_projection)

    # ── CTF infrastructure ───────────────────────────────────────────────
    ctf_calculator = CTFCalculatorCPU()
    ctf_size = compute_ctf_friendly_size(2 * tile_size)
    fourier_handler = FourierTransformer(ctf_size, ctf_size, use_gpu=False)
    print(f"  CTF size: {ctf_size}, tile_size: {tile_size}")

    # ── Generate test matrix ─────────────────────────────────────────────
    condition_index = 0
    manifest = []

    for mean_df in DEFOCUS_MEANS:
        for half_astig in HALF_ASTIGS:
            for angle_deg in ANGLES:
                condition_index += 1
                df1 = mean_df + half_astig
                df2 = mean_df - half_astig

                condition_name = (
                    f"cond_{condition_index:03d}_"
                    f"df{int(mean_df)}_"
                    f"ha{int(half_astig)}_"
                    f"ang{int(angle_deg)}"
                )
                cond_dir = output_base / condition_name
                cond_dir.mkdir(parents=True, exist_ok=True)

                print(f"\n[{condition_index}/24] {condition_name}")
                print(f"  df1={df1:.0f}, df2={df2:.0f}, angle={angle_deg:.0f}°")

                cos_tilt = np.cos(np.radians(TILT_ANGLE))
                all_tiles = []
                pre_shot_tiles = []
                truth_particles = []
                offset_particles_small = []
                offset_particles_large = []
                particle_delta_zs = []

                tilt_name = f"tilt_{TILT_ANGLE:+06.1f}.mrc"

                for p_idx in range(N_PARTICLES_PER_CONDITION):
                    position = p_idx + 1  # 1-indexed

                    # Per-particle z-offset
                    dz = float(rng.normal(0, DELTA_Z_SIGMA))
                    particle_delta_zs.append(dz)
                    dz_contribution = dz * cos_tilt

                    # True CTF params with z-offset
                    eff_df1 = df1 + dz_contribution
                    eff_df2 = df2 + dz_contribution

                    true_params = CTFParams.from_defocus_pair(
                        df1=eff_df1, df2=eff_df2,
                        angle_degrees=angle_deg,
                        pixel_size=PIXEL_SIZE,
                        wavelength=wavelength,
                        cs_mm=CS_MM,
                        amplitude_contrast=AMP_CONTRAST,
                        do_half_grid=True, do_sq_ctf=False,
                    )

                    # Apply Baxter noise model
                    noisy_tile, pre_shot = apply_baxter_noise(
                        base_projection, true_params,
                        fourier_handler, ctf_calculator, rng,
                        snr_structural=SNR_STRUCTURAL,
                        snr_shot=SNR_SHOT,
                    )

                    all_tiles.append(noisy_tile)
                    if p_idx == 0:
                        pre_shot_tiles.append(pre_shot)

                    # Truth particle dict
                    truth_particles.append(make_particle_dict(
                        position, euler, df1, df2, angle_deg,
                        tilt_name, TILT_ANGLE,
                    ))

                    # Offset particle dicts (small and large perturbations)
                    for pert_name, pert in PERTURBATIONS.items():
                        offset_mean = mean_df + pert["defocus"]
                        offset_half = half_astig + pert["astig"]
                        offset_df1 = offset_mean + offset_half
                        offset_df2 = offset_mean - offset_half
                        offset_angle = angle_deg + pert["angle"]
                        p_dict = make_particle_dict(
                            position, euler,
                            offset_df1, offset_df2, offset_angle,
                            tilt_name, TILT_ANGLE,
                        )
                        if pert_name == "small":
                            offset_particles_small.append(p_dict)
                        else:
                            offset_particles_large.append(p_dict)

                # Save MRC stack
                stack = np.stack(all_tiles, axis=0).astype(np.float32)
                stack_path = cond_dir / "particles.mrc"
                with mrcfile.new(str(stack_path), overwrite=True) as mrc:
                    mrc.set_data(stack)

                # Save pre-shot-noise image for visual CTF inspection
                pre_shot_path = visual_dir / f"{condition_name}_pre_shot.mrc"
                with mrcfile.new(str(pre_shot_path), overwrite=True) as mrc:
                    mrc.set_data(pre_shot_tiles[0])

                # Save reference volume (symlink to avoid duplication)
                ref_path = cond_dir / "reference.mrc"
                if not ref_path.exists():
                    ref_path.symlink_to(RIBOSOME_PATH)

                # Save star files
                header = make_star_header()
                truth_star = cond_dir / "truth.star"
                write_star_file(truth_star, truth_particles, header)

                for pert_name, particles in [
                    ("small", offset_particles_small),
                    ("large", offset_particles_large),
                ]:
                    offset_star = cond_dir / f"offset_{pert_name}.star"
                    write_star_file(offset_star, particles, header)

                # Save condition metadata
                meta = {
                    "condition_index": condition_index,
                    "mean_defocus": mean_df,
                    "half_astigmatism": half_astig,
                    "defocus_angle": angle_deg,
                    "df1": df1, "df2": df2,
                    "pixel_size": PIXEL_SIZE,
                    "wavelength": wavelength,
                    "snr_structural": SNR_STRUCTURAL,
                    "snr_shot": SNR_SHOT,
                    "n_particles": N_PARTICLES_PER_CONDITION,
                    "tilt_angle": TILT_ANGLE,
                    "delta_z_sigma": DELTA_Z_SIGMA,
                    "particle_delta_zs": particle_delta_zs,
                    "perturbations": PERTURBATIONS,
                }
                with open(cond_dir / "metadata.json", "w") as f:
                    json.dump(meta, f, indent=2)

                manifest.append(meta)

    # Save overall manifest
    with open(output_base / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Generated {condition_index} conditions")
    print(f"  Output: {output_base}")
    print(f"  Visual CTF inspection: {visual_dir}")
    print(f"  Pre-shot-noise MRCs: {len(list(visual_dir.glob('*_pre_shot.mrc')))} files")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
