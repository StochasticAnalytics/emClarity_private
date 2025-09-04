"""
Tilt-Series Assets Panel for emClarity GUI.

This module provides the Tilt-Series Assets panel interface for managing different types of
tilt-series assets including Images, Particle Positions, 3D Volumes, Refine Packages,
Atomic Coordinates, and MT Packages.
"""

import os
from datetime import datetime

import mrcfile
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFont,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class AssetTypeToolbar(QWidget):
    """Toolbar with buttons for different asset types."""

    asset_type_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_asset_type = "images"
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(10, 5, 10, 5)

        # Asset type buttons configuration
        asset_types = [
            ("movies", "Movies", "🎬"),
            ("images", "Images", "🖼️"),
            ("particles", "Particle Positions", "⚫"),
            ("volumes", "3D Volumes", "📦"),
            ("refine", "Refine Pkgs", "🔧"),
            ("coordinates", "Atomic Coordinates", "⚛️"),
            ("utils", "Utils", "🛠️"),
        ]

        self.buttons = {}
        for asset_id, label, icon in asset_types:
            button = QToolButton()
            button.setText(f"{icon}\n{label}")
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setMinimumSize(80, 60)
            button.clicked.connect(
                lambda checked, aid=asset_id: self.select_asset_type(aid)
            )

            self.buttons[asset_id] = button
            layout.addWidget(button)

        # Set Images as default selected
        self.buttons["images"].setChecked(True)
        self.update_button_styles()

        layout.addStretch()

    def select_asset_type(self, asset_type):
        """Select an asset type and update button states."""
        if asset_type == self.current_asset_type:
            return

        # Uncheck previous button
        if self.current_asset_type in self.buttons:
            self.buttons[self.current_asset_type].setChecked(False)

        # Check new button
        self.current_asset_type = asset_type
        if asset_type in self.buttons:
            self.buttons[asset_type].setChecked(True)

        self.update_button_styles()
        self.asset_type_changed.emit(asset_type)

    def update_button_styles(self):
        """Update button styling based on selection state."""
        for asset_id, button in self.buttons.items():
            if button.isChecked():
                button.setStyleSheet(
                    """
                    QToolButton {
                        background-color: #0078D4;
                        color: white;
                        border: 2px solid #106EBE;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                    QToolButton:hover {
                        background-color: #106EBE;
                    }
                """
                )
            else:
                button.setStyleSheet(
                    """
                    QToolButton {
                        background-color: #F5F5F5;
                        color: #333333;
                        border: 1px solid #CCCCCC;
                        border-radius: 4px;
                    }
                    QToolButton:hover {
                        background-color: #E5E5E5;
                        border-color: #999999;
                    }
                """
                )


class GroupsPanel(QWidget):
    """Left sidebar panel for managing asset groups with fixed width."""

    group_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Set fixed width constraints
        self.setFixedWidth(220)
        self.setMinimumWidth(220)
        self.setMaximumWidth(220)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        # Groups header
        header = QLabel("Groups:")
        header.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(header)

        # Groups list
        self.groups_list = QListWidget()

        # Add sample groups (updated for tilt-series)
        sample_groups = [
            "All Tilt-Series (500)",
            "High Resolution (150)",
            "Low Dose (200)",
            "Failed Processing (12)",
            "New Group (1)",
        ]

        for group in sample_groups:
            self.groups_list.addItem(group)

        # Select first item by default
        if self.groups_list.count() > 0:
            self.groups_list.setCurrentRow(0)

        # Connect selection signal
        self.groups_list.currentTextChanged.connect(self.group_selected.emit)

        layout.addWidget(self.groups_list)
        layout.addStretch()


