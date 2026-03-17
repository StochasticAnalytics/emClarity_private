"""FastAPI application entry point for the emClarity backend.

Start the server with:
    uvicorn backend.main:app --reload --port 8000

The backend serves both the REST API and the production React frontend
(built to frontend/dist/).  All /api/* requests are handled by the API
router; everything else falls through to the SPA's index.html.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.api.router import router

app = FastAPI(
    title="emClarity Backend",
    description="REST API for the emClarity cryo-EM processing pipeline",
    version="0.1.0",
)

# CORS — only needed when the frontend is served from a separate origin
# (e.g. a Vite dev server during active frontend development).  In the
# normal production workflow the frontend is served from the same origin
# so CORS is not involved.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server (default port)
        "http://127.0.0.1:5173",
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


# ---------------------------------------------------------------------------
# Serve the production React build (frontend/dist/)
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIR.is_dir():
    # Serve static assets (JS, CSS, images) at /assets/...
    _assets_dir = _FRONTEND_DIR / "assets"
    if _assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_assets_dir)),
            name="frontend-assets",
        )

    @app.get("/{path:path}", response_model=None)
    async def spa_fallback(request: Request, path: str):
        """Serve static files from the frontend build, falling back to
        index.html for client-side routes (SPA behaviour)."""
        # Try to serve the exact file (favicon.svg, etc.)
        file_path = _FRONTEND_DIR / path
        if path and file_path.is_file():
            return FileResponse(file_path)
        # Everything else → index.html (React Router handles the route)
        index = _FRONTEND_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse("Frontend not built. Run: cd frontend && npm run build", status_code=503)
