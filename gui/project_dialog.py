import os
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QPushButton, QFileDialog,
    QDialogButtonBox, QListWidgetItem
)

RECENT_PROJECTS_DIR = Path.home() / ".emClarity"
RECENT_PROJECTS_FILE = RECENT_PROJECTS_DIR / "recent_projects.json"
MAX_RECENT_PROJECTS = 10

class ProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Project")
        self.selected_project = None
        self.setup_ui()
        self.load_recent_projects()

    def setup_ui(self):
        self.layout = QVBoxLayout(self)
        
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.accept)
        self.layout.addWidget(self.list_widget)

        browse_button = QPushButton("Browse for a project directory...")
        browse_button.clicked.connect(self.browse)
        self.layout.addWidget(browse_button)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)

    def load_recent_projects(self):
        if not RECENT_PROJECTS_FILE.exists():
            return
        try:
            with open(RECENT_PROJECTS_FILE, 'r') as f:
                recent_projects = json.load(f)
            for project in recent_projects:
                self.list_widget.addItem(project)
        except (json.JSONDecodeError, IOError):
            # Handle corrupted or empty file
            pass

    def browse(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Project Directory")
        if dir_path:
            self.selected_project = dir_path
            self.accept()

    def accept(self):
        if self.list_widget.currentItem():
            self.selected_project = self.list_widget.currentItem().text()
        super().accept()

    @staticmethod
    def get_project_path(parent=None):
        dialog = ProjectDialog(parent)
        if dialog.exec() == QDialog.Accepted:
            if dialog.selected_project:
                ProjectDialog.add_to_recent_projects(dialog.selected_project)
                return dialog.selected_project
        return None

    @staticmethod
    def add_to_recent_projects(project_path):
        RECENT_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        recent_projects = []
        if RECENT_PROJECTS_FILE.exists():
            try:
                with open(RECENT_PROJECTS_FILE, 'r') as f:
                    recent_projects = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        if project_path in recent_projects:
            recent_projects.remove(project_path)
        
        recent_projects.insert(0, project_path)
        
        with open(RECENT_PROJECTS_FILE, 'w') as f:
            json.dump(recent_projects[:MAX_RECENT_PROJECTS], f, indent=4)
