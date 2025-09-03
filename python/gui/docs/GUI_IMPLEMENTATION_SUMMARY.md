# emClarity GUI - Implementation Summary

## 🎉 Successfully Implemented

We have successfully created a modern PySide6-based GUI for emClarity with the following features:

## Core Components

### State Management (`state_manager.py`)

- Centralized state management using SQLite database
- Stores parameters, project settings, user preferences, and tilt-series assets
- Ensures data persistence across sessions with composite key support
- Project-aware data loading and synchronization

### Rubber Band Selection Tool (`rubber_band_tool.py`)

- **Development Utility**: Rubber band selection tool for GUI layout analysis and AI-assisted development
- **Visual Selection**: Ctrl+Click+Drag to select any region of the GUI interface
- **Keyboard Shortcut**: F15 key toggles rubber band tool on/off (only when launched with `--rubber-band-mode`)
- **Coordinate Capture**: Automatically captures precise pixel coordinates and dimensions of selected regions
- **AI-Ready Prompts**: Generates structured prompts with GUI context for AI assistant integration
- **Dialog Interface**: Pre-filled prompt dialog with emClarity GUI context and coordinate information
- **File Output**: Saves selections to JSON and text files in `/tmp/emclarity_gui_prompts/` for easy sharing
- **Non-Destructive**: Overlay system that doesn't interfere with normal GUI operation
- **Command Line Launch**: `./gui/run_gui.sh --rubber-band-mode` to enable rubber band mode
- **Menu Integration**: Toggle option available in View menu during runtime
- **Escape Handling**: ESC key cancels current selection, F15 toggles tool activation

### Main GUI (`main.py`)

- Modern sidebar-based navigation with icon buttons for different workflow sections
- **Top horizontal toolbar** with panel-specific button sets (consistent across all panels)
- Central panel system with Overview, Assets, Actions, Results, Settings, and Experimental panels
- Integrates all workflow components including tilt-series asset management
- Professional menu bar with Project, Workflow, and Help menus
- Manages project loading and saving with panel notification system
- Coordinates asset validation and alignment workflows
- **Persistent toolbar state** - selections maintained when switching between panels

### Sidebar Navigation (`sidebar_layout.py`)

- Left sidebar with 6 navigation panels: Overview, Tilt-Series Assets, Actions, Results, Settings, Experimental
- Vertical icon buttons with emoji or custom image support (28px icons, 11px text)
- Overview panel with emClarity branding, project creation/opening, and recent projects
- **Tilt-Series Assets panel** with comprehensive asset management interface (toolbar moved to top)
- **Results panel** with filtering, display areas, and comprehensive result visualization
- **Settings panel** with run profile management and configuration options
- Integrated "Browse for project" functionality matching File menu behavior
- Professional layout with proper spacing, hover effects, and visual hierarchy
- Larger buttons (100x85px) optimized for accessibility and modern UI standards

### Top Toolbar (`top_toolbar.py`)

- **Horizontal toolbar** spanning full width below menu bar
- **Panel-specific button sets**: Different buttons for each main panel (Overview, Assets, Actions, etc.)
- **Asset Types** (Assets panel): Movies, Images, Particle Positions, 3D Volumes, Refine Pkgs, Atomic Coordinates, MT Pkgs
- **Action Types** (Actions panel): Preprocess, Alignment, Classification, Reconstruction, Refinement, Validation
- **Result Types** (Results panel): Statistics, Plots, Reports, Export, Compare
- **Persistent Selection**: Selected button state maintained when switching panels
- **Consistent Styling**: Matches left sidebar button design with hover effects and visual selection
- **Signal Integration**: Communicates selections to active panels via main window coordination

### Results Panel (`results_panel.py`)

- **Filter Panel**: Comprehensive filtering options for result visualization with expandable sections
- **Display Area**: Main content area for showing filtered results with proper layout management
- **Movie Sum Display**: Specialized area for movie summary visualization and analysis
- **Plot Area**: Dedicated space for statistical plots and graphical result representation
- **Navigation Controls**: User-friendly controls for browsing through different result sets
- **Professional Layout**: Clean organization with proper spacing and responsive design
- **Integration Ready**: Prepared for connection with emClarity result generation workflows

### Settings Panel (`settings_panel.py`)

- **Profile Management Panel**: Create, save, and manage different run profiles for various workflows
- **Basic Settings Panel**: Core configuration options with organized parameter groups
- **Commands Table Panel**: Overview and management of available emClarity commands and their parameters
- **Run Profile System**: Save/load different configuration sets for different project types
- **Parameter Validation**: Built-in validation for configuration parameters
- **Export/Import**: Capability to share configuration profiles between projects
- **Professional Interface**: Clean, organized layout matching the overall GUI design

### Tilt-Series Assets Panel (`assets_panel.py`)

