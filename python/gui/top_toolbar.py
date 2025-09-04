"""
Top Toolbar Widget for emClarity GUI.

This module provides a horizontal toolbar that sits at the top of the main window,
containing different button sets depending on the active panel. The toolbar maintains
consistent styling with the left sidebar and persists state across panel switches.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QToolButton, QWidget


class HorizontalToolbarButton(QToolButton):
    """Custom horizontal toolbar button with consistent styling."""

    def __init__(self, button_id, text, icon, parent=None):
        super().__init__(parent)
        self.button_id = button_id
        self.setText(f"{icon}\n{text}")
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setCheckable(True)
        self.setMinimumSize(80, 70)  # Similar height to sidebar width
        self.setMaximumHeight(80)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # Apply consistent styling with sidebar
        self.update_style(False)

    def update_style(self, is_selected):
        """Update button styling based on selection state."""
        if is_selected:
            self.setStyleSheet(
                """
                QToolButton {
                    background-color: #0078D4;
                    color: white;
                    border: 2px solid #106EBE;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 13px;
                    padding: 4px;
                }
                QToolButton:hover {
                    background-color: #106EBE;
                }
            """
            )
        else:
            self.setStyleSheet(
                """
                QToolButton {
                    background-color: #F5F5F5;
                    color: #333333;
                    border: 1px solid #CCCCCC;
                    border-radius: 6px;
                    font-size: 13px;
                    padding: 4px;
                }
                QToolButton:hover {
                    background-color: #E5E5E5;
                    border-color: #999999;
                }
            """
            )


class TopToolbar(QWidget):
    """Top horizontal toolbar that changes content based on active panel."""

    # Signal emitted when a toolbar button is clicked
    button_clicked = Signal(str, str)  # (panel_type, button_id)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_panel = "overview"
        self.button_states = {}  # Store selection state for each panel
        self.button_groups = {}  # Store button widgets for each panel
        self.setup_ui()

    def setup_ui(self):
        """Setup the main toolbar layout."""
        layout = QHBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(15, 8, 15, 8)

        # Container for buttons (will be updated dynamically)
        self.button_container = QWidget()
        self.button_layout = QHBoxLayout(self.button_container)
        self.button_layout.setSpacing(5)
        self.button_layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self.button_container)
        layout.addStretch()

        # Add separator line at bottom
        self.setStyleSheet(
            """
            TopToolbar {
                border-bottom: 1px solid #CCCCCC;
                background-color: #FAFAFA;
            }
        """
        )

        # Initialize toolbar content
        self.setup_panel_configurations()
        self.update_toolbar_for_panel("overview")

    def setup_panel_configurations(self):
        """Define toolbar configurations for each panel."""
        self.panel_configs = {
            "overview": [
                ("recent", "Recent Projects", "📁"),
                ("templates", "Templates", "📋"),
                ("settings", "Quick Settings", "⚙️"),
            ],
            "assets": [
                ("images", "Tilt-Series", "🖼️"),
                ("particles", "Particle Positions", "⚫"),
                ("volumes", "3D Volumes", "📦"),
                ("refine", "Refine Pkgs", "🔧"),
                ("coordinates", "Atomic Coordinates", "⚛️"),
                ("utils", "Utils", "🛠️"),
            ],
            "actions": [
                ("preprocess", "Preprocess", "🔄"),
                ("align", "Tilt-Series Alignment", "📐"),
                ("subtomo_align", "Subtomo Alignment", "🔀"),
                ("averaging", "Averaging", "📊"),
                ("classify", "Classification", "🏷️"),
                ("reconstruct", "Reconstruction", "🏗️"),
                ("refine", "Refinement", "✨"),
                ("validate", "Validation", "✅"),
            ],
            "results": [
                ("statistics", "Statistics", "📊"),
                ("plots", "Plots", "📈"),
                ("reports", "Reports", "📋"),
                ("export", "Export", "💾"),
                ("compare", "Compare", "⚖️"),
            ],
            "settings": [
                ("general", "General", "⚙️"),
                ("run_profiles", "Run Profiles", "🖥️"),
                ("paths", "Paths", "📂"),
                ("performance", "Performance", "🚀"),
                ("advanced", "Advanced", "🔧"),
                ("plugins", "Plugins", "🔌"),
            ],
            "experimental": [
                ("legacy", "Legacy Interface", "🗂️"),
                ("debug", "Debug Tools", "🐛"),
                ("experimental", "Experimental", "🧪"),
            ],
        }

        # Initialize button states for each panel
        for panel, config in self.panel_configs.items():
            if config:  # If panel has buttons
                # Set first button as default selected
                self.button_states[panel] = config[0][0]
            else:
                self.button_states[panel] = None

    def update_toolbar_for_panel(self, panel_name):
        """Update toolbar content when switching panels."""
        if panel_name == self.current_panel:
            return

        # Clear existing buttons
        self.clear_buttons()

        # Get configuration for new panel
        config = self.panel_configs.get(panel_name, [])
        if not config:
            self.current_panel = panel_name
            return

        # Create buttons for new panel
        buttons = {}
        for button_id, text, icon in config:
            button = HorizontalToolbarButton(button_id, text, icon)
            button.clicked.connect(
                lambda checked, bid=button_id: self.on_button_clicked(bid)
            )
            buttons[button_id] = button
            self.button_layout.addWidget(button)

        self.button_groups[panel_name] = buttons

        # Restore selection state
        selected_button = self.button_states.get(panel_name)
        if selected_button and selected_button in buttons:
            buttons[selected_button].setChecked(True)
            buttons[selected_button].update_style(True)

        self.current_panel = panel_name

        # Update all button styles
        self.update_button_styles()

    def on_button_clicked(self, button_id):
        """Handle toolbar button clicks."""
        # Button click will be handled by global event filter when logging is enabled

        # Update selection state for current panel
        old_selection = self.button_states.get(self.current_panel)
        self.button_states[self.current_panel] = button_id

        # Update button styles
        buttons = self.button_groups.get(self.current_panel, {})

        # Uncheck old button
        if old_selection and old_selection in buttons:
            buttons[old_selection].setChecked(False)
            buttons[old_selection].update_style(False)

        # Check new button
        if button_id in buttons:
            buttons[button_id].setChecked(True)
            buttons[button_id].update_style(True)

        # Emit signal
        self.button_clicked.emit(self.current_panel, button_id)

    def clear_buttons(self):
        """Remove all buttons from the layout."""
        while self.button_layout.count():
            child = self.button_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def update_button_styles(self):
        """Update all button styles based on current selection."""
        buttons = self.button_groups.get(self.current_panel, {})
        selected = self.button_states.get(self.current_panel)

        for button_id, button in buttons.items():
            is_selected = button_id == selected
            button.setChecked(is_selected)
            button.update_style(is_selected)

    def get_current_selection(self, panel_name=None):
        """Get the currently selected button for a panel."""
        panel = panel_name or self.current_panel
        return self.button_states.get(panel)

    def set_selection(self, panel_name, button_id):
        """Programmatically set selection for a panel."""
        if panel_name in self.button_states:
            self.button_states[panel_name] = button_id

            # Update UI if this is the current panel
            if panel_name == self.current_panel:
                self.update_button_styles()


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout

    app = QApplication(sys.argv)

    # Test window
    test_widget = QWidget()
    test_widget.setWindowTitle("Top Toolbar Test")
    test_widget.resize(1200, 200)

    layout = QVBoxLayout(test_widget)

    # Create toolbar
    toolbar = TopToolbar()
    layout.addWidget(toolbar)

    # Test panel switching
    def test_panel_switch():
        import time

        panels = [
            "overview",
            "assets",
            "actions",
            "results",
            "settings",
            "experimental",
        ]
        for panel in panels:
            toolbar.update_toolbar_for_panel(panel)
            print(f"Switched to {panel} panel")
            app.processEvents()
            time.sleep(1)

    # Status label
    status = QLabel("Toolbar will cycle through different panels...")
    layout.addWidget(status)
    layout.addStretch()

    # Connect signals
    toolbar.button_clicked.connect(
        lambda panel, button: status.setText(f"Panel: {panel}, Button: {button}")
    )

    test_widget.show()

    # Start panel cycling after a delay
    from PySide6.QtCore import QTimer

    timer = QTimer()
    timer.timeout.connect(test_panel_switch)
    timer.setSingleShot(True)
    timer.start(2000)

    sys.exit(app.exec())
