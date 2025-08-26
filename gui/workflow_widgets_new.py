"""
Workflow guidance widgets for the emClarity GUI.

Provides visual workflow tracking and step-by-step guidance.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGroupBox, QTextEdit,
    QListWidget, QListWidgetItem, QSplitter
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QPalette, QColor, QPixmap, QPainter

from workflow_guide import EmClarityWorkflowGuide, WorkflowStage, WorkflowStep


class WorkflowStepWidget(QFrame):
    """Widget representing a single workflow step."""
    
    step_selected = Signal(str)  # step_id
    
    def __init__(self, step: WorkflowStep, is_completed: bool = False, 
                 is_current: bool = False, is_available: bool = False, parent=None):
        super().__init__(parent)
        self.step = step
        self.is_completed = is_completed
        self.is_current = is_current
        self.is_available = is_available
        
        self.setup_ui()
        self.update_appearance()
        
    def setup_ui(self):
        """Setup the step widget UI."""
        layout = QVBoxLayout()
        
        # Title and status
        title_layout = QHBoxLayout()
        
        # Status indicator
        self.status_label = QLabel("●")
        self.status_label.setFixedSize(16, 16)
        title_layout.addWidget(self.status_label)
        
        # Title
        title_label = QLabel(self.step.title)
        title_font = QFont()
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        # Time estimate
        if self.step.estimated_time:
            time_label = QLabel(f"~{self.step.estimated_time}")
            time_label.setStyleSheet("color: #666; font-size: 10px;")
            title_layout.addWidget(time_label)
        
        layout.addLayout(title_layout)
        
        # Description
        desc_label = QLabel(self.step.description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #555; margin: 4px 0px;")
        layout.addWidget(desc_label)
        
        # Commands and parameters (collapsed by default)
        details_layout = QHBoxLayout()
        
        if self.step.commands:
            cmd_label = QLabel(f"Commands: {', '.join(self.step.commands[:2])}")
            cmd_label.setStyleSheet("font-size: 10px; color: #777;")
            details_layout.addWidget(cmd_label)
        
        if self.step.sampling_rate:
            sampling_label = QLabel(f"Sampling: {self.step.sampling_rate}")
            sampling_label.setStyleSheet("font-size: 10px; color: #777;")
            details_layout.addWidget(sampling_label)
            
        if self.step.gpu_required:
            gpu_label = QLabel("🖥 GPU")
            gpu_label.setStyleSheet("font-size: 10px; color: #e74c3c;")
            details_layout.addWidget(gpu_label)
        
        details_layout.addStretch()
        layout.addLayout(details_layout)
        
        self.setLayout(layout)
        self.setFrameStyle(QFrame.Box)
        self.setLineWidth(1)
        self.setFixedHeight(80)
        
        # Make clickable
        self.setCursor(Qt.PointingHandCursor)
        
    def update_appearance(self):
        """Update widget appearance based on status."""
        if self.is_completed:
            self.status_label.setStyleSheet("color: #27ae60; font-size: 14px;")
            self.setStyleSheet("QFrame { background-color: #f8f9fa; border: 1px solid #27ae60; }")
        elif self.is_current:
            self.status_label.setStyleSheet("color: #3498db; font-size: 14px;")
            self.setStyleSheet("QFrame { background-color: #ebf3fd; border: 2px solid #3498db; }")
        elif self.is_available:
            self.status_label.setStyleSheet("color: #f39c12; font-size: 14px;")
            self.setStyleSheet("QFrame { background-color: #fefefe; border: 1px solid #f39c12; }")
        else:
            self.status_label.setStyleSheet("color: #95a5a6; font-size: 14px;")
            self.setStyleSheet("QFrame { background-color: #f5f5f5; border: 1px solid #bdc3c7; }")
    
    def mousePressEvent(self, event):
        """Handle click to select step."""
        if event.button() == Qt.LeftButton and (self.is_available or self.is_current):
            self.step_selected.emit(self.step.id)


class WorkflowSidebarWidget(QWidget):
    """Complete workflow sidebar widget."""
    
    step_selected = Signal(str, str)  # step_id, tab_name
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.workflow_guide = EmClarityWorkflowGuide()
        self.setup_ui()
        self.refresh_workflow()
        
    def setup_ui(self):
        """Setup the sidebar UI."""
        layout = QVBoxLayout()
        
        # Steps list (scrollable)
        steps_scroll = QScrollArea()
        self.steps_widget = QWidget()
        self.steps_layout = QVBoxLayout()
        self.steps_widget.setLayout(self.steps_layout)
        steps_scroll.setWidget(self.steps_widget)
        steps_scroll.setWidgetResizable(True)
        steps_scroll.setMaximumHeight(600)
        layout.addWidget(steps_scroll)
        
        self.setLayout(layout)
        self.setFixedWidth(300)
        
    def refresh_workflow(self):
        """Refresh the workflow display."""
        # Clear existing step widgets
        for i in reversed(range(self.steps_layout.count())):
            self.steps_layout.itemAt(i).widget().setParent(None)
        
        # Get workflow state
        next_steps = self.workflow_guide.get_next_steps()
        available_step_ids = [step.id for step in next_steps]
        
        # Add step widgets organized by stage
        for stage in WorkflowStage:
            stage_steps = self.workflow_guide.get_steps_by_stage(stage)
            if not stage_steps:
                continue
                
            # Stage header
            stage_header = QLabel(stage.value.replace('_', ' ').title())
            stage_font = QFont()
            stage_font.setBold(True)
            stage_font.setPointSize(10)
            stage_header.setFont(stage_font)
            stage_header.setStyleSheet("color: #2c3e50; margin: 8px 0px 4px 0px;")
            self.steps_layout.addWidget(stage_header)
            
            # Stage steps
            for step in stage_steps:
                is_completed = step.id in self.workflow_guide.completed_steps
                is_available = step.id in available_step_ids
                is_current = step == self.workflow_guide.current_step
                
                step_widget = WorkflowStepWidget(step, is_completed, is_current, is_available)
                step_widget.step_selected.connect(self.handle_step_selected)
                self.steps_layout.addWidget(step_widget)
        
        self.steps_layout.addStretch()
        
    
    def handle_step_selected(self, step_id: str):
        """Handle step selection."""
        step = self.workflow_guide.steps.get(step_id)
        if step and step.commands:
            # Determine which tab this step belongs to
            command = step.commands[0]  # Use first command to determine tab
            
            # Map commands to tabs
            command_to_tab = {
                'init': 'Project Setup',
                'segment': 'Project Setup', 
                'check': 'System',
                'help': 'System',
                'ctf': 'CTF',
                'autoAlign': 'Alignment',
                'alignRaw': 'Alignment',
                'templateSearch': 'Template Search',
                'cleanTemplateSearch': 'Template Search',
                'removeNeighbors': 'Template Search',
                'avg': 'Processing',
                'fsc': 'Processing',
                'pca': 'Processing',
                'cluster': 'Processing',
                'mask': 'Processing',
                'calcWeights': 'Processing',
                'skip': 'Processing',
                'reconstruct': 'Reconstruction',
                'tomoCPR': 'Reconstruction'
            }
            
            tab_name = command_to_tab.get(command, 'System')
            self.step_selected.emit(step_id, tab_name)
    
    def mark_step_completed(self, step_id: str):
        """Mark a step as completed and refresh display."""
        self.workflow_guide.mark_step_completed(step_id)
        self.refresh_workflow()
    
    def set_current_step(self, step_id: str):
        """Set the current workflow step."""
        if step_id in self.workflow_guide.steps:
            self.workflow_guide.current_step = self.workflow_guide.steps[step_id]
            self.refresh_workflow()
