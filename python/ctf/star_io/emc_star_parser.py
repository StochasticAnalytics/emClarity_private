"""
Parser and writer for cisTEM-style 30-column star files.

The star file format used by emClarity's CTF refinement pipeline has:
- Header lines: comments (#), column labels (_cisTEM*), data_/loop_ directives,
  and empty lines.
- Data rows: whitespace-delimited with exactly 30 columns per row.

Column definitions mirror the MATLAB reference at
ctf/EMC_ctf_refine_from_star.m lines 681-768.

Original MATLAB equivalent: ctf/EMC_ctf_refine_from_star.m (parse_star_file,
    write_refined_star_file, group_particles_by_tilt)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

# Column specification: (name, type) in file order (columns 1-30).
# Types: int for index/group columns, float for continuous values, str for text.
COLUMN_SPEC: list[tuple[str, type]] = [
    ("position_in_stack", int),       # 1
    ("psi", float),                   # 2
    ("theta", float),                 # 3
    ("phi", float),                   # 4
    ("x_shift", float),              # 5
    ("y_shift", float),              # 6
    ("defocus_1", float),            # 7
    ("defocus_2", float),            # 8
    ("defocus_angle", float),        # 9
    ("phase_shift", float),          # 10
    ("occupancy", float),            # 11
    ("logp", float),                 # 12
    ("sigma", float),                # 13
    ("score", float),                # 14
    ("score_change", float),         # 15
    ("pixel_size", float),           # 16
    ("voltage_kv", float),           # 17
    ("cs_mm", float),                # 18
    ("amplitude_contrast", float),   # 19
    ("beam_tilt_x", float),          # 20
    ("beam_tilt_y", float),          # 21
    ("image_shift_x", float),        # 22
    ("image_shift_y", float),        # 23
    ("best_2d_class", int),          # 24
    ("beam_tilt_group", int),        # 25
    ("particle_group", int),         # 26
    ("pre_exposure", float),         # 27
    ("total_exposure", float),       # 28
    ("original_image_filename", str),  # 29
    ("tilt_angle", float),           # 30
]

NUM_COLUMNS = len(COLUMN_SPEC)


def _is_header_line(line: str) -> bool:
    """Determine whether a line is a header line (not a data row).

    Header lines include empty/blank lines, comments (#), column label
    definitions (_cisTEM*), and STAR directives (data_, loop_).
    """
    stripped = line.strip()
    if not stripped:
        return True
    first_char = stripped[0]
    if first_char in ("#", "_"):
        return True
    return stripped.startswith(("data_", "loop_"))


def _parse_token(token: str, col_type: type) -> int | float | str:
    """Convert a whitespace-delimited token to the appropriate Python type.

    For int columns, handles both '1' and '1.0' representations (the MATLAB
    reference uses str2double for all numeric columns, producing doubles that
    are semantically integers for index/group fields).
    """
    if col_type is int:
        return int(float(token))
    if col_type is float:
        return float(token)
    # str — return as-is
    return token


def _format_value(value: int | float | str, col_type: type) -> str:
    """Format a particle field value for writing to a star file.

    Uses representations that roundtrip through parsing:
    - int: decimal integer string (no decimal point). Non-integral float
      values are truncated toward zero (e.g., 1.9 → "1") to match the
      MATLAB reference behaviour where all numeric columns are read via
      str2double then cast to integer for index/group fields.
    - float: Python str() which produces the shortest representation that
      uniquely identifies the float (guarantees float(str(x)) == x)
    - str: returned unchanged
    """
    if col_type is int:
        return str(int(value))
    if col_type is float:
        return str(float(value))
    return str(value)


def parse_star_file(path: Path) -> tuple[list[dict], list[str]]:
    """Parse a cisTEM-style 30-column star file.

    Reads header lines (comments, column labels, directives, blank lines)
    and data rows. Each data row must have exactly 30 whitespace-delimited
    tokens.

    Args:
        path: Path to the star file.

    Returns:
        A tuple of (particles, header_lines) where:
        - particles is a list of dicts, one per data row, with keys matching
          the 30 column names and values of appropriate types.
        - header_lines is a list of raw header line strings (newlines stripped).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If any data row does not have exactly 30 columns.
    """
    path = Path(path)
    header_lines: list[str] = []
    particles: list[dict] = []

    in_data_section = False

    with open(path, encoding="utf-8") as fh:
        for line_num, raw_line in enumerate(fh, start=1):
            line = raw_line.rstrip("\n").rstrip("\r")

            if _is_header_line(line):
                if not in_data_section:
                    header_lines.append(line)
                continue

            in_data_section = True
            tokens = line.split()
            if len(tokens) != NUM_COLUMNS:
                raise ValueError(
                    f"Line {line_num}: expected {NUM_COLUMNS} columns, "
                    f"got {len(tokens)}"
                )

            particle: dict = {}
            for (col_name, col_type), token in zip(COLUMN_SPEC, tokens, strict=True):
                try:
                    particle[col_name] = _parse_token(token, col_type)
                except (ValueError, TypeError) as exc:
                    raise ValueError(
                        f"{path}:{line_num}: column '{col_name}': "
                        f"cannot convert {token!r} to {col_type.__name__}"
                    ) from exc

            particles.append(particle)

    logger.debug("Parsed %d particles and %d header lines from %s",
                 len(particles), len(header_lines), path)
    return particles, header_lines


def write_star_file(
    path: Path,
    particles: list[dict],
    header_lines: list[str],
) -> None:
    """Write particles to a cisTEM-style 30-column star file.

    Writes header lines first (preserved from parsing), then one data row
    per particle with whitespace-delimited columns. The output roundtrips
    identically through parse_star_file: parsing the written file produces
    particle dicts equal to the input.

    Args:
        path: Output file path.
        particles: List of particle dicts with the 30 column-name keys.
        header_lines: Header lines to write before data rows.

    Raises:
        KeyError: If a particle dict is missing a required column key.
        ValueError: If any particle's ``original_image_filename`` contains
            spaces (the whitespace-delimited star format cannot represent
            filenames with embedded spaces).
    """
    path = Path(path)

    # Build output in memory first so a KeyError during formatting
    # does not leave a truncated (or empty) file on disk.
    lines: list[str] = []
    for header in header_lines:
        lines.append(header + "\n")

    for particle in particles:
        filename = particle["original_image_filename"]
        if " " in str(filename):
            raise ValueError(
                f"original_image_filename {filename!r} contains spaces; "
                "the whitespace-delimited star format does not support "
                "filenames with spaces"
            )
        tokens = [
            _format_value(particle[col_name], col_type)
            for col_name, col_type in COLUMN_SPEC
        ]
        lines.append(" ".join(tokens) + "\n")

    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


def group_particles_by_tilt(
    particles: list[dict],
) -> dict[str, list[dict]]:
    """Group particles by their original_image_filename field.

    Each group shares a tilt image (and thus a tilt angle, stored in
    column 30). This mirrors the MATLAB group_particles_by_tilt function
    at ctf/EMC_ctf_refine_from_star.m lines 786-803.

    Args:
        particles: List of particle dicts from parse_star_file.

    Returns:
        Dict mapping tilt image filename to the list of particles from
        that tilt. Insertion order matches first appearance in the input.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for particle in particles:
        tilt_name = particle["original_image_filename"]
        groups[tilt_name].append(particle)
    return dict(groups)
