# Component Log — emClarity Frontend

This document tracks all UI components created or substantially modified during Phase 0.1
(TASK-017 through TASK-024) of the cisTEMx frontend build.

---

## Phase 0.0 — Application Skeleton (TASK-001 – TASK-016)

Established the core application shell:

| Component | File | Role |
|-----------|------|------|
| `MainLayout` | `src/components/layout/MainLayout.tsx` | Root shell: sidebar + header + `<Outlet>` |
| `ProjectLayout` | `src/components/layout/ProjectLayout.tsx` | Fetches project by URL param; provides `<Outlet>` |
| `Header` | `src/components/layout/Header.tsx` | Top bar: app subtitle, project name, state badge |
| `Sidebar` | `src/components/layout/Sidebar.tsx` | Left nav rail: 7 section items |
| `SystemInfoPanel` | `src/components/layout/SystemInfoPanel.tsx` | Slide-in GPU/CPU/disk info panel |
| `LoadingSpinner` | `src/components/common/LoadingSpinner.tsx` | Animated spinner |
| `ErrorBoundary` | `src/components/common/ErrorBoundary.tsx` | React error boundary |
| `ProjectProvider` | `src/context/ProjectContext.tsx` | Context provider for active project |
| `ProjectPage` | `src/features/project/ProjectPage.tsx` | Landing: create / load / recent projects |
| `OverviewPage` | `src/features/overview/OverviewPage.tsx` | Dashboard skeleton |
| `ActionsPage` | `src/features/actions/ActionsPage.tsx` | Command panel skeleton |
| `AssetsPage` | `src/features/assets/AssetsPage.tsx` | Asset viewer skeleton |
| `ResultsPage` | `src/features/results/ResultsPage.tsx` | Results viewer skeleton |
| `WorkflowPage` | `src/features/workflow/WorkflowPage.tsx` | Workflow state machine skeleton |
| `SettingsPage` | `src/features/settings/SettingsPage.tsx` | Run profiles skeleton |
| `JobsPage` | `src/features/jobs/JobsPage.tsx` | Job monitor skeleton |
| `ExpertPage` | `src/features/expert/ExpertPage.tsx` | Expert parameters skeleton |

---

## Phase 0.1 — Tutorial-Driven UI Restructuring (TASK-017 – TASK-024)

### TASK-017 — OverviewPage: Pipeline Stepper + Stats

**Modified:** `src/features/overview/OverviewPage.tsx`

| Sub-component | Description |
|---------------|-------------|
| `StatCard` | Summary tile: label / value / optional sub-label with accent colouring |
| `PipelineProgressStepper` | 11-step horizontal stepper matching tutorial Figure 1; completed (green check), active (blue ring), upcoming (grey) |
| `RecentJobsSection` | Last 5 jobs table with status badges; links to Actions + Jobs pages |

Key decisions:
- `stateIndex()` maps workflow state string to numeric order for comparison
- `getActiveCycleStepId()` inspects job history to determine which iterative step is current during `CYCLE_N`
- `commandToStepId()` maps CLI command strings to step IDs exhaustively (throws on unknown command)
- Horizontal scroll wrapper allows stepper to overflow on narrow viewports without clipping

---

### TASK-018 — ActionsPage: 11 Parameter Tabs

**Modified:** `src/features/actions/ActionsPage.tsx`
**Modified:** `src/data/parameterRegistry.ts`

| Sub-component | Description |
|---------------|-------------|
| `ParameterAccordion` | Collapsible section grouping parameters by sub-category |
| `ParameterInput` | Form field: text / number / boolean / select rendering per parameter type |
| `HelpPanel` | Right panel showing objectives + command signature for the selected tab |
| `RunBar` | Bottom bar: run profile dropdown + Start Command button |

Tab IDs (matching tutorial sections 5–15):
`autoAlign` · `ctfEstimate` · `selectSubregions` · `templateSearch` · `init` ·
`ctf3d` · `avg` · `alignRaw` · `tomoCPR` · `classification` · `finalRecon`

Each tab shows: required params (starred in tutorial) → optional params (toggle) → expert link.

---

### TASK-019 — AssetsPage: 6 Asset Tabs

**Modified:** `src/features/assets/AssetsPage.tsx`

| Sub-component | Description |
|---------------|-------------|
| `AssetTable` | Sortable, filterable table via `@tanstack/react-table` |
| `AssetToolbar` | Import / Remove / Display batch action buttons |
| `AssetGroupHeader` | Section header with count badge |

Tab IDs: `tiltSeries` · `ctfData` · `tomograms` · `particlePositions` · `referenceVolumes` · `fscCurves`

Each tab uses identical table layout with per-tab column definitions.

---

### TASK-020 — ResultsPage: 6 Result Tabs

