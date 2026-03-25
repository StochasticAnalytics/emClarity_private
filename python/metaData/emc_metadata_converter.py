#!/usr/bin/env python3
"""
MATLAB to Star File Metadata Converter for emClarity.

This module provides functionality to convert emClarity MATLAB .mat files containing
subTomoMeta structures to a hierarchical directory structure using star files.

Key Features:
- Converts MATLAB nested structures to star files
- Maintains data integrity and relationships
- Creates hierarchical directory structure
- Uses pandas DataFrames for data manipulation
- Supports bidirectional conversion (MATLAB -> Star -> MATLAB)

Usage:
    converter = EmClarityMetadataConverter()
    converter.convert_mat_to_star("project.mat", "project_star/")

Author: emClarity Development Team
Date: September 3, 2025
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy.io
import starfile

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmClarityMetadataConverter:
    """
    Converts emClarity MATLAB .mat metadata files to star file directory structure.

    This class handles the conversion of complex nested MATLAB structures
    (subTomoMeta) into a hierarchical directory structure using star files,
    which are standard in the cryo-EM field and work well with pandas.
    """

    def __init__(self, validate_conversion: bool = True):
        """
        Initialize the converter.

        Args:
            validate_conversion: Whether to validate conversion accuracy
        """
        self.validate_conversion = validate_conversion
        self.geometry_columns = self._define_geometry_columns()
        self.tilt_geometry_columns = self._define_tilt_geometry_columns()

    def _define_geometry_columns(self) -> list[str]:
        """Define standard column names for geometry data (26 columns)."""
        return [
            "correlation_coefficient",  # Column 1
            "reserved_2",
            "reserved_3",  # Columns 2-3
            "subtomo_index",  # Column 4 - unique particle ID
            "reserved_5",
            "reserved_6",  # Columns 5-6
            "half_set",  # Column 7 - odd/even half set (1/2)
            "reserved_8",
            "reserved_9",  # Columns 8-9
            "reserved_10",  # Column 10
            "pos_x",
            "pos_y",
            "pos_z",  # Columns 11-13 - position in tomogram
            "euler_psi",
            "euler_theta",
            "euler_phi",  # Columns 14-16 - Euler angles
            "rot_matrix_r1c1",
            "rot_matrix_r1c2",
            "rot_matrix_r1c3",  # Columns 17-19
            "rot_matrix_r2c1",
            "rot_matrix_r2c2",
            "rot_matrix_r2c3",  # Columns 20-22
            "rot_matrix_r3c1",
            "rot_matrix_r3c2",
            "rot_matrix_r3c3",  # Columns 23-25
            "class_label",  # Column 26 - class assignment (-9999 = ignored)
        ]

    def _define_tilt_geometry_columns(self) -> list[str]:
        """Define standard column names for tilt geometry data (23 columns)."""
        return [
            "tilt_angle",  # Column 1
            "reserved_2",
            "reserved_3",  # Columns 2-3
            "exposure_dose",  # Column 4
            "reserved_5",
            "reserved_6",
            "reserved_7",
            "reserved_8",  # Columns 5-8
            "reserved_9",
            "reserved_10",
            "reserved_11",
            "reserved_12",  # Columns 9-12
            "reserved_13",
            "reserved_14",
            "reserved_15",
            "reserved_16",  # Columns 13-16
            "reserved_17",
            "reserved_18",
            "reserved_19",
            "reserved_20",  # Columns 17-20
            "reserved_21",
            "reserved_22",
            "reserved_23",  # Columns 21-23
        ]

    def convert_mat_to_star(
        self, mat_file_path: str | Path, output_dir: str | Path
    ) -> None:
        """
        Convert a MATLAB .mat file to star file directory structure.

        Args:
            mat_file_path: Path to input .mat file
            output_dir: Path to output directory
        """
        mat_file_path = Path(mat_file_path)
        output_dir = Path(output_dir)

        logger.info(f"Converting {mat_file_path} to {output_dir}")

        # Load MATLAB file
        logger.info("Loading MATLAB file...")
        mat_data = self._load_mat_file(mat_file_path)

        if "subTomoMeta" not in mat_data:
            raise ValueError("No 'subTomoMeta' found in the MATLAB file")

        subtomo_meta = mat_data["subTomoMeta"]

        # Create output directory structure
        output_dir.mkdir(parents=True, exist_ok=True)

        # Convert main components
        logger.info("Converting metadata components...")
        self._convert_top_level_metadata(subtomo_meta, output_dir)
        self._convert_geometry_data(subtomo_meta, output_dir)
        self._convert_tilt_geometry(subtomo_meta, output_dir)
        self._convert_mapback_geometry(subtomo_meta, output_dir)
        self._convert_cycle_data(subtomo_meta, output_dir)

        logger.info(f"Conversion complete. Output saved to {output_dir}")

    def _load_mat_file(self, mat_file_path: Path) -> dict[str, Any]:
        """Load MATLAB file with proper settings."""
        try:
            return scipy.io.loadmat(
                str(mat_file_path), struct_as_record=False, squeeze_me=True
            )
        except Exception as e:
            raise ValueError(f"Failed to load MATLAB file {mat_file_path}: {e}") from e

    def _convert_top_level_metadata(self, subtomo_meta: Any, output_dir: Path) -> None:
        """Convert top-level metadata to metadata.star file."""
        metadata = {}

        # Extract scalar values
        scalar_fields = [
            "currentCycle",
            "currentTomoCPR",
            "currentResForDefocusError",
            "maxGoldStandard",
            "nSubTomoInitial",
            "CUTPADDING",
        ]

        for field in scalar_fields:
            if hasattr(subtomo_meta, field):
                value = getattr(subtomo_meta, field)
                # Convert numpy types to Python native types
                if isinstance(value, np.ndarray):
                    value = value.item() if value.size == 1 else value.tolist()
                elif isinstance(value, (np.integer, np.floating)):
                    value = value.item()
                metadata[field] = value

        # Create DataFrame and save as star file
        metadata_df = pd.DataFrame([metadata])
        output_file = output_dir / "metadata.star"
        starfile.write(metadata_df, output_file)
        logger.info(f"Saved top-level metadata to {output_file}")

    def _convert_geometry_data(self, subtomo_meta: Any, output_dir: Path) -> None:
        """Convert geometry data from cycles."""
        geometry_dir = output_dir / "geometry"
        geometry_dir.mkdir(exist_ok=True)

        # Find all cycles
        cycle_fields = [attr for attr in dir(subtomo_meta) if attr.startswith("cycle")]

        for cycle_field in cycle_fields:
            cycle_data = getattr(subtomo_meta, cycle_field)

            # Check for geometry data
            if hasattr(cycle_data, "geometry"):
                self._convert_cycle_geometry(
                    cycle_data.geometry, cycle_field, geometry_dir
                )
            elif hasattr(cycle_data, "Avg_geometry"):
                self._convert_cycle_geometry(
                    cycle_data.Avg_geometry, f"{cycle_field}_avg", geometry_dir
                )

    def _convert_cycle_geometry(
        self, geometry_data: Any, cycle_name: str, geometry_dir: Path
    ) -> None:
        """Convert geometry data for a specific cycle."""
        output_file = geometry_dir / f"{cycle_name}_geometry.star"

        # Get all tomogram names
        if hasattr(geometry_data, "_fieldnames"):
            tomo_names = geometry_data._fieldnames
        else:
            # Fallback: get attribute names that don't start with '_'
            tomo_names = [
                attr
                for attr in dir(geometry_data)
                if not attr.startswith("_") and hasattr(geometry_data, attr)
            ]

        all_geometry_data = []

        for tomo_name in tomo_names:
            try:
                tomo_geometry = getattr(geometry_data, tomo_name)
                if isinstance(tomo_geometry, np.ndarray) and tomo_geometry.size > 0:
                    # Convert to DataFrame
                    df = self._array_to_geometry_dataframe(tomo_geometry, tomo_name)
                    all_geometry_data.append(df)
            except AttributeError:
                logger.warning(f"Could not access geometry for {tomo_name}")
                continue

        if all_geometry_data:
            # Combine all tomograms
            combined_df = pd.concat(all_geometry_data, ignore_index=True)
            starfile.write(combined_df, output_file)
            logger.info(
                f"Saved {len(combined_df)} particles from {len(all_geometry_data)} tomograms to {output_file}"
            )

    def _array_to_geometry_dataframe(
        self, array: np.ndarray, tomo_name: str
    ) -> pd.DataFrame:
        """Convert geometry array to pandas DataFrame."""
        if len(array.shape) != 2:
            raise ValueError(f"Expected 2D array, got shape {array.shape}")

        _n_particles, n_cols = array.shape

        # Use standard column names if we have the expected number
        if n_cols == len(self.geometry_columns):
            columns = self.geometry_columns
        else:
            # Generate generic column names
            columns = [f"col_{i + 1}" for i in range(n_cols)]
            logger.warning(
                f"Unexpected number of columns ({n_cols}) for geometry data, using generic names"
            )

        df = pd.DataFrame(array, columns=columns)
        df.insert(0, "tomogram_name", tomo_name)  # Add tomogram identifier

        return df

    def _convert_tilt_geometry(self, subtomo_meta: Any, output_dir: Path) -> None:
        """Convert tilt geometry data."""
        if not hasattr(subtomo_meta, "tiltGeometry"):
            logger.warning("No tiltGeometry found in metadata")
            return

        tilt_dir = output_dir / "tilt_geometry"
        tilt_dir.mkdir(exist_ok=True)

        tilt_geometry = subtomo_meta.tiltGeometry

        # Get all tilt series names
        if hasattr(tilt_geometry, "_fieldnames"):
            tilt_names = tilt_geometry._fieldnames
        else:
            tilt_names = [
                attr for attr in dir(tilt_geometry) if not attr.startswith("_")
            ]

        tilt_series_list = []

        for tilt_name in tilt_names:
            try:
                tilt_data = getattr(tilt_geometry, tilt_name)
                if isinstance(tilt_data, np.ndarray) and tilt_data.size > 0:
                    # Convert to DataFrame
                    df = self._array_to_tilt_dataframe(tilt_data, tilt_name)

                    # Save individual tilt series file
                    output_file = tilt_dir / f"{tilt_name}.star"
                    starfile.write(df, output_file)

                    # Add to series list
                    tilt_series_list.append(
                        {
                            "tilt_series_name": tilt_name,
                            "n_tilts": len(df),
                            "star_file": f"{tilt_name}.star",
                        }
                    )

            except AttributeError:
                logger.warning(f"Could not access tilt geometry for {tilt_name}")
                continue

        # Save tilt series list
        if tilt_series_list:
            series_df = pd.DataFrame(tilt_series_list)
            list_file = tilt_dir / "tilt_series_list.star"
            starfile.write(series_df, list_file)
            logger.info(f"Saved {len(tilt_series_list)} tilt series to {tilt_dir}")

    def _array_to_tilt_dataframe(
        self, array: np.ndarray, tilt_name: str
    ) -> pd.DataFrame:
        """Convert tilt geometry array to pandas DataFrame."""
        if len(array.shape) != 2:
            raise ValueError(f"Expected 2D array, got shape {array.shape}")

        _n_tilts, n_cols = array.shape

        # Use standard column names if we have the expected number
        if n_cols == len(self.tilt_geometry_columns):
            columns = self.tilt_geometry_columns
        else:
            # Generate generic column names
            columns = [f"col_{i + 1}" for i in range(n_cols)]
            logger.warning(
                f"Unexpected number of columns ({n_cols}) for tilt geometry, using generic names"
            )

        df = pd.DataFrame(array, columns=columns)
        df.insert(0, "tilt_series_name", tilt_name)
        df.insert(1, "tilt_index", range(1, len(df) + 1))  # 1-based indexing

        return df

    def _convert_mapback_geometry(self, subtomo_meta: Any, output_dir: Path) -> None:
        """Convert mapback geometry data."""
        if not hasattr(subtomo_meta, "mapBackGeometry"):
            logger.warning("No mapBackGeometry found in metadata")
            return

        mapback_dir = output_dir / "mapback_geometry"
        mapback_dir.mkdir(exist_ok=True)

        mapback_geom = subtomo_meta.mapBackGeometry

        # Convert tomoCoords if present
        if hasattr(mapback_geom, "tomoCoords"):
            self._convert_tomo_coordinates(mapback_geom.tomoCoords, mapback_dir)

        # Convert tomoName mappings if present
        if hasattr(mapback_geom, "tomoName"):
            self._convert_tomo_names(mapback_geom.tomoName, mapback_dir)

        # Convert per-tilt data
        self._convert_per_tilt_mapback(mapback_geom, mapback_dir)

    def _convert_tomo_coordinates(self, tomo_coords: Any, mapback_dir: Path) -> None:
        """Convert tomogram coordinate mappings."""
        if hasattr(tomo_coords, "_fieldnames"):
            tomo_names = tomo_coords._fieldnames
        else:
            tomo_names = [attr for attr in dir(tomo_coords) if not attr.startswith("_")]

        coord_data = []

        for tomo_name in tomo_names:
            try:
                coords = getattr(tomo_coords, tomo_name)
                coord_dict = {"tomogram_name": tomo_name}

                # Extract coordinate fields
                coord_fields = [
                    "is_active",
                    "y_i",
                    "y_f",
                    "NX",
                    "NY",
                    "NZ",
                    "dX_specimen_to_tomo",
                    "dY_specimen_to_tomo",
                    "dZ_specimen_to_tomo",
                    "tilt_NX",
                    "tilt_NY",
                ]

                for field in coord_fields:
                    if hasattr(coords, field):
                        value = getattr(coords, field)
                        if isinstance(value, (np.ndarray, np.number)):
                            value = value.item() if hasattr(value, "item") else value
                        coord_dict[field] = value

                coord_data.append(coord_dict)

            except AttributeError:
                logger.warning(f"Could not access coordinates for {tomo_name}")
                continue

        if coord_data:
            df = pd.DataFrame(coord_data)
            output_file = mapback_dir / "tomo_coordinates.star"
            starfile.write(df, output_file)
            logger.info(
                f"Saved coordinates for {len(coord_data)} tomograms to {output_file}"
            )

    def _convert_tomo_names(self, tomo_names: Any, mapback_dir: Path) -> None:
        """Convert tomogram name mappings."""
        if hasattr(tomo_names, "_fieldnames"):
            names = tomo_names._fieldnames
        else:
            names = [attr for attr in dir(tomo_names) if not attr.startswith("_")]

        name_data = []

        for name in names:
            try:
                name_info = getattr(tomo_names, name)
                name_dict = {"tomogram_name": name}

                # Extract name mapping fields
                name_fields = ["tiltName", "tomoIdx"]

                for field in name_fields:
                    if hasattr(name_info, field):
                        value = getattr(name_info, field)
                        if isinstance(value, (np.ndarray, np.number)):
                            value = value.item() if hasattr(value, "item") else value
                        name_dict[field] = value

                name_data.append(name_dict)

            except AttributeError:
                logger.warning(f"Could not access name mapping for {name}")
                continue

        if name_data:
            df = pd.DataFrame(name_data)
            output_file = mapback_dir / "tomo_names.star"
            starfile.write(df, output_file)
            logger.info(
                f"Saved name mappings for {len(name_data)} tomograms to {output_file}"
            )

    def _convert_per_tilt_mapback(self, mapback_geom: Any, mapback_dir: Path) -> None:
        """Convert per-tilt mapback data."""
        # Get all attributes that look like tilt series
        tilt_attrs = [
            attr
            for attr in dir(mapback_geom)
            if not attr.startswith("_")
            and attr not in ["tomoCoords", "tomoName"]
            and hasattr(mapback_geom, attr)
        ]

        for tilt_attr in tilt_attrs:
            try:
                tilt_data = getattr(mapback_geom, tilt_attr)
                if hasattr(tilt_data, "tomoList"):
                    # Create subdirectory for this tilt
                    tilt_dir = mapback_dir / tilt_attr
                    tilt_dir.mkdir(exist_ok=True)

                    # Convert tomo list
                    tomo_list = tilt_data.tomoList
                    if isinstance(tomo_list, str):
                        tomo_list = [tomo_list]
                    elif hasattr(tomo_list, "__iter__"):
                        tomo_list = list(tomo_list)

                    # Create DataFrame
                    list_data = []
                    for i, tomo in enumerate(tomo_list):
                        list_data.append(
                            {
                                "tilt_name": tilt_attr,
                                "tomo_index": i + 1,
                                "tomogram_name": tomo,
                            }
                        )

                    # Add other fields if present
                    other_fields = ["nTomos", "tomoCprRePrjSize"]
                    extra_data = {}
                    for field in other_fields:
                        if hasattr(tilt_data, field):
                            value = getattr(tilt_data, field)
                            if isinstance(value, (np.ndarray, np.number)):
                                value = (
                                    value.item() if hasattr(value, "item") else value
                                )
                            extra_data[field] = value

                    # Add extra fields to all rows
                    for row in list_data:
                        row.update(extra_data)

                    df = pd.DataFrame(list_data)
                    output_file = tilt_dir / "tomo_list.star"
                    starfile.write(df, output_file)

            except AttributeError:
                continue

    def _convert_cycle_data(self, subtomo_meta: Any, output_dir: Path) -> None:
        """Convert additional cycle-specific data (RawAlign, etc.)."""
        cycles_dir = output_dir / "cycles"
        cycles_dir.mkdir(exist_ok=True)

        # Find all cycles
        cycle_fields = [attr for attr in dir(subtomo_meta) if attr.startswith("cycle")]

        for cycle_field in cycle_fields:
            cycle_data = getattr(subtomo_meta, cycle_field)
            cycle_dir = cycles_dir / cycle_field
            cycle_dir.mkdir(exist_ok=True)

            # Convert RawAlign data if present
            if hasattr(cycle_data, "RawAlign"):
                self._convert_raw_align(cycle_data.RawAlign, cycle_dir)

            # Convert other cycle-specific data
            self._convert_other_cycle_data(cycle_data, cycle_dir)

    def _convert_raw_align(self, raw_align: Any, cycle_dir: Path) -> None:
        """Convert RawAlign data."""
        if hasattr(raw_align, "_fieldnames"):
            tomo_names = raw_align._fieldnames
        else:
            tomo_names = [attr for attr in dir(raw_align) if not attr.startswith("_")]

        all_align_data = []

        for tomo_name in tomo_names:
            try:
                align_data = getattr(raw_align, tomo_name)
                if isinstance(align_data, np.ndarray) and align_data.size > 0:
                    df = self._array_to_geometry_dataframe(align_data, tomo_name)
                    all_align_data.append(df)
            except AttributeError:
                continue

        if all_align_data:
            combined_df = pd.concat(all_align_data, ignore_index=True)
            output_file = cycle_dir / "raw_align.star"
            starfile.write(combined_df, output_file)
            logger.info(
                f"Saved RawAlign data for {len(all_align_data)} tomograms to {output_file}"
            )

    def _convert_other_cycle_data(self, cycle_data: Any, cycle_dir: Path) -> None:
        """Convert other cycle-specific data structures."""
        # Handle reference locations, class vectors, etc.
        cycle_fields = [
            attr
            for attr in dir(cycle_data)
            if not attr.startswith("_")
            and attr not in ["geometry", "Avg_geometry", "RawAlign"]
        ]

        other_data = {}

        for field in cycle_fields:
            try:
                value = getattr(cycle_data, field)

                # Convert various data types
                if isinstance(value, np.ndarray):
                    if value.dtype == "object":
                        # Handle object arrays (like class locations)
                        other_data[field] = str(value.tolist())
                    else:
                        other_data[field] = value.tolist()
                elif hasattr(value, "_fieldnames"):
                    # Handle nested structures
                    nested_dict = {}
                    for subfield in value._fieldnames:
                        subvalue = getattr(value, subfield)
                        if isinstance(subvalue, (np.ndarray, list)):
                            nested_dict[subfield] = str(subvalue)
                        else:
                            nested_dict[subfield] = str(subvalue)
                    other_data[field] = json.dumps(nested_dict)
                else:
                    other_data[field] = str(value)

            except (AttributeError, TypeError):
                continue

        if other_data:
            try:
                df = pd.DataFrame([other_data])
                output_file = cycle_dir / "other_data.star"
                starfile.write(df, output_file)
            except Exception as e:
                logger.warning(f"Could not save other cycle data: {e}")
                # Save as JSON instead
                json_file = cycle_dir / "other_data.json"
                with open(json_file, "w") as f:
                    json.dump(other_data, f, indent=2)


def main():
    """Command-line interface for the converter."""
    if len(sys.argv) != 3:
        print("Usage: python emc_metadata_converter.py <input.mat> <output_directory>")
        print("Example: python emc_metadata_converter.py project.mat project_star/")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]

    converter = EmClarityMetadataConverter()
    converter.convert_mat_to_star(input_file, output_dir)


if __name__ == "__main__":
    main()
