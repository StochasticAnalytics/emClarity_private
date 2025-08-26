#!/usr/bin/env python3
"""
Modern emClarity GUI with tabbed interface.
"""

import sys
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Any

# Add gui directory to path
gui_dir = Path(__file__).parent.absolute()
if str(gui_dir) not in sys.path:
    sys.path.insert(0, str(gui_dir))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, 
    QWidget, QTabWidget, QGroupBox, QPushButton, QLineEdit, 
    QTextEdit, QFormLayout, QGridLayout, QComboBox, QSpinBox,
    QCheckBox, QFileDialog, QMessageBox, QProgressBar, QSplitter,
    QMenuBar, QMenu
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QPalette, QColor, QAction, QTextCursor
from typing import List, Dict, Any

from config import get_default_config
from commands import EmClarityCommands
from widgets import CommandPanel, ScrollableTab, EnhancedTab, ParameterConfigPanel, CollapsibleCommandPanel
from parameters import EmClarityParameters
from project_dialog import ProjectDialog
from state_manager import GUIStateManager
from profile_widgets import RunProfileWidget
from autoalign_widget import AutoAlignWidget
from tilt_series_assets import TiltSeriesAssetsWidget


class CommandRunner(QThread):
    """Thread for running emClarity commands without blocking the GUI."""
    
    output_ready = Signal(str)
    error_ready = Signal(str)
    finished_signal = Signal(int)
    
    def __init__(self, command: List[str], working_dir: str = None):
        super().__init__()
        self.command = command
        self.working_dir = working_dir
        
    def run(self):
        """Execute the command."""
        try:
            process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.working_dir
            )
            
            stdout, stderr = process.communicate()
            
            if stdout:
                self.output_ready.emit(stdout)
            if stderr:
                self.error_ready.emit(stderr)
                
            self.finished_signal.emit(process.returncode)
            
        except Exception as e:
            self.error_ready.emit(f"Failed to execute command: {str(e)}")
            self.finished_signal.emit(-1)


class DynamicCommandTab(EnhancedTab):
    """Enhanced dynamic tab with command panels and parameter configuration."""
    
    def __init__(self, category: str, commands: List, parent=None):
        super().__init__(category, parent)
        self.category = category
        self.parent_window = parent
        self.parameter_manager = EmClarityParameters()
        self.setup_command_panels(commands)
        self.setup_parameter_panel()
        
    def setup_command_panels(self, commands):
        """Setup command panels for this category."""
        for command in commands:
            panel = CollapsibleCommandPanel(
                command.name,
                command.description,
                command.parameters,
                self
            )
            panel.run_command.connect(self.handle_command)
            panel.expansion_changed.connect(lambda expanded, name=command.name: self.handle_panel_expansion(name, expanded))
            self.add_command_panel(panel)
    
    def setup_parameter_panel(self):
        """Setup parameter configuration panel."""
        # Get parameters for this tab/category
        parameters = self.parameter_manager.get_parameters_for_tab(self.category)
        
        if parameters:
            param_panel = ParameterConfigPanel(self.category, parameters, self)
            param_panel.parameter_changed.connect(self.handle_parameter_change)
            self.set_parameter_panel(param_panel)
            
    def handle_command(self, command_name: str, arguments: List[str]):
        """Handle command execution request."""
        if hasattr(self.parent_window, 'run_emclarity_command'):
            # Get current parameter values for context
            param_values = {}
            if self.parameter_panel:
                param_values = self.parameter_panel.get_parameter_values()
            
            # Include parameter context in command execution
            self.parent_window.run_emclarity_command(command_name, arguments, param_values)
    
    def handle_parameter_change(self, param_name: str, value):
        """Handle parameter value change."""
        # Schedule state save when parameters change
        if hasattr(self.parent_window, 'schedule_state_save'):
            self.parent_window.schedule_state_save()
    
    def handle_panel_expansion(self, panel_name: str, expanded: bool):
        """Handle expansion/collapse of command panels."""
        if not hasattr(self, 'expanded_panels'):
            self.expanded_panels = set()
            
        if expanded:
            self.expanded_panels.add(panel_name)
        else:
            self.expanded_panels.discard(panel_name)
            
        # Schedule state save when panel states change
        if hasattr(self.parent_window, 'schedule_state_save'):
            self.parent_window.schedule_state_save()
    
    def restore_panel_states(self, expanded_panels):
        """Restore the expansion state of panels."""
        self.expanded_panels = set(expanded_panels) if expanded_panels else set()
        
        # Apply expansion states to panels
        if hasattr(self, 'content_layout'):
            for i in range(self.content_layout.count()):
                widget = self.content_layout.itemAt(i).widget()
                if hasattr(widget, 'set_expanded') and hasattr(widget, 'command_name'):
                    should_expand = widget.command_name in self.expanded_panels
                    widget.set_expanded(should_expand)


