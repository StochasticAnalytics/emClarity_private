#!/usr/bin/env python3
"""
Test script to verify all clickable elements in the overview panel are instrumented.
"""

import sys
import os
from pathlib import Path

# Add gui directory to path
gui_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(gui_dir))

import debug_instrumentation

def test_overview_panel_instrumentation():
    """Test that we can simulate all overview panel click events."""
    print("Testing Overview Panel Click Instrumentation...")
    
    # Initialize debug mode
    debug_instrumentation.init_rubber_band_debug(enabled=True)
    
    # Test all the clickable elements that should be instrumented in overview panel
    test_clicks = [
        {
            "element_id": "new_project_link",
            "element_type": "QLabel",
            "action_description": "Create new project",
            "panel_context": "overview",
            "additional_data": {"link_target": "new", "link_text": "Create a new project"}
        },
        {
            "element_id": "open_project_link", 
            "element_type": "QLabel",
            "action_description": "Open existing project",
            "panel_context": "overview",
            "additional_data": {"link_target": "open", "link_text": "Open an existing project"}
        },
        {
            "element_id": "browse_project_link",
            "element_type": "QLabel", 
            "action_description": "Browse for existing project",
            "panel_context": "overview",
            "additional_data": {"link_target": "browse", "link_text": "Browse for project..."}
        },
        {
            "element_id": "recent_project_test_project",
            "element_type": "QLabel",
            "action_description": "Open recent project: Test Project", 
            "panel_context": "overview",
            "additional_data": {
                "project_name": "Test Project",
                "project_path": "/path/to/test/project",
                "link_type": "recent_project"
            }
        }
    ]
    
    print(f"Testing {len(test_clicks)} clickable elements...")
    
    for i, click_data in enumerate(test_clicks, 1):
        print(f"\n{i}. Testing: {click_data['element_id']}")
        
        # Simulate the click
        debug_instrumentation.instrument_click_event(**click_data)
        
        # Verify the data was captured
        captured_data = debug_instrumentation.get_latest_click_data()
        
        if captured_data and captured_data['element_id'] == click_data['element_id']:
            print(f"   ✅ Successfully captured: {click_data['action_description']}")
            print(f"   📝 Data: {captured_data['element_type']} in {captured_data['panel_context']} panel")
        else:
            print(f"   ❌ Failed to capture click data for {click_data['element_id']}")
    
    print(f"\n🎯 Overview Panel Instrumentation Test Complete!")
    print(f"📋 All major clickable elements in overview panel should be instrumented:")
    print(f"   • Create new project link")
    print(f"   • Open existing project link") 
    print(f"   • Browse for project link")
    print(f"   • Recent project links (dynamic)")
    print(f"   • Sidebar navigation buttons (via switch_panel)")

if __name__ == "__main__":
    test_overview_panel_instrumentation()