class AssetDataTable(QWidget):
    """Main data table for displaying tilt-series asset information with proper expansion."""

    selection_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.populate_sample_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create table
        self.table = QTableWidget()

        # Set proper size policies for expansion
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Set up columns (updated for tilt-series)
        columns = [
            "I.D.",
            "Tilt-Series Name",
            "Parent I.D.",
            "Align I.D.",
            "X Size",
            "Y Size",
            "Pixel Size",
            "Cs",
            "Voltage",
            "Tilt Range",
            "Status",
        ]

        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)

        # Configure table properties
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)

        # Configure header to properly expand
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)

        # Set specific column behaviors
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID column
        header.setSectionResizeMode(
            1, QHeaderView.Stretch
        )  # Name column (main content)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Parent ID
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Align ID

        # Connect selection signal
        self.table.itemSelectionChanged.connect(self.on_selection_changed)

        layout.addWidget(self.table)

    def populate_sample_data(self):
        """Add sample tilt-series data to the table."""
        sample_data = [
            [
                "1",
                "TS_001_tilt_series",
                "-1",
                "-1",
                "4096",
                "4096",
                "0.6431",
                "2.70",
                "300.00",
                "±60°",
                "Valid",
            ],
            [
                "2",
                "TS_002_tilt_series",
                "-1",
                "-1",
                "4096",
                "4096",
                "0.6431",
                "2.70",
                "300.00",
                "±65°",
                "Valid",
            ],
            [
                "3",
                "TS_003_tilt_series",
                "-1",
                "-1",
                "4096",
                "4096",
                "0.6431",
                "2.70",
                "300.00",
                "±55°",
                "Processing",
            ],
            [
                "4",
                "TS_004_tilt_series",
                "-1",
                "-1",
                "4096",
                "4096",
                "0.6431",
                "2.70",
                "300.00",
                "±60°",
                "Failed",
            ],
            [
                "5",
                "TS_005_tilt_series",
                "-1",
                "-1",
                "4096",
                "4096",
                "0.6431",
                "2.70",
                "300.00",
                "±70°",
                "Valid",
            ],
            [
                "6",
                "TS_006_tilt_series",
                "-1",
                "-1",
                "4096",
                "4096",
                "0.6431",
                "2.70",
                "300.00",
                "±58°",
                "Valid",
            ],
            [
                "7",
                "TS_007_tilt_series",
                "-1",
                "-1",
                "4096",
                "4096",
                "0.6431",
                "2.70",
                "300.00",
                "±62°",
                "Processing",
            ],
        ]

        self.table.setRowCount(len(sample_data))

        for row_idx, row_data in enumerate(sample_data):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                self.table.setItem(row_idx, col_idx, item)

        # Select first row
        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def on_selection_changed(self):
        """Handle table selection changes."""
        current_row = self.table.currentRow()
        if current_row >= 0:
            # Get data from selected row
            row_data = {}
            for col in range(self.table.columnCount()):
                header = self.table.horizontalHeaderItem(col).text()
                item = self.table.item(current_row, col)
                row_data[header] = item.text() if item else ""

            self.selection_changed.emit(row_data)


