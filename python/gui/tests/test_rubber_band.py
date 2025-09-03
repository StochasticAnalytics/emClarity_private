#!/usr/bin/env python3
"""
Test script for the rubber band tool
"""

import os
import sys
from pathlib import Path

# Add gui directory to path
gui_dir = Path(__file__).parent.absolute()
if str(gui_dir) not in sys.path:
    sys.path.insert(0, str(gui_dir))

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    from rubber_band_tool import create_rubber_band_tool

    class TestWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Rubber Band Tool Test")
            self.setGeometry(100, 100, 800, 600)

            layout = QVBoxLayout()

            title = QLabel("Rubber Band Tool Test Window")
            title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 20px;")
            layout.addWidget(title)

            description = QLabel(
                "This window tests the rubber band selection tool.\n\n"
                "Instructions:\n"
                "1. Press ESC to activate the rubber band tool\n"
                "2. Hold Ctrl and click+drag to create a selection\n"
                "3. Release to open the prompt dialog\n"
                "4. Edit the prompt and save to file\n"
                "5. Right-click to cancel a selection\n"
                "6. Press ESC again to toggle the tool on/off"
            )
            description.setStyleSheet("font-size: 14px; padding: 20px;")
            layout.addWidget(description)

            self.status_label = QLabel(
                "Status: Tool ready. Press ESC to activate rubber band selection."
            )
            self.status_label.setStyleSheet(
                "font-size: 12px; color: blue; padding: 10px;"
            )
            layout.addWidget(self.status_label)

            # Test button
            test_button = QPushButton("Test Button - Try selecting this!")
            test_button.setStyleSheet(
                "padding: 15px; font-size: 16px; background-color: #4CAF50; color: white;"
            )
            layout.addWidget(test_button)

            self.setLayout(layout)

            # Initialize rubber band tool
            self.rubber_band_tool = create_rubber_band_tool(self)

            # Setup keyboard shortcut but don't auto-activate
            self.rubber_band_tool.setup_keyboard_shortcut()

            # Don't auto-activate - wait for ESC key press
            # QTimer.singleShot(2000, self.activate_tool)

        # Remove the old activate_tool method since we're not using it
        # def activate_tool(self):
        #     self.rubber_band_tool.activate()
        #     self.status_label.setText("Status: 🎯 Rubber Band Tool ACTIVE! Use Ctrl+Click+Drag to select, ESC to toggle.")
        #     self.status_label.setStyleSheet("font-size: 12px; color: green; padding: 10px;")

    def main():
        app = QApplication(sys.argv)

        window = TestWindow()
        window.show()

        print("Rubber Band Tool Test Started")
        print("Use Ctrl+Click+Drag in the test window to make selections")

        sys.exit(app.exec())

    if __name__ == "__main__":
        main()

except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure PySide6 is installed: pip install PySide6")
    sys.exit(1)
