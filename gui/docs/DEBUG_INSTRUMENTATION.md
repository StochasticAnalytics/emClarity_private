# GUI Debug Instrumentation System

The emClarity GUI debug instrumentation system provides a lightweight way to capture user interactions for analysis with the rubber band tool. This system is designed with minimal performance impact and conditional compilation support.

## Quick Start

1. **Launch with instrumentation enabled:**
   ```bash
   ./gui/run_gui.sh --rubber-band-mode
   ```

2. **Click on GUI elements** (buttons, links, menu items) - their context is automatically captured

3. **Use Ctrl+Click+Drag** to select areas with the rubber band tool

4. **The dialog will include both visual analysis AND click context**

## System Overview

### Debug Instrumentation Module (`debug_instrumentation.py`)

The core module provides:
- **Zero overhead when disabled** - fast early returns for production builds
- **Conditional compilation** via environment variables (like C++ `#ifdef`)
- **Automatic click data capture** with minimal code changes
- **Temporary file storage** for integration with rubber band tool

### Integration Patterns

#### Pattern 1: Decorator (Recommended for Methods)
```python
from . import debug_instrumentation

@debug_instrumentation.instrument_click(
    element_id="save_project_btn",
    element_type="QPushButton", 
    action_description="Save current project",
    panel_context="main_toolbar"
)
def save_project(self):
    # Normal implementation
    self.do_save_project()
```

#### Pattern 2: Direct Calls (Recommended for Event Handlers)
```python
def on_button_clicked(self):
    debug_instrumentation.instrument_click_event(
        element_id="process_data_btn",
        element_type="QPushButton",
        action_description="Start data processing",
        panel_context="processing_panel",
        additional_data={
            "processing_mode": self.get_processing_mode(),
            "input_files": len(self.selected_files)
        }
    )
    # Normal implementation
    self.start_processing()
```

#### Pattern 3: Lambda Integration (For Signals)
```python
button.clicked.connect(lambda: [
    debug_instrumentation.instrument_button_click(
        button, "Open file dialog", "assets"
    ),
    self.open_file_dialog()
])
```

#### Pattern 4: Convenience Functions
```python
# For buttons
debug_instrumentation.instrument_button_click(
    button, "Action description", "panel_name"
)

# For menu actions  
debug_instrumentation.instrument_menu_action(
    action, "menu_context"
)
```

## Implementation Examples

### Sidebar Navigation (Already Implemented)
```python
def switch_panel(self, panel_name: str):
    debug_instrumentation.instrument_click_event(
        element_id=f"{panel_name}_panel_button",
        element_type="SidebarNavigationButton", 
        action_description=f"Switch to {panel_name} panel",
        panel_context="sidebar_navigation",
        additional_data={
            "target_panel": panel_name,
            "source_panel": self.current_panel
        }
    )
    # Normal implementation continues...
```

### Top Toolbar (Already Implemented)
```python
def on_button_clicked(self, button_id):
    debug_instrumentation.instrument_click_event(
        element_id=f"{self.current_panel}_{button_id}_toolbar_btn",
        element_type="HorizontalToolbarButton",
        action_description=f"Activate {button_id} function in {self.current_panel} panel",
        panel_context=f"{self.current_panel}_toolbar"
    )
    # Normal implementation continues...
```

## Adding Instrumentation to New Components

### For New Buttons:
```python
class MyWidget(QWidget):
    def setup_ui(self):
        button = QPushButton("My Action")
        button.clicked.connect(self.on_my_action)
    
    @debug_instrumentation.instrument_click(
        "my_action_btn", "QPushButton", "Perform my action", "my_panel"
    )
    def on_my_action(self):
        # Implementation here
        pass
```

### For Menu Items:
```python
def setup_menu(self):
    action = QAction("&Export Data", self)
    action.triggered.connect(lambda: [
        debug_instrumentation.instrument_menu_action(action, "file_menu"),
        self.export_data()
    ])
```

### For Complex Widgets:
```python
def on_widget_interaction(self, data):
    debug_instrumentation.instrument_click_event(
        element_id=f"widget_{self.widget_id}",
        element_type=type(self).__name__,
        action_description=f"User interaction with {self.widget_type}",
        panel_context=self.parent_panel,
        additional_data={
            "interaction_type": data.get('type'),
            "widget_state": self.get_current_state(),
            "user_data": data
        }
    )
```

## Performance and Production Considerations

### Zero Overhead Design
- **Fast early return**: If rubber band mode is not active, functions return immediately
- **Conditional compilation**: Set `EMCLARITY_DEBUG_INSTRUMENTATION=False` to remove all instrumentation
- **Minimal memory footprint**: Only stores one recent click event

### Production Builds
```bash
# Disable all instrumentation (like C++ #ifdef)
export EMCLARITY_DEBUG_INSTRUMENTATION=False
python gui/launcher.py

# All instrumentation calls become no-ops
```

### Development Mode
```bash
# Enable instrumentation (default)
export EMCLARITY_DEBUG_INSTRUMENTATION=True
./gui/run_gui.sh --rubber-band-mode
```

## Data Flow

1. **User clicks GUI element** → `instrument_click_event()` called
2. **If rubber band mode active** → Click data saved to temporary file
3. **User drags rubber band selection** → Rubber band tool activated
4. **Dialog opens** → Reads latest click data + analyzes visual selection
5. **Enhanced AI prompt generated** → Includes both click context and visual analysis

## File Output

Click data is saved to `/tmp/emclarity_gui_debug/click_debug_YYYYMMDD_HHMMSS.json`:

```json
{
  "timestamp": "2025-08-27T10:30:45.123456",
  "element_id": "assets_panel_button", 
  "element_type": "SidebarNavigationButton",
  "action_description": "Switch to assets panel",
  "panel_context": "sidebar_navigation",
  "additional_data": {
    "target_panel": "assets",
    "source_panel": "overview"
  }
}
```

## Integration with Rubber Band Tool

The rubber band tool automatically:
- **Reads the latest click data** when generating prompts
- **Combines click context with visual analysis** 
- **Provides rich context** about what the user was trying to do
- **Suggests improvements** based on both interaction and visual data

## Adding More Components

To instrument new GUI components:

1. **Import the debug module**:
   ```python
   from . import debug_instrumentation
   ```

2. **Choose appropriate pattern** (decorator, direct call, or lambda)

3. **Add instrumentation to click handlers**:
   - Use descriptive `element_id` values
   - Include relevant `panel_context`
   - Add useful `additional_data`

4. **Test with rubber band mode** to see enhanced prompts

The system is designed to be:
- **Easy to add** to existing code
- **Zero performance impact** when disabled
- **Rich context provider** for AI-assisted GUI development
- **Production-safe** with conditional compilation

## Examples in Current Codebase

- **Sidebar navigation**: `sidebar_layout.py` - Panel switching
- **Top toolbar**: `top_toolbar.py` - Toolbar button clicks  
- **Menu actions**: `main.py` - File menu operations
- **Project links**: `sidebar_layout.py` - Create/open project links

Each provides rich context that helps the rubber band tool understand both **what was clicked** and **what the visual selection contains**.
