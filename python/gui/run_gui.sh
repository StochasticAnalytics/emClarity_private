#!/bin/bash
# emClarity GUI Launcher Script

# Help function
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --rubber-band-mode    Enable rubber band selection tool for GUI development"
    echo "  --help               Show this help message"
    echo ""
    echo "Rubber Band Mode:"
    echo "  When enabled, Click+Drag to select GUI regions for analysis"
    echo "  Press L to toggle click logging on/off"
    echo "  Click on GUI elements (when logging enabled) to capture context"
    echo "  Press ESC to toggle the rubber band tool on/off during runtime"
    echo "  Selected regions generate AI-friendly prompts for layout improvements"
    echo ""
}

# Check for help flag
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    show_help
    exit 0
fi

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EMCLARITY_ROOT="$(dirname "$SCRIPT_DIR")"

# Ensure we're in the emClarity directory
cd "$EMCLARITY_ROOT"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Creating it now..."
    python3 -m venv .venv
    echo "Installing required packages..."
    .venv/bin/pip install PySide6 typing_extensions
fi

# Activate virtual environment and run GUI
echo "Starting emClarity GUI..."
echo "emClarity root: $EMCLARITY_ROOT"

# Check for rubber band mode
if [[ "$*" == *"--rubber-band-mode"* ]]; then
    echo "🎯 Rubber Band Mode will be available"
    echo "Press ESC to activate rubber band selection tool"
    echo "Once active: Click+Drag to select GUI regions"
    echo "Press L to toggle click logging, then click elements to capture context"
fi

# Set up environment
export PYTHONPATH="$EMCLARITY_ROOT/gui:$PYTHONPATH"

# Try to detect and use the best available Qt platform
if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
    echo "Display detected, starting GUI..."
else
    echo "Warning: No display detected. You may need X11 forwarding or a graphical environment."
fi

# Launch the GUI with all arguments passed through
exec .venv/bin/python gui/launcher.py "$@"
