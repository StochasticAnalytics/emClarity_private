"""
AutoAlign widget for emClarity GUI.

Provides interface for running emClarity autoAlign with tilt-series asset groups.
Includes validation, progress tracking, and real-time status updates using Python multiprocessing.
"""

import os
import subprocess
import threading
import time
import multiprocessing as mp
from multiprocessing import Process, Queue, Value
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox,
    QFileDialog, QMessageBox, QLabel, QTextEdit, QProgressBar,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont
from profile_widgets import RunProfileWidget
from state_manager import GUIStateManager

if TYPE_CHECKING:
    from multiprocessing import Queue as MPQueue, Value as MPValue


def align_single_asset(asset_data: Dict[str, Any], output_queue, progress_value, status_queue):
    """
    Align a single asset using emClarity autoAlign.
    This function runs in a separate process for parallel execution.
    """
    try:
        asset_name = asset_data['name']
        status_queue.put(f"Starting alignment for {asset_name}")
        
        # Update progress
        with progress_value.get_lock():
            progress_value.value = 10
            
        # Build emClarity command
        cmd = [
            asset_data['emclarity_path'],
            'autoAlign',
            asset_data['project_name'],
            asset_data['tilt_series_name'],
            asset_data['raw_stack'],
            str(asset_data['unbinned_pixel_size']),
            str(asset_data['target_pixel_size']),
            str(asset_data['voltage']),
            str(asset_data['cs']),
            str(asset_data['amplitude_contrast'])
        ]
        
        status_queue.put(f"Running: {' '.join(cmd)}")
        
        # Run the alignment
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=asset_data['working_dir']
        )
        
        # Monitor output for progress
        for line in iter(process.stdout.readline, ''):
            if line:
                line = line.strip()
                status_queue.put(f"[{asset_name}] {line}")
                
                # Parse progress indicators from emClarity output
                if "Progress:" in line:
                    try:
                        prog = int(line.split("Progress:")[1].split("%")[0].strip())
                        with progress_value.get_lock():
                            progress_value.value = max(10, min(90, prog))
                    except:
                        pass
                elif "Completed" in line:
                    with progress_value.get_lock():
                        progress_value.value = 90
                        
        return_code = process.wait()
        
        if return_code == 0:
            with progress_value.get_lock():
                progress_value.value = 100
            output_queue.put({'asset': asset_name, 'success': True, 'message': 'Completed successfully'})
            status_queue.put(f"Completed alignment for {asset_name}")
        else:
            output_queue.put({'asset': asset_name, 'success': False, 'message': f'Failed with exit code {return_code}'})
            status_queue.put(f"Failed alignment for {asset_name}")
            
    except Exception as e:
        output_queue.put({'asset': asset_name, 'success': False, 'message': f'Error: {str(e)}'})
        status_queue.put(f"Error in {asset_name}: {str(e)}")


