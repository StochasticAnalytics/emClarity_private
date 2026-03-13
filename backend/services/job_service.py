"""Service for managing emClarity subprocess execution and monitoring.

Each command execution is tracked as a Job with a unique ID, subprocess
PID, and log file. Jobs can be listed, inspected, and cancelled.
"""

from __future__ import annotations

import signal
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from backend.models.job import Job, JobStatus
from backend.models.workflow import PipelineCommand


class JobService:
    """Manages emClarity subprocesses."""

    def __init__(self) -> None:
        # In-memory job registry (keyed by job ID)
        self._jobs: dict[str, Job] = {}
        # Active subprocess handles (keyed by job ID)
        self._processes: dict[str, subprocess.Popen[bytes]] = {}

    def start_job(
        self,
        command: PipelineCommand,
        cli_args: list[str],
        project_path: str,
        log_dir: str | None = None,
    ) -> Job:
        """Launch a command as a background subprocess.

        Args:
            command: The pipeline command being run.
            cli_args: Full CLI argument list (e.g., ["emClarity", "init", ...]).
            project_path: Project directory (used as cwd).
            log_dir: Directory for log files. Defaults to project_path/logFile/.
        """
        job_id = str(uuid.uuid4())

        if log_dir is None:
            log_dir = str(Path(project_path) / "logFile")
        Path(log_dir).mkdir(parents=True, exist_ok=True)

        log_path = str(Path(log_dir) / f"{command.value}_{job_id[:8]}.log")

        job = Job(
            id=job_id,
            command=command,
            status=JobStatus.PENDING,
            log_path=log_path,
            project_path=project_path,
        )

        try:
            log_fh = open(log_path, "wb")  # noqa: SIM115
            proc = subprocess.Popen(
                cli_args,
                cwd=project_path,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
            job.status = JobStatus.RUNNING
            job.pid = proc.pid
            job.start_time = datetime.now(tz=timezone.utc)

            self._processes[job_id] = proc
        except FileNotFoundError as exc:
            job.status = JobStatus.FAILED
            job.error_message = f"Command not found: {exc}"
        except OSError as exc:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)

        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Job | None:
        """Return a job by ID, refreshing its status if still running."""
        job = self._jobs.get(job_id)
        if job is not None:
            self._refresh_status(job)
        return job

    def list_jobs(
        self, status: JobStatus | None = None
    ) -> list[Job]:
        """List all tracked jobs, optionally filtered by status."""
        for job in self._jobs.values():
            self._refresh_status(job)

        jobs = list(self._jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]

        return sorted(jobs, key=lambda j: j.start_time or datetime.min, reverse=True)

    def cancel_job(self, job_id: str) -> Job | None:
        """Send SIGTERM to a running job's process."""
        job = self._jobs.get(job_id)
        if job is None:
            return None

        proc = self._processes.get(job_id)
        if proc is not None and proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            job.status = JobStatus.CANCELLED
            job.end_time = datetime.now(tz=timezone.utc)

        return job

    def read_log(self, job_id: str, tail: int = 100) -> str:
        """Read the last N lines of a job's log file."""
        job = self._jobs.get(job_id)
        if job is None or job.log_path is None:
            return ""

        log_path = Path(job.log_path)
        if not log_path.exists():
            return ""

        lines = log_path.read_text(errors="replace").splitlines()
        return "\n".join(lines[-tail:])

    async def stream_log(
        self, job_id: str, poll_interval: float = 0.5
    ) -> AsyncIterator[str]:
        """Yield new log lines as they are written (for SSE streaming).

        This is a simple tail-follow implementation suitable for the
        /jobs/{id}/log streaming endpoint.
        """
        import asyncio

        job = self._jobs.get(job_id)
        if job is None or job.log_path is None:
            return

        log_path = Path(job.log_path)
        last_pos = 0

        while True:
            if log_path.exists():
                with open(log_path, "r", errors="replace") as fh:
                    fh.seek(last_pos)
                    new_data = fh.read()
                    last_pos = fh.tell()

                if new_data:
                    yield new_data

            # Stop streaming if the job is no longer running
            self._refresh_status(job)
            if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
                # One final read to catch any remaining output
                if log_path.exists():
                    with open(log_path, "r", errors="replace") as fh:
                        fh.seek(last_pos)
                        final = fh.read()
                    if final:
                        yield final
                break

            await asyncio.sleep(poll_interval)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_status(self, job: Job) -> None:
        """Update job status from the subprocess return code."""
        if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            return

        proc = self._processes.get(job.id)
        if proc is None:
            return

        rc = proc.poll()
        if rc is None:
            return  # Still running

        job.exit_code = rc
        job.end_time = datetime.now(tz=timezone.utc)

        if rc == 0:
            job.status = JobStatus.COMPLETED
        else:
            job.status = JobStatus.FAILED
            job.error_message = f"Process exited with code {rc}"
