"""
emClarity command definitions and help text.

This module contains the command definitions that mirror the MATLAB version
of emClarity, providing a structured way to access all available commands.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class EmClarityCommand:
    """Represents an emClarity command with its parameters and help text."""

    name: str
    description: str
    usage: str
    parameters: List[Dict[str, Any]]
    help_text: str
    requires_gpu: bool = False
    category: str = "General"


class EmClarityCommands:
    """Container for all emClarity commands with detailed parameter definitions."""

    def __init__(self):
        """Initialize command definitions."""
        self.commands = self._define_commands()

    def _define_commands(self) -> Dict[str, EmClarityCommand]:
        """Define all available emClarity commands with detailed parameters.

        Returns:
            Dictionary mapping command names to EmClarityCommand objects
        """
        commands = {}

        # System commands
        commands["help"] = EmClarityCommand(
            name="help",
            description="Show available commands",
            usage="emClarity help",
            parameters=[],
            help_text="Display list of all available emClarity commands.",
            category="System",
        )

        commands["check"] = EmClarityCommand(
            name="check",
            description="System check for dependencies",
            usage="emClarity check",
            parameters=[],
            help_text="Check system dependencies and installation.",
            category="System",
        )

        # Project Setup
        commands["init"] = EmClarityCommand(
            name="init",
            description="Initialize new project from template matching results",
            usage="emClarity init param.m [tomoCpr iter]",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "tomoCpr_iter",
                    "type": "int",
                    "description": "TomoCPR iteration (optional)",
                    "required": False,
                },
            ],
            help_text="Create a new project from template matching results.",
            category="Project Setup",
        )

        commands["segment"] = EmClarityCommand(
            name="segment",
            description="Define subregions to reconstruct",
            usage="emClarity segment build|recon",
            parameters=[
                {
                    "name": "operation",
                    "type": "choice",
                    "choices": ["build", "recon"],
                    "description": "build: make bin10 tomos, recon: convert model files",
                    "required": True,
                }
            ],
            help_text='Define subregions to reconstruct. Use "build" to make bin10 tomos or "recon" to convert model files.',
            category="Project Setup",
        )

        commands["getActiveTilts"] = EmClarityCommand(
            name="getActiveTilts",
            description="Get number of active tilt-series",
            usage="emClarity getActiveTilts param.m",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                }
            ],
            help_text="Get the number of active tilt-series in the project.",
            category="Project Setup",
        )

        # Alignment
        commands["autoAlign"] = EmClarityCommand(
            name="autoAlign",
            description="Automatically align tilt-series",
            usage="emClarity autoAlign param.m stackName tiltFile tilt-axis rotation",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "stack_name",
                    "type": "file",
                    "description": "Stack file (.st)",
                    "required": True,
                },
                {
                    "name": "tilt_file",
                    "type": "file",
                    "description": "Tilt file (.rawtlt)",
                    "required": True,
                },
                {
                    "name": "tilt_axis",
                    "type": "float",
                    "description": "Tilt axis rotation (degrees)",
                    "required": True,
                },
                {
                    "name": "rotation",
                    "type": "float",
                    "description": "Image rotation (degrees)",
                    "required": True,
                },
            ],
            help_text="Automatically align tilt-series using fiducial markers.",
            category="Alignment",
        )

        commands["alignRaw"] = EmClarityCommand(
            name="alignRaw",
            description="Align references against individual subtomograms",
            usage="emClarity alignRaw param.m cycle [experimental_option]",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "int",
                    "description": "Cycle number",
                    "required": True,
                },
                {
                    "name": "experimental_option",
                    "type": "choice",
                    "choices": ["1", "2", "3"],
                    "description": "1: abs(ccc), 2: weighted, 3: abs(weighted)",
                    "required": False,
                },
            ],
            help_text="Align one or more references against individual subtomograms.",
            category="Alignment",
        )

        # CTF
        commands["ctf"] = EmClarityCommand(
            name="ctf",
            description="CTF estimation, correction, or refinement",
            usage="emClarity ctf estimate|refine|update|3d ...",
            parameters=[
                {
                    "name": "operation",
                    "type": "choice",
                    "choices": ["estimate", "refine", "update", "3d"],
                    "description": "CTF operation to perform",
                    "required": True,
                },
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "tilt_base",
                    "type": "string",
                    "description": "Tilt base name",
                    "required": False,
                },
                {
                    "name": "scratch_disk",
                    "type": "string",
                    "description": "Local scratch disk path",
                    "required": False,
                },
            ],
            help_text="Estimate, correct, or refine the CTF for tilt-series.",
            category="CTF",
            requires_gpu=True,
        )

        # Template Search
        commands["templateSearch"] = EmClarityCommand(
            name="templateSearch",
            description="Template matching/global search",
            usage="emClarity templateSearch param.m tomoName tomoIdx template symmetry [threshold] gpuIDX",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "tomo_name",
                    "type": "string",
                    "description": "Tomogram name",
                    "required": True,
                },
                {
                    "name": "tomo_idx",
                    "type": "int",
                    "description": "Tomogram index",
                    "required": True,
                },
                {
                    "name": "template",
                    "type": "file",
                    "description": "Template file",
                    "required": True,
                },
                {
                    "name": "symmetry",
                    "type": "string",
                    "description": "Symmetry (e.g., C1)",
                    "required": True,
                },
                {
                    "name": "threshold",
                    "type": "float",
                    "description": "Threshold override (optional)",
                    "required": False,
                },
                {
                    "name": "gpu_idx",
                    "type": "int",
                    "description": "GPU index",
                    "required": True,
                },
            ],
            help_text="Perform template matching/global search in tomograms.",
            category="Template Search",
            requires_gpu=True,
        )

        commands["cleanTemplateSearch"] = EmClarityCommand(
            name="cleanTemplateSearch",
            description="Clean search results based on neighbor constraints",
            usage="emClarity cleanTemplateSearch pixelSize distance angle neighbors",
            parameters=[
                {
                    "name": "pixel_size",
                    "type": "float",
                    "description": "Pixel size (Angstroms)",
                    "required": True,
                },
                {
                    "name": "distance",
                    "type": "float",
                    "description": "Distance to neighbor (Angstroms)",
                    "required": True,
                },
                {
                    "name": "angle",
                    "type": "float",
                    "description": "Angular deviation (degrees)",
                    "required": True,
                },
                {
                    "name": "neighbors",
                    "type": "int",
                    "description": "Minimum number of neighbors",
                    "required": True,
                },
            ],
            help_text="Clean template search results based on neighbor constraints.",
            category="Template Search",
        )

        commands["removeNeighbors"] = EmClarityCommand(
            name="removeNeighbors",
            description="Remove neighbors based on lattice constraints",
            usage="emClarity removeNeighbors pixelSize cycle distance angle neighbors",
            parameters=[
                {
                    "name": "pixel_size",
                    "type": "float",
                    "description": "Pixel size (Angstroms)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "string",
                    "description": "Cycle identifier",
                    "required": True,
                },
                {
                    "name": "distance",
                    "type": "float",
                    "description": "Distance cutoff (Angstroms)",
                    "required": True,
                },
                {
                    "name": "angle",
                    "type": "float",
                    "description": "Angle cutoff (degrees)",
                    "required": True,
                },
                {
                    "name": "neighbors",
                    "type": "int",
                    "description": "Number of neighbors",
                    "required": True,
                },
            ],
            help_text="Remove neighbors based on lattice constraints.",
            category="Template Search",
        )

        # Processing
        commands["avg"] = EmClarityCommand(
            name="avg",
            description="Average subtomograms",
            usage="emClarity avg param.m cycle stage",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "int",
                    "description": "Cycle number",
                    "required": True,
                },
                {
                    "name": "stage",
                    "type": "choice",
                    "choices": ["raw", "cluster_cls"],
                    "description": "Stage of alignment",
                    "required": True,
                },
            ],
            help_text="Average subtomograms at specified cycle and stage.",
            category="Processing",
        )

        commands["fsc"] = EmClarityCommand(
            name="fsc",
            description="Calculate the Fourier Shell Correlation",
            usage="emClarity fsc param.m cycle stage",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "int",
                    "description": "Cycle number",
                    "required": True,
                },
                {
                    "name": "stage",
                    "type": "choice",
                    "choices": ["raw", "cluster_cls"],
                    "description": "Stage of alignment",
                    "required": True,
                },
            ],
            help_text="Calculate the Fourier Shell Correlation between half-sets.",
            category="Processing",
        )

        commands["calcWeights"] = EmClarityCommand(
            name="calcWeights",
            description="Calculate weights for a given cycle",
            usage="emClarity calcWeights param.m cycle prefix symmetry [gpuIDX,tiltStart,tiltStop]",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "int",
                    "description": "Cycle number",
                    "required": True,
                },
                {
                    "name": "prefix",
                    "type": "string",
                    "description": "Output prefix",
                    "required": True,
                },
                {
                    "name": "symmetry",
                    "type": "string",
                    "description": "Symmetry (e.g., C1)",
                    "required": True,
                },
                {
                    "name": "gpu_idx",
                    "type": "int",
                    "description": "GPU index (optional)",
                    "required": False,
                },
            ],
            help_text="Calculate weights for a given cycle.",
            category="Processing",
            requires_gpu=True,
        )

        commands["mask"] = EmClarityCommand(
            name="mask",
            description="Create a mask",
            usage="emClarity mask fileNameIN.mrc fileNameOUT.mrc pixelSize [shape size center]",
            parameters=[
                {
                    "name": "input_file",
                    "type": "file",
                    "description": "Input file (.mrc) or output for geometric mask",
                    "required": True,
                },
                {
                    "name": "output_file",
                    "type": "string",
                    "description": "Output file (.mrc)",
                    "required": False,
                },
                {
                    "name": "pixel_size",
                    "type": "float",
                    "description": "Pixel size (Angstroms)",
                    "required": True,
                },
                {
                    "name": "shape",
                    "type": "choice",
                    "choices": ["sphere", "cylinder", "rectangle"],
                    "description": "Shape for geometric mask",
                    "required": False,
                },
                {
                    "name": "size",
                    "type": "string",
                    "description": "Size [nX,nY,nZ] for geometric mask",
                    "required": False,
                },
                {
                    "name": "center",
                    "type": "string",
                    "description": "Center [cX,cY,cZ] for geometric mask",
                    "required": False,
                },
            ],
            help_text="Create a mask from a volume or geometric shape.",
            category="Processing",
        )

        commands["pca"] = EmClarityCommand(
            name="pca",
            description="Principal Component Analysis for dimensionality reduction",
            usage="emClarity pca param.m cycle randomSubset [focusedMask]",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "int",
                    "description": "Cycle number",
                    "required": True,
                },
                {
                    "name": "random_subset",
                    "type": "bool",
                    "description": "Use random subset",
                    "required": True,
                },
                {
                    "name": "focused_mask",
                    "type": "choice",
                    "choices": ["0", "1", "2", "3"],
                    "description": "0: none, 1: std dev, 2: variance, 3: user supplied",
                    "required": False,
                },
            ],
            help_text="Reduce dimensionality prior to clustering, possibly on smaller subset of data.",
            category="Processing",
        )

        commands["cluster"] = EmClarityCommand(
            name="cluster",
            description="Cluster subtomograms into classes",
            usage="emClarity cluster param.m cycle",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "int",
                    "description": "Cycle number",
                    "required": True,
                },
            ],
            help_text="Use clustering approaches to sort populations.",
            category="Processing",
        )

        commands["skip"] = EmClarityCommand(
            name="skip",
            description="Skip to next cycle after class averaging",
            usage="emClarity skip param.m iter",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "iteration",
                    "type": "int",
                    "description": "Iteration number",
                    "required": True,
                },
            ],
            help_text="After averaging classes & possibly removing some, skip to next cycle.",
            category="Processing",
        )

        # Reconstruction
        commands["reconstruct"] = EmClarityCommand(
            name="reconstruct",
            description="Reconstruct volume from subtomograms",
            usage="emClarity reconstruct param.m cycle prefix symmetry maxExposure [classIDX]",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "int",
                    "description": "Cycle number",
                    "required": True,
                },
                {
                    "name": "prefix",
                    "type": "string",
                    "description": "Output prefix",
                    "required": True,
                },
                {
                    "name": "symmetry",
                    "type": "string",
                    "description": "Symmetry (e.g., C1)",
                    "required": True,
                },
                {
                    "name": "max_exposure",
                    "type": "float",
                    "description": "Max exposure (e/A^2)",
                    "required": True,
                },
                {
                    "name": "class_idx",
                    "type": "int",
                    "description": "Class index (-1 for all)",
                    "required": False,
                    "default": -1,
                },
            ],
            help_text="Reconstruct a volume from a set of subtomograms.",
            category="Reconstruction",
        )

        commands["tomoCPR"] = EmClarityCommand(
            name="tomoCPR",
            description="Tomogram Constrained Projection Refinement",
            usage="emClarity tomoCPR param.m cycle stage [nTiltStart]",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "int",
                    "description": "Cycle number",
                    "required": True,
                },
                {
                    "name": "stage",
                    "type": "choice",
                    "choices": ["Avg", "RawAlignment", "Cluster_cls"],
                    "description": "Stage of alignment",
                    "required": True,
                },
                {
                    "name": "tilt_start",
                    "type": "int",
                    "description": "Starting tilt number (optional)",
                    "required": False,
                },
            ],
            help_text="Tomogram constrained projection refinement.",
            category="Reconstruction",
        )

        # Utilities
        commands["rescale"] = EmClarityCommand(
            name="rescale",
            description="Change magnification on a volume",
            usage="emClarity rescale fileNameIN fileNameOut angPixIN angPixOut cpu/GPU",
            parameters=[
                {
                    "name": "input_file",
                    "type": "file",
                    "description": "Input file",
                    "required": True,
                },
                {
                    "name": "output_file",
                    "type": "string",
                    "description": "Output file",
                    "required": True,
                },
                {
                    "name": "pixel_in",
                    "type": "float",
                    "description": "Input pixel size (Angstroms)",
                    "required": True,
                },
                {
                    "name": "pixel_out",
                    "type": "float",
                    "description": "Output pixel size (Angstroms)",
                    "required": True,
                },
                {
                    "name": "device",
                    "type": "choice",
                    "choices": ["cpu", "GPU"],
                    "description": "Processing device",
                    "required": True,
                },
            ],
            help_text="Change the magnification on a volume.",
            category="Utilities",
        )

        commands["benchmark"] = EmClarityCommand(
            name="benchmark",
            description="Run performance benchmark",
            usage="emClarity benchmark fileNameOut fastScratchDisk nWorkers",
            parameters=[
                {
                    "name": "output_file",
                    "type": "string",
                    "description": "Output file name",
                    "required": True,
                },
                {
                    "name": "scratch_disk",
                    "type": "string",
                    "description": "Fast scratch disk path",
                    "required": True,
                },
                {
                    "name": "workers",
                    "type": "int",
                    "description": "Number of workers",
                    "required": True,
                },
            ],
            help_text="Run a performance benchmark.",
            category="Utilities",
        )

        commands["geometry"] = EmClarityCommand(
            name="geometry",
            description="Edit or analyze experimental metadata",
            usage="emClarity geometry param.m cycle stage operation vectOP STD/EVE/ODD",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "int",
                    "description": "Cycle number",
                    "required": True,
                },
                {
                    "name": "stage",
                    "type": "string",
                    "description": "Stage of alignment",
                    "required": True,
                },
                {
                    "name": "operation",
                    "type": "choice",
                    "choices": [
                        "SwitchCurrentCycle",
                        "UpdateTilts",
                        "WriteCsv",
                        "RemoveClasses",
                        "ShiftAll",
                        "ShiftBin",
                        "ListTomos",
                        "RemoveTomos",
                        "ListPercentiles",
                        "RemoveFraction",
                        "RemoveIgnoredParticles",
                        "RandomizeEulers",
                    ],
                    "description": "Geometry operation",
                    "required": True,
                },
                {
                    "name": "vect_op",
                    "type": "string",
                    "description": "Vector operation [0,0,0]",
                    "required": True,
                },
                {
                    "name": "halfset",
                    "type": "choice",
                    "choices": ["STD", "EVE", "ODD"],
                    "description": "Half-set selection",
                    "required": True,
                },
            ],
            help_text="Edit or analyze the experimental metadata.",
            category="Utilities",
        )

        commands["combineProjects"] = EmClarityCommand(
            name="combineProjects",
            description="Combine two or more projects",
            usage="emClarity combineProjects project1 project2 ...",
            parameters=[
                {
                    "name": "projects",
                    "type": "string",
                    "description": "Space-separated list of project files",
                    "required": True,
                }
            ],
            help_text="Combine two or more projects together.",
            category="Utilities",
        )

        commands["removeDuplicates"] = EmClarityCommand(
            name="removeDuplicates",
            description="Remove duplicated subtomograms",
            usage="emClarity removeDuplicates param.m cycle",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "int",
                    "description": "Cycle number",
                    "required": True,
                },
            ],
            help_text="Remove subtomos that have migrated to the same position.",
            category="Utilities",
        )

        commands["montage"] = EmClarityCommand(
            name="montage",
            description="Unstack/rotate montage elements",
            usage="emClarity montage param.m cycle stage class operation halfset",
            parameters=[
                {
                    "name": "param_file",
                    "type": "file",
                    "description": "Parameter file (.m)",
                    "required": True,
                },
                {
                    "name": "cycle",
                    "type": "int",
                    "description": "Cycle number",
                    "required": True,
                },
                {
                    "name": "stage",
                    "type": "choice",
                    "choices": ["RawAlignment", "Cluster_cls"],
                    "description": "Stage of alignment",
                    "required": True,
                },
                {
                    "name": "class_num",
                    "type": "int",
                    "description": "Class number",
                    "required": True,
                },
                {
                    "name": "operation",
                    "type": "string",
                    "description": "unstack or angles [ZXZ]",
                    "required": True,
                },
                {
                    "name": "halfset",
                    "type": "choice",
                    "choices": ["odd", "eve", "std"],
                    "description": "Half-set selection",
                    "required": True,
                },
            ],
            help_text="Unstack and/or rotate the elements of a montage about x.",
            category="Utilities",
        )

        return commands

    def get_commands_by_category(self) -> Dict[str, List[EmClarityCommand]]:
        """Get commands organized by category."""
        categories = {}
        for cmd in self.commands.values():
            if cmd.category not in categories:
                categories[cmd.category] = []
            categories[cmd.category].append(cmd)
        return categories

    def get_command(self, name: str) -> Optional[EmClarityCommand]:
        """Get a command by name."""
        return self.commands.get(name)
