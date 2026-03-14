# emClarity GUI Testing Guide

**Phase 0 Status**: All 16 tasks complete | 35 E2E tests passing | 27 backend unit tests passing

---

## Quick Start

You need **two terminals** — one for the backend, one for the frontend.

### Terminal 1: Backend (FastAPI)

```bash
cd /workspaces/cisTEMx
pip install -r backend/requirements.txt        # first time only
python -m uvicorn backend.main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/api/health` should return `{"status":"ok","service":"emClarity backend"}`

### Terminal 2: Frontend (React + Vite)

```bash
cd /workspaces/cisTEMx/frontend
npm install                                     # first time only
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## What to Test: Page-by-Page Walkthrough

### 1. Project Page (`/`)

The landing page. Create and manage emClarity projects.

| What to check | Expected behavior |
|---|---|
| "New Project" form renders | Name field, directory picker, create button |
| Create a project | Fill in name + directory path, submit → project appears in list |
| Project state badge | Shows `UNINITIALIZED` for new projects |
| Select a project | Clicking a project sets it as the active project (shown in header) |

**API calls to watch**: `POST /api/v1/projects`, `GET /api/v1/projects/{id}`

### 2. Parameters Page (`/parameters`)

Edit the 160+ emClarity processing parameters.

| What to check | Expected behavior |
|---|---|
| Tabs render by category | Microscope, Hardware, CTF, Alignment, Classification, etc. |
| Parameter form fields | Each param shows name, input control, default value, description |
| Type-appropriate inputs | Numeric params get number inputs, booleans get toggles, strings get text |
| Validation feedback | Out-of-range values show error messages |
| Required params marked | Required parameters visually distinguished |

**API calls to watch**: `GET /api/v1/parameters/schema`, `POST /api/v1/parameters/validate`

### 3. Tilt-Series Page (`/tilt-series`)

Sortable/filterable data table for managing tilt-series.

| What to check | Expected behavior |
|---|---|
| Table renders | Columns for name, status, defocus, tilt range, etc. |
| Column sorting | Click headers to sort ascending/descending |
| Column filtering | Filter controls narrow displayed rows |
| Status badges | Color-coded status indicators per tilt-series |

**API calls to watch**: `GET /api/v1/projects/{id}/tilt-series`

### 4. Workflow Page (`/workflow`)

Visual pipeline stepper showing the emClarity processing pipeline.

| What to check | Expected behavior |
|---|---|
| State machine visualization | Shows pipeline stages as a stepper/flowchart |
| Current state highlighted | Active state visually distinct |
| Available commands | Only valid next commands are enabled |
| Disabled commands | Out-of-order commands are grayed out |
| Run command | Clicking an available command submits a job |

**Pipeline stages** (in order):
```
UNINITIALIZED → TILT_ALIGNED → CTF_ESTIMATED → RECONSTRUCTED →
PARTICLES_PICKED → INITIALIZED → CYCLE_0_AVG → CYCLE_N_ALIGNED →
CYCLE_N_AVG → PROCESSING → EXPORT → DONE
```

**API calls to watch**: `GET /api/v1/workflow/state-machine`, `GET /api/v1/workflow/{project_id}/available-commands`, `POST /api/v1/workflow/{project_id}/run`

### 5. Jobs Page (`/jobs`)

Monitor running and completed jobs.

| What to check | Expected behavior |
|---|---|
| Job list renders | Shows all jobs with status badges |
| Status badges | PENDING (gray), RUNNING (blue), COMPLETED (green), FAILED (red), CANCELLED (yellow) |
| Job details | Click a job to see command, timestamps, log output |
| Log viewer | Displays job log content |
| Cancel button | Running jobs show a cancel button |
| Sort order | Newest jobs appear first |

**API calls to watch**: `GET /api/v1/jobs`, `GET /api/v1/jobs/{id}`, `GET /api/v1/jobs/{id}/log`, `DELETE /api/v1/jobs/{id}`

### 6. Results Page (`/results`)

View reconstruction quality metrics.

| What to check | Expected behavior |
|---|---|
| FSC curves | Fourier Shell Correlation plot renders (recharts) |
| 0.143 threshold line | Resolution threshold displayed on FSC plot |
| Particle statistics | Particle count, distribution info |
| System info panel | CPU cores, RAM, GPU info displayed |

### 7. Utilities Page (`/utilities`)

System diagnostics and helper operations.

| What to check | Expected behavior |
|---|---|
| System check | Runs `emClarity check` and displays output |
| Mask creator | Form for mask creation parameters |
| Volume rescaler | Input for target pixel size |
| Geometry operations | Dropdown with operations: RemoveClasses, RemoveFraction, RemoveLowScoringParticles, RestoreParticles, PrintGeometry |

**API calls to watch**: `POST /api/v1/utilities/check`, `POST /api/v1/utilities/mask`, `POST /api/v1/utilities/rescale`, `POST /api/v1/utilities/geometry`

### 8. Layout & Navigation (all pages)

| What to check | Expected behavior |
|---|---|
| Sidebar navigation | Links to all 7 pages, highlights active page |
| Header | Shows active project name and state badge |
| Responsive layout | Sidebar collapses on narrow screens |
| Settings panel | Accessible from header or sidebar |
| Error boundary | Broken components show error UI, not white screen |
| Loading states | Spinners shown while API calls are in flight |

---

## Running Automated Tests

### E2E Tests (require backend running on port 8000)

```bash
cd /workspaces/cisTEMx