**Modified:** `src/features/results/ResultsPage.tsx`

| Sub-component | Description |
|---------------|-------------|
| `ResultsListPanel` | Left column: scrollable list of result items |
| `ResultsViewerPanel` | Centre: chart or image viewer for selected result |
| `ResultsNavBar` | Right/top: page through results with prev/next arrows |
| `FscCurveChart` | Recharts `LineChart` of FSC vs spatial frequency |
| `ClassDistributionChart` | Recharts `BarChart` of particle class counts |

Tab IDs: `alignmentQuality` · `ctfDiagnostics` · `particlePicks` · `fscCurves` · `averages` · `particleStats`

---

### TASK-021 — WorkflowPage: State Machine Visualiser

**Modified:** `src/features/workflow/WorkflowPage.tsx`

| Sub-component | Description |
|---------------|-------------|
| `StateNode` | Rounded card for one workflow state with commands list |
| `CommandButton` | Run-command button with tooltip showing description |
| `TransitionArrow` | SVG connector between state nodes |

9 ordered states: `UNINITIALIZED` → `TILT_ALIGNED` → `CTF_ESTIMATED` → `RECONSTRUCTED` →
`PARTICLES_PICKED` → `INITIALIZED` → `CYCLE_N` → `EXPORT` → `DONE`

---

### TASK-022 — SettingsPage: Run Profiles

**Modified:** `src/features/settings/SettingsPage.tsx`

| Sub-component | Description |
|---------------|-------------|
| `SystemParamsBanner` | Read-only GPU / CPU / scratch disk display |
| `ProfileList` | List of saved run profiles with Create / Delete |
| `ProfileDetailForm` | React-hook-form form for editing a selected profile |

State persistence via `localStorage` through `useRunProfiles` hook.

---

### TASK-023 — JobsPage: Job Monitor

**Modified:** `src/features/jobs/JobsPage.tsx`

| Sub-component | Description |
|---------------|-------------|
| `JobsTable` | Auto-refreshing table (5 s interval) via `@tanstack/react-table` |
| `StatusBadge` | Colour-coded badge: PENDING / RUNNING / COMPLETED / FAILED / CANCELLED |
| `LogDrawer` | Side panel showing raw log output for selected job |
| `CancelButton` | Sends DELETE to `/api/v1/jobs/{id}` for RUNNING jobs |

---

### TASK-024 — App Shell Polish + Integration Verification

**Modified:** `src/components/layout/Header.tsx`
**Modified:** `src/components/layout/Sidebar.tsx`
**Modified:** `src/components/layout/ProjectLayout.tsx`
**Modified:** `src/context/ProjectContext.tsx`

#### Header changes
- Added **Cycle badge** alongside the state badge when `current_cycle > 0`
  (indigo pill: "Cycle N" — pulled from `ActiveProject.current_cycle`)
- `ActiveProject` interface extended with optional `current_cycle?: number`
- `ProjectLayout` now propagates `current_cycle` from the API response

#### Sidebar changes
- Added **collapsed / expanded toggle** button at the bottom of the rail
  - Collapsed: 48 px icon-only rail (`w-12`)
  - Expanded: 224 px icon + label rail (`w-56`) — default
  - Smooth CSS transition (`duration-200`)
- **Tooltip on hover in collapsed mode** via native `title` attribute on each nav item
- Branding abbreviation "eC" shown in collapsed mode; full "emClarity" in expanded mode
- Active route highlighting preserved in both modes
- Disabled placeholder items also respect collapsed width

---

## Shared Infrastructure

| File | Description |
|------|-------------|
| `src/api/client.ts` | `fetch` wrapper; `ApiError` with status + statusText |
| `src/api/types.ts` | Shared API response types |
| `src/api/parameters.ts` | Parameter file CRUD endpoints |
| `src/hooks/useApi.ts` | React Query wrappers: `useApiQuery`, `useApiMutation` |
| `src/hooks/useRecentProjects.ts` | `localStorage`-backed recent project list |
| `src/hooks/useRunProfiles.ts` | `localStorage`-backed run profile CRUD |
| `src/data/parameterRegistry.ts` | Maps each Action tab to its set of claimed parameter IDs |
| `src/data/parameter-schema.json` | Golden parameter definitions (type, default, range, units, …) |
| `src/types/parameters.ts` | `ParameterDefinition`, `ParameterFile`, `ValidationResult` |
| `src/types/project.ts` | `Project`, `TiltSeries`, `ProjectState` |
| `src/types/workflow.ts` | `WorkflowState`, `WorkflowTransition` |
| `src/types/runProfile.ts` | `RunProfile` |
| `src/lib/validation.ts` | Zod schema helpers for form validation |

---

*Last updated: Phase 0.1 complete (TASK-024)*
