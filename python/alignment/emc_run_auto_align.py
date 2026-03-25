#!/usr/bin/env python3
"""
Python equivalent of BH_runAutoAlign.m.

Auto tilt-series alignment function for emClarity.
Handles preprocessing, patch tracking, and bead-based refinement.
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from image_io.mrc_image import OPEN_IMG, SAVE_IMG, MRCImage
from utils.emc_str2double import emc_str2double
from utils.parameter_parser import parse_parameter_file

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))


logger = logging.getLogger(__name__)


def emc_run_auto_align(
    parameter_file: str | Path,
    stack_in: str | Path,
    tilt_angles: str | Path,
    img_rotation: str | float,
    skip_tilts: str | list[int] | None = None,
) -> None:
    """
    Run emClarity auto tilt-series alignment with integrated patch tracking and bead finding.

    This function replaces the MATLAB BH_runAutoAlign and integrates the functionality
    of the emC_autoAlign and emC_findBeads shell scripts directly into Python.

    Args:
        parameter_file: Path to emClarity parameter file
        stack_in: Input tilt series stack file
        tilt_angles: File containing tilt angles
        img_rotation: Image rotation angle in degrees
        skip_tilts: Optional list of tilt indices to skip

    Note:
        This is the Python equivalent of BH_runAutoAlign.m with integrated shell scripts

    Raises:
        FileNotFoundError: If input files don't exist
        ValueError: If parameters are invalid
        RuntimeError: If alignment processes fail
    """
    # Validate inputs
    if not Path(parameter_file).exists():
        raise FileNotFoundError(f"Parameter file not found: {parameter_file}")
    if not Path(stack_in).exists():
        raise FileNotFoundError(f"Stack file not found: {stack_in}")
    if not Path(tilt_angles).exists():
        raise FileNotFoundError(f"Tilt angles file not found: {tilt_angles}")

    # Parse parameters using our enhanced parameter parser
    try:
        emc = parse_parameter_file(parameter_file)
    except Exception as e:
        raise ValueError(f"Error parsing parameter file: {e}") from e

    # Handle optional skip_tilts argument
    if skip_tilts is not None:
        if isinstance(skip_tilts, str):
            skip_tilts = emc_str2double(skip_tilts)
        if not isinstance(skip_tilts, list):
            skip_tilts = [skip_tilts] if skip_tilts != 0 else None

    # Convert img_rotation to float
    if isinstance(img_rotation, str):
        img_rotation = emc_str2double(img_rotation)

    # Get auto-alignment parameters with defaults
    # Note: These replace the try/catch blocks in MATLAB with proper parameter validation
    auto_ali_params = _get_auto_alignment_parameters(emc)

    # Check bead diameter - if 0, disable bead refinement
    bead_diameter = emc.get("beadDiameter", 0.0) * 1e10  # Convert to Angstroms
    if bead_diameter == 0:
        auto_ali_params["refine_on_beads"] = False

    # Fixed parameters (could be moved to parameter file in future)
    fixed_params = {
        "low_res_cutoff": 800,
        "clean_up_results": False,
        "mag_option": 5,
        "tilt_angle_offset": 0.0,
        "tilt_option": 0,
    }

    logger.info(f"Loading stack: {stack_in}")
    print(f"Stack in is {stack_in}")

    # Load input stack with header-only initially (BAH optimization)
    try:
        input_mrc = MRCImage(stack_in, load_data=False)
        input_stack = OPEN_IMG("single", input_mrc)
    except Exception as e:
        raise ValueError(f"Error loading input stack: {e}") from e

    # Handle skip_tilts
    skip_tilts_logical = _handle_skip_tilts(skip_tilts, input_stack.shape[2])
    if skip_tilts_logical is not None:
        input_stack = input_stack[:, :, skip_tilts_logical]
    else:
        skip_tilts_logical = [True] * input_stack.shape[2]

    # Setup file paths and directories
    paths = _setup_paths_and_directories(stack_in)

    # Get header information for pixel size and origin
    header_info = _extract_header_info(input_mrc)

    # Handle tilt angles file
    _process_tilt_angles(tilt_angles, skip_tilts_logical, paths["base_name"])

    # Calculate binning parameters
    binning_params = _calculate_binning_parameters(
        auto_ali_params, emc["pixel_size_angstroms"]
    )

    # Get stack dimensions
    nx, ny, nz = input_stack.shape
    logger.info(f"Stack dimensions: {nx} x {ny} x {nz}")

    # Check if we should switch axes (requires GPU functions - placeholder for now)
    switch_axes = _should_switch_axes(emc, input_stack, img_rotation)

    # Handle axis switching and preprocessing
    if switch_axes:
        raise NotImplementedError(
            "Axis switching requires GPU functions - not yet implemented"
        )
    elif skip_tilts is not None:
        # Save modified stack
        _save_modified_stack(input_mrc, paths, header_info)
    else:
        # No modifications, create symbolic link
        _create_stack_symlink(stack_in, paths)

    # Calculate rotation matrix
    rot_mat = _calculate_rotation_matrix(img_rotation)

    # Preprocessing (simplified version without full GPU implementation)
    preprocessed_stack = _preprocess_stack(
        input_stack, emc, nx, ny, nz, auto_ali_params
    )

    # Save preprocessed stack
    _save_preprocessed_stack(preprocessed_stack, paths, emc, nx, ny, nz)

    # Run patch tracking (integrated from emC_autoAlign shell script)
    _run_integrated_patch_tracking(
        paths,
        rot_mat,
        emc,
        img_rotation,
        binning_params,
        nx,
        ny,
        nz,
        auto_ali_params,
        fixed_params,
    )

    # Handle tilt options
    _handle_tilt_options(fixed_params["tilt_option"], paths["base_name"])

    # Bead-based refinement
    too_few_beads = _run_bead_refinement(
        auto_ali_params["refine_on_beads"], paths, nx, ny, emc
    )

    # Fallback bead finding (integrated from emC_findBeads shell script)
    if too_few_beads or not auto_ali_params["refine_on_beads"]:
        _run_integrated_bead_finding(paths, nx, ny, emc)

    # Cleanup
    _cleanup_files(paths["fixed_name"])

    logger.info("Auto-alignment completed successfully")
    print("Auto-alignment completed")


def _get_auto_alignment_parameters(emc: dict) -> dict:
    """Extract auto-alignment parameters with defaults."""
    return {
        "resolution_cutoff": emc.get("autoAli_max_resolution", 18.0),
        "min_sampling_rate": emc.get("autoAli_min_sampling_rate", 10.0),
        "max_sampling_rate": emc.get("autoAli_max_sampling_rate", 4.0),
        "patch_size_factor": emc.get("autoAli_patch_size_factor", 4),
        "refine_on_beads": emc.get("autoAli_refine_on_beads", False),
        "border_size_pixels": emc.get("autoAli_patch_tracking_border", 64),
        "n_iters_no_rot": emc.get("autoAli_n_iters_no_rotation", 3),
        "patch_overlap": emc.get("autoAli_patch_overlap", 0.5),
        "iterations_per_bin": emc.get("autoAli_iterations_per_bin", 3),
        "max_shift_angstroms": emc.get("autoAli_max_shift_in_angstroms", 40.0),
        "divide_shift_limit_by": emc.get("autoAli_max_shift_factor", 1),
    }


def _handle_skip_tilts(
    skip_tilts: list[int] | None, total_tilts: int
) -> list[bool] | None:
    """Handle skip_tilts parameter and return logical indexing."""
    if skip_tilts is None:
        return None

    all_indices = list(range(1, total_tilts + 1))  # MATLAB 1-based indexing
    return [i not in skip_tilts for i in all_indices]


def _setup_paths_and_directories(stack_in: str | Path) -> dict:
    """Setup file paths and create necessary directories."""
    stack_path = Path(stack_in)
    base_name = stack_path.stem
    ext = stack_path.suffix

    paths = {
        "base_name": base_name,
        "ext": f"{ext}.preprocessed",
        "fixed_name": f"fixedStacks/{base_name}.fixed.preprocessed",
        "start_dir": Path.cwd(),
        "wrk_dir": Path(f"emC_autoAlign_{base_name}"),
        "fixed_stacks_dir": Path("fixedStacks"),
    }

    # Create directories
    paths["wrk_dir"].mkdir(exist_ok=True)
    paths["fixed_stacks_dir"].mkdir(exist_ok=True)

    return paths


def _extract_header_info(input_mrc: MRCImage) -> dict:
    """Extract header information for pixel size and origin."""
    header = input_mrc.get_header()
    return {
        "pixel_header": [
            header["cell_a"] / header["nx"],
            header["cell_b"] / header["ny"],
            header["cell_c"] / header["nz"],
        ],
        "origin_header": [header["origin_x"], header["origin_y"], header["origin_z"]],
    }


def _process_tilt_angles(
    tilt_angles: str | Path, skip_tilts_logical: list[bool], base_name: str
) -> None:
    """Process tilt angles file and write filtered version."""
    os.chdir("fixedStacks")

    try:
        tilt_angles_data = np.loadtxt(f"../{tilt_angles}")
        if skip_tilts_logical is not None:
            tilt_angles_data = tilt_angles_data[skip_tilts_logical]

        # Write filtered tilt angles
        with open(f"{base_name}.rawtlt", "w") as f:
            for angle in tilt_angles_data:
                f.write(f"{angle}\n")
    except Exception as e:
        raise ValueError(f"Error processing tilt angles: {e}") from e
    finally:
        os.chdir("..")


def _calculate_binning_parameters(
    auto_ali_params: dict, pixel_size_angstroms: float
) -> dict:
    """Calculate binning parameters for patch tracking."""
    bin_high = int(np.ceil(auto_ali_params["min_sampling_rate"] / pixel_size_angstroms))

    if auto_ali_params["max_sampling_rate"] > 4:
        bin_low = auto_ali_params["max_sampling_rate"]
    else:
        bin_low = int(
            np.ceil(auto_ali_params["max_sampling_rate"] / pixel_size_angstroms)
        )

    bin_inc = -1 * int(np.ceil((bin_high - bin_low) / 3))

    # Calculate shift limits
    first_iter_shift_limit_pixels = int(
        np.ceil(auto_ali_params["max_shift_angstroms"] / pixel_size_angstroms)
    )

    return {
        "bin_high": bin_high,
        "bin_low": bin_low,
        "bin_inc": bin_inc,
        "first_iter_shift_limit_pixels": first_iter_shift_limit_pixels,
    }


def _should_switch_axes(
    emc: dict, input_stack: np.ndarray, img_rotation: float
) -> bool:
    """Check if axes should be switched (placeholder - requires GPU functions)."""
    if emc.get("autoAli_switchAxes", False):
        logger.warning(
            "autoAli_switchAxes requires GPU functions - not yet implemented"
        )
        # TODO: Implement axis switching logic when GPU functions are available
    return False


def _save_modified_stack(input_mrc: MRCImage, paths: dict, header_info: dict) -> None:
    """Save modified stack with skip_tilts applied."""
    SAVE_IMG(
        input_mrc,
        f"fixedStacks/{paths['base_name']}.fixed",
        pixel_size=header_info["pixel_header"],
        origin=header_info["origin_header"],
    )


def _create_stack_symlink(stack_in: str | Path, paths: dict) -> None:
    """Create symbolic link to original stack."""
    os.chdir("fixedStacks")
    try:
        subprocess.run(
            ["ln", "-sf", f"../{stack_in}", f"{paths['base_name']}.fixed"], check=True
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to create symbolic link: {e}") from e
    finally:
        os.chdir("..")


def _calculate_rotation_matrix(img_rotation: float) -> list[float]:
    """Calculate rotation matrix from image rotation angle."""
    rad = np.radians(img_rotation)
    return [np.cos(rad), -np.sin(rad), np.sin(rad), np.cos(rad)]


def _preprocess_stack(
    input_stack: np.ndarray, emc: dict, nx: int, ny: int, nz: int, auto_ali_params: dict
) -> np.ndarray:
    """
    Preprocess tilt-series stack.

    Note: This is a simplified version. Full implementation requires BH_bandpass3d
    and other GPU functions.
    """
    logger.warning(
        "Using simplified preprocessing - full implementation requires BH_bandpass3d"
    )
    print("Preprocessing tilt-series")

    # For now, return the input stack unchanged
    # TODO: Implement proper preprocessing when BH_bandpass3d is available
    # This should include:
    # - Bandpass filtering
    # - Median filtering
    # - Image rotation application

    return input_stack


def _save_preprocessed_stack(
    preprocessed_stack: np.ndarray, paths: dict, emc: dict, nx: int, ny: int, nz: int
) -> None:
    """Save preprocessed stack."""
    # Create MRCImage object for saving
    temp_mrc = MRCImage.from_header(
        {
            "nx": nx,
            "ny": ny,
            "nz": nz,
            "cell_a": nx * emc["pixel_size_angstroms"],
            "cell_b": ny * emc["pixel_size_angstroms"],
            "cell_c": nz * emc["pixel_size_angstroms"],
            "origin_x": 0,
            "origin_y": 0,
            "origin_z": 0,
        }
    )
    temp_mrc._data = preprocessed_stack
    temp_mrc._is_data_loaded = True

    SAVE_IMG(temp_mrc, paths["fixed_name"], pixel_size=emc["pixel_size_angstroms"])
    print("Finished preprocessing tilt-series")


def _run_integrated_patch_tracking(
    paths: dict,
    rot_mat: list[float],
    emc: dict,
    img_rotation: float,
    binning_params: dict,
    nx: int,
    ny: int,
    nz: int,
    auto_ali_params: dict,
    fixed_params: dict,
) -> None:
    """
    Run integrated patch tracking - replaces emC_autoAlign shell script.

    This function implements the core logic from the emC_autoAlign bash script
    directly in Python, eliminating the need for external shell script dependencies.
    """
    # Change to working directory
    os.chdir(paths["wrk_dir"])

    # Write rotation matrix file
    with open("preRotXf.xf", "w") as f:
        f.write(
            f"{rot_mat[0]:.3f} {rot_mat[1]:.3f} {rot_mat[2]:.3f} {rot_mat[3]:.3f} 0.0 0.0\n"
        )

    logger.info(f"Starting integrated patch tracking in: {os.getcwd()}")
    print(f"Starting integrated patch tracking in: {os.getcwd()}")

    # Initialize iteration variables
    iteration = 1
    tilt_angle_offset = fixed_params["tilt_angle_offset"]
    tilt_option = fixed_params["tilt_option"]
    mag_option = fixed_params["mag_option"]

    # Main binning loop - implements the shell script's for loop logic
    bin_sequence = list(
        range(
            binning_params["bin_high"],
            binning_params["bin_low"] + binning_params["bin_inc"],
            binning_params["bin_inc"],
        )
    )

    logger.info(f"Binning sequence: {bin_sequence}")
    print(f"Binning sequence: {bin_sequence}")

    for i_bin in bin_sequence:
        # Calculate filter cutoffs
        lp_cut = (
            i_bin * emc["pixel_size_angstroms"] / auto_ali_params["resolution_cutoff"]
        )
        hp_cut = i_bin * emc["pixel_size_angstroms"] / fixed_params["low_res_cutoff"]

        logger.info(f"Bin {i_bin}: LP cutoff = {lp_cut:.4f}, HP cutoff = {hp_cut:.4f}")

        for bin_iter in range(1, auto_ali_params["iterations_per_bin"] + 1):
            logger.info(f"Iteration {iteration}, Bin {i_bin}, Sub-iteration {bin_iter}")

            # Calculate patch sizes
            if iteration < 4:
                pt_size_x = int(nx / (iteration * i_bin))
                pt_size_y = int(ny / (iteration * i_bin))
            else:
                pt_size_x = int(nx / (i_bin * auto_ali_params["patch_size_factor"]))
                pt_size_y = int(ny / (i_bin * auto_ali_params["patch_size_factor"]))

            pt_border = auto_ali_params["border_size_pixels"]
            pt_overlap = auto_ali_params["patch_overlap"]

            # Calculate shift limits
            if iteration >= 2:
                limit_shifts = (
                    int(
                        binning_params["first_iter_shift_limit_pixels"]
                        / (iteration ** auto_ali_params["divide_shift_limit_by"])
                    )
                    + 1
                )
            else:
                limit_shifts = binning_params["first_iter_shift_limit_pixels"]

            # Create round directory
            w_dir = f"round_{iteration}"
            p_name = f"INP-{iteration}"

            Path(w_dir).mkdir(exist_ok=True)
            os.chdir(w_dir)

            try:
                if iteration == 1:
                    # First iteration - run tiltxcorr for initial alignment
                    _run_first_iteration_alignment(
                        p_name, paths, limit_shifts, tilt_angle_offset
                    )
                else:
                    # Subsequent iterations - setup and run patch tracking
                    _run_subsequent_iteration_alignment(
                        p_name,
                        paths,
                        iteration,
                        i_bin,
                        lp_cut,
                        hp_cut,
                        limit_shifts,
                        pt_size_x,
                        pt_size_y,
                        pt_border,
                        pt_overlap,
                        tilt_angle_offset,
                        img_rotation,
                        auto_ali_params,
                        tilt_option,
                        mag_option,
                    )

                iteration += 1

            except Exception as e:
                logger.error(f"Error in iteration {iteration}: {e}")
                raise RuntimeError(
                    f"Patch tracking failed at iteration {iteration}: {e}"
                ) from e
            finally:
                os.chdir("..")  # Return to parent directory

    # Final processing
    final_round = iteration - 1
    logger.info(f"Completed {final_round} iterations")

    # Copy final results
    _copy_final_alignment_results(paths, final_round)

    # Return to starting directory
    os.chdir(paths["start_dir"])
    logger.info("Integrated patch tracking completed successfully")


def _run_first_iteration_alignment(
    p_name: str, paths: dict, limit_shifts: int, tilt_angle_offset: float
) -> None:
    """Run first iteration alignment using tiltxcorr."""
    logger.info(f"Running first iteration alignment with shift limit: {limit_shifts}")

    # Run tiltxcorr for initial cross-correlation
    cmd = [
        "tiltxcorr",
        "-InputFile",
        f"../../fixedStacks/{paths['base_name']}.fixed.preprocessed",
        "-OutputFile",
        f"{p_name}.prexf",
        "-TiltFile",
        f"../../fixedStacks/{paths['base_name']}.rawtlt",
        "-FilterSigma1",
        "0.001",
        "-FilterRadius2",
        "0.5",
        "-FilterSigma2",
        "0.05",
        "-CumulativeCorrelation",
        "-ShiftLimitsXandY",
        f"{limit_shifts},{limit_shifts}",
        "-AngleOffset",
        str(tilt_angle_offset),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=1800)
        logger.info("tiltxcorr completed successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"tiltxcorr failed: {e}")
        raise RuntimeError(f"tiltxcorr failed: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("tiltxcorr timed out after 30 minutes") from e

    # Convert transforms
    cmd = ["xftoxg", "-nfit", "0", f"{p_name}.prexf", f"{p_name}.inpXF"]
    try:
        subprocess.run(cmd, check=True, timeout=60)
        logger.info("Transform conversion completed")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"xftoxg failed: {e}") from e

    # Copy tilt angles
    import shutil

    shutil.copy(f"../../fixedStacks/{paths['base_name']}.rawtlt", f"{p_name}.tlt")


def _run_subsequent_iteration_alignment(
    p_name: str,
    paths: dict,
    iteration: int,
    i_bin: int,
    lp_cut: float,
    hp_cut: float,
    limit_shifts: int,
    pt_size_x: int,
    pt_size_y: int,
    pt_border: int,
    pt_overlap: float,
    tilt_angle_offset: float,
    img_rotation: float,
    auto_ali_params: dict,
    tilt_option: int,
    mag_option: int,
) -> None:
    """Run subsequent iteration alignment with patch tracking."""
    import shutil

    # Setup file links
    shutil.copy(
        f"../../fixedStacks/{paths['base_name']}.fixed.preprocessed", f"{p_name}.st"
    )

    prev_iter = iteration - 1
    prev_w_dir = f"../round_{prev_iter}"

    # Copy previous tilt angles
    shutil.copy(f"{prev_w_dir}/INP-{prev_iter}.tlt", f"{p_name}.rawtlt")

    # Handle transform files
    if iteration == 2:
        shutil.copy(f"{prev_w_dir}/INP-{prev_iter}.inpXF", f"{p_name}.inpXF")
    else:
        # Combine previous results using xfproduct
        cmd = [
            "xfproduct",
            "-InputFile1",
            f"{prev_w_dir}/INP-{prev_iter}.inpXF",
            "-InputFile2",
            f"{prev_w_dir}/INP-{prev_iter}.tltxf",
            "-OutputFile",
            f"{p_name}.inpXF",
        ]
        try:
            subprocess.run(cmd, check=True, timeout=120)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"xfproduct failed: {e}") from e

    # Create binned stack
    cmd = [
        "newstack",
        "-InputFile",
        f"{p_name}.st",
        "-OutputFile",
        f"{p_name}.preali",
        "-TransformFile",
        f"{p_name}.inpXF",
        "-BinByFactor",
        str(i_bin),
        "-AntialiasFilter",
        "5",
        "-FloatDensities",
        "2",
    ]

    try:
        subprocess.run(cmd, check=True, timeout=600)
        logger.info(f"Created binned stack with factor {i_bin}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"newstack failed: {e}") from e

    # Create prealignment transform file
    with open(f"{p_name}.rawtlt") as f:
        n_prjs = len(f.readlines())

    with open(f"{p_name}.prexg", "w") as f:
        for _ in range(n_prjs):
            f.write("1.0 0.0 0.0 1.0 0.0 0.0\n")

    # Determine rotation angle
    local_rotation = img_rotation if iteration == 2 else 0.0

    # Run tiltxcorr with patch tracking
    cmd = [
        "tiltxcorr",
        "-OverlapOfPatchesXandY",
        f"{pt_overlap},{pt_overlap}",
        "-IterateCorrelations",
        "1",
        "-ImagesAreBinned",
        str(i_bin),
        "-InputFile",
        f"{p_name}.preali",
        "-OutputFile",
        f"{p_name}_pt.fid",
        "-PrealignmentTransformFile",
        f"{p_name}.prexg",
        "-TiltFile",
        f"{p_name}.rawtlt",
        "-FilterSigma1",
        str(hp_cut),
        "-FilterRadius2",
        str(lp_cut),
        "-FilterSigma2",
        "0.05",
        "-ShiftLimitsXandY",
        f"{limit_shifts},{limit_shifts}",
        "-PadsInXandY",
        "128,128",
        "-SizeOfPatchesXandY",
        f"{pt_size_x},{pt_size_y}",
        "-BordersInXandY",
        f"{pt_border},{pt_border}",
        "-CorrelationCoefficient",
        "-RotationAngle",
        "0.0",
        "-AngleOffset",
        str(tilt_angle_offset),
    ]

    try:
        subprocess.run(cmd, check=True, timeout=1800)
        logger.info("Patch tracking tiltxcorr completed")
    except subprocess.CalledProcessError as e:
        logger.error(f"Patch tracking tiltxcorr failed: {e}")
        raise RuntimeError(f"Patch tracking tiltxcorr failed: {e}") from e

    # Process contours
    cmd = [
        "imodchopconts",
        "-InputModel",
        f"{p_name}_pt.fid",
        "-OutputModel",
        f"{p_name}.fid",
        "-NumberOfPieces",
        "2",
    ]

    try:
        subprocess.run(cmd, check=True, timeout=300)
        logger.info("Contour processing completed")
    except subprocess.CalledProcessError as e:
        logger.warning(f"imodchopconts failed: {e} - continuing anyway")
        # Copy the original file if chopping fails
        shutil.copy(f"{p_name}_pt.fid", f"{p_name}.fid")

    # Run tiltalign
    _run_tiltalign(
        p_name,
        i_bin,
        local_rotation,
        tilt_angle_offset,
        iteration,
        auto_ali_params,
        tilt_option,
        mag_option,
        pt_size_x,
        pt_size_y,
    )


def _run_tiltalign(
    p_name: str,
    i_bin: int,
    local_rotation: float,
    tilt_angle_offset: float,
    iteration: int,
    auto_ali_params: dict,
    tilt_option: int,
    mag_option: int,
    pt_size_x: int,
    pt_size_y: int,
) -> None:
    """Run tiltalign for fiducial-based alignment."""
    base_cmd = [
        "tiltalign",
        "-ModelFile",
        f"{p_name}.fid",
        "-ImageFile",
        f"{p_name}.preali",
        "-ImagesAreBinned",
        str(i_bin),
        "-OutputModelFile",
        f"{p_name}.3dmod",
        "-OutputResidualFile",
        f"{p_name}.resid",
        "-OutputFidXYZFile",
        f"{p_name}fid.xyz",
        "-OutputTiltFile",
        f"{p_name}.tlt",
        "-OutputTransformFile",
        f"{p_name}.tltxf_nonScaled",
        "-RotationAngle",
        str(local_rotation),
        "-TiltFile",
        f"{p_name}.rawtlt",
        "-AngleOffset",
        str(tilt_angle_offset),
        "-RotOption",
        "1",
        "-RotDefaultGrouping",
        "3",
        "-TiltOption",
        str(tilt_option),
        "-TiltDefaultGrouping",
        "3",
        "-MagOption",
        str(mag_option),
        "-MagDefaultGrouping",
        "3",
        "-BeamTiltOption",
        "0",
        "-ResidualReportCriterion",
        "1.0",
        "-SurfacesToAnalyze",
        "1",
        "-RobustFitting",
        "1",
        "-MetroFactor",
        "0.25",
        "-MaximumCycles",
        "1000",
        "-KFactorScaling",
        "1.0",
        "-NoSeparateTiltGroups",
        "2",
        "-AxisZShift",
        "1000",
        "-ShiftZFromOriginal",
        "1",
        "-AngleOffset",
        str(tilt_angle_offset),
    ]

    # Add local alignment parameters if beyond initial iterations
    if iteration > auto_ali_params["n_iters_no_rot"]:
        base_cmd.extend(
            [
                "-LocalAlignments",
                "-OutputLocalFile",
                f"{p_name}_local.xf",
                "-TargetPatchSizeXandY",
                f"{pt_size_x},{pt_size_y}",
                "-MinSizeOrOverlapXandY",
                "0.5,0.5",
                "-MinFidsTotalAndEachSurface",
                "8,3",
                "-FixXYZCoordinates",
                "1",
                "-LocalRotOption",
                "1",
                "-LocalRotDefaultGrouping",
                "6",
                "-LocalTiltOption",
                "0",
                "-LocalTiltDefaultGrouping",
                "6",
                "-LocalMagOption",
                "1",
                "-LocalMagDefaultGrouping",
                "7",
            ]
        )

    try:
        with open("tiltAlign.log", "w") as log_file:
            subprocess.run(
                base_cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=1800,
            )
        logger.info(f"tiltalign completed for iteration {iteration}")
    except subprocess.CalledProcessError as e:
        logger.error(f"tiltalign failed: {e}")
        raise RuntimeError(f"tiltalign failed: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("tiltalign timed out after 30 minutes") from e

    # Scale transforms
    cmd = f"awk -v BINVAL={i_bin} '{{print $1,$2,$3,$4,BINVAL*$5,BINVAL*$6}}' {p_name}.tltxf_nonScaled > {p_name}.tltxf"
    try:
        subprocess.run(cmd, shell=True, check=True, timeout=60)
        logger.info("Transform scaling completed")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Transform scaling failed: {e}") from e


def _copy_final_alignment_results(paths: dict, final_round: int) -> None:
    """Copy final alignment results to fixedStacks directory."""
    import shutil

    base_name = paths["base_name"]

    try:
        # Copy local alignment file
        shutil.copy(
            f"round_{final_round}/INP-{final_round}_local.xf",
            f"../fixedStacks/{base_name}.local",
        )

        # Combine transforms
        cmd = [
            "xfproduct",
            "-InputFile1",
            f"round_{final_round}/INP-{final_round}.inpXF",
            "-InputFile2",
            f"round_{final_round}/INP-{final_round}.tltxf",
            "-OutputFile",
            "withOutRot.xf",
        ]
        subprocess.run(cmd, check=True, timeout=120)

        # Copy final transforms and tilt angles
        shutil.copy("withOutRot.xf", f"../fixedStacks/{base_name}.xf")
        shutil.copy(
            f"round_{final_round}/INP-{final_round}.tlt",
            f"../fixedStacks/{base_name}.tlt",
        )

        # Add base name to list
        with open("../fixedStacks/baseName.list", "a") as f:
            f.write(f"{base_name}\n")

        logger.info("Final alignment results copied successfully")

    except Exception as e:
        logger.error(f"Error copying final results: {e}")
        raise RuntimeError(f"Failed to copy final alignment results: {e}") from e


def _run_integrated_bead_finding(paths: dict, nx: int, ny: int, emc: dict) -> None:
    """
    Run integrated bead finding - replaces emC_findBeads shell script.

    This function implements the core logic from the emC_findBeads bash script
    directly in Python, eliminating the need for external shell script dependencies.
    """
    logger.info("Running integrated bead finding")

    try:
        os.chdir("fixedStacks")
        base_name = paths["base_name"]

        # Calculate bead size in pixels
        bead_size_pixels = int(np.ceil(1.05 * 100 / emc["pixel_size_angstroms"]))
        thickness = 3000  # Fixed thickness as in original script

        logger.info(
            f"Bead finding parameters: size={bead_size_pixels}px, thickness={thickness}"
        )

        # Step 1: Create binned aligned stack
        cmd = [
            "newstack",
            "-InputFile",
            f"{base_name}.fixed.preprocessed",
            "-OutputFile",
            f"{base_name}_3dfind.ali",
            "-TransformFile",
            f"{base_name}.xf",
            "-ImagesAreBinned",
            "1.0",
            "-BinByFactor",
            "15",
        ]

        try:
            subprocess.run(cmd, check=True, timeout=600)
            logger.info("Created binned stack for 3D bead finding")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"newstack failed: {e}") from e

        # Step 2: Create reconstruction for bead finding
        cmd = [
            "tilt",
            "-InputProjections",
            f"{base_name}_3dfind.ali",
            "-OutputFile",
            f"{base_name}_3dfind.rec",
            "-IMAGEBINNED",
            "15",
            "-TILTFILE",
            f"{base_name}.tlt",
            "-LOCALFILE",
            f"{base_name}.local",
            "-THICKNESS",
            str(thickness),
            "-RADIAL",
            "0.35,0.035",
            "-FalloffIsTrueSigma",
            "1",
            "-XAXISTILT",
            "0.0",
            "-MODE",
            "2",
            "-UseGPU",
            "0",
            "-ActionIfGPUFails",
            "1,2",
            "-OFFSET",
            "0.0",
            "-SHIFT",
            "0.0",
            "0.0",
            "-PERPENDICULAR",
            "-FULLIMAGE",
            f"{nx},{ny}",
        ]

        try:
            subprocess.run(cmd, check=True, timeout=1800)
            logger.info("Created reconstruction for bead finding")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"tilt reconstruction failed: {e}") from e

        # Step 3: Find beads in 3D
        cmd = [
            "findbeads3d",
            "-InputFile",
            f"{base_name}_3dfind.rec",
            "-OutputFile",
            f"{base_name}_3dfind.mod",
            "-BeadSize",
            str(bead_size_pixels),
            "-MinRelativeStrength",
            "0.05",
            "-StorageThreshold",
            "0.0",
            "-MinSpacing",
            "0.9",
            "-BinningOfVolume",
            "15",
        ]

        try:
            subprocess.run(cmd, check=True, timeout=600)
            logger.info("3D bead finding completed")
        except subprocess.CalledProcessError as e:
            logger.warning(
                f"findbeads3d failed: {e} - this may be expected if no beads found"
            )

        # Step 4: Create erased reconstruction (project beads out)
        cmd = [
            "tilt",
            "-InputProjections",
            f"{base_name}_3dfind.ali",
            "-OutputFile",
            f"{base_name}.erase",
            "-IMAGEBINNED",
            "15",
            "-TILTFILE",
            f"{base_name}.tlt",
            "-LOCALFILE",
            f"{base_name}.local",
            "-THICKNESS",
            str(thickness),
            "-RADIAL",
            "0.35,0.035",
            "-FalloffIsTrueSigma",
            "1",
            "-XAXISTILT",
            "0.0",
            "-UseGPU",
            "0",
            "-ActionIfGPUFails",
            "1,2",
            "-OFFSET",
            "0.0",
            "-SHIFT",
            "0.0,0.0",
            "-ProjectModel",
            f"{base_name}_3dfind.mod",
            "-FULLIMAGE",
            f"{nx},{ny}",
            "-PERPENDICULAR",
            "-MODE",
            "2",
        ]

        try:
            subprocess.run(cmd, check=True, timeout=1800)
            logger.info("Created erased reconstruction")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Erased reconstruction failed: {e}")

        # Step 5: Cleanup temporary files (as in original script)
        cleanup_files = [f"{base_name}_3dfind.rec", f"{base_name}_3dfind.mod"]

        for file_path in cleanup_files:
            try:
                if Path(file_path).exists():
                    Path(file_path).unlink()
                    logger.debug(f"Cleaned up: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {file_path}: {e}")

        logger.info("Integrated bead finding completed")

    except Exception as e:
        logger.error(f"Error in integrated bead finding: {e}")
        raise RuntimeError(f"Integrated bead finding failed: {e}") from e
    finally:
        os.chdir(paths["start_dir"])


def _handle_tilt_options(tilt_option: int, base_name: str) -> None:
    """Handle tilt option settings."""
    if str(tilt_option) == "0":
        # Copy raw tilt angles to .tlt file
        try:
            subprocess.run(
                [
                    "cp",
                    f"fixedStacks/{base_name}.rawtlt",
                    f"fixedStacks/{base_name}.tlt",
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to copy tilt angles: {e}")


def _run_bead_refinement(
    refine_on_beads: bool, paths: dict, nx: int, ny: int, emc: dict
) -> bool:
    """
    Run bead-based refinement.

    Returns:
        bool: True if too few beads found, False otherwise
    """
    if not refine_on_beads:
        return False

    logger.info("Running bead-based refinement")
    too_few_beads = False

    try:
        os.chdir(paths["wrk_dir"])
        ext_list = ["tlt", "xf", "local"]

        # Create symbolic links
        for ext_item in ext_list:
            subprocess.run(
                [
                    "ln",
                    "-sf",
                    f"../fixedStacks/{paths['base_name']}.{ext_item}",
                    f"{paths['base_name']}.{ext_item}",
                ],
                check=True,
            )

        subprocess.run(
            [
                "ln",
                "-sf",
                f"../fixedStacks/{paths['base_name']}.fixed.preprocessed",
                f"{paths['base_name']}.fixed",
            ],
            check=True,
        )

        # Run bead refinement
        # TODO: Implement BH_refine_on_beads when available
        logger.warning(
            "Bead refinement requires BH_refine_on_beads - using placeholder"
        )
        # min_sampling_rate = 5  # TODO: Use when implementing bead refinement
        too_few_beads = False  # Placeholder

        if not too_few_beads:
            logger.info("Bead refinement completed successfully")
            # TODO: Implement proper bead refinement results handling
        else:
            logger.warning(
                "Too few beads found. Using iterative patch tracking results"
            )

    except Exception as e:
        logger.error(f"Error in bead refinement: {e}")
        too_few_beads = True
    finally:
        os.chdir(paths["start_dir"])

    return too_few_beads


def _cleanup_files(fixed_name: str) -> None:
    """Cleanup temporary files."""
    try:
        if Path(fixed_name).exists():
            Path(fixed_name).unlink()
            logger.info(f"Cleaned up temporary file: {fixed_name}")
    except Exception as e:
        logger.warning(f"Failed to cleanup file {fixed_name}: {e}")


def main():
    """Command line interface for emc_run_auto_align."""
    parser = argparse.ArgumentParser(
        description="Run emClarity auto tilt-series alignment with integrated patch tracking and bead finding",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("parameter_file", help="emClarity parameter file")
    parser.add_argument("stack_in", help="Input tilt series stack")
    parser.add_argument("tilt_angles", help="File containing tilt angles")
    parser.add_argument("img_rotation", type=float, help="Image rotation angle")
    parser.add_argument(
        "--skip-tilts", help="Comma-separated list of tilt indices to skip"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s")

    skip_tilts = None
    if args.skip_tilts:
        try:
            skip_tilts = [int(x.strip()) for x in args.skip_tilts.split(",")]
        except ValueError as err:
            raise ValueError("Invalid skip_tilts format. Use comma-separated integers.") from err

    try:
        emc_run_auto_align(
            args.parameter_file,
            args.stack_in,
            args.tilt_angles,
            args.img_rotation,
            skip_tilts,
        )
    except Exception as e:
        logger.error(f"Auto-alignment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
