"""Typed Pydantic models for per-project settings."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunProfile(BaseModel):
    """A single run profile configuration."""
    name: str
    gpu_count: int = 1
    cpu_cores: int = 4
    scratch_disk: str | None = None
    command_template: str | None = None


class ProjectSettings(BaseModel):
    """Per-project settings stored in the project registry."""
    run_profiles: list[RunProfile] = Field(default_factory=list)
    selected_run_profile: str | None = None
    system_params: dict[str, Any] | None = None
    viewer_path: str | None = None
    executable_paths: dict[str, str] = Field(default_factory=dict)
