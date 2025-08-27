#!/usr/bin/env python3
"""
Rubber Band Selection Tool for emClarity GUI Development

This tool provides a way to capture GUI regions and generate AI-friendly prompts
for layout changes and GUI element identification.
"""

import sys
import os
import json
import tempfile
import inspect
from pathlib import Path
from datetime import datetime
import debug_instrumentation
from typing import Dict, Any, Optional, Tuple, List

from PySide6.QtWidgets import (
    QWidget, QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QDialogButtonBox, QGroupBox,
    QFormLayout, QLineEdit, QSpinBox
)
from PySide6.QtCore import Qt, QRect, QPoint, Signal, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QKeySequence, QMouseEvent, QShortcut


class GuiContextAnalyzer:
    """
    Analyzes GUI context to identify panels, widgets, and provide code context.
    """
    
    def __init__(self, main_window=None):
        self.main_window = main_window
    
    def analyze_selection(self, selection_rect: QRect) -> Dict[str, Any]:
        """Analyze the selected region and provide detailed context."""
        context = {
            "active_panel": self.get_active_panel(),
            "widgets_in_selection": self.find_widgets_in_selection(selection_rect),
            "visual_elements": self.analyze_visual_elements(selection_rect),
            "code_context": self.get_code_context(),
            "layout_analysis": self.analyze_layout(selection_rect)
        }
        return context
    
    def get_active_panel(self) -> Dict[str, str]:
        """Determine which panel is currently active."""
        if not self.main_window:
            return {"panel": "unknown", "details": "No main window reference"}
        
        try:
            # Check if main window has sidebar widget
            if hasattr(self.main_window, 'sidebar_widget'):
                sidebar = self.main_window.sidebar_widget
                current_panel = getattr(sidebar, 'current_panel', 'unknown')
                
                panel_info = {
                    "panel": current_panel,
                    "details": f"Active panel: {current_panel}",
                    "panel_class": str(type(sidebar.panels.get(current_panel, None)).__name__) if hasattr(sidebar, 'panels') else "unknown"
                }
                
                # Get additional panel-specific info
                if hasattr(sidebar, 'panels') and current_panel in sidebar.panels:
                    panel_widget = sidebar.panels[current_panel]
                    panel_info["widget_type"] = type(panel_widget).__name__
                    panel_info["object_name"] = getattr(panel_widget, 'objectName', lambda: '')()
                
                return panel_info
            
        except Exception as e:
            return {"panel": "error", "details": f"Error detecting panel: {str(e)}"}
        
        return {"panel": "unknown", "details": "Could not determine active panel"}
    
    def find_widgets_in_selection(self, selection_rect: QRect) -> List[Dict[str, Any]]:
        """Find all widgets that intersect with the selection rectangle."""
        widgets = []
        
        if not self.main_window:
            return widgets
        
        try:
            # Get all child widgets recursively
            all_widgets = self._get_all_child_widgets(self.main_window)
            
            for widget in all_widgets:
                if not widget.isVisible():
                    continue
                    
                # Get widget geometry in global coordinates
                widget_rect = widget.geometry()
                global_pos = widget.mapToGlobal(QPoint(0, 0))
                global_rect = QRect(global_pos, widget_rect.size())
                
                # Check if widget intersects with selection
                if global_rect.intersects(selection_rect):
                    widget_info = {
                        "type": type(widget).__name__,
                        "object_name": getattr(widget, 'objectName', lambda: '')(),
                        "text": self._get_widget_text(widget),
                        "geometry": {
                            "x": global_rect.x(),
                            "y": global_rect.y(),
                            "width": global_rect.width(),
                            "height": global_rect.height()
                        },
                        "properties": self._get_widget_properties(widget),
                        "parent_chain": self._get_parent_chain(widget)
                    }
                    widgets.append(widget_info)
        
        except Exception as e:
            widgets.append({"error": f"Error finding widgets: {str(e)}"})
        
        return widgets
    
    def _get_all_child_widgets(self, parent_widget) -> List[QWidget]:
        """Recursively get all child widgets."""
        widgets = []
        
        def collect_widgets(widget):
            widgets.append(widget)
            for child in widget.findChildren(QWidget):
                if child not in widgets:  # Avoid duplicates
                    widgets.append(child)
        
        collect_widgets(parent_widget)
        return widgets
    
    def _get_widget_text(self, widget) -> str:
        """Extract text content from a widget."""
        try:
            # Try common text properties
            if hasattr(widget, 'text') and callable(widget.text):
                return widget.text()
            elif hasattr(widget, 'title') and callable(widget.title):
                return widget.title()
            elif hasattr(widget, 'windowTitle') and callable(widget.windowTitle):
                return widget.windowTitle()
            elif hasattr(widget, 'toolTip') and callable(widget.toolTip):
                tip = widget.toolTip()
                return tip if tip else ""
        except:
            pass
        return ""
    
    def _get_widget_properties(self, widget) -> Dict[str, Any]:
        """Get relevant properties of a widget."""
        props = {}
        try:
            props["enabled"] = widget.isEnabled()
            props["visible"] = widget.isVisible()
            props["focus_policy"] = str(widget.focusPolicy())
            
            # Style-related properties
            if hasattr(widget, 'styleSheet'):
                stylesheet = widget.styleSheet()
                props["has_custom_style"] = bool(stylesheet)
                if stylesheet:
                    props["style_length"] = len(stylesheet)
            
            # Widget-specific properties
            if hasattr(widget, 'isChecked'):
                props["checked"] = widget.isChecked()
            if hasattr(widget, 'value'):
                props["value"] = widget.value()
            if hasattr(widget, 'currentText'):
                props["current_text"] = widget.currentText()
                
        except Exception as e:
            props["error"] = str(e)
        
        return props
    
    def _get_parent_chain(self, widget) -> List[str]:
        """Get the chain of parent widgets."""
        chain = []
        current = widget.parent()
        while current:
            chain.append(type(current).__name__)
            current = current.parent()
        return chain
    
    def analyze_visual_elements(self, selection_rect: QRect) -> Dict[str, Any]:
        """Analyze visual elements in the selection area."""
        return {
            "area_size": f"{selection_rect.width()}x{selection_rect.height()}",
            "aspect_ratio": round(selection_rect.width() / selection_rect.height(), 2),
            "position_type": self._classify_position(selection_rect),
            "likely_ui_type": self._guess_ui_element_type(selection_rect)
        }
    
    def _classify_position(self, rect: QRect) -> str:
        """Classify the position of the selection within the window."""
        if not self.main_window:
            return "unknown"
        
        window_rect = self.main_window.geometry()
        
        # Calculate relative position
        rel_x = rect.x() / window_rect.width() if window_rect.width() > 0 else 0
        rel_y = rect.y() / window_rect.height() if window_rect.height() > 0 else 0
        
        # Classify position
        h_pos = "left" if rel_x < 0.33 else "center" if rel_x < 0.66 else "right"
        v_pos = "top" if rel_y < 0.33 else "middle" if rel_y < 0.66 else "bottom"
        
        return f"{v_pos}-{h_pos}"
    
    def _guess_ui_element_type(self, rect: QRect) -> str:
        """Guess the type of UI element based on dimensions."""
        width, height = rect.width(), rect.height()
        aspect_ratio = width / height if height > 0 else 0
        
        if height < 40 and width > 200:
            return "horizontal_toolbar_or_menu"
        elif width < 60 and height > 100:
            return "vertical_sidebar_or_panel"
        elif aspect_ratio > 3:
            return "horizontal_strip_or_banner"
        elif aspect_ratio < 0.5:
            return "vertical_column_or_list"
        elif 80 < width < 200 and 25 < height < 50:
            return "button_or_control"
        elif width > 400 and height > 300:
            return "main_content_area"
        else:
            return "mixed_content_region"
    
    def get_code_context(self) -> Dict[str, Any]:
        """Get code context for the current GUI state."""
        context = {}
        
        if not self.main_window:
            return context
        
        try:
            # Get main window class info
            main_class = type(self.main_window).__name__
            context["main_window_class"] = main_class
            
            # Get current module
            module = inspect.getmodule(self.main_window)
            if module:
                context["module_file"] = getattr(module, '__file__', 'unknown')
                context["module_name"] = getattr(module, '__name__', 'unknown')
            
            # Get active panel source if possible
            if hasattr(self.main_window, 'sidebar_widget'):
                sidebar = self.main_window.sidebar_widget
                current_panel = getattr(sidebar, 'current_panel', None)
                
                if current_panel and hasattr(sidebar, 'panels'):
                    panel_widget = sidebar.panels.get(current_panel)
                    if panel_widget:
                        panel_module = inspect.getmodule(panel_widget)
                        if panel_module:
                            context["active_panel_file"] = getattr(panel_module, '__file__', 'unknown')
                            context["active_panel_class"] = type(panel_widget).__name__
        
        except Exception as e:
            context["error"] = str(e)
        
        return context
    
    def analyze_layout(self, selection_rect: QRect) -> Dict[str, Any]:
        """Analyze the layout characteristics of the selection."""
        return {
            "selection_area": selection_rect.width() * selection_rect.height(),
            "center_point": {
                "x": selection_rect.center().x(),
                "y": selection_rect.center().y()
            },
            "corners": {
                "top_left": {"x": selection_rect.topLeft().x(), "y": selection_rect.topLeft().y()},
                "bottom_right": {"x": selection_rect.bottomRight().x(), "y": selection_rect.bottomRight().y()}
            }
        }


