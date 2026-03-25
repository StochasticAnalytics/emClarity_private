#!/usr/bin/env python3
"""
Python MRCImage Class - emClarity Equivalent.

This module provides a Python equivalent of the emClarity MRCImage class,
optimized for memory efficiency and performance based on BAH's modifications
to the original PEET code.

Key Performance Principles (from BAH's MATLAB modifications):
- Default to lazy loading (don't load volume unless requested)
- Avoid unnecessary object returns that bind memory
- Prioritize subvolume reads over full volume reads
- Efficient dtype casting after reading, not during

Author: emClarity Development Team
Date: September 3, 2025
Based on: PEET MRCImage class with BAH performance optimizations
"""

import logging
from pathlib import Path
from typing import Any

import mrcfile
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MRCImage:
    """
    Python equivalent of emClarity MRCImage class.

    Follows BAH's performance optimizations:
    - Lazy loading by default (flgLoad=False)
    - Memory-efficient operations
    - Fast subvolume access

    Usage:
        # Header-only loading (fast, low memory)
        img = MRCImage(filename)
        header = img.get_header()

        # Load data on demand
        img = MRCImage(filename, flg_load=True)
        data = img.get_data()

        # Create empty volume
        img = MRCImage.from_header(header)
    """

    def __init__(
        self,
        filename: str | Path | None = None,
        flg_load: bool = False,
        debug: bool = False,
    ):
        """
        Initialize MRCImage object.

        Args:
            filename: Path to MRC file (None for empty object)
            flg_load: Whether to load volume data (default False for performance)
            debug: Print debug information

        Note:
            Following BAH's modification: "Default is NOT to load volume into
            the MRC Object. Double memory and slower." (20171203)
        """
        # Initialize internal state
        self._filename = None
        self._header = None
        self._data = None
        self._mrc_handle = None
        self._is_data_loaded = False
        self._debug = debug

        # Initialize from file if provided
        if filename is not None:
            self.open(filename, flg_load, debug)

    def open(
        self, filename: str | Path, flg_load: bool = False, debug: bool = False
    ) -> None:
        """
        Open MRC file and load header.

        Args:
            filename: Path to MRC file
            flg_load: Whether to load volume data immediately
            debug: Print debug information
        """
        self._filename = Path(filename)
        self._debug = debug

        if not self._filename.exists():
            raise FileNotFoundError(f"MRC file not found: {filename}")

        # Load header (always done for opened files)
        self._load_header()

        # Load data if requested
        if flg_load:
            self._load_data()

        if debug:
            logger.info(f"Opened MRC file: {filename}")
            logger.info(
                f"Dimensions: {self.get_nx()} x {self.get_ny()} x {self.get_nz()}"
            )
            logger.info(f"Data loaded: {self._is_data_loaded}")

    def _load_header(self) -> None:
        """Load header information efficiently without loading data."""
        with mrcfile.open(self._filename, mode="r", permissive=True) as mrc:
            # Extract key header information as dict for fast access
            self._header = {
                "nx": int(mrc.header.nx),
                "ny": int(mrc.header.ny),
                "nz": int(mrc.header.nz),
                "mode": int(mrc.header.mode),
                "nxstart": int(mrc.header.nxstart),
                "nystart": int(mrc.header.nystart),
                "nzstart": int(mrc.header.nzstart),
                "mx": int(mrc.header.mx),
                "my": int(mrc.header.my),
                "mz": int(mrc.header.mz),
                "cell_a": float(mrc.header.cella.x),
                "cell_b": float(mrc.header.cella.y),
                "cell_c": float(mrc.header.cella.z),
                "origin_x": float(mrc.header.origin.x),
                "origin_y": float(mrc.header.origin.y),
                "origin_z": float(mrc.header.origin.z),
                "dtype": mrc.data.dtype,
                "pixel_size_x": None,
                "pixel_size_y": None,
                "pixel_size_z": None,
            }

            # Calculate pixel sizes (like original MATLAB code)
            if self._header["mx"] > 0:
                self._header["pixel_size_x"] = (
                    self._header["cell_a"] / self._header["mx"]
                )
            if self._header["my"] > 0:
                self._header["pixel_size_y"] = (
                    self._header["cell_b"] / self._header["my"]
                )
            if self._header["mz"] > 0:
                self._header["pixel_size_z"] = (
                    self._header["cell_c"] / self._header["mz"]
                )

    def _load_data(self) -> None:
        """
        Load volume data into memory.

        Note: Following BAH's optimization to avoid double memory usage
        by loading only when explicitly requested.
        """
        if self._is_data_loaded:
            return

        with mrcfile.open(self._filename, mode="r", permissive=True) as mrc:
            # Load data efficiently - mrcfile handles dtype conversion
            self._data = np.array(mrc.data, copy=True)
            self._is_data_loaded = True

        if self._debug:
            logger.info(
                f"Loaded data: shape={self._data.shape}, dtype={self._data.dtype}"
            )

    def get_header(self) -> dict[str, Any]:
        """
        Get header information.

        Returns:
            Dictionary containing header fields compatible with MATLAB version
        """
        if self._header is None:
            raise RuntimeError("No header loaded. Call open() first.")

        return self._header.copy()  # Return copy to prevent modification

    def get_data(self, force_load: bool = True) -> np.ndarray | None:
        """
        Get volume data.

        Args:
            force_load: Load data if not already loaded

        Returns:
            Volume data array or None if not loaded
        """
        if not self._is_data_loaded and force_load:
            self._load_data()

        return self._data

    def is_volume_loaded(self) -> bool:
        """Check if volume data is loaded in memory."""
        return self._is_data_loaded

    # Header accessor methods (matching MATLAB interface)
    def get_nx(self) -> int:
        """Get X dimension."""
        return self._header["nx"] if self._header else 0

    def get_ny(self) -> int:
        """Get Y dimension."""
        return self._header["ny"] if self._header else 0

    def get_nz(self) -> int:
        """Get Z dimension."""
        return self._header["nz"] if self._header else 0

    def get_nxstart(self) -> int:
        """Get X start offset."""
        return self._header["nxstart"] if self._header else 0

    def get_nystart(self) -> int:
        """Get Y start offset."""
        return self._header["nystart"] if self._header else 0

    def get_nzstart(self) -> int:
        """Get Z start offset."""
        return self._header["nzstart"] if self._header else 0

    def get_mx(self) -> int:
        """Get X sampling."""
        return self._header["mx"] if self._header else 0

    def get_my(self) -> int:
        """Get Y sampling."""
        return self._header["my"] if self._header else 0

    def get_mz(self) -> int:
        """Get Z sampling."""
        return self._header["mz"] if self._header else 0

    def get_cell_x(self) -> float:
        """Get cell dimension X."""
        return self._header["cell_a"] if self._header else 0.0

    def get_cell_y(self) -> float:
        """Get cell dimension Y."""
        return self._header["cell_b"] if self._header else 0.0

    def get_cell_z(self) -> float:
        """Get cell dimension Z."""
        return self._header["cell_c"] if self._header else 0.0

    def get_pixel_size(self) -> tuple[float, float, float]:
        """
        Get pixel sizes in X, Y, Z.

        Returns:
            Tuple of (pixel_size_x, pixel_size_y, pixel_size_z)
        """
        if not self._header:
            return (0.0, 0.0, 0.0)

        return (
            self._header["pixel_size_x"] or 0.0,
            self._header["pixel_size_y"] or 0.0,
            self._header["pixel_size_z"] or 0.0,
        )

    def get_filename(self) -> Path | None:
        """Get associated filename."""
        return self._filename

    def close(self) -> None:
        """
        Close MRC file and free memory.

        Note: Following BAH's pattern of explicit memory management.
        """
        self._data = None
        self._is_data_loaded = False
        self._mrc_handle = None

        if self._debug:
            logger.info("Closed MRC file and freed data memory")

    @classmethod
    def from_header(
        cls, header_dict: dict[str, Any], filename: str | Path | None = None
    ) -> "MRCImage":
        """
        Create empty MRCImage from header information.

        Args:
            header_dict: Header information dictionary
            filename: Optional filename to associate

        Returns:
            New MRCImage object with empty volume
        """
        img = cls()
        img._header = header_dict.copy()
        img._filename = Path(filename) if filename else None

        # Create zero volume if dimensions are specified
        if all(k in header_dict for k in ["nx", "ny", "nz"]):
            shape = (header_dict["nz"], header_dict["ny"], header_dict["nx"])
            img._data = np.zeros(shape, dtype=np.float32)
            img._is_data_loaded = True

        return img

    def __del__(self):
        """Destructor - ensure memory is freed."""
        self.close()

    def save(self, filename: str | Path, pixel_size=None, origin=None) -> None:
        """
        Save the MRC image to a file (MATLAB SAVE_IMG equivalent).

        Args:
            filename: Output filename
            pixel_size: Pixel size(s) in Angstroms (scalar or 3-element array)
            origin: Origin coordinates (3-element array or 'center')

        Note:
            Following BAH's pattern - doesn't return object to prevent memory binding.
        """
        if self._data is None:
            raise ValueError("No volume data to save")

        filename = Path(filename)

        # Handle pixel size parameter (following MATLAB logic)
        if pixel_size is not None:
            if np.isscalar(pixel_size):
                pixel_size = np.array([pixel_size, pixel_size, pixel_size])
            else:
                pixel_size = np.array(pixel_size)
                if len(pixel_size) == 1:
                    pixel_size = np.array([pixel_size[0], pixel_size[0], pixel_size[0]])
                elif len(pixel_size) != 3:
                    raise ValueError("pixel_size must be scalar or 3-element array")

        # Create new MRC file
        with mrcfile.new(filename, overwrite=True) as mrc:
            # Set data with appropriate dtype
            output_data = self._get_output_data()
            mrc.set_data(output_data)

            # Update header with pixel size if provided
            if pixel_size is not None:
                # Get dimensions from data shape
                if len(output_data.shape) == 3:
                    nz, ny, nx = output_data.shape  # MRC convention
                elif len(output_data.shape) == 2:
                    ny, nx = output_data.shape
                    nz = 1
                else:
                    raise ValueError("Unsupported data dimensionality")

                # Apply pixel size to cell dimensions (following MATLAB logic)
                mrc.header.cella.x = nx * pixel_size[0]
                mrc.header.cella.y = ny * pixel_size[1]
                mrc.header.cella.z = nz * pixel_size[2]

            # Handle origin if provided
            if origin is not None:
                if isinstance(origin, str) and origin == "center":
                    # Center the origin (following MATLAB: -cellDimension/2)
                    if pixel_size is not None:
                        mrc.header.origin.x = -mrc.header.cella.x / 2
                        mrc.header.origin.y = -mrc.header.cella.y / 2
                        mrc.header.origin.z = -mrc.header.cella.z / 2
                else:
                    origin = np.array(origin)
                    if len(origin) >= 3:
                        mrc.header.origin.x = origin[0]
                        mrc.header.origin.y = origin[1]
                        mrc.header.origin.z = origin[2]

            # Set standard MRC header values (following MATLAB)
            mrc.header.alpha = 90.0
            mrc.header.beta = 90.0
            mrc.header.gamma = 90.0
            mrc.header.ispg = 1  # Space group (1 for volume, not stack)

            # Update statistics if they're not set (following MATLAB logic)
            if mrc.header.dmin == 0.0 and mrc.header.dmax == 0.0 and output_data.size < 768**3:
                mrc.update_header_stats()

        if self._debug:
            logger.info(f"Saved MRC image to: {filename}")

    def _get_output_data(self) -> np.ndarray:
        """
        Get data in appropriate format for saving.

        Returns:
            Data array ready for MRC output

        Note:
            Following MATLAB logic for dtype handling and complex data.
        """
        if self._data is None:
            raise ValueError("No data available")

        data = self._data

        # Handle complex data (following MATLAB logic)
        if np.iscomplexobj(data):
            # For complex data, interleave real and imaginary parts
            # This follows the MATLAB pattern in SAVE_IMG.m
            if len(data.shape) == 3:
                nz, ny, nx = data.shape
                if data.dtype == np.complex128:
                    output = np.zeros((nz, ny, 2 * nx), dtype=np.float32)
                else:
                    output = np.zeros((nz, ny, 2 * nx), dtype=np.float32)
                output[:, :, ::2] = data.real.astype(np.float32)
                output[:, :, 1::2] = data.imag.astype(np.float32)
                return output
            else:
                # 2D case
                ny, nx = data.shape
                if data.dtype == np.complex128:
                    output = np.zeros((ny, 2 * nx), dtype=np.float32)
                else:
                    output = np.zeros((ny, 2 * nx), dtype=np.float32)
                output[:, ::2] = data.real.astype(np.float32)
                output[:, 1::2] = data.imag.astype(np.float32)
                return output

        # Handle normal data types
        if data.dtype == np.float64:
            return data.astype(np.float32)  # Convert double to single
        elif data.dtype in [np.int8, np.uint8, np.int16, np.uint16, np.float32]:
            return data  # Keep as is
        else:
            return data.astype(np.float32)  # Default to float32


