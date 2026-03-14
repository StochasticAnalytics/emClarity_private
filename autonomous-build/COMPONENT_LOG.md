# Component & Tool Log

Tracks all tools, components, and infrastructure added to the project during baseline setup and autonomous builds.

## Baseline Setup (2026-03-13)

### Frontend (frontend/)

**Framework:** React 19 + TypeScript 5 + Vite 8

**Production Dependencies:**
| Package | Version | Purpose |
|---------|---------|---------|
| `react` | ^19 | UI framework |
| `react-dom` | ^19 | DOM rendering |
| `react-router-dom` | ^7 | Client-side routing |
| `@tanstack/react-query` | ^5 | Server state / data fetching |
| `@tanstack/react-table` | ^8 | Tilt-series and job tables |
| `react-hook-form` | ^7 | Form state management |
| `@hookform/resolvers` | ^3 | Zod integration for forms |
| `zod` | ^3 | Schema validation |
| `recharts` | ^2 | FSC curve plotting |
| `lucide-react` | latest | Icon library |
| `tailwindcss` | ^4 | CSS utility framework |
| `@tailwindcss/vite` | ^4 | Vite plugin for Tailwind |

**Dev Dependencies:**
| Package | Purpose |
|---------|---------|
| `vitest` | Unit test runner |
| `jsdom` | DOM environment for tests |
| `@testing-library/react` | Component testing |
| `@testing-library/jest-dom` | DOM assertions |
| `@testing-library/user-event` | User interaction simulation |
| `eslint` | Linting |

**Components Created:**
| Component | Path | Purpose |
|-----------|------|---------|
| `MainLayout` | `components/layout/MainLayout.tsx` | App shell (sidebar + header + content) |
| `Sidebar` | `components/layout/Sidebar.tsx` | Navigation sidebar with icons |
| `Header` | `components/layout/Header.tsx` | Top header bar |
| `LoadingSpinner` | `components/common/LoadingSpinner.tsx` | Loading indicator |
| `ErrorBoundary` | `components/common/ErrorBoundary.tsx` | Error boundary wrapper |
| `ProjectPage` | `features/project/ProjectPage.tsx` | Project manager (placeholder) |
| `ParametersPage` | `features/parameters/ParametersPage.tsx` | Parameter editor (placeholder) |
| `TiltSeriesPage` | `features/tilt-series/TiltSeriesPage.tsx` | Tilt-series table (placeholder) |
| `WorkflowPage` | `features/workflow/WorkflowPage.tsx` | Pipeline runner (placeholder) |
| `JobsPage` | `features/jobs/JobsPage.tsx` | Job monitor (placeholder) |
| `ResultsPage` | `features/results/ResultsPage.tsx` | Results viewer (placeholder) |
| `UtilitiesPage` | `features/utilities/UtilitiesPage.tsx` | Utility tools (placeholder) |

**Hooks:**
| Hook | Path | Purpose |
|------|------|---------|
| `useApiQuery` | `hooks/useApi.ts` | React Query wrapper for GET |
| `useApiMutation` | `hooks/useApi.ts` | React Query wrapper for POST/PUT/DELETE |

**Type Definitions:**
| File | Types Defined |
|------|---------------|
| `types/parameters.ts` | `ParameterDefinition`, `ParameterSet`, `ParameterGroup` |
| `types/workflow.ts` | `WorkflowStep`, `PipelineStep`, `PipelineState` |
| `types/project.ts` | `ProjectInfo`, `ProjectDirectories`, `CreateProjectRequest` |

**API Client:**
| File | Purpose |
|------|---------|
| `api/client.ts` | Fetch wrapper with typed GET/POST/PUT/PATCH/DELETE |
| `api/types.ts` | Shared API types (PaginatedResponse, JobSummary, etc.) |

**Validation:**
| File | Schemas |
|------|---------|
| `lib/validation.ts` | Zod schemas for project name, pixel size, paths, create-project form |

### Backend (backend/)

**Framework:** FastAPI + Pydantic v2

**Dependencies:**
| Package | Purpose |
|---------|---------|
| `fastapi>=0.100.0` | Web framework |
| `uvicorn[standard]>=0.23.0` | ASGI server |
| `pydantic>=2.0.0` | Data validation |
| `python-multipart` | File upload support |

**API Endpoints:**
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Health check |
| GET | `/api/parameters/schema` | Parameter schema |
| GET | `/api/parameters/file/{path}` | Load param file |
| POST | `/api/parameters/file` | Save param file |
| POST | `/api/parameters/validate` | Validate parameters |
| POST | `/api/projects` | Create project |
| GET | `/api/projects/{path}` | Get project state |
| GET | `/api/projects/{path}/tilt-series` | List tilt series |
| GET | `/api/workflow/commands` | List commands |
| POST | `/api/workflow/execute` | Execute command |
| GET | `/api/workflow/state/{path}` | Get workflow state |
| GET | `/api/jobs` | List jobs |
| GET | `/api/jobs/{id}` | Get job status |
| GET | `/api/jobs/{id}/log` | Stream job log |
| DELETE | `/api/jobs/{id}` | Cancel job |
| GET | `/api/system/gpus` | Detect GPUs |
| GET | `/api/system/info` | System information |

