"""
Settings Panel for emClarity GUI

This module provides the Settings panel interface for managing run profiles,
configuration settings, and process management.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class ProfileManagementPanel(QWidget):
    """Left panel for managing run profiles."""

    profile_selected = Signal(str)
    profile_action = Signal(str, str)  # (action, profile_name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Profiles list
        profiles_group = QGroupBox("Run Profiles")
        profiles_layout = QVBoxLayout(profiles_group)

        self.profiles_list = QListWidget()
        self.profiles_list.setMaximumWidth(230)
        self.profiles_list.setMinimumWidth(200)

        # Add sample profiles
        sample_profiles = [
            "Default Local",
            "gpu",
            "recon",
            "all_gpu",
            "all_gpu_low_sampling",
            "salina",
            "Copy of Copy of all_gpu_low_sampling",
            "single",
            "TMsask",
            "Default Local",
            "debug",
            "CPU",
            "Copy of TMsask",
            "recon",
        ]

        for profile in sample_profiles:
            self.profiles_list.addItem(profile)

        # Select first item (Default Local)
        if self.profiles_list.count() > 0:
            self.profiles_list.setCurrentRow(0)

        # Connect selection signal
        self.profiles_list.currentTextChanged.connect(self.profile_selected.emit)

        profiles_layout.addWidget(self.profiles_list)
        layout.addWidget(profiles_group)

        # Profile management buttons
        buttons_group = QGroupBox("Profile Management")
        buttons_layout = QVBoxLayout(buttons_group)

        # Management buttons
        button_configs = [
            ("Add", self.on_add_profile),
            ("Rename", self.on_rename_profile),
            ("Remove", self.on_remove_profile),
            ("Duplicate", self.on_duplicate_profile),
            ("Import", self.on_import_profile),
            ("Export", self.on_export_profile),
        ]

        self.management_buttons = {}
        for label, callback in button_configs:
            button = QPushButton(label)
            button.setMinimumHeight(28)
            button.clicked.connect(callback)
            self.management_buttons[label.lower()] = button
            buttons_layout.addWidget(button)

        layout.addWidget(buttons_group)
        layout.addStretch()

    # Button callbacks (stub implementations)
    def on_add_profile(self):
        print("Add profile clicked (stub)")
        self.profile_action.emit("add", "")

    def on_rename_profile(self):
        current = self.profiles_list.currentItem()
        if current:
            print(f"Rename profile: {current.text()} (stub)")
            self.profile_action.emit("rename", current.text())

    def on_remove_profile(self):
        current = self.profiles_list.currentItem()
        if current:
            print(f"Remove profile: {current.text()} (stub)")
            self.profile_action.emit("remove", current.text())

    def on_duplicate_profile(self):
        current = self.profiles_list.currentItem()
        if current:
            print(f"Duplicate profile: {current.text()} (stub)")
            self.profile_action.emit("duplicate", current.text())

    def on_import_profile(self):
        print("Import profile clicked (stub)")
        self.profile_action.emit("import", "")

    def on_export_profile(self):
        current = self.profiles_list.currentItem()
        if current:
            print(f"Export profile: {current.text()} (stub)")
            self.profile_action.emit("export", current.text())


class BasicSettingsPanel(QWidget):
    """Panel for basic configuration settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        # Basic settings group
        settings_group = QGroupBox("Basic Settings")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(12)

        # Total processes
        processes_layout = QHBoxLayout()
        processes_label = QLabel("Total Number of Processes :")
        processes_value = QLabel("16")
        processes_value.setFont(QFont("Arial", 10, QFont.Bold))
        processes_layout.addWidget(processes_label)
        processes_layout.addWidget(processes_value)
        processes_layout.addStretch()
        settings_layout.addLayout(processes_layout)

        # Manager command
        manager_layout = QVBoxLayout()
        manager_label = QLabel("Manager Command :")
        manager_label.setFont(QFont("Arial", 10, QFont.Bold))
        self.manager_command = QLineEdit()
        self.manager_command.setText(
            "/usr/local/matlab/R2023a/bin/matlab -nodisplay -nosplash -r"
        )
        self.manager_command.setMinimumHeight(30)
        manager_layout.addWidget(manager_label)
        manager_layout.addWidget(self.manager_command)
        settings_layout.addLayout(manager_layout)

        # GUI Address
        gui_layout = QHBoxLayout()
        gui_label = QLabel("GUI Address : Automatic")
        gui_add_btn = QPushButton("Add")
        gui_specify_btn = QPushButton("Specify")
        gui_add_btn.setMaximumWidth(60)
        gui_specify_btn.setMaximumWidth(60)
        gui_layout.addWidget(gui_label)
        gui_layout.addStretch()
        gui_layout.addWidget(gui_add_btn)
        gui_layout.addWidget(gui_specify_btn)
        settings_layout.addLayout(gui_layout)

        # Controller Address
        controller_layout = QHBoxLayout()
        controller_label = QLabel("Controller Address : Automatic")
        controller_add_btn = QPushButton("Add")
        controller_specify_btn = QPushButton("Specify")
        controller_add_btn.setMaximumWidth(60)
        controller_specify_btn.setMaximumWidth(60)
        controller_layout.addWidget(controller_label)
        controller_layout.addStretch()
        controller_layout.addWidget(controller_add_btn)
        controller_layout.addWidget(controller_specify_btn)
        settings_layout.addLayout(controller_layout)

        layout.addWidget(settings_group)


