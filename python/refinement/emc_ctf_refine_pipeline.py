"""Pipeline orchestrator for CTF refinement from star files.

Reads a cisTEM-style 30-column star file, groups particles by tilt image,
runs per-tilt CTF refinement via :func:`refine_tilt_ctf`, and writes a
refined star file with updated defocus, shift, and score columns.

Port reference: ``ctf/EMC_ctf_refine_from_star.m`` (850 lines).

Pipeline stages::

    1. Parse star file (TASK-001 star_io)
    2. Read MRC stack header for image dimensions
    3. Read reference volume
    4. Compute CTF-friendly pad size (~2x tile size)
    5. Group particles by tilt
    6. For each tilt group:
       a. Load particle tiles from MRC stack
       b. Generate reference projections (TASK-012a)
       c. Prepare data tiles (TASK-012a)
       d. Run per-tilt CTF refinement (TASK-011)
       e. Apply refined parameters to particle dicts
       f. GPU memory cleanup
    7. Write refined star file with updated columns

This initial implementation uses single-GPU sequential processing.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

import numpy as np

try:
    import cupy as cp

    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False
    cp = None

from ..ctf.emc_ctf_params import CTFParams
from ..ctf.star_io.emc_star_parser import (
    group_particles_by_tilt,
    parse_star_file,
    write_star_file,
)
from ..image_io.mrc_image import MRCImage
from .emc_fourier_utils import FourierTransformer
from .emc_refine_tilt_ctf import RefinementOptions, RefinementResults, refine_tilt_ctf
from .emc_tile_prep import (
    compute_ctf_friendly_size,
    create_2d_soft_mask,
    prepare_data_tile,
    prepare_reference_projection,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class PipelineOptions:
    """Configuration for the full CTF refinement pipeline.

    Maps pipeline-level settings to the per-tilt
    :class:`~python.refinement.emc_refine_tilt_ctf.RefinementOptions`.

    Attributes:
        optimizer_type: Optimiser algorithm — ``'adam'`` or ``'lbfgsb'``.
        defocus_search_range: Symmetric bound on delta defocus (Angstroms).
        maximum_iterations: Hard iteration cap per tilt group.
        minimum_global_iterations: Iterations with only tilt-global parameters
            before unfreezing per-particle delta-z.
        global_only: When True, per-particle parameters are never unfrozen.
        lowpass_cutoff: Low-pass cutoff in Angstroms.
        highpass_cutoff: High-pass cutoff in Angstroms.
        shift_sigma: Gaussian penalty sigma for X/Y shifts (pixels).
        z_offset_sigma: Gaussian penalty sigma for per-particle z-offsets
            (Angstroms).
        soft_mask_edge_width: Edge width in pixels for the 2D soft circular
            mask applied to tiles before processing.
    """

    optimizer_type: str = "adam"
    defocus_search_range: float = 5000.0
    maximum_iterations: int = 15
    minimum_global_iterations: int = 3
    global_only: bool = False
    lowpass_cutoff: float = 10.0
    highpass_cutoff: float = 400.0
    shift_sigma: float = 5.0
    z_offset_sigma: float = 100.0
    soft_mask_edge_width: float = 7.0


@dataclasses.dataclass
class TiltGroupResult:
    """Summary of refinement for a single tilt group.

    Attributes:
        tilt_name: Original image filename identifying this tilt.
        tilt_angle: Tilt angle in degrees.
        n_particles: Number of particles in this group.
        n_iterations: Number of optimisation iterations run.
        converged: Whether the optimiser converged.
        mean_score: Mean per-particle cross-correlation score.
        refinement_results: Full :class:`RefinementResults` from the
            per-tilt refinement.
    """

    tilt_name: str
    tilt_angle: float
    n_particles: int
    n_iterations: int
    converged: bool
    mean_score: float
    refinement_results: RefinementResults


@dataclasses.dataclass
class PipelineResults:
    """Summary of the full CTF refinement pipeline run.

    Attributes:
        n_particles_total: Total number of particles in the input star file.
        n_particles_processed: Number of particles that were refined.
        n_tilt_groups: Number of tilt groups processed.
        tilt_group_results: Per-tilt summaries.
    """

    n_particles_total: int
    n_particles_processed: int
    n_tilt_groups: int
    tilt_group_results: list[TiltGroupResult]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def compute_electron_wavelength(voltage_kv: float) -> float:
    """Compute relativistic electron wavelength from accelerating voltage.

    Uses the relativistic de Broglie formula::

        wavelength = 12.2643 / sqrt(V * (1 + V * 0.978466e-6))

    where *V* is the accelerating voltage in volts.  This matches the MATLAB
    reference at ``ctf/EMC_ctf_refine_from_star.m`` line 89.

    Args:
        voltage_kv: Accelerating voltage in kilovolts (e.g. 300.0).

    Returns:
        Electron wavelength in Angstroms.
    """
    if voltage_kv <= 0.0:
        raise ValueError(
            f"Accelerating voltage must be positive, got {voltage_kv} kV"
        )
    voltage_v = voltage_kv * 1e3
    return 12.2643 / np.sqrt(voltage_v * (1.0 + voltage_v * 0.978466e-6))


def _build_refinement_options(options: PipelineOptions) -> RefinementOptions:
    """Convert pipeline options to per-tilt refinement options."""
    return RefinementOptions(
        optimizer_type=options.optimizer_type,
        defocus_search_range=options.defocus_search_range,
        maximum_iterations=options.maximum_iterations,
        minimum_global_iterations=options.minimum_global_iterations,
        global_only=options.global_only,
        lowpass_cutoff=options.lowpass_cutoff,
        highpass_cutoff=options.highpass_cutoff,
        shift_sigma=options.shift_sigma,
        z_offset_sigma=options.z_offset_sigma,
    )


def _apply_refinement_to_particles(
    tilt_particles: list[dict],
    results: RefinementResults,
    tilt_angle: float,
    pixel_size: float,
) -> None:
    """Update particle dicts in-place with refined CTF parameters.

    Applies the MATLAB result-unpacking convention from
    ``ctf/EMC_ctf_refine_from_star.m`` lines 412-431::

        defocus_correction = delta_defocus_tilt + delta_z * cos(tilt_angle)
        refined_df1 = df1 + delta_half_astigmatism + defocus_correction
        refined_df2 = df2 - delta_half_astigmatism + defocus_correction
        refined_angle = original_angle + delta_angle  (in degrees)
        refined_shift_x = shift_x_pixels * pixel_size  (pixels → Angstroms)

    Args:
        tilt_particles: Particle dicts for this tilt group (modified in-place).
        results: Refinement results from :func:`refine_tilt_ctf`.
        tilt_angle: Tilt angle in degrees.
        pixel_size: Pixel size in Angstroms (for shift conversion).
    """
    cos_tilt = np.cos(np.radians(tilt_angle))

    n_particles = len(tilt_particles)
    for arr_name in ("delta_z", "shift_x", "shift_y", "per_particle_scores"):
        arr = getattr(results, arr_name)
        if len(arr) != n_particles:
            raise ValueError(
                f"Result array '{arr_name}' has length {len(arr)}, "
                f"expected {n_particles} (one per particle)"
            )

    for i, p in enumerate(tilt_particles):
        # Per-particle defocus correction: tilt-global + z-offset projected
        dz = float(results.delta_z[i])
        defocus_correction = results.delta_defocus_tilt + dz * cos_tilt

        # Apply tilt-global astigmatism change + common defocus correction
        orig_df1 = p["defocus_1"]
        orig_df2 = p["defocus_2"]
        p["defocus_1"] = (
            orig_df1 + results.delta_half_astigmatism + defocus_correction
        )
        p["defocus_2"] = (
            orig_df2 - results.delta_half_astigmatism + defocus_correction
        )

        # Astigmatism angle: add delta (radians → degrees)
        p["defocus_angle"] = float(
            np.degrees(
                np.radians(p["defocus_angle"])
                + results.delta_astigmatism_angle
            )
        )

        # Shifts: refinement returns pixels, star file stores Angstroms
        p["x_shift"] = float(results.shift_x[i]) * pixel_size
        p["y_shift"] = float(results.shift_y[i]) * pixel_size

        # Score: per-particle cross-correlation peak height.
        # Only overwrite when the refinement computed a real score; NaN
        # signals a degenerate run (e.g. maximum_iterations=0) and the
        # original score should be preserved so that callers can
        # distinguish a genuinely-run refinement from a no-op.
        score = results.per_particle_scores[i]
        if not np.isnan(score):
            p["score"] = float(score)


def _free_gpu_memory() -> None:
    """Release GPU memory pools to prevent OOM across tilt groups."""
    if cp is not None:
        cp.get_default_memory_pool().free_all_blocks()


# ---------------------------------------------------------------------------
# Main pipeline function
# ---------------------------------------------------------------------------


def refine_ctf_from_star(
    star_path: Path,
    stack_path: Path,
    reference_volume_path: Path,
    output_star_path: Path,
    options: PipelineOptions | None = None,
) -> PipelineResults:
    """Run the full CTF refinement pipeline from star file to star file.

    Reads particle metadata from *star_path*, loads the corresponding image
    tiles from *stack_path*, generates reference projections from
    *reference_volume_path*, refines per-tilt CTF parameters, and writes
    the refined star file to *output_star_path*.

    This implementation processes tilt groups sequentially on a single GPU
    (or CPU fallback).

    Args:
        star_path: Input cisTEM-style 30-column star file.
        stack_path: MRC particle stack file.
        reference_volume_path: MRC 3D reference volume file.
        output_star_path: Output path for the refined star file.
        options: Pipeline configuration.  Uses defaults if ``None``.

    Returns:
        :class:`PipelineResults` summarising the refinement run.
    """
    if options is None:
        options = PipelineOptions()

    logger.info("=== CTF Refinement Pipeline ===")
    logger.info("  Star file:     %s", star_path)
    logger.info("  Stack file:    %s", stack_path)
    logger.info("  Reference vol: %s", reference_volume_path)
    logger.info("  Output:        %s", output_star_path)

    # ── Stage 1: Parse star file ─────────────────────────────────────────
    particles, header_lines = parse_star_file(Path(star_path))
    n_total = len(particles)
    logger.info("  Parsed %d particles from star file", n_total)

    if n_total == 0:
        # Empty star file: write empty output, return empty results
        write_star_file(Path(output_star_path), [], header_lines)
        logger.info("  Empty star file — writing empty output")
        return PipelineResults(
            n_particles_total=0,
            n_particles_processed=0,
            n_tilt_groups=0,
            tilt_group_results=[],
        )

    # ── Stage 2: Read MRC stack header and data ──────────────────────────
    stack_mrc = MRCImage(str(stack_path), flg_load=True)
    stack_header = stack_mrc.get_header()
    stack_data = stack_mrc.get_data()
    if stack_data is None:
        raise RuntimeError(
            f"Failed to load image data from MRC stack: {stack_path}"
        )
    tile_ny, tile_nx = stack_data.shape[1], stack_data.shape[2]
    logger.info(
        "  Stack tile size: [%d, %d], %d slices",
        tile_nx, tile_ny, stack_header["nz"],
    )

    # ── Stage 2b: Read reference volume ──────────────────────────────────
    ref_mrc = MRCImage(str(reference_volume_path), flg_load=True)
    ref_data = ref_mrc.get_data()
    if ref_data is None:
        raise RuntimeError(
            f"Failed to load image data from reference volume: "
            f"{reference_volume_path}"
        )
    ref_volume = ref_data.astype(np.float32)
    logger.info("  Reference volume size: %s", ref_volume.shape)

    # ── Stage 3: Compute CTF-friendly pad size ───────────────────────────
    ctf_size = compute_ctf_friendly_size(2 * max(tile_nx, tile_ny))
    logger.info(
        "  tile=[%d,%d] -> ctf_size=%d (FFT-friendly, ~2x)",
        tile_nx, tile_ny, ctf_size,
    )

    # Create shared masks and Fourier handler
    mask_radius = min(tile_nx, tile_ny) / 2.0 - 1.0
    soft_mask = create_2d_soft_mask(
        tile_ny, tile_nx,
        radius=mask_radius,
        edge_width=options.soft_mask_edge_width,
    )
    fourier_handler = FourierTransformer(ctf_size, ctf_size, use_gpu=False)

    # ── Stage 4: Group particles by tilt ─────────────────────────────────
    tilt_groups = group_particles_by_tilt(particles)
    n_tilt_groups_total = len(tilt_groups)
    logger.info("  %d tilt groups", n_tilt_groups_total)

    # Extract microscope parameters from first particle (constant across stack)
    first_p = particles[0]
    pixel_size = first_p["pixel_size"]
    wavelength = compute_electron_wavelength(first_p["voltage_kv"])
    cs_mm = first_p["cs_mm"]
    amplitude_contrast = first_p["amplitude_contrast"]

    # Build per-tilt refinement options
    refine_opts = _build_refinement_options(options)

    # ── Stage 5: Process each tilt group ─────────────────────────────────
    tilt_group_results: list[TiltGroupResult] = []

    for tilt_idx, (tilt_name, tilt_particles) in enumerate(
        tilt_groups.items(), start=1
    ):
        n_in_tilt = len(tilt_particles)

        if n_in_tilt == 0:
            logger.warning(
                "Tilt group '%s' has zero particles, skipping", tilt_name,
            )
            continue

        tilt_angle = tilt_particles[0]["tilt_angle"]
        logger.info(
            "  [%d/%d] Refining '%s' (angle=%.1f, %d particles)",
            tilt_idx, n_tilt_groups_total, tilt_name, tilt_angle, n_in_tilt,
        )

        # ── 5a-c: Prepare data and reference Fourier transforms ──────
        data_fts: list[np.ndarray] = []
        ref_fts: list[np.ndarray] = []

        for p in tilt_particles:
            # position_in_stack is 1-indexed (MATLAB convention)
            pos = p["position_in_stack"]
            if pos < 1:
                raise ValueError(
                    f"position_in_stack must be >= 1 (1-indexed), "
                    f"got {pos} in tilt group '{tilt_name}'"
                )
            slice_idx = pos - 1
            tile = stack_data[slice_idx].astype(np.float32)

            # Euler angles for reference projection (SPIDER ZYZ convention)
            euler_angles = (p["phi"], p["theta"], p["psi"])

            data_ft = prepare_data_tile(
                tile, soft_mask, ctf_size, fourier_handler,
                pixel_size, options.highpass_cutoff, options.lowpass_cutoff,
            )
            ref_ft = prepare_reference_projection(
                ref_volume, euler_angles, soft_mask, ctf_size, fourier_handler,
            )

            data_fts.append(data_ft)
            ref_fts.append(ref_ft)

        # ── 5d: Build base CTF params from first particle in group ───
        first_tp = tilt_particles[0]
        base_ctf = CTFParams.from_defocus_pair(
            df1=first_tp["defocus_1"],
            df2=first_tp["defocus_2"],
            angle_degrees=first_tp["defocus_angle"],
            pixel_size=pixel_size,
            wavelength=wavelength,
            cs_mm=cs_mm,
            amplitude_contrast=amplitude_contrast,
        )

        # ── 5e: Run per-tilt CTF refinement ──────────────────────────
        results = refine_tilt_ctf(
            data_fts,
            ref_fts,
            base_ctf,
            tilt_angle_degrees=tilt_angle,
            options=refine_opts,
        )

        # ── 5f: Apply refined parameters to particle dicts ───────────
        _apply_refinement_to_particles(
            tilt_particles, results, tilt_angle, pixel_size,
        )

        # ── Per-tilt summary logging ─────────────────────────────────
        n_iters = len(results.score_history)
        mean_score = float(np.mean(results.per_particle_scores))
        logger.info(
            "    %s | angle=%.1f | %d particles | %d iters | "
            "score=%.4f | converged=%s",
            tilt_name, tilt_angle, n_in_tilt, n_iters,
            mean_score, results.converged,
        )

        tilt_group_results.append(
            TiltGroupResult(
                tilt_name=tilt_name,
                tilt_angle=tilt_angle,
                n_particles=n_in_tilt,
                n_iterations=n_iters,
                converged=results.converged,
                mean_score=mean_score,
                refinement_results=results,
            )
        )

        # ── 5g: GPU memory cleanup between tilt groups ───────────────
        _free_gpu_memory()

    # ── Stage 6: Write refined star file ─────────────────────────────────
    write_star_file(Path(output_star_path), particles, header_lines)

    n_processed = sum(r.n_particles for r in tilt_group_results)
    logger.info("=== CTF Refinement Complete ===")
    logger.info(
        "  Processed %d / %d particles across %d tilt groups",
        n_processed, n_total, len(tilt_group_results),
    )
    logger.info("  Output: %s", output_star_path)

    return PipelineResults(
        n_particles_total=n_total,
        n_particles_processed=n_processed,
        n_tilt_groups=len(tilt_group_results),
        tilt_group_results=tilt_group_results,
    )