class AlignmentWorker(QThread):
    """Worker thread for managing multiple alignment processes with real-time progress tracking."""
    
    progress_updated = Signal(int, str)  # Overall progress percentage, current asset
    asset_progress_updated = Signal(str, int)  # Asset name, progress percentage
    status_updated = Signal(str)    # Status message
    log_updated = Signal(str)       # Log output
    finished = Signal(bool, str)    # Success, message
    
    def __init__(self, group_assets: Dict, alignment_params: Dict):
        super().__init__()
        self.group_assets = group_assets
        self.alignment_params = alignment_params
        self.processes = []
        self.should_stop = False
        
    def run(self):
        """Run alignment for all assets in the group using multiprocessing."""
        try:
            asset_list = list(self.group_assets.items())
            total_assets = len(asset_list)
            
            if total_assets == 0:
                self.finished.emit(False, "No assets to align")
                return
                
            self.status_updated.emit(f"Starting alignment for {total_assets} assets...")
            
            # Create shared memory for progress tracking
            manager = mp.Manager()
            output_queue = manager.Queue()
            status_queue = manager.Queue()
            
            # Progress values for each asset
            progress_values = {}
            processes = []
            
            # Start alignment processes
            for asset_name, asset_data in asset_list:
                if self.should_stop:
                    break
                    
                # Create shared progress value for this asset
                progress_values[asset_name] = manager.Value('i', 0)
                
                # Prepare asset data for alignment
                align_data = {
                    'name': asset_name,
                    'emclarity_path': self.alignment_params.get('emclarity_path', 'emClarity'),
                    'project_name': self.alignment_params.get('project_name', 'project'),
                    'tilt_series_name': asset_name,
                    'raw_stack': asset_data.get('raw_stack', ''),
                    'unbinned_pixel_size': self.alignment_params.get('unbinned_pixel_size', 1.0),
                    'target_pixel_size': self.alignment_params.get('target_pixel_size', 4.0),
                    'voltage': self.alignment_params.get('voltage', 300),
                    'cs': self.alignment_params.get('cs', 2.7),
                    'amplitude_contrast': self.alignment_params.get('amplitude_contrast', 0.07),
                    'working_dir': self.alignment_params.get('working_dir', os.getcwd())
                }
                
                # Start alignment process
                process = Process(
                    target=align_single_asset,
                    args=(align_data, output_queue, progress_values[asset_name], status_queue)
                )
                process.start()
                processes.append((process, asset_name))
                
                self.status_updated.emit(f"Started alignment for {asset_name}")
                time.sleep(0.5)  # Small delay between starts
                
            # Monitor progress
            completed_assets = 0
            failed_assets = 0
            
            while completed_assets + failed_assets < total_assets and not self.should_stop:
                # Update individual asset progress
                for asset_name, progress_val in progress_values.items():
                    with progress_val.get_lock():
                        current_progress = progress_val.value
                    self.asset_progress_updated.emit(asset_name, current_progress)
                
                # Calculate overall progress
                total_progress = sum(
                    progress_val.value for progress_val in progress_values.values()
                )
                overall_progress = int(total_progress / total_assets) if total_assets > 0 else 0
                self.progress_updated.emit(overall_progress, f"{completed_assets + failed_assets}/{total_assets} assets")
                
                # Check for status updates
                try:
                    while True:
                        status_msg = status_queue.get_nowait()
                        self.log_updated.emit(status_msg)
                        self.status_updated.emit(status_msg)
                except:
                    pass
                    
                # Check for completed assets
                try:
                    while True:
                        result = output_queue.get_nowait()
                        if result['success']:
                            completed_assets += 1
                            self.log_updated.emit(f"✓ {result['asset']}: {result['message']}")
                        else:
                            failed_assets += 1
                            self.log_updated.emit(f"✗ {result['asset']}: {result['message']}")
                except:
                    pass
                    
                time.sleep(0.1)  # Small delay for GUI responsiveness
                
            # Wait for all processes to complete
            for process, asset_name in processes:
                if process.is_alive():
                    process.join(timeout=1.0)
                    if process.is_alive():
                        process.terminate()
                        
            # Final status
            if self.should_stop:
                self.finished.emit(False, "Alignment stopped by user")
            elif failed_assets == 0:
                self.progress_updated.emit(100, f"All {total_assets} assets completed")
                self.finished.emit(True, f"Successfully aligned all {total_assets} assets")
            else:
                self.finished.emit(False, f"Completed {completed_assets}, failed {failed_assets} out of {total_assets} assets")
                
        except Exception as e:
            self.finished.emit(False, f"Error in alignment worker: {str(e)}")
            
    def stop(self):
        """Stop all running alignment processes."""
        self.should_stop = True
        for process, _ in self.processes:
            if process.is_alive():
                process.terminate()


