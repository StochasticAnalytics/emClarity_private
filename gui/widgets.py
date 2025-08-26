"""
Widgets for the emClarity GUI.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QFileDialog, QGroupBox,
    QTextEdit, QScrollArea, QGridLayout, QFrame, QSplitter,
    QToolButton, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QRect, QEasingCurve
from PySide6.QtGui import QFont, QPalette, QColor
from typing import Dict, Any, List


class ParameterWidget(QWidget):
    """Widget for entering command parameters."""
    
    value_changed = Signal()
    
    def __init__(self, param_name: str, param_type: str = "string", 
                 description: str = "", default_value: Any = None, parent=None):
        super().__init__(parent)
        self.param_name = param_name
        self.param_type = param_type
        self.description = description
        
        self.setup_ui()
        if default_value is not None:
            self.set_value(default_value)
            
    def setup_ui(self):
        """Setup the parameter input widget."""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        label = QLabel(f"{self.param_name}:")
        label.setMinimumWidth(120)
        layout.addWidget(label)
        
        # Input widget based on type
        if self.param_type == "string" or self.param_type == "file":
            self.input_widget = QLineEdit()
            if self.param_type == "file":
                browse_btn = QPushButton("Browse...")
                browse_btn.clicked.connect(self.browse_file)
                file_layout = QHBoxLayout()
                file_layout.addWidget(self.input_widget)
                file_layout.addWidget(browse_btn)
                file_widget = QWidget()
                file_widget.setLayout(file_layout)
                layout.addWidget(file_widget)
            else:
                layout.addWidget(self.input_widget)
                
        elif self.param_type == "int":
            self.input_widget = QSpinBox()
            self.input_widget.setRange(-999999, 999999)
            layout.addWidget(self.input_widget)
            
        elif self.param_type == "float":
            self.input_widget = QDoubleSpinBox()
            self.input_widget.setRange(-999999.0, 999999.0)
            self.input_widget.setDecimals(3)
            layout.addWidget(self.input_widget)
            
        elif self.param_type == "bool":
            self.input_widget = QCheckBox()
            layout.addWidget(self.input_widget)
            
        elif self.param_type == "choice":
            self.input_widget = QComboBox()
            layout.addWidget(self.input_widget)
            
        # Connect value changed signal
        if hasattr(self.input_widget, 'textChanged'):
            self.input_widget.textChanged.connect(lambda: self.value_changed.emit())
        elif hasattr(self.input_widget, 'valueChanged'):
            self.input_widget.valueChanged.connect(lambda: self.value_changed.emit())
        elif hasattr(self.input_widget, 'stateChanged'):
            self.input_widget.stateChanged.connect(lambda: self.value_changed.emit())
        elif hasattr(self.input_widget, 'currentTextChanged'):
            self.input_widget.currentTextChanged.connect(lambda: self.value_changed.emit())
            
        # Tooltip
        if self.description:
            self.input_widget.setToolTip(self.description)
            
        self.setLayout(layout)
        
    def browse_file(self):
        """Browse for file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, f"Select {self.param_name}", "", "All files (*)"
        )
        if filename:
            self.input_widget.setText(filename)
            
    def get_value(self):
        """Get the current value."""
        if self.param_type in ["string", "file"]:
            return self.input_widget.text().strip()
        elif self.param_type in ["int", "float"]:
            return self.input_widget.value()
        elif self.param_type == "bool":
            return self.input_widget.isChecked()
        elif self.param_type == "choice":
            return self.input_widget.currentText()
        return None
        
    def set_value(self, value):
        """Set the current value."""
        if self.param_type in ["string", "file"]:
            self.input_widget.setText(str(value))
        elif self.param_type in ["int", "float"]:
            self.input_widget.setValue(value)
        elif self.param_type == "bool":
            self.input_widget.setChecked(bool(value))
        elif self.param_type == "choice":
            self.input_widget.setCurrentText(str(value))
            
    def set_choices(self, choices: List[str]):
        """Set choices for choice type parameters."""
        if self.param_type == "choice":
            self.input_widget.clear()
            self.input_widget.addItems(choices)


