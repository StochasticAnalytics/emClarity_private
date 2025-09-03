"""
Under Development Panel Widget for emClarity GUI

Shows a placeholder panel for features that are under development.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QTextEdit, QProgressBar
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor


class UnderDevelopmentPanel(QWidget):
    """A placeholder panel for features under development."""
    
    def __init__(self, feature_name: str, description: str = "", parent=None):
        super().__init__(parent)
        self.feature_name = feature_name
        self.description = description or f"The {feature_name} feature is currently under development."
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the UI for the under development panel."""
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)
        
        # Main container
        container = QFrame()
        container.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        container.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 2px dashed #dee2e6;
                border-radius: 10px;
                padding: 30px;
            }
        """)
        container.setMaximumWidth(600)
        
        container_layout = QVBoxLayout(container)
        container_layout.setAlignment(Qt.AlignCenter)
        container_layout.setSpacing(15)
        
        # Construction icon (using text emoji for now)
        icon_label = QLabel("🚧")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px;")
        container_layout.addWidget(icon_label)
        
        # Title
        title = QLabel(f"{self.feature_name}")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #495057; margin: 10px;")
        container_layout.addWidget(title)
        
        # Under development label
        dev_label = QLabel("Under Development")
        dev_label.setAlignment(Qt.AlignCenter)
        dev_font = QFont()
        dev_font.setPointSize(14)
        dev_font.setItalic(True)
        dev_label.setFont(dev_font)
        dev_label.setStyleSheet("color: #6c757d; margin-bottom: 15px;")
        container_layout.addWidget(dev_label)
        
        # Description
        desc_label = QLabel(self.description)
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #6c757d; font-size: 12px; line-height: 1.4;")
        container_layout.addWidget(desc_label)
        
        # Progress bar (animated to show activity)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ced4da;
                border-radius: 3px;
                background-color: #e9ecef;
                height: 8px;
            }
            QProgressBar::chunk {
                background-color: #007bff;
                border-radius: 2px;
            }
        """)
        container_layout.addWidget(self.progress_bar)
        
        # Status text
        status_text = QLabel("Development in progress...")
        status_text.setAlignment(Qt.AlignCenter)
        status_text.setStyleSheet("color: #6c757d; font-size: 10px; font-style: italic;")
        container_layout.addWidget(status_text)
        
        layout.addWidget(container)
        
        # Add some helpful information at the bottom
        info_frame = QFrame()
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(8)
        
        info_title = QLabel("💡 What to expect:")
        info_title.setStyleSheet("font-weight: bold; color: #495057; font-size: 11px;")
        info_layout.addWidget(info_title)
        
        features = [
            "• Enhanced user interface design",
            "• Advanced configuration options", 
            "• Improved workflow integration",
            "• Real-time feedback and validation"
        ]
        
        for feature in features:
            feature_label = QLabel(feature)
            feature_label.setStyleSheet("color: #6c757d; font-size: 10px; margin-left: 10px;")
            info_layout.addWidget(feature_label)
        
        layout.addWidget(info_frame)
        
        # Add stretch to keep content centered
        layout.addStretch()


class RunProfilesPanel(QWidget):
    """Panel that integrates the existing RunProfileWidget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the UI for the run profiles panel."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title section
        title_layout = QHBoxLayout()
        
        # Title
        title = QLabel("Run Profiles")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #333; margin-bottom: 10px;")
        title_layout.addWidget(title)
        
        title_layout.addStretch()
        
        # Help button
        help_btn = QPushButton("❓ Help")
        help_btn.setMaximumWidth(80)
        help_btn.setStyleSheet("""
            QPushButton {
                background-color: #e9ecef;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #dee2e6;
            }
        """)
        title_layout.addWidget(help_btn)
        
        layout.addLayout(title_layout)
        
        # Description
        desc = QLabel("Manage computational resources and execution profiles for emClarity workflows.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-style: italic; margin-bottom: 15px;")
        layout.addWidget(desc)
        
        # Import and embed the existing RunProfileWidget
        try:
            from profile_widgets import RunProfileWidget
            self.profile_widget = RunProfileWidget(self.parent_window)
            layout.addWidget(self.profile_widget)
        except ImportError as e:
            # Fallback if RunProfileWidget isn't available
            error_label = QLabel(f"Error loading Run Profiles widget: {e}")
            error_label.setStyleSheet("color: red; font-style: italic;")
            layout.addWidget(error_label)
            layout.addStretch()
