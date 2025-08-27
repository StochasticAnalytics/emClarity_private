#!/usr/bin/env python3
"""
Simple test to verify L key works in the actual GUI
"""

import sys
import os

# Add GUI module to path
sys.path.insert(0, '/sa_shared/git/emClarity/gui')

try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel
    from PySide6.QtCore import Qt
    
    from debug_instrumentation import setup_click_logging_shortcut, toggle_click_logging
    
    class SimpleTestWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Simple L Key Test")
            self.setGeometry(200, 200, 300, 200)
            
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)
            
            self.label = QLabel("Press L to test toggle")
            layout.addWidget(self.label)
            
            self.button = QPushButton("Test Button")
            layout.addWidget(self.button)
            
            # Try to setup L shortcut
            try:
                # Enable rubber band mode first
                import debug_instrumentation
                debug_instrumentation._RUBBER_BAND_MODE = True
                
                self.shortcut = setup_click_logging_shortcut(self)
                if self.shortcut:
                    print("✅ L key shortcut created successfully")
                else:
                    print("❌ L key shortcut failed to create")
            except Exception as e:
                print(f"❌ Error setting up shortcut: {e}")
    
        def keyPressEvent(self, event):
            print(f"🔑 Key pressed: {event.key()} (L is {Qt.Key_L})")
            if event.key() == Qt.Key_L:
                print("🎯 L key detected - calling toggle directly")
                try:
                    result = toggle_click_logging()
                    print(f"🔄 Toggle result: {result}")
                    self.label.setText(f"Click logging: {'ON' if result else 'OFF'}")
                except Exception as e:
                    print(f"❌ Toggle error: {e}")
            super().keyPressEvent(event)
    
    def run_simple_test():
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        window = SimpleTestWindow()
        window.show()
        
        print("🧪 Simple test window created")
        print("🔑 Press L key to test toggle")
        
        return app.exec()

    if __name__ == "__main__":
        run_simple_test()
        
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
