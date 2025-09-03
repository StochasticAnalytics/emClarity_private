#!/usr/bin/env python3
"""
Test QT_AVAILABLE in debug_instrumentation
"""

import sys
sys.path.insert(0, '/sa_shared/git/emClarity/gui')

try:
    import debug_instrumentation
    print(f"QT_AVAILABLE = {debug_instrumentation.QT_AVAILABLE}")
    print(f"_RUBBER_BAND_MODE = {debug_instrumentation._RUBBER_BAND_MODE}")
    print(f"_CLICK_LOGGING_ENABLED = {debug_instrumentation._CLICK_LOGGING_ENABLED}")
    print(f"_DEBUG_DATA_FILE = {debug_instrumentation._DEBUG_DATA_FILE}")
    print(f"_CLICK_FILTER = {debug_instrumentation._CLICK_FILTER}")
    
    # Test PySide6 import directly
    try:
        from PySide6.QtCore import QObject, QEvent, Qt
        from PySide6.QtWidgets import QApplication
        print("✅ PySide6 imports work directly")
    except ImportError as e:
        print(f"❌ PySide6 import error: {e}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
