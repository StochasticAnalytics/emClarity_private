"""
emClarity GUI package.

This package provides a PySide6-based graphical user interface
for the emClarity cryo-EM processing software.
"""

__version__ = "1.0.0"
__author__ = "emClarity Team"

from .config import EmClarityConfig, get_default_config
from .commands import EmClarityCommands, EmClarityCommand

__all__ = ['EmClarityConfig', 'get_default_config', 'EmClarityCommands', 'EmClarityCommand']
