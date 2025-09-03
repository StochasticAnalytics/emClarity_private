#!/usr/bin/env python3
"""Test script to simulate pixel size update functionality."""

import sys
import os
import sqlite3

# Add the gui directory to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'gui'))

def test_pixel_size_update_simulation():
    """Simulate the pixel size update process."""
    print("🧪 Testing Pixel Size Update Functionality...")
    
    db_path = "gui/emclarity_gui_state.db"
    
    # Simulate the update_pixel_size_selected workflow
    print("\n1. Simulating user input validation...")
    test_pixel_size = "2.468"  # Simulate user input
    
    # Test input validation
    try:
        pixel_size = float(test_pixel_size.strip())
        if pixel_size <= 0:
            raise ValueError("Pixel size must be positive")
        print(f"   ✅ Valid pixel size: {pixel_size}")
    except ValueError as e:
        print(f"   ❌ Invalid input: {e}")
        return
    
    # Simulate asset selection
    print("\n2. Simulating asset selection...")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT asset_name FROM tilt_series_assets LIMIT 3;")
        selected_assets = cursor.fetchall()
        print(f"   Selected {len(selected_assets)} assets for testing:")
        for asset_name, in selected_assets:
            print(f"     - {asset_name}")
    
    # Simulate updating pixel sizes
    print("\n3. Simulating pixel size update...")
    updated_count = 0
    asset_names = [asset[0] for asset in selected_assets]
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for asset_name in asset_names:
            # Update in database (simulating the save_assets process)
            cursor.execute("UPDATE tilt_series_assets SET pixel_size = ? WHERE asset_name = ?", 
                         (pixel_size, asset_name))
            updated_count += 1
            print(f"   ✅ Updated pixel size for {asset_name}: {pixel_size}")
        conn.commit()
    
    # Verify the updates
    print("\n4. Verifying updates...")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for asset_name in asset_names:
            cursor.execute("SELECT pixel_size FROM tilt_series_assets WHERE asset_name = ?", (asset_name,))
            result = cursor.fetchone()
            if result and result[0] == pixel_size:
                print(f"   ✅ {asset_name}: {result[0]} (verified)")
            else:
                print(f"   ❌ {asset_name}: Update failed")
    
    # Test state manager loading
    print("\n5. Testing state manager integration...")
    try:
        from state_manager import GUIStateManager
        state_manager = GUIStateManager()
        assets = state_manager.load_tilt_series_assets()
        
        for asset_name in asset_names:
            if asset_name in assets:
                loaded_pixel_size = assets[asset_name].get('pixel_size')
                if loaded_pixel_size == pixel_size:
                    print(f"   ✅ State manager loaded correct pixel size for {asset_name}")
                else:
                    print(f"   ❌ State manager failed to load pixel size for {asset_name}")
            else:
                print(f"   ❌ Asset {asset_name} not found in loaded assets")
                
    except Exception as e:
        print(f"   ❌ State manager test failed: {e}")
    
    print(f"\n✅ Pixel size update simulation complete!")
    print(f"   Updated {updated_count} assets to pixel size {pixel_size}")
    
    # Show current pixel size distribution
    print("\n📊 Current pixel size distribution:")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT pixel_size, COUNT(*) FROM tilt_series_assets WHERE pixel_size IS NOT NULL GROUP BY pixel_size ORDER BY pixel_size;")
        distribution = cursor.fetchall()
        for pixel_size_val, count in distribution:
            print(f"   {pixel_size_val}: {count} assets")

if __name__ == "__main__":
    test_pixel_size_update_simulation()
