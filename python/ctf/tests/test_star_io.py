"""
Tests for the cisTEM-style 30-column star file I/O module.

Uses a synthetic star file with 5 particles across 2 tilt groups to verify
parsing, writing, roundtripping, grouping, and error handling.
"""

import textwrap
from pathlib import Path

import pytest

from ..star_io.emc_star_parser import (
    COLUMN_SPEC,
    NUM_COLUMNS,
    group_particles_by_tilt,
    parse_star_file,
    write_star_file,
)

# ---------------------------------------------------------------------------
# Synthetic star file fixture: 5 particles, 2 tilt groups
# ---------------------------------------------------------------------------
# Tilt group A: "tiltA.mrc" at tilt angle 15.0 (particles 1, 2, 3)
# Tilt group B: "tiltB.mrc" at tilt angle -30.5 (particles 4, 5)

STAR_FILE_CONTENT = textwrap.dedent("""\
    # This is a comment line
    #
    data_emClarity
    loop_
    _cisTEMPositionInStack #1
    _cisTEMAnglePsi #2
    _cisTEMAngleTheta #3
    _cisTEMAnglePhi #4
    _cisTEMXShift #5
    _cisTEMYShift #6
    _cisTEMDefocus1 #7
    _cisTEMDefocus2 #8
    _cisTEMDefocusAngle #9
    _cisTEMPhaseShift #10
    _cisTEMOccupancy #11
    _cisTEMLogP #12
    _cisTEMSigma #13
    _cisTEMScore #14
    _cisTEMScoreChange #15
    _cisTEMPixelSize #16
    _cisTEMVoltage #17
    _cisTEMCs #18
    _cisTEMAmplitudeContrast #19
    _cisTEMBeamTiltX #20
    _cisTEMBeamTiltY #21
    _cisTEMImageShiftX #22
    _cisTEMImageShiftY #23
    _cisTEMBest2DClass #24
    _cisTEMBeamTiltGroup #25
    _cisTEMParticleGroup #26
    _cisTEMPreExposure #27
    _cisTEMTotalExposure #28
    _cisTEMOriginalImageFilename #29
    _cisTEMOriginalXPosition #30
    1 12.5 45.0 90.0 1.25 -0.75 25000.5 24800.3 35.2 0.0 100.0 -5000.0 1.0 0.1234 0.001 1.35 300.0 2.7 0.07 0.0 0.0 0.0 0.0 1 1 1 0.0 3.5 tiltA.mrc 15.0
    2 13.0 44.5 91.2 1.30 -0.80 25100.0 24900.0 35.5 0.0 100.0 -4800.0 1.0 0.1300 0.002 1.35 300.0 2.7 0.07 0.0 0.0 0.0 0.0 1 1 1 0.0 3.5 tiltA.mrc 15.0
    3 14.2 46.1 89.8 1.10 -0.60 25200.0 25000.0 34.8 0.0 100.0 -5100.0 1.0 0.1100 -0.001 1.35 300.0 2.7 0.07 0.0 0.0 0.0 0.0 2 1 1 0.0 3.5 tiltA.mrc 15.0
    4 20.0 50.3 85.0 2.00 -1.50 26000.0 25500.0 40.0 0.0 100.0 -4500.0 1.0 0.0900 0.003 1.35 300.0 2.7 0.07 0.0 0.0 0.0 0.0 3 2 2 3.5 7.0 tiltB.mrc -30.5
    5 21.5 51.0 84.5 2.10 -1.60 26100.0 25600.0 40.5 0.0 100.0 -4600.0 1.0 0.0950 0.004 1.35 300.0 2.7 0.07 0.0 0.0 0.0 0.0 3 2 2 3.5 7.0 tiltB.mrc -30.5
""")


@pytest.fixture
def star_file(tmp_path: Path) -> Path:
    """Write the synthetic star file to a temporary directory."""
    p = tmp_path / "test.star"
    p.write_text(STAR_FILE_CONTENT)
    return p


@pytest.fixture
def parsed(star_file: Path) -> tuple[list[dict], list[str]]:
    """Parse the synthetic star file."""
    return parse_star_file(star_file)


# ---------------------------------------------------------------------------
# Positive control: parser handles empty lines and comment lines in header
# ---------------------------------------------------------------------------