class EnhancedParameterWidget(QWidget):
    """Enhanced parameter widget that handles vectors, units, and better formatting."""
    
    value_changed = Signal()
    
    def __init__(self, parameter, parent=None):
        super().__init__(parent)
        self.parameter = parameter
        self.input_widgets = []
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the enhanced parameter widget UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Header with name and unit
        header_layout = QHBoxLayout()
        
        # Parameter name
        name_label = QLabel(self.parameter.display_name)
        name_font = QFont()
        name_font.setBold(True)
        name_label.setFont(name_font)
        header_layout.addWidget(name_label)
        
        # Required indicator
        if self.parameter.required:
            req_label = QLabel("*")
            req_label.setStyleSheet("color: red; font-weight: bold;")
            req_label.setToolTip("Required parameter")
            header_layout.addWidget(req_label)
        
        header_layout.addStretch()
        
        # Unit label
        if self.parameter.unit:
            unit_label = QLabel(f"[{self.parameter.unit}]")
            unit_font = QFont()
            unit_font.setBold(True)
            unit_font.setPointSize(14)  # Set to 14pt
            unit_label.setFont(unit_font)
            unit_label.setStyleSheet("color: #2C5AA0; font-weight: bold;")
            header_layout.addWidget(unit_label)
        
        layout.addLayout(header_layout)
        
        # Input widgets based on type
        input_layout = QHBoxLayout()
        
        if self.parameter.param_type == "vector":
            # Vector input - multiple spinboxes
            vector_size = self.parameter.vector_size or 3
            self.input_widgets = []
            
            for i in range(vector_size):
                if (isinstance(self.parameter.default, (list, tuple)) and 
                    len(self.parameter.default) > i):
                    default_val = self.parameter.default[i]
                    if isinstance(default_val, float):
                        widget = QDoubleSpinBox()
                        widget.setDecimals(6)
                    else:
                        widget = QSpinBox()
                else:
                    widget = QDoubleSpinBox()
                    widget.setDecimals(3)
                
                # Set bounds for this element if vector_bounds is available
                if (hasattr(self.parameter, 'vector_bounds') and 
                    self.parameter.vector_bounds and 
                    i < len(self.parameter.vector_bounds)):
                    min_val, max_val = self.parameter.vector_bounds[i]
                    widget.setRange(min_val, max_val)
                else:
                    # Default range
                    if isinstance(widget, QSpinBox):
                        widget.setRange(-1000000, 1000000)
                    else:
                        widget.setRange(-1e10, 1e10)
                
                widget.valueChanged.connect(lambda: self.value_changed.emit())
                self.input_widgets.append(widget)
                input_layout.addWidget(widget)
                
                # Add comma label between values (except last)
                if i < vector_size - 1:
                    comma_label = QLabel(",")
                    input_layout.addWidget(comma_label)
            
        elif self.parameter.param_type == "string":
            widget = QLineEdit()
            widget.textChanged.connect(lambda: self.value_changed.emit())
            self.input_widgets = [widget]
            input_layout.addWidget(widget)
            
        elif self.parameter.param_type == "file":
            widget = QLineEdit()
            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(lambda: self.browse_file(widget))
            
            widget.textChanged.connect(lambda: self.value_changed.emit())
            self.input_widgets = [widget]
            
            file_layout = QHBoxLayout()
            file_layout.addWidget(widget)
            file_layout.addWidget(browse_btn)
            input_layout.addLayout(file_layout)
            
        elif self.parameter.param_type == "int":
            widget = QSpinBox()
            if self.parameter.min_value is not None:
                widget.setMinimum(int(self.parameter.min_value))
            else:
                widget.setMinimum(-1000000)
            if self.parameter.max_value is not None:
                widget.setMaximum(int(self.parameter.max_value))
            else:
                widget.setMaximum(1000000)
            
            widget.valueChanged.connect(lambda: self.value_changed.emit())
            self.input_widgets = [widget]
            input_layout.addWidget(widget)
            
        elif self.parameter.param_type == "float":
            widget = QDoubleSpinBox()
            
            # Set decimal places based on parameter
            if self.parameter.name == "PIXEL_SIZE":
                widget.setDecimals(4)
            else:
                widget.setDecimals(6)
                
            if self.parameter.min_value is not None:
                widget.setMinimum(self.parameter.min_value)
            else:
                widget.setMinimum(-1e10)
            if self.parameter.max_value is not None:
                widget.setMaximum(self.parameter.max_value)
            else:
                widget.setMaximum(1e10)
            
            widget.valueChanged.connect(lambda: self.value_changed.emit())
            self.input_widgets = [widget]
            input_layout.addWidget(widget)
            
        elif self.parameter.param_type == "bool":
            widget = QCheckBox()
            widget.stateChanged.connect(lambda: self.value_changed.emit())
            self.input_widgets = [widget]
            input_layout.addWidget(widget)
            
        elif self.parameter.param_type == "choice":
            widget = QComboBox()
            if self.parameter.choices:
                widget.addItems(self.parameter.choices)
            widget.currentTextChanged.connect(lambda: self.value_changed.emit())
            self.input_widgets = [widget]
            input_layout.addWidget(widget)
        
        input_layout.addStretch()
        layout.addLayout(input_layout)
        
                # Description
        if self.parameter.description:
            desc_label = QLabel(self.parameter.description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #333; font-size: 14pt; font-weight: normal; margin-top: 3px;")
            layout.addWidget(desc_label)
        
        # Set default value
        if self.parameter.default is not None:
            self.set_value(self.parameter.default)
        
        # Enhanced tooltip
        self.setup_tooltip()
        
        self.setLayout(layout)
    
    def setup_tooltip(self):
        """Setup enhanced tooltip with parameter details."""
        tooltip_parts = [self.parameter.description]
        
        if self.parameter.unit:
            tooltip_parts.append(f"Unit: {self.parameter.unit}")
        
        if self.parameter.param_type in ["int", "float"]:
            if self.parameter.min_value is not None or self.parameter.max_value is not None:
                range_str = "Range: "
                if self.parameter.min_value is not None:
                    range_str += f"{self.parameter.min_value}"
                else:
                    range_str += "-∞"
                range_str += " to "
                if self.parameter.max_value is not None:
                    range_str += f"{self.parameter.max_value}"
                else:
                    range_str += "∞"
                tooltip_parts.append(range_str)
        
        if self.parameter.param_type == "choice" and self.parameter.choices:
            if self.parameter.name == "symmetry":
                # Special tooltip for symmetry parameter
                tooltip_parts.append("Common symmetries: C1 (no symmetry), C2 (2-fold), C12 (12-fold), D2 (dihedral), O (octahedral)")
                tooltip_parts.append(f"All choices: {', '.join(self.parameter.choices)}")
            else:
                tooltip_parts.append(f"Choices: {', '.join(self.parameter.choices)}")
        
        if self.parameter.param_type == "vector" and self.parameter.vector_size:
            tooltip_parts.append(f"Vector size: {self.parameter.vector_size}")
            if (hasattr(self.parameter, 'vector_bounds') and 
                self.parameter.vector_bounds):
                bounds_str = "Element bounds: "
                bounds_list = []
                for i, (min_val, max_val) in enumerate(self.parameter.vector_bounds):
                    bounds_list.append(f"[{i+1}]: {min_val}-{max_val}")
                bounds_str += ", ".join(bounds_list)
                tooltip_parts.append(bounds_str)
        
        if self.parameter.default is not None:
            tooltip_parts.append(f"Default: {self.parameter.default}")
        
        if self.parameter.required:
            tooltip_parts.append("⚠️ Required parameter")
        
        tooltip = "\n".join(tooltip_parts)
        self.setToolTip(tooltip)
        
        # Apply tooltip to all input widgets
        for widget in self.input_widgets:
            widget.setToolTip(tooltip)
    
    def browse_file(self, line_edit):
        """Browse for file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, f"Select {self.parameter.display_name}", "", "All files (*)"
        )
        if filename:
            line_edit.setText(filename)
    
    def get_value(self):
        """Get the current value."""
        if not self.input_widgets:
            return None
        
        if self.parameter.param_type == "vector":
            return [widget.value() for widget in self.input_widgets]
        elif self.parameter.param_type in ["string", "file"]:
            return self.input_widgets[0].text().strip()
        elif self.parameter.param_type in ["int", "float"]:
            return self.input_widgets[0].value()
        elif self.parameter.param_type == "bool":
            return self.input_widgets[0].isChecked()
        elif self.parameter.param_type == "choice":
            return self.input_widgets[0].currentText()
        
        return None
    
    def set_value(self, value):
        """Set the current value."""
        if not self.input_widgets:
            return
        
        if self.parameter.param_type == "vector":
            if isinstance(value, (list, tuple)):
                for i, widget in enumerate(self.input_widgets):
                    if i < len(value):
                        widget.setValue(value[i])
        elif self.parameter.param_type in ["string", "file"]:
            self.input_widgets[0].setText(str(value))
        elif self.parameter.param_type in ["int", "float"]:
            self.input_widgets[0].setValue(value)
        elif self.parameter.param_type == "bool":
            self.input_widgets[0].setChecked(bool(value))
        elif self.parameter.param_type == "choice":
            self.input_widgets[0].setCurrentText(str(value))


class CollapsibleCommandPanel(QWidget):
    """Collapsible command panel that can be expanded/collapsed."""
    
    run_command = Signal(str, list)  # command_name, arguments
    expansion_changed = Signal(str, bool)  # command_name, is_expanded
    
    def __init__(self, command_name: str, command_description: str, 
                 parameters: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.command_name = command_name
        self.command_description = command_description
        self.parameters = parameters
        self.param_widgets = {}
        self.is_expanded = False
        self.content_widget = None
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the collapsible command panel UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header with expand/collapse button
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            QWidget {
                background-color: #E8F0FE;
                border: 1px solid #D1E3FD;
                border-radius: 6px;
                padding: 4px;
            }
            QWidget:hover {
                background-color: #D6E9FF;
            }
        """)
        
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 6, 8, 6)
        
        # Expand/collapse button
        self.expand_btn = QToolButton()
        self.expand_btn.setText("▶")
        self.expand_btn.setStyleSheet("""
            QToolButton {
                border: none;
                background: transparent;
                font-size: 12px;
                font-weight: bold;
                color: #4A90E2;
                min-width: 16px;
                max-width: 16px;
            }
            QToolButton:hover {
                color: #2E5BA6;
            }
        """)
        self.expand_btn.clicked.connect(self.toggle_expansion)
        header_layout.addWidget(self.expand_btn)
        
        # Command name
        name_label = QLabel(self.command_name)
        name_font = QFont()
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setStyleSheet("color: #333; background: transparent; border: none;")
        header_layout.addWidget(name_label)
        
        header_layout.addStretch()
        
        # Quick run button (always visible)
        quick_run_btn = QPushButton("Run")
        quick_run_btn.setStyleSheet("""
            QPushButton {
                background-color: #4A90E2;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                min-width: 50px;
            }
            QPushButton:hover {
                background-color: #2E5BA6;
            }
            QPushButton:pressed {
                background-color: #1E3A66;
            }
        """)
        quick_run_btn.clicked.connect(self.quick_run)
        header_layout.addWidget(quick_run_btn)
        
        layout.addWidget(header_widget)
        
        # Content widget (initially hidden)
        self.content_widget = QWidget()
        self.content_widget.setVisible(False)
        self.setup_content()
        layout.addWidget(self.content_widget)
        
        self.setLayout(layout)
        
    def setup_content(self):
        """Setup the expandable content area."""
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(10, 8, 10, 8)
        
        # Add border and styling
        self.content_widget.setStyleSheet("""
            QWidget {
                background-color: #F8FBFF;
                border: 1px solid #D1E3FD;
                border-top: none;
                border-radius: 0px 0px 6px 6px;
            }
        """)
        
        # Description
        if self.command_description:
            desc_label = QLabel(self.command_description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("""
                color: #666; 
                font-style: italic; 
                background: transparent; 
                border: none;
                margin-bottom: 8px;
            """)
            layout.addWidget(desc_label)
            
        # Parameter widgets
        if self.parameters:
            params_widget = QWidget()
            params_layout = QVBoxLayout(params_widget)
            params_widget.setStyleSheet("background: transparent; border: none;")
            
            for param in self.parameters:
                param_widget = ParameterWidget(
                    param["name"],
                    param.get("type", "string"),
                    param.get("description", ""),
                    param.get("default", None)
                )
                
                if param.get("choices"):
                    param_widget.set_choices(param["choices"])
                    
                self.param_widgets[param["name"]] = param_widget
                params_layout.addWidget(param_widget)
                
            layout.addWidget(params_widget)
            
        # Full run button with parameters
        full_run_btn = QPushButton(f"Run {self.command_name} with Parameters")
        full_run_btn.setStyleSheet("""
            QPushButton {
                background-color: #28A745;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                margin-top: 8px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1E7E34;
            }
        """)
        full_run_btn.clicked.connect(self.full_run)
        layout.addWidget(full_run_btn)
        
    def toggle_expansion(self):
        """Toggle the expansion state of the panel."""
        self.is_expanded = not self.is_expanded
        self.content_widget.setVisible(self.is_expanded)
        
        # Update button icon
        self.expand_btn.setText("▼" if self.is_expanded else "▶")
        
        # Emit signal for state tracking
        self.expansion_changed.emit(self.command_name, self.is_expanded)
        
        # Force layout update
        self.updateGeometry()
        
    def set_expanded(self, expanded: bool):
        """Set expansion state programmatically."""
        if self.is_expanded != expanded:
            self.toggle_expansion()
            
    def quick_run(self):
        """Run command with default parameters."""
        self.run_command.emit(self.command_name, [])
        
    def full_run(self):
        """Run command with configured parameters."""
        args = []
        for param in self.parameters:
            param_name = param["name"]
            if param_name in self.param_widgets:
                value = self.param_widgets[param_name].get_value()
                if value:  # Only add non-empty values
                    args.append(str(value))
                    
        self.run_command.emit(self.command_name, args)
        
    def get_parameter_values(self) -> Dict[str, Any]:
        """Get all parameter values."""
        values = {}
        for name, widget in self.param_widgets.items():
            values[name] = widget.get_value()
        return values


class CommandPanel(QGroupBox):
    """Panel for configuring and running a specific command."""
    
    run_command = Signal(str, list)  # command_name, arguments
    
    def __init__(self, command_name: str, command_description: str, 
                 parameters: List[Dict[str, Any]], parent=None):
        super().__init__(command_name, parent)
        self.command_name = command_name
        self.command_description = command_description
        self.parameters = parameters
        self.param_widgets = {}
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the command panel UI."""
        layout = QVBoxLayout()
        
        # Description
        if self.command_description:
            desc_label = QLabel(self.command_description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #666; font-style: italic;")
            layout.addWidget(desc_label)
            
        # Parameter widgets
        if self.parameters:
            params_widget = QWidget()
            params_layout = QVBoxLayout(params_widget)
            
            for param in self.parameters:
                param_widget = ParameterWidget(
                    param["name"],
                    param.get("type", "string"),
                    param.get("description", ""),
                    param.get("default", None)
                )
                
                if param.get("choices"):
                    param_widget.set_choices(param["choices"])
                    
                self.param_widgets[param["name"]] = param_widget
                params_layout.addWidget(param_widget)
                
            layout.addWidget(params_widget)
            
        # Run button
        run_btn = QPushButton(f"Run {self.command_name}")
        run_btn.clicked.connect(self.run_clicked)
        layout.addWidget(run_btn)
        
        self.setLayout(layout)
        
    def run_clicked(self):
        """Handle run button click."""
        args = []
        for param in self.parameters:
            param_name = param["name"]
            if param_name in self.param_widgets:
                value = self.param_widgets[param_name].get_value()
                if value:  # Only add non-empty values
                    args.append(str(value))
                    
        self.run_command.emit(self.command_name, args)
        
    def get_parameter_values(self) -> Dict[str, Any]:
        """Get all parameter values."""
        values = {}
        for name, widget in self.param_widgets.items():
            values[name] = widget.get_value()
        return values


class ScrollableTab(QScrollArea):
    """Scrollable tab widget for handling many command panels."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Content widget
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.addStretch()
        
        self.setWidget(self.content_widget)
        
    def add_command_panel(self, panel: CommandPanel):
        """Add a command panel to the tab."""
        # Insert before the stretch
        self.content_layout.insertWidget(self.content_layout.count() - 1, panel)
        
    def clear_panels(self):
        """Clear all command panels."""
        while self.content_layout.count() > 1:  # Keep the stretch
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()


class ParameterConfigPanel(QWidget):
    """Panel for configuring emClarity parameters."""
    
    parameter_changed = Signal(str, object)  # parameter_name, value
    
    def __init__(self, tab_name: str, parameters, parent=None):
        super().__init__(parent)
        self.tab_name = tab_name
        self.parameters = parameters
        self.param_widgets = {}
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the parameter configuration panel."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        title = QLabel(f"{self.tab_name} Parameters")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Separator
        separator = QFrame()
        separator.setFrameStyle(QFrame.HLine | QFrame.Sunken)
        layout.addWidget(separator)
        
        # Scrollable parameter area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        params_widget = QWidget()
        params_layout = QVBoxLayout(params_widget)
        params_layout.setSpacing(15)
        
        # Add parameter widgets
        for parameter in self.parameters:
            param_widget = EnhancedParameterWidget(parameter)
            param_widget.value_changed.connect(
                lambda: self.on_parameter_changed(parameter)
            )
            self.param_widgets[parameter.name] = param_widget
            params_layout.addWidget(param_widget)
            
            # Add separator between parameters
            sep = QFrame()
            sep.setFrameStyle(QFrame.HLine | QFrame.Sunken)
            sep.setStyleSheet("QFrame { color: #E0E0E0; }")
            params_layout.addWidget(sep)
        
        params_layout.addStretch()
        scroll.setWidget(params_widget)
        layout.addWidget(scroll)
        
        # Save button
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        
        save_btn = QPushButton("Save Parameter File")
        save_btn.setToolTip("Save current parameters to a .m file")
        save_btn.clicked.connect(self.save_parameters)
        save_layout.addWidget(save_btn)
        
        layout.addLayout(save_layout)
        self.setLayout(layout)
    
    def on_parameter_changed(self, parameter):
        """Handle parameter value change."""
        if parameter.name in self.param_widgets:
            value = self.param_widgets[parameter.name].get_value()
            self.parameter_changed.emit(parameter.name, value)
    
    def get_parameter_values(self) -> Dict[str, Any]:
        """Get all parameter values."""
        values = {}
        for name, widget in self.param_widgets.items():
            value = widget.get_value()
            if value is not None:
                values[name] = value
        return values
    
    def set_parameter_values(self, values: Dict[str, Any]):
        """Set parameter values."""
        for name, value in values.items():
            if name in self.param_widgets:
                self.param_widgets[name].set_value(value)
    
    def save_parameters(self):
        """Save parameters to file."""
        from parameters import EmClarityParameters
        
        values = self.get_parameter_values()
        param_manager = EmClarityParameters()
        
        # Validate parameters
        errors = param_manager.validate_parameters(values)
        if errors:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Parameter Validation", 
                              "Parameter validation errors:\n\n" + "\n".join(errors))
            return
        
        # Create parameter file
        content, filename = param_manager.create_parameter_file(values, self.tab_name.lower())
        
        # Save file dialog
        from PySide6.QtWidgets import QFileDialog
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Parameter File", filename, "MATLAB files (*.m);;All files (*)"
        )
        
        if save_path:
            try:
                with open(save_path, 'w') as f:
                    f.write(content)
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Success", f"Parameters saved to {save_path}")
            except Exception as e:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Error", f"Failed to save file:\n{str(e)}")


