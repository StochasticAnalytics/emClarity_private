#!/usr/bin/env python3
"""
Standalone test for the Assets panel.
Run this to see just the Assets panel in isolation.
"""

import sys
from pathlib import Path

# Add the python package root to path for proper imports
python_root = Path(__file__).parent.parent.parent
if str(python_root) not in sys.path:
    sys.path.insert(0, str(python_root))

from gui.assets_panel import AssetsPanel
from PySide6.QtWidgets import QApplication


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
