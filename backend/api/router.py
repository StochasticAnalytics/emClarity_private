"""Main API router that aggregates all endpoint modules.

Import this router in main.py and include it on the FastAPI app.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api import jobs, parameters, projects, system, workflow
from backend.api import v1_projects, v1_workflow, v1_system, v1_jobs

router = APIRouter()

router.include_router(parameters.router)
router.include_router(parameters.v1_router)
router.include_router(projects.router)
router.include_router(v1_projects.router)
router.include_router(workflow.router)
# v1_workflow must come AFTER v1_projects so the shared _projects dict is
# populated before any route handlers run.
router.include_router(v1_workflow.router)
router.include_router(jobs.router)
router.include_router(system.router)
# V1 system and jobs endpoints
router.include_router(v1_system.router)
# v1_jobs/schema must be registered before v1_jobs/{job_id} to avoid
# "schema" being interpreted as a job ID.
router.include_router(v1_jobs.router)
