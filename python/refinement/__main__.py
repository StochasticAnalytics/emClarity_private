r"""CLI entry point for CTF refinement.

Run as::

    python -m refinement --star input.star --stack particles.mrc \
        --ref reference.mrc --output refined.star

Maps CLI arguments to :class:`PipelineOptions` and calls
:func:`refine_ctf_from_star`.

Port reference: ``ctf/EMC_ctf_refine_from_star.m`` lines 577-593 (options).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_VALID_OPTIMIZERS = ("adam", "lbfgsb")


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for CTF refinement CLI.

    Returns:
        Configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="emclarity-ctf-refine",
        description=(
            "Refine per-tilt CTF parameters (defocus, astigmatism, "
            "per-particle z-offsets) from a cisTEM-style star file."
        ),
    )

    # -- Required arguments --------------------------------------------------
    required = parser.add_argument_group("required arguments")
    required.add_argument(
        "--star",
        type=str,
        required=True,
        help="Input cisTEM-style 30-column star file.",
    )
    required.add_argument(
        "--stack",
        type=str,
        required=True,
        help="MRC particle stack file.",
    )
    required.add_argument(
        "--ref",
        type=str,
        required=True,
        help="MRC 3D reference volume.",
    )
    required.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output path for the refined star file.",
    )

    # -- Optional arguments --------------------------------------------------
    parser.add_argument(
        "--defocus-search-range",
        type=float,
        default=5000.0,
        metavar="ANGSTROMS",
        help="Symmetric defocus search range in Angstroms (default: 5000).",
    )
    parser.add_argument(
        "--maximum-iterations",
        type=int,
        default=15,
        metavar="N",
        help="Maximum optimiser iterations per tilt group (default: 15).",
    )
    parser.add_argument(
        "--lowpass-cutoff",
        type=float,
        default=10.0,
        metavar="ANGSTROMS",
        help="Low-pass resolution cutoff in Angstroms (default: 10).",
    )
    parser.add_argument(
        "--highpass-cutoff",
        type=float,
        default=400.0,
        metavar="ANGSTROMS",
        help="High-pass resolution cutoff in Angstroms (default: 400).",
    )
    parser.add_argument(
        "--optimizer",
        type=str,
        default="adam",
        choices=_VALID_OPTIMIZERS,
        help="Optimiser algorithm: 'adam' or 'lbfgsb' (default: adam).",
    )
    parser.add_argument(
        "--global-only",
        action="store_true",
        default=False,
        help="Only optimise tilt-global parameters (no per-particle offsets).",
    )

    # -- Debug options -------------------------------------------------------
    debug_group = parser.add_argument_group("debug options")
    debug_group.add_argument(
        "--debug-tilt-list",
        type=str,
        default="",
        metavar="NAMES",
        help=(
            "Comma-separated list of tilt names to process. "
            "Empty means all tilts (default: '')."
        ),
    )
    debug_group.add_argument(
        "--exit-after-n-tilts",
        type=int,
        default=0,
        metavar="N",
        help="Stop after processing N tilt groups. 0 = all (default: 0).",
    )
    debug_group.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose (DEBUG-level) logging.",
    )
    debug_group.add_argument(
        "--cpu",
        action="store_true",
        default=False,
        help="Force CPU-only mode (disable GPU acceleration).",
    )

    return parser


def _validate_input_paths(args: argparse.Namespace) -> list[str]:
    """Check that required input files exist.

    Args:
        args: Parsed CLI arguments.

    Returns:
        List of error messages (empty if all paths valid).
    """
    errors: list[str] = []
    for label, path_str in [
        ("--star", args.star),
        ("--stack", args.stack),
        ("--ref", args.ref),
    ]:
        p = Path(path_str)
        if not p.exists():
            errors.append(f"{label}: file not found: {p}")
    return errors


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for CTF refinement.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        Exit code: 0 on success, 1 on user error, 2 on runtime error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # -- Configure logging ---------------------------------------------------
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s | %(name)s | %(message)s",
    )

    # -- Validate input paths ------------------------------------------------
    path_errors = _validate_input_paths(args)
    if path_errors:
        for err in path_errors:
            logger.error(err)
        return 1

    # -- Validate output directory exists ------------------------------------
    output_path = Path(args.output)
    output_dir = output_path.parent
    if not output_dir.exists():
        logger.error(
            "--output: parent directory does not exist: %s", output_dir,
        )
        return 1

    # -- Deferred imports (avoid loading heavy deps for --help / validation) -
    from .emc_ctf_refine_pipeline import PipelineOptions, refine_ctf_from_star

    # -- Build pipeline options ----------------------------------------------
    options = PipelineOptions(
        optimizer_type=args.optimizer,
        defocus_search_range=args.defocus_search_range,
        maximum_iterations=args.maximum_iterations,
        lowpass_cutoff=args.lowpass_cutoff,
        highpass_cutoff=args.highpass_cutoff,
        global_only=args.global_only,
        debug_tilt_list=args.debug_tilt_list,
        exit_after_n_tilts=args.exit_after_n_tilts,
    )

    # -- Run pipeline --------------------------------------------------------
    try:
        results = refine_ctf_from_star(
            star_path=Path(args.star),
            stack_path=Path(args.stack),
            reference_volume_path=Path(args.ref),
            output_star_path=output_path,
            options=options,
        )
    except Exception:
        logger.exception("CTF refinement failed")
        return 2

    logger.info(
        "Refined %d / %d particles across %d tilt groups",
        results.n_particles_processed,
        results.n_particles_total,
        results.n_tilt_groups,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
