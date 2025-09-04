#!/usr/bin/env python3
"""
Test F1 toggle functionality for click logging
"""

import sys

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Add GUI module to path
sys.path.insert(0, "/sa_shared/git/emClarity/gui")

try:
    from debug_instrumentation import (
        init_rubber_band_debug,
        is_click_logging_enabled,
        setup_click_logging_shortcut,
        toggle_click_logging,
    )

    class TestF1Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Test F1 Click Logging Toggle")
            self.setGeometry(100, 100, 400, 300)

            # Create test widgets
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)

            self.status_label = QLabel("Click Logging: UNKNOWN")
            layout.addWidget(self.status_label)

            self.test_button = QPushButton("Test Button")
            layout.addWidget(self.test_button)

            check_button = QPushButton("Check Logging Status")
            check_button.clicked.connect(self.check_status)
            layout.addWidget(check_button)

            manual_toggle = QPushButton("Manual Toggle (for testing)")
            manual_toggle.clicked.connect(self.manual_toggle)
            layout.addWidget(manual_toggle)

            # Initialize debug instrumentation
            init_rubber_band_debug(enabled=True)

            # Setup F1 shortcut
            setup_click_logging_shortcut(self)

            # Update initial status
            self.check_status()

            print("🧪 Test F1 Window Created")
            print("📝 Instructions:")
            print("   1. Press F1 to toggle click logging on/off")
            print("   2. Click 'Check Logging Status' to verify state")
            print("   3. Click 'Test Button' to generate click events")
            print("   4. Check /tmp/emclarity_gui_debug/ for debug files")

        def check_status(self):
            enabled = is_click_logging_enabled()
            status = "ENABLED" if enabled else "DISABLED"
            self.status_label.setText(f"Click Logging: {status}")
            print(f"📊 Current click logging status: {status}")

        def manual_toggle(self):
            toggle_click_logging()
            self.check_status()

    def run_test():
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        window = TestF1Window()
        window.show()

        print("\n✅ F1 Test window opened")
        print("🔑 Press F1 to toggle click logging")

        return app.exec()

    if __name__ == "__main__":
        run_test()

except Exception as e:
    print(f"❌ Test failed: {e}")
    print(f"📍 Error type: {type(e).__name__}")
    import traceback

    traceback.print_exc()