class ActionButtonsPanel(QWidget):
    """Compact horizontal panel with action buttons for tilt-series management."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)  # Compact spacing

        # Set fixed height and proper size policy
        self.setFixedHeight(50)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Action buttons (updated for tilt-series)
        buttons = [
            ("Add", self.on_add_clicked),
            ("Import", self.on_import_clicked),
            ("Remove", self.on_remove_clicked),
            ("Remove All", self.on_remove_all_clicked),
            ("Rename", self.on_rename_clicked),
            ("Add To Group", self.on_add_to_group_clicked),
            ("Display", self.on_display_clicked),
            (
                "Validate",
                self.on_validate_clicked,
            ),  # Changed from Statistics to Validate
        ]

        self.buttons = {}
        for label, callback in buttons:
            button = QPushButton(label)
            button.setMinimumHeight(30)
            button.setMaximumHeight(30)
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            button.clicked.connect(callback)
            self.buttons[label.lower().replace(" ", "_")] = button
            layout.addWidget(button)

        layout.addStretch()

    # Stub methods for button actions
    def on_add_clicked(self):
        print("Add tilt-series button clicked (stub)")

    def on_import_clicked(self):
        print("Import tilt-series button clicked (stub)")

    def on_remove_clicked(self):
        print("Remove tilt-series button clicked (stub)")

    def on_remove_all_clicked(self):
        print("Remove All tilt-series button clicked (stub)")

    def on_rename_clicked(self):
        print("Rename tilt-series button clicked (stub)")

    def on_add_to_group_clicked(self):
        print("Add To Group button clicked (stub)")

    def on_display_clicked(self):
        print("Display tilt-series button clicked (stub)")

    def on_validate_clicked(self):
        print("Validate tilt-series button clicked (stub)")


class DetailsPanel(QWidget):
    """Bottom panel showing details of selected tilt-series with fixed height and three-column layout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 10)

        # Set fixed height and proper size policy
        self.setFixedHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Details group box
        group_box = QGroupBox("Tilt-Series Details")
        group_layout = QHBoxLayout(group_box)  # Changed to horizontal for three columns
        group_layout.setSpacing(20)

        # Create three columns for metadata display
        self.detail_labels = {}

        # Column 1: Basic info
        col1_widget = QWidget()
        col1_layout = QFormLayout(col1_widget)
        col1_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        col1_fields = [("Name", ""), ("I.D.", ""), ("Status", "")]

        for field, default_value in col1_fields:
            label = QLabel(str(default_value))
            label.setStyleSheet("QLabel { color: #333333; font-weight: normal; }")
            self.detail_labels[field] = label
            col1_layout.addRow(f"{field}:", label)

        # Column 2: Dimensions and technical
        col2_widget = QWidget()
        col2_layout = QFormLayout(col2_widget)
        col2_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        col2_fields = [("X Size", ""), ("Y Size", ""), ("Pixel Size", "")]

        for field, default_value in col2_fields:
            label = QLabel(str(default_value))
            label.setStyleSheet("QLabel { color: #333333; font-weight: normal; }")
            self.detail_labels[field] = label
            col2_layout.addRow(f"{field}:", label)

        # Column 3: Microscope settings
        col3_widget = QWidget()
        col3_layout = QFormLayout(col3_widget)
        col3_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        col3_fields = [("Voltage", ""), ("Cs", ""), ("Tilt Range", "")]

        for field, default_value in col3_fields:
            label = QLabel(str(default_value))
            label.setStyleSheet("QLabel { color: #333333; font-weight: normal; }")
            self.detail_labels[field] = label
            col3_layout.addRow(f"{field}:", label)

        # Add columns to group layout with equal spacing
        group_layout.addWidget(col1_widget, 1)
        group_layout.addWidget(col2_widget, 1)
        group_layout.addWidget(col3_widget, 1)

        layout.addWidget(group_box)

    def update_details(self, asset_data):
        """Update the details panel with selected tilt-series data."""
        # Mapping from table headers to detail fields
        field_mapping = {
            "Tilt-Series Name": "Name",
            "I.D.": "I.D.",
            "X Size": "X Size",
            "Y Size": "Y Size",
            "Pixel Size": "Pixel Size",
            "Cs": "Cs",
            "Voltage": "Voltage",
            "Tilt Range": "Tilt Range",
            "Status": "Status",
        }

        for table_header, detail_field in field_mapping.items():
            if table_header in asset_data and detail_field in self.detail_labels:
                value = asset_data[table_header]

                # Add units where appropriate
                if detail_field in {"X Size", "Y Size"}:
                    value = f"{value} px"
                elif detail_field == "Voltage":
                    value = f"{value} kV"
                elif detail_field == "Cs":
                    value = f"{value} mm"
                elif detail_field == "Pixel Size":
                    value = f"{value} Å"

                self.detail_labels[detail_field].setText(value)


