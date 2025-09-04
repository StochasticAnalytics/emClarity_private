import subprocess
from typing import Any, Dict, List

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ProfileValidator(QThread):
    """Thread for validating a run profile resource via SSH."""

    validation_result = Signal(
        str, str, bool, str
    )  # profile_name, resource_id, is_valid, message
    debug_output = Signal(str)  # debug message
    debug_output_end = Signal()  # signal to add spacing after method

    def __init__(
        self,
        profile_name: str,
        resource_id: str,
        hostname: str,
        username: str,
        gpus: int,
        project_path: str,
    ):
        super().__init__()
        self.profile_name = profile_name
        self.resource_id = resource_id
        self.hostname = hostname
        self.username = username
        self.gpus = gpus
        self.project_path = project_path

    def run(self):
        """Run validation checks."""
        try:
            self.debug_output.emit(
                f"Starting validation for {self.username}@{self.hostname}"
            )

            # 1. Check SSH connection
            ssh_command = f"ssh -o ConnectTimeout=5 -o BatchMode=yes {self.username}@{self.hostname} 'echo Connection successful'"
            self.debug_output.emit(f"Running SSH test: {ssh_command}")

            process = subprocess.run(
                ssh_command,
                check=False,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.debug_output.emit(f"SSH test return code: {process.returncode}")
            if process.stdout:
                self.debug_output.emit(f"SSH stdout: {process.stdout.strip()}")
            if process.stderr:
                self.debug_output.emit(f"SSH stderr: {process.stderr.strip()}")

            if process.returncode != 0:
                self.validation_result.emit(
                    self.profile_name,
                    self.resource_id,
                    False,
                    f"SSH connection failed: {process.stderr.strip() if process.stderr else 'Connection refused'}",
                )
                return

            # 2. Check project directory existence
            dir_check_command = f"ssh -o ConnectTimeout=5 -o BatchMode=yes {self.username}@{self.hostname} 'test -d {self.project_path}'"
            self.debug_output.emit(f"Checking project directory: {dir_check_command}")

            process = subprocess.run(
                dir_check_command, check=False, shell=True, timeout=10
            )
            self.debug_output.emit(f"Directory check return code: {process.returncode}")

            if process.returncode != 0:
                self.validation_result.emit(
                    self.profile_name,
                    self.resource_id,
                    False,
                    "Project directory not found on remote host.",
                )
                return

            # 3. Check project directory writability
            write_check_command = f"ssh -o ConnectTimeout=5 -o BatchMode=yes {self.username}@{self.hostname} 'test -w {self.project_path}'"
            self.debug_output.emit(f"Checking write permissions: {write_check_command}")

            process = subprocess.run(
                write_check_command, check=False, shell=True, timeout=10
            )
            self.debug_output.emit(f"Write check return code: {process.returncode}")

            if process.returncode != 0:
                self.validation_result.emit(
                    self.profile_name,
                    self.resource_id,
                    False,
                    "Project directory is not writable on remote host.",
                )
                return

            # 4. Check GPU count
            gpu_check_command = f"ssh -o ConnectTimeout=5 -o BatchMode=yes {self.username}@{self.hostname} 'nvidia-smi --list-gpus | wc -l'"
            self.debug_output.emit(f"Checking GPU count: {gpu_check_command}")

            process = subprocess.run(
                gpu_check_command,
                check=False,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.debug_output.emit(f"GPU check return code: {process.returncode}")
            if process.stdout:
                self.debug_output.emit(f"GPU count output: {process.stdout.strip()}")
            if process.stderr:
                self.debug_output.emit(f"GPU check stderr: {process.stderr.strip()}")

            if process.returncode != 0:
                self.validation_result.emit(
                    self.profile_name,
                    self.resource_id,
                    True,
                    "Could not verify GPU count (nvidia-smi not found?).",
                )
                return

            try:
                remote_gpus = int(process.stdout.strip())
                self.debug_output.emit(
                    f"Found {remote_gpus} GPUs, expected {self.gpus}"
                )
                if remote_gpus < self.gpus:
                    self.validation_result.emit(
                        self.profile_name,
                        self.resource_id,
                        False,
                        f"Expected {self.gpus} GPUs, but found {remote_gpus}.",
                    )
                    return
            except (ValueError, IndexError) as e:
                self.debug_output.emit(f"Error parsing GPU count: {e}")
                self.validation_result.emit(
                    self.profile_name,
                    self.resource_id,
                    True,
                    "Could not parse GPU count from remote host.",
                )
                return

            self.debug_output.emit("Validation completed successfully")
            self.validation_result.emit(
                self.profile_name,
                self.resource_id,
                True,
                "Profile validated successfully.",
            )
            self.debug_output_end.emit()

        except subprocess.TimeoutExpired:
            self.debug_output.emit("Validation timed out")
            self.validation_result.emit(
                self.profile_name, self.resource_id, False, "Validation timed out."
            )
            self.debug_output_end.emit()
        except Exception as e:
            self.debug_output.emit(f"Validation exception: {e}")
            self.validation_result.emit(
                self.profile_name,
                self.resource_id,
                False,
                f"An error occurred during validation: {e}",
            )
            self.debug_output_end.emit()


class RunProfileWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.profiles: Dict[
            str, List[Dict[str, Any]]
        ] = {}  # profile_name -> list of resources
        self.validator_thread = None
        self.setup_ui()
        self.load_profiles()

    def __del__(self):
        """Cleanup when widget is destroyed."""
        if self.validator_thread and self.validator_thread.isRunning():
            self.validator_thread.quit()
            self.validator_thread.wait()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Input form
        form_layout = QHBoxLayout()

        # Profile selection/creation
        self.profile_combo = QComboBox()
        self.profile_combo.setEditable(True)
        self.profile_combo.setPlaceholderText("Profile Name")
        self.profile_combo.currentTextChanged.connect(self.on_profile_selected)

        self.hostname_input = QLineEdit()
        self.hostname_input.setPlaceholderText("Hostname or IP")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.gpus_input = QSpinBox()
        self.gpus_input.setMinimum(0)
        self.gpus_input.setPrefix("GPUs: ")

        form_layout.addWidget(QLabel("Profile:"))
        form_layout.addWidget(self.profile_combo)
        form_layout.addWidget(self.hostname_input)
        form_layout.addWidget(self.username_input)
        form_layout.addWidget(self.gpus_input)

        # Buttons
        button_layout = QHBoxLayout()

        add_resource_button = QPushButton("Add Resource to Profile")
        add_resource_button.clicked.connect(self.add_resource_to_profile)
        button_layout.addWidget(add_resource_button)

        update_resource_button = QPushButton("Update Selected Resource")
        update_resource_button.clicked.connect(self.update_selected_resource)
        button_layout.addWidget(update_resource_button)

        copy_profile_button = QPushButton("Copy Profile")
        copy_profile_button.clicked.connect(self.copy_profile)
        button_layout.addWidget(copy_profile_button)

        revalidate_button = QPushButton("Re-validate Selected")
        revalidate_button.clicked.connect(self.revalidate_selected)
        button_layout.addWidget(revalidate_button)

        delete_button = QPushButton("Delete Selected")
        delete_button.clicked.connect(self.delete_selected)
        delete_button.setStyleSheet("background-color: #dc3545; color: white;")
        button_layout.addWidget(delete_button)

        clear_button = QPushButton("Clear Form")
        clear_button.clicked.connect(self.clear_form)
        button_layout.addWidget(clear_button)

        layout.addLayout(form_layout)
        layout.addLayout(button_layout)

        # Profiles tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(
            ["Profile/Resource", "Hostname", "Username", "GPUs", "Status"]
        )
        self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        layout.addWidget(self.tree)

    def on_profile_selected(self, profile_name):
        """Handle profile selection from combo box."""
        if profile_name and profile_name in self.profiles:
            # Select the profile in the tree
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                if item.text(0) == profile_name:
                    self.tree.setCurrentItem(item)
                    break

    def on_tree_selection_changed(self):
        """Handle tree selection changes."""
        current_item = self.tree.currentItem()
        if current_item:
            parent = current_item.parent()
            if parent:  # This is a resource item
                profile_name = parent.text(0)
                self.profile_combo.setCurrentText(profile_name)
                self.hostname_input.setText(current_item.text(1))
                self.username_input.setText(current_item.text(2))
                self.gpus_input.setValue(
                    int(current_item.text(3)) if current_item.text(3).isdigit() else 0
                )
            else:  # This is a profile item
                profile_name = current_item.text(0)
                self.profile_combo.setCurrentText(profile_name)
                # Clear resource fields when selecting profile
                self.hostname_input.clear()
                self.username_input.clear()
                self.gpus_input.setValue(0)

    def add_resource_to_profile(self):
        """Add a resource to a profile."""
        profile_name = self.profile_combo.currentText().strip()
        hostname = self.hostname_input.text().strip()
        username = self.username_input.text().strip()
        gpus = self.gpus_input.value()

        if not all([profile_name, hostname, username]):
            QMessageBox.warning(
                self, "Missing Information", "Please fill in all fields."
            )
            return

        if (
            not hasattr(self.parent_window, "project_path")
            or not self.parent_window.project_path
        ):
            QMessageBox.warning(
                self,
                "No Project Open",
                "Please open a project before adding a resource.",
            )
            return

        project_path = str(self.parent_window.project_path)

        # Create profile if it doesn't exist
        if profile_name not in self.profiles:
            self.profiles[profile_name] = []

        # Check if this exact resource already exists in the profile
        for resource in self.profiles[profile_name]:
            if resource["hostname"] == hostname and resource["username"] == username:
                QMessageBox.warning(
                    self,
                    "Duplicate Resource",
                    "This resource already exists in the profile.",
                )
                return

        # Create unique resource ID
        resource_id = f"{hostname}_{username}_{len(self.profiles[profile_name])}"

        resource = {
            "id": resource_id,
            "hostname": hostname,
            "username": username,
            "gpus": gpus,
            "status": "Validating...",
        }

        self.profiles[profile_name].append(resource)
        self.update_tree()
        self.update_profile_combo()
        self.save_profiles()

        # Run validation in a separate thread
        self.validator_thread = ProfileValidator(
            profile_name, resource_id, hostname, username, gpus, project_path
        )
        self.validator_thread.validation_result.connect(self.update_resource_status)
        if hasattr(self.parent_window, "debug_output"):
            self.validator_thread.debug_output.connect(self.parent_window.debug_output)
            self.validator_thread.debug_output_end.connect(
                self.parent_window.debug_output_end_method
            )
        self.validator_thread.start()

        # Clear resource fields after adding
        self.hostname_input.clear()
        self.username_input.clear()
        self.gpus_input.setValue(0)

    def update_selected_resource(self):
        """Update the selected resource."""
        current_item = self.tree.currentItem()
        if not current_item:
            QMessageBox.warning(
                self, "No Selection", "Please select a resource to update."
            )
            return

        parent = current_item.parent()
        if not parent:
            QMessageBox.warning(
                self,
                "Invalid Selection",
                "Please select a resource (not a profile) to update.",
            )
            return

        profile_name = parent.text(0)
        old_hostname = current_item.text(1)
        old_username = current_item.text(2)

        hostname = self.hostname_input.text().strip()
        username = self.username_input.text().strip()
        gpus = self.gpus_input.value()

        if not all([hostname, username]):
            QMessageBox.warning(
                self, "Missing Information", "Please fill in hostname and username."
            )
            return

        if (
            not hasattr(self.parent_window, "project_path")
            or not self.parent_window.project_path
        ):
            QMessageBox.warning(
                self,
                "No Project Open",
                "Please open a project before updating a resource.",
            )
            return

        project_path = str(self.parent_window.project_path)

        # Find and update the resource
        for resource in self.profiles[profile_name]:
            if (
                resource["hostname"] == old_hostname
                and resource["username"] == old_username
            ):
                resource["hostname"] = hostname
                resource["username"] = username
                resource["gpus"] = gpus
                resource["status"] = "Validating..."
                break

        self.update_tree()
        self.save_profiles()

        # Run validation in a separate thread
        resource_id = f"{hostname}_{username}_{gpus}"
        self.validator_thread = ProfileValidator(
            profile_name, resource_id, hostname, username, gpus, project_path
        )
        self.validator_thread.validation_result.connect(self.update_resource_status)
        if hasattr(self.parent_window, "debug_output"):
            self.validator_thread.debug_output.connect(self.parent_window.debug_output)
            self.validator_thread.debug_output_end.connect(
                self.parent_window.debug_output_end_method
            )
        self.validator_thread.start()

    def copy_profile(self):
        """Copy a profile with all its resources."""
        current_item = self.tree.currentItem()
        if not current_item:
            QMessageBox.warning(
                self, "No Selection", "Please select a profile to copy."
            )
            return

        # Get profile name (either selected profile or parent of selected resource)
        if current_item.parent():
            source_profile_name = current_item.parent().text(0)
        else:
            source_profile_name = current_item.text(0)

        # Get new profile name
        new_profile_name = self.profile_combo.currentText().strip()
        if not new_profile_name or new_profile_name == source_profile_name:
            QMessageBox.warning(
                self,
                "Invalid Name",
                "Please enter a new profile name in the Profile field.",
            )
            return

        if new_profile_name in self.profiles:
            QMessageBox.warning(
                self, "Duplicate Profile", "A profile with this name already exists."
            )
            return

        # Copy all resources from source profile
        if source_profile_name in self.profiles:
            self.profiles[new_profile_name] = []
            for resource in self.profiles[source_profile_name]:
                new_resource = {
                    "id": f"{resource['hostname']}_{resource['username']}_{len(self.profiles[new_profile_name])}",
                    "hostname": resource["hostname"],
                    "username": resource["username"],
                    "gpus": resource["gpus"],
                    "status": "Copied (not validated)",
                }
                self.profiles[new_profile_name].append(new_resource)

        self.update_tree()
        self.update_profile_combo()
        self.save_profiles()
        QMessageBox.information(
            self,
            "Profile Copied",
            f"Profile '{source_profile_name}' copied to '{new_profile_name}' with {len(self.profiles[new_profile_name])} resources.",
        )

    def delete_selected(self):
        """Delete the selected profile or resource."""
        current_item = self.tree.currentItem()
        if not current_item:
            QMessageBox.warning(
                self, "No Selection", "Please select a profile or resource to delete."
            )
            return

        parent = current_item.parent()
        if parent:  # Deleting a resource
            profile_name = parent.text(0)
            hostname = current_item.text(1)
            username = current_item.text(2)

            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete the resource '{username}@{hostname}' from profile '{profile_name}'?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                # Remove the resource
                self.profiles[profile_name] = [
                    r
                    for r in self.profiles[profile_name]
                    if not (r["hostname"] == hostname and r["username"] == username)
                ]

                # Remove profile if it has no resources left
                if not self.profiles[profile_name]:
                    del self.profiles[profile_name]

        else:  # Deleting a profile
            profile_name = current_item.text(0)
            resource_count = len(self.profiles.get(profile_name, []))

            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete the profile '{profile_name}' and all its {resource_count} resources?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                del self.profiles[profile_name]

        self.update_tree()
        self.update_profile_combo()
        self.save_profiles()
        self.clear_form()

    def clear_form(self):
        """Clear all form fields."""
        self.profile_combo.setCurrentText("")
        self.hostname_input.clear()
        self.username_input.clear()
        self.gpus_input.setValue(0)
        self.tree.clearSelection()

    def update_resource_status(self, profile_name, resource_id, is_valid, message):
        """Update the status of a specific resource."""
        if profile_name in self.profiles:
            for resource in self.profiles[profile_name]:
                if resource["id"] == resource_id:
                    resource["status"] = "Valid" if is_valid else f"Invalid: {message}"
                    break
            self.update_tree()
            self.save_profiles()

        # Clean up the thread
        if self.validator_thread:
            self.validator_thread.quit()
            self.validator_thread.wait()
            self.validator_thread = None

    def update_tree(self):
        """Update the tree widget with current profiles and resources."""
        self.tree.clear()

        for profile_name, resources in self.profiles.items():
            profile_item = QTreeWidgetItem(
                [profile_name, "", "", f"{len(resources)} resources", ""]
            )
            profile_item.setExpanded(True)

            for resource in resources:
                resource_item = QTreeWidgetItem(
                    [
                        f"{resource['username']}@{resource['hostname']}",
                        resource["hostname"],
                        resource["username"],
                        str(resource["gpus"]),
                        resource.get("status", "Unknown"),
                    ]
                )
                # Store the resource ID in UserRole for later retrieval
                resource_item.setData(0, Qt.UserRole, resource["id"])
                profile_item.addChild(resource_item)

            self.tree.addTopLevelItem(profile_item)

    def update_profile_combo(self):
        """Update the profile combo box with current profiles."""
        current_text = self.profile_combo.currentText()
        self.profile_combo.clear()
        self.profile_combo.addItems(list(self.profiles.keys()))
        self.profile_combo.setCurrentText(current_text)

    def save_profiles(self):
        if hasattr(self.parent_window, "state_manager"):
            self.parent_window.state_manager.save_run_profiles(self.profiles)

    def load_profiles(self):
        if hasattr(self.parent_window, "state_manager"):
            loaded_profiles = self.parent_window.state_manager.load_run_profiles()
            # Convert old format to new format if needed
            if loaded_profiles and isinstance(list(loaded_profiles.values())[0], dict):
                # Old format detected, convert to new format
                self.profiles = {}
                for name, old_data in loaded_profiles.items():
                    if "hostname" in old_data:  # Single resource format
                        self.profiles[name] = [
                            {
                                "id": f"{old_data['hostname']}_{old_data['username']}_0",
                                "hostname": old_data["hostname"],
                                "username": old_data["username"],
                                "gpus": old_data["gpus"],
                                "status": old_data.get("status", "Unknown"),
                            }
                        ]
            else:
                self.profiles = loaded_profiles
            self.update_tree()
            self.update_profile_combo()

    def revalidate_selected(self):
        """Re-run validation on selected resource."""
        # Debug output to see if method is called
        if hasattr(self.parent_window, "debug_output"):
            self.parent_window.debug_output("Re-validate button clicked")

        selected_item = self.tree.currentItem()
        if not selected_item:
            if hasattr(self.parent_window, "debug_output"):
                self.parent_window.debug_output("No item selected for re-validation")
            return

        # Check if project path is available
        if (
            not hasattr(self.parent_window, "project_path")
            or not self.parent_window.project_path
        ):
            QMessageBox.warning(
                self,
                "Warning",
                "No project path available. Please open a project first.",
            )
            return

        project_path = str(self.parent_window.project_path)

        # Determine profile and resource
        if selected_item.parent():  # Resource item
            profile_name = selected_item.parent().text(0)
            resource_id = selected_item.data(0, Qt.UserRole)
            if hasattr(self.parent_window, "debug_output"):
                self.parent_window.debug_output(
                    f"Selected resource: {profile_name} -> {resource_id}"
                )
        else:  # Profile item - revalidate first resource
            profile_name = selected_item.text(0)
            if hasattr(self.parent_window, "debug_output"):
                self.parent_window.debug_output(f"Selected profile: {profile_name}")
            if profile_name not in self.profiles or not self.profiles[profile_name]:
                if hasattr(self.parent_window, "debug_output"):
                    self.parent_window.debug_output(
                        f"Profile {profile_name} has no resources"
                    )
                return
            resource_id = self.profiles[profile_name][0]["id"]
            if hasattr(self.parent_window, "debug_output"):
                self.parent_window.debug_output(f"Using first resource: {resource_id}")

        # Find the resource data
        resource_data = None
        for resource in self.profiles[profile_name]:
            if resource["id"] == resource_id:
                resource_data = resource
                break

        if not resource_data:
            if hasattr(self.parent_window, "debug_output"):
                self.parent_window.debug_output(
                    f"Resource data not found for {resource_id}"
                )
            return

        if hasattr(self.parent_window, "debug_output"):
            self.parent_window.debug_output(
                f"Found resource data: {resource_data['hostname']}@{resource_data['username']}"
            )

        # Stop existing validation if running
        if self.validator_thread and self.validator_thread.isRunning():
            if hasattr(self.parent_window, "debug_output"):
                self.parent_window.debug_output("Stopping existing validation thread")
            self.validator_thread.quit()
            self.validator_thread.wait()

        # Update status to "Validating..."
        resource_data["status"] = "Validating..."
        self.update_tree()

        if hasattr(self.parent_window, "debug_output"):
            self.parent_window.debug_output("Starting re-validation...")

        # Start validation
        self.validator_thread = ProfileValidator(
            profile_name,
            resource_id,
            resource_data["hostname"],
            resource_data["username"],
            resource_data["gpus"],
            project_path,
        )

        # Connect signals
        self.validator_thread.validation_result.connect(self.update_resource_status)
        if hasattr(self.parent_window, "debug_output"):
            self.validator_thread.debug_output.connect(self.parent_window.debug_output)
            self.validator_thread.debug_output_end.connect(
                self.parent_window.debug_output_end_method
            )

        self.validator_thread.start()
