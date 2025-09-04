#!/usr/bin/env python3
"""
Test the new rubber band behavior.

- Rubber band selection: just click+drag (no Ctrl).
- Click logging: Ctrl+click only (or forced logs for navigation).
"""

import sys

from PySide6.QtCore import Qt
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
    from debug_instrumentation import instrument_click_event, is_ctrl_pressed
    from rubber_band_tool import RubberBandTool

    class TestWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Test New Rubber Band Behavior")
            self.setGeometry(100, 100, 600, 400)

            # Create test widgets
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)

            self.status_label = QLabel("Status: Ready")
            layout.addWidget(self.status_label)

            # Test button with click instrumentation
            self.test_button = QPushButton("Test Button (with logging)")
            self.test_button.clicked.connect(self.button_clicked)
            layout.addWidget(self.test_button)

            # Regular button
            self.regular_button = QPushButton("Regular Button (no logging)")
            layout.addWidget(self.regular_button)

            # Rubber band tool
            self.rubber_band_tool = RubberBandTool(self)

            print("🧪 Test Window Created")
            print("📝 Instructions:")
            print("   1. Try clicking Test Button normally (should NOT log)")
            print("   2. Try Ctrl+clicking Test Button (should log)")
            print("   3. Press ESC to activate rubber band")
            print("   4. Try click+drag to select area (should work WITHOUT Ctrl)")
            print("   5. Press ESC again to deactivate")

        def button_clicked(self):
            # Test both regular and Ctrl detection
            print(f"\n🔍 Button clicked! Ctrl pressed: {is_ctrl_pressed()}")

            # Only log if Ctrl is pressed
            if is_ctrl_pressed():
                instrument_click_event(
                    element_id="test_button",
                    element_type="QPushButton",
                    action="Test button clicked",
                    panel="test_window",
                )
                self.status_label.setText("Status: Click logged (Ctrl was pressed)")
            else:
                self.status_label.setText("Status: Click NOT logged (Ctrl not pressed)")

        def mousePressEvent(self, event):
            # Test Ctrl detection in mouse events
            if event.button() == Qt.LeftButton:
                print(f"🖱️ Mouse press - Ctrl: {is_ctrl_pressed()}")
            super().mousePressEvent(event)

    def run_test():
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        window = TestWindow()
        window.show()

        print("\n✅ Test window opened. Test the new behavior:")
        print("   • Regular clicks should NOT be logged")
        print("   • Ctrl+clicks should be logged")
        print("   • Rubber band should work with just click+drag (no Ctrl)")

        return app.exec()

    if __name__ == "__main__":
        run_test()

except Exception as e:
    print(f"❌ Test failed: {e}")
    print(f"📍 Error type: {type(e).__name__}")
    import traceback

    traceback.print_exc()
