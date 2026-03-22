"""Synthetic data generator for end-to-end CTF refinement validation.

Creates a complete synthetic dataset with known ground-truth CTF parameters:
a 3D reference volume, projections at specified tilt angles, CTF-modulated
particle tiles with per-particle defocus offsets, and star files with
deliberately offset CTF parameters for pipeline recovery testing.

The generation pipeline mirrors the real refinement data flow:

1. Create a 3D Gaussian-blob reference volume.
2. For each tilt group (tilt angle), project the volume at known Euler angles.
3. For each particle:
   a. Apply the *true* CTF (with known defocus + per-particle delta_z).
   b. Add Gaussian noise at specified SNR.
4. Write an MRC stack containing all particle tiles.
5. Write a star file with *offset* CTF parameters (defocus, astigmatism, angle).
6. Write a ground-truth star file for validation.

The offset star file simulates a real-world scenario where initial CTF estimates
are imperfect and the refinement pipeline must recover improved values.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Sequence

import mrcfile
import numpy as np

from ....ctf.emc_ctf_cpu import CTFCalculatorCPU
from ....ctf.emc_ctf_params import CTFParams
from ....ctf.star_io.emc_star_parser import write_star_file
from ...emc_ctf_refine_pipeline import compute_electron_wavelength
from ...emc_fourier_utils import FourierTransformer
from ...emc_tile_prep import (
    spider_zyz_inverse_matrix,
    rotate_volume_trilinear,
    center_crop_or_pad,
    compute_ctf_friendly_size,
    create_2d_soft_mask,
)


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class MicroscopeParams:
    """Microscope and imaging parameters held constant across all particles."""

    pixel_size: float = 1.5          # Angstroms
    voltage_kv: float = 300.0        # kV
    cs_mm: float = 2.7               # mm
    amplitude_contrast: float = 0.07


@dataclasses.dataclass
class GroundTruthCTF:
    """True CTF parameters for a tilt group (before per-particle offsets)."""

    defocus_1: float = 20000.0       # Angstroms
    defocus_2: float = 19000.0       # Angstroms
    defocus_angle: float = 45.0      # degrees


@dataclasses.dataclass
class CTFOffset:
    """Deliberate offset applied to ground-truth CTF for the input star file."""

    defocus_offset: float = 300.0    # Angstroms (added to mean defocus)
    astigmatism_offset: float = 100.0  # Angstroms (added to half-astigmatism)
    angle_offset: float = 5.0        # degrees (added to astigmatism angle)


@dataclasses.dataclass
class ParticleSpec:
    """Specification for a single synthetic particle."""

    euler_phi: float = 0.0           # degrees (SPIDER ZYZ)
    euler_theta: float = 0.0         # degrees
    euler_psi: float = 0.0           # degrees
    delta_z: float = 0.0             # per-particle z-offset (Angstroms)


@dataclasses.dataclass
class TiltGroupSpec:
    """Specification for a synthetic tilt group."""

    tilt_name: str                   # e.g. "tilt_001.mrc"
    tilt_angle: float                # degrees
    particles: list[ParticleSpec]


@dataclasses.dataclass
class SyntheticDataset:
    """Container for all output paths and ground-truth parameters."""

    stack_path: Path
    reference_path: Path
    offset_star_path: Path
    truth_star_path: Path
    ground_truth_ctf: GroundTruthCTF
    ctf_offset: CTFOffset
    microscope: MicroscopeParams
    tilt_groups: list[TiltGroupSpec]
    per_particle_delta_z: list[float]
    tile_size: int
    snr: float


# ---------------------------------------------------------------------------
# Volume generation
# ---------------------------------------------------------------------------


def create_structured_phantom(
    size: int = 64,
) -> np.ndarray:
    """Create a structured 3D phantom with features at multiple scales.

    The phantom contains:
    - A hard-edged sphere (sharp boundary provides high-frequency content
      essential for CTF-sensitive cross-correlation)
    - Several small off-center Gaussian blobs (break symmetry and add
      intermediate-frequency content)

    The hard sphere edge is the critical feature: it produces power at
    spatial frequencies up to Nyquist, where CTF sensitivity to defocus
    changes is strongest.  A single smooth Gaussian concentrates power at
    frequencies where the CTF is nearly constant, making defocus refinement
    impossible.

    Args:
        size: Side length of the cubic volume in voxels.

    Returns:
        Float32 array of shape ``(size, size, size)``.
    """
    c = size // 2
    z, y, x = np.mgrid[0:size, 0:size, 0:size]
    dist = np.sqrt(
        (z - c) ** 2.0 + (y - c) ** 2.0 + (x - c) ** 2.0
    )

    # Hard-edged sphere: radius = size/4 (sharp boundary → high-freq power)
    sphere_radius = size / 4.0
    volume = np.zeros((size, size, size), dtype=np.float32)
    volume[dist <= sphere_radius] = 1.0

    # Add small off-center Gaussian blobs for asymmetry
    blob_positions = [
        (c + size // 8, c, c),
        (c, c + size // 6, c - size // 10),
        (c - size // 8, c - size // 8, c + size // 8),
    ]
    blob_sigma = 2.0  # small sigma → high-frequency content

    for bz, by, bx in blob_positions:
        blob = np.exp(
            -((z - bz) ** 2 + (y - by) ** 2 + (x - bx) ** 2)
            / (2.0 * blob_sigma ** 2)
        ).astype(np.float32)
        volume += 0.5 * blob

    return volume


# ---------------------------------------------------------------------------
# Projection and CTF application
# ---------------------------------------------------------------------------


def _project_volume(
    volume: np.ndarray,
    euler_angles: tuple[float, float, float],
) -> np.ndarray:
    """Rotate volume by SPIDER ZYZ angles and project along Z.

    Args:
        volume: 3D array of shape ``(nz, ny, nx)``.
        euler_angles: ``(phi, theta, psi)`` in degrees.

    Returns:
        2D projection of shape ``(ny, nx)``.
    """
    phi, theta, psi = euler_angles
    rot_matrix = spider_zyz_inverse_matrix(phi, theta, psi)
    rotated = rotate_volume_trilinear(volume, rot_matrix)
    return np.sum(rotated, axis=0).astype(np.float32)


def _apply_ctf_to_tile(
    tile: np.ndarray,
    ctf_params: CTFParams,
    fourier_handler: FourierTransformer,
    ctf_calculator: CTFCalculatorCPU,
) -> np.ndarray:
    """Apply CTF to a 2D tile in Fourier space and return real-space result.

    The tile is padded to CTF-friendly size, FFT'd, multiplied by the CTF,
    then inverse-FFT'd and cropped back.

    Args:
        tile: 2D real-space tile.
        ctf_params: CTF parameters for this particle.
        fourier_handler: Fourier transform handler at CTF size.
        ctf_calculator: CPU CTF calculator.

    Returns:
        CTF-convolved tile at original dimensions.
    """
    nx = fourier_handler.nx
    ny = fourier_handler.ny

    # Pad tile to CTF size
    padded = center_crop_or_pad(tile, (nx, ny))

    # Forward FFT
    spectrum = fourier_handler.forward_fft(padded)

    # Compute CTF image
    ctf_image = ctf_calculator.compute(ctf_params, (nx, ny))
    ctf_image = ctf_image.T  # (nx//2+1, ny) to match FourierTransformer layout

    # Apply CTF
    spectrum_ctf = spectrum * ctf_image

    # Inverse FFT
    result = fourier_handler.inverse_fft(spectrum_ctf)

    # Crop back to original tile size
    return center_crop_or_pad(result, tile.shape).astype(np.float32)


def _add_noise(
    tile: np.ndarray,
    snr: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Add Gaussian noise to a tile at specified signal-to-noise ratio.

    SNR is defined as ``std(signal) / std(noise)``.

    Args:
        tile: 2D signal tile.
        snr: Desired signal-to-noise ratio.
        rng: NumPy random generator.

    Returns:
        Noisy tile (float32).
    """
    signal_std = float(np.std(tile))
    if signal_std < 1e-30:
        # Degenerate signal — just return noise
        return rng.standard_normal(tile.shape).astype(np.float32)
    noise_std = signal_std / snr
    noise = rng.standard_normal(tile.shape).astype(np.float32) * noise_std
    return tile + noise