class CommandsTablePanel(QWidget):
    """Panel for commands table and controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Commands table group
        table_group = QGroupBox("Commands Configuration")
        table_layout = QVBoxLayout(table_group)

        # Commands table
        self.commands_table = QTableWidget()

        # Set up columns
        columns = [
            "Command",
            "No. Copies",
            "No. Threads Per Copy",
            "Override Total No. Copies?",
            "Override Total No. Copies?",  # Appears twice in spec
            "Launch Delay (ms)",
        ]

        self.commands_table.setColumnCount(len(columns))
        self.commands_table.setHorizontalHeaderLabels(columns)

        # Configure table properties
        self.commands_table.setAlternatingRowColors(True)
        self.commands_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.commands_table.setSelectionMode(QAbstractItemView.SingleSelection)

        # Add sample row with blue highlighting
        self.commands_table.setRowCount(1)
        sample_data = ["emClarity", "1", "4", "No", "No", "0"]

        for col, value in enumerate(sample_data):
            item = QTableWidgetItem(value)
            self.commands_table.setItem(0, col, item)

        # Select the row to give it blue highlighting
        self.commands_table.selectRow(0)

        # Resize columns
        header = self.commands_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        # Set minimum height to show the row + headers + some space
        self.commands_table.setMinimumHeight(120)
        self.commands_table.setMaximumHeight(200)

        table_layout.addWidget(self.commands_table)

        # Table controls
        controls_layout = QHBoxLayout()

        self.add_button = QPushButton("Add")
        self.edit_button = QPushButton("Edit")
        self.remove_button = QPushButton("Remove")

        # Connect button signals
        self.add_button.clicked.connect(self.on_add_command)
        self.edit_button.clicked.connect(self.on_edit_command)
        self.remove_button.clicked.connect(self.on_remove_command)

        controls_layout.addWidget(self.add_button)
        controls_layout.addWidget(self.edit_button)
        controls_layout.addWidget(self.remove_button)
        controls_layout.addStretch()

        # Control input on the right
        self.control_input = QLineEdit()
        self.control_input.setPlaceholderText("Command input...")
        self.control_input.setMaximumWidth(150)
        controls_layout.addWidget(self.control_input)

        table_layout.addLayout(controls_layout)
        layout.addWidget(table_group)

        # Add stretch to take up remaining space
        layout.addStretch()

    # Table control callbacks (stub implementations)
    def on_add_command(self):
        print("Add command clicked (stub)")

    def on_edit_command(self):
        print("Edit command clicked (stub)")

    def on_remove_command(self):
        print("Remove command clicked (stub)")


class ConfigurationPanel(QWidget):
    """Right panel containing configuration settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(20)

        # Basic settings
        self.basic_settings = BasicSettingsPanel()
        layout.addWidget(self.basic_settings)

        # Commands table
        self.commands_table_panel = CommandsTablePanel()
        layout.addWidget(self.commands_table_panel)