# Run all 35 tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_parameter_schema.py -v
python -m pytest tests/test_parameter_validation.py -v
python -m pytest tests/test_project_management.py -v
python -m pytest tests/test_workflow_state.py -v
python -m pytest tests/test_system_info.py -v
python -m pytest tests/test_job_management.py -v
```

### Backend Unit Tests (no server needed)

```bash
cd /workspaces/cisTEMx

# Run all 27 tests
python -m pytest backend/tests/ -v

# With coverage
python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

### Frontend Tests

```bash
cd /workspaces/cisTEMx/frontend

# Run once
npm run test

# Watch mode (re-runs on file change)
npm run test:watch

# TypeScript compilation check
npm run typecheck

# Lint
npm run lint
```

---

## API Quick Reference

Base URL: `http://localhost:8000`

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Health check |
| `/api/v1/parameters/schema` | GET | All 160 parameter definitions |
| `/api/v1/parameters/validate` | POST | Validate parameter values |
| `/api/v1/parameters/file/{path}` | GET | Parse a MATLAB param.m file |
| `/api/v1/parameters/file` | POST | Write a MATLAB param.m file |
| `/api/v1/projects` | POST | Create new project |
| `/api/v1/projects/{id}` | GET | Get project details |
| `/api/v1/projects/{id}` | DELETE | Delete project |
| `/api/v1/projects/{id}/tilt-series` | GET | List tilt-series for project |
| `/api/v1/workflow/state-machine` | GET | Full state machine definition |
| `/api/v1/workflow/{project_id}/available-commands` | GET | Commands available in current state |
| `/api/v1/workflow/{project_id}/run` | POST | Execute a pipeline command |
| `/api/v1/jobs` | GET | List all jobs |
| `/api/v1/jobs/{id}` | GET | Job status and details |
| `/api/v1/jobs/{id}/log` | GET | Job log output |
| `/api/v1/jobs/{id}` | DELETE | Cancel a running job |
| `/api/system/info` | GET | CPU, RAM, GPU info |
| `/api/v1/utilities/check` | POST | Run emClarity system check |
| `/api/v1/utilities/mask` | POST | Create mask |
| `/api/v1/utilities/rescale` | POST | Rescale volume |
| `/api/v1/utilities/geometry` | POST | Geometry operations |

FastAPI auto-docs available at: **http://localhost:8000/docs** (Swagger UI) and **http://localhost:8000/redoc**

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Frontend shows network errors | Confirm backend is running on port 8000 |
| CORS errors in browser console | Backend CORS is configured for `localhost:5173` — make sure frontend is on that port |
| `npm install` fails | Delete `frontend/node_modules` and `frontend/package-lock.json`, retry |
| `pip install` fails | Try `pip install --upgrade pip` first, then retry |
| E2E tests fail with connection refused | Start the backend server before running E2E tests |
| TypeScript errors | Run `npm run typecheck` to see specific errors |
| Blank page in browser | Check browser console (F12) for JavaScript errors |
| Port 8000 already in use | `lsof -i :8000` to find the process, or use `--port 8001` |
| Port 5173 already in use | Vite will auto-increment to 5174; update CORS in `backend/main.py` if needed |

---

## Tech Stack Summary

| Layer | Technology | Version |
|---|---|---|
| Frontend framework | React | 19 |
| Language | TypeScript | 5.9 |
| Build tool | Vite | 8 |
| Styling | Tailwind CSS | 4 |
| Routing | React Router DOM | 7 |
| Server state | TanStack React Query | 5 |
| Data tables | TanStack React Table | 8 |
| Forms | React Hook Form + Zod | 7 / 4 |
| Charts | Recharts | 3 |
| Icons | Lucide React | latest |
| Backend framework | FastAPI | 0.100+ |
| Data validation | Pydantic | 2.0+ |
| ASGI server | Uvicorn | 0.23+ |
| Frontend tests | Vitest + Testing Library | 4 / 16 |
| Backend tests | pytest | latest |