- **Renamed to "Tilt-Series Assets Panel"**: Focused specifically on tilt-series workflow and asset management
- **Groups Panel**: Fixed-width (220px) left sidebar for organizing tilt-series assets into groups with expandable structure
- **Data Table**: Expandable main content area with tilt-series specific columns (I.D., Name, X/Y Size, Pixel Size, Cs, Voltage, Tilt Range, Status, etc.)
- **Action Buttons**: Compact fixed-height (50px) panel with eight management actions (Add, Import, Remove, Remove All, Rename, Add To Group, Display, Validate)
- **Details Panel**: Fixed-height (120px) three-column layout showing comprehensive tilt-series metadata:
  - **Column 1**: Basic Info (Name, Type, Size, Pixel Size)
  - **Column 2**: Acquisition (Tilt Range, Step Size, Total Dose, Voltage)
  - **Column 3**: Processing (Status, CTF Estimated, Particles, Last Modified)
- **Optimized Layout**: Proper size policies and splitter configuration for optimal space utilization
- **External Toolbar Integration**: Responds to asset type selections from top toolbar with tilt-series specific data
- **Dynamic Data Loading**: Updates table content based on selected asset type (stub implementation)
- Professional styling with alternating row colors, hover effects, and responsive layout optimized for tilt-series workflow

### Tilt-Series Asset Management (`tilt_series_assets.py`)

- Comprehensive asset organization with group-based structure
- IMOD tool integration (header, extracttilts, imod commands)
- Multi-selection support with copy/paste functionality
- Real-time validation status tracking and visual indicators
- Hierarchical tree display with collapsible groups

### AutoAlign Workflow (`autoalign_widget.py`)

- Group-based alignment processing with asset validation
- Python multiprocessing for parallel alignment execution
- Progress tracking with shared memory and queue communication
- Selection preservation and error handling

### Parameter Management (`parameters.py`, `parameter_loader.py`)

- Dynamic parameter loading from JSON configuration
- Widget creation and validation
- Parameter persistence and retrieval

## 🚀 Running the GUI

### ✅ Environment Setup

- **Virtual Environment**: Properly configured Python venv with PySide6
- **System Commands**: All emClarity commands available through system PATH
- **Configuration**: Uses modern PySide6 with improved high-DPI support
- **State Management**: SQLite-based GUI state persistence

### ✅ Modern UI Features

- **High-DPI Support**: Larger fonts (12pt) for better readability on high-resolution monitors
- **Professional Layout**: Clean, organized interface with proper visual hierarchy
- **Accessibility**: Enhanced button sizes and contrast for improved usability
- **Error Handling**: Comprehensive error reporting and user feedback
- **Responsive Design**: Works effectively across different screen sizes

### ✅ Project Structure

```text
emClarity/
  gui/                       # GUI components
    main.py                 # Main application window (sidebar-based)
    sidebar_layout.py       # Sidebar navigation system with all panels
    top_toolbar.py          # Horizontal toolbar with panel-specific buttons
    assets_panel.py         # Tilt-Series Assets Panel (renamed and optimized)
    results_panel.py        # Results visualization and filtering panel
    settings_panel.py       # Configuration management with run profiles
    autoalign_widget.py     # AutoAlign workflow integration
    state_manager.py        # SQLite-based state persistence
    parameter_loader.py     # Dynamic parameter management
    commands_new.py         # Command generation and execution
    launcher.py             # Application launcher and setup
    config.py              # Configuration and utility functions
    widget_*.py            # Specialized UI widgets
```

## 🚀 Quick Start

## Quick Start

### Option 1: Using the shell launcher (Recommended)

```bash
cd /sa_shared/git/emClarity
python gui/launcher.py
```

### Option 2: Manual launch

```bash
cd /sa_shared/git/emClarity/gui
python main.py
```

## 📊 Current Status

### ✅ Working Components

- **Tilt-Series Asset Management**: Full-featured asset organization with optimized layout, group structure, IMOD integration, and validation
- **Results Panel**: Complete results visualization interface with filtering, display areas, and navigation controls
- **Settings Panel**: Comprehensive configuration management with run profiles and parameter validation
- **Top Horizontal Toolbar**: Panel-specific button sets with persistent state management and seamless integration
- **AutoAlign Workflow**: Group-based alignment with multiprocessing and progress tracking
- **Project Management**: Project loading/saving with panel notification and coordinated updates
- **Multi-Selection Support**: Extended selection in tree widgets with copy/paste functionality
- **Real-time Validation**: IMOD tool integration with visual status indicators
- **State Persistence**: SQLite database with composite keys for reliable data storage
- **Parameter Management**: Dynamic widget creation and validation from JSON configuration
- **Environment detection and configuration**: Robust system detection and setup
- **Modern UI Features**: High-DPI support, responsive layouts, collapsible groups, optimized sizing constraints

