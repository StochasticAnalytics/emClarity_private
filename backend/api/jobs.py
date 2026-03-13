"""API endpoints for job monitoring and management.

Routes:
    GET    /api/jobs           - List all jobs
    GET    /api/jobs/{id}      - Get a specific job's status
    GET    /api/jobs/{id}/log  - Stream or fetch job log output
    DELETE /api/jobs/{id}      - Cancel a running job
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.models.job import Job, JobListResponse, JobStatus
from backend.services.job_service import JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# Shared job service instance (must match the one used in workflow.py)
# In a production setup, this would be injected via dependency injection.
# For this scaffold, we import the same module-level instance.
from backend.api.workflow import _job_service


@router.get("", response_model=JobListResponse)
async def list_jobs(status: JobStatus | None = None) -> JobListResponse:
    """List all tracked jobs, optionally filtered by status.

    Query parameters:
        status: Filter by job status (pending, running, completed, failed, cancelled)
    """
    jobs = _job_service.list_jobs(status=status)
    return JobListResponse(jobs=jobs, total=len(jobs))


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str) -> Job:
    """Get the current status of a specific job."""
    job = _job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


@router.get("/{job_id}/log")
async def get_job_log(job_id: str, stream: bool = False, tail: int = 100):
    """Fetch or stream a job's log output.

    Query parameters:
        stream: If true, return a Server-Sent Events stream
        tail: Number of lines to return (non-streaming mode, default 100)
    """
    job = _job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if stream:
        # Server-Sent Events stream
        async def event_stream():
            async for chunk in _job_service.stream_log(job_id):
                # SSE format: each message is "data: ...\n\n"
                for line in chunk.splitlines():
                    yield f"data: {line}\n\n"
            yield "event: done\ndata: stream ended\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    # Non-streaming: return last N lines
    log_content = _job_service.read_log(job_id, tail=tail)
    return {"job_id": job_id, "log": log_content}


@router.delete("/{job_id}", response_model=Job)
async def cancel_job(job_id: str) -> Job:
    """Cancel a running job by sending SIGTERM to its process."""
    job = _job_service.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job
