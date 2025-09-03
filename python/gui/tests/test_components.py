#!/usr/bin/env python3
"""
Test script for emClarity GUI components.

This script tests the configuration and command parsing without the GUI.
"""

import os
import sys
from pathlib import Path

# Add the python package root to path for proper imports
python_root = Path(__file__).parent.parent.parent
if str(python_root) not in sys.path:
    sys.path.insert(0, str(python_root))

from gui.commands import EMCLARITY_COMMANDS, EmClarityCommand
from gui.config import EmClarityConfig, get_default_config


def test_config():
    """Test the configuration setup."""
    print("Testing emClarity configuration...")
    try:
        config = get_default_config()
        print(f"✓ Configuration loaded successfully")
        print(f"  emClarity root: {config.emclarity_root}")

        # Test environment info
        env_info = config.get_environment_info()
        print(f"✓ Environment info retrieved")
        for key, value in env_info.items():
            print(f"  {key}: {value}")

        # Test binary detection
        binaries = config.get_available_binaries()
        print(f"✓ Found {len(binaries)} binaries")

        latest = config.get_latest_binary()
        print(f"  Latest binary: {latest}")

        return True
    except Exception as e:
        print(f"✗ Configuration failed: {e}")
        return False


def test_commands():
    """Test the command definitions."""
    print("\nTesting command definitions...")
    try:
        # Test categories
        categories = EMCLARITY_COMMANDS.get_categories()
        print(f"✓ Found {len(categories)} command categories:")
        for cat in categories:
            commands = EMCLARITY_COMMANDS.get_commands_by_category(cat)
            print(f"  {cat}: {len(commands)} commands")

        # Test specific command
        help_cmd = EMCLARITY_COMMANDS.get_command("help")
        if help_cmd:
            print(f"✓ Help command found: {help_cmd.description}")

        # Test all commands
        all_commands = EMCLARITY_COMMANDS.get_all_commands()
        print(f"✓ Total commands available: {len(all_commands)}")

        return True
    except Exception as e:
        print(f"✗ Command testing failed: {e}")
        return False


def main():
    """Main test function."""
    print("emClarity GUI Component Test")
    print("=" * 40)

    config_ok = test_config()
    commands_ok = test_commands()

    if config_ok and commands_ok:
        print("\n✓ All tests passed! The GUI components are working correctly.")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the error messages above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