class TestParseHeader:
    """Verify header line handling (positive control)."""

    def test_header_count(self, parsed: tuple[list[dict], list[str]]) -> None:
        """Header should contain comment lines, data_, loop_, and _cisTEM labels."""
        _, header_lines = parsed
        # 2 comment lines + data_ + loop_ + 30 column labels = 34
        assert len(header_lines) == 34

    def test_comment_lines_preserved(self, parsed: tuple[list[dict], list[str]]) -> None:
        _, header_lines = parsed
        assert header_lines[0] == "# This is a comment line"
        assert header_lines[1] == "#"

    def test_directive_lines_preserved(self, parsed: tuple[list[dict], list[str]]) -> None:
        _, header_lines = parsed
        assert header_lines[2] == "data_emClarity"
        assert header_lines[3] == "loop_"

    def test_column_labels_preserved(self, parsed: tuple[list[dict], list[str]]) -> None:
        _, header_lines = parsed
        # First label is at index 4
        assert header_lines[4].strip().startswith("_cisTEM")


# ---------------------------------------------------------------------------
# Core parsing tests
# ---------------------------------------------------------------------------

class TestParseStarFile:
    """Verify correct parsing of data rows."""

    def test_particle_count(self, parsed: tuple[list[dict], list[str]]) -> None:
        particles, _ = parsed
        assert len(particles) == 5

    def test_all_columns_present(self, parsed: tuple[list[dict], list[str]]) -> None:
        particles, _ = parsed
        expected_keys = {name for name, _ in COLUMN_SPEC}
        for p in particles:
            assert set(p.keys()) == expected_keys

    def test_column_spec_length(self) -> None:
        assert NUM_COLUMNS == 30

    # --- Type correctness (acceptance criteria) ---

    def test_position_in_stack_is_int(self, parsed: tuple[list[dict], list[str]]) -> None:
        particles, _ = parsed
        for p in particles:
            assert isinstance(p["position_in_stack"], int)

    def test_defocus_1_is_float(self, parsed: tuple[list[dict], list[str]]) -> None:
        particles, _ = parsed
        for p in particles:
            assert isinstance(p["defocus_1"], float)

    def test_original_image_filename_is_str(self, parsed: tuple[list[dict], list[str]]) -> None:
        particles, _ = parsed
        for p in particles:
            assert isinstance(p["original_image_filename"], str)

    def test_int_columns_are_int(self, parsed: tuple[list[dict], list[str]]) -> None:
        int_cols = [name for name, t in COLUMN_SPEC if t is int]
        particles, _ = parsed
        for p in particles:
            for col in int_cols:
                assert isinstance(p[col], int), f"{col} should be int"

    def test_float_columns_are_float(self, parsed: tuple[list[dict], list[str]]) -> None:
        float_cols = [name for name, t in COLUMN_SPEC if t is float]
        particles, _ = parsed
        for p in particles:
            for col in float_cols:
                assert isinstance(p[col], float), f"{col} should be float"

    # --- Spot-check specific values ---

    def test_first_particle_values(self, parsed: tuple[list[dict], list[str]]) -> None:
        particles, _ = parsed
        p = particles[0]
        assert p["position_in_stack"] == 1
        assert p["psi"] == 12.5
        assert p["theta"] == 45.0
        assert p["phi"] == 90.0
        assert p["x_shift"] == 1.25
        assert p["y_shift"] == -0.75
        assert p["defocus_1"] == 25000.5
        assert p["defocus_2"] == 24800.3
        assert p["defocus_angle"] == 35.2
        assert p["phase_shift"] == 0.0
        assert p["occupancy"] == 100.0
        assert p["logp"] == -5000.0
        assert p["sigma"] == 1.0
        assert p["score"] == 0.1234
        assert p["score_change"] == 0.001
        assert p["pixel_size"] == 1.35
        assert p["voltage_kv"] == 300.0
        assert p["cs_mm"] == 2.7
        assert p["amplitude_contrast"] == 0.07
        assert p["beam_tilt_x"] == 0.0
        assert p["beam_tilt_y"] == 0.0
        assert p["image_shift_x"] == 0.0
        assert p["image_shift_y"] == 0.0
        assert p["best_2d_class"] == 1
        assert p["beam_tilt_group"] == 1
        assert p["particle_group"] == 1
        assert p["pre_exposure"] == 0.0
        assert p["total_exposure"] == 3.5
        assert p["original_image_filename"] == "tiltA.mrc"
        assert p["tilt_angle"] == 15.0

    def test_last_particle_values(self, parsed: tuple[list[dict], list[str]]) -> None:
        particles, _ = parsed
        p = particles[4]
        assert p["position_in_stack"] == 5
        assert p["original_image_filename"] == "tiltB.mrc"
        assert p["tilt_angle"] == -30.5
        assert p["defocus_1"] == 26100.0
        assert p["beam_tilt_group"] == 2


