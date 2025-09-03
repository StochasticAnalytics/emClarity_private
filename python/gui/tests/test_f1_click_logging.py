#!/usr/bin/env python3
"""
Test the new F1 toggle click logging system.
"""

import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QPushButton,
                               QVBoxLayout, QWidget)

# Add GUI module to path
sys.path.insert(0, "/sa_shared/git/emClarity/gui")

try:
    from debug_instrumentation import (get_latest_click_data,
                                       init_rubber_band_debug,
                                       is_click_logging_enabled,
                                       setup_click_logging_shortcut,
                                       toggle_click_logging)

    class TestWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Test F1 Click Logging")
            self.setGeometry(100, 100, 500, 300)

            # Create test widgets
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)

            # Status display
            self.status_label = QLabel("Status: Click logging disabled")
            layout.addWidget(self.status_label)

            # Test buttons
            btn1 = QPushButton("Test Button 1")
            btn2 = QPushButton("Test Button 2")
            btn3 = QPushButton("Test Button 3")

            layout.addWidget(btn1)
            layout.addWidget(btn2)
            layout.addWidget(btn3)

            # Instructions
            instructions = QLabel(
                """
Instructions:
1. Press F1 to toggle click logging
2. Click on buttons to test logging
3. Watch console for logged clicks
            """
            )
            layout.addWidget(instructions)

            # Initialize debug system
            init_rubber_band_debug(enabled=True)

            # Setup F1 shortcut
            setup_click_logging_shortcut(self)

            # Update status periodically
            self.timer = QTimer()
            self.timer.timeout.connect(self.update_status)
            self.timer.start(500)  # Update every 500ms

            print("🧪 Test Window Created")
            print("📝 Press F1 to toggle click logging")
            print("📝 Click on buttons to test")

        def update_status(self):
            """Update the status label."""
            enabled = is_click_logging_enabled()
            status = "ENABLED" if enabled else "DISABLED"
            self.status_label.setText(f"Status: Click logging {status}")

            # Show recent click data
            click_data = get_latest_click_data()
            if click_data and len(click_data) > 0:
                last_click = click_data[-1]
                widget_info = f"{last_click.get('widget_class', 'Unknown')} '{last_click.get('widget_text', '')}'"
                print(f"🎯 Last logged click: {widget_info}")

    def run_test():
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        window = TestWindow()
        window.show()

        print("\n✅ Test window opened")
        print("🔑 Press F1 to toggle click logging")
        print("🖱️ Click buttons to test logging")

        return app.exec()

    if __name__ == "__main__":
        run_test()

except Exception as e:
    print(f"❌ Test failed: {e}")
    print(f"📍 Error type: {type(e).__name__}")
    import traceback

    traceback.print_exc()