class EnhancedTab(QWidget):
    """Enhanced tab widget with collapsible command panels and parameter config on right."""
    
    def __init__(self, tab_name: str, parent=None):
        super().__init__(parent)
        self.tab_name = tab_name
        self.command_panels = []
        self.parameter_panel = None
        self.expanded_panels = set()  # Track which panels are expanded
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the enhanced tab UI with split layout."""
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Create splitter for resizable panes
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side: Commands (smaller, collapsible)
        commands_widget = QWidget()
        commands_widget.setMaximumWidth(400)  # Limit width
        commands_widget.setMinimumWidth(250)
        
        commands_layout = QVBoxLayout(commands_widget)
        commands_layout.setContentsMargins(5, 5, 5, 5)
        
        # Commands title
        commands_title = QLabel("Commands")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        commands_title.setFont(title_font)
        commands_layout.addWidget(commands_title)
        
        # Commands scroll area
        self.commands_scroll = QScrollArea()
        self.commands_scroll.setWidgetResizable(True)
        self.commands_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.commands_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        commands_content = QWidget()
        self.commands_content_layout = QVBoxLayout(commands_content)
        self.commands_content_layout.setSpacing(2)  # Tighter spacing for collapsed panels
        self.commands_content_layout.addStretch()
        
        self.commands_scroll.setWidget(commands_content)
        commands_layout.addWidget(self.commands_scroll)
        
        # Right side: Parameters (larger)
        parameters_widget = QWidget()
        parameters_layout = QVBoxLayout(parameters_widget)
        parameters_layout.setContentsMargins(5, 5, 5, 5)
        
        # Placeholder for parameter panel
        placeholder = QLabel("Parameter configuration will appear here when tab is populated.")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #888; font-style: italic;")
        parameters_layout.addWidget(placeholder)
        
        # Add to splitter
        splitter.addWidget(commands_widget)
        splitter.addWidget(parameters_widget)
        
        # Set splitter sizes (30% commands, 70% parameters)
        splitter.setSizes([300, 700])
        
        layout.addWidget(splitter)
        self.setLayout(layout)
        
        # Store references
        self.commands_widget = commands_widget
        self.parameters_widget = parameters_widget
        self.parameters_layout = parameters_layout
        self.splitter = splitter
        
    def add_command_panel(self, panel):
        """Add a command panel to the left side."""
        # Use CollapsibleCommandPanel instead of regular CommandPanel
        if hasattr(panel, 'expansion_changed'):
            # It's already a collapsible panel
            collapsible_panel = panel
        else:
            # Convert regular panel to collapsible
            collapsible_panel = CollapsibleCommandPanel(
                panel.command_name,
                panel.command_description,
                panel.parameters,
                self
            )
            # Connect signals
            collapsible_panel.run_command.connect(panel.run_command)
        
        # Connect expansion tracking
        collapsible_panel.expansion_changed.connect(self.on_panel_expansion_changed)
        
        # Insert before the stretch
        self.commands_content_layout.insertWidget(
            self.commands_content_layout.count() - 1, collapsible_panel
        )
        self.command_panels.append(collapsible_panel)
        
    def on_panel_expansion_changed(self, command_name: str, is_expanded: bool):
        """Handle panel expansion state change."""
        if is_expanded:
            self.expanded_panels.add(command_name)
        else:
            self.expanded_panels.discard(command_name)
        
        # Could save state here if needed
        self.save_panel_states()
        
    def save_panel_states(self):
        """Save current panel expansion states."""
        # This will be called by the main window to save to database
        pass
    
    def restore_panel_states(self, expanded_panels: list):
        """Restore panel expansion states."""
        self.expanded_panels = set(expanded_panels)
        for panel in self.command_panels:
            if hasattr(panel, 'command_name'):
                should_expand = panel.command_name in self.expanded_panels
                panel.set_expanded(should_expand)
        
    def set_parameter_panel(self, panel):
        """Set the parameter configuration panel on the right side."""
        # Clear existing parameter widgets
        while self.parameters_layout.count() > 0:
            child = self.parameters_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Add new parameter panel
        self.parameter_panel = panel
        self.parameters_layout.addWidget(panel)
        
    def clear_panels(self):
        """Clear all panels."""
        # Clear command panels
        while self.commands_content_layout.count() > 1:  # Keep the stretch
            child = self.commands_content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.command_panels.clear()
        self.expanded_panels.clear()
        
        # Clear parameter panel
        if self.parameter_panel:
            self.parameter_panel.deleteLater()
            self.parameter_panel = None
    
    def get_splitter_sizes(self) -> str:
        """Get splitter sizes as string for state saving."""
        sizes = self.splitter.sizes()
        return f"{sizes[0]},{sizes[1]}"
    
    def set_splitter_sizes(self, sizes_str: str):
        """Set splitter sizes from string."""
        try:
            sizes = [int(x) for x in sizes_str.split(',')]
            if len(sizes) == 2:
                self.splitter.setSizes(sizes)
        except (ValueError, AttributeError):
            pass  # Use default sizes
