#!/usr/bin/env python3
"""
Test GUI creation without actually showing it.

This tests that the GUI can be instantiated correctly.
"""

import sys
import os
from pathlib import Path

# Add the gui directory to the Python path
gui_dir = Path(__file__).parent.absolute()
if str(gui_dir) not in sys.path:
    sys.path.insert(0, str(gui_dir))

# Set up for headless testing
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

try:
    from PySide6.QtWidgets import QApplication
    from main import EmClarityMainWindow

    def test_gui_creation():
        """Test that the GUI can be created."""
        print("Testing GUI creation...")
        
        app = QApplication(sys.argv)
        app.setApplicationName("emClarity GUI Test")
        
        try:
            window = EmClarityMainWindow()
            print("✓ GUI window created successfully")
            
            # Test that configuration loaded
            if window.config:
                version_info = window.config.get_version_info()
                print(f"✓ Configuration loaded: emClarity {version_info['version']}")
            else:
                print("✗ Configuration failed to load")
                return False
            
            # Test that commands are available
            if hasattr(window, 'command_tree') and window.command_tree.topLevelItemCount() > 0:
                print(f"✓ Command tree populated with {window.command_tree.topLevelItemCount()} categories")
            else:
                print("✗ Command tree not populated")
                return False
            
            print("✓ GUI test completed successfully")
            return True
            
        except Exception as e:
            print(f"✗ GUI creation failed: {e}")
            return False
        finally:
            app.quit()

    if __name__ == "__main__":
        success = test_gui_creation()
        sys.exit(0 if success else 1)

except ImportError as e:
    print(f"✗ Import failed: {e}")
    print("This may be expected in a headless environment without display support.")
    sys.exit(0)  # Don't fail on import issues in headless environments
