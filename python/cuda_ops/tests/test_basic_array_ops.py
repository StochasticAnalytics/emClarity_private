"""
test_basic_array_ops.py.

Comprehensive tests for CUDA basic array operations.
Tests both functionality and performance against NumPy/CuPy equivalents.

Author: emClarity Python Conversion
Date: September 2025
"""

import sys
import time
import unittest
from pathlib import Path

import numpy as np
import pytest

cp = pytest.importorskip("cupy", reason="CuPy required for CUDA array ops tests")

# Add the python package root to path for proper imports
python_root = Path(__file__).parent.parent.parent
if str(python_root) not in sys.path:
    sys.path.insert(0, str(python_root))

try:
    from cuda_ops.basic_array_ops import (
        BasicArrayOps,
        cuda_array_add,
        cuda_array_scale,
        cuda_transpose_2d,
    )

    CUDA_AVAILABLE = True
except ImportError as e:
    print(f"CUDA operations not available: {e}")
    CUDA_AVAILABLE = False


class TestBasicArrayOps(unittest.TestCase):
    """Test CUDA basic array operations."""

    def setUp(self):
        """Set up test fixtures."""
        if not CUDA_AVAILABLE:
            self.skipTest("CUDA operations not available")

        self.ops = BasicArrayOps()

        # Test data sizes
        self.small_size = 1000
        self.medium_size = 100000
        self.large_size = 1000000

        # 2D test shapes
        self.small_2d = (50, 40)
        self.medium_2d = (500, 400)
        self.large_2d = (1000, 800)

        # 3D test shapes
        self.small_3d = (20, 30, 25)
        self.medium_3d = (100, 120, 80)
        self.large_3d = (200, 150, 100)

    def test_array_add_small(self):
        """Test array addition with small arrays."""
        # Create test data
        a_cpu = np.random.rand(self.small_size).astype(np.float32)
        b_cpu = np.random.rand(self.small_size).astype(np.float32)

        a_gpu = cp.asarray(a_cpu)
        b_gpu = cp.asarray(b_cpu)

        # CUDA implementation
        result_cuda = self.ops.array_add(a_gpu, b_gpu)

        # Reference implementation
        result_reference = a_gpu + b_gpu

        # Compare results
        np.testing.assert_allclose(
            cp.asnumpy(result_cuda), cp.asnumpy(result_reference), rtol=1e-6, atol=1e-6
        )

    def test_array_add_large(self):
        """Test array addition with large arrays."""
        # Create test data
        a_cpu = np.random.rand(self.large_size).astype(np.float32)
        b_cpu = np.random.rand(self.large_size).astype(np.float32)

        a_gpu = cp.asarray(a_cpu)
        b_gpu = cp.asarray(b_cpu)

        # CUDA implementation
        result_cuda = self.ops.array_add(a_gpu, b_gpu)

        # Reference implementation
        result_reference = a_gpu + b_gpu

        # Compare results
        np.testing.assert_allclose(
            cp.asnumpy(result_cuda), cp.asnumpy(result_reference), rtol=1e-6, atol=1e-6
        )

    def test_array_add_with_output(self):
        """Test array addition with pre-allocated output."""
        # Create test data
        a_cpu = np.random.rand(self.medium_size).astype(np.float32)
        b_cpu = np.random.rand(self.medium_size).astype(np.float32)

        a_gpu = cp.asarray(a_cpu)
        b_gpu = cp.asarray(b_cpu)
        output_gpu = cp.empty_like(a_gpu)

        # CUDA implementation with pre-allocated output
        result_cuda = self.ops.array_add(a_gpu, b_gpu, output_gpu)

        # Ensure the same array object is returned
        self.assertIs(result_cuda, output_gpu)

        # Reference implementation
        result_reference = a_gpu + b_gpu

        # Compare results
        np.testing.assert_allclose(
            cp.asnumpy(result_cuda), cp.asnumpy(result_reference), rtol=1e-6, atol=1e-6
        )

    def test_array_scale(self):
        """Test array scaling."""
        # Create test data
        input_cpu = np.random.rand(self.medium_size).astype(np.float32)
        scale_factor = 3.14159

        input_gpu = cp.asarray(input_cpu)

        # CUDA implementation
        result_cuda = self.ops.array_scale(input_gpu, scale_factor)

        # Reference implementation
        result_reference = input_gpu * scale_factor

        # Compare results
        np.testing.assert_allclose(
            cp.asnumpy(result_cuda), cp.asnumpy(result_reference), rtol=1e-6, atol=1e-6
        )

    def test_transpose_2d_small(self):
        """Test 2D transpose with small array."""
        # Create test data
        input_cpu = np.random.rand(*self.small_2d).astype(np.float32)
        input_gpu = cp.asarray(input_cpu)

        # CUDA implementation
        result_cuda = self.ops.transpose_2d(input_gpu)

        # Reference implementation
        result_reference = input_gpu.T

        # Compare results
        np.testing.assert_allclose(
            cp.asnumpy(result_cuda), cp.asnumpy(result_reference), rtol=1e-6, atol=1e-6
        )

        # Check shape
        self.assertEqual(result_cuda.shape, (self.small_2d[1], self.small_2d[0]))

    def test_transpose_2d_large(self):
        """Test 2D transpose with large array."""
        # Create test data
        input_cpu = np.random.rand(*self.large_2d).astype(np.float32)
        input_gpu = cp.asarray(input_cpu)

        # CUDA implementation
        result_cuda = self.ops.transpose_2d(input_gpu)

        # Reference implementation
        result_reference = input_gpu.T

        # Compare results
        np.testing.assert_allclose(
            cp.asnumpy(result_cuda), cp.asnumpy(result_reference), rtol=1e-6, atol=1e-6
        )

    def test_vector_magnitude_squared(self):
        """Test vector magnitude squared calculation."""
        # Create test data
        input_cpu = np.random.rand(self.medium_size).astype(np.float32)
        input_gpu = cp.asarray(input_cpu)

        # CUDA implementation
        result_cuda = self.ops.vector_magnitude_squared(input_gpu)

        # Reference implementation
        result_reference = input_gpu * input_gpu

        # Compare results
        np.testing.assert_allclose(
            cp.asnumpy(result_cuda), cp.asnumpy(result_reference), rtol=1e-6, atol=1e-6
        )

    def test_convenience_functions(self):
        """Test convenience wrapper functions."""
        # Test data
        a_cpu = np.random.rand(self.small_size).astype(np.float32)
        b_cpu = np.random.rand(self.small_size).astype(np.float32)

        a_gpu = cp.asarray(a_cpu)
        b_gpu = cp.asarray(b_cpu)

        # Test convenience functions
        result_add = cuda_array_add(a_gpu, b_gpu)
        result_scale = cuda_array_scale(a_gpu, 2.5)

        # Reference results
        ref_add = a_gpu + b_gpu
        ref_scale = a_gpu * 2.5

        # Compare
        np.testing.assert_allclose(
            cp.asnumpy(result_add), cp.asnumpy(ref_add), rtol=1e-6
        )
        np.testing.assert_allclose(
            cp.asnumpy(result_scale), cp.asnumpy(ref_scale), rtol=1e-6
        )

    def test_error_handling(self):
        """Test error handling for invalid inputs."""
        # Test mismatched shapes for addition
        a = cp.random.rand(100).astype(cp.float32)
        b = cp.random.rand(200).astype(cp.float32)

        with self.assertRaises(ValueError):
            self.ops.array_add(a, b)

        # Test wrong dtype
        a_int = cp.random.randint(0, 10, size=100).astype(cp.int32)

        with self.assertRaises(ValueError):
            self.ops.array_scale(a_int, 2.0)

        # Test wrong dimensions for 2D transpose
        a_3d = cp.random.rand(10, 10, 10).astype(cp.float32)

        with self.assertRaises(ValueError):
            self.ops.transpose_2d(a_3d)


