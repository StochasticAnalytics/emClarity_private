"""
Workflow management for emClarity GUI.

This module provides workflow guidance and progress tracking to help users
understand the proper sequence of emClarity operations.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from enum import Enum


class WorkflowStage(Enum):
    """Stages in the emClarity workflow."""
    PROJECT_SETUP = "project_setup"
    CTF_ESTIMATION = "ctf_estimation"
    ALIGNMENT = "alignment"
    TEMPLATE_SEARCH = "template_search"
    ITERATIVE_REFINEMENT = "iterative_refinement"
    CLASSIFICATION = "classification"
    RECONSTRUCTION = "reconstruction"


@dataclass
class WorkflowStep:
    """A single step in the emClarity workflow."""
    id: str
    name: str
    description: str
    stage: WorkflowStage
    required_commands: List[str]
    required_parameters: List[str]
    prerequisites: List[str]  # IDs of prerequisite steps
    optional: bool = False
    typical_order: int = 0


class EmClarityWorkflow:
    """Manages the emClarity workflow and provides guidance."""
    
    def __init__(self):
        self.steps = self._define_workflow_steps()
        self.completed_steps = set()
        
    def _define_workflow_steps(self) -> Dict[str, WorkflowStep]:
        """Define the complete emClarity workflow."""
        steps = {}
        
        # Stage 1: Project Setup
        steps['project_init'] = WorkflowStep(
            id='project_init',
            name='Initialize Project',
            description='Set up project structure and basic parameters',
            stage=WorkflowStage.PROJECT_SETUP,
            required_commands=['init'],
            required_parameters=['projectName', 'workingDirectory', 'PIXEL_SIZE', 'nGPUs'],
            prerequisites=[],
            typical_order=1
        )
        
        steps['tilt_series_prep'] = WorkflowStep(
            id='tilt_series_prep',
            name='Prepare Tilt Series',
            description='Import and organize tilt series data',
            stage=WorkflowStage.PROJECT_SETUP,
            required_commands=['getActiveTilts'],
            required_parameters=['tiltSeriesPattern', 'startingAngle'],
            prerequisites=['project_init'],
            typical_order=2
        )
        
        # Stage 2: CTF Estimation
        steps['ctf_estimate'] = WorkflowStep(
            id='ctf_estimate',
            name='CTF Estimation',
            description='Estimate contrast transfer function parameters',
            stage=WorkflowStage.CTF_ESTIMATION,
            required_commands=['ctf'],
            required_parameters=['PIXEL_SIZE', 'VOLTAGE', 'Cs', 'AMPCONT'],
            prerequisites=['tilt_series_prep'],
            typical_order=3
        )
        
        steps['ctf_refine'] = WorkflowStep(
            id='ctf_refine',
            name='CTF Refinement',
            description='Refine CTF parameters (optional but recommended)',
            stage=WorkflowStage.CTF_ESTIMATION,
            required_commands=['ctf'],
            required_parameters=['defEstimate', 'defWindow'],
            prerequisites=['ctf_estimate'],
            optional=True,
            typical_order=4
        )
        
        # Stage 3: Alignment
        steps['auto_align'] = WorkflowStep(
            id='auto_align',
            name='Automatic Alignment',
            description='Automatically align tilt series',
            stage=WorkflowStage.ALIGNMENT,
            required_commands=['autoAlign'],
            required_parameters=['Ali_samplingRate', 'Ali_mRadius', 'Ali_mCenter'],
            prerequisites=['ctf_estimate'],
            typical_order=5
        )
        
        # Stage 4: Template Search
        steps['template_search'] = WorkflowStep(
            id='template_search',
            name='Template Matching',
            description='Search for particles using template matching',
            stage=WorkflowStage.TEMPLATE_SEARCH,
            required_commands=['templateSearch'],
            required_parameters=['Tmp_bandpass', 'Tmp_angleSearch', 'particleRadius'],
            prerequisites=['auto_align'],
            typical_order=6
        )
        
        steps['clean_search'] = WorkflowStep(
            id='clean_search',
            name='Clean Search Results',
            description='Clean template search results and remove neighbors',
            stage=WorkflowStage.TEMPLATE_SEARCH,
            required_commands=['cleanTemplateSearch', 'removeNeighbors'],
            required_parameters=[],
            prerequisites=['template_search'],
            typical_order=7
        )
        
        # Stage 5: Iterative Refinement
        steps['initial_alignment'] = WorkflowStep(
            id='initial_alignment',
            name='Initial Particle Alignment',
            description='Align particles against reference (Cycle 1)',
            stage=WorkflowStage.ITERATIVE_REFINEMENT,
            required_commands=['alignRaw'],
            required_parameters=['Raw_angleSearch', 'symmetry'],
            prerequisites=['clean_search'],
            typical_order=8
        )
        
        steps['averaging'] = WorkflowStep(
            id='averaging',
            name='Average Subtomograms',
            description='Calculate average from aligned particles',
            stage=WorkflowStage.ITERATIVE_REFINEMENT,
            required_commands=['avg'],
            required_parameters=[],
            prerequisites=['initial_alignment'],
            typical_order=9
        )
        
        steps['fsc_analysis'] = WorkflowStep(
            id='fsc_analysis',
            name='FSC Analysis',
            description='Calculate Fourier Shell Correlation for resolution assessment',
            stage=WorkflowStage.ITERATIVE_REFINEMENT,
            required_commands=['fsc'],
            required_parameters=[],
            prerequisites=['averaging'],
            optional=True,
            typical_order=10
        )
        
        # Stage 6: Classification
        steps['pca_analysis'] = WorkflowStep(
            id='pca_analysis',
            name='PCA Analysis',
            description='Principal component analysis for classification',
            stage=WorkflowStage.CLASSIFICATION,
            required_commands=['pca'],
            required_parameters=['Pca_clusters'],
            prerequisites=['averaging'],
            typical_order=11
        )
        
        steps['clustering'] = WorkflowStep(
            id='clustering',
            name='Cluster Analysis',
            description='Cluster particles into classes',
            stage=WorkflowStage.CLASSIFICATION,
            required_commands=['cluster'],
            required_parameters=[],
            prerequisites=['pca_analysis'],
            typical_order=12
        )
        
        # Stage 7: Reconstruction
        steps['final_reconstruction'] = WorkflowStep(
            id='final_reconstruction',
            name='Final Reconstruction',
            description='Generate final high-resolution reconstruction',
            stage=WorkflowStage.RECONSTRUCTION,
            required_commands=['reconstruct'],
            required_parameters=['Rec_boxSize'],
            prerequisites=['clustering'],
            typical_order=13
        )
        
        steps['tomo_cpr'] = WorkflowStep(
            id='tomo_cpr',
            name='Tomogram CPR',
            description='Tomogram Constrained Projection Refinement (optional)',
            stage=WorkflowStage.RECONSTRUCTION,
            required_commands=['tomoCPR'],
            required_parameters=[],
            prerequisites=['final_reconstruction'],
            optional=True,
            typical_order=14
        )
        
        return steps
    
    def get_steps_for_stage(self, stage: WorkflowStage) -> List[WorkflowStep]:
        """Get all steps for a given stage."""
        return [step for step in self.steps.values() if step.stage == stage]
    
    def get_next_steps(self) -> List[WorkflowStep]:
        """Get the next recommended steps based on completed steps."""
        available_steps = []
        
        for step in self.steps.values():
            if step.id in self.completed_steps:
                continue
                
            # Check if all prerequisites are completed
            prerequisites_met = all(
                prereq in self.completed_steps 
                for prereq in step.prerequisites
            )
            
            if prerequisites_met:
                available_steps.append(step)
        
        # Sort by typical order
        available_steps.sort(key=lambda x: x.typical_order)
        return available_steps
    
    def mark_step_completed(self, step_id: str):
        """Mark a step as completed."""
        self.completed_steps.add(step_id)
    
    def get_workflow_progress(self) -> Dict[WorkflowStage, float]:
        """Get completion percentage for each workflow stage."""
        progress = {}
        
        for stage in WorkflowStage:
            stage_steps = self.get_steps_for_stage(stage)
            if not stage_steps:
                progress[stage] = 100.0
                continue
                
            # Only count required steps for progress
            required_steps = [s for s in stage_steps if not s.optional]
            if not required_steps:
                progress[stage] = 100.0
                continue
                
            completed_required = sum(
                1 for step in required_steps 
                if step.id in self.completed_steps
            )
            
            progress[stage] = (completed_required / len(required_steps)) * 100.0
        
        return progress
    
    def get_workflow_recommendations(self) -> List[str]:
        """Get workflow recommendations based on current state."""
        recommendations = []
        next_steps = self.get_next_steps()
        
        if not next_steps:
            recommendations.append("🎉 All workflow steps completed!")
            return recommendations
        
        # Get the highest priority next step
        next_step = next_steps[0]
        recommendations.append(
            f"🎯 Next: {next_step.name} - {next_step.description}"
        )
        
        # Check for missing parameters
        missing_params = self._get_missing_parameters(next_step)
        if missing_params:
            recommendations.append(
                f"⚠️ Configure these parameters first: {', '.join(missing_params)}"
            )
        
        # Stage-specific recommendations
        if next_step.stage == WorkflowStage.CTF_ESTIMATION:
            recommendations.append(
                "💡 Tip: Accurate CTF estimation is crucial for high-resolution results"
            )
        elif next_step.stage == WorkflowStage.TEMPLATE_SEARCH:
            recommendations.append(
                "💡 Tip: Use a good quality template - it determines particle detection quality"
            )
        elif next_step.stage == WorkflowStage.ITERATIVE_REFINEMENT:
            recommendations.append(
                "💡 Tip: This stage is iterative - you may need to repeat alignment and averaging"
            )
        
        return recommendations
    
    def _get_missing_parameters(self, step: WorkflowStep) -> List[str]:
        """Get list of missing required parameters for a step."""
        # This would need to be integrated with the actual parameter system
        # For now, return empty list
        return []