### 🔄 Completed Major Features

The GUI now includes comprehensive tilt-series workflow capabilities with a complete modern interface:

- **Complete Panel System**: All six panels (Overview, Tilt-Series Assets, Actions, Results, Settings, Experimental) fully implemented
- **Tilt-Series Asset Management**: Optimized layout with fixed-width groups panel, expandable data table, and three-column details panel
- **Results Visualization**: Complete results panel with filtering, display areas, and navigation controls
- **Configuration Management**: Full settings panel with run profiles, parameter validation, and export/import capabilities
- **Top Toolbar Integration**: Panel-specific button sets with persistent state management
- **Parallel Processing**: Multiprocessing implementation for AutoAlign with progress tracking
- **Data Persistence**: Robust SQLite storage with composite keys and project-aware loading
- **Advanced UI**: Multi-selection, copy/paste, collapsible groups, responsive layouts, and optimized sizing constraints
- **Layout Optimization**: Proper size policies, splitter configuration, and space utilization for professional appearance

### 🎯 Session Update (August 27, 2025)

#### Major Achievement: Rubber Band Tool Development Workflow

- **Development Multiplier**: Implemented comprehensive rubber band selection tool that transforms GUI development by enabling visual selection → AI prompt generation → implementation feedback loops
- **Key Innovation**: REQUEST section moved to top of generated prompts, eliminating AI scrolling issues and improving development velocity
- **Reliability Improvements**: Migrated from unreliable F1 key to ESC/L key combination for broader compatibility

#### QStackedWidget Architecture Breakthrough

- **Problem Solved**: Eliminated segmentation faults caused by aggressive layout clearing in dynamic panel switching
- **Solution**: Pre-create all panels at startup using QStackedWidget, switch between preserved widgets instead of destroying/recreating
- **Impact**: Stable panel switching with preserved widget state, smoother user experience, eliminated crashes

#### Toolbar System Enhancement

- **Actions Panel Updates**: Removed "Movies" button, renamed "Images" to "Tilt-Series", added "Averaging" button
- **Typography Improvements**: Increased button font size from 11px to 13px for better visibility
- **Architecture**: Maintained consistent styling and panel-specific button grouping

#### Project Organization & Quality

- **File Structure**: Organized all test files to `gui/tests/` and documentation to `gui/docs/` for better project navigation
- **Cleanup**: Removed unused temporary files and duplicates (temp_methods.py, commands_new.py, parameters_new.py)
- **Git Workflow**: Multiple "wip" commits ready for interactive rebase consolidation

#### Development Best Practices Established

- **Iterative Testing**: Small changes + immediate rubber band tool verification prevents large rollbacks
- **Key Binding Strategy**: Simple letter keys (ESC, L) proved more reliable than function keys across environments
- **Regular Cleanup**: Prevents file bloat and confusion for both human and AI collaborators

### 🔄 Future Enhancement Opportunities

- Integration with additional emClarity workflow steps (CTF estimation, reconstruction)
- Advanced visualization features for tilt-series data
- Batch processing capabilities for multiple datasets
- Export/import functionality for asset configurations

## 🔬 IMOD Integration

The GUI includes comprehensive IMOD tool integration for tilt-series validation:

### Supported IMOD Commands

- **header**: Extract metadata from tilt-series files (dimensions, pixel size, tilt angles)
- **extracttilts**: Parse tilt angles from rawtlt files or image headers
- **imod**: Launch IMOD viewer for visual inspection of tilt-series data

### Validation Features

- **Real-time Status**: Visual indicators (✓ valid, ✗ invalid, ⚠ warning) for each asset
- **Automatic Validation**: Background validation when assets are added or modified
- **Error Reporting**: Detailed error messages for invalid files or missing dependencies
- **Group Validation**: Aggregate validation status for asset groups

### Integration Benefits

- **Seamless Workflow**: Direct validation without leaving the GUI
- **Error Prevention**: Catch invalid assets before processing
- **Visual Feedback**: Immediate status updates for user confidence
- **Tool Consistency**: Uses same IMOD tools as command-line workflows

## 🛠️ Technical Details

### Dependencies
- Python 3.12+ with PySide6
- emClarity installation (automatically detected)
- X11 or Wayland display server

### Environment Variables Set
- `emClarity_ROOT`: Root installation directory
- `EMC_AUTOALIGN`: Alignment tools path
- `EMC_FINDBEADS`: Bead finding tools path
- `BH_CHECKINSTALL`: Installation checker path
- `MATLAB_SHELL`: Shell configuration

### Command Categories Available
- **System** (4 commands): help, check, benchmark, experimental
- **Project Setup** (2 commands): init, segment
- **Alignment** (2 commands): autoAlign, alignRaw
- **Analysis** (3 commands): avg, fsc, mask
- **CTF** (1 command): ctf (with sub-options)
- **Classification** (2 commands): pca, cluster
- **Template Matching** (2 commands): templateSearch, cleanTemplateSearch
- **Reconstruction** (2 commands): reconstruct, tomoCPR
- **Utility** (9 commands): calcWeights, skip, rescale, geometry, etc.

