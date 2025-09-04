"""
Results Panel for emClarity GUI.

This module provides the Results panel interface for viewing and analyzing
processing results including aligned movie spectra, plots, and navigation controls.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QRadioButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


class FilterPanel(QWidget):
    """Left filter panel for filtering results."""

    filter_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # Filter options
        filter_group = QGroupBox("Filter Options")
        filter_layout = QVBoxLayout(filter_group)

        # Radio button group
        self.filter_button_group = QButtonGroup()

        # Filter radio buttons
        self.all_movies_radio = QRadioButton("All Movies")
        self.by_filter_radio = QRadioButton("By Filter")
        self.show_job_details_radio = QRadioButton("Show Job Details")

        # Set default selection
        self.all_movies_radio.setChecked(True)

        # Add to button group
        self.filter_button_group.addButton(self.all_movies_radio, 0)
        self.filter_button_group.addButton(self.by_filter_radio, 1)
        self.filter_button_group.addButton(self.show_job_details_radio, 2)

        # Connect signals
        self.filter_button_group.buttonClicked.connect(self.on_filter_changed)

        # Add to layout
        filter_layout.addWidget(self.all_movies_radio)
        filter_layout.addWidget(self.by_filter_radio)
        filter_layout.addWidget(self.show_job_details_radio)

        layout.addWidget(filter_group)

        # Results list
        list_group = QGroupBox("Results")
        list_layout = QVBoxLayout(list_group)

        # Header for list
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(5, 0, 5, 0)

        id_header = QLabel("ID")
        id_header.setFont(QFont("Arial", 9, QFont.Bold))
        file_header = QLabel("File")
        file_header.setFont(QFont("Arial", 9, QFont.Bold))

        header_layout.addWidget(id_header)
        header_layout.addWidget(file_header)
        header_layout.addStretch()

        list_layout.addWidget(header_widget)

        # Results list widget
        self.results_list = QListWidget()
        self.results_list.setMaximumWidth(320)
        self.results_list.setMinimumWidth(300)

        # Add sample data (stub)
        sample_results = [
            "1 - sample_movie_001.mrc",
            "2 - sample_movie_002.mrc",
            "3 - sample_movie_003.mrc",
            "4 - sample_movie_004.mrc",
        ]

        for result in sample_results:
            self.results_list.addItem(result)

        # Select first item
        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)

        list_layout.addWidget(self.results_list)
        layout.addWidget(list_group)

        layout.addStretch()

    def on_filter_changed(self, button):
        """Handle filter radio button changes."""
        filter_type = button.text()
        print(f"Filter changed to: {filter_type}")
        self.filter_changed.emit(filter_type)


class DisplayArea(QWidget):
    """Display area for spectra and movie sum."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Title label
        title_label = QLabel(self.title)
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Display frame
        display_frame = QFrame()
        display_frame.setFrameStyle(QFrame.Box)
        display_frame.setStyleSheet(
            """
            QFrame {
                background-color: white;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
            }
        """
        )
        display_frame.setMinimumHeight(200)

        # Placeholder content
        frame_layout = QVBoxLayout(display_frame)
        placeholder = QLabel(f"{self.title}\n(Display Area)")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #888888; font-style: italic;")
        frame_layout.addWidget(placeholder)

        layout.addWidget(display_frame)


class MovieSumDisplay(QWidget):
    """Movie sum display with navigation controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Title
        title_label = QLabel("Aligned Movie Sum")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Main content area
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # Image display area
        image_frame = QFrame()
        image_frame.setFrameStyle(QFrame.Box)
        image_frame.setStyleSheet(
            """
            QFrame {
                background-color: white;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
            }
        """
        )
        image_frame.setMinimumHeight(200)

        image_layout = QVBoxLayout(image_frame)
        image_placeholder = QLabel("Movie Display\n(Image Area)")
        image_placeholder.setAlignment(Qt.AlignCenter)
        image_placeholder.setStyleSheet("color: #888888; font-style: italic;")
        image_layout.addWidget(image_placeholder)

        content_layout.addWidget(image_frame)

        # Navigation controls
        nav_widget = QWidget()
        nav_widget.setMaximumWidth(60)
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setAlignment(Qt.AlignCenter)
        nav_layout.setSpacing(5)

        # Circular navigation buttons (simulated with round buttons)
        nav_buttons = ["⬆", "⬅", "⭕", "➡", "⬇"]
        self.nav_buttons = {}

        for i, symbol in enumerate(nav_buttons):
            btn = QPushButton(symbol)
            btn.setFixedSize(32, 32)
            btn.setStyleSheet(
                """
                QPushButton {
                    border-radius: 16px;
                    background-color: #F0F0F0;
                    border: 1px solid #CCCCCC;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #E0E0E0;
                }
                QPushButton:pressed {
                    background-color: #D0D0D0;
                }
            """
            )
            btn.clicked.connect(lambda checked, s=symbol: self.on_nav_clicked(s))
            self.nav_buttons[symbol] = btn
            nav_layout.addWidget(btn)

        content_layout.addWidget(nav_widget)
        layout.addWidget(content_widget)

    def on_nav_clicked(self, direction):
        """Handle navigation button clicks."""
        print(f"Navigation clicked: {direction}")


class PlotArea(QWidget):
    """Plot area for shifts visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Title
        title_label = QLabel("Plot of Shifts")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(title_label)

        # Plot frame
        plot_frame = QFrame()
        plot_frame.setFrameStyle(QFrame.Box)
        plot_frame.setStyleSheet(
            """
            QFrame {
                background-color: white;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
            }
        """
        )
        plot_frame.setMinimumHeight(150)

        # Placeholder content
        frame_layout = QVBoxLayout(plot_frame)
        placeholder = QLabel("Shifts Plot\n(Visualization Area)")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #888888; font-style: italic;")
        frame_layout.addWidget(placeholder)

        layout.addWidget(plot_frame)


