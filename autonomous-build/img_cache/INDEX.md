# Screenshot Reference Index

Annotated screenshots of the cisTEM GUI for use by autonomous build agents.
Annotations are in **magenta** to distinguish from GUI elements.

## Conventions
- **Annotations**: Magenta block text, arrows, and brackets drawn over screenshots
- **Images**: gitignored (*.png) — this index and metadata MDs are tracked
- **Architecture reference**: See [cistem_gui_architecture.md](cistem_gui_architecture.md) for full panel hierarchy, class names, and frontend vocabulary mapping

## Vocabulary Quick Reference

| cisTEM Code | Frontend Term | What It Is |
|-------------|--------------|------------|
| MenuBook (wxListbook) | Navigation rail / sidebar nav | Vertical icon strip on left side |
| Pages in MenuBook | Views / pages | Each icon switches the main content area |
| Sub-books (AssetsBook, etc.) | Tab bar / sub-navigation | Horizontal tabs within a page |
| Panel classes | Page components | Self-contained views |

---

## 1. Overview Panel — `Overview_panel.png`

**Detailed metadata**: [Overview_panel.md](Overview_panel.md)
**Source**: cisTEM beta — main landing screen after launch
**cisTEM class**: `MyOverviewPanel` → inherits `OverviewPanel` (wxFormBuilder)
**Source file**: `src/gui/MyOverviewPanel.cpp`

### Annotated Regions

| Region | cisTEM Implementation | Frontend Equivalent | Notes |
|--------|----------------------|--------------------|----|
| **Navigation rail** (left icon strip) | `MenuBook` — a `wxListbook` with `wxLB_LEFT`. 6 entries: Overview, Assets, Actions, Results, Settings, Experimental. Icons from `src/gui/icons/`. | Sidebar nav / navigation rail | Primary navigation. Always visible. Switches the entire main content area. |
| **Welcome / debug info** (top center) | `SetWelcomeInfo()` writes version, branch, build flags into `InfoText` (a `wxRichTextCtrl`). Shows `CISTEM_VERSION_TEXT`, `CISTEM_CURRENT_BRANCH`, compile flags. | Dev/debug banner | **Not needed in new GUI.** Only useful during development. |
| **Action buttons** (center) | "Create a new project" and "Open an existing project" are **URL links** inside the `wxRichTextCtrl`, handled by `OnInfoURL()`. "CreateProject" triggers `main_frame->StartNewProject()`, "OpenProject" triggers `main_frame->GetFileAndOpenProject()`. | Primary action buttons / CTA | These are the main entry points. Should be prominent buttons (not text links) in the new GUI. |
| **Recent projects list** (bottom center) | Populated by `GetRecentProjectsFromSettings()` from wxConfig keys `RecentProject1`–`RecentProject5`. Shows up to 5 recent project file paths as clickable URLs. Clicking opens the project DB directly. | Recent items list | Nice-to-have for Phase 0. Projects stored as full filesystem paths. |

### Behavior Notes (from source)
- When a project is open, `SetWelcomeInfo()` is replaced by `SetProjectInfo()` which shows: project name, directory, total runtime, total jobs run
- The Overview panel contains a single `wxRichTextCtrl` (`InfoText`) — all content is rendered as rich text, not discrete widgets
- The `wxStaticLine` (`m_staticline2`) provides a vertical separator between the navigation rail and the content area

### Intent for Phase 0 (emClarity GUI)
- Replicate the navigation rail pattern — vertical sidebar that switches between pages
- Home/overview page should have **real buttons** for create/open project (not embedded rich text links)
- Skip the debug/build info banner
- Recent projects: optional for Phase 0, but the pattern (store paths, show clickable list) is straightforward
