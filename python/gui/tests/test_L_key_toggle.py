#!/usr/bin/env python3
"""
Test L key toggle functionality for click logging
"""

import sys
import os

# Add GUI module to path
sys.path.insert(0, '/sa_shared/git/emClarity/gui')

try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence
    
    from debug_instrumentation import (
        setup_click_logging_shortcut, 
        toggle_click_logging, 
        _CLICK_LOGGING_ENABLED,
        install_global_event_filter,
        _RUBBER_BAND_MODE,
        _QT_AVAILABLE
    )
    
    # Set rubber band mode for testing
    import debug_instrumentation
    debug_instrumentation._RUBBER_BAND_MODE = True
    
    class TestLKeyWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Test L Key Click Logging Toggle")
            self.setGeometry(100, 100, 400, 300)
            
            # Create test widgets
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)
            
            self.status_label = QLabel("Click Logging: DISABLED")
            layout.addWidget(self.status_label)
            
            self.test_button = QPushButton("Test Button - Click me after pressing L")
            layout.addWidget(self.test_button)
            
            # Install global event filter
            install_global_event_filter(QApplication.instance())
            
            # Setup L key shortcut
            self.shortcut = setup_click_logging_shortcut(self)
            
            print("🧪 Test L Key Window Created")
            print(f"🔍 Rubber band mode: {_RUBBER_BAND_MODE}")
            print(f"🔍 Qt available: {_QT_AVAILABLE}")
            print("📝 Instructions:")
            print("   1. Press L to toggle click logging on/off")
            print("   2. Click the test button to see if logging works")
            print("   3. Press L again to toggle off")
            
            # Track toggle status
            self.update_status()
    
        def update_status(self):
            status = "ENABLED" if debug_instrumentation._CLICK_LOGGING_ENABLED else "DISABLED"
            self.status_label.setText(f"Click Logging: {status}")
            print(f"🎯 Click logging status: {status}")
    
        def keyPressEvent(self, event):
            if event.key() == Qt.Key_L:
                print("🔑 L key pressed - toggling...")
                toggle_result = toggle_click_logging()
                self.update_status()
                return
            super().keyPressEvent(event)
    
    def run_test():
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        window = TestLKeyWindow()
        window.show()
        
        print("\n✅ L Key Test window opened")
        print("🔑 Press L to toggle click logging")
        print("🖱️ Then click the test button to verify logging works")
        
        return app.exec()

    if __name__ == "__main__":
        run_test()
        
except Exception as e:
    print(f"❌ Test failed: {e}")
    print(f"📍 Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()
