"""
Comprehensive tests for emc_pad_zeros_3d with comparison to MATLAB original.

Tests include:
- Round-trip testing with mrcfile volumes
- Comparison with MATLAB BH_padZeros3d output
- GPU vs CPU consistency (when CuPy available)
- Various padding modes and parameters
"""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

# Add the python package root to path for proper imports
python_root = Path(__file__).parent.parent.parent
if str(python_root) not in sys.path:
    sys.path.insert(0, str(python_root))

from masking.emc_pad_zeros_3d import BH_padZeros3d, emc_pad_zeros_3d

# Try to import required packages
try:
    import mrcfile

    HAS_MRCFILE = True
except ImportError:
    HAS_MRCFILE = False

try:
    import cupy as cp

    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False


class TestPadZeros3D(unittest.TestCase):
    """Test cases for the 3D padding function."""

    def setUp(self):
        """Set up test fixtures."""
        np.random.seed(42)  # For reproducible tests

        # Create test volumes
        self.small_3d = np.random.randn(10, 12, 8).astype(np.float32)
        self.medium_3d = np.random.randn(64, 64, 32).astype(np.float32)
        self.test_2d = np.random.randn(16, 20).astype(np.float32)

        # Standard padding parameters
        self.pad_low_3d = np.array([2, 3, 1])
        self.pad_top_3d = np.array([4, 2, 3])
        self.pad_low_2d = np.array([3, 2])
        self.pad_top_2d = np.array([2, 4])

    def test_basic_padding_3d(self):
        """Test basic 3D padding functionality."""
        result = emc_pad_zeros_3d(
            self.small_3d,
            self.pad_low_3d,
            self.pad_top_3d,
            method="CPU",
            precision="single",
        )

        expected_shape = (
            self.small_3d.shape[0] + self.pad_low_3d[0] + self.pad_top_3d[0],
            self.small_3d.shape[1] + self.pad_low_3d[1] + self.pad_top_3d[1],
            self.small_3d.shape[2] + self.pad_low_3d[2] + self.pad_top_3d[2],
        )

        self.assertEqual(result.shape, expected_shape)
        self.assertEqual(result.dtype, np.float32)

        # Check that original data is preserved
        np.testing.assert_array_equal(
            result[
                self.pad_low_3d[0] : -self.pad_top_3d[0] or None,
                self.pad_low_3d[1] : -self.pad_top_3d[1] or None,
                self.pad_low_3d[2] : -self.pad_top_3d[2] or None,
            ],
            self.small_3d,
        )

        # Check that padding is zeros
        self.assertTrue(np.all(result[: self.pad_low_3d[0], :, :] == 0))
        self.assertTrue(np.all(result[:, : self.pad_low_3d[1], :] == 0))
        self.assertTrue(np.all(result[:, :, : self.pad_low_3d[2]] == 0))

    def test_basic_padding_2d(self):
        """Test basic 2D padding functionality."""
        result = emc_pad_zeros_3d(
            self.test_2d,
            self.pad_low_2d,
            self.pad_top_2d,
            method="CPU",
            precision="single",
        )

        expected_shape = (
            self.test_2d.shape[0] + self.pad_low_2d[0] + self.pad_top_2d[0],
            self.test_2d.shape[1] + self.pad_low_2d[1] + self.pad_top_2d[1],
        )

        self.assertEqual(result.shape, expected_shape)

        # Check original data preservation
        np.testing.assert_array_equal(
            result[
                self.pad_low_2d[0] : -self.pad_top_2d[0] or None,
                self.pad_low_2d[1] : -self.pad_top_2d[1] or None,
            ],
            self.test_2d,
        )

    @unittest.skipUnless(HAS_CUPY, "CuPy not available")
    def test_gpu_vs_cpu_consistency(self):
        """Test that GPU and CPU methods produce identical results."""
        cpu_result = emc_pad_zeros_3d(
            self.small_3d,
            self.pad_low_3d,
            self.pad_top_3d,
            method="CPU",
            precision="single",
        )

        gpu_result = emc_pad_zeros_3d(
            self.small_3d,
            self.pad_low_3d,
            self.pad_top_3d,
            method="GPU",
            precision="single",
        )

        # Convert GPU result back to CPU for comparison
        gpu_result_cpu = cp.asnumpy(gpu_result)

        np.testing.assert_array_equal(cpu_result, gpu_result_cpu)

    def test_precision_modes(self):
        """Test different precision modes."""
        for precision in ["single", "double"]:
            result = emc_pad_zeros_3d(
                self.small_3d, self.pad_low_3d, self.pad_top_3d, precision=precision
            )

            expected_dtype = np.float32 if precision == "single" else np.float64
            self.assertEqual(result.dtype, expected_dtype)

    def test_negative_padding_trimming(self):
        """Test trimming functionality with negative padding."""
        # Test trimming 2 pixels from low end only
        trim_vals = np.array([-2, -2, -2])  # Trim from beginning
        pad_vals = np.array([0, 0, 0])  # No padding at end

        result = emc_pad_zeros_3d(self.small_3d, trim_vals, pad_vals)

        # Original shape: (10, 12, 8), trim 2 from beginning = (8, 10, 6)
        expected_shape = (8, 10, 6)

        self.assertEqual(result.shape, expected_shape)

        # Check that trimmed data matches original with offset
        np.testing.assert_array_equal(result, self.small_3d[2:, 2:, 2:])

    def test_constant_extrapolation(self):
        """Test padding with constant value."""
        extrap_val = 5.0

        result = emc_pad_zeros_3d(
            self.small_3d, self.pad_low_3d, self.pad_top_3d, extrap_val=extrap_val
        )

        # Check that padding regions have the extrapolation value
        self.assertTrue(np.all(result[: self.pad_low_3d[0], :, :] == extrap_val))
        self.assertTrue(np.all(result[-self.pad_top_3d[0] :, :, :] == extrap_val))

    def test_random_extrapolation(self):
        """Test padding with random noise."""
        result = emc_pad_zeros_3d(
            self.small_3d, self.pad_low_3d, self.pad_top_3d, extrap_val="random"
        )

        # Check that padding regions are not zero (should be random)
        padding_region = result[: self.pad_low_3d[0], :, :]
        self.assertFalse(np.all(padding_region == 0))

        # Check that random values have reasonable statistics
        original_mean = np.mean(self.small_3d)
        original_std = np.std(self.small_3d)
        padding_mean = np.mean(padding_region)
        padding_std = np.std(padding_region)

        # Should be approximately similar statistics
        self.assertAlmostEqual(padding_mean, original_mean, places=0)
        self.assertAlmostEqual(padding_std, original_std, places=0)

    def test_fwd_inv_modes(self):
        """Test forward and inverse padding modes."""
        # Create padding specification array
        pad_specs = np.array(
            [
                [1, 2, 1],  # fwd low
                [2, 1, 2],  # fwd high
                [3, 3, 1],  # inv low
                [1, 3, 3],  # inv high
            ]
        )

        # Test forward mode
        fwd_result = emc_pad_zeros_3d(self.small_3d, "fwd", pad_specs)

        expected_fwd_shape = (
            self.small_3d.shape[0] + 1 + 2,  # low + high
            self.small_3d.shape[1] + 2 + 1,
            self.small_3d.shape[2] + 1 + 2,
        )

        self.assertEqual(fwd_result.shape, expected_fwd_shape)

        # Test inverse mode
        inv_result = emc_pad_zeros_3d(self.small_3d, "inv", pad_specs)

        expected_inv_shape = (
            self.small_3d.shape[0] + 3 + 1,  # low + high
            self.small_3d.shape[1] + 3 + 3,
            self.small_3d.shape[2] + 1 + 3,
        )

        self.assertEqual(inv_result.shape, expected_inv_shape)

    def test_matlab_compatibility_interface(self):
        """Test the MATLAB-compatible BH_padZeros3d interface."""
        result = BH_padZeros3d(
            self.small_3d, self.pad_low_3d, self.pad_top_3d, "CPU", "single"
        )

        # Should match the modern interface
        expected = emc_pad_zeros_3d(
            self.small_3d,
            self.pad_low_3d,
            self.pad_top_3d,
            method="CPU",
            precision="single",
        )

        np.testing.assert_array_equal(result, expected)

    @unittest.skipUnless(HAS_MRCFILE, "mrcfile not available")
    def test_mrcfile_roundtrip(self):
        """Test reading/writing MRC files and padding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test MRC file
            test_file = Path(tmpdir) / "test_volume.mrc"

            with mrcfile.new(test_file, overwrite=True) as mrc:
                mrc.set_data(self.medium_3d)

            # Read back and test padding
            with mrcfile.open(test_file, mode="r") as mrc:
                volume = mrc.data.copy()

            # Apply padding
            padded = emc_pad_zeros_3d(
                volume, np.array([10, 10, 5]), np.array([10, 10, 5]), precision="single"
            )

            # Verify results
            expected_shape = (
                self.medium_3d.shape[0] + 20,
                self.medium_3d.shape[1] + 20,
                self.medium_3d.shape[2] + 10,
            )

            self.assertEqual(padded.shape, expected_shape)

            # Save padded result
            padded_file = Path(tmpdir) / "padded_volume.mrc"
            with mrcfile.new(padded_file, overwrite=True) as mrc:
                mrc.set_data(padded.astype(np.float32))

            # Verify file was written correctly
            with mrcfile.open(padded_file, mode="r") as mrc:
                saved_volume = mrc.data
                np.testing.assert_array_equal(saved_volume, padded)


def create_test_volumes_for_matlab_comparison():
    """
    Create test volumes and save them for comparison with MATLAB.

    This function creates test MRC files that can be loaded in MATLAB
    to compare the Python and MATLAB implementations.
    """
    if not HAS_MRCFILE:
        print("mrcfile not available - cannot create test volumes")
        return

    # Create deterministic test data
    np.random.seed(12345)

    test_volumes = {
        "small_3d": np.random.randn(16, 20, 12).astype(np.float32),
        "medium_3d": np.random.randn(64, 64, 32).astype(np.float32),
        "noise_3d": np.random.randn(32, 32, 16).astype(np.float32) * 2.5 + 1.2,
    }

    output_dir = Path("test_volumes")
    output_dir.mkdir(exist_ok=True)

    for name, volume in test_volumes.items():
        output_file = output_dir / f"{name}.mrc"

        with mrcfile.new(output_file, overwrite=True) as mrc:
            mrc.set_data(volume)

        print(f"Created {output_file} with shape {volume.shape}")

        # Also create padded versions for comparison
        for pad_name, (pad_low, pad_top) in [
            ("basic", ([4, 6, 2], [6, 4, 4])),
            ("asymmetric", ([2, 8, 1], [10, 2, 5])),
            ("trim", ([-2, -2, -1], [0, 0, 0])),
        ]:
            try:
                padded = emc_pad_zeros_3d(
                    volume,
                    np.array(pad_low),
                    np.array(pad_top),
                    method="CPU",
                    precision="single",
                )

                padded_file = output_dir / f"{name}_{pad_name}_padded.mrc"
                with mrcfile.new(padded_file, overwrite=True) as mrc:
                    mrc.set_data(padded)

                print(f"Created {padded_file} with shape {padded.shape}")

            except Exception as e:
                print(f"Failed to create {name}_{pad_name}: {e}")

    # Create parameter file for MATLAB testing
    param_file = output_dir / "test_parameters.txt"
    with open(param_file, "w") as f:
        f.write("# Test parameters for MATLAB comparison\n")
        f.write("# Format: volume_name, pad_low, pad_top, expected_shape\n")
        f.write("small_3d, [4,6,2], [6,4,4], [26,30,18]\n")
        f.write("medium_3d, [4,6,2], [6,4,4], [74,74,38]\n")
        f.write("noise_3d, [2,8,1], [10,2,5], [44,42,22]\n")

    print(f"\nTest volumes created in {output_dir}/")
    print("You can now test these with MATLAB BH_padZeros3d for comparison")


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2, exit=False)

    # Create test volumes for MATLAB comparison
    print("\n" + "=" * 60)
    print("Creating test volumes for MATLAB comparison...")
    create_test_volumes_for_matlab_comparison()
