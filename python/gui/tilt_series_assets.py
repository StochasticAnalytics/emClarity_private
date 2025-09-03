"""
Tilt-Series Assets widget for emClarity GUI.

Manages tilt-series collections with import, validation, and asset tracking.
"""

import glob
import os
import subprocess
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class TiltSeriesAssetsWidget(QWidget):
    """Widget for managing tilt-series assets."""

    # Signal emitted when assets change
    assets_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.assets: Dict[str, Dict[str, Any]] = {}  # asset_name -> asset_data
        self.current_mode = "images"  # Default mode, can be changed by toolbar
        self.setup_ui()

        # Initialize groups dictionary but don't load assets until project is opened
        self.groups = {}

        # Ensure default group exists
        if "Default" not in self.groups:
            self.create_group("Default")

    def handle_asset_type_change(self, asset_type: str):
        """Handle changes from the top toolbar asset type selection."""
        print(f"Assets panel switching to mode: {asset_type}")
        self.current_mode = asset_type
        self.update_right_panel_for_mode()

    def update_right_panel_for_mode(self):
        """Update the right panel content based on current mode."""
        if hasattr(self, "right_panel_container"):
            # Clear the current right panel content
            layout = self.right_panel_container.layout()
            if layout:
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().setParent(None)
            else:
                layout = QVBoxLayout(self.right_panel_container)
                self.right_panel_container.setLayout(layout)

            # Recreate the right panel based on current mode
            if self.current_mode == "utils":
                self.create_utils_right_panel(layout)
            else:
                self.create_standard_right_panel(layout)

    def showEvent(self, event):
        """Called when the widget becomes visible - load assets if project is available."""
        super().showEvent(event)
        # Only load assets if we have a project path
        if (
            hasattr(self.parent_window, "project_path")
            and self.parent_window.project_path
        ):
            self.load_assets()

    def on_project_opened(self):
        """Called when a project is opened - load assets for the new project."""
        if (
            hasattr(self.parent_window, "project_path")
            and self.parent_window.project_path
        ):
            self.load_assets()
        else:
            print(
                "TiltSeriesAssetsWidget: No project path found or project_path is None"
            )

    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Title
        title = QLabel("Tilt-Series Assets")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Manage tilt-series collections for processing. Import from directories or select individual files.\n"
            "Assets can be reused across different processing workflows."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(desc)

        # Main content in horizontal layout
        main_layout = QHBoxLayout()

        # Left side - Asset tree and controls
        left_panel = self.create_left_panel()
        main_layout.addWidget(left_panel, 2)  # 2/3 of width

        # Right side - Container for dynamic content based on mode
        self.right_panel_container = QWidget()
        main_layout.addWidget(self.right_panel_container, 1)  # 1/3 of width

        # Initialize right panel content
        self.update_right_panel_for_mode()

        layout.addLayout(main_layout)

    def create_left_panel(self) -> QGroupBox:
        """Create the left panel with asset tree and controls."""
        group = QGroupBox("Tilt-Series Assets")
        layout = QVBoxLayout(group)

        # Asset tree
        self.assets_tree = QTreeWidget()
        self.assets_tree.setHeaderLabels(
            ["Group/Name", "Path", "Size (X,Y,Z)", "Stack", "Tilt", "Pixel Size"]
        )

        # Enable multi-selection
        self.assets_tree.setSelectionMode(QTreeWidget.ExtendedSelection)

        # Set column widths - make first column much wider for group/asset names
        self.assets_tree.setColumnWidth(0, 300)  # Wide for group/asset names
        self.assets_tree.setColumnWidth(1, 300)  # Path
        self.assets_tree.setColumnWidth(2, 120)  # Size dimensions
        self.assets_tree.setColumnWidth(3, 100)  # Stack status
        self.assets_tree.setColumnWidth(4, 100)  # Tilt status

        # Initialize groups dictionary
        self.groups = {}

        self.assets_tree.setAlternatingRowColors(True)
        self.assets_tree.itemSelectionChanged.connect(self.on_asset_selected)
        layout.addWidget(self.assets_tree)

        # Control buttons
        button_layout = QHBoxLayout()

        self.validate_button = QPushButton("Validate Selected")
        self.validate_button.clicked.connect(self.validate_selected)
        button_layout.addWidget(self.validate_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_selected)
        self.delete_button.setStyleSheet("background-color: #dc3545; color: white;")
        button_layout.addWidget(self.delete_button)

        # Add tree control buttons
        button_layout.addWidget(QLabel("|"))  # Separator

        self.collapse_all_button = QPushButton("Collapse All")
        self.collapse_all_button.clicked.connect(self.collapse_all_groups)
        self.collapse_all_button.setToolTip(
            "Collapse all groups to show only group names"
        )
        button_layout.addWidget(self.collapse_all_button)

        self.expand_all_button = QPushButton("Expand All")
        self.expand_all_button.clicked.connect(self.expand_all_groups)
        self.expand_all_button.setToolTip("Expand all groups to show individual assets")
        button_layout.addWidget(self.expand_all_button)

        layout.addLayout(button_layout)

        return group

    def create_standard_right_panel(self, layout: QVBoxLayout):
        """Create the standard right panel with asset details and import controls."""
        # Asset form
        form_group = QGroupBox("Selected Asset")
        form_layout = QFormLayout(form_group)

        # Asset name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Asset name")
        form_layout.addRow("Name:", self.name_input)

        # File path
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("File or directory path")
        form_layout.addRow("Path:", self.path_input)

        # Tilt file (if different)
        self.tilt_file_input = QLineEdit()
        self.tilt_file_input.setPlaceholderText("Auto-detected from stack name")
        form_layout.addRow("Tilt File:", self.tilt_file_input)

        # Processing status
        self.status_combo = QComboBox()
        self.status_combo.addItems(
            ["Imported", "Validated", "Aligned", "Processing", "Complete", "Error"]
        )
        form_layout.addRow("Status:", self.status_combo)

        layout.addWidget(form_group)

        # Update/Save buttons
        save_layout = QHBoxLayout()

        self.update_button = QPushButton("Update Selected")
        self.update_button.clicked.connect(self.update_selected)
        self.update_button.setEnabled(False)
        save_layout.addWidget(self.update_button)

        self.clear_button = QPushButton("Clear Form")
        self.clear_button.clicked.connect(self.clear_form)
        save_layout.addWidget(self.clear_button)

        layout.addLayout(save_layout)

        # Import controls
        import_group = QGroupBox("Import Controls")
        import_layout = QVBoxLayout(import_group)

        # Group management
        group_layout = QHBoxLayout()
        group_layout.addWidget(QLabel("Group:"))

        self.group_combo = QComboBox()
        self.group_combo.setEditable(True)
        self.group_combo.addItem("Default")
        self.group_combo.setCurrentText("Default")
        group_layout.addWidget(self.group_combo)

        self.add_group_button = QPushButton("Add Group")
        self.add_group_button.clicked.connect(self.add_group)
        group_layout.addWidget(self.add_group_button)

        import_layout.addLayout(group_layout)

        # Import type selection
        import_type_layout = QHBoxLayout()
        self.import_files_radio = QRadioButton("Select Files")
        self.import_files_radio.setChecked(True)
        self.import_directory_radio = QRadioButton("Select Directory")

        import_type_layout.addWidget(self.import_files_radio)
        import_type_layout.addWidget(self.import_directory_radio)
        import_layout.addLayout(import_type_layout)

        # Import and copy buttons
        button_layout = QHBoxLayout()

        self.import_button = QPushButton("Import into Group")
        self.import_button.clicked.connect(self.import_assets)
        button_layout.addWidget(self.import_button)

        self.copy_to_group_button = QPushButton("Copy to Group")
        self.copy_to_group_button.clicked.connect(self.copy_to_group)
        self.copy_to_group_button.setEnabled(False)
        button_layout.addWidget(self.copy_to_group_button)

        import_layout.addLayout(button_layout)

        layout.addWidget(import_group)

        # Display/Preview section
        display_group = QGroupBox("Display & Preview")
        display_layout = QVBoxLayout(display_group)

        # Display buttons
        display_button_layout = QHBoxLayout()

        self.display_button = QPushButton("Display in IMOD")
        self.display_button.clicked.connect(self.display_in_imod)
        self.display_button.setEnabled(False)
        self.display_button.setStyleSheet(
            "background-color: #28a745; color: white; font-weight: bold;"
        )
        display_button_layout.addWidget(self.display_button)

        self.refresh_button = QPushButton("Refresh Validation")
        self.refresh_button.clicked.connect(self.refresh_validation)
        display_button_layout.addWidget(self.refresh_button)

        display_layout.addLayout(display_button_layout)

        # Info display area
        self.info_display = QLabel("Select an asset to view details...")
        self.info_display.setWordWrap(True)
        self.info_display.setStyleSheet(
            """
            QLabel {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 10px;
                margin: 5px;
            }
        """
        )
        self.info_display.setMinimumHeight(100)
        display_layout.addWidget(self.info_display)

        layout.addWidget(display_group)

    def create_utils_right_panel(self, layout: QVBoxLayout):
        """Create the utils mode right panel with simplified controls."""
        # Asset form (same as standard)
        form_group = QGroupBox("Selected Asset")
        form_layout = QFormLayout(form_group)

        # Asset name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Asset name")
        form_layout.addRow("Name:", self.name_input)

        # File path
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("File or directory path")
        form_layout.addRow("Path:", self.path_input)

        # Tilt file (if different)
        self.tilt_file_input = QLineEdit()
        self.tilt_file_input.setPlaceholderText("Auto-detected from stack name")
        form_layout.addRow("Tilt File:", self.tilt_file_input)

        # Processing status
        self.status_combo = QComboBox()
        self.status_combo.addItems(
            ["Imported", "Validated", "Aligned", "Processing", "Complete", "Error"]
        )
        form_layout.addRow("Status:", self.status_combo)

        layout.addWidget(form_group)

        # Update/Save buttons (same as standard)
        save_layout = QHBoxLayout()

        self.update_button = QPushButton("Update Selected")
        self.update_button.clicked.connect(self.update_selected)
        self.update_button.setEnabled(False)
        save_layout.addWidget(self.update_button)

        self.clear_button = QPushButton("Clear Form")
        self.clear_button.clicked.connect(self.clear_form)
        save_layout.addWidget(self.clear_button)

        layout.addLayout(save_layout)

        # NEW: Pixel Size Update section (this is the key addition for utils mode)
        pixel_group = QGroupBox("Pixel Size Update")
        pixel_layout = QVBoxLayout(pixel_group)

        # Instructions
        pixel_instruction = QLabel("Update pixel size for selected assets:")
        pixel_instruction.setStyleSheet("color: #666; font-style: italic;")
        pixel_layout.addWidget(pixel_instruction)

        # Pixel size input and update button
        pixel_input_layout = QHBoxLayout()

        self.pixel_size_input = QLineEdit()
        self.pixel_size_input.setPlaceholderText("Enter pixel size (e.g., 0.6431)")
        pixel_input_layout.addWidget(self.pixel_size_input)

        self.update_pixel_size_button = QPushButton("Update Pixel Size")
        self.update_pixel_size_button.clicked.connect(self.update_pixel_size_selected)
        self.update_pixel_size_button.setEnabled(
            False
        )  # Enable when assets are selected
        pixel_input_layout.addWidget(self.update_pixel_size_button)

        # Make both buttons same size as the update/clear buttons above
        self.update_pixel_size_button.setMinimumSize(self.update_button.sizeHint())

        pixel_layout.addLayout(pixel_input_layout)
        layout.addWidget(pixel_group)

    def import_assets(self):
        """Import tilt-series assets from files or directories into selected group."""
        if (
            not hasattr(self.parent_window, "project_path")
            or not self.parent_window.project_path
        ):
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return

        # Get the selected group
        current_group = self.group_combo.currentText()
        if not current_group:
            current_group = "Default"

        # Ensure group exists
        if current_group not in self.groups:
            self.create_group(current_group)

        # File dialog based on selection type
        dialog = QFileDialog(self, f"Import into '{current_group}' Group")

        # Start in rawData directory if it exists
        start_dir = os.path.join(self.parent_window.project_path, "rawData")
        if os.path.exists(start_dir):
            dialog.setDirectory(start_dir)
        else:
            dialog.setDirectory(self.parent_window.project_path)

        if self.import_files_radio.isChecked():
            # Select multiple files
            dialog.setFileMode(QFileDialog.ExistingFiles)
            dialog.setNameFilter("Stack files (*.st *.mrc);;All files (*)")
        else:
            # Select directory
            dialog.setFileMode(QFileDialog.Directory)
            dialog.setOption(QFileDialog.ShowDirsOnly, True)

        if dialog.exec():
            selected_paths = dialog.selectedFiles()
            self.process_selected_paths(selected_paths, current_group)

    def process_selected_paths(self, paths: List[str], group_name: str = "Default"):
        """Process selected files or directories for a specific group."""
        if not paths:
            return

        # For directory mode, scan for files
        if (
            self.import_directory_radio.isChecked()
            and len(paths) == 1
            and os.path.isdir(paths[0])
        ):
            directory = paths[0]
            # Scan directory for stack files
            stack_files = []
            for ext in ["*.st", "*.mrc"]:
                pattern = os.path.join(directory, ext)
                stack_files.extend(glob.glob(pattern))

            if not stack_files:
                QMessageBox.information(
                    self,
                    "No Files Found",
                    f"No stack files found in directory:\n{directory}",
                )
                return

            self.import_stack_files(stack_files, group_name)

        elif self.import_files_radio.isChecked():
            # Process individual files
            files = [p for p in paths if os.path.isfile(p)]
            if files:
                self.import_stack_files(files, group_name)
            else:
                QMessageBox.warning(self, "No Files", "No valid files selected.")
        else:
            QMessageBox.warning(
                self, "Invalid Selection", "Please select the appropriate import mode."
            )

    def import_stack_files(self, stack_files: List[str], group_name: str = "Default"):
        """Import stack files into the specified group."""
        for stack_file in stack_files:
            if not os.path.isfile(stack_file):
                print(f"Stack file not found: {stack_file}")
                continue

            print(f"Processing stack file: {stack_file}")

            # Generate unique name for this asset
            base_name = os.path.splitext(os.path.basename(stack_file))[0]
            asset_name = base_name
            counter = 1

            # Check if name already exists in any group
            all_assets = {}
            for group_assets in self.groups.values():
                all_assets.update(group_assets)

            while asset_name in all_assets:
                asset_name = f"{base_name}_{counter}"
                counter += 1

            # Get stack dimensions using IMOD header
            x_dim, y_dim, z_dim = self.get_stack_dimensions(stack_file)
            if x_dim == 0 or y_dim == 0 or z_dim == 0:
                print(f"Failed to get valid dimensions for {stack_file}")

            # Find or extract tilt file (always enabled now)
            tilt_file = ""
            tilt_validated = False
            tilt_file = self.find_or_extract_tilt_file(stack_file)
            if tilt_file:
                # Validate tilt file against number of slices
                tilt_validated = self.validate_tilt_file(tilt_file, z_dim)
                if not tilt_validated:
                    print(f"Tilt file validation failed for {tilt_file}")

            # Create asset data with dimensions
            asset_data = {
                "name": asset_name,
                "file_path": stack_file,
                "directory": os.path.dirname(stack_file),
                "tilt_file": tilt_file,
                "x_dim": x_dim,
                "y_dim": y_dim,
                "z_dim": z_dim,
                "stack_validated": x_dim > 0 and y_dim > 0 and z_dim > 0,
                "tilt_validated": tilt_validated,
                "status": "Imported",
            }

            # Add to group
            self.groups[group_name][asset_name] = asset_data

            # Add to tree under group
            self.add_asset_to_tree(asset_data, group_name)

        # Always run validation (now default)
        self.validate_group_assets(group_name)

        # Save assets to persistence
        self.save_assets()

    def auto_detect_tilt_file(self, stack_file: str) -> str:
        """Auto-detect tilt file based on stack file name."""
        base_name = os.path.splitext(stack_file)[0]
        tilt_file = base_name + ".rawtlt"

        if os.path.isfile(tilt_file):
            return tilt_file
        return ""

    def get_stack_dimensions(self, stack_file: str) -> tuple:
        """Get stack dimensions using IMOD header command."""
        try:
            # Run header -size command
            result = subprocess.run(
                ["header", "-size", stack_file],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                # Parse output: typically "X Y Z" format
                output = result.stdout.strip()
                dimensions = output.split()
                if len(dimensions) >= 3:
                    x, y, z = int(dimensions[0]), int(dimensions[1]), int(dimensions[2])
                    return (x, y, z)
            else:
                print(f"header command failed for {stack_file}: {result.stderr}")

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            ValueError,
            FileNotFoundError,
        ) as e:
            print(f"Error getting dimensions for {stack_file}: {e}")

        return (0, 0, 0)  # Default if failed

    def extract_tilt_file(self, stack_file: str) -> str:
        """Extract tilt file using IMOD extracttilts command."""
        base_name = os.path.splitext(stack_file)[0]
        tilt_file = base_name + ".rawtlt"

        try:
            # Run extracttilts command
            result = subprocess.run(
                ["extracttilts", stack_file, tilt_file],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0 and os.path.isfile(tilt_file):
                print(f"Successfully extracted tilt file: {tilt_file}")
                return tilt_file
            else:
                print(f"extracttilts failed for {stack_file}: {result.stderr}")

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            FileNotFoundError,
        ) as e:
            print(f"Error extracting tilt file for {stack_file}: {e}")

        return ""

    def find_or_extract_tilt_file(self, stack_file: str) -> str:
        """Find existing tilt file or extract it from stack."""
        # First try to find existing .rawtlt file
        base_name = os.path.splitext(stack_file)[0]
        tilt_file = base_name + ".rawtlt"

        if os.path.isfile(tilt_file):
            return tilt_file

        # If not found, try to extract it
        return self.extract_tilt_file(stack_file)

    def validate_tilt_file(self, tilt_file: str, expected_slices: int) -> bool:
        """Validate that tilt file has correct number of lines."""
        if not os.path.isfile(tilt_file):
            return False

        try:
            with open(tilt_file, "r") as f:
                lines = f.readlines()
                # Count non-empty lines
                tilt_lines = len([line for line in lines if line.strip()])

            if tilt_lines == expected_slices:
                return True
            else:
                print(
                    f"Tilt file validation failed: {tilt_file} has {tilt_lines} lines, expected {expected_slices}"
                )
                return False

        except Exception as e:
            print(f"Error validating tilt file {tilt_file}: {e}")
            return False

    def create_group(self, group_name: str):
        """Create a new group for organizing assets."""
        if group_name not in self.groups:
            self.groups[group_name] = {}

            # Add group to tree
            group_item = QTreeWidgetItem(self.assets_tree)
            group_item.setText(0, group_name)
            group_item.setText(1, "[Group]")
            group_item.setText(2, "")  # No size for groups
            group_item.setText(3, "0")
            group_item.setText(4, "assets")
            group_item.setExpanded(True)

            # Update combo box
            if self.group_combo.findText(group_name) == -1:
                self.group_combo.addItem(group_name)

    def add_group(self):
        """Add a new group via user input."""
        group_name = self.group_combo.currentText().strip()
        if not group_name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a group name.")
            return

        if group_name in self.groups:
            QMessageBox.information(
                self, "Group Exists", f"Group '{group_name}' already exists."
            )
            return

        self.create_group(group_name)
        self.group_combo.setCurrentText(group_name)

    def add_asset_to_tree(self, asset_data: Dict[str, Any], group_name: str):
        """Add an asset to the tree under its group."""
        # Find group item
        group_item = None
        for i in range(self.assets_tree.topLevelItemCount()):
            item = self.assets_tree.topLevelItem(i)
            if item.text(0) == group_name:
                group_item = item
                break

        if not group_item:
            self.create_group(group_name)
            group_item = self.assets_tree.topLevelItem(
                self.assets_tree.topLevelItemCount() - 1
            )

        # Add asset item
        asset_item = QTreeWidgetItem(group_item)
        asset_item.setText(0, asset_data["name"])
        asset_item.setText(1, asset_data["file_path"])

        # Size column - display dimensions
        x_dim = asset_data.get("x_dim", 0)
        y_dim = asset_data.get("y_dim", 0)
        z_dim = asset_data.get("z_dim", 0)
        if x_dim > 0 and y_dim > 0 and z_dim > 0:
            asset_item.setText(2, f"{x_dim},{y_dim},{z_dim}")
            # Reset to normal color for valid dimensions
            asset_item.setForeground(2, QColor(0, 0, 0))  # Black for valid dimensions
        else:
            asset_item.setText(2, "Unknown")
            asset_item.setForeground(
                2, QColor(139, 0, 0)
            )  # Dark red for unknown dimensions

        # Stack column - use validation status
        stack_validated = asset_data.get("stack_validated", False)
        if stack_validated:
            asset_item.setText(3, "Stack")
            # Reset to normal color for validated stack
            asset_item.setForeground(3, QColor(0, 0, 0))  # Black for validated stack
        else:
            asset_item.setText(3, "Stack")
            # Dark red for unvalidated stack
            asset_item.setForeground(3, QColor(139, 0, 0))

        # Tilt column - use validation status
        tilt_file = asset_data.get("tilt_file", "")
        tilt_validated = asset_data.get("tilt_validated", False)
        if tilt_file and tilt_validated:
            asset_item.setText(4, "Tilt")
            # Reset to normal color for validated tilt file
            asset_item.setForeground(
                4, QColor(0, 0, 0)
            )  # Black for validated tilt file
        elif tilt_file:
            asset_item.setText(4, "Tilt")
            # Dark red for unvalidated tilt file
            asset_item.setForeground(4, QColor(139, 0, 0))
        else:
            asset_item.setText(4, "None")
            # Dark red for no tilt file
            asset_item.setForeground(4, QColor(139, 0, 0))

        # Pixel Size column
        pixel_size = asset_data.get("pixel_size", None)
        if pixel_size is not None and pixel_size > 0:
            asset_item.setText(5, f"{pixel_size:.3f}")
            asset_item.setForeground(5, QColor(0, 0, 0))  # Black for valid pixel size
        else:
            asset_item.setText(5, "Unknown")
            asset_item.setForeground(
                5, QColor(139, 0, 0)
            )  # Dark red for missing pixel size

        # Store asset name for later reference
        asset_item.setData(0, Qt.UserRole, asset_data["name"])
        asset_item.setData(1, Qt.UserRole, group_name)

    def copy_to_group(self):
        """Copy selected assets to the current group."""
        selected_items = self.assets_tree.selectedItems()
        asset_items = [item for item in selected_items if item.parent() is not None]

        if not asset_items:
            QMessageBox.warning(self, "No Selection", "Please select assets to copy.")
            return

        target_group = self.group_combo.currentText()
        if not target_group:
            target_group = "Default"

        # Ensure target group exists
        if target_group not in self.groups:
            self.create_group(target_group)

        copied_assets = []
        skipped_assets = []

        for item in asset_items:
            asset_name = item.data(0, Qt.UserRole)
            source_group = item.data(1, Qt.UserRole)

            if not asset_name or not source_group:
                continue

            if target_group == source_group:
                skipped_assets.append(asset_name)
                continue

            # Copy asset data
            source_data = self.groups[source_group][asset_name].copy()

            # Generate new name if needed
            new_name = asset_name
            counter = 1
            while new_name in self.groups[target_group]:
                new_name = f"{asset_name}_copy_{counter}"
                counter += 1

            source_data["name"] = new_name
            self.groups[target_group][new_name] = source_data
            copied_assets.append((asset_name, new_name))

        # Refresh the entire tree to update group counts
        self.update_tree_display()

        # Save changes
        self.save_assets()

        # Build result message
        message_parts = []
        if copied_assets:
            if len(copied_assets) == 1:
                asset_name, new_name = copied_assets[0]
                message_parts.append(
                    f"Copied '{asset_name}' to '{target_group}' as '{new_name}'."
                )
            else:
                message_parts.append(
                    f"Copied {len(copied_assets)} assets to '{target_group}':"
                )
                for asset_name, new_name in copied_assets[:5]:  # Show first 5
                    message_parts.append(f"  • {asset_name} → {new_name}")
                if len(copied_assets) > 5:
                    message_parts.append(f"  • ... and {len(copied_assets) - 5} more")

        if skipped_assets:
            message_parts.append(
                f"\nSkipped {len(skipped_assets)} assets already in '{target_group}'."
            )

        if message_parts:
            QMessageBox.information(self, "Copy Complete", "\n".join(message_parts))

    def validate_group_assets(self, group_name: str):
        """Validate all assets in a group."""
        if group_name not in self.groups:
            return

        print(f"Validating assets in group: {group_name}")

        for asset_name, asset_data in self.groups[group_name].items():
            print(f"Validating asset: {asset_name}")

            # Re-validate stack file and get dimensions
            stack_file = asset_data["file_path"]
            x_dim, y_dim, z_dim = 0, 0, 0
            stack_validated = False

            if os.path.isfile(stack_file):
                # Get stack dimensions
                x_dim, y_dim, z_dim = self.get_stack_dimensions(stack_file)
                stack_validated = x_dim > 0 and y_dim > 0 and z_dim > 0
                print(
                    f"  Stack dimensions: {x_dim}x{y_dim}x{z_dim}, validated: {stack_validated}"
                )

                # Update asset data with current dimensions
                asset_data["x_dim"] = x_dim
                asset_data["y_dim"] = y_dim
                asset_data["z_dim"] = z_dim
                asset_data["stack_validated"] = stack_validated
            else:
                print(f"  Stack file not found: {stack_file}")
                # File doesn't exist
                asset_data["stack_validated"] = False

            # Re-validate tilt file
            tilt_file = asset_data.get("tilt_file", "")
            tilt_validated = False

            if tilt_file and os.path.isfile(tilt_file) and z_dim > 0:
                tilt_validated = self.validate_tilt_file(tilt_file, z_dim)
                asset_data["tilt_validated"] = tilt_validated
                print(f"  Tilt file: {tilt_file}, validated: {tilt_validated}")
            else:
                asset_data["tilt_validated"] = False
                if tilt_file:
                    print(f"  Tilt file not found or invalid: {tilt_file}")
                else:
                    print(f"  No tilt file specified")

            # Update status based on validation results
            if not os.path.isfile(stack_file):
                asset_data["status"] = "Missing File"
            elif not stack_validated:
                asset_data["status"] = "Invalid Stack"
            elif tilt_file and not os.path.isfile(tilt_file):
                asset_data["status"] = "Missing Tilt"
            elif tilt_file and not tilt_validated:
                asset_data["status"] = "Invalid Tilt"
            else:
                asset_data["status"] = "Validated"

            print(f"  Final status: {asset_data['status']}")

        # Update tree display
        self.update_tree_display()

    def update_tree_display(self):
        """Update the tree display to reflect current asset states."""
        # Clear and rebuild tree
        self.assets_tree.clear()

        for group_name, group_assets in self.groups.items():
            # Create group item
            group_item = QTreeWidgetItem(self.assets_tree)
            group_item.setText(0, group_name)
            group_item.setText(1, "[Group]")
            group_item.setText(2, "")  # No size for groups
            group_item.setText(3, f"{len(group_assets)}")
            group_item.setText(4, "assets")
            group_item.setExpanded(True)

            # Add assets to group
            for asset_name, asset_data in group_assets.items():
                self.add_asset_to_tree(asset_data, group_name)

    def save_assets(self):
        """Save assets to persistent storage."""
        if hasattr(self.parent_window, "state_manager"):
            # Flatten groups structure for storage with unique keys
            flat_assets = {}
            for group_name, group_assets in self.groups.items():
                for asset_name, asset_data in group_assets.items():
                    # Create unique key combining group and asset name
                    unique_key = f"{group_name}::{asset_name}"

                    # Add group info to asset data
                    flat_asset = asset_data.copy()
                    flat_asset["group"] = group_name
                    flat_asset["original_name"] = (
                        asset_name  # Preserve original asset name
                    )
                    flat_assets[unique_key] = flat_asset

            self.parent_window.state_manager.save_tilt_series_assets(flat_assets)

    def load_assets(self):
        """Load assets from persistent storage."""
        if hasattr(self.parent_window, "state_manager"):
            flat_assets = self.parent_window.state_manager.load_tilt_series_assets()

            # Rebuild groups structure
            self.groups = {}
            for unique_key, asset_data in flat_assets.items():
                group_name = asset_data.get("group", "Default")

                # Extract original asset name (handle both old and new formats)
                if "::" in unique_key:
                    # New format: "group::asset_name"
                    asset_name = asset_data.get(
                        "original_name", unique_key.split("::", 1)[1]
                    )
                else:
                    # Old format compatibility: use the key as asset name
                    asset_name = unique_key

                if group_name not in self.groups:
                    self.create_group(group_name)

                # Remove group and original_name info from asset data for clean storage
                clean_asset = {
                    k: v
                    for k, v in asset_data.items()
                    if k not in ["group", "original_name"]
                }
                clean_asset["name"] = asset_name  # Ensure name is set correctly
                self.groups[group_name][asset_name] = clean_asset

            self.update_tree_display()

    def update_pixel_size_selected(self):
        """Update pixel size for selected assets or groups."""
        pixel_size_text = self.pixel_size_input.text().strip()

        if not pixel_size_text:
            QMessageBox.warning(
                self, "No Pixel Size", "Please enter a pixel size value."
            )
            return

        try:
            pixel_size = float(pixel_size_text)
            if pixel_size <= 0:
                raise ValueError("Pixel size must be positive")
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter a valid positive number for pixel size.",
            )
            return

        assets_to_process, operation_description = (
            self.get_target_assets_for_operation()
        )

        if not assets_to_process:
            QMessageBox.information(
                self,
                "No Selection",
                "Please select assets or groups to update pixel size.",
            )
            return

        print(f"Updating pixel size to {pixel_size} for {operation_description}")

        updated_count = 0

        for group_name, asset_name, asset_data in assets_to_process:
            asset_data["pixel_size"] = pixel_size
            updated_count += 1
            print(f"  Updated pixel size for {asset_name}: {pixel_size}")

        # Update tree display and save
        self.update_tree_display()
        self.save_assets()

        # Clear the input field
        self.pixel_size_input.clear()

        # Show results
        QMessageBox.information(
            self,
            "Pixel Size Updated",
            f"Updated pixel size to {pixel_size} for {updated_count} assets from {operation_description}.",
        )

    def get_target_assets_for_operation(self):
        """Get the assets that should be targeted for operations based on current selection.

        Returns:
            tuple: (assets_to_process, operation_description)
            assets_to_process: list of (group_name, asset_name, asset_data) tuples
            operation_description: string describing what will be processed
        """
        selected_items = self.assets_tree.selectedItems()

        if not selected_items:
            return [], "No selection"

        # Separate groups and assets
        group_items = [item for item in selected_items if item.parent() is None]
        asset_items = [item for item in selected_items if item.parent() is not None]

        assets_to_process = []
        descriptions = []

        # Process selected groups (all assets in those groups)
        for group_item in group_items:
            group_name = group_item.text(0)
            if group_name in self.groups:
                group_assets = self.groups[group_name]
                for asset_name, asset_data in group_assets.items():
                    assets_to_process.append((group_name, asset_name, asset_data))
                descriptions.append(
                    f"group '{group_name}' ({len(group_assets)} assets)"
                )

        # Process selected individual assets
        for asset_item in asset_items:
            asset_name = asset_item.data(0, Qt.UserRole)
            group_name = asset_item.data(1, Qt.UserRole)

            if (
                group_name
                and group_name in self.groups
                and asset_name in self.groups[group_name]
            ):
                asset_data = self.groups[group_name][asset_name]
                assets_to_process.append((group_name, asset_name, asset_data))

        if asset_items:
            descriptions.append(f"{len(asset_items)} selected assets")

        # Build description
        if descriptions:
            operation_description = " and ".join(descriptions)
        else:
            operation_description = "No valid selection"

        return assets_to_process, operation_description

    def validate_selected(self):
        """Validate the selected assets or all assets in selected groups."""
        assets_to_process, operation_description = (
            self.get_target_assets_for_operation()
        )

        if not assets_to_process:
            QMessageBox.information(
                self, "No Selection", "Please select assets or groups to validate."
            )
            return

        print(f"Validating {operation_description}")

        # Track validation results
        validated_count = 0
        total_count = len(assets_to_process)
        groups_to_update = set()

        for group_name, asset_name, asset_data in assets_to_process:
            print(f"Validating asset: {asset_name} in group: {group_name}")

            # Re-validate stack file and get dimensions
            stack_file = asset_data["file_path"]
            x_dim, y_dim, z_dim = 0, 0, 0
            stack_validated = False

            if os.path.isfile(stack_file):
                # Get stack dimensions
                x_dim, y_dim, z_dim = self.get_stack_dimensions(stack_file)
                stack_validated = x_dim > 0 and y_dim > 0 and z_dim > 0
                print(
                    f"  Stack dimensions: {x_dim}x{y_dim}x{z_dim}, validated: {stack_validated}"
                )

                # Update asset data with current dimensions
                asset_data["x_dim"] = x_dim
                asset_data["y_dim"] = y_dim
                asset_data["z_dim"] = z_dim
                asset_data["stack_validated"] = stack_validated
            else:
                print(f"  Stack file not found: {stack_file}")
                asset_data["stack_validated"] = False

            # Re-validate tilt file
            tilt_file = asset_data.get("tilt_file", "")
            tilt_validated = False

            if tilt_file and os.path.isfile(tilt_file) and z_dim > 0:
                tilt_validated = self.validate_tilt_file(tilt_file, z_dim)
                asset_data["tilt_validated"] = tilt_validated
                print(f"  Tilt file: {tilt_file}, validated: {tilt_validated}")
            else:
                asset_data["tilt_validated"] = False
                if tilt_file:
                    print(f"  Tilt file not found or invalid: {tilt_file}")
                else:
                    print(f"  No tilt file specified")

            # Update status based on validation results
            if not os.path.isfile(stack_file):
                asset_data["status"] = "Missing File"
            elif not stack_validated:
                asset_data["status"] = "Invalid Stack"
            elif tilt_file and not os.path.isfile(tilt_file):
                asset_data["status"] = "Missing Tilt"
            elif tilt_file and not tilt_validated:
                asset_data["status"] = "Invalid Tilt"
            else:
                asset_data["status"] = "Validated"
                validated_count += 1

            print(f"  Final status: {asset_data['status']}")
            groups_to_update.add(group_name)

        # Update tree display and save
        self.update_tree_display()
        self.save_assets()

        # Show results
        QMessageBox.information(
            self,
            "Validation Complete",
            f"Validated {validated_count} of {total_count} assets from {operation_description}.",
        )

    def validate_all_assets(self):
        """Validate all imported assets."""
        if hasattr(self.parent_window, "output_text"):
            self.parent_window.output_text.append(
                "Validating all assets - STUB: Not yet implemented"
            )

    def copy_selected(self):
        """Copy the selected asset."""
        selected_item = self.assets_tree.currentItem()
        if not selected_item or selected_item.parent():
            return

        asset_name = selected_item.text(0)
        if asset_name not in self.assets:
            return

        # Create copy with new name
        original_data = self.assets[asset_name].copy()
        copy_name = f"{asset_name}_copy"

        counter = 1
        while copy_name in self.assets:
            copy_name = f"{asset_name}_copy_{counter}"
            counter += 1

        original_data["name"] = copy_name
        self.assets[copy_name] = original_data

        self.update_assets_tree()
        self.save_assets()

    def delete_selected(self):
        """Delete the selected assets (supports multiple selection)."""
        selected_items = self.assets_tree.selectedItems()
        if not selected_items:
            return

        # Separate groups and assets
        group_items = [item for item in selected_items if item.parent() is None]
        asset_items = [item for item in selected_items if item.parent() is not None]

        # Handle group deletions
        if group_items:
            group_names = [item.text(0) for item in group_items]

            # Check for Default group
            if "Default" in group_names:
                QMessageBox.warning(
                    self, "Cannot Delete", "Cannot delete the Default group."
                )
                return

            if len(group_names) == 1:
                message = f"Are you sure you want to delete group '{group_names[0]}' and all its assets?"
            else:
                message = f"Are you sure you want to delete {len(group_names)} groups and all their assets?"

            reply = QMessageBox.question(
                self, "Delete Groups", message, QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                for group_name in group_names:
                    if group_name in self.groups:
                        del self.groups[group_name]
                        # Remove from combo box
                        index = self.group_combo.findText(group_name)
                        if index >= 0:
                            self.group_combo.removeItem(index)

        # Handle asset deletions
        if asset_items:
            asset_count = len(asset_items)

            if asset_count == 1:
                asset_name = asset_items[0].data(0, Qt.UserRole)
                group_name = asset_items[0].data(1, Qt.UserRole)
                message = f"Are you sure you want to delete asset '{asset_name}' from group '{group_name}'?"
            else:
                message = f"Are you sure you want to delete {asset_count} assets?"

            reply = QMessageBox.question(
                self, "Delete Assets", message, QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                deleted_count = 0
                for item in asset_items:
                    asset_name = item.data(0, Qt.UserRole)
                    group_name = item.data(1, Qt.UserRole)

                    if (
                        group_name
                        and group_name in self.groups
                        and asset_name in self.groups[group_name]
                    ):
                        del self.groups[group_name][asset_name]
                        deleted_count += 1

                if deleted_count > 0:
                    print(f"Deleted {deleted_count} assets")

        # Update display and save if anything was deleted
        if group_items or asset_items:
            self.update_tree_display()
            self.save_assets()

    def on_asset_selected(self):
        """Handle asset selection change (supports multiple selection)."""
        selected_items = self.assets_tree.selectedItems()

        if not selected_items:
            self.clear_form()
            self.update_info_display(None)
            if hasattr(self, "update_button"):
                self.update_button.setEnabled(False)
            if hasattr(self, "copy_to_group_button"):
                self.copy_to_group_button.setEnabled(False)
            if hasattr(self, "display_button"):
                self.display_button.setEnabled(False)
            if hasattr(self, "update_pixel_size_button"):
                self.update_pixel_size_button.setEnabled(False)
            return

        # Filter to only asset items (not group items)
        asset_items = [item for item in selected_items if item.parent() is not None]
        group_items = [item for item in selected_items if item.parent() is None]

        if not asset_items and not group_items:
            # Nothing selected
            self.clear_form()
            self.update_info_display(None)
            if hasattr(self, "update_button"):
                self.update_button.setEnabled(False)
            if hasattr(self, "copy_to_group_button"):
                self.copy_to_group_button.setEnabled(False)
            if hasattr(self, "display_button"):
                self.display_button.setEnabled(False)
            if hasattr(self, "validate_button"):
                self.validate_button.setEnabled(False)
            if hasattr(self, "update_pixel_size_button"):
                self.update_pixel_size_button.setEnabled(False)
            return

        if not asset_items and group_items:
            # Only groups selected - enable validation but disable other operations
            self.clear_form()
            self.update_info_display(None)
            if hasattr(self, "update_button"):
                self.update_button.setEnabled(False)
            if hasattr(self, "copy_to_group_button"):
                try:
                    self.copy_to_group_button.setEnabled(False)
                except RuntimeError:
                    # Widget deleted during mode switch
                    pass
            if hasattr(self, "display_button"):
                try:
                    self.display_button.setEnabled(
                        False
                    )  # Can't display multiple assets
                except RuntimeError:
                    # Widget deleted during mode switch
                    pass
            if hasattr(self, "validate_button"):
                try:
                    self.validate_button.setEnabled(
                        True
                    )  # Enable validation for groups
                except RuntimeError:
                    # Widget deleted during mode switch
                    pass
            if hasattr(self, "update_pixel_size_button"):
                try:
                    self.update_pixel_size_button.setEnabled(
                        True
                    )  # Enable pixel size update for groups
                except RuntimeError:
                    # Widget deleted during mode switch
                    pass
            return

        # Handle single vs multiple selection
        if len(asset_items) == 1:
            # Single selection - show details and enable all actions
            selected_item = asset_items[0]
            asset_name = selected_item.data(0, Qt.UserRole)
            group_name = selected_item.data(1, Qt.UserRole)

            if (
                group_name
                and group_name in self.groups
                and asset_name in self.groups[group_name]
            ):
                asset_data = self.groups[group_name][asset_name]
                self.populate_form(asset_data)
                self.update_info_display(asset_data)
                if hasattr(self, "update_button"):
                    self.update_button.setEnabled(True)
                if hasattr(self, "copy_to_group_button"):
                    try:
                        self.copy_to_group_button.setEnabled(True)
                    except RuntimeError:
                        # Widget deleted during mode switch
                        pass
                if hasattr(self, "display_button"):
                    try:
                        self.display_button.setEnabled(True)
                    except RuntimeError:
                        # Widget deleted during mode switch
                        pass
                if hasattr(self, "validate_button"):
                    try:
                        self.validate_button.setEnabled(True)
                    except RuntimeError:
                        # Widget deleted during mode switch
                        pass
                if hasattr(self, "update_pixel_size_button"):
                    try:
                        self.update_pixel_size_button.setEnabled(True)
                    except RuntimeError:
                        # Widget deleted during mode switch
                        pass
            else:
                self.clear_form()
                self.update_info_display(None)
                if hasattr(self, "update_button"):
                    self.update_button.setEnabled(False)
                if hasattr(self, "copy_to_group_button"):
                    self.copy_to_group_button.setEnabled(False)
                if hasattr(self, "display_button"):
                    self.display_button.setEnabled(False)
                if hasattr(self, "validate_button"):
                    self.validate_button.setEnabled(False)
                if hasattr(self, "update_pixel_size_button"):
                    self.update_pixel_size_button.setEnabled(False)
        else:
            # Multiple selection - show summary and enable limited actions
            self.clear_form()
            self.update_info_display_multiple(asset_items)
            if hasattr(self, "update_button"):
                self.update_button.setEnabled(False)  # Disable for multi-selection
            if hasattr(self, "copy_to_group_button"):
                try:
                    self.copy_to_group_button.setEnabled(True)  # Allow multi-copy
                except RuntimeError:
                    # Widget deleted during mode switch
                    pass
            if hasattr(self, "display_button"):
                try:
                    self.display_button.setEnabled(False)  # Disable for multi-selection
                except RuntimeError:
                    # Widget deleted during mode switch
                    pass
            if hasattr(self, "validate_button"):
                try:
                    self.validate_button.setEnabled(
                        True
                    )  # Enable validation for multi-selection
                except RuntimeError:
                    # Widget deleted during mode switch
                    pass
            if hasattr(self, "update_pixel_size_button"):
                try:
                    self.update_pixel_size_button.setEnabled(
                        True
                    )  # Enable pixel size update for multi-selection
                except RuntimeError:
                    # Widget deleted during mode switch
                    pass

    def update_info_display_multiple(self, asset_items):
        """Update info display for multiple selected assets."""
        if not hasattr(self, "info_display") or not self.info_display:
            return

        try:
            asset_count = len(asset_items)
            group_counts = {}
            total_validated = 0
            total_with_tilt = 0

            for item in asset_items:
                asset_name = item.data(0, Qt.UserRole)
                group_name = item.data(1, Qt.UserRole)

                if (
                    group_name
                    and group_name in self.groups
                    and asset_name in self.groups[group_name]
                ):
                    asset_data = self.groups[group_name][asset_name]

                    # Count by group
                    group_counts[group_name] = group_counts.get(group_name, 0) + 1

                    # Count validated assets
                    if asset_data.get("stack_validated", False):
                        total_validated += 1

                    # Count assets with tilt files
                    if asset_data.get("tilt_file"):
                        total_with_tilt += 1

            # Build summary info
            info_lines = []
            info_lines.append(f"<b>Selected Assets:</b> {asset_count}")

            # Group breakdown
            if len(group_counts) > 1:
                group_info = []
                for group, count in group_counts.items():
                    group_info.append(f"{group} ({count})")
                info_lines.append(f"<b>Groups:</b> {', '.join(group_info)}")

            # Validation summary
            validation_color = (
                "darkgreen"
                if total_validated == asset_count
                else "darkorange" if total_validated > 0 else "darkred"
            )
            info_lines.append(
                f"<b>Validated:</b> <span style='color: {validation_color};'>{total_validated}/{asset_count}</span>"
            )

            # Tilt file summary
            tilt_color = (
                "darkgreen"
                if total_with_tilt == asset_count
                else "darkorange" if total_with_tilt > 0 else "darkred"
            )
            info_lines.append(
                f"<b>With Tilt Files:</b> <span style='color: {tilt_color};'>{total_with_tilt}/{asset_count}</span>"
            )

            info_lines.append(
                "<br><i>Use Ctrl+click or Shift+click for multi-selection</i>"
            )

            self.info_display.setText("<br>".join(info_lines))
        except RuntimeError:
            # Widget has been deleted during mode switching, ignore
            pass

    def update_selected(self):
        """Update the selected asset with form data."""
        selected_item = self.assets_tree.currentItem()
        if not selected_item or selected_item.parent():
            return

        old_name = selected_item.text(0)
        new_name = self.name_input.text().strip()

        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Asset name cannot be empty.")
            return

        if old_name in self.assets:
            asset_data = self.assets[old_name]

            # Update data
            asset_data["name"] = new_name
            asset_data["file_path"] = self.path_input.text().strip()
            asset_data["tilt_file"] = self.tilt_file_input.text().strip()
            asset_data["status"] = self.status_combo.currentText()

            # Handle name change
            if new_name != old_name:
                if new_name in self.assets:
                    QMessageBox.warning(
                        self, "Name Exists", f"Asset name '{new_name}' already exists."
                    )
                    return
                self.assets[new_name] = asset_data
                del self.assets[old_name]

            self.update_assets_tree()
            self.save_assets()

    def clear_form(self):
        """Clear the asset form."""
        if hasattr(self, "name_input"):
            self.name_input.clear()
        if hasattr(self, "path_input"):
            self.path_input.clear()
        if hasattr(self, "tilt_file_input"):
            self.tilt_file_input.clear()
        if hasattr(self, "status_combo"):
            self.status_combo.setCurrentIndex(0)

    def populate_form(self, asset_data: Dict[str, Any]):
        """Populate the form with asset data."""
        if hasattr(self, "name_input"):
            self.name_input.setText(asset_data.get("name", ""))
        if hasattr(self, "path_input"):
            self.path_input.setText(asset_data.get("file_path", ""))
        if hasattr(self, "tilt_file_input"):
            self.tilt_file_input.setText(asset_data.get("tilt_file", ""))
        if hasattr(self, "status_combo"):
            status = asset_data.get("status", "Imported")
            index = self.status_combo.findText(status)
            if index >= 0:
                self.status_combo.setCurrentIndex(index)

    def get_asset_by_name(
        self, group_name: str, asset_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get asset data by group and name."""
        if group_name in self.groups and asset_name in self.groups[group_name]:
            return self.groups[group_name][asset_name]
        return None

    def get_all_assets(self) -> Dict[str, Dict[str, Any]]:
        """Get all assets from all groups."""
        all_assets = {}
        for group_name, group_assets in self.groups.items():
            for asset_name, asset_data in group_assets.items():
                # Add group info to asset
                asset_with_group = asset_data.copy()
                asset_with_group["group"] = group_name
                all_assets[asset_name] = asset_with_group
        return all_assets

    def update_info_display(self, asset_data: Optional[Dict[str, Any]]):
        """Update the info display area with asset details."""
        if not hasattr(self, "info_display") or not self.info_display:
            return

        try:
            if asset_data is None:
                self.info_display.setText("Select an asset to view details...")
                return

            # Build info text
            info_lines = []
            info_lines.append(f"<b>Asset:</b> {asset_data.get('name', 'Unknown')}")
            info_lines.append(f"<b>Path:</b> {asset_data.get('file_path', 'Unknown')}")

            # Dimensions
            x_dim = asset_data.get("x_dim", 0)
            y_dim = asset_data.get("y_dim", 0)
            z_dim = asset_data.get("z_dim", 0)
            if x_dim > 0 and y_dim > 0 and z_dim > 0:
                info_lines.append(f"<b>Dimensions:</b> {x_dim} × {y_dim} × {z_dim}")
            else:
                info_lines.append(
                    "<b>Dimensions:</b> <span style='color: darkred;'>Unknown</span>"
                )

            # Stack validation
            stack_validated = asset_data.get("stack_validated", False)
            if stack_validated:
                info_lines.append("<b>Stack:</b> ✓ Validated")
            else:
                info_lines.append(
                    "<b>Stack:</b> <span style='color: darkred;'>⚠ Not validated</span>"
                )

            # Tilt file
            tilt_file = asset_data.get("tilt_file", "")
            tilt_validated = asset_data.get("tilt_validated", False)
            if tilt_file and tilt_validated:
                info_lines.append("<b>Tilt file:</b> ✓ Validated")
            elif tilt_file:
                info_lines.append(
                    "<b>Tilt file:</b> <span style='color: darkred;'>⚠ Found but not validated</span>"
                )
            else:
                info_lines.append(
                    "<b>Tilt file:</b> <span style='color: darkred;'>✗ Not found</span>"
                )

            self.info_display.setText("<br>".join(info_lines))
        except RuntimeError:
            # Widget has been deleted during mode switching, ignore
            pass

    def display_in_imod(self):
        """Display the selected asset in IMOD."""
        selected_item = self.assets_tree.currentItem()
        if not selected_item or selected_item.parent() is None:
            QMessageBox.warning(
                self, "No Asset Selected", "Please select an asset to display."
            )
            return

        asset_name = selected_item.data(0, Qt.UserRole)
        group_name = selected_item.data(1, Qt.UserRole)

        if (
            not group_name
            or group_name not in self.groups
            or asset_name not in self.groups[group_name]
        ):
            QMessageBox.warning(self, "Invalid Selection", "Selected asset not found.")
            return

        asset_data = self.groups[group_name][asset_name]
        stack_file = asset_data.get("file_path", "")

        print(f"Attempting to display asset: {asset_name}")
        print(f"Original file path: {stack_file}")

        # Try to resolve the file path if it's relative or has issues
        resolved_path = stack_file
        if stack_file and not os.path.isabs(stack_file):
            # If it's a relative path, try to resolve it relative to project path
            if (
                hasattr(self.parent_window, "project_path")
                and self.parent_window.project_path
            ):
                resolved_path = os.path.join(
                    str(self.parent_window.project_path), stack_file
                )
                print(f"Resolved relative path to: {resolved_path}")

        # Normalize the path to handle any path issues
        if resolved_path:
            resolved_path = os.path.normpath(resolved_path)
            print(f"Normalized path: {resolved_path}")

        if not resolved_path:
            QMessageBox.warning(
                self, "No File Path", "No file path specified for this asset."
            )
            return

        if not os.path.isfile(resolved_path):
            # Try original path as fallback
            if stack_file and os.path.isfile(stack_file):
                resolved_path = stack_file
                print(f"Using original path as fallback: {resolved_path}")
            else:
                error_msg = f"Stack file not found:\nOriginal: {stack_file}\nResolved: {resolved_path}\n\nPlease check that the file exists and the path is correct."
                QMessageBox.warning(self, "File Not Found", error_msg)
                return

        try:
            # Launch IMOD with the stack file
            print(f"Launching IMOD for: {resolved_path}")
            subprocess.Popen(
                ["imod", resolved_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Update info display to show IMOD was launched
            current_info = self.info_display.text()
            self.info_display.setText(
                current_info + "<br><b>Status:</b> Launched in IMOD"
            )

        except FileNotFoundError:
            QMessageBox.warning(
                self,
                "IMOD Not Found",
                "IMOD not found in PATH. Please ensure IMOD is installed and accessible.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Launch Error", f"Error launching IMOD: {e}")

    def refresh_validation(self):
        """Re-run validation on selected assets/groups, or all assets if nothing selected."""
        assets_to_process, operation_description = (
            self.get_target_assets_for_operation()
        )

        if not assets_to_process:
            # If nothing selected, validate all groups (original behavior)
            print("No selection - validating all assets in all groups")
            total_assets = 0
            validated_assets = 0

            for group_name in self.groups.keys():
                group_assets = len(self.groups[group_name])
                total_assets += group_assets

                self.validate_group_assets(group_name)

                # Count validated assets in this group
                for asset_data in self.groups[group_name].values():
                    if asset_data.get("stack_validated", False):
                        validated_assets += 1

            operation_description = f"all {total_assets} assets"
        else:
            # Validate only selected assets/groups
            print(f"Refreshing validation for {operation_description}")
            validated_assets = 0
            groups_to_update = set()

            for group_name, asset_name, asset_data in assets_to_process:
                # Re-validate stack file and get dimensions
                stack_file = asset_data["file_path"]
                x_dim, y_dim, z_dim = 0, 0, 0
                stack_validated = False

                if os.path.isfile(stack_file):
                    # Get stack dimensions
                    x_dim, y_dim, z_dim = self.get_stack_dimensions(stack_file)
                    stack_validated = x_dim > 0 and y_dim > 0 and z_dim > 0

                    # Update asset data with current dimensions
                    asset_data["x_dim"] = x_dim
                    asset_data["y_dim"] = y_dim
                    asset_data["z_dim"] = z_dim
                    asset_data["stack_validated"] = stack_validated
                else:
                    asset_data["stack_validated"] = False

                # Re-validate tilt file
                tilt_file = asset_data.get("tilt_file", "")
                tilt_validated = False

                if tilt_file and os.path.isfile(tilt_file) and z_dim > 0:
                    tilt_validated = self.validate_tilt_file(tilt_file, z_dim)
                    asset_data["tilt_validated"] = tilt_validated
                else:
                    asset_data["tilt_validated"] = False

                # Update status based on validation results
                if not os.path.isfile(stack_file):
                    asset_data["status"] = "Missing File"
                elif not stack_validated:
                    asset_data["status"] = "Invalid Stack"
                elif tilt_file and not os.path.isfile(tilt_file):
                    asset_data["status"] = "Missing Tilt"
                elif tilt_file and not tilt_validated:
                    asset_data["status"] = "Invalid Tilt"
                else:
                    asset_data["status"] = "Validated"

                if asset_data.get("stack_validated", False):
                    validated_assets += 1

                groups_to_update.add(group_name)

        # Update tree display
        self.update_tree_display()

        # Save updated validation states
        self.save_assets()

        # Show results
        QMessageBox.information(
            self,
            "Validation Complete",
            f"Validation complete!\n"
            f"Validated {validated_assets} assets from {operation_description}.",
        )

        # Update info display if asset is selected
        selected_item = self.assets_tree.currentItem()
        if selected_item and selected_item.parent() is not None:
            asset_name = selected_item.data(0, Qt.UserRole)
            group_name = selected_item.data(1, Qt.UserRole)
            if (
                group_name
                and asset_name
                and group_name in self.groups
                and asset_name in self.groups[group_name]
            ):
                self.update_info_display(self.groups[group_name][asset_name])

    def collapse_all_groups(self):
        """Collapse all groups to show only group names."""
        for i in range(self.assets_tree.topLevelItemCount()):
            group_item = self.assets_tree.topLevelItem(i)
            group_item.setExpanded(False)

    def expand_all_groups(self):
        """Expand all groups to show individual assets."""
        for i in range(self.assets_tree.topLevelItemCount()):
            group_item = self.assets_tree.topLevelItem(i)
            group_item.setExpanded(True)