# ---------------------------------------------------------------------------
# Negative control: wrong column count
# ---------------------------------------------------------------------------

class TestParseErrors:
    """Verify error handling for malformed data."""

    def test_too_few_columns_raises_value_error(self, tmp_path: Path) -> None:
        """A data row with 29 columns should raise ValueError."""
        content = textwrap.dedent("""\
            # header
            data_test
            loop_
            _cisTEMPositionInStack #1
            1 12.5 45.0 90.0 1.25 -0.75 25000.5 24800.3 35.2 0.0 100.0 -5000.0 1.0 0.1234 0.001 1.35 300.0 2.7 0.07 0.0 0.0 0.0 0.0 1 1 1 0.0 3.5 tiltA.mrc
        """)
        p = tmp_path / "bad.star"
        p.write_text(content)
        with pytest.raises(ValueError, match="expected 30 columns"):
            parse_star_file(p)

    def test_too_many_columns_raises_value_error(self, tmp_path: Path) -> None:
        """A data row with 31 columns should also raise ValueError."""
        content = textwrap.dedent("""\
            # header
            1 12.5 45.0 90.0 1.25 -0.75 25000.5 24800.3 35.2 0.0 100.0 -5000.0 1.0 0.1234 0.001 1.35 300.0 2.7 0.07 0.0 0.0 0.0 0.0 1 1 1 0.0 3.5 tiltA.mrc 15.0 EXTRA
        """)
        p = tmp_path / "extra.star"
        p.write_text(content)
        with pytest.raises(ValueError, match="expected 30 columns"):
            parse_star_file(p)

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_star_file(tmp_path / "nonexistent.star")


# ---------------------------------------------------------------------------
# Roundtrip test (acceptance criterion)
# ---------------------------------------------------------------------------

class TestRoundtrip:
    """parse -> write -> parse must produce identical particle dicts."""

    def test_roundtrip_particles(
        self, star_file: Path, parsed: tuple[list[dict], list[str]], tmp_path: Path
    ) -> None:
        particles_1, headers_1 = parsed

        roundtrip_path = tmp_path / "roundtrip.star"
        write_star_file(roundtrip_path, particles_1, headers_1)

        particles_2, _headers_2 = parse_star_file(roundtrip_path)

        assert len(particles_2) == len(particles_1)
        for p1, p2 in zip(particles_1, particles_2, strict=False):
            assert p1 == p2, f"Mismatch: {p1} != {p2}"

    def test_roundtrip_header_count(
        self, star_file: Path, parsed: tuple[list[dict], list[str]], tmp_path: Path
    ) -> None:
        particles_1, headers_1 = parsed

        roundtrip_path = tmp_path / "roundtrip2.star"
        write_star_file(roundtrip_path, particles_1, headers_1)
        _, headers_2 = parse_star_file(roundtrip_path)

        assert len(headers_2) == len(headers_1)

    def test_double_roundtrip(
        self, star_file: Path, parsed: tuple[list[dict], list[str]], tmp_path: Path
    ) -> None:
        """Two roundtrips should still produce identical results."""
        particles_1, headers_1 = parsed

        path_a = tmp_path / "rt_a.star"
        write_star_file(path_a, particles_1, headers_1)
        particles_a, headers_a = parse_star_file(path_a)

        path_b = tmp_path / "rt_b.star"
        write_star_file(path_b, particles_a, headers_a)
        particles_b, _ = parse_star_file(path_b)

        for pa, pb in zip(particles_a, particles_b, strict=False):
            assert pa == pb