**Note:** Backend endpoints use `/api/` prefix. E2E tests expect `/api/v1/` prefix. The developer agent must migrate endpoints to `/api/v1/` to pass E2E tests (TASK-002 through TASK-006).

**Models:**
| Model | File | Purpose |
|-------|------|---------|
| `ParameterDefinition` | `models/parameter.py` | Parameter schema entry |
| `ParameterValue` | `models/parameter.py` | Name-value pair |
| `ParameterFile` | `models/parameter.py` | Parameter file contents |
| `ParameterValidationResult` | `models/parameter.py` | Validation result |
| `Project` | `models/project.py` | Project state |
| `TiltSeries` | `models/project.py` | Tilt series metadata |
| `ProjectState` | `models/project.py` | Pipeline state enum |
| `PipelineCommand` | `models/workflow.py` | Command enum |
| `CommandRequest` | `models/workflow.py` | Execute command request |
| `CommandInfo` | `models/workflow.py` | Command metadata |
| `WorkflowState` | `models/workflow.py` | Workflow state response |
| `Job` | `models/job.py` | Job lifecycle |
| `JobStatus` | `models/job.py` | Job status enum |

**Services:**
| Service | File | Purpose |
|---------|------|---------|
| `ParameterService` | `services/parameter_service.py` | Schema loading, validation, file I/O |
| `ProjectService` | `services/project_service.py` | Project CRUD, state detection |
| `WorkflowService` | `services/workflow_service.py` | Command building, state machine |
| `JobService` | `services/job_service.py` | Subprocess management |
| `SystemService` | `services/system_service.py` | GPU/CPU detection |

### E2E Tests (tests/)

**Test Framework:** pytest + httpx (async)

| Test File | Tests | Validates |
|-----------|-------|-----------|
| `test_parameter_schema.py` | 8 | Parameter schema API contract |
| `test_parameter_validation.py` | 7 | Parameter validation logic |
| `test_project_management.py` | 6 | Project CRUD operations |
| `test_workflow_state.py` | 5 | Pipeline state machine enforcement |
| `test_system_info.py` | 5 | System hardware detection |
| `test_job_management.py` | 4 | Job lifecycle management |
| **Total** | **35** | |

### Backend Unit Tests (backend/tests/)

| Test File | Tests | Validates |
|-----------|-------|-----------|
| `test_parameters.py` | 17 | Parameter models, service, endpoints |
| `test_projects.py` | 10 | Project models, service, endpoints |
| **Total** | **27** | |

---

## API Contract Alignment Notes

The E2E tests define the authoritative API contract. Key differences the developer agent must resolve:

1. **URL prefix**: Tests use `/api/v1/`, backend uses `/api/`
2. **Schema response format**: Tests expect `{"parameters": [...]}`, backend returns flat array
3. **Project creation**: Tests send `{name, directory, parameters}`, backend expects `{name, path}`
4. **Project response**: Tests expect `id` field, backend returns `name`+`path`
5. **Workflow endpoints**: Tests expect project-scoped routes (`/workflow/{project_id}/...`)
6. **Job model**: Tests expect `project_id`, `created_at`, `updated_at` fields
7. **Deprecated params**: Tests expect `flgCCCcutoff` accepted as alias for `ccc_cutoff`

---

## Orchestrator Updates (2026-03-14)

### Streaming Fix
- Switched `--stream` mode to use `--output-format stream-json --verbose`
- Reads stdout line-by-line (NDJSON events) instead of empty stderr
- Background thread drains stderr to prevent pipe deadlock
- Displays `[TOOL]`, `[TEXT]`, `[INIT]`, `[DONE]` events to console in real time

### Logging Enhancements
- Per-stage timing with token counts
- Full QA output captured at INFO level
- Task lifecycle summaries: `╰── TASK-002 COMPLETE (485s total)`
- End-of-run report with per-status breakdown

### QA Verdict Parser
- Tries 3 patterns: exact markdown, plain text, heading
- Unparseable output tagged and deferred to oracle (not blocked)
- QA prompt updated to require plain-text verdict format
- QA timeout increased 300s → 600s

### New: claude-launcher.sh
- Launches claude with orchestrator-compatible flags
- Auto-injects `memories/MEMORY.md` via `--append-system-prompt`
- Use for interactive sessions that need project context

### New: Memory Files
| File | Purpose |
|------|---------|
| `memories/claude_cli_patterns.md` | CLI flags, output formats, subprocess patterns |
| `memories/orchestrator_tuning.md` | Config, retry, streaming lessons |
| `memories/phase_0_notes.md` | Agent observations, QA self-correction |
