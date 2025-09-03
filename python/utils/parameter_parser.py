#!/usr/bin/env python3
"""
Simplified parameter parser for emClarity Python implementation.

This is a basic version that handles the core functionality needed for auto-alignment.
For a full implementation, see the complete parser in testScripts/python/metaData/
"""

import ast
import os
from pathlib import Path
from typing import Any, Dict, Union


def parse_parameter_file(parameter_file: Union[str, Path]) -> Dict[str, Any]:
    """
    Parse emClarity parameter file.

    Args:
        parameter_file: Path to parameter file

    Returns:
        Dictionary of parsed parameters

    Raises:
        FileNotFoundError: If parameter file doesn't exist
        ValueError: If required parameters are missing
    """
    parameter_file = Path(parameter_file)
    if not parameter_file.exists():
        raise FileNotFoundError(f"Parameter file not found: {parameter_file}")

    # Parse basic parameters
    params = _parse_basic_parameters(parameter_file)

    # Validate and set defaults
    params = _validate_and_set_defaults(params)

    return params


def _parse_basic_parameters(parameter_file: Path) -> Dict[str, Any]:
    """Parse basic parameters from file."""
    params = {}

    # String parameters that should not be evaluated
    string_keys = {
        "subtomometa",
        "ali_mtype",
        "cls_mtype",
        "raw_mtype",
        "fsc_mtype",
        "pca_distmeasure",
        "kms_mtype",
        "flgprecision",
        "tmp_xcfscale",
        "fastscratchdisk",
        "tmp_erasemasktype",
        "startingdirection",
        "peak_mtype",
        "symmetry",
        "gmm_covariance_type",
        "distance_metric",
    }

    try:
        with open(parameter_file, "r") as f:
            lines = f.readlines()
    except Exception as e:
        raise ValueError(f"Error reading parameter file: {e}")

    # Remove comments and empty lines
    raw_lines = []
    for line in lines:
        cleaned_line = line.split("%", 1)[0].strip()
        if cleaned_line:
            raw_lines.append(cleaned_line)

    # Parse name=value pairs
    for line in raw_lines:
        parts = line.split("=", 1)
        if len(parts) == 2:
            name = parts[0].strip()
            value_str = parts[1].strip()

            if not name:
                continue

            if name.lower() in string_keys:
                params[name] = value_str
            else:
                try:
                    params[name] = ast.literal_eval(value_str)
                except (ValueError, SyntaxError):
                    # If it can't be evaluated, store as string
                    params[name] = value_str

    return params


