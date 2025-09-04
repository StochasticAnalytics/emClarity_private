#!/usr/bin/env python3
"""
Sidebar navigation layout for emClarity GUI.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from state_manager import GUIStateManager


class VerticalIconButton(QPushButton):
    """Custom button for sidebar navigation with icon above text."""

    def __init__(self, panel_id: str, text: str, icon: str, parent=None):
        super().__init__(parent)
        self.panel_id = panel_id
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setup_layout(text, icon)
        self.setup_styling()

    def setup_layout(self, text: str, icon: str):
        """Setup the vertical layout with icon above text."""
        # Create a widget to hold the icon and text
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 12, 6, 12)  # Increased padding
        layout.setSpacing(6)  # Increased spacing
        layout.setAlignment(Qt.AlignCenter)

        # Icon label
        icon_label = QLabel(icon)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(
            "font-size: 60px; margin: 0px;"
        )  # Much larger icon to fill toolbar width
        layout.addWidget(icon_label)

        # Text label
        text_label = QLabel(text)
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setWordWrap(True)
        text_label.setStyleSheet(
            "font-size: 11px; font-weight: normal; margin: 0px;"
        )  # Larger text
        layout.addWidget(text_label)

        # Set the widget as the button's central widget
        self.setLayout(layout)

    def setup_styling(self):
        """Setup button styling."""
        self.setStyleSheet(
            """
            VerticalIconButton {
                border: none;
                background-color: transparent;
                border-radius: 10px;
                padding: 3px;
                margin: 3px;
                min-height: 85px;  /* Increased height */
                max-height: 85px;
                min-width: 100px;  /* Increased width */
                max-width: 100px;
            }

            VerticalIconButton:hover {
                background-color: #e8f2ff;
            }

            VerticalIconButton:checked {
                background-color: #4A90E2;
                color: white;
            }

            VerticalIconButton:checked QLabel {
                color: white;
            }

            VerticalIconButton:checked:hover {
                background-color: #357ABD;
            }
        """
        )


class IconButton(QPushButton):
    """Custom button for sidebar navigation with icon support."""

    def __init__(self, text: str, icon_name: str = None, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.icon_name = icon_name
        self.setup_styling()

    def setup_styling(self):
        """Setup button styling."""
        self.setStyleSheet(
            """
            IconButton {
                text-align: left;
                padding: 15px 20px;
                border: none;
                background-color: transparent;
                font-size: 14px;
                font-weight: normal;
                border-radius: 8px;
                margin: 2px;
            }

            IconButton:hover {
                background-color: #e8f4fd;
                color: #2c5aa0;
            }

            IconButton:checked {
                background-color: #4A90E2;
                color: white;
                font-weight: bold;
            }

            IconButton:checked:hover {
                background-color: #357ABD;
            }
        """
        )

        # Set minimum size and size policy
        self.setMinimumHeight(50)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)


class OverviewPanel(QWidget):
    """Overview panel with project creation/opening options."""

    project_requested = Signal(str)  # Signal emitted when project action is requested

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state_manager = GUIStateManager()
        self.setup_ui()

    def setup_ui(self):
        """Setup the overview panel UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(30)
        layout.setContentsMargins(40, 40, 40, 40)

        # Add some top spacing
        layout.addItem(QSpacerItem(20, 60, QSizePolicy.Minimum, QSizePolicy.Fixed))

        # Main logo/title area
        self.setup_header(layout)

        # Begin section
        self.setup_begin_section(layout)

        # Recent projects section
        self.setup_recent_projects_section(layout)

        # Add stretch to push everything up
        layout.addStretch()

    def setup_header(self, layout):
        """Setup the main header with emClarity branding."""
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setAlignment(Qt.AlignCenter)
        header_layout.setSpacing(15)
        header_layout.setContentsMargins(20, 30, 20, 10)

        # Ensure header widget has sufficient minimum size
        header_widget.setMinimumSize(500, 200)  # Explicit minimum size

        # Large emClarity logo/title - simulate logo with styled text
        logo_widget = QWidget()
        logo_layout = QVBoxLayout(logo_widget)
        logo_layout.setAlignment(Qt.AlignCenter)
        logo_layout.setSpacing(5)

        # Ensure logo widget has sufficient size
        logo_widget.setMinimumSize(480, 80)

        # Main emClarity title (simulate logo) - fixed sizing to prevent cutoff
        title_label = QLabel("emClarity")
        title_font = QFont()
        title_font.setPointSize(36)  # Reduced from 48 to prevent cutoff
        title_font.setBold(True)
        title_font.setFamily("Arial")
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            """
            color: #2c5aa0;
            margin: 15px;
            background-color: white;
            padding: 25px 40px;  /* Increased horizontal padding */
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            min-width: 300px;  /* Ensure minimum width */
        """
        )
        # Ensure the label can expand
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        logo_layout.addWidget(title_label)

        # Beta overlay (simulate)
        beta_label = QLabel("beta")
        beta_font = QFont()
        beta_font.setPointSize(14)  # Increased font size
        beta_font.setItalic(True)
        beta_label.setFont(beta_font)
        beta_label.setAlignment(Qt.AlignCenter)
        beta_label.setStyleSheet("color: #888888; margin-top: -10px;")
        logo_layout.addWidget(beta_label)

        header_layout.addWidget(logo_widget)

        # Welcome text - increased font size
        welcome_label = QLabel(
            "Welcome to emClarity (Computational Imaging System for Transmission Electron Microscopy)"
        )
        welcome_font = QFont()
        welcome_font.setPointSize(14)  # Increased from 12
        welcome_label.setFont(welcome_font)
        welcome_label.setAlignment(Qt.AlignCenter)
        welcome_label.setWordWrap(True)
        welcome_label.setStyleSheet(
            "color: #333333; margin: 15px 20px;"
        )  # Increased margins
        header_layout.addWidget(welcome_label)

        # Information link - increased font size
        info_link = QLabel(
            '<a href="https://emclarity.org" style="color: #4A90E2; text-decoration: none;">For more information, manuals and tutorials please visit emclarity.org</a>'
        )
        info_link.setAlignment(Qt.AlignCenter)
        info_link.setOpenExternalLinks(True)
        info_link.setStyleSheet("margin: 8px; font-size: 13px;")  # Increased from 11px
        header_layout.addWidget(info_link)

        # Version/build information (will be populated by parent)
        self.version_labels_widget = QWidget()
        self.version_labels_layout = QVBoxLayout(self.version_labels_widget)
        self.version_labels_layout.setAlignment(Qt.AlignCenter)
        self.version_labels_layout.setSpacing(3)  # Increased spacing

        # Create version info labels with increased font size
        self.version_label = QLabel("Loading version...")
        self.commit_label = QLabel("")
        self.branch_label = QLabel("")
        self.build_label = QLabel("")

        for label in [
            self.version_label,
            self.commit_label,
            self.branch_label,
            self.build_label,
        ]:
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(
                "color: #666666; font-size: 12px; margin: 2px;"
            )  # Increased from 10px
            self.version_labels_layout.addWidget(label)

        header_layout.addWidget(self.version_labels_widget)

        layout.addWidget(header_widget)

    def setup_begin_section(self, layout):
        """Setup the Begin section with project options."""
        # Begin section header
        begin_label = QLabel("Begin")
        begin_font = QFont()
        begin_font.setPointSize(18)  # Increased from 16
        begin_font.setBold(True)
        begin_label.setFont(begin_font)
        begin_label.setStyleSheet(
            "color: #333333; margin-top: 20px; margin-bottom: 15px;"
        )  # Increased margins
        begin_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(begin_label)

        # Project actions container
        actions_widget = QWidget()
        actions_layout = QVBoxLayout(actions_widget)
        actions_layout.setSpacing(12)  # Increased spacing
        actions_layout.setAlignment(Qt.AlignCenter)

        # Create new project link with improved styling
        self.new_project_link = QLabel(
            '<a href="#new" style="color: #4A90E2; text-decoration: none;">Create a new project</a>'
        )
        self.new_project_link.setAlignment(Qt.AlignCenter)
        self.new_project_link.linkActivated.connect(
            lambda: self.project_requested.emit("new")
        )

        self.new_project_link.setStyleSheet(
            """
            QLabel {
                padding: 12px 25px;  /* Increased padding */
                font-size: 16px;  /* Increased from 15px */
                margin: 5px;
                font-weight: bold;  /* Make text bolder */
                min-height: 35px;  /* Ensure consistent height */
            }
            QLabel:hover {
                background-color: #f0f8ff;
                border-radius: 6px;
            }
        """
        )
        actions_layout.addWidget(self.new_project_link)

        # Open existing project link with improved styling
        self.open_project_link = QLabel(
            '<a href="#open" style="color: #4A90E2; text-decoration: none;">Open an existing project</a>'
        )
        self.open_project_link.setAlignment(Qt.AlignCenter)
        self.open_project_link.linkActivated.connect(
            lambda: self.project_requested.emit("open")
        )

        self.open_project_link.setStyleSheet(
            """
            QLabel {
                padding: 12px 25px;  /* Increased padding */
                font-size: 16px;  /* Increased from 15px */
                margin: 5px;
                font-weight: bold;  /* Make text bolder */
                min-height: 35px;  /* Ensure consistent height */
            }
            QLabel:hover {
                background-color: #f0f8ff;
                border-radius: 6px;
            }
        """
        )
        actions_layout.addWidget(self.open_project_link)

        layout.addWidget(actions_widget)

    def setup_recent_projects_section(self, layout):
        """Setup the recent projects section."""
        # Recent projects header
        recent_label = QLabel("Open Recent Project")
        recent_font = QFont()
        recent_font.setPointSize(16)  # Increased from 14
        recent_font.setBold(True)
        recent_label.setFont(recent_font)
        recent_label.setStyleSheet(
            "color: #333333; margin-top: 30px; margin-bottom: 15px;"
        )  # Increased margins
        recent_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(recent_label)

        # Recent projects container
        self.recent_projects_widget = QWidget()
        self.recent_projects_layout = QVBoxLayout(self.recent_projects_widget)
        self.recent_projects_layout.setSpacing(6)  # Increased spacing
        self.recent_projects_layout.setAlignment(Qt.AlignCenter)

        # Add "Browse for project..." option at the top with improved styling
        browse_link = QLabel(
            '<a href="#browse" style="color: #4A90E2; text-decoration: none;">Browse for project...</a>'
        )
        browse_link.setAlignment(Qt.AlignCenter)
        browse_link.linkActivated.connect(lambda: self.project_requested.emit("open"))

        browse_link.setStyleSheet(
            """
            QLabel {
                padding: 10px 20px;  /* Increased padding */
                font-size: 15px;  /* Increased from 14px */
                margin: 6px;
                font-weight: bold;
                border: 2px solid #4A90E2;  /* Thicker border */
                border-radius: 6px;
                background-color: #f8f9fa;
                min-height: 30px;  /* Ensure consistent height */
                min-width: 200px;  /* Ensure minimum width */
            }
            QLabel:hover {
                background-color: #e8f4fd;
                border-radius: 6px;
                border-color: #2c5aa0;  /* Darker border on hover */
            }
        """
        )
        self.recent_projects_layout.addWidget(browse_link)

        # Load and display recent projects
        self.refresh_recent_projects()

        layout.addWidget(self.recent_projects_widget)

    def refresh_recent_projects(self):
        """Refresh the recent projects list."""
        # Clear existing items except the browse link (if it exists)
        items_to_remove = []
        for i in range(self.recent_projects_layout.count()):
            item = self.recent_projects_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                # Don't remove the browse link (it contains "Browse for project")
                if not (
                    hasattr(widget, "text") and "Browse for project" in widget.text()
                ):
                    items_to_remove.append(widget)

        for widget in items_to_remove:
            widget.deleteLater()

        # Get recent projects from state manager
        recent_projects = self.state_manager.get_recent_projects(5)

        if not recent_projects:
            no_recent_label = QLabel("No recent projects")
            no_recent_label.setAlignment(Qt.AlignCenter)
            no_recent_label.setStyleSheet(
                "color: #888888; font-style: italic; padding: 12px; font-size: 13px;"
            )  # Increased font size
            self.recent_projects_layout.addWidget(no_recent_label)
        else:
            for project in recent_projects:
                project_name = project["name"]
                project_path = project["path"]

                # Create hyperlink for each recent project with improved layout
                project_link = QLabel(
                    f'<a href="{project_path}" style="color: #4A90E2; text-decoration: none;">{project_path}</a>'
                )
                project_link.setAlignment(Qt.AlignCenter)
                project_link.setWordWrap(False)  # Disable wrapping to keep on one line
                project_link.linkActivated.connect(
                    lambda path=project_path: self.open_recent_project(path)
                )

                project_link.setStyleSheet(
                    """
                    QLabel {
                        padding: 8px 20px;  /* Increased padding */
                        font-size: 14px;  /* Increased from 12px */
                        margin: 3px;
                        max-width: 600px;  /* Increased max width */
                        min-height: 30px;  /* Ensure consistent height */
                        white-space: nowrap;  /* Prevent text wrapping */
                        text-overflow: ellipsis;  /* Add ellipsis for long paths */
                    }
                    QLabel:hover {
                        background-color: #f0f8ff;
                        border-radius: 4px;
                    }
                """
                )

                self.recent_projects_layout.addWidget(project_link)

    def open_recent_project(self, project_path: str):
        """Open a recent project."""
        self.project_requested.emit(project_path)

    def set_version_info(
        self,
        version_info: str,
        commit_info: str = "",
        branch_info: str = "",
        build_info: str = "",
    ):
        """Set the version information display."""
        self.version_label.setText(version_info)
        if commit_info:
            self.commit_label.setText(commit_info)
        if branch_info:
            self.branch_label.setText(branch_info)
        if build_info:
            self.build_label.setText(build_info)


