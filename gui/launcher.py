#!/usr/bin/env python3
"""
Launcher script for emClarity GUI.

This script sets up the Python path and launches the main GUI application.
"""

import sys
import os
from pathlib import Path

# Add the gui directory to the Python path
gui_dir = Path(__file__).parent.absolute()
if str(gui_dir) not in sys.path:
    sys.path.insert(0, str(gui_dir))

def main():
    """Main launcher function."""
    print("Starting emClarity GUI...")
    
    # Check if we have display support
    if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        print("Warning: No display detected. You may need to set up X11 forwarding or run on a system with a display.")
    
    # Set QT platform plugin fallback
    if 'QT_QPA_PLATFORM' not in os.environ:
        # Try xcb first, fallback to wayland if that fails
        try:
            os.environ['QT_QPA_PLATFORM'] = 'xcb'
        except:
            os.environ['QT_QPA_PLATFORM'] = 'wayland'
    
    try:
        import main
        main.main()
    except ImportError as e:
        print(f"Error importing GUI modules: {e}")
        print("\nPlease ensure you have activated the virtual environment:")
        print("source .venv/bin/activate")
        print("pip install PySide6")
        sys.exit(1)
    except Exception as e:
        print(f"Error starting GUI: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