# ---------------------------------------------------------------------------
# Write error handling (negative controls)
# ---------------------------------------------------------------------------

class TestWriteErrors:
    """Verify write_star_file raises on unsupported inputs."""

    def test_space_in_filename_raises_value_error(
        self, parsed: tuple[list[dict], list[str]], tmp_path: Path
    ) -> None:
        """Filenames with spaces must raise ValueError (whitespace-delimited format)."""
        particles, headers = parsed
        # Shallow-copy the first particle and inject a space in the filename.
        bad_particle = dict(particles[0])
        bad_particle["original_image_filename"] = "tilt A.mrc"
        with pytest.raises(ValueError, match="spaces"):
            write_star_file(tmp_path / "should_not_exist.star", [bad_particle], headers)


# ---------------------------------------------------------------------------
# Group by tilt (acceptance criterion)
# ---------------------------------------------------------------------------

class TestGroupParticlesByTilt:
    """Verify tilt grouping logic."""

    def test_two_groups(self, parsed: tuple[list[dict], list[str]]) -> None:
        particles, _ = parsed
        groups = group_particles_by_tilt(particles)
        assert len(groups) == 2

    def test_group_names(self, parsed: tuple[list[dict], list[str]]) -> None:
        particles, _ = parsed
        groups = group_particles_by_tilt(particles)
        assert "tiltA.mrc" in groups
        assert "tiltB.mrc" in groups

    def test_group_sizes(self, parsed: tuple[list[dict], list[str]]) -> None:
        particles, _ = parsed
        groups = group_particles_by_tilt(particles)
        assert len(groups["tiltA.mrc"]) == 3
        assert len(groups["tiltB.mrc"]) == 2

    def test_group_particles_share_tilt_angle(
        self, parsed: tuple[list[dict], list[str]]
    ) -> None:
        particles, _ = parsed
        groups = group_particles_by_tilt(particles)
        for tilt_name, group in groups.items():
            angles = {p["tilt_angle"] for p in group}
            assert len(angles) == 1, (
                f"Particles in {tilt_name} have inconsistent tilt angles: {angles}"
            )

    def test_group_tilt_angles(self, parsed: tuple[list[dict], list[str]]) -> None:
        particles, _ = parsed
        groups = group_particles_by_tilt(particles)
        assert groups["tiltA.mrc"][0]["tilt_angle"] == 15.0
        assert groups["tiltB.mrc"][0]["tilt_angle"] == -30.5

    def test_empty_input(self) -> None:
        groups = group_particles_by_tilt([])
        assert groups == {}


# ---------------------------------------------------------------------------
# Positive control: parser handles edge cases in headers
# ---------------------------------------------------------------------------

class TestHeaderEdgeCases:
    """Additional positive controls for header handling."""

    def test_empty_lines_in_header(self, tmp_path: Path) -> None:
        """Empty lines between header entries should not cause errors."""
        content = textwrap.dedent("""\
            # comment

            data_test

            loop_
            _cisTEMPositionInStack #1

            1 12.5 45.0 90.0 1.25 -0.75 25000.5 24800.3 35.2 0.0 100.0 -5000.0 1.0 0.1234 0.001 1.35 300.0 2.7 0.07 0.0 0.0 0.0 0.0 1 1 1 0.0 3.5 tiltA.mrc 15.0
        """)
        p = tmp_path / "blanks.star"
        p.write_text(content)
        particles, header_lines = parse_star_file(p)
        assert len(particles) == 1
        # comment + blank + data_test + blank + loop_ + label + blank = 7
        assert len(header_lines) == 7

    def test_multiple_comment_styles(self, tmp_path: Path) -> None:
        """Lines starting with # should be treated as headers regardless of content."""
        content = textwrap.dedent("""\
            # comment one
            ## double hash
            #
            1 12.5 45.0 90.0 1.25 -0.75 25000.5 24800.3 35.2 0.0 100.0 -5000.0 1.0 0.1234 0.001 1.35 300.0 2.7 0.07 0.0 0.0 0.0 0.0 1 1 1 0.0 3.5 tiltA.mrc 15.0
        """)
        p = tmp_path / "comments.star"
        p.write_text(content)
        particles, header_lines = parse_star_file(p)
        assert len(particles) == 1
        assert len(header_lines) == 3