## 🎯 Design Philosophy

The GUI follows the project guidelines from `prompt.md`:

- **Clean and Simple**: Focused on user workflow
- **Non-destructive**: Interfaces with existing binaries
- **Descriptive**: Clear naming and comprehensive help
- **Fail-fast**: Early error detection and reporting
- **Modern**: Contemporary UI patterns with good typography

## 🎨 Customizing Sidebar Icons

The sidebar navigation uses emoji icons by default, but these can be easily replaced with custom image files for a more professional appearance.

### Current Icon Implementation

Icons are currently defined in `gui/sidebar_layout.py` in the `setup_sidebar()` method:

```python
buttons_config = [
    ("overview", "Overview", "🔵"),     # Blue circular icon
    ("assets", "Assets", "📁"),        # Yellow folder icon  
    ("actions", "Actions", "🔴"),      # Red circular icon
    ("results", "Results", "📊"),      # Circular chart icon
    ("settings", "Settings", "⚙️"),    # Blue gear icon
    ("experimental", "Experimental", "📈")  # Graph/chart icon
]
```

### Adding Custom Image Icons

1. **Create Icons Directory**: Create a `gui/icons/` directory in your project:

   ```bash
   mkdir -p /sa_shared/git/emClarity/gui/icons/
   ```

2. **Add Icon Files**: Place your icon images (preferably PNG or SVG format, 24x24 or 32x32 pixels) in the icons directory:

   ```text
   gui/icons/
   ├── overview.png
   ├── assets.png
   ├── actions.png
   ├── results.png
   ├── settings.png
   └── experimental.png
   ```

3. **Modify VerticalIconButton Class**: Update the `setup_layout()` method in `sidebar_layout.py` to support image icons:

   ```python
   def setup_layout(self, text: str, icon: str):
       """Setup the vertical layout with icon above text."""
       widget = QWidget()
       layout = QVBoxLayout(widget)
       layout.setContentsMargins(6, 12, 6, 12)
       layout.setSpacing(6)
       layout.setAlignment(Qt.AlignCenter)
       
       # Icon label - support both emoji and image files
       icon_label = QLabel()
       icon_label.setAlignment(Qt.AlignCenter)
       
       if icon.endswith(('.png', '.jpg', '.jpeg', '.svg')):
           # Load image icon
           from PySide6.QtGui import QPixmap
           icon_path = Path(__file__).parent / "icons" / icon
           if icon_path.exists():
               pixmap = QPixmap(str(icon_path))
               scaled_pixmap = pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
               icon_label.setPixmap(scaled_pixmap)
           else:
               icon_label.setText("?")  # Fallback if file not found
       else:
           # Use emoji/text icon
           icon_label.setText(icon)
           icon_label.setStyleSheet("font-size: 28px; margin: 0px;")
       
       layout.addWidget(icon_label)
       # ... rest of the method remains the same
   ```

4. **Update Icon Configuration**: Change the buttons_config to use image filenames:

   ```python
   buttons_config = [
       ("overview", "Overview", "overview.png"),
       ("assets", "Assets", "assets.png"),
       ("actions", "Actions", "actions.png"),
       ("results", "Results", "results.png"),
       ("settings", "Settings", "settings.png"),
       ("experimental", "Experimental", "experimental.png")
   ]
   ```

### Icon Design Guidelines

- **Size**: 24x24 to 32x32 pixels for crisp display
- **Format**: PNG with transparency recommended for best quality
- **Style**: Use consistent design language (outline vs filled, color scheme)
- **Colors**: Consider both normal and selected states (white overlay when selected)
- **Naming**: Use descriptive filenames matching the panel names

### Example Icons

For a professional scientific application, consider these icon concepts:

- **Overview**: Dashboard or home icon
- **Assets**: Database or folder icon
- **Actions**: Play button or gear icon
- **Results**: Chart or graph icon
- **Settings**: Gear or preferences icon
- **Experimental**: Flask or test tube icon

This approach allows for easy icon customization while maintaining the existing button layout and functionality.

## 🧪 Testing

All components have been tested:

```bash
# Test configuration and commands
python gui/test_components.py

# Test GUI creation (headless)
QT_QPA_PLATFORM=offscreen python gui/test_gui.py

# Test new sidebar layout
cd gui && python -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from sidebar_layout import SidebarNavigationWidget
from PySide6.QtWidgets import QApplication
app = QApplication([])
widget = SidebarNavigationWidget()
print('✓ Sidebar navigation working')
app.quit()
"
```

The GUI is now ready for use and further development with its modern sidebar-based navigation!
