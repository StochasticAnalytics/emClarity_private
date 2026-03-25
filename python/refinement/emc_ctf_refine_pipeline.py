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
        minimum_global_iterations: Deprecated — retained for backward
            compatibility but ignored.  All parameters are optimised
            from the first iteration.
        global_only: When True, per-particle parameters are permanently
            frozen; only tilt-global parameters are optimised.
        lowpass_cutoff: Low-pass cutoff in Angstroms.
        highpass_cutoff: High-pass cutoff in Angstroms.
        shift_sigma: Gaussian penalty sigma for X/Y shifts (pixels).
        z_offset_sigma: Gaussian penalty sigma for per-particle z-offsets
            (Angstroms).
        soft_mask_edge_width: Edge width in pixels for the 2D soft circular
            mask applied to tiles before processing.
        debug_tilt_list: Comma-separated list of tilt names to process.
            Empty string means process all tilts.
        exit_after_n_tilts: Stop after processing this many tilt groups.
            Zero means process all tilt groups.
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
    debug_tilt_list: str = ""
    exit_after_n_tilts: int = 0


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

        # Occupancy: mark as refined (MATLAB line 429)
        p["occupancy"] = 100.0


# Saturation detection threshold (MATLAB line 443)
_SATURATION_BOUND_TOL = 0.99

# Fixed angle search range in degrees (supplement specification)
_ANGLE_SEARCH_RANGE_DEG = 45.0

# Large defocus correction warning threshold (MATLAB line 33-34: >= 2000 A)
_DEFOCUS_WARNING_THRESHOLD = 2000.0

# Diagnostic file column header (16 tab-delimited columns)
_DIAG_HEADER = (
    "tilt_name\ttilt_angle\tn_particles\tn_iters\tconverged\t"
    "delta_df\tdelta_astig\tdelta_angle_deg\t"
    "score_mean\tscore_std\tscore_min\tscore_max\tscore_change_pct\t"
    "df_sat\tastig_sat\tangle_sat"
)


def _write_diagnostics(
    output_star_path: Path,
    tilt_group_results: list[TiltGroupResult],
    defocus_search_range: float,
) -> Path:
    """Write per-tilt diagnostic file alongside the output star file.

    Produces a tab-delimited file matching the MATLAB reference at
    ``ctf/EMC_ctf_refine_from_star.m`` lines 482-557.  Each row is one
    tilt group with 16 columns: tilt metadata, parameter deltas, score
    statistics, and saturation flags.

    Args:
        output_star_path: Path to the output star file (used to derive
            the diagnostics filename).
        tilt_group_results: Per-tilt summaries from the pipeline.
        defocus_search_range: Symmetric defocus search range (Angstroms)
            used for saturation detection.

    Returns:
        Path to the written diagnostics file.
    """
    diag_path = output_star_path.with_name(
        output_star_path.stem + "_diagnostics.txt"
    )

    bound_tol = _SATURATION_BOUND_TOL
    df_range = defocus_search_range
    astig_range = defocus_search_range / 2.0
    angle_range_deg = _ANGLE_SEARCH_RANGE_DEG

    lines: list[str] = [_DIAG_HEADER]

    for tgr in tilt_group_results:
        rr = tgr.refinement_results
        scores = rr.per_particle_scores
        valid_scores = scores[~np.isnan(scores)]

        if len(valid_scores) > 0:
            s_mean = float(np.mean(valid_scores))
            s_std = float(np.std(valid_scores, ddof=min(1, len(valid_scores) - 1)))
            s_min = float(np.min(valid_scores))
            s_max = float(np.max(valid_scores))
        else:
            s_mean = s_std = s_min = s_max = 0.0

        # Score change %: (final - initial) / final * 100
        # NOTE: MATLAB lines 535-538 divide by s_final (not s_init).
        # The PRD spec table says /initial, but MATLAB is authoritative here.
        # Uses per-particle mean from score_history (MATLAB lines 535-538)
        n_p = tgr.n_particles
        if len(rr.score_history) >= 2 and n_p > 0:
            s_init = rr.score_history[0] / n_p
            s_final = rr.score_history[-1] / n_p
            if s_final != 0.0:
                score_change_pct = 100.0 * (s_final - s_init) / s_final
            else:
                score_change_pct = 0.0
        else:
            score_change_pct = 0.0

        # Delta angle in degrees for output and saturation check
        delta_angle_deg = float(np.degrees(rr.delta_astigmatism_angle))

        # Saturation flags (MATLAB lines 532-534)
        df_sat = int(abs(rr.delta_defocus_tilt) >= bound_tol * df_range)
        astig_sat = int(
            abs(rr.delta_half_astigmatism) >= bound_tol * astig_range
        )
        angle_sat = int(abs(delta_angle_deg) >= bound_tol * angle_range_deg)

        line = (
            f"{tgr.tilt_name}\t"
            f"{tgr.tilt_angle:.2f}\t"
            f"{tgr.n_particles:d}\t"
            f"{tgr.n_iterations:d}\t"
            f"{int(tgr.converged):d}\t"
            f"{rr.delta_defocus_tilt:.1f}\t"
            f"{rr.delta_half_astigmatism:.1f}\t"
            f"{delta_angle_deg:.1f}\t"
            f"{s_mean:.6f}\t"
            f"{s_std:.6f}\t"
            f"{s_min:.6f}\t"
            f"{s_max:.6f}\t"
            f"{score_change_pct:.1f}\t"
            f"{df_sat:d}\t"
            f"{astig_sat:d}\t"
            f"{angle_sat:d}"
        )
        lines.append(line)

    diag_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("  Diagnostics: %s (%d tilt groups)", diag_path, len(tilt_group_results))
    return diag_path


