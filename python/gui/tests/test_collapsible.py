#!/usr/bin/env python3
"""
Test script for collapsible panels functionality.
"""

import os
import sys

from main import EmClarityWindow
from PySide6.QtWidgets import QApplication

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def main():
    """Test the collapsible functionality."""
    app = QApplication(sys.argv)

    # Create window
    window = EmClarityWindow()
    window.show()

    print("GUI launched successfully!")
    print("Features to test:")
    print("1. Collapsible command panels (click the ▶/▼ arrows)")
    print("2. State persistence (expand/collapse panels, then restart)")
    print("3. Parameter configuration in right panel")
    print("4. Keep on Top toggle")
    print("5. Font size changes in View menu")

    # Run for 5 seconds then close
    import threading
    import time

    def auto_close():
        time.sleep(5)
        window.close()
        app.quit()

    # Start auto-close timer
    threading.Thread(target=auto_close, daemon=True).start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