class TestPerformance(unittest.TestCase):
    """Performance benchmarks comparing CUDA vs reference implementations."""

    def setUp(self):
        """Set up performance test fixtures."""
        if not CUDA_AVAILABLE:
            self.skipTest("CUDA operations not available")

        self.ops = BasicArrayOps()

        # Large arrays for performance testing
        self.perf_size_1d = 10_000_000  # 10M elements
        self.perf_size_2d = (3000, 3000)  # 9M elements
        self.perf_size_3d = (200, 200, 200)  # 8M elements

    def test_performance_array_add(self):
        """Benchmark array addition performance."""
        print(f"\n--- Array Addition Performance ({self.perf_size_1d:,} elements) ---")

        # Create test data
        a_cpu = np.random.rand(self.perf_size_1d).astype(np.float32)
        b_cpu = np.random.rand(self.perf_size_1d).astype(np.float32)

        a_gpu = cp.asarray(a_cpu)
        b_gpu = cp.asarray(b_cpu)

        # Warm up GPU
        _ = self.ops.array_add(a_gpu, b_gpu)
        cp.cuda.Device().synchronize()

        # Benchmark CUDA implementation
        start_time = time.time()
        for _ in range(10):
            result_cuda = self.ops.array_add(a_gpu, b_gpu)
        cp.cuda.Device().synchronize()
        cuda_time = (time.time() - start_time) / 10

        # Benchmark CuPy reference
        start_time = time.time()
        for _ in range(10):
            result_cupy = a_gpu + b_gpu
        cp.cuda.Device().synchronize()
        cupy_time = (time.time() - start_time) / 10

        print(f"CUDA kernel: {cuda_time * 1000:.2f} ms")
        print(f"CuPy reference: {cupy_time * 1000:.2f} ms")
        print(f"Speedup: {cupy_time / cuda_time:.2f}x")

        # Verify correctness
        np.testing.assert_allclose(
            cp.asnumpy(result_cuda), cp.asnumpy(result_cupy), rtol=1e-6
        )

    def test_performance_transpose_2d(self):
        """Benchmark 2D transpose performance."""
        print(f"\n--- 2D Transpose Performance {self.perf_size_2d} ---")

        # Create test data
        input_cpu = np.random.rand(*self.perf_size_2d).astype(np.float32)
        input_gpu = cp.asarray(input_cpu)

        # Warm up GPU
        _ = self.ops.transpose_2d(input_gpu)
        cp.cuda.Device().synchronize()

        # Benchmark CUDA implementation
        start_time = time.time()
        for _ in range(10):
            result_cuda = self.ops.transpose_2d(input_gpu)
        cp.cuda.Device().synchronize()
        cuda_time = (time.time() - start_time) / 10

        # Benchmark CuPy reference
        start_time = time.time()
        for _ in range(10):
            result_cupy = input_gpu.T
        cp.cuda.Device().synchronize()
        cupy_time = (time.time() - start_time) / 10

        print(f"CUDA kernel: {cuda_time * 1000:.2f} ms")
        print(f"CuPy reference: {cupy_time * 1000:.2f} ms")
        print(f"Speedup: {cupy_time / cuda_time:.2f}x")

        # Verify correctness
        np.testing.assert_allclose(
            cp.asnumpy(result_cuda), cp.asnumpy(result_cupy), rtol=1e-6
        )


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