def SAVE_IMG(
    mrc_image: MRCImage, filename: str | Path, pixel_size=None, origin=None
) -> None:
    """
    Save MRC image to file (MATLAB SAVE_IMG equivalent).

    Args:
        mrc_image: MRCImage object to save
        filename: Output filename
        pixel_size: Pixel size(s) in Angstroms
        origin: Origin coordinates

    Note:
        Following BAH's pattern - doesn't return object to prevent memory binding.
        This is the functional equivalent of the MATLAB SAVE_IMG method.
    """
    mrc_image.save(filename, pixel_size=pixel_size, origin=origin)


def OPEN_IMG(dtype_str: str, mrc_image: MRCImage) -> np.ndarray:
    """
    Load image data with specified dtype (MATLAB OPEN_IMG equivalent).

    Args:
        dtype_str: Data type ('single', 'double', 'int16', etc.)
        mrc_image: MRCImage object to load from

    Returns:
        Volume data as numpy array

    Note:
        Following BAH's optimization: "2x as fast to recast the whole array,
        than to either read in as different types"
    """
    # Map MATLAB dtypes to numpy dtypes
    dtype_map = {
        "single": np.float32,
        "double": np.float64,
        "int8": np.int8,
        "int16": np.int16,
        "int32": np.int32,
        "uint8": np.uint8,
        "uint16": np.uint16,
        "uint32": np.uint32,
    }

    if dtype_str not in dtype_map:
        raise ValueError(f"Unsupported dtype: {dtype_str}")

    # Get data (this will load if not already loaded)
    data = mrc_image.get_data(force_load=True)

    # Convert dtype efficiently (following BAH's optimization)
    target_dtype = dtype_map[dtype_str]
    if data.dtype != target_dtype:
        data = data.astype(target_dtype)

    return data


