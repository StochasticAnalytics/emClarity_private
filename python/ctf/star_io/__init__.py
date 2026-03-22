"""
Star file I/O for cisTEM-style 30-column star files.

Provides parsing, writing, and grouping of particle records used by
emClarity's CTF refinement pipeline.
"""

from .emc_star_parser import (
    COLUMN_SPEC,
    group_particles_by_tilt,
    parse_star_file,
    write_star_file,
)

__all__ = [
    "COLUMN_SPEC",
    "group_particles_by_tilt",
    "parse_star_file",
    "write_star_file",
]
