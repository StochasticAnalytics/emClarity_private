"""Pydantic models for emClarity project state management.

An emClarity project progresses through a series of well-defined states
as tilt-series data is processed from raw micrographs to final 3D
reconstructions.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ProjectState(str, Enum):
    """Processing states an emClarity project passes through.

    The pipeline is sequential: each state requires all prior states
    to have been completed successfully.
    """

    UNINITIALIZED = "uninitialized"
    TILT_ALIGNED = "tilt_aligned"
    CTF_ESTIMATED = "ctf_estimated"
    RECONSTRUCTED = "reconstructed"
    PARTICLES_PICKED = "particles_picked"
    INITIALIZED = "initialized"
    CYCLE_N = "cycle_n"
    EXPORT = "export"
    DONE = "done"


class TiltSeries(BaseModel):
    """Metadata for a single tilt series within a project."""

    name: str = Field(..., description="Tilt series identifier (e.g., 'tilt1')")
    stack_path: str | None = Field(
        default=None,
        description="Path to the raw tilt-series stack (.st file)",
    )
    rawtlt_path: str | None = Field(
        default=None,
        description="Path to the raw tilt angles file (.rawtlt)",
    )
    aligned: bool = Field(default=False, description="Whether tilt-series alignment is complete")
    ctf_estimated: bool = Field(default=False, description="Whether CTF has been estimated")


class Project(BaseModel):
    """Top-level representation of an emClarity project.

    Tracks the overall processing state and the collection of tilt
    series being processed.
    """

    name: str = Field(..., description="Project name")
    path: str = Field(..., description="Absolute path to the project directory")
    state: ProjectState = Field(
        default=ProjectState.UNINITIALIZED,
        description="Current pipeline state",
    )
    current_cycle: int = Field(
        default=0,
        description="Current refinement cycle number (0 = not yet cycling)",
    )
    tilt_series: list[TiltSeries] = Field(
        default_factory=list,
        description="Tilt series in this project",
    )
    parameter_file: str | None = Field(
        default=None,
        description="Path to the active parameter file",
    )
