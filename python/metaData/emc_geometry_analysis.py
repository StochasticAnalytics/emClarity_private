#!/usr/bin/env python3
"""
Python emClarity Geometry Analysis Tool

This module provides Python equivalents of BH_geometryAnalysis.m functionality,
with enhanced visualization and analysis capabilities using the star file format.

Key Features:
- Load geometry data from star files or converted MATLAB files
- Generate comprehensive 4-panel tomogram summary plots
- Analyze particle distributions, correlations, and quality metrics
- Support for cycle-specific and tomogram-specific analysis
- Interactive plotting and statistical summaries

Author: emClarity Development Team
Date: September 3, 2025
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.io
import seaborn as sns
import starfile
from matplotlib.backends.backend_pdf import PdfPages
from scipy import stats

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up plotting style
plt.style.use("default")
sns.set_palette("husl")


class EmClarityGeometryAnalyzer:
    """
    Main class for emClarity geometry analysis and visualization.

    Provides functionality to:
    - Load geometry data from various sources (star files, MATLAB files)
    - Generate comprehensive tomogram analysis plots
    - Perform statistical analysis of particle distributions
    - Export results in multiple formats
    """

    def __init__(self, metadata_source: Union[str, Path]):
        """
        Initialize the geometry analyzer.

        Args:
            metadata_source: Path to metadata (star directory or .mat file)
        """
        self.metadata_source = Path(metadata_source)
        self.geometry_data = {}
        self.tilt_geometry = {}
        self.metadata = {}
        self.current_cycle = None

        # Data column mappings (based on emClarity conventions)
        self.COLS = {
            "ccc": 0,  # Cross-correlation coefficient
            "subtomo_idx": 3,  # Subtomogram index (1-based in MATLAB, 0-based here)
            "half_set": 6,  # Half set (1=ODD, 2=EVE)
            "x_coord": 10,  # X coordinate
            "y_coord": 11,  # Y coordinate
            "z_coord": 12,  # Z coordinate
            "phi": 13,  # Euler angle phi
            "psi": 14,  # Euler angle psi
            "theta": 15,  # Euler angle theta
            "class": 25,  # Class assignment
            "defocus_u": 7,  # Defocus U
            "defocus_v": 8,  # Defocus V
            "tilt_angle": 19,  # Tilt angle for this particle
            "dose": 20,  # Cumulative dose
        }

        self._load_metadata()

    def _load_metadata(self):
        """Load metadata from source (star files or MATLAB file)."""
        if self.metadata_source.is_dir():
            self._load_star_metadata()
        elif self.metadata_source.suffix == ".mat":
            self._load_matlab_metadata()
        else:
            raise ValueError(f"Unsupported metadata source: {self.metadata_source}")

    def _load_star_metadata(self):
        """Load metadata from star file directory structure."""
        logger.info(f"Loading star file metadata from {self.metadata_source}")

        # Load top-level metadata
        metadata_file = self.metadata_source / "metadata.star"
        if metadata_file.exists():
            meta_df = starfile.read(metadata_file)
            self.metadata = meta_df.iloc[0].to_dict() if len(meta_df) > 0 else {}

        # Load geometry data
        geometry_dir = self.metadata_source / "geometry"
        if geometry_dir.exists():
            for geom_file in geometry_dir.glob("*.star"):
                cycle_name = geom_file.stem
                geom_df = starfile.read(geom_file)

                # Group by tomogram
                self.geometry_data[cycle_name] = {}
                for tomo_name, group in geom_df.groupby("tomogram_name"):
                    # Convert to numpy array (remove tomogram_name column)
                    data_cols = [col for col in group.columns if col != "tomogram_name"]
                    self.geometry_data[cycle_name][tomo_name] = group[data_cols].values

        # Load tilt geometry
        tilt_dir = self.metadata_source / "tilt_geometry"
        if tilt_dir.exists():
            for tilt_file in tilt_dir.glob("*.star"):
                if tilt_file.name == "tilt_series_list.star":
                    continue

                tomo_name = tilt_file.stem
                tilt_df = starfile.read(tilt_file)

                # Remove metadata columns
                data_cols = [
                    col
                    for col in tilt_df.columns
                    if col not in ["tilt_series_name", "tilt_index"]
                ]
                self.tilt_geometry[tomo_name] = tilt_df[data_cols].values

        # Determine current cycle
        cycle_keys = [k for k in self.geometry_data.keys() if "cycle" in k.lower()]
        if cycle_keys:
            # Use the highest numbered cycle as current
            cycle_numbers = []
            for key in cycle_keys:
                try:
                    if "cycle" in key:
                        num_part = key.split("cycle")[1].split("_")[0]
                        cycle_numbers.append((int(num_part), key))
                except BaseException:
                    continue
            if cycle_numbers:
                self.current_cycle = max(cycle_numbers)[1]

    def _load_matlab_metadata(self):
        """Load metadata from MATLAB .mat file."""
        logger.info(f"Loading MATLAB metadata from {self.metadata_source}")

        mat_data = scipy.io.loadmat(
            str(self.metadata_source), struct_as_record=False, squeeze_me=True
        )

        if "subTomoMeta" not in mat_data:
            raise ValueError("MATLAB file does not contain 'subTomoMeta' structure")

        subtomo_meta = mat_data["subTomoMeta"]

        # Extract cycle data
        for attr_name in dir(subtomo_meta):
            if attr_name.startswith("cycle"):
                cycle_obj = getattr(subtomo_meta, attr_name)
                cycle_name = attr_name

                # Load RawAlign geometry if available
                if hasattr(cycle_obj, "RawAlign"):
                    raw_align = cycle_obj.RawAlign
                    self.geometry_data[f"{cycle_name}_geometry"] = {}

                    for tomo_attr in dir(raw_align):
                        if not tomo_attr.startswith("_"):
                            tomo_data = getattr(raw_align, tomo_attr)
                            if isinstance(tomo_data, np.ndarray):
                                self.geometry_data[f"{cycle_name}_geometry"][
                                    tomo_attr
                                ] = tomo_data

        # Load tilt geometry
        if hasattr(subtomo_meta, "tiltGeometry"):
            tilt_geom = subtomo_meta.tiltGeometry
            for tomo_attr in dir(tilt_geom):
                if not tomo_attr.startswith("_"):
                    tomo_data = getattr(tilt_geom, tomo_attr)
                    if isinstance(tomo_data, np.ndarray):
                        self.tilt_geometry[tomo_attr] = tomo_data

        # Determine current cycle
        if hasattr(subtomo_meta, "currentCycle"):
            cycle_num = subtomo_meta.currentCycle
            self.current_cycle = f"cycle{cycle_num:03d}_geometry"

    def list_available_cycles(self) -> List[str]:
        """List all available analysis cycles."""
        return list(self.geometry_data.keys())

    def list_available_tomograms(self, cycle: Optional[str] = None) -> List[str]:
        """List all available tomograms for a given cycle."""
        if cycle is None:
            cycle = self.current_cycle

        if cycle not in self.geometry_data:
            return []

        return list(self.geometry_data[cycle].keys())

    def get_geometry_data(
        self, cycle: Optional[str] = None, tomogram: Optional[str] = None
    ) -> np.ndarray:
        """
        Get geometry data for specified cycle and tomogram.

        Args:
            cycle: Cycle name (uses current if None)
            tomogram: Tomogram name (returns all if None)

        Returns:
            Geometry data array or dict of arrays
        """
        if cycle is None:
            cycle = self.current_cycle

        if cycle not in self.geometry_data:
            raise ValueError(
                f"Cycle '{cycle}' not found. Available: {list(self.geometry_data.keys())}"
            )

        if tomogram is None:
            return self.geometry_data[cycle]

        if tomogram not in self.geometry_data[cycle]:
            raise ValueError(f"Tomogram '{tomogram}' not found in cycle '{cycle}'")

        return self.geometry_data[cycle][tomogram]

    def get_tilt_data(self, tomogram: str) -> Optional[np.ndarray]:
        """Get tilt series data for specified tomogram."""
        return self.tilt_geometry.get(tomogram, None)

    def create_tomogram_summary_plot(
        self,
        cycle: Optional[str] = None,
        tomogram: Optional[str] = None,
        save_path: Optional[Union[str, Path]] = None,
        show_plot: bool = True,
    ) -> plt.Figure:
        """
        Create comprehensive 4-panel summary plot for a tomogram.

        This recreates and enhances the visualization from the demo script,
        showing:
        1. Correlation coefficient distribution
        2. 3D particle position scatter
        3. Class distribution
        4. Tilt series analysis (if available)

        Args:
            cycle: Cycle to analyze (uses current if None)
            tomogram: Tomogram to analyze (uses first available if None)
            save_path: Path to save plot (optional)
            show_plot: Whether to display the plot

        Returns:
            matplotlib Figure object
        """
        if cycle is None:
            cycle = self.current_cycle

        available_tomos = self.list_available_tomograms(cycle)
        if not available_tomos:
            raise ValueError(f"No tomograms found for cycle '{cycle}'")

        if tomogram is None:
            tomogram = available_tomos[0]

        # Get geometry data
        geom_data = self.get_geometry_data(cycle, tomogram)
        tilt_data = self.get_tilt_data(tomogram)

        # Filter included particles (class != -9999)
        included_mask = geom_data[:, self.COLS["class"]] != -9999
        included_data = geom_data[included_mask]

        # Create figure with 2x2 subplot layout
        fig = plt.figure(figsize=(16, 12))
        gs = gridspec.GridSpec(2, 2, hspace=0.3, wspace=0.3)

        # Panel 1: Correlation Coefficient Distribution
        ax1 = fig.add_subplot(gs[0, 0])
        if len(included_data) > 0:
            ccc_values = included_data[:, self.COLS["ccc"]]
            ax1.hist(
                ccc_values,
                bins=max(10, len(ccc_values) // 20),
                alpha=0.7,
                color="skyblue",
                edgecolor="black",
            )
            ax1.axvline(
                np.mean(ccc_values),
                color="red",
                linestyle="--",
                label=f"Mean: {np.mean(ccc_values):.3f}",
            )
            ax1.axvline(
                np.median(ccc_values),
                color="orange",
                linestyle="--",
                label=f"Median: {np.median(ccc_values):.3f}",
            )
            ax1.set_xlabel("Cross-Correlation Coefficient")
            ax1.set_ylabel("Number of Particles")
            ax1.set_title(
                f"CCC Distribution\n{tomogram}\n{len(included_data)}/{len(geom_data)} particles"
            )
            ax1.legend()
            ax1.grid(True, alpha=0.3)
        else:
            ax1.text(
                0.5,
                0.5,
                "No included particles",
                ha="center",
                va="center",
                transform=ax1.transAxes,
            )
            ax1.set_title(f"CCC Distribution - {tomogram}\n0 particles")

        # Panel 2: 3D Particle Positions
        ax2 = fig.add_subplot(gs[0, 1], projection="3d")
        if len(included_data) > 0:
            x_coords = included_data[:, self.COLS["x_coord"]]
            y_coords = included_data[:, self.COLS["y_coord"]]
            z_coords = included_data[:, self.COLS["z_coord"]]
            ccc_values = included_data[:, self.COLS["ccc"]]

            # Color by correlation coefficient
            scatter = ax2.scatter(
                x_coords,
                y_coords,
                z_coords,
                c=ccc_values,
                cmap="viridis",
                alpha=0.6,
                s=20,
            )
            ax2.set_xlabel("X Coordinate")
            ax2.set_ylabel("Y Coordinate")
            ax2.set_zlabel("Z Coordinate")
            ax2.set_title("3D Particle Distribution\n(colored by CCC)")

            # Add colorbar
            cbar = plt.colorbar(scatter, ax=ax2, shrink=0.8)
            cbar.set_label("CCC")
        else:
            ax2.text(0.5, 0.5, 0.5, "No particles", ha="center", va="center")
            ax2.set_title("3D Particle Distribution")

        # Panel 3: Class Distribution and Half-Set Analysis
        ax3 = fig.add_subplot(gs[1, 0])
        if len(included_data) > 0:
            classes = included_data[:, self.COLS["class"]]
            half_sets = included_data[:, self.COLS["half_set"]]

            # Create stacked bar chart for class distribution by half-set
            unique_classes = np.unique(classes)
            odd_counts = []
            eve_counts = []

            for cls in unique_classes:
                cls_mask = classes == cls
                cls_data = included_data[cls_mask]
                odd_count = np.sum(cls_data[:, self.COLS["half_set"]] == 1)
                eve_count = np.sum(cls_data[:, self.COLS["half_set"]] == 2)
                odd_counts.append(odd_count)
                eve_counts.append(eve_count)

            x_pos = np.arange(len(unique_classes))
            width = 0.8

            ax3.bar(
                x_pos, odd_counts, width, label="ODD", alpha=0.7, color="lightcoral"
            )
            ax3.bar(
                x_pos,
                eve_counts,
                width,
                bottom=odd_counts,
                label="EVE",
                alpha=0.7,
                color="lightblue",
            )

            ax3.set_xlabel("Class Number")
            ax3.set_ylabel("Number of Particles")
            ax3.set_title("Class Distribution by Half-Set")
            ax3.set_xticks(x_pos)
            ax3.set_xticklabels([f"{int(c)}" for c in unique_classes])
            ax3.legend()
            ax3.grid(True, alpha=0.3)

            # Add total counts as text
            total_odd = np.sum(half_sets == 1)
            total_eve = np.sum(half_sets == 2)
            ax3.text(
                0.02,
                0.98,
                f"Total ODD: {total_odd}\nTotal EVE: {total_eve}",
                transform=ax3.transAxes,
                va="top",
                ha="left",
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
            )
        else:
            ax3.text(
                0.5,
                0.5,
                "No class data",
                ha="center",
                va="center",
                transform=ax3.transAxes,
            )
            ax3.set_title("Class Distribution")

        # Panel 4: Tilt Series Analysis (if available)
        ax4 = fig.add_subplot(gs[1, 1])
        if tilt_data is not None and len(tilt_data) > 0:
            # Assuming tilt data columns: [tilt_angle, dose, ...]
            tilt_angles = tilt_data[:, 0]  # First column typically tilt angle

            if tilt_data.shape[1] > 1:
                doses = tilt_data[:, 1]  # Second column typically dose
                ax4_twin = ax4.twinx()

                # Plot tilt scheme
                line1 = ax4.plot(
                    range(len(tilt_angles)),
                    tilt_angles,
                    "bo-",
                    label="Tilt Angle",
                    markersize=4,
                )
                line2 = ax4_twin.plot(
                    range(len(doses)),
                    doses,
                    "ro-",
                    label="Cumulative Dose",
                    markersize=4,
                )

                ax4.set_xlabel("Tilt Index")
                ax4.set_ylabel("Tilt Angle (degrees)", color="blue")
                ax4_twin.set_ylabel("Cumulative Dose (e⁻/Å²)", color="red")
                ax4.tick_params(axis="y", labelcolor="blue")
                ax4_twin.tick_params(axis="y", labelcolor="red")

                # Combine legends
                lines = line1 + line2
                labels = [l.get_label() for l in lines]
                ax4.legend(lines, labels, loc="upper left")

                ax4.set_title(f"Tilt Series Analysis\n{len(tilt_angles)} tilts")
                ax4.grid(True, alpha=0.3)

                # Add statistics
                tilt_range = f"{np.min(tilt_angles):.1f}° to {np.max(tilt_angles):.1f}°"
                tilt_step = np.mean(np.diff(np.sort(tilt_angles)))
                ax4.text(
                    0.02,
                    0.98,
                    f"Range: {tilt_range}\nStep: {tilt_step:.1f}°",
                    transform=ax4.transAxes,
                    va="top",
                    ha="left",
                    bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
                )
            else:
                ax4.plot(range(len(tilt_angles)), tilt_angles, "bo-", markersize=4)
                ax4.set_xlabel("Tilt Index")
                ax4.set_ylabel("Tilt Angle (degrees)")
                ax4.set_title(f"Tilt Angles\n{len(tilt_angles)} tilts")
                ax4.grid(True, alpha=0.3)
        else:
            ax4.text(
                0.5,
                0.5,
                "No tilt data available",
                ha="center",
                va="center",
                transform=ax4.transAxes,
            )
            ax4.set_title("Tilt Series Analysis")

        # Add overall title
        fig.suptitle(
            f"emClarity Tomogram Analysis\nCycle: {cycle} | Tomogram: {tomogram}",
            fontsize=16,
            fontweight="bold",
        )

        # Save if requested
        if save_path:
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(save_path, dpi=300, bbox_inches="tight")
            logger.info(f"Plot saved to {save_path}")

        # Show if requested
        if show_plot:
            plt.show()

        return fig

    def create_cycle_overview_plots(
        self,
        cycle: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        max_tomograms: int = 20,
    ) -> None:
        """
        Create overview plots for all tomograms in a cycle.

        Args:
            cycle: Cycle to analyze (uses current if None)
            output_dir: Directory to save plots (creates if needed)
            max_tomograms: Maximum number of tomograms to plot
        """
        if cycle is None:
            cycle = self.current_cycle

        if output_dir is None:
            output_dir = Path(f"geometry_analysis_{cycle}")
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        available_tomos = self.list_available_tomograms(cycle)
        if not available_tomos:
            logger.warning(f"No tomograms found for cycle '{cycle}'")
            return

        # Limit number of tomograms if requested
        tomos_to_plot = available_tomos[:max_tomograms]

        logger.info(
            f"Creating plots for {len(tomos_to_plot)} tomograms in cycle '{cycle}'"
        )

        # Create individual tomogram plots
        for i, tomo in enumerate(tomos_to_plot):
            logger.info(f"Processing {i+1}/{len(tomos_to_plot)}: {tomo}")

            try:
                fig = self.create_tomogram_summary_plot(
                    cycle=cycle, tomogram=tomo, show_plot=False
                )

                # Save plot
                plot_path = output_dir / f"{tomo}_summary.png"
                fig.savefig(plot_path, dpi=300, bbox_inches="tight")
                plt.close(fig)

            except Exception as e:
                logger.error(f"Failed to create plot for {tomo}: {e}")

        # Create summary statistics file
        self._create_cycle_statistics(cycle, output_dir)

        logger.info(f"Analysis complete. Output saved to {output_dir}")

    def _create_cycle_statistics(self, cycle: str, output_dir: Path) -> None:
        """Create statistical summary for the entire cycle."""
        stats_data = []

        for tomo_name in self.list_available_tomograms(cycle):
            try:
                geom_data = self.get_geometry_data(cycle, tomo_name)
                included_mask = geom_data[:, self.COLS["class"]] != -9999
                included_data = geom_data[included_mask]

                if len(included_data) > 0:
                    ccc_values = included_data[:, self.COLS["ccc"]]
                    classes = included_data[:, self.COLS["class"]]
                    half_sets = included_data[:, self.COLS["half_set"]]

                    stats_entry = {
                        "tomogram": tomo_name,
                        "total_particles": len(geom_data),
                        "included_particles": len(included_data),
                        "inclusion_rate": (
                            len(included_data) / len(geom_data)
                            if len(geom_data) > 0
                            else 0
                        ),
                        "mean_ccc": np.mean(ccc_values),
                        "median_ccc": np.median(ccc_values),
                        "std_ccc": np.std(ccc_values),
                        "min_ccc": np.min(ccc_values),
                        "max_ccc": np.max(ccc_values),
                        "n_classes": len(np.unique(classes)),
                        "n_odd": np.sum(half_sets == 1),
                        "n_eve": np.sum(half_sets == 2),
                    }
                    stats_data.append(stats_entry)

            except Exception as e:
                logger.warning(f"Failed to compute statistics for {tomo_name}: {e}")

        if stats_data:
            stats_df = pd.DataFrame(stats_data)
            stats_path = output_dir / f"{cycle}_statistics.csv"
            stats_df.to_csv(stats_path, index=False)

            # Create summary report
            report_path = output_dir / f"{cycle}_summary_report.txt"
            with open(report_path, "w") as f:
                f.write(f"emClarity Geometry Analysis Summary\n")
                f.write(f"Cycle: {cycle}\n")
                f.write(f"Analysis Date: {pd.Timestamp.now()}\n")
                f.write(f"=" * 50 + "\n\n")

                f.write(f"Dataset Overview:\n")
                f.write(f"  Number of tomograms: {len(stats_df)}\n")
                f.write(f"  Total particles: {stats_df['total_particles'].sum()}\n")
                f.write(
                    f"  Included particles: {stats_df['included_particles'].sum()}\n"
                )
                f.write(
                    f"  Overall inclusion rate: {stats_df['included_particles'].sum() / stats_df['total_particles'].sum():.3f}\n\n"
                )

                f.write(f"CCC Statistics:\n")
                f.write(
                    f"  Mean CCC: {stats_df['mean_ccc'].mean():.4f} ± {stats_df['mean_ccc'].std():.4f}\n"
                )
                f.write(
                    f"  CCC range: {stats_df['min_ccc'].min():.4f} to {stats_df['max_ccc'].max():.4f}\n\n"
                )

                f.write(f"Half-set Distribution:\n")
                f.write(f"  Total ODD particles: {stats_df['n_odd'].sum()}\n")
                f.write(f"  Total EVE particles: {stats_df['n_eve'].sum()}\n")
                f.write(
                    f"  ODD/EVE ratio: {stats_df['n_odd'].sum() / max(stats_df['n_eve'].sum(), 1):.3f}\n\n"
                )

                f.write(f"Per-tomogram Statistics:\n")
                f.write(
                    f"  Particles per tomogram: {stats_df['included_particles'].mean():.1f} ± {stats_df['included_particles'].std():.1f}\n"
                )
                f.write(
                    f"  Classes per tomogram: {stats_df['n_classes'].mean():.1f} ± {stats_df['n_classes'].std():.1f}\n"
                )


def main():
    """Command-line interface for geometry analysis."""
    import argparse

    parser = argparse.ArgumentParser(
        description="emClarity Geometry Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze single tomogram from star files
  python emc_geometry_analysis.py project_star/ --tomogram tomo_001 --cycle cycle000_geometry

  # Create overview for all tomograms in cycle
  python emc_geometry_analysis.py project_star/ --cycle cycle000_geometry --overview

  # Analyze from MATLAB file
  python emc_geometry_analysis.py subTomoMeta.mat --tomogram tomo_001

  # List available data
  python emc_geometry_analysis.py project_star/ --list
        """,
    )

    parser.add_argument(
        "metadata_source", help="Path to metadata (star directory or .mat file)"
    )
    parser.add_argument("--cycle", help="Cycle to analyze (default: current cycle)")
    parser.add_argument("--tomogram", help="Specific tomogram to analyze")
    parser.add_argument(
        "--overview", action="store_true", help="Create overview plots for entire cycle"
    )
    parser.add_argument(
        "--list", action="store_true", help="List available cycles and tomograms"
    )
    parser.add_argument("--output", help="Output directory for plots")
    parser.add_argument(
        "--max-tomos",
        type=int,
        default=20,
        help="Maximum tomograms for overview (default: 20)",
    )
    parser.add_argument(
        "--no-display", action="store_true", help="Do not display plots"
    )

    args = parser.parse_args()

    try:
        # Initialize analyzer
        analyzer = EmClarityGeometryAnalyzer(args.metadata_source)

        if args.list:
            # List available data
            print("Available cycles:")
            for cycle in analyzer.list_available_cycles():
                tomos = analyzer.list_available_tomograms(cycle)
                print(f"  {cycle}: {len(tomos)} tomograms")

            if analyzer.current_cycle:
                print(f"\nCurrent cycle: {analyzer.current_cycle}")
                print("Available tomograms:")
                for tomo in analyzer.list_available_tomograms()[:10]:  # Show first 10
                    print(f"  {tomo}")
                if len(analyzer.list_available_tomograms()) > 10:
                    print(
                        f"  ... and {len(analyzer.list_available_tomograms()) - 10} more"
                    )

        elif args.overview:
            # Create cycle overview
            analyzer.create_cycle_overview_plots(
                cycle=args.cycle, output_dir=args.output, max_tomograms=args.max_tomos
            )

        else:
            # Create single tomogram plot
            fig = analyzer.create_tomogram_summary_plot(
                cycle=args.cycle,
                tomogram=args.tomogram,
                save_path=args.output,
                show_plot=not args.no_display,
            )

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