class SidebarNavigationWidget(QWidget):
    """Main sidebar navigation widget with panels."""

    panel_changed = Signal(str)  # Signal emitted when panel changes
    project_requested = Signal(str)  # Signal for project operations

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_panel = "overview"
        self.setup_ui()

    def create_nav_button(self, panel_id: str, text: str, icon: str):
        """Create a navigation button with icon and text."""
        btn = VerticalIconButton(panel_id, text, icon)
        btn.clicked.connect(lambda: self.switch_panel(panel_id))
        return btn

    def setup_ui(self):
        """Setup the sidebar navigation UI."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left sidebar with navigation buttons
        self.setup_sidebar(main_layout)

        # Right panel stack
        self.setup_panels(main_layout)

    def setup_sidebar(self, layout):
        """Setup the left sidebar with navigation buttons."""
        sidebar_frame = QFrame()
        sidebar_frame.setFrameStyle(QFrame.StyledPanel)
        sidebar_frame.setFixedWidth(
            120
        )  # Increased from 100px to accommodate larger buttons
        sidebar_frame.setStyleSheet(
            """
            QFrame {
                background-color: #f0f2f5;
                border-right: 1px solid #d0d4d8;
            }
        """
        )

        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(8, 20, 8, 20)  # Adjusted margins
        sidebar_layout.setSpacing(15)  # Increased spacing between buttons

        # Navigation buttons with icons and text below
        self.nav_buttons = {}

        # Create buttons with vertical icon + text layout
        buttons_config = [
            ("overview", "Overview", "🔵"),  # Blue circular icon
            ("assets", "Assets", "📁"),  # Yellow folder icon
            ("actions", "Actions", "🔴"),  # Red circular icon
            ("results", "Results", "📊"),  # Circular chart icon
            ("settings", "Settings", "⚙️"),  # Blue gear icon
            ("experimental", "Experimental", "📈"),  # Graph/chart icon
        ]

        for panel_id, text, icon in buttons_config:
            btn_widget = self.create_nav_button(panel_id, text, icon)
            if panel_id == "overview":
                btn_widget.setChecked(True)  # Default selection
            sidebar_layout.addWidget(btn_widget)
            self.nav_buttons[panel_id] = btn_widget

        # Add stretch to push buttons to top
        sidebar_layout.addStretch()

        layout.addWidget(sidebar_frame)

    def setup_panels(self, layout):
        """Setup the stacked widget for different panels."""
        self.panels_stack = QStackedWidget()

        # Store panel references for external access
        self.panels = {}

        # Overview panel
        self.overview_panel = OverviewPanel()
        self.overview_panel.project_requested.connect(self.project_requested)
        self.panels_stack.addWidget(self.overview_panel)
        self.panels["overview"] = self.overview_panel

        # Assets panel - use new AssetsPanel
        try:
            from .assets_panel import TiltSeriesAssetsPanel

            assets_panel = TiltSeriesAssetsPanel()
            self.panels_stack.addWidget(assets_panel)
            self.panels["assets"] = assets_panel
        except ImportError:
            # Fallback to TiltSeriesAssetsWidget if new panel not available
            try:
                from tilt_series_assets import TiltSeriesAssetsWidget

                assets_panel = TiltSeriesAssetsWidget(self.parent())
                self.panels_stack.addWidget(assets_panel)
                self.panels["assets"] = assets_panel
            except ImportError:
                # Final fallback if neither available
                assets_panel = QWidget()
                assets_layout = QVBoxLayout(assets_panel)
                assets_layout.addWidget(QLabel("Assets Panel - Asset Management"))
                assets_layout.addWidget(
                    QLabel("This will contain the Assets management interface")
                )
                assets_layout.addStretch()
                self.panels_stack.addWidget(assets_panel)
                self.panels["assets"] = assets_panel

        # Actions panel - integrate AutoAlignWidget and other action widgets
        try:
            from autoalign_widget import AutoAlignWidget

            actions_panel = AutoAlignWidget(self.parent())
            self.panels_stack.addWidget(actions_panel)
            self.panels["actions"] = actions_panel
        except ImportError:
            # Fallback if AutoAlignWidget not available
            actions_panel = QWidget()
            actions_layout = QVBoxLayout(actions_panel)
            actions_layout.addWidget(QLabel("Actions Panel"))
            actions_layout.addWidget(QLabel("This will contain:"))
            actions_layout.addWidget(QLabel("• Align Tilt Series"))
            actions_layout.addWidget(QLabel("• Align Sub Tomo"))
            actions_layout.addStretch()
            self.panels_stack.addWidget(actions_panel)
            self.panels["actions"] = actions_panel

        # Results panel - use new ResultsPanel
        try:
            from results_panel import ResultsPanel

            results_panel = ResultsPanel()
            self.panels_stack.addWidget(results_panel)
            self.panels["results"] = results_panel
        except ImportError:
            # Fallback if ResultsPanel not available
            results_panel = QWidget()
            results_layout = QVBoxLayout(results_panel)
            results_layout.addWidget(QLabel("Results Panel"))
            results_layout.addWidget(QLabel("Results visualization and analysis"))
            results_layout.addStretch()
            self.panels_stack.addWidget(results_panel)
            self.panels["results"] = results_panel

        # Settings panel - use new SettingsPanel
        try:
            from settings_panel import SettingsPanel

            settings_panel = SettingsPanel(self.parent())
            self.panels_stack.addWidget(settings_panel)
            self.panels["settings"] = settings_panel
        except ImportError:
            # Fallback if SettingsPanel not available
            settings_panel = QWidget()
            settings_layout = QVBoxLayout(settings_panel)
            settings_layout.addWidget(QLabel("Settings Panel"))
            settings_layout.addWidget(QLabel("Configuration and preferences"))
            settings_layout.addStretch()
            self.panels_stack.addWidget(settings_panel)
            self.panels["settings"] = settings_panel

        # Experimental panel - note: legacy interface moved to settings->run_profiles
        try:
            experimental_panel = QWidget()
            experimental_layout = QVBoxLayout(experimental_panel)

            # Add a header
            header_label = QLabel("Experimental Panel")
            header_font = QFont()
            header_font.setPointSize(14)
            header_font.setBold(True)
            header_label.setFont(header_font)
            header_label.setStyleSheet("color: #333333; margin: 10px; padding: 10px;")
            experimental_layout.addWidget(header_label)

            # Add info about legacy interface migration
            migration_info = QLabel(
                "ℹ️ Note: The legacy tabbed interface has been migrated to Settings → Run Profiles.\n\n"
                "This panel is reserved for experimental features and development tools."
            )
            migration_info.setWordWrap(True)
            migration_info.setStyleSheet(
                """
                background-color: #e7f3ff;
                border: 1px solid #b3d9ff;
                border-radius: 6px;
                padding: 15px;
                margin: 10px;
                color: #0066cc;
                font-size: 12px;
            """
            )
            experimental_layout.addWidget(migration_info)

            # Add placeholder content for future experimental features
            future_features = QLabel("🧪 Future Experimental Features:")
            future_features.setStyleSheet(
                "font-weight: bold; margin: 10px; font-size: 13px;"
            )
            experimental_layout.addWidget(future_features)

            features_list = [
                "• AI-assisted parameter optimization",
                "• Real-time processing feedback",
                "• Advanced visualization tools",
                "• Plugin architecture testing",
                "• Performance profiling utilities",
            ]

            for feature in features_list:
                feature_label = QLabel(feature)
                feature_label.setStyleSheet(
                    "margin-left: 20px; margin-bottom: 5px; color: #666;"
                )
                experimental_layout.addWidget(feature_label)

            experimental_layout.addStretch()

            self.panels_stack.addWidget(experimental_panel)
            self.panels["experimental"] = experimental_panel

        except Exception as e:
            print(f"Error setting up experimental panel: {e}")
            # Fallback experimental panel
            experimental_panel = QWidget()
            experimental_layout = QVBoxLayout(experimental_panel)
            experimental_layout.addWidget(QLabel("Experimental Panel"))
            experimental_layout.addWidget(QLabel("Development and testing area"))
            experimental_layout.addStretch()
            self.panels_stack.addWidget(experimental_panel)
            self.panels["experimental"] = experimental_panel

        layout.addWidget(self.panels_stack)

    def switch_panel(self, panel_name: str):
        """Switch to a different panel."""
        # Store previous panel
        previous_panel = self.current_panel

        panel_indices = {
            "overview": 0,
            "assets": 1,
            "actions": 2,
            "results": 3,
            "settings": 4,
            "experimental": 5,
        }

        if panel_name in panel_indices:
            self.panels_stack.setCurrentIndex(panel_indices[panel_name])
            self.current_panel = panel_name
            self.panel_changed.emit(panel_name)

    def get_overview_panel(self) -> OverviewPanel:
        """Get the overview panel for external access."""
        return self.overview_panel

    def refresh_recent_projects(self):
        """Refresh recent projects in overview panel."""
        self.overview_panel.refresh_recent_projects()

    def notify_panels_project_opened(self):
        """Notify all panels that a project has been opened."""
        for panel_name, panel in self.panels.items():
            if hasattr(panel, "on_project_opened"):
                try:
                    panel.on_project_opened()
                    print(f"Notified {panel_name} panel of project opening")
                except Exception as e:
                    print(f"Error notifying {panel_name} panel of project opening: {e}")

    def get_panel(self, panel_name: str):
        """Get a specific panel by name."""
        return self.panels.get(panel_name)
