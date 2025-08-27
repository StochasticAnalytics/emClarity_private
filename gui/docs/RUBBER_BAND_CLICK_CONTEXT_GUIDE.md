# Rubber Band Tool with Click Context - Quick Reference

## Quick Start

### 1. Launch GUI with Click Context Tracking
```bash
./gui/run_gui.sh --rubber-band-mode
```
You'll see: `🔍 GUI Debug Instrumentation ACTIVE`

### 2. New Workflow
1. **Ctrl+Click** on GUI elements you want to analyze (buttons, menus, links)
2. **Press ESC** to activate rubber band tool
3. **Click+Drag** to select visual area (no Ctrl needed!)
4. **Dialog opens** with both click context AND visual analysis

### 3. What You Get
- **Element Context**: What you Ctrl+clicked, what it does, which panel
- **Visual Analysis**: What widgets are in the selected area
- **Enhanced AI Prompt**: Ready to paste with full context

## Example Output

When you Ctrl+click "Assets" panel button then select a toolbar area:

```
🖱️ ELEMENT INTERACTION DATA:
- Last Clicked Element: assets_panel_button
- Element Type: SidebarNavigationButton  
- Intended Action: Switch to assets panel
- Element Panel: sidebar_navigation
- Click Time: 10:31:06

🎯 ACTIVE PANEL:
- Panel: assets
- Panel Class: TiltSeriesAssetsPanel

🔍 SELECTION ANALYSIS:
- UI Element Type: Horizontal Strip
- Widgets Found: 5
- Widget Types: QPushButton, QLabel
```

## Controls

- **ESC**: Toggle rubber band tool on/off
- **Click+Drag**: Select area (when tool active) - No Ctrl needed!
- **Ctrl+Click**: Capture element context for analysis
- **Right-click**: Cancel current selection
- **Regular clicks**: Work normally without logging anything

## For Developers

### Adding Instrumentation to New Components

**Method 1: Decorator**
```python
@debug_instrumentation.instrument_click(
    "button_id", "QPushButton", "What it does", "panel_name"
)
def button_clicked(self):
    # Your code here
```

**Method 2: Direct Call**
```python
def on_action(self):
    debug_instrumentation.instrument_click_event(
        "element_id", "ElementType", "Description", "panel"
    )
    # Your code here
```

### Production Builds
```bash
# Disable all instrumentation for production
export EMCLARITY_DEBUG_INSTRUMENTATION=False
```

## Troubleshooting

**No click data captured?**
- Make sure you clicked a GUI element BEFORE using rubber band tool
- Check that debug instrumentation is active (look for 🔍 message)

**Performance issues?**  
- Instrumentation has zero overhead when rubber band mode is off
- Only captures the most recent click (minimal memory usage)

**Import errors?**
- Make sure you're in the activated virtual environment
- Run from the emClarity root directory

## Files and Locations

- **Click data**: `/tmp/emclarity_gui_debug/click_debug_TIMESTAMP.json`
- **Prompts**: `/tmp/emclarity_gui_prompts/gui_analysis_TIMESTAMP.txt`
- **Documentation**: `gui/DEBUG_INSTRUMENTATION.md`

This system combines **what you clicked** with **what you selected** to provide rich context for AI-assisted GUI analysis and improvement.