class UtilsPixelSizePanel(QWidget):
    """Panel for editing pixel sizes of selected tilt-series assets with backup functionality."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.pixel_size_backups = {}  # Store original values for reversal
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Set fixed height and proper size policy
        self.setFixedHeight(50)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Label
        label = QLabel("Pixel Size (Å):")
        label.setFixedWidth(100)
        layout.addWidget(label)

        # Text field for new pixel size
        self.pixel_size_field = QLineEdit()
        self.pixel_size_field.setFixedWidth(120)
        self.pixel_size_field.setPlaceholderText("e.g., 1.2")
        layout.addWidget(self.pixel_size_field)

        # Update button
        self.update_button = QPushButton("Update Selected")
        self.update_button.setFixedWidth(120)
        self.update_button.clicked.connect(self.update_pixel_sizes)
        layout.addWidget(self.update_button)

        # Revert button
        self.revert_button = QPushButton("Revert Changes")
        self.revert_button.setFixedWidth(120)
        self.revert_button.clicked.connect(self.revert_pixel_sizes)
        layout.addWidget(self.revert_button)

        layout.addStretch()

    def update_pixel_sizes(self):
        """Update pixel sizes for selected assets using mrcfile."""
        try:
            new_pixel_size = float(self.pixel_size_field.text())
        except ValueError:
            QMessageBox.warning(
                self, "Invalid Input", "Please enter a valid pixel size value."
            )
            return

        # Get selected assets from parent
        if not hasattr(self.parent_window, "get_selected_assets"):
            QMessageBox.warning(self, "Error", "Cannot access selected assets.")
            return

        selected_assets = self.parent_window.get_selected_assets()
        if not selected_assets:
            QMessageBox.warning(
                self, "No Selection", "Please select one or more tilt-series assets."
            )
            return

        # Get project path
        project_path = None
        if (
            hasattr(self.parent_window, "parent_window")
            and self.parent_window.parent_window
        ) and hasattr(self.parent_window.parent_window, "project_path"):
            project_path = self.parent_window.parent_window.project_path

        if not project_path:
            QMessageBox.warning(self, "No Project", "No project is currently open.")
            return

        updated_count = 0
        failed_files = []

        for asset in selected_assets:
            file_path = asset.get("file_path") or asset.get("path")
            if not file_path:
                continue

            # Make path absolute if relative
            if not os.path.isabs(file_path):
                file_path = os.path.join(project_path, file_path)

            if not os.path.exists(file_path):
                failed_files.append(f"{os.path.basename(file_path)} (not found)")
                continue

            try:
                # Create backup if not already exists
                if file_path not in self.pixel_size_backups:
                    with mrcfile.open(file_path, mode="r", header_only=True) as mrc:
                        self.pixel_size_backups[file_path] = {
                            "original_pixel_size": float(
                                mrc.header.cella.x / mrc.header.nx
                            ),
                            "backup_time": datetime.now().isoformat(),
                        }

                # Update pixel size
                with mrcfile.open(file_path, mode="r+", header_only=True) as mrc:
                    # Update the header fields
                    mrc.header.cella.x = new_pixel_size * mrc.header.nx
                    mrc.header.cella.y = new_pixel_size * mrc.header.ny
                    mrc.header.cella.z = new_pixel_size * mrc.header.nz

                updated_count += 1

            except Exception as e:
                failed_files.append(f"{os.path.basename(file_path)} ({e!s})")

        # Show result message
        if updated_count > 0:
            message = f"Successfully updated pixel size to {new_pixel_size} Å for {updated_count} file(s)."
            if failed_files:
                message += "\n\nFailed to update:\n" + "\n".join(failed_files)
            QMessageBox.information(self, "Update Complete", message)
        else:
            QMessageBox.warning(
                self,
                "Update Failed",
                "Failed to update any files:\n" + "\n".join(failed_files),
            )

    def revert_pixel_sizes(self):
        """Revert pixel sizes to original values using backup data."""
        if not self.pixel_size_backups:
            QMessageBox.information(
                self, "No Changes", "No pixel size changes to revert."
            )
            return

        reverted_count = 0
        failed_files = []

        for file_path, backup_data in self.pixel_size_backups.items():
            if not os.path.exists(file_path):
                failed_files.append(f"{os.path.basename(file_path)} (not found)")
                continue

            try:
                original_pixel_size = backup_data["original_pixel_size"]

                with mrcfile.open(file_path, mode="r+", header_only=True) as mrc:
                    # Restore original pixel size
                    mrc.header.cella.x = original_pixel_size * mrc.header.nx
                    mrc.header.cella.y = original_pixel_size * mrc.header.ny
                    mrc.header.cella.z = original_pixel_size * mrc.header.nz

                reverted_count += 1

            except Exception as e:
                failed_files.append(f"{os.path.basename(file_path)} ({e!s})")

        # Clear backup data for successfully reverted files
        if reverted_count > 0:
            self.pixel_size_backups.clear()

        # Show result message
        if reverted_count > 0:
            message = f"Successfully reverted pixel sizes for {reverted_count} file(s)."
            if failed_files:
                message += "\n\nFailed to revert:\n" + "\n".join(failed_files)
            QMessageBox.information(self, "Revert Complete", message)
        else:
            QMessageBox.warning(
                self,
                "Revert Failed",
                "Failed to revert any files:\n" + "\n".join(failed_files),
            )


class TiltSeriesAssetsPanel(QWidget):
    """Main Tilt-Series Assets panel with optimized layout and proper space utilization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_asset_type = "images"  # Default selection
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Main content area with splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left side: Groups panel (fixed width)
        self.groups_panel = GroupsPanel()
        splitter.addWidget(self.groups_panel)

        # Right side: Table and details (expandable)
        right_widget = QWidget()
        right_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 10, 10, 5)
        right_layout.setSpacing(5)

        # Data table (should expand to fill space)
        self.data_table = AssetDataTable()
        right_layout.addWidget(self.data_table, 1)  # Give it stretch factor 1

        # Action buttons panel (normal view) - initially visible
        self.action_buttons = ActionButtonsPanel()
        right_layout.addWidget(self.action_buttons, 0)  # No stretch

        # Utils pixel size panel (utils view) - initially hidden
        self.utils_panel = UtilsPixelSizePanel(self)
        self.utils_panel.hide()
        right_layout.addWidget(self.utils_panel, 0)  # No stretch

        # Details panel (fixed height)
        self.details_panel = DetailsPanel()
        right_layout.addWidget(self.details_panel, 0)  # No stretch

        splitter.addWidget(right_widget)

        # Set splitter proportions and constraints
        splitter.setSizes([220, 980])  # Groups panel : Main content (total 1200)
        splitter.setStretchFactor(0, 0)  # Don't stretch groups panel
        splitter.setStretchFactor(1, 1)  # Allow main content to stretch

        # Set minimum sizes
        splitter.setChildrenCollapsible(False)

        layout.addWidget(splitter)

    def connect_signals(self):
        """Connect signals between components."""
        # Group selection changes
        self.groups_panel.group_selected.connect(self.on_group_selected)

        # Table selection changes
        self.data_table.selection_changed.connect(self.details_panel.update_details)

        # Initialize with first selection if available
        self.data_table.on_selection_changed()

    def handle_asset_type_change(self, asset_type):
        """Handle asset type selection from external toolbar."""
        if asset_type == self.current_asset_type:
            return

        print(f"Tilt-Series Assets panel: Asset type changed to {asset_type}")
        self.current_asset_type = asset_type

        # Switch between normal view and utils view
        if asset_type == "utils":
            # Hide action buttons, show utils panel
            print(
                "Switching to Utils view - hiding action buttons, showing utils panel"
            )
            self.action_buttons.hide()
            self.utils_panel.show()
        else:
            # Show action buttons, hide utils panel
            print(
                f"Switching to normal view ({asset_type}) - showing action buttons, hiding utils panel"
            )
            self.action_buttons.show()
            self.utils_panel.hide()

        # Update data table content based on asset type
        self.update_data_for_asset_type(asset_type)

    def update_data_for_asset_type(self, asset_type):
        """Update the data table based on selected asset type (stub)."""
        # This is a stub - in real implementation, this would load different data
        table = self.data_table.table

        asset_type_map = {
            "movies": "movie",
            "images": "tilt_series",
            "particles": "particle",
            "volumes": "volume",
            "refine": "refine_pkg",
            "coordinates": "coordinate",
            "utils": "tilt_series",  # Utils shows tilt-series assets
        }

        asset_suffix = asset_type_map.get(asset_type, "unknown")
        print(f"Loading {asset_suffix} data...")

        # For demo, just update the first column to show asset type
        if table.rowCount() > 0:
            for row in range(table.rowCount()):
                item = table.item(row, 1)  # Name column
                if item:
                    base_name = f"TS_{row + 1:03d}"
                    item.setText(f"{base_name}_{asset_suffix}")

    def on_group_selected(self, group_name):
        """Handle group selection changes."""
        print(f"Group selected: {group_name} (stub)")
        # TODO: Filter table data based on selected group

    def get_current_asset_type(self):
        """Get the currently selected asset type."""
        return self.current_asset_type

    def get_selected_assets(self):
        """Get the currently selected assets for pixel size editing."""
        selected_assets = []

        # Get selected rows from the data table
        table = self.data_table.table
        selected_items = table.selectedItems()

        if not selected_items:
            return selected_assets

        # Get unique rows
        selected_rows = set()
        for item in selected_items:
            selected_rows.add(item.row())

        # Extract asset data for each selected row
        for row in selected_rows:
            asset_data = {}
            for col in range(table.columnCount()):
                header = table.horizontalHeaderItem(col).text()
                item = table.item(row, col)
                asset_data[header] = item.text() if item else ""

            # Create a file path based on the tilt-series name
            # This is a simplified version - in real implementation, this would come
            # from actual data
            tilt_series_name = asset_data.get("Tilt-Series Name", "")
            if tilt_series_name:
                # Assume files are .st files in a standard location
                asset_data["file_path"] = f"{tilt_series_name}.st"
                selected_assets.append(asset_data)

        return selected_assets


# Keep backward compatibility
AssetsPanel = TiltSeriesAssetsPanel


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    panel = AssetsPanel()
    panel.setWindowTitle("Assets Panel - emClarity")
    panel.resize(1200, 800)
    panel.show()

    sys.exit(app.exec())
