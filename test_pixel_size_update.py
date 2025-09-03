#!/usr/bin/env python3
"""Test script for pixel size update functionality."""

import sys
import os
import sqlite3

# Add the gui directory to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'gui'))

def test_pixel_size_database_operations():
    """Test pixel size database operations."""
    print("Testing pixel size database operations...")
    
    db_path = "gui/emclarity_gui_state.db"
    
    # Test 1: Check current state
    print("\n1. Checking current pixel sizes...")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT asset_name, pixel_size FROM tilt_series_assets WHERE asset_name LIKE '%Position_5%' OR asset_name LIKE '%Position_43%';")
        results = cursor.fetchall()
        for asset_name, pixel_size in results:
            print(f"  {asset_name}: {pixel_size}")
    
    # Test 2: Update some pixel sizes
    print("\n2. Updating pixel sizes...")
    test_pixel_size = 1.2345
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tilt_series_assets SET pixel_size = ? WHERE asset_name LIKE '%Position_5%' OR asset_name LIKE '%Position_43%';", (test_pixel_size,))
        conn.commit()
        print(f"  Updated pixel size to {test_pixel_size}")
    
    # Test 3: Verify the updates
    print("\n3. Verifying updates...")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT asset_name, pixel_size FROM tilt_series_assets WHERE asset_name LIKE '%Position_5%' OR asset_name LIKE '%Position_43%';")
        results = cursor.fetchall()
        for asset_name, pixel_size in results:
            print(f"  {asset_name}: {pixel_size}")
            if pixel_size == test_pixel_size:
                print(f"    ✅ Successfully updated!")
            else:
                print(f"    ❌ Update failed!")
    
    print("\n4. Testing GUI state manager integration...")
    try:
        from state_manager import GUIStateManager
        
        # Initialize state manager
        state_manager = GUIStateManager()
        
        # Load assets
        assets = state_manager.load_tilt_series_assets()
        print(f"  Loaded {len(assets)} assets from database")
        
        # Find test assets
        test_assets = {k: v for k, v in assets.items() if 'Position_5' in k or 'Position_43' in k}
        print(f"  Found {len(test_assets)} test assets")
        
        for asset_name, asset_data in test_assets.items():
            pixel_size = asset_data.get('pixel_size')
            print(f"    {asset_name}: pixel_size = {pixel_size}")
            if pixel_size == test_pixel_size:
                print(f"      ✅ State manager correctly loaded pixel size!")
            else:
                print(f"      ❌ State manager failed to load pixel size!")
                
    except ImportError as e:
        print(f"  ❌ Could not import state_manager: {e}")
    except Exception as e:
        print(f"  ❌ Error testing state manager: {e}")
        
    print("\n✅ Pixel size database testing complete!")

if __name__ == "__main__":
    test_pixel_size_database_operations()
