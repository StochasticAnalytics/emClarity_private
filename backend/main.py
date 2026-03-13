"""FastAPI application entry point for the emClarity backend.

Start the server with:
    uvicorn backend.main:app --reload --port 8000

The backend serves the React GUI (expected at localhost:5173 during
development) and provides REST endpoints for parameter management,
project handling, workflow execution, and system info.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.router import router

app = FastAPI(
    title="emClarity Backend",
    description="REST API for the emClarity cryo-EM processing pipeline",
    version="0.1.0",
)

# CORS configuration: allow the React dev server and common local origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Fallback React dev server
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/api/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "emClarity backend"}
