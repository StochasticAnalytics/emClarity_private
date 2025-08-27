#!/usr/bin/env python3
"""
Standalone test for the Assets panel.
Run this to see just the Assets panel in isolation.
"""

import sys
from pathlib import Path

# Add gui directory to path
gui_dir = Path(__file__).parent
if str(gui_dir) not in sys.path:
    sys.path.insert(0, str(gui_dir))

from PySide6.QtWidgets import QApplication
from assets_panel import AssetsPanel

def main():
    app = QApplication(sys.argv)
    
    # Create and show Assets panel
    panel = AssetsPanel()
    panel.setWindowTitle("emClarity - Assets Panel Test")
    panel.resize(1200, 800)
    panel.show()
    
    print("Assets Panel Features:")
    print("- Asset type toolbar with 7 asset types (Movies, Images, etc.)")
    print("- Groups panel on the left for organizing assets")
    print("- Main data table with sortable columns")
    print("- Action buttons for asset management")
    print("- Details panel showing selected asset information")
    print("\nTry:")
    print("- Clicking different asset type buttons in the toolbar")
    print("- Selecting different groups in the left panel")
    print("- Clicking on different rows in the table")
    print("- Clicking the action buttons (they show stub messages)")
    
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