class RubberBandOverlay(QWidget):
    """
    Transparent overlay widget that captures rubber band selections.
    """
    
    selection_made = Signal(QRect)
    escape_pressed = Signal()  # New signal for ESC key
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        # Enable keyboard focus to capture ESC key
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Rubber band state
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.is_selecting = False
        self.selection_rect = QRect()
        
        # Make it cover the entire screen
        self.resize(QApplication.primaryScreen().size())
        
        # Key modifier for activation (Ctrl by default)
        self.activation_key = Qt.KeyboardModifier.ControlModifier
        
    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            # Emit signal to let the main tool handle the ESC key
            self.escape_pressed.emit()
            event.accept()
            return
        # Handle other keys normally
        super().keyPressEvent(event)
    
    def mousePressEvent(self, event: QMouseEvent):
        """Start rubber band selection on click and drag."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.is_selecting = True
            self.update()
        elif event.button() == Qt.MouseButton.RightButton and self.is_selecting:
            # Right-click cancels current selection
            self.cancel_selection()
        
    def mouseMoveEvent(self, event: QMouseEvent):
        """Update rubber band during drag."""
        if self.is_selecting:
            self.end_point = event.pos()
            self.update()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Finish rubber band selection."""
        if self.is_selecting and event.button() == Qt.MouseButton.LeftButton:
            self.is_selecting = False
            
            # Create selection rectangle
            self.selection_rect = QRect(self.start_point, self.end_point).normalized()
            
            # Only emit if we have a meaningful selection
            if self.selection_rect.width() > 10 and self.selection_rect.height() > 10:
                self.selection_made.emit(self.selection_rect)
            
            self.update()
    
    def paintEvent(self, event):
        """Draw the rubber band."""
        if not self.is_selecting:
            return
            
        painter = QPainter(self)
        
        # Set up pen for rubber band
        pen = QPen(QColor(255, 0, 0, 180))  # Semi-transparent red
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        
        # Draw selection rectangle
        rect = QRect(self.start_point, self.end_point).normalized()
        painter.drawRect(rect)
        
        # Fill with semi-transparent color
        painter.fillRect(rect, QColor(255, 0, 0, 30))
    
    def cancel_selection(self):
        """Cancel current selection."""
        self.is_selecting = False
        self.update()