class SettingsPanel(QWidget):
    """Main Settings panel combining all components."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent  # Store reference to main window
        self.current_settings_type = "general"  # Default selection
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Top header section
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 5, 10, 5)

        # Run Profiles button (highlighted/selected)
        self.run_profiles_button = QToolButton()
        self.run_profiles_button.setText("⚙️ Run Profiles")
        self.run_profiles_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.run_profiles_button.setCheckable(True)
        self.run_profiles_button.setChecked(True)
        self.run_profiles_button.setMinimumHeight(35)
        self.run_profiles_button.setStyleSheet(
            """
            QToolButton {
                background-color: #0078D4;
                color: white;
                border: 2px solid #106EBE;
                border-radius: 6px;
                font-weight: bold;
                padding: 6px 12px;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: #106EBE;
            }
        """
        )

        header_layout.addWidget(self.run_profiles_button)
        header_layout.addStretch()

        layout.addWidget(header_widget)

        # Main content area - use a stacked widget for different panels
        self.content_stack = QStackedWidget()

        # Default view for run_profiles: Legacy tabbed interface (migrated from experimental)
        legacy_panel = self._create_legacy_interface_panel()
        self.content_stack.addWidget(legacy_panel)

        layout.addWidget(self.content_stack)

    def _create_legacy_interface_panel(self):
        """Create the legacy tabbed interface panel (migrated from experimental)."""
        try:
            from autoalign_widget import AutoAlignWidget as OriginalAutoAlignWidget
            from commands import EmClarityCommands
            from main import DynamicCommandTab
            from profile_widgets import RunProfileWidget
            from PySide6.QtWidgets import QTabWidget
            from tilt_series_assets import (
                TiltSeriesAssetsWidget as OriginalTiltSeriesWidget,
            )

            legacy_panel = QWidget()
            legacy_layout = QVBoxLayout(legacy_panel)

            # Add a header
            header_label = QLabel("Legacy Interface - Run Profiles & System Management")
            header_font = QFont()
            header_font.setPointSize(14)
            header_font.setBold(True)
            header_label.setFont(header_font)
            header_label.setStyleSheet("color: #333333; margin: 10px; padding: 10px;")
            legacy_layout.addWidget(header_label)

            # Create the tabbed widget
            tab_widget = QTabWidget()
            tab_widget.setStyleSheet(
                """
                QTabWidget::pane {
                    border: 1px solid #d0d0d0;
                    background-color: white;
                    border-radius: 6px;
                }
                QTabBar::tab {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                              stop: 0 #f0f0f0, stop: 1 #e5e5e5);
                    border: 1px solid #d0d0d0;
                    padding: 8px 12px;
                    margin-right: 1px;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    min-width: 60px;
                    font-size: 10px;
                }
                QTabBar::tab:selected {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                              stop: 0 white, stop: 1 #f8f8f8);
                    border-bottom-color: white;
                    margin-bottom: -1px;
                }
            """
            )

            # Primary tab: Run Profiles (from the System tab in experimental)
            run_profiles_tab = QWidget()
            run_profiles_layout = QVBoxLayout(run_profiles_tab)

            # Add description for run profiles
            desc_label = QLabel(
                "Manage computational resources and execution profiles for emClarity workflows."
            )
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet(
                "color: #666; font-style: italic; margin: 5px; padding: 5px;"
            )
            run_profiles_layout.addWidget(desc_label)

            # Add the actual RunProfileWidget
            run_profiles_layout.addWidget(RunProfileWidget(self.main_window))
            tab_widget.addTab(run_profiles_tab, "Run Profiles")

            # Add other legacy tabs for comprehensive system management
            commands_obj = EmClarityCommands()
            categories = commands_obj.get_commands_by_category()

            # Add asset management tab
            tab_widget.addTab(OriginalTiltSeriesWidget(self.main_window), "Assets")

            # Add alignment tab
            tab_widget.addTab(OriginalAutoAlignWidget(self.main_window), "Alignment")

            # Add a few other important tabs for legacy interface
            for category in ["CTF", "Processing", "Reconstruction"]:
                if category in categories:
                    tab = DynamicCommandTab(
                        category, categories[category], self.main_window
                    )
                    tab_widget.addTab(tab, category)

            legacy_layout.addWidget(tab_widget)

            return legacy_panel

        except ImportError as e:
            print(f"Could not load legacy interface for run profiles: {e}")
            # Fallback to simple RunProfileWidget
            fallback_panel = QWidget()
            fallback_layout = QVBoxLayout(fallback_panel)

            header_label = QLabel("Run Profiles")
            header_font = QFont()
            header_font.setPointSize(14)
            header_font.setBold(True)
            header_label.setFont(header_font)
            fallback_layout.addWidget(header_label)

            try:
                from profile_widgets import RunProfileWidget

                fallback_layout.addWidget(RunProfileWidget(self.main_window))
            except ImportError:
                fallback_layout.addWidget(
                    QLabel("Run Profiles widget could not be loaded")
                )

            return fallback_panel

    def connect_signals(self):
        """Connect signals between components."""
        # Note: Since we migrated to legacy interface, profile management signals
        # are now handled within the RunProfileWidget itself
        # Future signal connections can be added here as needed
        pass

    def handle_settings_type_change(self, settings_type):
        """Handle settings type selection from external toolbar."""
        if settings_type == self.current_settings_type:
            return

        print(f"Settings panel: Settings type changed to {settings_type}")
        self.current_settings_type = settings_type

        # Update panel content based on settings type
        self.update_content_for_settings_type(settings_type)

    def update_content_for_settings_type(self, settings_type):
        """Update the panel content based on selected settings type."""
        # For run_profiles, show the default view (index 0)
        if settings_type == "run_profiles":
            self.content_stack.setCurrentIndex(0)  # Show default splitter
            print("Showing Run Profiles panel")
            return

        # For other settings types, create and show under development panels
        # First check if we already have a widget for this settings type
        existing_widget = None
        for i in range(1, self.content_stack.count()):  # Skip index 0 (default)
            widget = self.content_stack.widget(i)
            if (
                hasattr(widget, "settings_type")
                and widget.settings_type == settings_type
            ):
                existing_widget = widget
                self.content_stack.setCurrentWidget(existing_widget)
                break

        if existing_widget:
            return  # Already showing the right panel

        # Create new panel for this settings type
        if settings_type == "general":
            panel = self._create_under_development_panel(
                "General Settings",
                "General application settings and preferences including themes, default behaviors, and user interface options.",
            )

        elif settings_type == "paths":
            panel = self._create_under_development_panel(
                "Path Settings",
                "Configure default paths for data directories, output locations, temporary files, and external tool executables.",
            )

        elif settings_type == "performance":
            panel = self._create_under_development_panel(
                "Performance Settings",
                "Optimize application performance with memory usage controls, threading options, and processing priorities.",
            )

        elif settings_type == "advanced":
            panel = self._create_under_development_panel(
                "Advanced Settings",
                "Advanced configuration options for power users including debug modes, experimental features, and low-level parameters.",
            )

        elif settings_type == "plugins":
            panel = self._create_under_development_panel(
                "Plugin Settings",
                "Manage plugins and extensions for emClarity including installation, updates, and configuration.",
            )
        else:
            panel = self._create_fallback_panel(
                settings_type, f"Settings for {settings_type}"
            )

        # Mark the panel with its settings type for future reference
        panel.settings_type = settings_type

        # Add and show the new panel
        self.content_stack.addWidget(panel)
        self.content_stack.setCurrentWidget(panel)
        print(f"Created and showing panel for {settings_type}")

    def _create_under_development_panel(self, feature_name, description):
        """Create an under development panel for the given feature."""
        try:
            import os
            import sys

            gui_dir = os.path.dirname(os.path.abspath(__file__))
            if gui_dir not in sys.path:
                sys.path.append(gui_dir)

            from under_development_panel import UnderDevelopmentPanel

            return UnderDevelopmentPanel(feature_name, description)
        except ImportError as e:
            print(f"Failed to load under development panel: {e}")
            return self._create_fallback_panel(feature_name, description)

    def _create_fallback_panel(self, feature_name, description):
        """Create a simple fallback panel if the under development panel can't be loaded."""
        fallback = QWidget()
        layout = QVBoxLayout(fallback)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(f"{feature_name}")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        desc = QLabel(description)
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(desc)

        dev_label = QLabel("🚧 Under Development")
        dev_label.setAlignment(Qt.AlignCenter)
        dev_label.setStyleSheet("color: #6c757d; font-size: 14px; margin-top: 20px;")
        layout.addWidget(dev_label)

        return fallback

    def on_profile_selected(self, profile_name):
        """Handle profile selection changes."""
        print(f"Profile selected: {profile_name}")
        # TODO: Load configuration for selected profile

    def on_profile_action(self, action, profile_name):
        """Handle profile management actions."""
        print(f"Profile action: {action} on {profile_name}")
        # TODO: Implement profile management logic

    def get_current_settings_type(self):
        """Get the currently selected settings type."""
        return self.current_settings_type


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    panel = SettingsPanel()
    panel.setWindowTitle("Settings Panel - emClarity")
    panel.resize(1200, 800)
    panel.show()

    sys.exit(app.exec())
