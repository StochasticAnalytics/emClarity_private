# Overview Panel — Detailed Metadata

**Screenshot**: `Overview_panel.png`
**cisTEM class**: `MyOverviewPanel` (inherits `OverviewPanel`)
**Source files**:
- `src/gui/MyOverviewPanel.h` — header
- `src/gui/MyOverviewPanel.cpp` — behavior (250+ lines)
- `src/gui/ProjectX_gui_main.h` — base class (wxFormBuilder generated, lines 187–208)

## Widget Composition

The entire Overview panel is built from just three widgets:

| Widget | Type | Name | Purpose |
|--------|------|------|---------|
| InfoText | `wxRichTextCtrl` | `InfoText` | All content rendered as styled rich text with embedded URLs. Read-only. |
| WelcomePanel | `wxPanel` | `WelcomePanel` | Container/parent for InfoText |
| Separator | `wxStaticLine` | `m_staticline2` | Vertical divider between nav rail and content area |

This means the Overview page has **no discrete widgets** — no buttons, no list controls, no forms. Everything (headings, links, project list) is rich text.

## Two Display Modes

### Mode 1: Welcome (no project open) — `SetWelcomeInfo()`
Lines 67–248 in MyOverviewPanel.cpp. Shows:
- cisTEM logo (embedded bitmap)
- "Welcome to cisTEM (Computational Imaging System for Transmission Electron Microscopy)"
- Link to cistem.org
- Version info (conditionally compiled):
  - `CISTEM_VERSION_TEXT` — version string
  - `CISTEM_TIME_READABLE` — commit datetime
  - `CISTEM_CURRENT_BRANCH` — git branch
  - `CISTEM_SVN_REV` — legacy SVN revision
- Build flags: ENABLEGPU, MKL, EXPERIMENTAL, ROTATEFORSPEED, PROFILING
- "Begin" section with Create/Open project links
- Recent projects list (up to 5)

### Mode 2: Project open — `SetProjectInfo()`
Lines 11–65 in MyOverviewPanel.cpp. Shows:
- cisTEM logo
- Conditional prompt if no movies/images imported: "To get started, go to the Assets panel and import some movies or images..."
- Project summary:
  - Project name
  - Project directory path
  - Total job runtime (formatted as hours and days)
  - Total number of jobs run

## Action Buttons (URL Links)

The "buttons" are actually clickable URLs inside the wxRichTextCtrl, handled by a single event handler:

**Handler**: `OnInfoURL(wxTextUrlEvent& event)` — lines 250–276

| URL String | Action |
|-----------|--------|
| `"CreateProject"` | Calls `main_frame->StartNewProject()` |
| `"OpenProject"` | Calls `main_frame->GetFileAndOpenProject()` |
| `"http://cistem.org"` | Opens external browser via `wxLaunchDefaultBrowser()` |
| Any other URL | Treated as a project DB path → calls `main_frame->OpenProject(url)` |

This last case is how recent project entries work — each path is a clickable URL that opens the project directly.

## Recent Projects System

**Read**: `GetRecentProjectsFromSettings()` — `src/gui/gui_functions.cpp` lines 110–125
- Reads wxConfig keys `RecentProject1` through `RecentProject5`
- Returns up to 5 file paths

**Write**: `AddProjectToRecentProjects()` — `src/gui/gui_functions.cpp` lines 127–150
- Inserts new path at position 1, shifts others down
- Deduplicates (if project already in list, moves it to top)
- Truncates at 5 entries
- Called from `MainFrame.cpp` on project create (line 578) and project open (line 855)

**Storage**: wxConfig (platform-specific — registry on Windows, plist on macOS, dotfile on Linux)

## Implications for Phase 0 (emClarity)

| cisTEM Pattern | Recommendation for New GUI |
|---------------|---------------------------|
| All content in wxRichTextCtrl | Use proper React components — real buttons, real lists, real layout |
| URL-based "buttons" | Use `<button>` or `<Link>` components with onClick handlers |
| Two display modes (welcome vs project) | Conditional rendering based on project state: `project ? <ProjectDashboard /> : <WelcomePage />` |
| Recent projects in wxConfig | Store in localStorage or backend DB. Display as a card list, not raw file paths. |
| Build flags / version text | Omit from user-facing UI. Available via /api/v1/system/info if needed. |
| Project summary (name, dir, runtime, jobs) | Good pattern to keep — show as a dashboard card on the project overview page |