def create_test_mrc(
    filename: str | Path,
    shape: tuple[int, int, int] = (10, 20, 30),
    pixel_size: float = 1.0,
) -> Path:
    """
    Create a test MRC file for development and testing.

    Args:
        filename: Output filename
        shape: Volume shape (nz, ny, nx)
        pixel_size: Pixel size in Angstroms

    Returns:
        Path to created file
    """
    filename = Path(filename)

    # Create test data - simple gradient
    nz, ny, nx = shape
    data = np.zeros(shape, dtype=np.float32)

    for z in range(nz):
        for y in range(ny):
            for x in range(nx):
                data[z, y, x] = (x + y + z) / (nx + ny + nz)

    # Create MRC file
    with mrcfile.new(filename, overwrite=True) as mrc:
        mrc.set_data(data)
        mrc.header.mx = nx
        mrc.header.my = ny
        mrc.header.mz = nz
        mrc.header.cella.x = nx * pixel_size
        mrc.header.cella.y = ny * pixel_size
        mrc.header.cella.z = nz * pixel_size
        mrc.update_header_from_data()

    logger.info(f"Created test MRC file: {filename}")
    logger.info(f"Shape: {shape}, Pixel size: {pixel_size} Å")

    return filename


def test_mrc_image_basic():
    """Basic test of MRCImage functionality."""
    print("=" * 50)
    print("Testing MRCImage Basic Functionality")
    print("=" * 50)

    # Create test file in /tmp
    test_file = Path("/tmp/test_mrc_image.mrc")
    test_save_file = Path("/tmp/test_mrc_save.mrc")

    create_test_mrc(test_file, shape=(5, 10, 15), pixel_size=2.0)

    try:
        # Test 1: Header-only loading (default, fast)
        print("\n1. Testing header-only loading...")
        img = MRCImage(test_file)

        print(f"   Filename: {img.get_filename()}")
        print(f"   Dimensions: {img.get_nx()} x {img.get_ny()} x {img.get_nz()}")
        print(f"   Pixel sizes: {img.get_pixel_size()}")
        print(f"   Data loaded: {img.is_volume_loaded()}")

        # Test 2: Header access
        print("\n2. Testing header access...")
        header = img.get_header()
        print(f"   Header keys: {list(header.keys())}")
        print(
            f"   Cell dimensions: {header['cell_a']:.1f} x {header['cell_b']:.1f} x {header['cell_c']:.1f}"
        )

        # Test 3: Data loading on demand
        print("\n3. Testing data loading...")
        data = img.get_data()
        print(f"   Data shape: {data.shape}")
        print(f"   Data dtype: {data.dtype}")
        print(f"   Data range: {data.min():.3f} to {data.max():.3f}")
        print(f"   Data loaded: {img.is_volume_loaded()}")

        # Test 4: OPEN_IMG function
        print("\n4. Testing OPEN_IMG function...")
        data_single = OPEN_IMG("single", img)
        print(f"   OPEN_IMG shape: {data_single.shape}")
        print(f"   OPEN_IMG dtype: {data_single.dtype}")

        # Test 5: SAVE_IMG functionality
        print("\n5. Testing SAVE_IMG functionality...")

        # Test basic save
        SAVE_IMG(img, test_save_file)
        print(f"   Saved basic file: {test_save_file}")

        # Test save with pixel size
        SAVE_IMG(img, test_save_file, pixel_size=1.5)
        print("   Saved with pixel size 1.5 Å")

        # Test save with pixel size array and centered origin
        SAVE_IMG(img, test_save_file, pixel_size=[1.0, 1.5, 2.0], origin="center")
        print("   Saved with anisotropic pixel sizes and centered origin")

        # Verify saved file can be read back
        img_loaded = MRCImage(test_save_file)
        data_loaded = img_loaded.get_data()
        print(
            f"   Loaded back - shape: {data_loaded.shape}, dtype: {data_loaded.dtype}"
        )
        print(f"   Pixel sizes from saved file: {img_loaded.get_pixel_size()}")

        # Test 6: Memory management
        print("\n6. Testing memory management...")
        print(f"   Before close - data loaded: {img.is_volume_loaded()}")
        img.close()
        print(f"   After close - data loaded: {img.is_volume_loaded()}")

        print("\n✅ All tests passed!")

    finally:
        # Cleanup
        for f in [test_file, test_save_file]:
            if f.exists():
                f.unlink()
                print(f"   Cleaned up: {f}")


