"""V1 API endpoints for job tracking and management.

Routes:
    GET /api/v1/jobs           - List jobs, optionally filtered by project_id
    GET /api/v1/jobs/schema    - Return the Job schema definition
    GET /api/v1/jobs/{id}      - Get a specific job's status (404 if not found)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs-v1"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class JobStatus(str, Enum):
    """Lifecycle states for a tracked job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Job(BaseModel):
    """Represents a single emClarity command execution."""

    id: str = Field(..., description="Unique job identifier (UUID)")
    project_id: str = Field(..., description="Project this job belongs to")
    command: str = Field(..., description="The emClarity command (e.g. 'autoAlign')")
    status: JobStatus = Field(
        default=JobStatus.PENDING,
        description="Current job status",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        description="When the job was created (ISO-8601)",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        description="When the job was last updated (ISO-8601)",
    )
    pid: int | None = Field(default=None, description="OS process ID")
    exit_code: int | None = Field(default=None, description="Process exit code")
    error_message: str | None = Field(default=None, description="Error summary if failed")
    log_path: str | None = Field(default=None, description="Path to the job's log file")


# ---------------------------------------------------------------------------
# In-memory job registry (keyed by job ID)
# ---------------------------------------------------------------------------

_jobs: dict[str, Job] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/schema", response_model=dict[str, Any])
async def get_job_schema() -> dict[str, Any]:
    """Return the Job model schema definition.

    Provides field descriptions and status enum values for client validation.
    """
    schema = Job.model_json_schema()
    return schema


@router.get("", response_model=list[Job])
async def list_jobs(project_id: str | None = None) -> list[Job]:
    """List all tracked jobs, optionally filtered by project_id.

    Query parameters:
        project_id: Filter jobs to a specific project (optional)
    """
    jobs = list(_jobs.values())
    if project_id is not None:
        jobs = [j for j in jobs if j.project_id == project_id]
    return sorted(jobs, key=lambda j: j.created_at, reverse=True)


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str) -> Job:
    """Get the current status of a specific job.

    Returns 404 if the job does not exist.
    """
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job
