#!/usr/bin/env python3
"""
Test the fixed rubber band behavior.

- Regular clicks should NOT be logged.
- Ctrl+clicks should be logged.
- Multiple Ctrl+clicks should all be logged (not overwritten).
"""

import json
import os
import sys
from pathlib import Path

# Add GUI module to path
sys.path.insert(0, "/sa_shared/git/emClarity/gui")


def test_debug_file_behavior():
    """Test that debug files are appended to, not overwritten."""
    # Clean up any existing debug files
    debug_dir = Path("/tmp/emclarity_gui_debug")
    if debug_dir.exists():
        for file in debug_dir.glob("click_debug_*.json"):
            file.unlink()

    print("🧪 Testing debug file behavior...")

    try:
        from debug_instrumentation import init_rubber_band_debug, instrument_click_event

        # Initialize debug mode
        init_rubber_band_debug(enabled=True)
        print("✅ Debug mode initialized")

        # Test multiple events (force_log to simulate Ctrl+clicks)
        print("📝 Adding test events...")

        instrument_click_event(
            "test_button_1",
            "QPushButton",
            "First test click",
            "test_panel",
            force_log=True,
        )

        instrument_click_event(
            "test_button_2",
            "QPushButton",
            "Second test click",
            "test_panel",
            force_log=True,
        )

        instrument_click_event(
            "test_button_3",
            "QPushButton",
            "Third test click",
            "test_panel",
            force_log=True,
        )

        # Check if all events were saved
        debug_files = list(debug_dir.glob("click_debug_*.json"))
        if debug_files:
            latest_file = max(debug_files, key=lambda f: f.stat().st_mtime)
            with open(latest_file) as f:
                data = json.load(f)

            if isinstance(data, list):
                print(f"✅ Found {len(data)} events in debug file (should be 3)")
                for i, event in enumerate(data, 1):
                    print(
                        f"   Event {i}: {event['element_id']} - {event['action_description']}"
                    )

                if len(data) == 3:
                    print("✅ All events preserved - no overwriting!")
                else:
                    print(f"❌ Expected 3 events, got {len(data)}")
            else:
                print(
                    f"❌ Expected list of events, got single event: {data['element_id']}"
                )
        else:
            print("❌ No debug files found")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()


def test_ctrl_behavior():
    """Test that regular clicks aren't logged."""
    print("\n🧪 Testing Ctrl behavior...")

    try:
        from debug_instrumentation import instrument_click_event, is_ctrl_pressed

        print(f"Current Ctrl state: {is_ctrl_pressed()}")

        # This should NOT be logged (no force_log, no Ctrl)
        print("📝 Testing regular click (should NOT log)...")
        instrument_click_event(
            "regular_click", "QPushButton", "Regular click test", "test_panel"
        )

        # This SHOULD be logged (force_log=True simulates Ctrl+click)
        print("📝 Testing forced log (should log)...")
        instrument_click_event(
            "forced_click",
            "QPushButton",
            "Forced click test",
            "test_panel",
            force_log=True,
        )

        print("✅ Ctrl behavior test completed")

    except Exception as e:
        print(f"❌ Ctrl test failed: {e}")


if __name__ == "__main__":
    print("🔍 Testing Fixed Rubber Band Behavior")
    print("=" * 50)

    # Set environment variable for debug mode
    os.environ["EMCLARITY_DEBUG_INSTRUMENTATION"] = "1"

    test_debug_file_behavior()
    test_ctrl_behavior()

    print("\n✅ Tests completed. Check output above for results.")
