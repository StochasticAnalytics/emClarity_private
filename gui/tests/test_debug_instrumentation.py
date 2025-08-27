#!/usr/bin/env python3
"""
Test script for debug instrumentation system.
"""

import sys
import os
from pathlib import Path

# Add gui directory to path
gui_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(gui_dir))

import debug_instrumentation

def test_debug_instrumentation():
    """Test the debug instrumentation system."""
    print("Testing debug instrumentation...")
    
    # Initialize debug mode
    debug_instrumentation.init_rubber_band_debug(enabled=True)
    
    # Test if active
    print(f"Debug active: {debug_instrumentation.is_rubber_band_debug_active()}")
    
    # Test click instrumentation
    debug_instrumentation.instrument_click_event(
        element_id="test_button",
        element_type="QPushButton",
        action_description="Test button click",
        panel_context="test_panel",
        additional_data={"test": True, "value": 42}
    )
    
    # Get the data back
    click_data = debug_instrumentation.get_latest_click_data()
    print(f"Click data captured: {click_data}")
    
    # Test decorator
    @debug_instrumentation.instrument_click(
        "decorated_test", "TestMethod", "Test decorated method", "test"
    )
    def test_method():
        return "decorated method called"
    
    result = test_method()
    print(f"Decorated method result: {result}")
    
    # Get updated data
    updated_data = debug_instrumentation.get_latest_click_data()
    print(f"Updated click data: {updated_data}")
    
    print("Debug instrumentation test completed!")

if __name__ == "__main__":
    test_debug_instrumentation()
