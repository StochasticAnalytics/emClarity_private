"""Main API router that aggregates all endpoint modules.

Import this router in main.py and include it on the FastAPI app.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api import jobs, parameters, projects, system, workflow

router = APIRouter()

router.include_router(parameters.router)
router.include_router(parameters.v1_router)
router.include_router(projects.router)
router.include_router(workflow.router)
router.include_router(jobs.router)
router.include_router(system.router)
