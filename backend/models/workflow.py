"""Pydantic models for emClarity workflow and pipeline commands.

Each processing step in the emClarity pipeline maps to a command that
can be executed with specific parameters. This module defines the
command vocabulary and request/response models.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PipelineCommand(str, Enum):
    """Available emClarity processing commands.

    These map to the subcommands accepted by the `emClarity` entry point.
    The ordering here reflects the typical processing sequence.
    """

    AUTO_ALIGN = "autoAlign"
    CTF_ESTIMATE = "ctf estimate"
    CTF_3D = "ctf 3d"
    TEMPLATE_SEARCH = "templateSearch"
    INIT = "init"
    AVG = "avg"
    ALIGN_RAW = "alignRaw"
    TOMO_CPR = "tomoCPR"
    PCA = "pca"
    CLUSTER = "cluster"
    FSC = "fsc"
    RECONSTRUCT = "reconstruct"


# Defines which commands are available at each pipeline stage and their
# required predecessor commands.
COMMAND_PREREQUISITES: dict[PipelineCommand, list[PipelineCommand]] = {
    PipelineCommand.AUTO_ALIGN: [],
    PipelineCommand.CTF_ESTIMATE: [PipelineCommand.AUTO_ALIGN],
    PipelineCommand.CTF_3D: [PipelineCommand.CTF_ESTIMATE],
    PipelineCommand.TEMPLATE_SEARCH: [PipelineCommand.CTF_3D],
    PipelineCommand.INIT: [PipelineCommand.TEMPLATE_SEARCH],
    PipelineCommand.AVG: [PipelineCommand.INIT],
    PipelineCommand.ALIGN_RAW: [PipelineCommand.AVG],
    PipelineCommand.TOMO_CPR: [PipelineCommand.ALIGN_RAW],
    PipelineCommand.PCA: [PipelineCommand.AVG],
    PipelineCommand.CLUSTER: [PipelineCommand.PCA],
    PipelineCommand.FSC: [PipelineCommand.AVG],
    PipelineCommand.RECONSTRUCT: [PipelineCommand.AVG],
}


class CommandInfo(BaseModel):
    """Describes a pipeline command for the frontend."""

    command: PipelineCommand
    label: str = Field(..., description="Human-readable command name")
    description: str = Field(default="", description="What this command does")
    prerequisites: list[PipelineCommand] = Field(
        default_factory=list,
        description="Commands that must complete before this one",
    )


class CommandRequest(BaseModel):
    """Request to execute a pipeline command."""

    command: PipelineCommand = Field(..., description="The command to execute")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameter overrides for this command",
    )
    tilt_series_name: str | None = Field(
        default=None,
        description="Specific tilt series to process (None = all)",
    )
    cycle: int = Field(
        default=0,
        description="Refinement cycle number",
    )
    gpu_ids: list[int] | None = Field(
        default=None,
        description="GPU device IDs to use (None = auto-detect)",
    )


class WorkflowState(BaseModel):
    """Current state of the processing pipeline for a project."""

    completed_commands: list[PipelineCommand] = Field(
        default_factory=list,
        description="Commands that have completed successfully",
    )
    available_commands: list[PipelineCommand] = Field(
        default_factory=list,
        description="Commands that can be run given the current state",
    )
    current_cycle: int = Field(default=0, description="Current refinement cycle")
