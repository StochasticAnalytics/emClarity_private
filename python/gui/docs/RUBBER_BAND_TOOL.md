# Rubber Band Tool for emClarity GUI Development

## Overview

The rubber band tool is a development utility for the emClarity GUI that helps with layout analysis, element identification, and generating AI-friendly prompts for GUI improvements.

## Features

- **Visual Selection**: Use Ctrl+Click+Drag to select any region of the GUI
- **Coordinate Capture**: Automatically captures precise coordinates and dimensions
- **AI-Ready Prompts**: Generates structured prompts for AI assistance
- **Temporary File Output**: Saves selections to files for easy sharing with AI agents
- **Non-Destructive**: Does not interfere with normal GUI operation

## Usage

### Starting with Rubber Band Mode

There are several ways to enable the rubber band tool:

#### 1. Command Line Launch
```bash
./gui/run_gui.sh --rubber-band-mode
```

#### 2. Menu Option (During Runtime)
- Open the emClarity GUI normally
- Go to `View` → `Toggle Rubber Band Mode`

#### 3. Help
```bash
./gui/run_gui.sh --help
```

### Making Selections

1. **Activate Selection**: Hold `Ctrl` and click in the GUI
2. **Drag to Select**: While holding `Ctrl`, drag to create a selection rectangle
3. **Release to Capture**: Release the mouse button to capture the selection
4. **Edit Prompt**: A dialog will appear with a pre-filled prompt
5. **Save or Cancel**: Choose to save the prompt to a file or cancel

### Keyboard Shortcuts

- `Ctrl + Click + Drag`: Create selection
- `ESC`: Toggle rubber band tool on/off (only when launched with `--rubber-band-mode`)
- `Right-click`: Cancel current selection
- `View` menu: Toggle rubber band mode on/off (alternative method)

## Output Files

The tool creates two types of files in `/tmp/emclarity_gui_prompts/`:

### JSON Format (`gui_prompt_YYYYMMDD_HHMMSS.json`)
```json
{
  "timestamp": "2025-08-27T10:30:45.123456",
  "selection_coordinates": {
    "x": 150,
    "y": 200,
    "width": 300,
    "height": 150
  },
  "prompt_text": "Your edited prompt here...",
  "gui_context": "emClarity PySide6 GUI - Development Tool"
}
```

### Text Format (`gui_prompt_YYYYMMDD_HHMMSS.txt`)
Human-readable format suitable for copying into AI chat interfaces.

## Default Prompt Template

The dialog includes a comprehensive default prompt that provides:

- **Coordinates**: Exact pixel coordinates and dimensions
- **Context**: Information about the emClarity GUI architecture
- **GUI Layout**: Description of the current interface structure
- **Request Template**: Placeholder for specific requests
- **Additional Details**: Section for extra context

## Example Workflow

1. **Launch in Rubber Band Mode**:
   ```bash
   ./gui/run_gui.sh --rubber-band-mode
   ```

2. **Navigate to Problem Area**: Go to the part of the GUI you want to analyze

3. **Make Selection**: Ctrl+Click+Drag over the relevant area

4. **Edit Prompt**: Modify the pre-filled text to describe your specific needs:
   ```text
   REQUEST:
   Please help me improve the button layout in this panel. The buttons are too close together and need better spacing.
   
   ADDITIONAL DETAILS:
   - Current buttons: Add, Remove, Edit
   - Desired spacing: 10px between buttons
   - Button size should be consistent
   ```

5. **Save to File**: Click "Save to File" to generate the output files

6. **Toggle Tool**: Use ESC to disable/enable the tool while working

7. **Share with AI**: Copy the text file content or upload the JSON to your AI assistant

## Development Use Cases

### Layout Improvements
- Select button groups that need better spacing
- Identify alignment issues in forms
- Analyze panel proportions

### Element Identification
- Select unknown widgets to get coordinate information
- Identify specific UI components by location
- Map out interaction areas

### Bug Reporting
- Capture exact coordinates of problem areas
- Document visual issues with precise locations
- Create reproducible issue reports

### Design Iterations
- Compare before/after layouts
- Document design decisions with coordinates
- Track UI changes over time

## Technical Details

### Implementation
- Built with PySide6 overlay widgets
- Transparent window capture system
- Non-blocking coordinate detection
- JSON and text output formats

### File Locations
- Temporary files: `/tmp/emclarity_gui_prompts/`
- Naming pattern: `gui_prompt_YYYYMMDD_HHMMSS.{json,txt}`
- Automatic directory creation

### Coordinate System
- Origin: Top-left corner of the GUI window
- Units: Pixels
- Format: (x, y, width, height)

## Tips for Best Results

1. **Be Specific**: Edit the default prompt to describe exactly what you need
2. **Include Context**: Add information about the current state of the GUI
3. **Use Multiple Selections**: Create several selections for complex layouts
4. **Save Regularly**: Files are timestamped for easy organization
5. **Combine with Screenshots**: Use rubber band coordinates alongside screenshots

## Troubleshooting

### Tool Not Activating
- Check that `--rubber-band-mode` flag was used
- Verify PySide6 is installed
- Check for Qt platform errors in console

### Selections Not Working
- Ensure you're holding `Ctrl` while clicking
- Try different areas of the GUI
- Check console for error messages

### Files Not Saving
- Check write permissions for `/tmp/` directory
- Verify disk space availability
- Check console for file system errors

### Dialog Not Appearing
- Try ESC to cancel current selection
- Check if dialog is hidden behind other windows
- Restart rubber band mode from View menu

## Integration with AI Assistants

The generated prompts are designed to work well with AI coding assistants:

1. **Copy the text file content** directly into your AI chat
2. **Upload the JSON file** if your AI supports file uploads  
3. **Include screenshots** alongside the coordinate data for visual context
4. **Reference the GUI architecture** mentioned in the prompt template

The tool provides AI assistants with:
- Exact pixel coordinates for surgical precision
- Context about the emClarity GUI structure
- Structured format for consistent responses
- Technical details about PySide6 implementation
