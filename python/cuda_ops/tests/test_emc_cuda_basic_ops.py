"""
Tests for CUDA-accelerated basic array operations.
"""

import unittest
from unittest import skipIf

import cupy as cp
import numpy as np

try:
    from ..emc_cuda_basic_ops import CudaBasicOps

    CUPY_AVAILABLE = True
except ImportError:
    CUPY_AVAILABLE = False


@skipIf(not CUPY_AVAILABLE, "CuPy not available")
class TestCudaBasicOps(unittest.TestCase):
    """Test CUDA basic operations implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.cuda_ops = CudaBasicOps()
        self.assertTrue(self.cuda_ops.is_ready(), "CUDA kernels not loaded")

    def test_add_arrays(self):
        """Test CUDA array addition."""
        # Test 1D arrays
        a = cp.array([1.0, 2.0, 3.0, 4.0], dtype=cp.float32)
        b = cp.array([10.0, 20.0, 30.0, 40.0], dtype=cp.float32)

        result = self.cuda_ops.add_arrays(a, b)
        expected = cp.array([11.0, 22.0, 33.0, 44.0], dtype=cp.float32)

        cp.testing.assert_array_equal(result, expected)

        # Test 2D arrays
        a_2d = cp.random.rand(100, 50).astype(cp.float32)
        b_2d = cp.random.rand(100, 50).astype(cp.float32)

        result_2d = self.cuda_ops.add_arrays(a_2d, b_2d)
        expected_2d = a_2d + b_2d

        cp.testing.assert_array_almost_equal(result_2d, expected_2d, decimal=6)

    def test_add_arrays_shape_mismatch(self):
        """Test that array addition fails with mismatched shapes."""
        a = cp.array([1.0, 2.0, 3.0], dtype=cp.float32)
        b = cp.array([1.0, 2.0], dtype=cp.float32)

        with self.assertRaises(ValueError):
            self.cuda_ops.add_arrays(a, b)

    def test_multiply_scalar(self):
        """Test CUDA scalar multiplication."""
        # Test 1D array
        a = cp.array([1.0, 2.0, 3.0, 4.0], dtype=cp.float32)
        scalar = 3.5

        result = self.cuda_ops.multiply_scalar(a, scalar)
        expected = a * scalar

        cp.testing.assert_array_almost_equal(result, expected, decimal=6)

        # Test 3D array
        a_3d = cp.random.rand(10, 20, 30).astype(cp.float32)
        scalar = -2.7

        result_3d = self.cuda_ops.multiply_scalar(a_3d, scalar)
        expected_3d = a_3d * scalar

        cp.testing.assert_array_almost_equal(result_3d, expected_3d, decimal=5)

    def test_transpose_2d(self):
        """Test 2D matrix transpose."""
        # Test small matrix
        a = cp.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=cp.float32)

        result = self.cuda_ops.transpose_2d(a)
        expected = cp.array([[1.0, 4.0], [2.0, 5.0], [3.0, 6.0]], dtype=cp.float32)

        cp.testing.assert_array_equal(result, expected)

        # Test larger random matrix
        a_large = cp.random.rand(128, 256).astype(cp.float32)
        result_large = self.cuda_ops.transpose_2d(a_large)
        expected_large = a_large.T

        cp.testing.assert_array_almost_equal(result_large, expected_large, decimal=6)

    def test_transpose_2d_wrong_dimension(self):
        """Test that 2D transpose fails with wrong dimensions."""
        a_1d = cp.array([1.0, 2.0, 3.0], dtype=cp.float32)
        a_3d = cp.random.rand(10, 20, 30).astype(cp.float32)

        with self.assertRaises(ValueError):
            self.cuda_ops.transpose_2d(a_1d)

        with self.assertRaises(ValueError):
            self.cuda_ops.transpose_2d(a_3d)

    def test_transpose_3d(self):
        """Test 3D array transpose."""
        # Test small 3D array
        a = cp.arange(24, dtype=cp.float32).reshape(2, 3, 4)

        result = self.cuda_ops.transpose_3d(a)

        # Verify shape
        self.assertEqual(result.shape, (4, 3, 2))

        # Test against NumPy transpose
        a_np = cp.asnumpy(a)
        expected_np = np.transpose(a_np, (2, 1, 0))
        expected = cp.array(expected_np)

        cp.testing.assert_array_equal(result, expected)

        # Test larger random array
        a_large = cp.random.rand(32, 64, 16).astype(cp.float32)
        result_large = self.cuda_ops.transpose_3d(a_large)

        # Verify shape
        self.assertEqual(result_large.shape, (16, 64, 32))

        # Verify against NumPy
        a_large_np = cp.asnumpy(a_large)
        expected_large_np = np.transpose(a_large_np, (2, 1, 0))
        expected_large = cp.array(expected_large_np)

        cp.testing.assert_array_almost_equal(result_large, expected_large, decimal=6)

    def test_transpose_3d_wrong_dimension(self):
        """Test that 3D transpose fails with wrong dimensions."""
        a_2d = cp.random.rand(10, 20).astype(cp.float32)

        with self.assertRaises(ValueError):
            self.cuda_ops.transpose_3d(a_2d)

    def test_performance_comparison(self):
        """Test performance against CuPy built-ins."""
        # This is more of a benchmark than a test, but useful for validation
        size = (512, 512)
        a = cp.random.rand(*size).astype(cp.float32)
        b = cp.random.rand(*size).astype(cp.float32)

        # Test that our CUDA implementation gives same results as CuPy
        cuda_result = self.cuda_ops.add_arrays(a, b)
        cupy_result = a + b

        cp.testing.assert_array_almost_equal(cuda_result, cupy_result, decimal=6)

        # Test transpose
        cuda_transpose = self.cuda_ops.transpose_2d(a)
        cupy_transpose = a.T

        cp.testing.assert_array_almost_equal(cuda_transpose, cupy_transpose, decimal=6)

    def test_memory_layout(self):
        """Test that operations work with different memory layouts."""
        # Test with non-contiguous arrays
        a = cp.random.rand(100, 200).astype(cp.float32)
        b = cp.random.rand(100, 200).astype(cp.float32)

        # Create non-contiguous views
        a_slice = a[::2, ::2]
        b_slice = b[::2, ::2]

        # Should work (will be made contiguous internally)
        result = self.cuda_ops.add_arrays(a_slice, b_slice)
        expected = a_slice + b_slice

        cp.testing.assert_array_almost_equal(result, expected, decimal=6)


if __name__ == "__main__":
    unittest.main()
