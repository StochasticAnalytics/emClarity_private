#!/usr/bin/env python3
"""
Modern emClarity GUI with tabbed interface.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import debug_instrumentation
from autoalign_widget import AutoAlignWidget
from commands import EmClarityCommands
from config import get_default_config
from parameters import EmClarityParameters
from profile_widgets import RunProfileWidget
from project_dialog import ProjectDialog
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPalette, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from rubber_band_tool import create_rubber_band_tool
from sidebar_layout import SidebarNavigationWidget
from state_manager import GUIStateManager
from tilt_series_assets import TiltSeriesAssetsWidget
from top_toolbar import TopToolbar
from widgets import (
    CollapsibleCommandPanel,
    CommandPanel,
    EnhancedTab,
    ParameterConfigPanel,
    ScrollableTab,
)

# Add gui directory to path
gui_dir = Path(__file__).parent.absolute()
if str(gui_dir) not in sys.path:
    sys.path.insert(0, str(gui_dir))


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
                cwd=self.working_dir,
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
                command.name, command.description, command.parameters, self
            )
            panel.run_command.connect(self.handle_command)
            panel.expansion_changed.connect(
                lambda expanded, name=command.name: self.handle_panel_expansion(
                    name, expanded
                )
            )
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
        if hasattr(self.parent_window, "run_emclarity_command"):
            # Get current parameter values for context
            param_values = {}
            if self.parameter_panel:
                param_values = self.parameter_panel.get_parameter_values()

            # Include parameter context in command execution
            self.parent_window.run_emclarity_command(
                command_name, arguments, param_values
            )

    def handle_parameter_change(self, param_name: str, value):
        """Handle parameter value change."""
        # Schedule state save when parameters change
        if hasattr(self.parent_window, "schedule_state_save"):
            self.parent_window.schedule_state_save()

    def handle_panel_expansion(self, panel_name: str, expanded: bool):
        """Handle expansion/collapse of command panels."""
        if not hasattr(self, "expanded_panels"):
            self.expanded_panels = set()

        if expanded:
            self.expanded_panels.add(panel_name)
        else:
            self.expanded_panels.discard(panel_name)

        # Schedule state save when panel states change
        if hasattr(self.parent_window, "schedule_state_save"):
            self.parent_window.schedule_state_save()

    def restore_panel_states(self, expanded_panels):
        """Restore the expansion state of panels."""
        self.expanded_panels = set(expanded_panels) if expanded_panels else set()

        # Apply expansion states to panels
        if hasattr(self, "content_layout"):
            for i in range(self.content_layout.count()):
                widget = self.content_layout.itemAt(i).widget()
                if hasattr(widget, "set_expanded") and hasattr(widget, "command_name"):
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
        self.rubber_band_tool = None  # Initialize rubber band tool

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
                self.saved_geometry = window_state.get("geometry")
                self.saved_font_size = window_state.get("font_size", 10)
                self.saved_keep_on_top = window_state.get("keep_on_top", False)
                self.saved_splitter_sizes = window_state.get("splitter_sizes", "")
            else:
                self.saved_geometry = None
                self.saved_font_size = 10
                self.saved_keep_on_top = False
                self.saved_splitter_sizes = ""
        except Exception as e:
            print(f"Error loading saved state: {e}")
            self.saved_geometry = None
            self.saved_font_size = 10
            self.saved_keep_on_top = False
            self.saved_splitter_sizes = ""

    def save_current_state(self):
        """Save current GUI state to database."""
        try:
            # Window state
            geometry = self.saveGeometry().toHex().data().decode()
            window_state = self.saveState().toHex().data().decode()
            font_size = QApplication.instance().font().pointSize()
            keep_on_top = (
                self.keep_on_top_checkbox.isChecked()
                if hasattr(self, "keep_on_top_checkbox")
                else False
            )

            # No splitter sizes for now with sidebar layout
            splitter_sizes = ""

            self.state_manager.save_window_state(
                geometry, window_state, font_size, keep_on_top, splitter_sizes
            )

            # Save sidebar panel state
            if hasattr(self, "sidebar_widget"):
                current_panel = self.sidebar_widget.current_panel
                self.state_manager.save_tab_state(
                    f"sidebar_{current_panel}",
                    True,  # is_active
                    [],  # no expanded_panels for sidebar
                )

        except Exception as e:
            print(f"Error saving state: {e}")

    def schedule_state_save(self):
        """Schedule a state save (debounced to avoid too frequent saves)."""
        self.state_save_timer.stop()
        self.state_save_timer.start(1000)  # Save after 1 second of inactivity

    def restore_window_state(self):
        """Restore window state after the window is shown."""
        try:
            if hasattr(self, "saved_geometry") and self.saved_geometry:
                self.restoreGeometry(bytes.fromhex(self.saved_geometry))

            if hasattr(self, "saved_font_size"):
                self.change_font_size(self.saved_font_size)

            if hasattr(self, "saved_keep_on_top") and hasattr(
                self, "keep_on_top_checkbox"
            ):
                self.keep_on_top_checkbox.setChecked(self.saved_keep_on_top)
                if self.saved_keep_on_top:
                    self.toggle_keep_on_top(Qt.CheckState.Checked.value)

        except Exception as e:
            print(f"Error restoring window state: {e}")

    def closeEvent(self, event):
        """Handle window close event - save state before closing."""
        self.save_current_state()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        """Handle key press events."""
        # Handle L key for click logging toggle (when in rubber band mode)
        if (
            hasattr(self, "rubber_band_mode")
            and self.rubber_band_mode
            and event.key() == Qt.Key_L
        ):
            print("🔑 L key detected - attempting to toggle click logging...")
            try:
                import debug_instrumentation

                result = debug_instrumentation.toggle_click_logging()
                status = "ENABLED" if result else "DISABLED"
                print(f"🎯 Click logging {status} (L key pressed)")
            except Exception as e:
                print(f"⚠️ Error toggling click logging: {e}")
                import traceback

                traceback.print_exc()
            return

        # Pass other key events to parent
        super().keyPressEvent(event)

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

        # Header with version info (simplified)
        self.setup_simplified_header(main_layout)

        # Top toolbar for asset types / panel-specific buttons
        self.top_toolbar = TopToolbar()
        self.top_toolbar.button_clicked.connect(self.handle_toolbar_button_click)
        main_layout.addWidget(self.top_toolbar)

        # Main content splitter (vertical) for sidebar + output
        content_splitter = QSplitter(Qt.Vertical)

        # Sidebar navigation widget
        self.sidebar_widget = SidebarNavigationWidget(self)
        self.sidebar_widget.panel_changed.connect(self.handle_panel_change)
        self.sidebar_widget.project_requested.connect(self.handle_project_request)
        content_splitter.addWidget(self.sidebar_widget)

        # Output panel
        self.setup_output_panel(content_splitter)

        # Set content splitter proportions (give most space to sidebar widget)
        content_splitter.setSizes([800, 150])
        main_layout.addWidget(content_splitter)

        # Apply styling
        self.setup_styling()

        # Connect signals for state saving
        if hasattr(self, "keep_on_top_checkbox"):
            self.keep_on_top_checkbox.toggled.connect(self.schedule_state_save)

    def showEvent(self, event):
        """Handle show event - restore saved state after window is visible."""
        super().showEvent(event)
        if not hasattr(self, "_state_restored"):
            self.restore_window_state()
            self._state_restored = True

            # Load configuration after window is shown
            QTimer.singleShot(100, self.load_config)

    def auto_open_project(self):
        """Automatically open project dialog when GUI starts."""
        if not hasattr(self, "project_path"):
            self.open_project()

    def setup_simplified_header(self, layout):
        """Setup simplified header with basic controls."""
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)

        # Project path label
        self.project_path_label = QLabel("No project open.")
        self.project_path_label.setStyleSheet(
            "font-style: italic; color: gray; font-size: 12px;"
        )
        header_layout.addWidget(self.project_path_label)

        header_layout.addStretch()

        # Keep on top toggle
        self.keep_on_top_checkbox = QCheckBox("Keep on Top")
        self.keep_on_top_checkbox.setToolTip(
            "Keep this window on top of all other windows"
        )
        self.keep_on_top_checkbox.stateChanged.connect(self.toggle_keep_on_top)
        header_layout.addWidget(self.keep_on_top_checkbox)

        # Debug toggle
        self.debug_checkbox = QCheckBox("Debug Mode")
        self.debug_checkbox.setToolTip("Enable debug output in console")
        header_layout.addWidget(self.debug_checkbox)

        layout.addWidget(header_widget)

    def handle_panel_change(self, panel_name: str):
        """Handle panel change in sidebar navigation."""
        print(f"Switched to panel: {panel_name}")

        # Update top toolbar for the new panel
        if hasattr(self, "top_toolbar"):
            self.top_toolbar.update_toolbar_for_panel(panel_name)

        # Schedule state save when panels change
        self.schedule_state_save()

    def handle_toolbar_button_click(self, panel_type: str, button_id: str):
        """Handle clicks from the top toolbar buttons."""
        print(f"Toolbar button clicked - Panel: {panel_type}, Button: {button_id}")

        # Forward the toolbar selection to the appropriate panel
        if hasattr(self, "sidebar_widget") and hasattr(self.sidebar_widget, "panels"):
            current_panel = self.sidebar_widget.panels.get(panel_type)
            print(f"Current panel for {panel_type}: {current_panel}")

            # Handle asset panel toolbar selections
            if panel_type == "assets" and hasattr(
                current_panel, "handle_asset_type_change"
            ):
                print(f"Calling handle_asset_type_change with button_id: {button_id}")
                current_panel.handle_asset_type_change(button_id)

            # Handle results panel toolbar selections
            elif panel_type == "results" and hasattr(
                current_panel, "handle_action_type_change"
            ):
                current_panel.handle_action_type_change(button_id)

            # Handle settings panel toolbar selections
            elif panel_type == "settings" and hasattr(
                current_panel, "handle_settings_type_change"
            ):
                current_panel.handle_settings_type_change(button_id)

            # Handle actions panel toolbar selections
            elif panel_type == "actions" and hasattr(
                current_panel, "handle_action_type_change"
            ):
                current_panel.handle_action_type_change(button_id)

            # Handle other panel types - show under development panels
            elif panel_type == "overview":
                self._show_under_development_for_button(panel_type, button_id)
            elif panel_type == "experimental":
                self._show_under_development_for_button(panel_type, button_id)

        # Schedule state save
        self.schedule_state_save()

    def _show_under_development_for_button(self, panel_type: str, button_id: str):
        """Show under development panel for the given button."""
        # Map button IDs to user-friendly names and descriptions
        button_info = {
            # Overview panel buttons
            "recent": (
                "Recent Projects",
                "Quick access to recently opened emClarity projects with preview information and project statistics.",
            ),
            "templates": (
                "Project Templates",
                "Pre-configured project templates for common workflows including ribosome, virus, and membrane protein studies.",
            ),
            "settings": (
                "Quick Settings",
                "Commonly used settings and preferences that can be quickly adjusted without going to the full settings panel.",
            ),
            # Experimental panel buttons
            "legacy": (
                "Legacy Interface",
                "Access to the original emClarity interface and legacy features for backward compatibility.",
            ),
            "debug": (
                "Debug Tools",
                "Advanced debugging tools for troubleshooting and development including log viewers and diagnostic utilities.",
            ),
            "experimental": (
                "Experimental Features",
                "Beta and experimental features that are being tested and may become part of future releases.",
            ),
            # Actions panel buttons (if not handled by the panel itself)
            "preprocess": (
                "Preprocessing",
                "Data preprocessing including drift correction, dose weighting, and quality assessment.",
            ),
            "align": (
                "Tilt-Series Alignment",
                "Align tilt-series using fiducial markers or patch tracking methods.",
            ),
            "subtomo_align": (
                "Subtomogram Alignment",
                "Align and average subtomograms for high-resolution structure determination.",
            ),
            "averaging": (
                "Averaging",
                "Generate averaged structures from aligned subtomograms with classification and refinement.",
            ),
            "classify": (
                "Classification",
                "Classify subtomograms into different structural states or conformations.",
            ),
            "reconstruct": (
                "Reconstruction",
                "Reconstruct 3D volumes from aligned tilt-series data.",
            ),
            "refine": (
                "Refinement",
                "Refine particle positions, orientations, and CTF parameters for improved resolution.",
            ),
            "validate": (
                "Validation",
                "Validate results using resolution estimation, FSC curves, and quality metrics.",
            ),
        }

        feature_name, description = button_info.get(
            button_id,
            (button_id.title(), f"Feature for {button_id} in {panel_type} panel."),
        )

        print(
            f"Showing under development panel for {panel_type} -> {button_id}: {feature_name}"
        )

        # For now, just print what would be shown
        # In a full implementation, this could create a temporary dialog or update a status area
        print(f"Would show: {feature_name}")
        print(f"Description: {description}")

    def handle_project_request(self, action: str):
        """Handle project-related requests from sidebar."""
        if action == "new":
            self.create_new_project()
        elif action == "open":
            self.open_project()
        elif action.startswith("/"):  # Assume it's a file path
            self.open_specific_project(action)

    def create_new_project(self):
        """Create a new project."""
        # For now, just open the regular project dialog
        # In the future, this could open a project creation wizard
        self.open_project()

    def open_specific_project(self, project_path: str):
        """Open a specific project by path."""
        project_path_obj = Path(project_path)
        if project_path_obj.exists() and project_path_obj.is_dir():
            if not os.access(project_path_obj, os.W_OK):
                QMessageBox.warning(
                    self, "Permission Denied", "The selected directory is not writable."
                )
                return

            self.project_path = project_path_obj
            self.project_path_label.setText(f"Project: {self.project_path}")
            self.project_path_label.setStyleSheet(
                "font-size: 12px; color: #333;"
            )  # Reset style
            self.setWindowTitle(f"emClarity GUI - {self.project_path.name}")

            # Update recent projects
            self.state_manager.save_recent_project(
                self.project_path.name, str(self.project_path), "Created via GUI"
            )

            # Refresh recent projects in sidebar
            self.sidebar_widget.refresh_recent_projects()

            # Notify panels that project has been opened
            self.sidebar_widget.notify_panels_project_opened()

            # Stay on overview panel after opening project
            self.sidebar_widget.switch_panel("overview")

        else:
            QMessageBox.warning(
                self,
                "Error",
                f"Project path does not exist or is not accessible: {project_path}",
            )

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
        self.keep_on_top_checkbox.setToolTip(
            "Keep this window on top of all other windows"
        )
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
        """Setup the menu bar with Project, Workflow, and Help menus."""
        menubar = self.menuBar()

        # Project menu
        project_menu = menubar.addMenu("&Project")

        new_project_action = QAction("New Project...", self)
        new_project_action.triggered.connect(self.create_new_project)
        project_menu.addAction(new_project_action)

        open_project_action = QAction("Open Project...", self)
        open_project_action.triggered.connect(self.open_project)
        project_menu.addAction(open_project_action)

        project_menu.addSeparator()

        # Recent projects submenu
        recent_menu = project_menu.addMenu("Recent Projects")
        self.update_recent_projects_menu(recent_menu)

        # Workflow menu
        workflow_menu = menubar.addMenu("&Workflow")

        # Add workflow actions - these can be expanded later
        assets_action = QAction("Manage Assets", self)
        assets_action.triggered.connect(
            lambda: self.sidebar_widget.switch_panel("assets")
        )
        workflow_menu.addAction(assets_action)

        actions_action = QAction("Run Actions", self)
        actions_action.triggered.connect(
            lambda: self.sidebar_widget.switch_panel("actions")
        )
        workflow_menu.addAction(actions_action)

        results_action = QAction("View Results", self)
        results_action.triggered.connect(
            lambda: self.sidebar_widget.switch_panel("results")
        )
        workflow_menu.addAction(results_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("About emClarity", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        tutorial_action = QAction("Tutorial", self)
        tutorial_action.triggered.connect(self.show_tutorial)
        help_menu.addAction(tutorial_action)

        # View menu (keeping for font size control)
        view_menu = menubar.addMenu("&View")

        # Rubber band mode toggle
        self.rubber_band_action = QAction("Toggle Rubber Band Mode", self)
        self.rubber_band_action.setCheckable(True)
        self.rubber_band_action.setToolTip(
            "Enable/disable rubber band selection tool for GUI development"
        )
        self.rubber_band_action.triggered.connect(self.toggle_rubber_band_mode)
        view_menu.addAction(self.rubber_band_action)

        view_menu.addSeparator()

        # Font size submenu
        font_menu = view_menu.addMenu("Font Size")

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

    def update_recent_projects_menu(self, menu):
        """Update the recent projects menu."""
        menu.clear()
        recent_projects = self.state_manager.get_recent_projects(5)

        if recent_projects:
            for project in recent_projects:
                action = QAction(project["path"], self)
                action.triggered.connect(
                    lambda checked, path=project["path"]: self.open_specific_project(
                        path
                    )
                )
                menu.addAction(action)
        else:
            no_recent_action = QAction("No recent projects", self)
            no_recent_action.setEnabled(False)
            menu.addAction(no_recent_action)

    def show_about(self):
        """Show about dialog."""
        version_info = "Unknown"
        if self.config:
            version_info = self.config.get_version_info()
            version_text = f"emClarity {version_info['version']}"
        else:
            version_text = "emClarity"

        QMessageBox.about(
            self,
            "About emClarity",
            f"{version_text}\n\n"
            "Computational Imaging System for Transmission Electron Microscopy\n\n"
            "For more information, visit: https://emclarity.org",
        )

    def show_tutorial(self):
        """Show tutorial information."""
        QMessageBox.information(
            self,
            "Tutorial",
            "For tutorials and documentation, please visit:\n\n"
            "https://emclarity.org\n\n"
            "Additional resources are available in the docs/ directory of your emClarity installation.",
        )

    def toggle_rubber_band_mode(self):
        """Toggle rubber band mode on/off."""
        if (
            hasattr(self, "rubber_band_tool")
            and self.rubber_band_tool
            and self.rubber_band_tool.is_active
        ):
            self.disable_rubber_band_mode()
            self.rubber_band_action.setChecked(False)
        else:
            self.enable_rubber_band_mode()
            self.rubber_band_action.setChecked(True)

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
        QMessageBox.information(
            self,
            "Info",
            "Example parameters loading not yet implemented in sidebar layout.",
        )

    def export_all_parameters(self):
        """Export parameters from all panels to a single parameter file."""
        QMessageBox.information(
            self, "Info", "Parameter export not yet implemented in sidebar layout."
        )

    # Legacy tab-related methods - keeping for potential future use
    # def setup_tabs(self):
    #     """Setup all tabs using dynamic command system - LEGACY."""
    #     pass

    # def restore_tab_states(self):
    #     """Restore saved states for all tabs - LEGACY."""
    #     pass

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
        self.setStyleSheet(
            """
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
        """
        )

    def toggle_keep_on_top(self, state):
        """Toggle the keep on top window flag."""
        if state == Qt.CheckState.Checked.value:
            # Set window to stay on top
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        else:
            # Remove stay on top flag
            self.setWindowFlags(
                self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint
            )

        # Show the window again as changing flags hides it
        self.show()

    def load_config(self):
        """Load emClarity configuration."""
        try:
            self.config = get_default_config()
            version_info = self.config.get_version_info()

            version_text = (
                f"emClarity {version_info['version']} | {version_info['root']}"
            )

            # Set version info in sidebar overview panel
            if hasattr(self, "sidebar_widget"):
                overview_panel = self.sidebar_widget.get_overview_panel()
                overview_panel.set_version_info(version_text)

        except Exception as e:
            error_text = f"Configuration Error: {str(e)}"
            if hasattr(self, "sidebar_widget"):
                overview_panel = self.sidebar_widget.get_overview_panel()
                overview_panel.set_version_info(error_text)

    def handle_workflow_step(self, step_id: str, tab_name: str):
        """Handle workflow step selection - switch to appropriate tab."""
        pass

    def run_emclarity_command(
        self, command: str, args: List[str] = None, param_values: Dict[str, Any] = None
    ):
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
                content, filename = param_manager.create_parameter_file(
                    param_values, command
                )

                # Save to temporary location (could be in project directory)
                import os
                import tempfile

                temp_dir = tempfile.gettempdir()
                param_file_path = os.path.join(temp_dir, filename)

                with open(param_file_path, "w") as f:
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
        if hasattr(self, "debug_checkbox") and self.debug_checkbox.isChecked():
            self.output_text.append(f"DEBUG: {message}")
            # Scroll to bottom
            cursor = self.output_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.output_text.setTextCursor(cursor)

    def enable_rubber_band_mode(self):
        """Enable rubber band selection tool for GUI development."""
        try:
            # Set rubber band mode flag
            self.rubber_band_mode = True

            # Initialize debug instrumentation for click tracking
            debug_instrumentation.init_rubber_band_debug(enabled=True)

            # Setup L shortcut for click logging toggle
            debug_instrumentation.setup_click_logging_shortcut(self)

            if not self.rubber_band_tool:
                self.rubber_band_tool = create_rubber_band_tool(self)
                # Setup keyboard shortcut when rubber band mode is enabled
                self.rubber_band_tool.setup_keyboard_shortcut()

            # DON'T auto-activate - wait for user to press the key
            # self.rubber_band_tool.activate()

            # Update window title to indicate rubber band mode is available
            current_title = self.windowTitle()
            if "- Rubber Band Mode" not in current_title:
                self.setWindowTitle(f"{current_title} - Rubber Band Mode")

            # Add rubber band mode indicator to output
            self.output_text.append("🎯 Rubber Band Mode READY!")
            self.output_text.append("Press ESC to activate rubber band selection tool")
            self.output_text.append("Once active: Click+Drag to select GUI regions")
            self.output_text.append(
                "Use L to toggle click logging for capturing interaction context"
            )
            self.output_text.append("Press ESC again to deactivate")
            self.output_text.append("-" * 50)

        except Exception as e:
            print(f"Error enabling rubber band mode: {e}")
            QMessageBox.warning(
                self, "Error", f"Failed to enable rubber band mode: {e}"
            )

    def disable_rubber_band_mode(self):
        """Disable rubber band selection tool."""
        if self.rubber_band_tool:
            self.rubber_band_tool.deactivate()

            # Update window title
            current_title = self.windowTitle()
            if "- Rubber Band Mode" in current_title:
                self.setWindowTitle(current_title.replace(" - Rubber Band Mode", ""))

            self.output_text.append("Rubber Band Mode deactivated.")

    def debug_output_end_method(self):
        """Add spacing after a method's debug output."""
        if hasattr(self, "debug_checkbox") and self.debug_checkbox.isChecked():
            self.output_text.append("")  # Add empty line for spacing

    def open_project(self):
        """Open a project directory."""
        dir_path = ProjectDialog.get_project_path(self)
        if dir_path:
            project_path = Path(dir_path)
            if not os.access(project_path, os.W_OK):
                QMessageBox.warning(
                    self, "Permission Denied", "The selected directory is not writable."
                )
                return

            self.project_path = project_path
            self.project_path_label.setText(f"Project: {self.project_path}")
            self.project_path_label.setStyleSheet(
                "font-size: 12px; color: #333;"
            )  # Reset style
            self.setWindowTitle(f"emClarity GUI - {self.project_path.name}")

            # Update recent projects
            self.state_manager.save_recent_project(
                self.project_path.name, str(self.project_path), "Opened via GUI"
            )

            # Refresh recent projects in sidebar
            self.sidebar_widget.refresh_recent_projects()

            # Notify panels that project has been opened
            self.sidebar_widget.notify_panels_project_opened()

            # Stay on overview panel after opening project
            self.sidebar_widget.switch_panel("overview")

    # Legacy method for tab notification - keeping for reference
    # def notify_tabs_project_opened(self):
    #     """Notify all tabs that a project has been opened - LEGACY."""
    #     pass


def main():
    """Main entry point."""
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="emClarity GUI")
    parser.add_argument(
        "--rubber-band-mode",
        action="store_true",
        help="Enable rubber band selection tool for GUI development",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = EmClarityWindow()

    # Enable rubber band mode if requested
    if args.rubber_band_mode:
        print("Starting emClarity GUI in Rubber Band Mode...")
        print("Use Click+Drag to select GUI regions for analysis")
        print("Use L to toggle click logging for capturing interaction context")
        window.enable_rubber_band_mode()

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
