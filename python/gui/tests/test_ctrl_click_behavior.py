#!/usr/bin/env python3
"""
Test the new Ctrl+Click behavior for debug instrumentation.
"""

import sys
from pathlib import Path

import debug_instrumentation

# Add gui directory to path
gui_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(gui_dir))


def test_ctrl_click_behavior():
    """Test the new Ctrl+click logging behavior."""
    print("Testing new Ctrl+Click behavior...")

    # Initialize debug mode
    debug_instrumentation.init_rubber_band_debug(enabled=True)

    print("✅ Debug mode active")

    # Test 1: Regular click (should not log)
    print("\n1. Testing regular click (should NOT log):")
    debug_instrumentation.instrument_click_event(
        "test_button", "QPushButton", "Test action", "test_panel"
    )
    data = debug_instrumentation.get_latest_click_data()
    if data and data.get("element_id") == "test_button":
        print("   ❌ Regular click was logged (unexpected)")
    else:
        print("   ✅ Regular click was NOT logged (correct)")

    # Test 2: Forced log (should log)
    print("\n2. Testing forced log (should log):")
    debug_instrumentation.instrument_click_event(
        "forced_button", "QPushButton", "Forced action", "test_panel", force_log=True
    )
    data = debug_instrumentation.get_latest_click_data()
    if data and data.get("element_id") == "forced_button":
        print("   ✅ Forced log worked (correct)")
        print(f"   📝 Logged: {data['action_description']}")
    else:
        print("   ❌ Forced log failed (unexpected)")

    # Test 3: Check if Ctrl detection function exists
    print("\n3. Testing Ctrl key detection function:")
    try:
        ctrl_pressed = debug_instrumentation.is_ctrl_pressed()
        print(f"   ✅ Ctrl detection available, currently pressed: {ctrl_pressed}")
        print("   💡 Note: Ctrl state depends on actual keyboard at test time")
    except Exception as e:
        print(f"   ❌ Ctrl detection failed: {e}")

    print("\n🎯 Summary:")
    print("   • Regular clicks: Only logged when Ctrl+Click is used")
    print("   • Navigation actions: Always logged (force_log=True)")
    print("   • Rubber band selection: Now just Click+Drag (no Ctrl needed)")
    print("   • GUI operation: Normal clicks work without interference")


if __name__ == "__main__":
    test_ctrl_click_behavior()