class EmClarityWindow(QMainWindow):
    """Modern emClarity GUI window with tabbed interface."""
    
    def __init__(self):
        super().__init__()
        
        # Initialize state manager
        self.state_manager = GUIStateManager()
        
        # Setup auto-save timer for state (needed early for UI setup)
        self.state_save_timer = QTimer()
        self.state_save_timer.timeout.connect(self.save_current_state)
        self.state_save_timer.setSingleShot(True)
        
        # Load and apply saved state
        self.load_saved_state()
        
        # Initialize components
        self.config = None
        self.command_runner = None
        self.parameter_manager = EmClarityParameters()
        
        # Setup UI
        self.setup_ui()
        self.setup_styling()
        
        # Load configuration
        self.load_config()
    
    def load_saved_state(self):
        """Load and apply previously saved GUI state."""
        try:
            window_state = self.state_manager.load_window_state()
            if window_state:
                # Apply geometry (will be set after show())
                self.saved_geometry = window_state.get('geometry')
                self.saved_font_size = window_state.get('font_size', 10)
                self.saved_keep_on_top = window_state.get('keep_on_top', False)
                self.saved_splitter_sizes = window_state.get('splitter_sizes', '')
            else:
                self.saved_geometry = None
                self.saved_font_size = 10
                self.saved_keep_on_top = False
                self.saved_splitter_sizes = ''
        except Exception as e:
            print(f"Error loading saved state: {e}")
            self.saved_geometry = None
            self.saved_font_size = 10
            self.saved_keep_on_top = False
            self.saved_splitter_sizes = ''
    
    def save_current_state(self):
        """Save current GUI state to database."""
        try:
            # Window state
            geometry = self.saveGeometry().toHex().data().decode()
            window_state = self.saveState().toHex().data().decode()
            font_size = QApplication.instance().font().pointSize()
            keep_on_top = self.keep_on_top_checkbox.isChecked() if hasattr(self, 'keep_on_top_checkbox') else False
            
            # Get splitter sizes from current tab
            splitter_sizes = ""
            current_tab = self.tab_widget.currentWidget()
            if hasattr(current_tab, 'get_splitter_sizes'):
                splitter_sizes = current_tab.get_splitter_sizes()
            
            self.state_manager.save_window_state(
                geometry, window_state, font_size, keep_on_top, splitter_sizes
            )
            
            # Save tab states and parameters
            for i in range(self.tab_widget.count()):
                tab = self.tab_widget.widget(i)
                tab_name = self.tab_widget.tabText(i)
                
                # Tab expansion state
                expanded_panels = []
                if hasattr(tab, 'expanded_panels'):
                    expanded_panels = list(tab.expanded_panels)
                
                self.state_manager.save_tab_state(
                    tab_name, 
                    i == self.tab_widget.currentIndex(),
                    expanded_panels
                )
                
                # Parameter values
                if hasattr(tab, 'parameter_panel') and tab.parameter_panel:
                    params = tab.parameter_panel.get_parameter_values()
                    if params:
                        self.state_manager.save_parameter_values(tab_name, params)
                        
        except Exception as e:
            print(f"Error saving state: {e}")
    
    def schedule_state_save(self):
        """Schedule a state save (debounced to avoid too frequent saves)."""
        self.state_save_timer.stop()
        self.state_save_timer.start(1000)  # Save after 1 second of inactivity
    
    def restore_window_state(self):
        """Restore window state after the window is shown."""
        try:
            if hasattr(self, 'saved_geometry') and self.saved_geometry:
                self.restoreGeometry(bytes.fromhex(self.saved_geometry))
            
            if hasattr(self, 'saved_font_size'):
                self.change_font_size(self.saved_font_size)
            
            if hasattr(self, 'saved_keep_on_top') and hasattr(self, 'keep_on_top_checkbox'):
                self.keep_on_top_checkbox.setChecked(self.saved_keep_on_top)
                if self.saved_keep_on_top:
                    self.toggle_keep_on_top(Qt.CheckState.Checked.value)
                    
        except Exception as e:
            print(f"Error restoring window state: {e}")
    
    def closeEvent(self, event):
        """Handle window close event - save state before closing."""
        self.save_current_state()
        super().closeEvent(event)
        
    def setup_ui(self):
        """Setup the main UI."""
        self.setWindowTitle("emClarity GUI")
        self.setGeometry(100, 100, 1500, 1050)
        
        # Setup menu bar
        self.setup_menu_bar()
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Header with version info
        self.setup_header(main_layout)

        # Project path label
        self.project_path_label = QLabel("No project open.")
        self.project_path_label.setStyleSheet("font-style: italic; color: gray;")
        main_layout.addWidget(self.project_path_label)
        
        # Main content splitter (vertical)
        content_splitter = QSplitter(Qt.Vertical)
        
        # Tabbed interface
        self.tab_widget = QTabWidget()
        self.setup_tabs()
        self.tab_widget.setEnabled(False) # Disable tabs initially
        content_splitter.addWidget(self.tab_widget)
        
        # Output panel
        self.setup_output_panel(content_splitter)
        
        
        # Set content splitter proportions
        content_splitter.setSizes([400, 150, 100])
        main_layout.addWidget(content_splitter)
        
        # Apply styling
        self.setup_styling()
        
        # Load saved state
        self.load_saved_state()
        
        # Connect signals for state saving
        self.tab_widget.currentChanged.connect(self.schedule_state_save)
        if hasattr(self, 'keep_on_top_checkbox'):
            self.keep_on_top_checkbox.toggled.connect(self.schedule_state_save)
    
    def showEvent(self, event):
        """Handle show event - restore saved state after window is visible."""
        super().showEvent(event)
        if not hasattr(self, '_state_restored'):
            self.restore_window_state()
            self._state_restored = True
            
            # Auto-open project dialog on first show
            QTimer.singleShot(100, self.auto_open_project)
    
    def auto_open_project(self):
        """Automatically open project dialog when GUI starts."""
        if not hasattr(self, 'project_path'):
            self.open_project()
        
    def setup_header(self, layout):
        """Setup header with version information."""
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        
        # Title
        title = QLabel("emClarity GUI")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Keep on top toggle
        self.keep_on_top_checkbox = QCheckBox("Keep on Top")
        self.keep_on_top_checkbox.setToolTip("Keep this window on top of all other windows")
        self.keep_on_top_checkbox.stateChanged.connect(self.toggle_keep_on_top)
        header_layout.addWidget(self.keep_on_top_checkbox)
        
        # Debug toggle
        self.debug_checkbox = QCheckBox("Debug Mode")
        self.debug_checkbox.setToolTip("Enable debug output in console")
        header_layout.addWidget(self.debug_checkbox)
        
        # Add some spacing
        header_layout.addSpacing(20)
        
        # Version info (will be populated later)
        self.version_label = QLabel("Loading...")
        header_layout.addWidget(self.version_label)
        
        layout.addWidget(header_widget)
        
    def setup_menu_bar(self):
        """Setup the menu bar with View menu for font size control."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        open_project_action = QAction("Open Project...", self)
        open_project_action.triggered.connect(self.open_project)
        file_menu.addAction(open_project_action)

        # View menu
        view_menu = menubar.addMenu("&View")
        
        # Font size submenu
        font_menu = view_menu.addMenu("Font Size")
        
        # Parameters menu
        params_menu = menubar.addMenu("&Parameters")
        
        # Load example parameters action
        load_example_action = QAction("Load Example Parameters", self)
        load_example_action.setToolTip("Load example parameters based on gen_param.m")
        load_example_action.triggered.connect(self.load_example_parameters)
        params_menu.addAction(load_example_action)
        
        # Export all parameters action
        export_all_action = QAction("Export All Parameters", self)
        export_all_action.setToolTip("Export parameters from all tabs to a single file")
        export_all_action.triggered.connect(self.export_all_parameters)
        params_menu.addAction(export_all_action)
        
        # Font size options
        font_sizes = [8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24]
        current_font_size = QApplication.instance().font().pointSize()
        if current_font_size not in font_sizes:
            current_font_size = 10  # default
        
        self.font_size_actions = []
        for size in font_sizes:
            action = QAction(f"{size}pt", self)
            action.setCheckable(True)
            if size == current_font_size:
                action.setChecked(True)
            action.triggered.connect(lambda checked, s=size: self.change_font_size(s))
            font_menu.addAction(action)
            self.font_size_actions.append(action)
    
    def change_font_size(self, size):
        """Change the font size for the entire GUI."""
        # Update all font size actions to reflect the new selection
        for action in self.font_size_actions:
            action.setChecked(False)
        
        # Find and check the selected size action
        for action in self.font_size_actions:
            if action.text() == f"{size}pt":
                action.setChecked(True)
                break
        
        # Create new font with the selected size
        new_font = QFont()
        new_font.setPointSize(size)
        
        # Apply to the entire application
        QApplication.instance().setFont(new_font)
        
        # Force update of all widgets
        self.update()
    
    def load_example_parameters(self):
        """Load example parameters from gen_param.m file."""
        try:
            # Example parameters based on the gen_param.m file
            example_params = {
                'subTomoMeta': 'full_enchilada_2_1_branch_5',
                'nGPUs': 4,
                'nCpuCores': 16,
                'n_tilt_workers': 4,
                'fastScratchDisk': 'ram',
                'PIXEL_SIZE': 2.50e-10,
                'Cs': 2.7e-3,
                'VOLTAGE': 300e3,
                'AMPCONT': 0.04,
                'defEstimate': 3.5e-6,
                'defWindow': 1.75e-6,
                'defCutOff': 6e-10,
                'max_ctf3dDepth': 100e-9,
                'whitenPS': [0, 0, 0.5],
                'Ali_samplingRate': 3,
                'Ali_mType': 'cylinder',
                'Ali_mRadius': [220, 220, 164],
                'Ali_mCenter': [0, 0, 0],
                'symmetry': 'C12',
                'particleRadius': [180, 180, 150],
                'particleMass': 3.2,
                'Cls_mType': 'cylinder',
                'Cls_mRadius': [220, 220, 164],
                'Cls_mCenter': [0, 0, 0],
                'Cls_samplingRate': 3,
                'Peak_mType': 'cylinder',
                'Peak_mRadius': [40, 40, 40],
                'Tmp_samplingRate': 5,
                'Tmp_bandpass': [0.01, 1200, 25],
                'Tmp_threshold': 1500,
                'Tmp_angleSearch': [180, 12, 180, 12],
                'Tmp_targetSize': [512, 512, 768],
                'nPeaks': 1,
                'Fsc_bfactor': 10,
                'CUM_e_DOSE': 180,
                'beadDiameter': 10e-9,
                'startingDirection': 'pos',
            }
            
            # Apply parameters to all tabs
            for i in range(self.tab_widget.count()):
                tab = self.tab_widget.widget(i)
                if hasattr(tab, 'parameter_panel') and tab.parameter_panel:
                    # Filter parameters for this tab
                    tab_params = {}
                    for param_name, value in example_params.items():
                        if param_name in tab.parameter_panel.param_widgets:
                            tab_params[param_name] = value
                    
                    if tab_params:
                        tab.parameter_panel.set_parameter_values(tab_params)
            
            QMessageBox.information(self, "Success", "Example parameters loaded successfully!")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load example parameters:\n{str(e)}")
    
    def export_all_parameters(self):
        """Export parameters from all tabs to a single parameter file."""
        try:
            # Collect parameters from all tabs
            all_params = {}
            tab_names = []
            
            for i in range(self.tab_widget.count()):
                tab = self.tab_widget.widget(i)
                tab_name = self.tab_widget.tabText(i)
                tab_names.append(tab_name)
                
                if hasattr(tab, 'parameter_panel') and tab.parameter_panel:
                    params = tab.parameter_panel.get_parameter_values()
                    all_params.update(params)
            
            if not all_params:
                QMessageBox.warning(self, "Warning", "No parameters to export")
                return
            
            # Create parameter file
            param_manager = EmClarityParameters()
            content, filename = param_manager.create_parameter_file(all_params, "gui_export")
            
            # Save file dialog
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Export All Parameters", filename, "MATLAB files (*.m);;All files (*)"
            )
            
            if save_path:
                with open(save_path, 'w') as f:
                    f.write(content)
                QMessageBox.information(self, "Success", 
                    f"Parameters from {len(tab_names)} tabs exported to {save_path}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export parameters:\n{str(e)}")
        
    def setup_tabs(self):
        """Setup all tabs using dynamic command system."""
        commands_obj = EmClarityCommands()
        categories = commands_obj.get_commands_by_category()
        
        # Define tab order (user requested order)
        tab_order = [
            'TiltSeriesAssets',  # New tab for asset management
            'Alignment', 
            'CTF', 
            'Template Search', 
            'Processing', 
            'Reconstruction', 
            'Utilities',
            'System',
            'Project Setup'
        ]
        
        for category in tab_order:
            if category == 'TiltSeriesAssets':
                tab = TiltSeriesAssetsWidget(self)
                self.tab_widget.addTab(tab, "Tilt-Series Assets")
            elif category in categories:
                if category == 'System':
                    tab = QWidget()
                    layout = QVBoxLayout(tab)
                    layout.addWidget(RunProfileWidget(self))
                    self.tab_widget.addTab(tab, "System")
                elif category == 'Alignment':
                    tab = AutoAlignWidget(self)
                    self.tab_widget.addTab(tab, "Tilt-Series Alignment")
                else:
                    tab = DynamicCommandTab(category, categories[category], self)
                    self.tab_widget.addTab(tab, category)
        
        # Restore saved tab states after all tabs are created
        self.restore_tab_states()
        
    def restore_tab_states(self):
        """Restore saved states for all tabs."""
        try:
            for i in range(self.tab_widget.count()):
                tab = self.tab_widget.widget(i)
                tab_name = self.tab_widget.tabText(i)
                
                # Load tab state
                tab_state = self.state_manager.load_tab_state(tab_name)
                if tab_state:
                    # Restore expanded panels
                    expanded_panels = tab_state.get('expanded_panels', [])
                    if hasattr(tab, 'restore_panel_states'):
                        tab.restore_panel_states(expanded_panels)
                    
                    # Restore parameter values
                    params = self.state_manager.load_parameter_values(tab_name)
                    if params and hasattr(tab, 'parameter_panel') and tab.parameter_panel:
                        tab.parameter_panel.set_parameter_values(params)
                        
                    # Set active tab if it was active before
                    if tab_state.get('is_active', False):
                        self.tab_widget.setCurrentIndex(i)
                        
        except Exception as e:
            print(f"Error restoring tab states: {e}")
        
    def setup_output_panel(self, splitter):
        """Setup output panel for command results."""
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        
        output_layout.addWidget(QLabel("Command Output:"))
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumHeight(200)
        output_layout.addWidget(self.output_text)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        output_layout.addWidget(self.progress_bar)
        
        splitter.addWidget(output_widget)
        
    def setup_styling(self):
        """Setup modern styling."""
        # Set larger default font
        font = QFont()
        font.setPointSize(11)
        self.setFont(font)
        
        # Modern color scheme with softer blues and rounded tabs
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QTabWidget::pane {
                border: 1px solid #d0d0d0;
                background-color: white;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #f0f0f0, stop: 1 #e5e5e5);
                border: 1px solid #d0d0d0;
                padding: 10px 18px;
                margin-right: 1px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                min-width: 80px;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 white, stop: 1 #f8f8f8);
                border-bottom-color: white;
                margin-bottom: -1px;
            }
            QTabBar::tab:hover:!selected {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #f5f5f5, stop: 1 #e8e8e8);
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #d5d5d5;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px 0 8px;
                background-color: #f5f5f5;
            }
            QPushButton {
                background-color: #4A90E2;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #357ABD;
            }
            QPushButton:pressed {
                background-color: #2E6DA4;
            }
            QLineEdit, QComboBox, QSpinBox {
                padding: 6px;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                background-color: white;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 2px solid #4A90E2;
            }
            QTextEdit {
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                background-color: white;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                background-color: white;
                border: 2px solid #d0d0d0;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #4A90E2;
                border: 2px solid #4A90E2;
                border-radius: 3px;
            }
            QToolTip {
                background-color: #ffffcc;
                border: 1px solid #b8b8b8;
                color: #000000;
                font-size: 16px;
                padding: 8px;
                border-radius: 4px;
                opacity: 230;
            }
        """)
        
    def toggle_keep_on_top(self, state):
        """Toggle the keep on top window flag."""
        if state == Qt.CheckState.Checked.value:
            # Set window to stay on top
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        else:
            # Remove stay on top flag
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
        
        # Show the window again as changing flags hides it
        self.show()
        
    def load_config(self):
        """Load emClarity configuration."""
        try:
            self.config = get_default_config()
            version_info = self.config.get_version_info()
            
            self.version_label.setText(
                f"emClarity {version_info['version']} | {version_info['root']}"
            )
            
        except Exception as e:
            self.version_label.setText(f"Configuration Error: {str(e)}")
            self.version_label.setStyleSheet("color: red;")
    
    def handle_workflow_step(self, step_id: str, tab_name: str):
        """Handle workflow step selection - switch to appropriate tab."""
        pass
            
    def run_emclarity_command(self, command: str, args: List[str] = None, param_values: Dict[str, Any] = None):
        """Run an emClarity command with optional parameter context."""
        if not self.config:
            QMessageBox.warning(self, "Warning", "emClarity configuration not loaded")
            return
        
        try:
            # If parameter values provided, could create a parameter file
            param_file_path = None
            if param_values:
                # Create temporary parameter file for this command
                param_manager = EmClarityParameters()
                content, filename = param_manager.create_parameter_file(param_values, command)
                
                # Save to temporary location (could be in project directory)
                import tempfile
                import os
                temp_dir = tempfile.gettempdir()
                param_file_path = os.path.join(temp_dir, filename)
                
                with open(param_file_path, 'w') as f:
                    f.write(content)
                
                self.output_text.append(f"Created parameter file: {param_file_path}")
            
            # Build command
            cmd_parts = [self.config.binary_path, command]
            if args:
                cmd_parts.extend(args)
            
            # Add parameter file to command if created
            if param_file_path:
                cmd_parts.append(param_file_path)
                
            self.output_text.append(f"\n> Running: {' '.join(cmd_parts)}")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            
            # Run command in thread
            self.command_runner = CommandRunner(cmd_parts)
            self.command_runner.output_ready.connect(self.on_command_output)
            self.command_runner.error_ready.connect(self.on_command_error)
            self.command_runner.finished_signal.connect(self.on_command_finished)
            self.command_runner.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to run command: {str(e)}")
            self.progress_bar.setVisible(False)
            
    def on_command_output(self, output: str):
        """Handle command output."""
        self.output_text.append(output)
        
    def on_command_error(self, error: str):
        """Handle command error."""
        self.output_text.append(f"ERROR: {error}")
        
    def on_command_finished(self, return_code: int):
        """Handle command completion."""
        self.progress_bar.setVisible(False)
        if return_code == 0:
            self.output_text.append("Command completed successfully.")
        else:
            self.output_text.append(f"Command failed with return code {return_code}")
            
        # Scroll to bottom
        cursor = self.output_text.textCursor()
        cursor.movePosition(cursor.End)
        self.output_text.setTextCursor(cursor)

    def debug_output(self, message: str):
        """Output debug message if debug mode is enabled."""
        if hasattr(self, 'debug_checkbox') and self.debug_checkbox.isChecked():
            self.output_text.append(f"DEBUG: {message}")
            # Scroll to bottom
            cursor = self.output_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.output_text.setTextCursor(cursor)
    
    def debug_output_end_method(self):
        """Add spacing after a method's debug output."""
        if hasattr(self, 'debug_checkbox') and self.debug_checkbox.isChecked():
            self.output_text.append("")  # Add empty line for spacing

    def open_project(self):
        """Open a project directory."""
        dir_path = ProjectDialog.get_project_path(self)
        if dir_path:
            project_path = Path(dir_path)
            if not os.access(project_path, os.W_OK):
                QMessageBox.warning(self, "Permission Denied", "The selected directory is not writable.")
                return

            self.project_path = project_path
            self.project_path_label.setText(f"Project: {self.project_path}")
            self.project_path_label.setStyleSheet("")  # Reset style
            self.tab_widget.setEnabled(True)
            self.setWindowTitle(f"emClarity GUI - {self.project_path.name}")
            
            # Notify all tabs that a project has been opened
            self.notify_tabs_project_opened()
            
    def notify_tabs_project_opened(self):
        """Notify all tabs that a project has been opened so they can load their data."""
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            
            # Check if the widget has a method to handle project opening
            if hasattr(widget, 'on_project_opened'):
                try:
                    widget.on_project_opened()
                except Exception as e:
                    print(f"Error notifying tab {i} of project opening: {e}")
            
            # For nested widgets (like System tab with RunProfileWidget)
            if hasattr(widget, 'layout') and widget.layout():
                for j in range(widget.layout().count()):
                    child_widget = widget.layout().itemAt(j).widget()
                    if child_widget and hasattr(child_widget, 'on_project_opened'):
                        try:
                            child_widget.on_project_opened()
                        except Exception as e:
                            print(f"Error notifying child widget of project opening: {e}")

def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    window = EmClarityWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