def check_convergence_health(
    results: RefinementResults,
    options: PipelineOptions,
) -> list[str]:
    """Check refinement results for convergence health issues.

    Inspects per-tilt refinement results for warning conditions that indicate
    potential problems — without aborting the pipeline.  Mirrors the MATLAB
    convergence warnings at ``ctf/EMC_ctf_refine_from_star.m`` lines 31-35.

    Warning conditions checked:
        (a) **Score decrease**: total score at the last iteration is lower
            than at the first iteration, suggesting divergence.
        (b) **Large defocus correction**: ``abs(delta_defocus_tilt) >= 2000 A``,
            which often indicates a wrong starting defocus or sign convention
            error (MATLAB line 34).
        (c) **Parameter saturation**: any refined parameter is at >= 99% of
            its search range bound, suggesting the true optimum lies outside
            the allowed range.

    Args:
        results: Refinement results from :func:`refine_tilt_ctf`.
        options: Pipeline configuration (provides search range bounds).

    Returns:
        List of human-readable warning strings.  Empty list means healthy.
    """
    warnings_list: list[str] = []

    # (a) Score decreased between first and last iteration — compare per-particle
    # normalized values to match the scale used in the diagnostic file output.
    n_particles = len(results.per_particle_scores)
    if len(results.score_history) >= 2 and results.score_history[-1] < results.score_history[0]:
        norm = float(n_particles) if n_particles > 0 else 1.0
        first_pp = results.score_history[0] / norm
        last_pp = results.score_history[-1] / norm
        warnings_list.append(
            f"Score decreased from {first_pp:.4f} "
            f"to {last_pp:.4f} "
            f"(delta={last_pp - first_pp:.4f}) per particle"
        )

    # (b) Large defocus correction (MATLAB line 34: >= 2000 A)
    if abs(results.delta_defocus_tilt) >= _DEFOCUS_WARNING_THRESHOLD:
        warnings_list.append(
            f"Large defocus correction: {results.delta_defocus_tilt:.1f} A "
            f"(threshold: {_DEFOCUS_WARNING_THRESHOLD:.0f} A)"
        )

    # (c) Parameter saturation at 99% of search range bound
    bound_tol = _SATURATION_BOUND_TOL
    df_range = options.defocus_search_range
    astig_range = df_range / 2.0
    angle_range_deg = _ANGLE_SEARCH_RANGE_DEG

    if abs(results.delta_defocus_tilt) >= bound_tol * df_range:
        warnings_list.append(
            f"Defocus at search bound: {results.delta_defocus_tilt:.1f} A "
            f"(bound: +/-{df_range:.0f} A)"
        )

    if abs(results.delta_half_astigmatism) >= bound_tol * astig_range:
        warnings_list.append(
            f"Half-astigmatism at search bound: "
            f"{results.delta_half_astigmatism:.1f} A "
            f"(bound: +/-{astig_range:.0f} A)"
        )

    delta_angle_deg = float(np.degrees(results.delta_astigmatism_angle))
    if abs(delta_angle_deg) >= bound_tol * angle_range_deg:
        warnings_list.append(
            f"Astigmatism angle at search bound: {delta_angle_deg:.1f} deg "
            f"(bound: +/-{angle_range_deg:.0f} deg)"
        )

    return warnings_list


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
    if stack_data.ndim != 3:
        raise RuntimeError(
            f"Expected 3-D MRC stack (nz, ny, nx), "
            f"got array with {stack_data.ndim} dimensions "
            f"(shape {stack_data.shape})"
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

    # ── Debug filtering: restrict to named tilts or first N ───────────
    if options.debug_tilt_list:
        selected = {
            name.strip()
            for name in options.debug_tilt_list.split(",")
            if name.strip()
        }
        tilt_groups = {k: v for k, v in tilt_groups.items() if k in selected}
        if not tilt_groups:
            logger.warning(
                "debug_tilt_list produced no matches: none of %s found in tilt groups",
                list(selected),
            )
        logger.info(
            "  debug_tilt_list: processing %d / %d tilt groups",
            len(tilt_groups), n_tilt_groups_total,
        )

    if options.exit_after_n_tilts > 0:
        kept = dict(list(tilt_groups.items())[: options.exit_after_n_tilts])
        logger.info(
            "  exit_after_n_tilts=%d: processing %d / %d tilt groups",
            options.exit_after_n_tilts, len(kept), len(tilt_groups),
        )
        tilt_groups = kept

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
            n_slices = stack_data.shape[0]
            if pos > n_slices:
                raise ValueError(
                    f"position_in_stack {pos} exceeds stack depth "
                    f"{n_slices} in tilt group '{tilt_name}'"
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

        # ── Convergence health warnings ───────────────────────────────
        health_warnings = check_convergence_health(results, options)
        for warn_msg in health_warnings:
            logger.warning("    [%s] %s", tilt_name, warn_msg)

        # ── Per-tilt summary logging ─────────────────────────────────
        n_iters = len(results.score_history)
        _scores = results.per_particle_scores
        _valid = _scores[~np.isnan(_scores)]
        mean_score = float(np.mean(_valid)) if len(_valid) > 0 else float("nan")
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

    # ── Stage 7: Write per-tilt diagnostics ───────────────────────────────
    if tilt_group_results:
        _write_diagnostics(
            Path(output_star_path),
            tilt_group_results,
            options.defocus_search_range,
        )

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
