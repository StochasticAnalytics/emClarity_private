"""Pydantic models for job tracking and subprocess management.

Each emClarity command execution is tracked as a Job with its own
process ID, log file, and status lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from backend.models.workflow import PipelineCommand


class JobStatus(str, Enum):
    """Lifecycle states for a running job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(BaseModel):
    """Represents a single command execution."""

    id: str = Field(..., description="Unique job identifier (UUID)")
    command: PipelineCommand = Field(..., description="The pipeline command being executed")
    status: JobStatus = Field(default=JobStatus.PENDING, description="Current job status")
    pid: int | None = Field(default=None, description="OS process ID (set when running)")
    start_time: datetime | None = Field(default=None, description="When the job started")
    end_time: datetime | None = Field(default=None, description="When the job finished")
    log_path: str | None = Field(default=None, description="Path to the job's log file")
    exit_code: int | None = Field(default=None, description="Process exit code (set when done)")
    project_path: str = Field(..., description="Project this job belongs to")
    error_message: str | None = Field(
        default=None,
        description="Error summary if the job failed",
    )


class JobListResponse(BaseModel):
    """Response model for listing jobs."""

    jobs: list[Job] = Field(default_factory=list)
    total: int = Field(default=0, description="Total number of jobs")