# ---------------------------------------------------------------------------
# Star file helpers
# ---------------------------------------------------------------------------


def _star_header_lines() -> list[str]:
    """Standard star file header lines matching cisTEM format."""
    labels = [
        "_cisTEMPositionInStack",
        "_cisTEMAnglePsi",
        "_cisTEMAngleTheta",
        "_cisTEMAnglePhi",
        "_cisTEMXShift",
        "_cisTEMYShift",
        "_cisTEMDefocus1",
        "_cisTEMDefocus2",
        "_cisTEMDefocusAngle",
        "_cisTEMPhaseShift",
        "_cisTEMOccupancy",
        "_cisTEMLogP",
        "_cisTEMSigma",
        "_cisTEMScore",
        "_cisTEMScoreChange",
        "_cisTEMPixelSize",
        "_cisTEMVoltage",
        "_cisTEMCs",
        "_cisTEMAmplitudeContrast",
        "_cisTEMBeamTiltX",
        "_cisTEMBeamTiltY",
        "_cisTEMImageShiftX",
        "_cisTEMImageShiftY",
        "_cisTEMBest2DClass",
        "_cisTEMBeamTiltGroup",
        "_cisTEMParticleGroup",
        "_cisTEMPreExposure",
        "_cisTEMTotalExposure",
        "_cisTEMOriginalImageFilename",
        "_cisTEMTiltAngle",
    ]
    lines = ["", "data_", "", "loop_"]
    for label in labels:
        lines.append(label)
    return lines