class NavigationControls(QWidget):
    """Bottom navigation controls."""

    navigation_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Navigation buttons
        self.prev_button = QPushButton("Previous")
        self.delete_button = QPushButton("Delete Job & Disk")
        self.next_button = QPushButton("Next")

        # Style the delete button differently
        self.delete_button.setStyleSheet(
            """
            QPushButton {
                background-color: #DC3545;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #C82333;
            }
        """
        )

        # Connect signals
        self.prev_button.clicked.connect(
            lambda: self.navigation_clicked.emit("previous")
        )
        self.delete_button.clicked.connect(
            lambda: self.navigation_clicked.emit("delete")
        )
        self.next_button.clicked.connect(lambda: self.navigation_clicked.emit("next"))

        # Add buttons
        layout.addWidget(self.prev_button)
        layout.addWidget(self.delete_button)
        layout.addWidget(self.next_button)

        layout.addStretch()

        # Additional controls on the right
        self.control_input = QLineEdit()
        self.control_input.setPlaceholderText("Control input...")
        self.control_input.setMaximumWidth(150)
        layout.addWidget(self.control_input)


class ResultsPanel(QWidget):
    """Main Results panel combining all components."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_action_type = "find_particles"  # Default selection
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left side: Filter panel
        self.filter_panel = FilterPanel()
        splitter.addWidget(self.filter_panel)

        # Right side: Main content area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 5)

        # Top display areas
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setSpacing(10)

        # Spectra display
        self.spectra_display = DisplayArea("Aligned Sum Spectra (Nyquist : 2.8 Å)")
        top_layout.addWidget(self.spectra_display)

        # Movie sum display
        self.movie_display = MovieSumDisplay()
        top_layout.addWidget(self.movie_display)

        content_layout.addWidget(top_widget)

        # Bottom section
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setSpacing(10)

        # Plot area (left)
        self.plot_area = PlotArea()
        bottom_layout.addWidget(self.plot_area, 1)

        # Empty space (right) to balance layout
        empty_widget = QWidget()
        empty_widget.setMinimumWidth(200)
        bottom_layout.addWidget(empty_widget)

        content_layout.addWidget(bottom_widget)

        # Navigation controls
        self.nav_controls = NavigationControls()
        content_layout.addWidget(self.nav_controls)

        splitter.addWidget(content_widget)

        # Set splitter proportions
        splitter.setSizes([350, 850])  # Filter panel : Main content

        layout.addWidget(splitter)

    def connect_signals(self):
        """Connect signals between components."""
        # Filter changes
        self.filter_panel.filter_changed.connect(self.on_filter_changed)

        # Navigation
        self.nav_controls.navigation_clicked.connect(self.on_navigation_clicked)

    def handle_action_type_change(self, action_type):
        """Handle action type selection from external toolbar."""
        if action_type == self.current_action_type:
            return

        print(f"Results panel: Action type changed to {action_type}")
        self.current_action_type = action_type

        # TODO: Update display content based on action type
        self.update_content_for_action_type(action_type)

    def update_content_for_action_type(self, action_type):
        """Update the display content based on selected action type (stub)."""
        # This is a stub - in real implementation, this would load different result data

        if action_type == "align_movies":
            self.spectra_display.title = "Movie Alignment Results"
            print("Loading movie alignment results...")
        elif action_type == "find_ctf":
            self.spectra_display.title = "CTF Estimation Results"
            print("Loading CTF estimation results...")
        elif action_type == "find_particles":
            self.spectra_display.title = "Particle Detection Results"
            print("Loading particle detection results...")
        elif action_type == "2d_classify":
            self.spectra_display.title = "2D Classification Results"
            print("Loading 2D classification results...")
        elif action_type == "3d_refinement":
            self.spectra_display.title = "3D Refinement Results"
            print("Loading 3D refinement results...")

    def on_filter_changed(self, filter_type):
        """Handle filter changes."""
        print(f"Filter changed: {filter_type}")
        # TODO: Update results list based on filter

    def on_navigation_clicked(self, action):
        """Handle navigation button clicks."""
        print(f"Navigation action: {action}")
        # TODO: Implement navigation logic

    def get_current_action_type(self):
        """Get the currently selected action type."""
        return self.current_action_type


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    panel = ResultsPanel()
    panel.setWindowTitle("Results Panel - emClarity")
    panel.resize(1200, 800)
    panel.show()

    sys.exit(app.exec())
