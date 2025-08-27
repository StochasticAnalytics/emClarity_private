"""
Settings Panel for emClarity GUI

This module provides the Settings panel interface for managing run profiles,
configuration settings, and process management.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QSplitter, QGroupBox,
    QToolButton, QHeaderView, QAbstractItemView, QFormLayout, QSpacerItem,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


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
            "recon"
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
            ("Export", self.on_export_profile)
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
        self.manager_command.setText("/usr/local/matlab/R2023a/bin/matlab -nodisplay -nosplash -r")
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
            "Launch Delay (ms)"
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
        self.run_profiles_button.setStyleSheet("""
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
        """)
        
        header_layout.addWidget(self.run_profiles_button)
        header_layout.addStretch()
        
        layout.addWidget(header_widget)
        
        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side: Profile management
        self.profile_panel = ProfileManagementPanel()
        splitter.addWidget(self.profile_panel)
        
        # Right side: Configuration
        self.config_panel = ConfigurationPanel()
        splitter.addWidget(self.config_panel)
        
        # Set splitter proportions
        splitter.setSizes([250, 750])  # Profile panel : Configuration panel
        
        layout.addWidget(splitter)
    
    def connect_signals(self):
        """Connect signals between components."""
        # Profile selection changes
        self.profile_panel.profile_selected.connect(self.on_profile_selected)
        
        # Profile management actions
        self.profile_panel.profile_action.connect(self.on_profile_action)
    
    def handle_settings_type_change(self, settings_type):
        """Handle settings type selection from external toolbar."""
        if settings_type == self.current_settings_type:
            return
            
        print(f"Settings panel: Settings type changed to {settings_type}")
        self.current_settings_type = settings_type
        
        # TODO: Update panel content based on settings type
        self.update_content_for_settings_type(settings_type)
    
    def update_content_for_settings_type(self, settings_type):
        """Update the panel content based on selected settings type (stub)."""
        # This is a stub - in real implementation, this would show different settings panels
        
        if settings_type == "general":
            print("Loading general settings...")
            self.run_profiles_button.setText("⚙️ General Settings")
        elif settings_type == "paths":
            print("Loading path settings...")
            self.run_profiles_button.setText("📂 Path Settings")
        elif settings_type == "performance":
            print("Loading performance settings...")
            self.run_profiles_button.setText("🚀 Performance Settings")
        elif settings_type == "advanced":
            print("Loading advanced settings...")
            self.run_profiles_button.setText("🔧 Advanced Settings")
        elif settings_type == "plugins":
            print("Loading plugin settings...")
            self.run_profiles_button.setText("🔌 Plugin Settings")
    
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