def _validate_and_set_defaults(params: Dict[str, Any]) -> Dict[str, Any]:
    """Validate required parameters and set defaults."""

    # Check required parameters
    required = [
        "PIXEL_SIZE",
        "Cs",
        "VOLTAGE",
        "AMPCONT",
        "nGPUs",
        "nCpuCores",
        "symmetry",
    ]
    for req in required:
        if req not in params:
            raise ValueError(f"Required parameter '{req}' not found in parameter file")

    # Validate and convert pixel size
    if not isinstance(params["PIXEL_SIZE"], (int, float)) or params["PIXEL_SIZE"] <= 0:
        raise ValueError("PIXEL_SIZE must be a positive number")

    params["pixel_size_si"] = params["PIXEL_SIZE"]
    params["pixel_size_angstroms"] = params["PIXEL_SIZE"] * 1e10

    # Validate other required parameters
    if not isinstance(params["Cs"], (int, float)) or params["Cs"] < 0:
        raise ValueError("Cs must be a non-negative number")

    if not isinstance(params["VOLTAGE"], (int, float)) or params["VOLTAGE"] < 20e3:
        raise ValueError("VOLTAGE must be >= 20,000 V")

    if not isinstance(params["AMPCONT"], (int, float)) or not (
        0 <= params["AMPCONT"] <= 1
    ):
        raise ValueError("AMPCONT must be between 0 and 1")

    if not isinstance(params["nGPUs"], int) or params["nGPUs"] < 1:
        raise ValueError("nGPUs must be a positive integer")

    if not isinstance(params["nCpuCores"], int) or params["nCpuCores"] < 1:
        raise ValueError("nCpuCores must be a positive integer")

    # Handle fastScratchDisk
    if "fastScratchDisk" not in params:
        params["fastScratchDisk"] = ""
    elif str(params["fastScratchDisk"]).lower() == "ram":
        # Handle RAM disk configuration
        emc_cache_mem = os.getenv("EMC_CACHE_MEM")
        if not emc_cache_mem:
            print("EMC_CACHE_MEM environment variable not found. Disabling RAM disk.")
            params["fastScratchDisk"] = ""
        else:
            try:
                mem_gb = float(emc_cache_mem)
                if mem_gb < 32:
                    print(f"EMC_CACHE_MEM ({mem_gb}GB) < 32GB. Disabling RAM disk.")
                    params["fastScratchDisk"] = ""
                else:
                    mcr_cache = os.getenv("MCR_CACHE_ROOT")
                    params["fastScratchDisk"] = mcr_cache if mcr_cache else ""
            except ValueError:
                print("Invalid EMC_CACHE_MEM value. Disabling RAM disk.")
                params["fastScratchDisk"] = ""

    # Set auto-alignment defaults
    auto_ali_defaults = {
        "autoAli_max_resolution": 18.0,
        "autoAli_min_sampling_rate": 10.0,
        "autoAli_max_sampling_rate": 4.0,
        "autoAli_patch_size_factor": 4,
        "autoAli_refine_on_beads": False,
        "autoAli_patch_tracking_border": 64,
        "autoAli_n_iters_no_rotation": 3,
        "autoAli_patch_overlap": 0.5,
        "autoAli_iterations_per_bin": 3,
        "autoAli_max_shift_in_angstroms": 40.0,
        "autoAli_max_shift_factor": 1,
        "autoAli_switchAxes": True,
        "beadDiameter": 0.0,
    }

    for key, default_value in auto_ali_defaults.items():
        if key not in params:
            params[key] = default_value

    # Set other common defaults
    common_defaults = {
        "nPeaks": 1,
        "CUTPADDING": 20,
        "flgCCCcutoff": 0.0,
        "flgProjectVolumes": False,
        "flgLimitToOneProcess": False,
        "force_no_symmetry": False,
    }

    for key, default_value in common_defaults.items():
        if key not in params:
            params[key] = default_value

    # Handle force_no_symmetry
    if params.get("force_no_symmetry"):
        params["symmetry"] = "C1"

    # Handle limit to one process
    if params.get("flgLimitToOneProcess"):
        params["nCpuCores"] = 1

    return params


def test_parameter_parser():
    """Test the parameter parser with a simple parameter file."""
    print("Testing parameter parser...")

    # Create test parameter file
    test_file = Path("/tmp/test_param.m")
    with open(test_file, "w") as f:
        f.write("% Test parameter file\n")
        f.write("subTomoMeta=test_project\n")
        f.write("PIXEL_SIZE=2.0e-10\n")
        f.write("Cs=2.7e-3\n")
        f.write("VOLTAGE=300e3\n")
        f.write("AMPCONT=0.07\n")
        f.write("nGPUs=2\n")
        f.write("nCpuCores=8\n")
        f.write("symmetry=C1\n")
        f.write("autoAli_max_resolution=20.0\n")
        f.write("beadDiameter=100e-10\n")

    try:
        # Test parsing
        params = parse_parameter_file(test_file)

        print("✅ Parameter parsing successful!")
        print(f"   Pixel size: {params['pixel_size_angstroms']} Å")
        print(f"   Voltage: {params['VOLTAGE']} V")
        print(f"   GPUs: {params['nGPUs']}")
        print(f"   Auto-alignment resolution: {params['autoAli_max_resolution']} Å")
        print(f"   Bead diameter: {params['beadDiameter']} m")

        # Test defaults
        assert params["autoAli_min_sampling_rate"] == 10.0
        assert params["nPeaks"] == 1
        assert params["flgProjectVolumes"] is False

        print("✅ All tests passed!")

    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    test_parameter_parser()