def _make_particle_dict(
    position: int,
    spec: ParticleSpec,
    tilt_name: str,
    tilt_angle: float,
    df1: float,
    df2: float,
    df_angle: float,
    microscope: MicroscopeParams,
) -> dict:
    """Create a 30-column particle dict for a star file."""
    return {
        "position_in_stack": position,
        "psi": spec.euler_psi,
        "theta": spec.euler_theta,
        "phi": spec.euler_phi,
        "x_shift": 0.0,
        "y_shift": 0.0,
        "defocus_1": df1,
        "defocus_2": df2,
        "defocus_angle": df_angle,
        "phase_shift": 0.0,
        "occupancy": 100.0,
        "logp": 0.0,
        "sigma": 1.0,
        "score": 0.0,
        "score_change": 0.0,
        "pixel_size": microscope.pixel_size,
        "voltage_kv": microscope.voltage_kv,
        "cs_mm": microscope.cs_mm,
        "amplitude_contrast": microscope.amplitude_contrast,
        "beam_tilt_x": 0.0,
        "beam_tilt_y": 0.0,
        "image_shift_x": 0.0,
        "image_shift_y": 0.0,
        "best_2d_class": 1,
        "beam_tilt_group": 1,
        "particle_group": 1,
        "pre_exposure": 0.0,
        "total_exposure": 50.0,
        "original_image_filename": tilt_name,
        "tilt_angle": tilt_angle,
    }


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