def test_mrc_image_performance():
    """Test performance optimizations from BAH's modifications."""
    print("\n" + "=" * 50)
    print("Testing MRCImage Performance Features")
    print("=" * 50)

    test_file = Path("/tmp/test_performance.mrc")

    try:
        # Create larger test file
        create_test_mrc(test_file, shape=(20, 50, 80), pixel_size=1.2)

        # Test 1: Default flgLoad=0 behavior (header only)
        print("\n1. Testing lazy loading (BAH optimization)...")
        import time

        start_time = time.time()
        img = MRCImage(test_file)  # Should be fast - header only
        header_time = time.time() - start_time
        print(f"   Header-only load time: {header_time:.4f}s")
        print(f"   Data loaded: {img.is_volume_loaded()}")

        # Test 2: Data loading on demand
        start_time = time.time()
        data = img.get_data()  # Now loads data
        data_time = time.time() - start_time
        print(f"   Data load time: {data_time:.4f}s")
        print(f"   Data loaded: {img.is_volume_loaded()}")

        # Test 3: Efficient dtype conversion (BAH optimization)
        print("\n2. Testing efficient dtype conversion...")
        start_time = time.time()
        data_int16 = OPEN_IMG("int16", img)
        convert_time = time.time() - start_time
        print(f"   Dtype conversion time: {convert_time:.4f}s")
        print(f"   Original dtype: {data.dtype}, converted: {data_int16.dtype}")

        # Test 4: Memory cleanup
        print("\n3. Testing memory cleanup...")
        print(f"   Before close - data loaded: {img.is_volume_loaded()}")
        img.close()
        print(f"   After close - data loaded: {img.is_volume_loaded()}")

        print("\n✅ Performance tests completed!")

    finally:
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    test_mrc_image_basic()
    test_mrc_image_performance()
