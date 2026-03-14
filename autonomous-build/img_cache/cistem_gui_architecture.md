# cisTEM GUI Architecture Reference

Source: `/sa_shared/git/cisTEM/worktrees/multiview_particle_stacks/src/gui/`

## Frontend Vocabulary

| cisTEM Term | Frontend Equivalent | Description |
|-------------|-------------------|-------------|
| `MenuBook` (wxListbook) | **Navigation rail** / sidebar nav | Vertical icon strip on left. Uses `wxLB_LEFT` orientation. |
| Pages (in MenuBook) | **Views** / **pages** | Each sidebar icon switches to a different page/view. |
| `AssetsBook`, `ResultsBook`, etc. | **Tab bar** / **sub-navigation** | Horizontal wxListbook (`wxLB_TOP`) within each page for sub-sections. |
| Panel classes (`MyOverviewPanel`) | **Page components** | Each panel is a self-contained view with its own state and event handlers. |
| `wxFormBuilder` (.fbp files) | **Component templates** | Layout definitions generated into C++ base classes. `My*` subclasses add behavior. |

## Main Navigation (MenuBook)

| Index | Label | Class | Icon | Notes |
|-------|-------|-------|------|-------|
| 0 | Overview | `MyOverviewPanel` | `overview_icon.cpp` | Default/home page |
| 1 | Assets | `MyAssetsPanel` | `assets_icon.cpp` | Data management |
| 2 | Actions | `ActionsPanelSpa` or `ActionsPanelTm` | `action_icon.cpp` | Workflow-specific, dynamically swapped |
| 3 | Results | `MyResultsPanel` | `results_icon.cpp` | Output visualization |
| 4 | Settings | `MySettingsPanel` | `settings_icon.cpp` | Run profiles |
| 5 | Experimental | `MyExperimentalPanel` | `experimental_icon.cpp` | Compile-time conditional |

## Panel Inheritance Pattern

```
wxFormBuilder (.fbp)
  → generates base class (e.g. OverviewPanel)
    → My* subclass adds behavior (e.g. MyOverviewPanel)
```

All base classes live in `ProjectX_gui_main.h/.cpp` (generated). Behavior subclasses are in separate `My*.h/.cpp` files.

## Sub-Navigation by Page

### Assets (AssetsBook, wxLB_TOP)
Movies, Images, Particle Positions, 3D Volumes, Refine Pkgs., Atomic Coordinates, TM Pkgs.

### Actions — SPA Workflow (ActionsBook)
Align Movies, Find CTF, Find Particles, 2D Classify, Ab-Initio 3D, Auto Refine, Manual Refine, Refine CTF, Generate 3D, Sharpen 3D

### Actions — TM Workflow (ActionsBook)
Align Movies, Find CTF, Match Templates, Refine Template, Generate 3D, Sharpen 3D

### Results (ResultsBook)
Align Movies, Find CTF, Find Particles, 2D Classify, 3D Refinement, TM Results

### Settings (SettingsBook)
Run Profiles

## Key Source Files

| File | Purpose |
|------|---------|
| `projectx.cpp` | App entry point, panel instantiation, icon setup |
| `MainFrame.h/.cpp` | Main window, event handlers, panel switching |
| `ProjectX_gui_main.h/.cpp` | wxFormBuilder-generated base classes |
| `MyOverviewPanel.h/.cpp` | Overview panel behavior |
| `workflows/WorkflowRegistry.h` | Factory for workflow-specific Actions panels |
| `workflows/SpaWorkflow.h` | SPA workflow panel registration |
| `workflows/TmWorkflow.h` | TM workflow panel registration |
| `gui_functions.cpp` | Helpers: recent projects, settings |
| `wxformbuilder/*.fbp` | Layout definitions |