class AutoAlignWidget(QWidget):
    """Widget for configuring and running emClarity autoAlign with asset groups."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.state_manager = GUIStateManager()
        self.worker = None
        self.selected_group = None
        self.group_assets = {}
        self.asset_progress = {}  # Track individual asset progress
        self.setup_ui()
        # Don't load asset groups until a project is available
        
    def showEvent(self, event):
        """Called when the widget becomes visible - refresh profile list and asset groups."""
        super().showEvent(event)
        self.update_profile_list()
        # Only load asset groups if we have a project path and preserve selection
        if hasattr(self.parent_window, 'project_path') and self.parent_window.project_path:
            # Save current selection
            current_selection = self.group_combo.currentText()
            self.load_asset_groups()
            # Restore selection if it still exists
            if current_selection and current_selection != "Select a group...":
                index = self.group_combo.findText(current_selection)
                if index >= 0:
                    self.group_combo.setCurrentIndex(index)
                    
    def on_project_opened(self):
        """Called when a project is opened - load asset groups for the new project."""
        # Reset selection when opening a new project
        self.selected_group = None
        self.load_asset_groups()
        
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Tilt-Series Alignment (AutoAlign)")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Description
        desc = QLabel(
            "Automatically align tilt-series using fiducial markers or correlation-based methods.\n"
            "Select a tilt-series asset group to align all validated assets in parallel.\n"
            "All assets in the group must be validated before alignment can begin."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(desc)
        
        # Main content in horizontal layout
        main_layout = QHBoxLayout()
        
        # Left side - Group selection and parameters
        left_panel = self.create_left_panel()
        main_layout.addWidget(left_panel, 2)  # 2/3 of width
        
        # Right side - Run configuration and progress
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel, 1)  # 1/3 of width
        
        layout.addLayout(main_layout)
        
        # Run controls
        run_layout = QHBoxLayout()
        
        self.run_button = QPushButton("Run AutoAlign")
        self.run_button.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 10px;")
        self.run_button.clicked.connect(self.run_alignment)
        run_layout.addWidget(self.run_button)
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; padding: 10px;")
        self.stop_button.clicked.connect(self.stop_alignment)
        self.stop_button.setEnabled(False)
        run_layout.addWidget(self.stop_button)
        
        layout.addLayout(run_layout)
        self.run_button.clicked.connect(self.run_autoalign)
        layout.addWidget(self.run_button)
        
    def create_left_panel(self) -> QGroupBox:
        """Create the left panel with asset group selection and parameters."""
        group = QGroupBox("Tilt-Series Asset Group Selection")
        layout = QVBoxLayout(group)
        
        # Group Selection section
        group_select_group = QGroupBox("Select Asset Group")
        group_layout = QVBoxLayout(group_select_group)
        
        # Group selection combo box
        select_layout = QHBoxLayout()
        select_layout.addWidget(QLabel("Asset Group:"))
        self.group_combo = QComboBox()
        self.group_combo.currentTextChanged.connect(self.on_group_selected)
        select_layout.addWidget(self.group_combo)
        
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.load_asset_groups)
        select_layout.addWidget(refresh_button)
        
        group_layout.addLayout(select_layout)
        
        # Group assets tree view
        self.group_assets_tree = QTreeWidget()
        self.group_assets_tree.setHeaderLabels(["Asset", "Status", "Files"])
        self.group_assets_tree.setMaximumHeight(200)
        
        # Set column widths - make first column wider for asset names
        self.group_assets_tree.setColumnWidth(0, 300)  # Wide for asset names
        self.group_assets_tree.setColumnWidth(1, 120)  # Status
        self.group_assets_tree.setColumnWidth(2, 150)  # Files
        
        self.group_assets_tree.setAlternatingRowColors(True)
        group_layout.addWidget(self.group_assets_tree)
        
        # Validation status
        self.validation_status = QLabel("No group selected")
        self.validation_status.setStyleSheet("color: #666; font-weight: bold;")
        group_layout.addWidget(self.validation_status)
        
        layout.addWidget(group_select_group)
        
        # Alignment Parameters section  
        align_group = QGroupBox("Alignment Parameters")
        align_layout = QFormLayout(align_group)
        
        # Project name
        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText("e.g., project_001")
        self.project_name.setText("project_001")
        align_layout.addRow("Project Name:", self.project_name)
        
        # Pixel sizes
        self.unbinned_pixel_size = QDoubleSpinBox()
        self.unbinned_pixel_size.setRange(0.1, 10.0)
        self.unbinned_pixel_size.setValue(1.0)
        self.unbinned_pixel_size.setSuffix(" Å")
        self.unbinned_pixel_size.setDecimals(3)
        align_layout.addRow("Unbinned Pixel Size:", self.unbinned_pixel_size)
        
        self.target_pixel_size = QDoubleSpinBox()
        self.target_pixel_size.setRange(1.0, 20.0)
        self.target_pixel_size.setValue(4.0)
        self.target_pixel_size.setSuffix(" Å")
        self.target_pixel_size.setDecimals(1)
        align_layout.addRow("Target Pixel Size:", self.target_pixel_size)
        
        # Microscope parameters
        self.voltage = QSpinBox()
        self.voltage.setRange(80, 300)
        self.voltage.setValue(300)
        self.voltage.setSuffix(" keV")
        align_layout.addRow("Voltage:", self.voltage)
        
        self.cs = QDoubleSpinBox()
        self.cs.setRange(0.0, 5.0)
        self.cs.setValue(2.7)
        self.cs.setSuffix(" mm")
        self.cs.setDecimals(1)
        align_layout.addRow("Cs:", self.cs)
        
        self.amplitude_contrast = QDoubleSpinBox()
        self.amplitude_contrast.setRange(0.0, 1.0)
        self.amplitude_contrast.setValue(0.07)
        self.amplitude_contrast.setDecimals(3)
        align_layout.addRow("Amplitude Contrast:", self.amplitude_contrast)
        
        layout.addWidget(align_group)
        
        return group
        
        return group
        
    def create_right_panel(self) -> QGroupBox:
        """Create the right panel with run configuration and progress tracking."""
        group = QGroupBox("Run Configuration & Progress")
        layout = QVBoxLayout(group)
        
        # Run Profile section
        profile_group = QGroupBox("Run Profile")
        profile_layout = QFormLayout(profile_group)
        
        # Profile selection
        self.profile_combo = QComboBox()
        self.profile_combo.currentTextChanged.connect(self.update_scratch_disk_display)
        self.update_profile_list()
        profile_layout.addRow("Profile:", self.profile_combo)
        
        # Processes per GPU
        self.processes_per_gpu = QSpinBox()
        self.processes_per_gpu.setRange(1, 16)
        self.processes_per_gpu.setValue(2)
        self.processes_per_gpu.setToolTip("Number of processes per GPU (adjust based on memory)")
        profile_layout.addRow("Processes per GPU:", self.processes_per_gpu)
        
        # Fast scratch disk (read-only display)
        self.scratch_display = QLineEdit()
        self.scratch_display.setReadOnly(True)
        self.scratch_display.setPlaceholderText("Will show profile's fast scratch disk")
        self.scratch_display.setStyleSheet("background-color: #f8f9fa;")
        profile_layout.addRow("Fast Scratch Disk:", self.scratch_display)
        
        scratch_help = QLabel("Fast scratch disk is configured in the run profile")
        scratch_help.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
        profile_layout.addRow("", scratch_help)
        
        layout.addWidget(profile_group)
        
        # Progress section
        progress_group = QGroupBox("Alignment Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        # Overall progress
        progress_layout.addWidget(QLabel("Overall Progress:"))
        self.overall_progress = QProgressBar()
        self.overall_progress.setTextVisible(True)
        progress_layout.addWidget(self.overall_progress)
        
        # Individual asset progress
        progress_layout.addWidget(QLabel("Individual Asset Progress:"))
        self.asset_progress_tree = QTreeWidget()
        self.asset_progress_tree.setHeaderLabels(["Asset", "Progress", "Status"])
        self.asset_progress_tree.setMaximumHeight(150)
        progress_layout.addWidget(self.asset_progress_tree)
        
        layout.addWidget(progress_group)
        
        # Status section
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        
        self.status_label = QLabel("Ready to run")
        self.status_label.setStyleSheet("color: #28a745; font-weight: bold;")
        status_layout.addWidget(self.status_label)
        
        # Log output
        self.log_output = QTextEdit()
        self.log_output.setMaximumHeight(100)
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("background-color: #f8f9fa; font-family: monospace; font-size: 10px;")
        status_layout.addWidget(QLabel("Log Output:"))
        status_layout.addWidget(self.log_output)
        
        layout.addWidget(status_group)
        
        return group
        
    def browse_file(self, line_edit: QLineEdit, title: str, file_filter: str):
        """Browse for a file and set it in the line edit."""
        current_dir = getattr(self.parent_window, 'project_path', os.getcwd())
        if hasattr(self.parent_window, 'project_path'):
            current_dir = os.path.join(current_dir, 'rawData')
            
        filename, _ = QFileDialog.getOpenFileName(self, title, current_dir, file_filter)
        if filename:
            # Make path relative to project if possible
            if hasattr(self.parent_window, 'project_path'):
                try:
                    rel_path = os.path.relpath(filename, self.parent_window.project_path)
                    line_edit.setText(rel_path)
                except ValueError:
                    line_edit.setText(filename)
            else:
                line_edit.setText(filename)
                
    def browse_directory(self, line_edit: QLineEdit, title: str):
        """Browse for a directory and set it in the line edit."""
        current_dir = getattr(self.parent_window, 'project_path', os.getcwd())
        dirname = QFileDialog.getExistingDirectory(self, title, current_dir)
        if dirname:
            line_edit.setText(dirname)
            
    def update_profile_list(self):
        """Update the profile combo box with available profiles."""
        self.profile_combo.clear()
        
        # Add a debug message to see if this is being called
        if hasattr(self.parent_window, 'debug_output'):
            self.parent_window.debug_output("Updating profile list in AutoAlign")
            
        if hasattr(self.parent_window, 'tab_widget'):
            # Find the System tab and get profiles
            for i in range(self.parent_window.tab_widget.count()):
                tab_text = self.parent_window.tab_widget.tabText(i)
                if hasattr(self.parent_window, 'debug_output'):
                    self.parent_window.debug_output(f"Checking tab: {tab_text}")
                    
                if tab_text == "System":
                    system_tab = self.parent_window.tab_widget.widget(i)
                    
                    # Look for RunProfileWidget - it should be in a layout
                    def find_profile_widget(widget):
                        if isinstance(widget, RunProfileWidget):
                            return widget
                        for child in widget.children():
                            if hasattr(child, 'children'):
                                result = find_profile_widget(child)
                                if result:
                                    return result
                        return None
                    
                    profile_widget = find_profile_widget(system_tab)
                    if profile_widget and hasattr(profile_widget, 'profiles'):
                        profile_names = list(profile_widget.profiles.keys())
                        if hasattr(self.parent_window, 'debug_output'):
                            self.parent_window.debug_output(f"Found profiles: {profile_names}")
                        self.profile_combo.addItems(profile_names)
                        # Update scratch disk display for the first profile
                        if profile_names:
                            self.update_scratch_disk_display()
                        return
                    else:
                        if hasattr(self.parent_window, 'debug_output'):
                            self.parent_window.debug_output("No profile widget found or no profiles attribute")
                    break
        
        if hasattr(self.parent_window, 'debug_output'):
            self.parent_window.debug_output("Profile update completed")
            
    def update_scratch_disk_display(self):
        """Update the fast scratch disk display based on selected profile."""
        # For now, default to 'ram' since we haven't implemented profile-based scratch disk yet
        self.scratch_display.setText("ram")
        
    def get_profile_data(self, profile_name: str) -> Optional[Dict[str, Any]]:
        """Get profile data for the specified profile name."""
        if not hasattr(self.parent_window, 'tab_widget'):
            return None
            
        for i in range(self.parent_window.tab_widget.count()):
            if self.parent_window.tab_widget.tabText(i) == "System":
                system_tab = self.parent_window.tab_widget.widget(i)
                
                def find_profile_widget(widget):
                    if isinstance(widget, RunProfileWidget):
                        return widget
                    for child in widget.children():
                        if hasattr(child, 'children'):
                            result = find_profile_widget(child)
                            if result:
                                return result
                    return None
                
                profile_widget = find_profile_widget(system_tab)
                if profile_widget and hasattr(profile_widget, 'profiles'):
                    if profile_name in profile_widget.profiles:
                        return profile_widget.profiles[profile_name]
                break
        return None
                        
    def validate_inputs(self) -> tuple[bool, str]:
        """Validate all inputs and return (is_valid, error_message)."""
        # Check required files
        if not self.stack_input.text().strip():
            return False, "Tilt-series stack file is required"
            
        if not self.rawtlt_input.text().strip():
            return False, "Raw tilt file is required"
            
        # Check if project is open
        if not hasattr(self.parent_window, 'project_path'):
            return False, "No project is open. Please open a project first."
            
        # Check if files exist
        project_path = self.parent_window.project_path
        stack_path = os.path.join(project_path, self.stack_input.text())
        rawtlt_path = os.path.join(project_path, self.rawtlt_input.text())
        
        if not os.path.exists(stack_path):
            return False, f"Stack file not found: {stack_path}"
            
        if not os.path.exists(rawtlt_path):
            return False, f"Raw tilt file not found: {rawtlt_path}"
            
        # Check profile selection
        if not self.profile_combo.currentText():
            return False, "Please select a run profile"
            
        return True, ""
        
    def generate_parameter_file(self) -> str:
        """Generate a parameter file for autoAlign with default values."""
        params = []
        
        # Required parameters with defaults for autoAlign
        params.append(f"subTomoMeta=autoAlign_{os.path.splitext(os.path.basename(self.stack_input.text()))[0]}")
        
        # Default microscope parameters (will be configurable in project settings later)
        params.append("PIXEL_SIZE=2.5e-10")
        params.append("Cs=2.7e-3")
        params.append("VOLTAGE=300e3")
        params.append("AMPCONT=0.04")
        params.append("symmetry=C1")
        
        # Get GPU and CPU info from selected profile
        profile_name = self.profile_combo.currentText()
        profile_resources = self.get_profile_data(profile_name)
        
        if profile_resources and len(profile_resources) > 0:
            # Use first resource for now
            resource = profile_resources[0]
            total_gpus = resource.get('gpus', 1)
            total_cores = total_gpus * self.processes_per_gpu.value()
            params.append(f"nGPUs={total_gpus}")
            params.append(f"nCpuCores={total_cores}")
        else:
            # Fallback values
            params.append("nGPUs=1")
            params.append(f"nCpuCores={self.processes_per_gpu.value()}")
            
        # Fast scratch disk (default to ram)
        params.append("fastScratchDisk=ram")
            
        return "\n".join(params)
        
    def run_autoalign(self):
        """Run the autoAlign command."""
        # Validate inputs
        is_valid, error_msg = self.validate_inputs()
        if not is_valid:
            QMessageBox.warning(self, "Invalid Input", error_msg)
            return
            
    def load_asset_groups(self):
        """Load tilt-series asset groups from state manager."""
        try:
            # Load flat assets and rebuild groups structure like TiltSeriesAssetsWidget does
            flat_assets = self.state_manager.load_tilt_series_assets()
            
            # Rebuild groups structure
            self.group_assets = {}
            for unique_key, asset_data in flat_assets.items():
                group_name = asset_data.get('group', 'Default')
                
                # Extract original asset name (handle both old and new formats)
                if '::' in unique_key:
                    # New format: "group::asset_name"
                    asset_name = asset_data.get('original_name', unique_key.split('::', 1)[1])
                else:
                    # Old format compatibility: use the key as asset name
                    asset_name = unique_key
                
                if group_name not in self.group_assets:
                    self.group_assets[group_name] = {}
                    
                # Remove group and original_name info from asset data for clean storage
                clean_asset = {k: v for k, v in asset_data.items() if k not in ['group', 'original_name']}
                clean_asset['name'] = asset_name  # Ensure name is set correctly
                self.group_assets[group_name][asset_name] = clean_asset
            
            # Update combo box with group names only
            self.group_combo.clear()
            self.group_combo.addItem("Select a group...")
            for group_name in self.group_assets.keys():
                self.group_combo.addItem(group_name)
                
            print(f"Loaded {len(self.group_assets)} groups: {list(self.group_assets.keys())}")
                
        except Exception as e:
            print(f"Error loading asset groups: {e}")
            self.group_assets = {}
            
    def on_group_selected(self, group_name: str):
        """Handle group selection change."""
        if group_name == "Select a group..." or not group_name:
            self.selected_group = None
            self.group_assets_tree.clear()
            self.validation_status.setText("No group selected")
            self.validation_status.setStyleSheet("color: #666; font-weight: bold;")
            self.run_button.setEnabled(False)
            return
            
        self.selected_group = group_name
        self.update_group_display()
        self.validate_group()
        
    def update_group_display(self):
        """Update the group assets tree display."""
        self.group_assets_tree.clear()
        
        if not self.selected_group or self.selected_group not in self.group_assets:
            return
            
        group_data = self.group_assets[self.selected_group]
        
        for asset_name, asset_data in group_data.items():
            item = QTreeWidgetItem(self.group_assets_tree)
            item.setText(0, asset_name)
            
            # Status based on validation - check multiple validation indicators
            is_validated = (
                asset_data.get('status') == 'Validated' or
                (asset_data.get('stack_validated', False) and asset_data.get('tilt_validated', False))
            )
            
            if is_validated:
                item.setText(1, "✓ Validated")
                item.setForeground(1, Qt.GlobalColor.darkGreen)
            else:
                item.setText(1, "✗ Not Validated")
                item.setForeground(1, Qt.GlobalColor.darkRed)
                
            # Files info
            files = []
            if asset_data.get('raw_stack'):
                files.append("Stack")
            if asset_data.get('tilt_file'):
                files.append("Tilt")
            if asset_data.get('dimensions'):
                files.append("Dims")
            item.setText(2, ", ".join(files) if files else "No files")
            
    def validate_group(self):
        """Check if all assets in the group are validated and ready for alignment."""
        if not self.selected_group or self.selected_group not in self.group_assets:
            return False
            
        group_data = self.group_assets[self.selected_group]
        
        if not group_data:
            self.validation_status.setText("Group is empty")
            self.validation_status.setStyleSheet("color: #dc3545; font-weight: bold;")
            self.run_button.setEnabled(False)
            return False
            
        total_assets = len(group_data)
        
        # Count validated assets using the same logic as display
        validated_assets = 0
        for asset in group_data.values():
            is_validated = (
                asset.get('status') == 'Validated' or
                (asset.get('stack_validated', False) and asset.get('tilt_validated', False))
            )
            if is_validated:
                validated_assets += 1
        
        if validated_assets == total_assets:
            self.validation_status.setText(f"✓ All {total_assets} assets validated - Ready to align")
            self.validation_status.setStyleSheet("color: #28a745; font-weight: bold;")
            self.run_button.setEnabled(True)
            return True
        else:
            self.validation_status.setText(f"✗ {validated_assets}/{total_assets} assets validated - Cannot align")
            self.validation_status.setStyleSheet("color: #dc3545; font-weight: bold;")
            self.run_button.setEnabled(False)
            return False
            
    def run_alignment(self):
        """Run alignment for the selected asset group."""
        if not self.validate_group():
            QMessageBox.warning(self, "Cannot Run", "All assets in the group must be validated before alignment.")
            return
            
        # Get alignment parameters
        alignment_params = {
            'project_name': self.project_name.text().strip() or "project_001",
            'unbinned_pixel_size': self.unbinned_pixel_size.value(),
            'target_pixel_size': self.target_pixel_size.value(),
            'voltage': self.voltage.value(),
            'cs': self.cs.value(),
            'amplitude_contrast': self.amplitude_contrast.value(),
            'emclarity_path': 'emClarity',  # TODO: Get from profile
            'working_dir': getattr(self.parent_window, 'project_path', os.getcwd())
        }
        
        # Confirm alignment
        group_data = self.group_assets[self.selected_group]
        asset_count = len(group_data)
        
        reply = QMessageBox.question(
            self, "Run Alignment",
            f"Run alignment for {asset_count} assets in group '{self.selected_group}'?\n\n"
            f"This will run multiple alignment processes in parallel.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        # Start alignment worker
        self.worker = AlignmentWorker(group_data, alignment_params)
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.asset_progress_updated.connect(self.on_asset_progress_updated)
        self.worker.status_updated.connect(self.on_status_updated)
        self.worker.log_updated.connect(self.on_log_updated)
        self.worker.finished.connect(self.on_alignment_finished)
        
        # Update UI for running state
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("Starting alignment...")
        self.status_label.setStyleSheet("color: #ffc107; font-weight: bold;")
        
        # Initialize progress tracking
        self.asset_progress_tree.clear()
        for asset_name in group_data.keys():
            item = QTreeWidgetItem(self.asset_progress_tree)
            item.setText(0, asset_name)
            item.setText(1, "0%")
            item.setText(2, "Waiting...")
            
        self.worker.start()
        
    def stop_alignment(self):
        """Stop the running alignment."""
        if self.worker:
            self.worker.stop()
            self.worker.wait()
            
    def on_progress_updated(self, progress: int, current_info: str):
        """Handle overall progress updates."""
        self.overall_progress.setValue(progress)
        self.overall_progress.setFormat(f"{progress}% - {current_info}")
        
    def on_asset_progress_updated(self, asset_name: str, progress: int):
        """Handle individual asset progress updates."""
        for i in range(self.asset_progress_tree.topLevelItemCount()):
            item = self.asset_progress_tree.topLevelItem(i)
            if item.text(0) == asset_name:
                item.setText(1, f"{progress}%")
                if progress == 100:
                    item.setText(2, "Completed")
                    item.setForeground(2, Qt.GlobalColor.darkGreen)
                elif progress > 0:
                    item.setText(2, "Running...")
                    item.setForeground(2, Qt.GlobalColor.blue)
                break
                
    def on_status_updated(self, status: str):
        """Handle status updates."""
        self.status_label.setText(status)
        
    def on_log_updated(self, log_message: str):
        """Handle log updates."""
        self.log_output.append(log_message)
        
    def on_alignment_finished(self, success: bool, message: str):
        """Handle alignment completion."""
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
        if success:
            self.status_label.setText("Alignment completed successfully")
            self.status_label.setStyleSheet("color: #28a745; font-weight: bold;")
            self.overall_progress.setValue(100)
            QMessageBox.information(self, "Alignment Complete", message)
        else:
            self.status_label.setText("Alignment failed")
            self.status_label.setStyleSheet("color: #dc3545; font-weight: bold;")
            QMessageBox.warning(self, "Alignment Failed", message)
            
        self.worker = None
        
    def browse_file(self, line_edit: QLineEdit, title: str, file_filter: str):
        """Browse for a file and set it in the line edit."""
        current_dir = getattr(self.parent_window, 'project_path', os.getcwd())
        if hasattr(self.parent_window, 'project_path'):
            current_dir = os.path.join(current_dir, 'rawData')
            
        filename, _ = QFileDialog.getOpenFileName(self, title, current_dir, file_filter)
        if filename:
            # Make path relative to project if possible
            if hasattr(self.parent_window, 'project_path'):
                try:
                    rel_path = os.path.relpath(filename, self.parent_window.project_path)
                    line_edit.setText(rel_path)
                except ValueError:
                    line_edit.setText(filename)
            else:
                line_edit.setText(filename)
                
    def browse_directory(self, line_edit: QLineEdit, title: str):
        """Browse for a directory and set it in the line edit."""
        current_dir = getattr(self.parent_window, 'project_path', os.getcwd())
        dirname = QFileDialog.getExistingDirectory(self, title, current_dir)
        if dirname:
            line_edit.setText(dirname)

    def update_profile_list(self):
        """Update the profile combo box with available profiles."""
        try:
            if hasattr(self.parent_window, "run_profile_widget"):
                profiles = self.parent_window.run_profile_widget.get_all_profiles()
                self.profile_combo.clear()
                for profile_name in profiles.keys():
                    self.profile_combo.addItem(profile_name)
                    
                if profiles:
                    self.update_scratch_disk_display()
        except Exception as e:
            print(f"Error updating profile list: {e}")
            
    def update_scratch_disk_display(self):
        """Update the scratch disk display based on selected profile."""
        try:
            profile_name = self.profile_combo.currentText()
            if hasattr(self.parent_window, "run_profile_widget") and profile_name:
                profiles = self.parent_window.run_profile_widget.get_all_profiles()
                if profile_name in profiles:
                    fast_disk = profiles[profile_name].get("fast_scratch_disk", "Not configured")
                    self.scratch_display.setText(fast_disk)
                else:
                    self.scratch_display.setText("Profile not found")
            else:
                self.scratch_display.setText("No profile selected")
        except Exception as e:
            self.scratch_display.setText(f"Error: {e}")