class GuiElementInfoDialog(QDialog):
    """
    Dialog for inputting text along with captured GUI coordinates and context analysis.
    """
    
    def __init__(self, selection_rect: QRect, context_analysis: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.selection_rect = selection_rect
        self.context_analysis = context_analysis
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("GUI Element Analysis - Rubber Band Tool")
        self.setModal(True)
        self.resize(600, 500)
        
        layout = QVBoxLayout(self)
        
        # Info section
        info_group = QGroupBox("Selection Information")
        info_layout = QFormLayout(info_group)
        
        # Coordinates display
        coords_text = f"X: {self.selection_rect.x()}, Y: {self.selection_rect.y()}"
        size_text = f"Width: {self.selection_rect.width()}, Height: {self.selection_rect.height()}"
        
        info_layout.addRow("Top-Left Coordinates:", QLabel(coords_text))
        info_layout.addRow("Selection Size:", QLabel(size_text))
        info_layout.addRow("Timestamp:", QLabel(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        layout.addWidget(info_group)
        
        # Enhanced prompt section
        prompt_group = QGroupBox("AI Agent Prompt")
        prompt_layout = QVBoxLayout(prompt_group)
        
        # Generate enhanced prompt
        enhanced_prompt = self._generate_enhanced_prompt(coords_text, size_text)
        
        self.prompt_text = QTextEdit()
        self.prompt_text.setPlainText(enhanced_prompt)
        self.prompt_text.setMinimumHeight(250)
        
        prompt_layout.addWidget(QLabel("Enhanced AI prompt with context analysis:"))
        prompt_layout.addWidget(self.prompt_text)
        
        layout.addWidget(prompt_group)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal, self
        )
        
        # Add Save to File button
        save_button = QPushButton("Save to File")
        buttons.addButton(save_button, QDialogButtonBox.ButtonRole.ActionRole)
        
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        save_button.clicked.connect(self.save_to_file)
        
        layout.addWidget(buttons)
    
    def _format_widgets_info(self, widgets: List[Dict[str, Any]]) -> str:
        """Format widget information for display."""
        lines = []
        for i, widget in enumerate(widgets):
            if "error" in widget:
                continue
                
            widget_type = widget.get("type", "Unknown")
            text = widget.get("text", "")
            object_name = widget.get("object_name", "")
            
            line = f"{i+1}. {widget_type}"
            if object_name:
                line += f" ('{object_name}')"
            if text:
                line += f" - Text: '{text[:50]}{'...' if len(text) > 50 else ''}'"
            
            # Add geometry info
            geom = widget.get("geometry", {})
            if geom:
                line += f" - Size: {geom.get('width', 0)}x{geom.get('height', 0)}"
            
            lines.append(line)
        
        return "\n".join(lines) if lines else "No widgets found in selection area."
    
    def _generate_enhanced_prompt(self, coords_text: str, size_text: str) -> str:
        """Generate an enhanced AI prompt with detailed context."""
        
        # Get click data from debug instrumentation
        click_data_list = debug_instrumentation.get_latest_click_data()
        
        # Get the most recent click event (last item in the list)
        click_data = None
        if click_data_list and isinstance(click_data_list, list) and len(click_data_list) > 0:
            click_data = click_data_list[-1]  # Get the most recent click
        
        # Extract key information
        panel_info = self.context_analysis.get("active_panel", {})
        active_panel = panel_info.get("panel", "unknown")
        panel_class = panel_info.get("panel_class", "unknown")
        
        visual = self.context_analysis.get("visual_elements", {})
        ui_type = visual.get("likely_ui_type", "unknown")
        position = visual.get("position_type", "unknown")
        
        widgets = self.context_analysis.get("widgets_in_selection", [])
        widget_types = [w.get("type", "") for w in widgets if "error" not in w]
        
        code_context = self.context_analysis.get("code_context", {})
        panel_file = code_context.get("active_panel_file", "unknown")
        
        enhanced_prompt = f"""GUI Analysis Request - emClarity Interface

remembering #file:copilot-instructions.md #file:emClarity_Tutorial.md #file:GUI_IMPLEMENTATION_SUMMARY.md 

SELECTION COORDINATES: 
- Area: {coords_text} (Size: {size_text})
- Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

REQUEST:
Based on the detailed analysis below, please help me with:

[DESCRIBE YOUR SPECIFIC REQUEST HERE - The context analysis should help you understand exactly what's selected]

--------------------------------------------------

{self._format_click_data_section(click_data)}

DETAILED CONTEXT ANALYSIS:

🎯 ACTIVE PANEL:
- Panel: {active_panel}
- Panel Class: {panel_class}
- Source File: {panel_file.split('/')[-1] if '/' in str(panel_file) else panel_file}

🔍 SELECTION ANALYSIS:
- UI Element Type: {ui_type.replace('_', ' ').title()}
- Position: {position.replace('-', ' ').title()}
- Widgets Found: {len(widget_types)}
- Widget Types: {', '.join(set(widget_types)) if widget_types else 'None detected'}

📋 WIDGET DETAILS:
{self._format_widgets_summary(widgets)}

🎨 VISUAL CHARACTERISTICS:
- Aspect Ratio: {visual.get('aspect_ratio', 'unknown')}
- Area Size: {visual.get('area_size', 'unknown')}
- Likely Purpose: {self._guess_element_purpose(ui_type, widget_types)}

RUBBER BAND TOOL USAGE:
- Launched with: --rubber-band-mode flag
- Selection method: Click+Drag
- Click logging: Press L to toggle click logging on/off
- Toggle tool: ESC key
- Cancel selection: Right-click

CURRENT GUI LAYOUT:
The emClarity GUI uses a modern PySide6-based interface with:
- Left sidebar navigation (Overview, Tilt-Series Assets, Actions, Results, Settings, Experimental)
- Top horizontal toolbar with panel-specific buttons
- Central content area with different panels
- Professional menu bar and consistent styling

ANALYSIS ASSISTANCE NEEDED:
- Layout improvements for the {ui_type.replace('_', ' ')} area
- Widget spacing and alignment optimization
- Visual hierarchy and styling enhancements
- Functionality improvements for {active_panel} panel

Please confirm you understand the context and provide specific recommendations for the selected area.

CODE CONTEXT:
- Active panel source: {panel_file}
- Main window class: {code_context.get('main_window_class', 'unknown')}
- Module: {code_context.get('module_name', 'unknown')}
"""
        
        return enhanced_prompt
    
    def _format_click_data_section(self, click_data: Dict[str, Any]) -> str:
        """Format click data section for the prompt."""
        if not click_data:
            return """🖱️ ELEMENT INTERACTION DATA:
No recent element click captured. To capture element context:
1. Press L to enable click logging
2. Click on any GUI element (button, menu, etc.)
3. Press ESC to activate rubber band selection
4. Click+Drag to select the area for analysis

"""
        
        # Format timestamp
        click_time = click_data.get("timestamp", "unknown")
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(click_time)
            formatted_time = dt.strftime("%H:%M:%S")
        except:
            formatted_time = click_time
        
        # Extract click information from the event filter format
        widget_class = click_data.get("widget_class", "unknown")
        widget_text = click_data.get("widget_text", "")
        widget_name = click_data.get("widget_name", "unnamed")
        widget_parent = click_data.get("widget_parent", "unknown")
        
        # Format click position
        click_pos = click_data.get("click_position", {})
        pos_text = f"({click_pos.get('x', 0):.0f}, {click_pos.get('y', 0):.0f})" if click_pos else "unknown"
        
        section = f"""🖱️ ELEMENT INTERACTION DATA:
- Last Clicked Element: {widget_name if widget_name != 'unnamed' else widget_class}
- Widget Type: {widget_class}
- Widget Text: {widget_text[:100] + '...' if len(widget_text) > 100 else widget_text or 'no text'}
- Parent Widget: {widget_parent}
- Click Position: {pos_text}
- Click Time: {formatted_time}

"""
        return section
    
    def _format_widgets_summary(self, widgets: List[Dict[str, Any]]) -> str:
        """Create a concise summary of widgets for the prompt."""
        if not widgets or all("error" in w for w in widgets):
            return "- No widgets detected in selection area"
        
        summary = []
        for widget in widgets[:5]:  # Limit to first 5 widgets
            if "error" in widget:
                continue
            widget_type = widget.get("type", "Unknown")
            text = widget.get("text", "")
            summary.append(f"- {widget_type}{f': \"{text}\"' if text else ''}")
        
        if len([w for w in widgets if "error" not in w]) > 5:
            summary.append(f"- ... and {len(widgets) - 5} more widgets")
        
        return "\n".join(summary) if summary else "- No widgets detected"
    
    def _guess_element_purpose(self, ui_type: str, widget_types: List[str]) -> str:
        """Guess the purpose of the UI element based on type and widgets."""
        if "toolbar" in ui_type:
            return "Action buttons and controls"
        elif "sidebar" in ui_type:
            return "Navigation or secondary controls"
        elif "button" in ui_type or "QPushButton" in widget_types:
            return "User interaction element"
        elif "content" in ui_type:
            return "Main information display area"
        elif any("Label" in wt for wt in widget_types):
            return "Information display or form labels"
        elif any("Edit" in wt for wt in widget_types):
            return "Data input or configuration"
        else:
            return "Mixed interface elements"
    
    def get_prompt_data(self) -> Dict[str, Any]:
        """Get the complete prompt data with enhanced context."""
        return {
            "timestamp": datetime.now().isoformat(),
            "selection_coordinates": {
                "x": self.selection_rect.x(),
                "y": self.selection_rect.y(),
                "width": self.selection_rect.width(),
                "height": self.selection_rect.height()
            },
            "context_analysis": self.context_analysis,
            "prompt_text": self.prompt_text.toPlainText(),
            "gui_context": "emClarity PySide6 GUI - Development Tool",
            "enhanced_analysis": True
        }
    
    def save_to_file(self):
        """Save prompt data to temporary file."""
        data = self.get_prompt_data()
        
        # Create temporary file
        temp_dir = Path(tempfile.gettempdir()) / "emclarity_gui_prompts"
        temp_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gui_prompt_{timestamp}.json"
        filepath = temp_dir / filename
        
        # Save data
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Also save as text file for easy reading
        text_filename = f"gui_prompt_{timestamp}.txt"
        text_filepath = temp_dir / text_filename
        
        with open(text_filepath, 'w') as f:
            f.write(f"emClarity GUI Analysis Prompt\n")
            f.write(f"Generated: {data['timestamp']}\n")
            f.write(f"Coordinates: ({data['selection_coordinates']['x']}, {data['selection_coordinates']['y']})\n")
            f.write(f"Size: {data['selection_coordinates']['width']} x {data['selection_coordinates']['height']}\n")
            f.write(f"\n{'-'*50}\n\n")
            f.write(data['prompt_text'])
        
        print(f"Prompt saved to:")
        print(f"  JSON: {filepath}")
        print(f"  Text: {text_filepath}")
        
        self.accept()


class RubberBandTool:
    """
    Main rubber band tool coordinator.
    """
    
    def __init__(self, main_window=None):
        self.main_window = main_window
        self.overlay = None
        self.is_active = False
        self.keyboard_shortcut = None
        self.context_analyzer = GuiContextAnalyzer(main_window)
        
    def setup_keyboard_shortcut(self):
        """Setup ESC keyboard shortcut for toggling rubber band mode."""
        if self.main_window and not self.keyboard_shortcut:
            # This shortcut will only work when the overlay is NOT active
            self.keyboard_shortcut = QShortcut(QKeySequence("Escape"), self.main_window)
            self.keyboard_shortcut.activated.connect(self.handle_main_window_escape)
            print("🎯 Rubber Band Tool: ESC key shortcut ready")
            print("   Press ESC to toggle rubber band selection on/off")
    
    def handle_main_window_escape(self):
        """Handle ESC key from main window (when overlay is not active)."""
        if not self.is_active:
            # Only activate if not already active
            self.activate()
        
    def toggle_activation(self):
        """Toggle rubber band tool activation via keyboard shortcut or overlay ESC."""
        print(f"🔧 ESC TOGGLE: Before - is_active = {self.is_active}")
        
        if self.is_active:
            print("🔧 ESC TOGGLE: Deactivating rubber band tool")
            self.deactivate()
        else:
            print("🔧 ESC TOGGLE: Activating rubber band tool")
            self.activate()
            
        print(f"🔧 ESC TOGGLE: After - is_active = {self.is_active}")
        
    def activate(self):
        """Activate the rubber band tool."""
        if self.is_active:
            return
            
        self.is_active = True
        
        # Create overlay
        self.overlay = RubberBandOverlay()
        self.overlay.selection_made.connect(self.handle_selection)
        self.overlay.escape_pressed.connect(self.deactivate)  # Direct connection to deactivate
        
        # Show overlay
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()
        self.overlay.setFocus()  # Ensure it can capture keyboard events
        
        print("Rubber band tool activated!")
        print("Use Click+Drag to select GUI regions")
        print("Use L to toggle click logging for capturing interaction context")
        print("Right-click to cancel current selection")
        print("Press ESC to deactivate rubber band tool")
        
    def deactivate(self):
        """Deactivate the rubber band tool."""
        if not self.is_active:
            return
            
        self.is_active = False
        
        if self.overlay:
            self.overlay.hide()
            self.overlay.deleteLater()
            self.overlay = None
            
        print("Rubber band tool deactivated!")
        print("Press ESC to reactivate rubber band tool")
    
    def handle_selection(self, rect: QRect):
        """Handle completed selection with enhanced context analysis."""
        print(f"Selection made: {rect}")
        print("🔍 Analyzing GUI context...")
        
        # Analyze the selection context
        context_analysis = self.context_analyzer.analyze_selection(rect)
        
        # Display brief analysis in console
        panel_info = context_analysis.get("active_panel", {})
        visual_info = context_analysis.get("visual_elements", {})
        widget_count = len([w for w in context_analysis.get("widgets_in_selection", []) if "error" not in w])
        
        print(f"📋 Panel: {panel_info.get('panel', 'unknown')}")
        print(f"🎯 UI Type: {visual_info.get('likely_ui_type', 'unknown').replace('_', ' ')}")
        print(f"🔧 Widgets: {widget_count} found")
        
        # Hide overlay temporarily
        if self.overlay:
            self.overlay.hide()
        
        # Show enhanced dialog with context analysis
        dialog = GuiElementInfoDialog(rect, context_analysis, self.main_window)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted:
            print("Enhanced prompt data saved!")
        
        # Reactivate overlay
        if self.overlay:
            self.overlay.show()
            self.overlay.raise_()


def create_rubber_band_tool(main_window=None) -> RubberBandTool:
    """Factory function to create rubber band tool."""
    return RubberBandTool(main_window)


# Command line interface for testing
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Create a simple test window
    test_window = QWidget()
    test_window.setWindowTitle("Rubber Band Tool Test")
    test_window.resize(800, 600)
    test_window.show()
    
    # Create and activate tool
    tool = create_rubber_band_tool(test_window)
    
    # Activate after a short delay
    QTimer.singleShot(1000, tool.activate)
    
    sys.exit(app.exec())
