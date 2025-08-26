"""
Configuration and environment setup for emClarity GUI.

This module handles the environment variable setup that mirrors
the MATLAB version's functionality.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


class EmClarityConfig:
    """Configuration class for emClarity environment setup."""
    
    def __init__(self, emclarity_root: Optional[str] = None):
        """Initialize emClarity configuration.
        
        Args:
            emclarity_root: Path to emClarity root directory. If None, attempts to detect automatically.
        """
        self.emclarity_root = self._determine_emclarity_root(emclarity_root)
        self.setup_environment()
    
    def _determine_emclarity_root(self, provided_root: Optional[str]) -> str:
        """Determine the emClarity root directory.
        
        Args:
            provided_root: User-provided root path
            
        Returns:
            Path to emClarity root directory
            
        Raises:
            ValueError: If emClarity root cannot be determined
        """
        if provided_root:
            root_path = Path(provided_root)
            if root_path.exists():
                return str(root_path.absolute())
            else:
                raise ValueError(f"Provided emClarity root does not exist: {provided_root}")
        
        # Try environment variable
        env_root = os.getenv('emClarity_ROOT')
        if env_root:
            root_path = Path(env_root)
            if root_path.exists():
                return str(root_path.absolute())
        
        # Try to detect from current script location
        current_file = Path(__file__).absolute()
        # Assume we're in gui/ subdirectory of emClarity
        potential_root = current_file.parent.parent
        if (potential_root / 'testScripts' / 'emClarity.m').exists():
            return str(potential_root)
        
        raise ValueError(
            "Cannot determine emClarity root directory. "
            "Please set emClarity_ROOT environment variable or provide the path explicitly."
        )
    
    def setup_environment(self) -> None:
        """Setup environment variables required by emClarity."""
        # Set emClarity_ROOT
        os.environ['emClarity_ROOT'] = self.emclarity_root
        
        # Set MATLAB_SHELL
        os.environ['MATLAB_SHELL'] = '/bin/bash'
        
        # Setup paths for binaries and dependencies
        emclarity_path = Path(self.emclarity_root)
        
        # Setup alignment tool paths
        alignment_path = emclarity_path / 'alignment'
        os.environ['EMC_AUTOALIGN'] = str(alignment_path / 'emC_autoAlign')
        os.environ['EMC_FINDBEADS'] = str(alignment_path / 'emC_findBeads')
        
        # Setup metadata path
        metadata_path = emclarity_path / 'metaData'
        os.environ['BH_CHECKINSTALL'] = str(metadata_path / 'BH_checkInstall')
        
        # Setup cisTEM dependencies
        deps_path = emclarity_path / 'bin' / 'deps'
        cistem_deps_file = deps_path / 'cisTEMDeps.txt'
        
        if cistem_deps_file.exists():
            try:
                with open(cistem_deps_file, 'r') as f:
                    deps = [line.strip() for line in f if line.strip()]
                
                for dep in deps:
                    env_var = f'EMC_{dep.upper()}'
                    dep_path = deps_path / f'emC_{dep}'
                    os.environ[env_var] = str(dep_path)
            except IOError:
                print(f"Warning: Could not read cisTEM dependencies file: {cistem_deps_file}")
    
    def get_available_binaries(self) -> List[str]:
        """Get list of available emClarity binaries.
        
        Returns:
            List of available binary names
        """
        bin_path = Path(self.emclarity_root) / 'bin'
        if not bin_path.exists():
            return []
        
        binaries = []
        for item in bin_path.iterdir():
            if item.is_file() and item.name.startswith('emClarity_'):
                binaries.append(item.name)
        
        return sorted(binaries)
    
    def get_latest_binary(self) -> Optional[str]:
        """Get the latest version of emClarity binary.
        
        Returns:
            Path to the latest binary, or None if not found
        """
        binaries = self.get_available_binaries()
        if not binaries:
            return None
        
        # Return the last one when sorted (should be latest version)
        latest_binary = binaries[-1]
        bin_path = Path(self.emclarity_root) / 'bin' / latest_binary
        return str(bin_path)
    
    def get_version_info(self) -> Dict[str, str]:
        """Get detailed version information.
        
        Returns:
            Dictionary with version details
        """
        latest_binary = self.get_latest_binary()
        if not latest_binary:
            return {
                'version': 'Unknown',
                'binary': 'Not found',
                'root': self.emclarity_root
            }
        
        # Extract version from binary name
        binary_name = Path(latest_binary).name
        if binary_name.startswith('emClarity_'):
            version_part = binary_name.replace('emClarity_', '')
            # Clean up version string
            version = version_part.replace('_', '.')
        else:
            version = 'Unknown'
        
        return {
            'version': version,
            'binary': binary_name,
            'root': self.emclarity_root,
            'full_path': latest_binary
        }
    
    def create_logfile_directory(self) -> None:
        """Create logfile directory if it doesn't exist."""
        log_dir = Path.cwd() / 'logFile'
        log_dir.mkdir(exist_ok=True)
    
    def get_environment_info(self) -> Dict[str, str]:
        """Get current environment configuration.
        
        Returns:
            Dictionary of environment variables and paths
        """
        return {
            'emClarity_ROOT': self.emclarity_root,
            'Available Binaries': ', '.join(self.get_available_binaries()),
            'Latest Binary': self.get_latest_binary() or 'None found',
            'EMC_AUTOALIGN': os.getenv('EMC_AUTOALIGN', 'Not set'),
            'EMC_FINDBEADS': os.getenv('EMC_FINDBEADS', 'Not set'),
            'BH_CHECKINSTALL': os.getenv('BH_CHECKINSTALL', 'Not set'),
        }


def get_default_config() -> EmClarityConfig:
    """Get default emClarity configuration.
    
    Returns:
        Configured EmClarityConfig instance
    """
    return EmClarityConfig()
