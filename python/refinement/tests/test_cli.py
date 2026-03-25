"""Tests for the CTF refinement CLI entry point.

Tests argument parsing, input validation, and error handling without
requiring real MRC files or GPU hardware.

Positive controls:
    - ``build_parser`` always succeeds (independent of test logic)
    - ``--help`` always exits with code 0

Negative controls:
    - Missing required args always fails (independent of implementation)
    - Non-existent input files always produce exit code 1
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from .. import emc_ctf_refine_pipeline as pipeline_module
from ..__main__ import _validate_input_paths, build_parser, main

# ---------------------------------------------------------------------------
# Positive control: parser construction always succeeds
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Verify that build_parser returns a usable ArgumentParser."""

    def test_parser_is_created(self):
        parser = build_parser()
        assert parser is not None
        assert parser.prog == "emclarity-ctf-refine"

    def test_help_exits_zero(self):
        """--help always exits with code 0 (positive control)."""
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Required arguments
# ---------------------------------------------------------------------------


class TestRequiredArgs:
    """Missing required args produce argparse errors, not tracebacks."""

    def test_no_args_exits_with_error(self):
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2  # argparse default for missing args

    def test_missing_star_exits_with_error(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--stack", "y", "--ref", "z", "--output", "w"])
        assert exc_info.value.code == 2

    def test_missing_stack_exits_with_error(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--star", "x", "--ref", "z", "--output", "w"])
        assert exc_info.value.code == 2

    def test_missing_ref_exits_with_error(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--star", "x", "--stack", "y", "--output", "w"])
        assert exc_info.value.code == 2

    def test_missing_output_exits_with_error(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--star", "x", "--stack", "y", "--ref", "z"])
        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Argument defaults match MATLAB
# ---------------------------------------------------------------------------


class TestDefaults:
    """All defaults must match the MATLAB reference implementation."""

    @pytest.fixture()
    def parsed(self):
        parser = build_parser()
        return parser.parse_args([
            "--star", "a.star",
            "--stack", "b.mrc",
            "--ref", "c.mrc",
            "--output", "d.star",
        ])

    def test_defocus_search_range_default(self, parsed):
        assert parsed.defocus_search_range == 5000.0

    def test_maximum_iterations_default(self, parsed):
        assert parsed.maximum_iterations == 15

    def test_lowpass_cutoff_default(self, parsed):
        assert parsed.lowpass_cutoff == 10.0

    def test_highpass_cutoff_default(self, parsed):
        assert parsed.highpass_cutoff == 400.0

    def test_optimizer_default(self, parsed):
        assert parsed.optimizer == "adam"

    def test_global_only_default(self, parsed):
        assert parsed.global_only is False

    def test_debug_tilt_list_default(self, parsed):
        assert parsed.debug_tilt_list == ""

    def test_exit_after_n_tilts_default(self, parsed):
        assert parsed.exit_after_n_tilts == 0

    def test_verbose_default(self, parsed):
        assert parsed.verbose is False

    def test_cpu_default(self, parsed):
        assert parsed.cpu is False


# ---------------------------------------------------------------------------
# Optimizer validation
# ---------------------------------------------------------------------------


class TestOptimizerChoice:
    """--optimizer must accept valid values and reject invalid ones."""

    def test_adam_accepted(self):
        parser = build_parser()
        args = parser.parse_args([
            "--star", "a", "--stack", "b", "--ref", "c", "--output", "d",
            "--optimizer", "adam",
        ])
        assert args.optimizer == "adam"

    def test_lbfgsb_accepted(self):
        parser = build_parser()
        args = parser.parse_args([
            "--star", "a", "--stack", "b", "--ref", "c", "--output", "d",
            "--optimizer", "lbfgsb",
        ])
        assert args.optimizer == "lbfgsb"

    def test_invalid_optimizer_rejected(self):
        """Invalid optimizer produces argparse error (negative control)."""
        with pytest.raises(SystemExit) as exc_info:
            main([
                "--star", "a", "--stack", "b", "--ref", "c", "--output", "d",
                "--optimizer", "invalid",
            ])
        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Input path validation
# ---------------------------------------------------------------------------


class TestInputPathValidation:
    """Missing input files produce clean error messages, not tracebacks."""

    def test_missing_files_returns_exit_code_1(self, tmp_path):
        """Non-existent input files yield exit code 1."""
        result = main([
            "--star", str(tmp_path / "nonexistent.star"),
            "--stack", str(tmp_path / "nonexistent.mrc"),
            "--ref", str(tmp_path / "nonexistent.mrc"),
            "--output", str(tmp_path / "output.star"),
        ])
        assert result == 1

    def test_missing_star_only(self, tmp_path):
        """Only --star missing."""
        stack = tmp_path / "stack.mrc"
        ref = tmp_path / "ref.mrc"
        stack.write_bytes(b"\x00")
        ref.write_bytes(b"\x00")

        result = main([
            "--star", str(tmp_path / "missing.star"),
            "--stack", str(stack),
            "--ref", str(ref),
            "--output", str(tmp_path / "out.star"),
        ])
        assert result == 1

    def test_validate_input_paths_all_exist(self, tmp_path):
        """No errors when all files exist (positive control)."""
        star = tmp_path / "input.star"
        stack = tmp_path / "stack.mrc"
        ref = tmp_path / "ref.mrc"
        for f in (star, stack, ref):
            f.write_bytes(b"\x00")

        ns = MagicMock()
        ns.star = str(star)
        ns.stack = str(stack)
        ns.ref = str(ref)

        errors = _validate_input_paths(ns)
        assert errors == []

    def test_validate_input_paths_none_exist(self, tmp_path):
        """All three missing paths reported."""
        ns = MagicMock()
        ns.star = str(tmp_path / "a")
        ns.stack = str(tmp_path / "b")
        ns.ref = str(tmp_path / "c")

        errors = _validate_input_paths(ns)
        assert len(errors) == 3

    def test_missing_output_directory(self, tmp_path):
        """Output dir doesn't exist → exit code 1."""
        star = tmp_path / "input.star"
        stack = tmp_path / "stack.mrc"
        ref = tmp_path / "ref.mrc"
        for f in (star, stack, ref):
            f.write_bytes(b"\x00")

        result = main([
            "--star", str(star),
            "--stack", str(stack),
            "--ref", str(ref),
            "--output", str(tmp_path / "nonexistent_dir" / "out.star"),
        ])
        assert result == 1


# ---------------------------------------------------------------------------
# Flag arguments
# ---------------------------------------------------------------------------


class TestFlagArguments:
    """Boolean flags (--global-only, --verbose, --cpu) work correctly."""

    def test_global_only_flag(self):
        parser = build_parser()
        args = parser.parse_args([
            "--star", "a", "--stack", "b", "--ref", "c", "--output", "d",
            "--global-only",
        ])
        assert args.global_only is True

    def test_verbose_flag(self):
        parser = build_parser()
        args = parser.parse_args([
            "--star", "a", "--stack", "b", "--ref", "c", "--output", "d",
            "--verbose",
        ])
        assert args.verbose is True

    def test_cpu_flag(self):
        parser = build_parser()
        args = parser.parse_args([
            "--star", "a", "--stack", "b", "--ref", "c", "--output", "d",
            "--cpu",
        ])
        assert args.cpu is True


# ---------------------------------------------------------------------------
# Debug options parsing
# ---------------------------------------------------------------------------


class TestDebugOptions:
    """Debug CLI options are correctly parsed."""

    def test_debug_tilt_list_parsed(self):
        parser = build_parser()
        args = parser.parse_args([
            "--star", "a", "--stack", "b", "--ref", "c", "--output", "d",
            "--debug-tilt-list", "tilt_001.mrc,tilt_002.mrc",
        ])
        assert args.debug_tilt_list == "tilt_001.mrc,tilt_002.mrc"

    def test_exit_after_n_tilts_parsed(self):
        parser = build_parser()
        args = parser.parse_args([
            "--star", "a", "--stack", "b", "--ref", "c", "--output", "d",
            "--exit-after-n-tilts", "3",
        ])
        assert args.exit_after_n_tilts == 3


# ---------------------------------------------------------------------------
# Pipeline options mapping
# ---------------------------------------------------------------------------


class TestPipelineOptionsMapping:
    """CLI args are correctly mapped to PipelineOptions fields.

    Uses mock to avoid actually running the pipeline.
    """

    @patch.object(pipeline_module, "refine_ctf_from_star")
    def test_options_passed_to_pipeline(self, mock_refine, tmp_path):
        """Verify all CLI args map to the correct PipelineOptions fields."""
        star = tmp_path / "input.star"
        stack = tmp_path / "stack.mrc"
        ref = tmp_path / "ref.mrc"
        output = tmp_path / "output.star"
        for f in (star, stack, ref):
            f.write_bytes(b"\x00")

        mock_refine.return_value = MagicMock(
            n_particles_processed=0,
            n_particles_total=0,
            n_tilt_groups=0,
        )

        result = main([
            "--star", str(star),
            "--stack", str(stack),
            "--ref", str(ref),
            "--output", str(output),
            "--optimizer", "lbfgsb",
            "--defocus-search-range", "3000",
            "--maximum-iterations", "10",
            "--lowpass-cutoff", "8.0",
            "--highpass-cutoff", "300.0",
            "--global-only",
            "--debug-tilt-list", "tilt_001.mrc",
            "--exit-after-n-tilts", "2",
        ])

        assert result == 0
        mock_refine.assert_called_once()

        _, kwargs = mock_refine.call_args
        opts = kwargs["options"]
        assert opts.optimizer_type == "lbfgsb"
        assert opts.defocus_search_range == 3000.0
        assert opts.maximum_iterations == 10
        assert opts.lowpass_cutoff == 8.0
        assert opts.highpass_cutoff == 300.0
        assert opts.global_only is True
        assert opts.debug_tilt_list == "tilt_001.mrc"
        assert opts.exit_after_n_tilts == 2

    @patch.object(pipeline_module, "refine_ctf_from_star")
    def test_pipeline_exception_returns_exit_2(self, mock_refine, tmp_path):
        """Runtime errors in the pipeline yield exit code 2."""
        star = tmp_path / "input.star"
        stack = tmp_path / "stack.mrc"
        ref = tmp_path / "ref.mrc"
        for f in (star, stack, ref):
            f.write_bytes(b"\x00")

        mock_refine.side_effect = RuntimeError("test error")

        result = main([
            "--star", str(star),
            "--stack", str(stack),
            "--ref", str(ref),
            "--output", str(tmp_path / "output.star"),
        ])
        assert result == 2
