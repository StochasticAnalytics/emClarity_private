"""
State management for emClarity GUI using SQLite database.
Handles saving and restoring GUI state including window geometry,
tab states, parameter values, and panel expansions.
"""

import sqlite3
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime


class GUIStateManager:
    """Manages GUI state persistence using SQLite database."""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Default to gui directory
            gui_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(gui_dir, 'emclarity_gui_state.db')
        
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Window state table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS window_state (
                    id INTEGER PRIMARY KEY,
                    geometry TEXT,
                    window_state TEXT,
                    font_size INTEGER,
                    keep_on_top BOOLEAN,
                    splitter_sizes TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tab state table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tab_state (
                    id INTEGER PRIMARY KEY,
                    tab_name TEXT UNIQUE,
                    active_tab BOOLEAN,
                    expanded_panels TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Parameter values table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS parameter_values (
                    id INTEGER PRIMARY KEY,
                    tab_name TEXT,
                    parameter_name TEXT,
                    parameter_value TEXT,
                    parameter_type TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tab_name, parameter_name)
                )
            ''')
            
            # Recent projects table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recent_projects (
                    id INTEGER PRIMARY KEY,
                    project_name TEXT,
                    project_path TEXT,
                    parameter_file TEXT,
                    last_opened TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Run profiles table - handle migration from old schema
            cursor.execute("PRAGMA table_info(run_profiles)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'resource_id' not in columns:
                # Old schema detected, migrate
                cursor.execute('DROP TABLE IF EXISTS run_profiles_old')
                cursor.execute('ALTER TABLE run_profiles RENAME TO run_profiles_old')
                
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS run_profiles (
                    id INTEGER PRIMARY KEY,
                    profile_name TEXT,
                    resource_id TEXT,
                    hostname TEXT,
                    username TEXT,
                    gpus INTEGER,
                    status TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(profile_name, resource_id)
                )
            ''')
            
            # Migrate old data if needed
            if 'resource_id' not in columns:
                cursor.execute("SELECT * FROM run_profiles_old")
                old_data = cursor.fetchall()
                for row in old_data:
                    # Convert old format: (id, profile_name, hostname, username, gpus, status, timestamp)
                    profile_name, hostname, username, gpus, status = row[1], row[2], row[3], row[4], row[5]
                    resource_id = f"{hostname}_{username}_0"
                    cursor.execute('''
                        INSERT INTO run_profiles (profile_name, resource_id, hostname, username, gpus, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (profile_name, resource_id, hostname, username, gpus, status))
                cursor.execute('DROP TABLE run_profiles_old')
            
            conn.commit()
    
    def save_window_state(self, geometry: str, window_state: str, 
                         font_size: int, keep_on_top: bool, 
                         splitter_sizes: str):
        """Save window state to database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Delete existing state (keep only one)
            cursor.execute('DELETE FROM window_state')
            
            # Insert new state
            cursor.execute('''
                INSERT INTO window_state 
                (geometry, window_state, font_size, keep_on_top, splitter_sizes)
                VALUES (?, ?, ?, ?, ?)
            ''', (geometry, window_state, font_size, keep_on_top, splitter_sizes))
            
            conn.commit()
    
    def load_window_state(self) -> Optional[Dict[str, Any]]:
        """Load window state from database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT geometry, window_state, font_size, keep_on_top, splitter_sizes
                FROM window_state ORDER BY last_updated DESC LIMIT 1
            ''')
            
            row = cursor.fetchone()
            if row:
                return {
                    'geometry': row[0],
                    'window_state': row[1],
                    'font_size': row[2],
                    'keep_on_top': bool(row[3]),
                    'splitter_sizes': row[4]
                }
        return None
    
    def save_tab_state(self, tab_name: str, active_tab: bool, 
                      expanded_panels: list):
        """Save tab state including expanded panels."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            expanded_json = json.dumps(expanded_panels)
            
            cursor.execute('''
                INSERT OR REPLACE INTO tab_state 
                (tab_name, active_tab, expanded_panels)
                VALUES (?, ?, ?)
            ''', (tab_name, active_tab, expanded_json))
            
            conn.commit()
    
    def load_tab_state(self, tab_name: str) -> Optional[Dict[str, Any]]:
        """Load tab state from database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT active_tab, expanded_panels
                FROM tab_state WHERE tab_name = ?
            ''', (tab_name,))
            
            row = cursor.fetchone()
            if row:
                expanded_panels = json.loads(row[1]) if row[1] else []
                return {
                    'active_tab': bool(row[0]),
                    'expanded_panels': expanded_panels
                }
        return None
    
    def save_parameter_values(self, tab_name: str, parameters: Dict[str, Any]):
        """Save parameter values for a tab."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for param_name, value in parameters.items():
                if value is not None:
                    # Convert value to JSON string for storage
                    if isinstance(value, (list, dict)):
                        value_str = json.dumps(value)
                        param_type = 'json'
                    else:
                        value_str = str(value)
                        param_type = type(value).__name__
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO parameter_values
                        (tab_name, parameter_name, parameter_value, parameter_type)
                        VALUES (?, ?, ?, ?)
                    ''', (tab_name, param_name, value_str, param_type))
            
            conn.commit()
    
    def load_parameter_values(self, tab_name: str) -> Dict[str, Any]:
        """Load parameter values for a tab."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT parameter_name, parameter_value, parameter_type
                FROM parameter_values WHERE tab_name = ?
            ''', (tab_name,))
            
            parameters = {}
            for row in cursor.fetchall():
                param_name, value_str, param_type = row
                
                # Convert back from string based on type
                if param_type == 'json':
                    value = json.loads(value_str)
                elif param_type == 'bool':
                    value = value_str.lower() == 'true'
                elif param_type == 'int':
                    value = int(value_str)
                elif param_type == 'float':
                    value = float(value_str)
                else:
                    value = value_str
                
                parameters[param_name] = value
            
            return parameters
    
    def save_recent_project(self, project_name: str, project_path: str, 
                           parameter_file: str = None):
        """Save a recent project."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Remove existing entry for this project
            cursor.execute('''
                DELETE FROM recent_projects WHERE project_name = ? OR project_path = ?
            ''', (project_name, project_path))
            
            # Insert new entry
            cursor.execute('''
                INSERT INTO recent_projects 
                (project_name, project_path, parameter_file)
                VALUES (?, ?, ?)
            ''', (project_name, project_path, parameter_file))
            
            # Keep only last 10 projects
            cursor.execute('''
                DELETE FROM recent_projects WHERE id NOT IN (
                    SELECT id FROM recent_projects 
                    ORDER BY last_opened DESC LIMIT 10
                )
            ''')
            
            conn.commit()
    
    def get_recent_projects(self, limit: int = 10) -> list:
        """Get recent projects list."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT project_name, project_path, parameter_file, last_opened
                FROM recent_projects 
                ORDER BY last_opened DESC LIMIT ?
            ''', (limit,))
            
            return [
                {
                    'name': row[0],
                    'path': row[1],
                    'parameter_file': row[2],
                    'last_opened': row[3]
                }
                for row in cursor.fetchall()
            ]
    
    def clear_all_state(self):
        """Clear all saved state (useful for reset)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM window_state')
            cursor.execute('DELETE FROM tab_state')
            cursor.execute('DELETE FROM parameter_values')
            cursor.execute('DELETE FROM recent_projects')
            cursor.execute('DELETE FROM run_profiles')
            conn.commit()
    
    def export_state(self, export_path: str):
        """Export current state to a file."""
        state = {
            'window_state': self.load_window_state(),
            'tabs': {},
            'parameters': {},
            'recent_projects': self.get_recent_projects()
        }
        
        # Load all tab states and parameters
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get all tabs
            cursor.execute('SELECT DISTINCT tab_name FROM tab_state')
            for (tab_name,) in cursor.fetchall():
                state['tabs'][tab_name] = self.load_tab_state(tab_name)
                state['parameters'][tab_name] = self.load_parameter_values(tab_name)
        
        with open(export_path, 'w') as f:
            json.dump(state, f, indent=2, default=str)
    
    def import_state(self, import_path: str):
        """Import state from a file."""
        with open(import_path, 'r') as f:
            state = json.load(f)
        
        # Clear existing state
        self.clear_all_state()
        
        # Import window state
        if state.get('window_state'):
            ws = state['window_state']
            self.save_window_state(
                ws.get('geometry', ''),
                ws.get('window_state', ''),
                ws.get('font_size', 10),
                ws.get('keep_on_top', False),
                ws.get('splitter_sizes', '')
            )
        
        # Import tab states and parameters
        for tab_name, tab_state in state.get('tabs', {}).items():
            self.save_tab_state(
                tab_name,
                tab_state.get('active_tab', False),
                tab_state.get('expanded_panels', [])
            )
        
        for tab_name, params in state.get('parameters', {}).items():
            self.save_parameter_values(tab_name, params)
        
        # Import recent projects
        for project in state.get('recent_projects', []):
            self.save_recent_project(
                project['name'],
                project['path'],
                project.get('parameter_file')
            )

    def save_run_profiles(self, profiles: Dict[str, List[Dict[str, Any]]]):
        """Save run profiles to the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM run_profiles')
            for profile_name, resources in profiles.items():
                for resource in resources:
                    cursor.execute('''
                        INSERT INTO run_profiles (profile_name, resource_id, hostname, username, gpus, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (profile_name, resource['id'], resource['hostname'], resource['username'], 
                         resource['gpus'], resource.get('status', 'N/A')))
            conn.commit()

    def load_run_profiles(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load run profiles from the database."""
        profiles = {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT profile_name, resource_id, hostname, username, gpus, status FROM run_profiles')
            for row in cursor.fetchall():
                profile_name = row[0]
                if profile_name not in profiles:
                    profiles[profile_name] = []
                profiles[profile_name].append({
                    "id": row[1],
                    "hostname": row[2],
                    "username": row[3],
                    "gpus": row[4],
                    "status": row[5]
                })
        return profiles
    
    def save_tilt_series_assets(self, assets: Dict[str, Dict[str, Any]]):
        """Save tilt-series assets to database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create table if not exists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tilt_series_assets (
                    asset_name TEXT PRIMARY KEY,
                    file_path TEXT,
                    directory TEXT,
                    tilt_file TEXT,
                    status TEXT,
                    metadata TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    pixel_size REAL
                )
            ''')
            
            # Clear existing assets
            cursor.execute('DELETE FROM tilt_series_assets')
            
            # Insert current assets
            for asset_name, asset_data in assets.items():
                cursor.execute('''
                    INSERT INTO tilt_series_assets 
                    (asset_name, file_path, directory, tilt_file, status, metadata, pixel_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    asset_name,
                    asset_data.get('file_path', ''),
                    asset_data.get('directory', ''),
                    asset_data.get('tilt_file', ''),
                    asset_data.get('status', 'Imported'),
                    json.dumps({k: v for k, v in asset_data.items() 
                              if k not in ['file_path', 'directory', 'tilt_file', 'status', 'pixel_size']}),
                    asset_data.get('pixel_size', None)
                ))
            conn.commit()
    
    def load_tilt_series_assets(self) -> Dict[str, Dict[str, Any]]:
        """Load tilt-series assets from database."""
        assets = {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute('''
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='tilt_series_assets'
            ''')
            if not cursor.fetchone():
                return assets
                
            cursor.execute('''
                SELECT asset_name, file_path, directory, tilt_file, status, metadata, pixel_size
                FROM tilt_series_assets
            ''')
            
            for row in cursor.fetchall():
                asset_name = row[0]
                metadata = json.loads(row[5]) if row[5] else {}
                
                assets[asset_name] = {
                    'name': asset_name,
                    'file_path': row[1],
                    'directory': row[2], 
                    'tilt_file': row[3],
                    'status': row[4],
                    'pixel_size': row[6] if row[6] is not None else None,
                    **metadata
                }
        return assets