def generate_synthetic_dataset(
    output_dir: Path,
    *,
    tile_size: int = 64,
    vol_size: int = 64,
    n_particles_per_tilt: int = 10,
    tilt_angles: Sequence[float] = (-60.0, -30.0, 0.0, 30.0, 60.0),
    ground_truth_ctf: GroundTruthCTF | None = None,
    ctf_offset: CTFOffset | None = None,
    microscope: MicroscopeParams | None = None,
    snr: float = 5.0,
    seed: int = 42,
    delta_z_sigma: float = 30.0,
) -> SyntheticDataset:
    """Generate a complete synthetic dataset for E2E CTF refinement testing.

    Creates reference volume, CTF-modulated particle tiles with noise,
    and star files with offset CTF parameters.

    Args:
        output_dir: Directory to write output files.
        tile_size: Side length of 2D particle tiles.
        vol_size: Side length of 3D reference volume.
        n_particles_per_tilt: Number of particles per tilt group.
        tilt_angles: Tilt angles in degrees for each tilt group.
        ground_truth_ctf: True CTF parameters. Uses defaults if None.
        ctf_offset: Offset to apply for input star file. Uses defaults if None.
        microscope: Microscope parameters. Uses defaults if None.
        snr: Signal-to-noise ratio for noise addition.
        seed: Random seed for reproducibility.
        delta_z_sigma: Std dev for per-particle z-offsets (Angstroms).

    Returns:
        :class:`SyntheticDataset` with all paths and ground-truth values.
    """
    if ground_truth_ctf is None:
        ground_truth_ctf = GroundTruthCTF()
    if ctf_offset is None:
        ctf_offset = CTFOffset()
    if microscope is None:
        microscope = MicroscopeParams()

    rng = np.random.default_rng(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Create reference volume ────────────────────────────────────────
    volume = create_structured_phantom(vol_size)
    ref_path = output_dir / "reference.mrc"
    with mrcfile.new(str(ref_path), overwrite=True) as mrc:
        mrc.set_data(volume)

    # ── 2. Set up CTF calculation infrastructure ──────────────────────────
    wavelength = compute_electron_wavelength(microscope.voltage_kv)
    ctf_calculator = CTFCalculatorCPU()
    ctf_size = compute_ctf_friendly_size(2 * tile_size)
    fourier_handler = FourierTransformer(ctf_size, ctf_size, use_gpu=False)

    # ── 3. Generate particles for each tilt group ─────────────────────────
    tilt_groups: list[TiltGroupSpec] = []
    all_tiles: list[np.ndarray] = []
    truth_particles: list[dict] = []
    offset_particles: list[dict] = []
    all_delta_z: list[float] = []
    position_counter = 0

    # Soft mask for the tile
    mask_radius = tile_size / 2.0 - 1.0
    soft_mask = create_2d_soft_mask(
        tile_size, tile_size, radius=mask_radius, edge_width=7.0,
    )

    # Ground truth mean defocus and half-astigmatism
    gt_mean_df = (ground_truth_ctf.defocus_1 + ground_truth_ctf.defocus_2) / 2.0
    gt_half_astig = (ground_truth_ctf.defocus_1 - ground_truth_ctf.defocus_2) / 2.0

    for tilt_angle in tilt_angles:
        tilt_name = f"tilt_{tilt_angle:+06.1f}.mrc"
        cos_tilt = np.cos(np.radians(tilt_angle))

        particle_specs: list[ParticleSpec] = []

        for _ in range(n_particles_per_tilt):
            position_counter += 1

            # Random Euler angles for variety
            phi = rng.uniform(0, 360)
            theta = rng.uniform(0, 30)  # modest tilt range
            psi = rng.uniform(0, 360)

            # Per-particle z-offset
            dz = float(rng.normal(0, delta_z_sigma))
            all_delta_z.append(dz)

            spec = ParticleSpec(
                euler_phi=phi,
                euler_theta=theta,
                euler_psi=psi,
                delta_z=dz,
            )
            particle_specs.append(spec)

            # ── Project volume ────────────────────────────────────────
            projection = _project_volume(
                volume, (phi, theta, psi),
            )
            # Crop/pad projection to tile_size
            projection = center_crop_or_pad(
                projection, (tile_size, tile_size),
            )

            # ── Apply true CTF with per-particle z-offset ────────────
            # Effective defocus for this particle
            dz_contribution = dz * cos_tilt
            eff_df1 = ground_truth_ctf.defocus_1 + dz_contribution
            eff_df2 = ground_truth_ctf.defocus_2 + dz_contribution

            true_ctf_params = CTFParams.from_defocus_pair(
                df1=eff_df1,
                df2=eff_df2,
                angle_degrees=ground_truth_ctf.defocus_angle,
                pixel_size=microscope.pixel_size,
                wavelength=wavelength,
                cs_mm=microscope.cs_mm,
                amplitude_contrast=microscope.amplitude_contrast,
                do_half_grid=True,
                do_sq_ctf=False,
            )

            ctf_tile = _apply_ctf_to_tile(
                projection, true_ctf_params, fourier_handler, ctf_calculator,
            )

            # ── Add noise ─────────────────────────────────────────────
            noisy_tile = _add_noise(ctf_tile, snr, rng)
            all_tiles.append(noisy_tile)

            # ── Build ground-truth particle dict ──────────────────────
            truth_particles.append(
                _make_particle_dict(
                    position=position_counter,
                    spec=spec,
                    tilt_name=tilt_name,
                    tilt_angle=tilt_angle,
                    df1=ground_truth_ctf.defocus_1,
                    df2=ground_truth_ctf.defocus_2,
                    df_angle=ground_truth_ctf.defocus_angle,
                    microscope=microscope,
                )
            )

            # ── Build offset particle dict ────────────────────────────
            # Apply offsets to mean defocus and half-astigmatism,
            # then convert back to df1/df2
            offset_mean = gt_mean_df + ctf_offset.defocus_offset
            offset_half = gt_half_astig + ctf_offset.astigmatism_offset
            offset_df1 = offset_mean + offset_half
            offset_df2 = offset_mean - offset_half
            offset_angle = (
                ground_truth_ctf.defocus_angle + ctf_offset.angle_offset
            )

            offset_particles.append(
                _make_particle_dict(
                    position=position_counter,
                    spec=spec,
                    tilt_name=tilt_name,
                    tilt_angle=tilt_angle,
                    df1=offset_df1,
                    df2=offset_df2,
                    df_angle=offset_angle,
                    microscope=microscope,
                )
            )

        tilt_groups.append(
            TiltGroupSpec(
                tilt_name=tilt_name,
                tilt_angle=tilt_angle,
                particles=particle_specs,
            )
        )

    # ── 4. Write MRC stack ────────────────────────────────────────────────
    stack_data = np.stack(all_tiles, axis=0)
    stack_path = output_dir / "particles.mrc"
    with mrcfile.new(str(stack_path), overwrite=True) as mrc:
        mrc.set_data(stack_data)

    # ── 5. Write star files ───────────────────────────────────────────────
    header = _star_header_lines()

    offset_star_path = output_dir / "input_offset.star"
    write_star_file(offset_star_path, offset_particles, header)

    truth_star_path = output_dir / "ground_truth.star"
    write_star_file(truth_star_path, truth_particles, header)

    return SyntheticDataset(
        stack_path=stack_path,
        reference_path=ref_path,
        offset_star_path=offset_star_path,
        truth_star_path=truth_star_path,
        ground_truth_ctf=ground_truth_ctf,
        ctf_offset=ctf_offset,
        microscope=microscope,
        tilt_groups=tilt_groups,
        per_particle_delta_z=all_delta_z,
        tile_size=tile_size,
        snr=snr,
    )


def compute_snr_of_tiles(
    stack_path: Path,
) -> float:
    """Estimate the SNR of generated tiles by comparing signal to noise.

    Computes ``std(signal) / std(noise)`` where signal is the mean tile
    and noise is the per-tile residual from the mean.  This is an empirical
    check that the specified SNR was applied correctly.

    Args:
        stack_path: Path to the MRC particle stack.

    Returns:
        Estimated SNR as a float.
    """
    with mrcfile.open(str(stack_path), mode="r") as mrc:
        data = mrc.data.copy()

    if data.ndim != 3 or data.shape[0] < 2:
        raise ValueError("Need at least 2 tiles for SNR estimation")

    # Mean signal across all tiles
    mean_tile = np.mean(data, axis=0)
    signal_std = float(np.std(mean_tile))

    # Noise: residual from mean
    residuals = data - mean_tile[np.newaxis, :, :]
    noise_std = float(np.std(residuals))

    if noise_std < 1e-30:
        return float("inf")

    return signal_std / noise_std
