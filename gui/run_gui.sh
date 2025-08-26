#!/bin/bash
# emClarity GUI Launcher Script

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

# Set up environment
export PYTHONPATH="$EMCLARITY_ROOT/gui:$PYTHONPATH"

# Try to detect and use the best available Qt platform
if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
    echo "Display detected, starting GUI..."
else
    echo "Warning: No display detected. You may need X11 forwarding or a graphical environment."
fi

# Launch the GUI
exec .venv/bin/python gui/launcher.py "$@"
