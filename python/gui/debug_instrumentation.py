#!/usr/bin/env python3
"""
Simple Debug Instrumentation for emClarity GUI.

Single event filter that logs mouse clicks when rubber band mode is active
and click logging is toggled on via L key.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
import contextlib

try:
    from PySide6.QtCore import QEvent, QObject, Qt
    from PySide6.QtGui import QKeySequence, QMouseEvent, QShortcut
    from PySide6.QtWidgets import QApplication

    QT_AVAILABLE = True
    print("🔧 QT imports successful - QT_AVAILABLE = True")
except ImportError as e:
    QT_AVAILABLE = False
    print(f"🔧 QT import failed - QT_AVAILABLE = False, error: {e}")

# Global state
_RUBBER_BAND_MODE = False
_CLICK_LOGGING_ENABLED = False
_DEBUG_DATA_FILE = None
_CLICK_FILTER = None


class ClickLoggingFilter(QObject):
    """Single event filter that logs all mouse clicks when enabled."""

    def eventFilter(self, obj, event):
        """Filter mouse click events and log them if conditions are met."""
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            print(f"�️ Mouse click detected on {type(obj).__name__}")

            # Only log if we're in rubber band mode AND click logging is enabled
            if _RUBBER_BAND_MODE and _CLICK_LOGGING_ENABLED:
                print("✅ Logging click event")
                self._log_click_event(obj, event)
            else:
                print("❌ Skipping logging")

        # Always pass the event through normally
        return False

    def _log_click_event(self, widget, event):
        """Log a click event with widget information."""
        try:
            # Extract widget information
            widget_info = self._extract_widget_info(widget)

            # Create click record
            click_data = {
                "timestamp": datetime.now().isoformat(),
                "widget_class": widget_info["class"],
                "widget_name": widget_info["name"],
                "widget_text": widget_info["text"],
                "widget_parent": widget_info["parent"],
                "click_position": {
                    "x": event.position().x(),
                    "y": event.position().y(),
                },
                "global_position": {
                    "x": event.globalPosition().x(),
                    "y": event.globalPosition().y(),
                },
            }

            # Save to debug file
            self._save_click_data(click_data)

            # Print to console
            print(
                f"🎯 Click logged: {widget_info['class']} '{widget_info['text']}' in {widget_info['parent']}"
            )

        except Exception as e:
            print(f"Click logging error: {e}")

    def _extract_widget_info(self, widget):
        """Extract useful information from a widget."""
        info = {
            "class": widget.__class__.__name__,
            "name": getattr(widget, "objectName", lambda: "")() or "unnamed",
            "text": "",
            "parent": "unknown",
        }

        # Try to get text
        if hasattr(widget, "text"):
            with contextlib.suppress(BaseException):
                info["text"] = widget.text()
        elif hasattr(widget, "title"):
            with contextlib.suppress(BaseException):
                info["text"] = widget.title()

        # Try to get parent info
        if hasattr(widget, "parent") and widget.parent():
            parent = widget.parent()
            info["parent"] = parent.__class__.__name__
            if hasattr(parent, "objectName"):
                parent_name = parent.objectName()
                if parent_name:
                    info["parent"] = f"{parent.__class__.__name__}({parent_name})"

        return info

    def _save_click_data(self, click_data):
        """Save click data to debug file."""
        if not _DEBUG_DATA_FILE:
            return

        try:
            # Read existing data
            existing_data = []
            if _DEBUG_DATA_FILE.exists():
                try:
                    with open(_DEBUG_DATA_FILE) as f:
                        content = f.read().strip()
                        if content:
                            existing_data = json.loads(content)
                            if not isinstance(existing_data, list):
                                existing_data = [existing_data]
                except (json.JSONDecodeError, FileNotFoundError):
                    existing_data = []

            # Add new click
            existing_data.append(click_data)

            # Write back
            with open(_DEBUG_DATA_FILE, "w") as f:
                json.dump(existing_data, f, indent=2)

        except Exception as e:
            print(f"Error saving click data: {e}")


def init_rubber_band_debug(enabled: bool = False):
    """Initialize rubber band debug mode with simple click logging."""
    global _RUBBER_BAND_MODE, _DEBUG_DATA_FILE, _CLICK_LOGGING_ENABLED, _CLICK_FILTER

    print(f"🔧 INIT: enabled = {enabled}")
    print(f"🔧 INIT: QT_AVAILABLE = {QT_AVAILABLE}")

    _RUBBER_BAND_MODE = enabled
    _CLICK_LOGGING_ENABLED = False  # Always start disabled

    if enabled and QT_AVAILABLE:
        print("🔧 INIT: Creating debug data file...")
        # Create debug data file
        temp_dir = Path(tempfile.gettempdir()) / "emclarity_gui_debug"
        temp_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _DEBUG_DATA_FILE = temp_dir / f"click_debug_{timestamp}.json"

        print("🔧 INIT: Installing global event filter...")
        # Create event filter but don't install it yet - only install when logging is enabled
        _CLICK_FILTER = ClickLoggingFilter()
        print("🔧 INIT: Event filter created (will be installed on L key press)")

        print("🔍 GUI Debug Instrumentation ACTIVE")
        print(f"📝 Click data will be saved to: {_DEBUG_DATA_FILE}")
        print("🔑 Press L to toggle click logging (currently OFF)")
    else:
        print(
            f"🔧 INIT: Not initializing debug - enabled={enabled}, QT_AVAILABLE={QT_AVAILABLE}"
        )
        _DEBUG_DATA_FILE = None


def toggle_click_logging() -> bool:
    """Toggle click logging on/off with L key. Returns new state."""
    global _CLICK_LOGGING_ENABLED

    print(f"🔧 BEFORE toggle: _CLICK_LOGGING_ENABLED = {_CLICK_LOGGING_ENABLED}")
    print(f"🔧 BEFORE toggle: _RUBBER_BAND_MODE = {_RUBBER_BAND_MODE}")
    print(f"🔧 BEFORE toggle: QT_AVAILABLE = {QT_AVAILABLE}")

    if not _RUBBER_BAND_MODE:
        print("⚠️ Cannot toggle - rubber band mode not active")
        return False

    _CLICK_LOGGING_ENABLED = not _CLICK_LOGGING_ENABLED

    # Install/remove event filter based on logging state
    app = QApplication.instance()
    if app and _CLICK_FILTER:
        if _CLICK_LOGGING_ENABLED:
            print("🔧 Installing event filter for click logging...")
            app.installEventFilter(_CLICK_FILTER)
        else:
            print("🔧 Removing event filter to avoid interference...")
            app.removeEventFilter(_CLICK_FILTER)

    print(f"🔧 AFTER toggle: _CLICK_LOGGING_ENABLED = {_CLICK_LOGGING_ENABLED}")

    status = "ENABLED" if _CLICK_LOGGING_ENABLED else "DISABLED"
    print(f"🎯 Click logging {status}")
    return _CLICK_LOGGING_ENABLED


def setup_click_logging_shortcut(parent_widget):
    """Setup L key shortcut to toggle click logging."""
    if not QT_AVAILABLE or not _RUBBER_BAND_MODE:
        return None

    try:
        shortcut = QShortcut(QKeySequence("L"), parent_widget)
        shortcut.activated.connect(toggle_click_logging)
        return shortcut
    except Exception as e:
        print(f"⚠️ Could not setup click logging shortcut: {e}")
        return None


def is_rubber_band_debug_active() -> bool:
    """Check if rubber band debug mode is active."""
    return _RUBBER_BAND_MODE


def is_click_logging_enabled() -> bool:
    """Check if click logging is currently enabled."""
    return _RUBBER_BAND_MODE and _CLICK_LOGGING_ENABLED


def get_latest_click_data() -> Optional[list]:
    """Get all click data for rubber band analysis."""
    if not _RUBBER_BAND_MODE or not _DEBUG_DATA_FILE:
        return None

    try:
        if _DEBUG_DATA_FILE.exists():
            with open(_DEBUG_DATA_FILE) as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    return data if isinstance(data, list) else [data]
    except Exception as e:
        print(f"Error reading click data: {e}")

    return None


def clear_click_data():
    """Clear the current click data."""
    if _DEBUG_DATA_FILE and _DEBUG_DATA_FILE.exists():
        with contextlib.suppress(Exception):
            _DEBUG_DATA_FILE.unlink()


# Conditional compilation support
INCLUDE_DEBUG_INSTRUMENTATION = os.getenv(
    "EMCLARITY_DEBUG_INSTRUMENTATION", "1"
).lower() in ["true", "1", "yes", "on"]

if not INCLUDE_DEBUG_INSTRUMENTATION:
    # Replace all functions with no-ops for production builds
    def init_rubber_band_debug(*args, **kwargs):
        pass

    def toggle_click_logging():
        return False

    def setup_click_logging_shortcut(*args, **kwargs):
        return None

    def is_rubber_band_debug_active():
        return False

    def is_click_logging_enabled():
        return False

    def get_latest_click_data():
        return None

    def clear_click_data():
        pass
