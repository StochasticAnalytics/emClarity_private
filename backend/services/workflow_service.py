"""Service for building emClarity commands and tracking pipeline state.

Translates frontend command requests into the CLI invocations that
emClarity expects, and determines which commands are available given
the current project state.
"""

from __future__ import annotations

from backend.models.workflow import (
    COMMAND_PREREQUISITES,
    CommandInfo,
    CommandRequest,
    PipelineCommand,
    WorkflowState,
)

# Human-readable labels and descriptions for each command
_COMMAND_INFO: dict[PipelineCommand, tuple[str, str]] = {
    PipelineCommand.AUTO_ALIGN: (
        "Tilt-Series Alignment",
        "Align raw tilt-series images using fiducial or patch tracking",
    ),
    PipelineCommand.CTF_ESTIMATE: (
        "CTF Estimation",
        "Estimate defocus and astigmatism for each tilt image",
    ),
    PipelineCommand.CTF_3D: (
        "3D CTF Correction",
        "Apply 3D CTF correction and reconstruct tomograms",
    ),
    PipelineCommand.TEMPLATE_SEARCH: (
        "Template Search",
        "Search for particles using a 3D template",
    ),
    PipelineCommand.INIT: (
        "Initialize Project",
        "Initialize the sub-tomogram averaging project",
    ),
    PipelineCommand.AVG: (
        "Average",
        "Compute the sub-tomogram average from aligned particles",
    ),
    PipelineCommand.ALIGN_RAW: (
        "Align Particles",
        "Refine particle orientations against the current average",
    ),
    PipelineCommand.TOMO_CPR: (
        "Tilt-Series Refinement",
        "Refine tilt-series geometry using current particle positions",
    ),
    PipelineCommand.PCA: (
        "PCA Analysis",
        "Principal component analysis for heterogeneity detection",
    ),
    PipelineCommand.CLUSTER: (
        "Classification",
        "Classify particles based on PCA eigenvectors",
    ),
    PipelineCommand.FSC: (
        "FSC Calculation",
        "Compute Fourier Shell Correlation for resolution estimation",
    ),
    PipelineCommand.RECONSTRUCT: (
        "Final Reconstruction",
        "Generate the final high-resolution 3D reconstruction",
    ),
}


class WorkflowService:
    """Build CLI commands and manage pipeline state."""

    def list_commands(self) -> list[CommandInfo]:
        """Return metadata for all available pipeline commands."""
        result: list[CommandInfo] = []
        for cmd in PipelineCommand:
            label, description = _COMMAND_INFO.get(cmd, (cmd.value, ""))
            result.append(
                CommandInfo(
                    command=cmd,
                    label=label,
                    description=description,
                    prerequisites=COMMAND_PREREQUISITES.get(cmd, []),
                )
            )
        return result

    def get_workflow_state(
        self, completed_commands: list[PipelineCommand]
    ) -> WorkflowState:
        """Determine which commands are available given completed ones.

        A command is available if all its prerequisites are in the
        completed set.
        """
        completed_set = set(completed_commands)
        available: list[PipelineCommand] = []

        for cmd, prereqs in COMMAND_PREREQUISITES.items():
            if cmd in completed_set:
                continue  # Already done
            if all(p in completed_set for p in prereqs):
                available.append(cmd)

        return WorkflowState(
            completed_commands=completed_commands,
            available_commands=available,
            current_cycle=0,
        )

    def build_cli_command(self, request: CommandRequest, param_file: str) -> list[str]:
        """Translate a CommandRequest into an emClarity CLI invocation.

        Returns the command as a list of arguments suitable for
        subprocess.Popen.
        """
        cmd = request.command
        parts: list[str] = ["emClarity"]

        if cmd == PipelineCommand.AUTO_ALIGN:
            parts.extend([
                "autoAlign",
                param_file,
                request.tilt_series_name or "",
                f"{request.tilt_series_name or ''}.rawtlt",
                "0",
            ])
        elif cmd == PipelineCommand.CTF_ESTIMATE:
            parts.extend([
                "ctf",
                "estimate",
                param_file,
                request.tilt_series_name or "",
            ])
        elif cmd == PipelineCommand.CTF_3D:
            parts.extend(["ctf", "3d", param_file])
        elif cmd == PipelineCommand.TEMPLATE_SEARCH:
            parts.extend(["templateSearch", param_file])
        elif cmd == PipelineCommand.INIT:
            parts.extend(["init", param_file])
        elif cmd == PipelineCommand.AVG:
            parts.extend([
                "avg",
                param_file,
                str(request.cycle),
                "RawAlignment" if request.cycle == 0 else "NoAlignment",
            ])
        elif cmd == PipelineCommand.ALIGN_RAW:
            parts.extend(["alignRaw", param_file, str(request.cycle)])
        elif cmd == PipelineCommand.TOMO_CPR:
            parts.extend(["tomoCPR", param_file, str(request.cycle)])
        elif cmd == PipelineCommand.PCA:
            parts.extend(["pca", param_file, str(request.cycle)])
        elif cmd == PipelineCommand.CLUSTER:
            parts.extend(["cluster", param_file, str(request.cycle)])
        elif cmd == PipelineCommand.FSC:
            parts.extend(["fsc", param_file, str(request.cycle)])
        elif cmd == PipelineCommand.RECONSTRUCT:
            parts.extend(["reconstruct", param_file, str(request.cycle)])

        return parts
