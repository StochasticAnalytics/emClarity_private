"""
test_memory_utils.py.

Unit tests for memory layout utility functions.
Tests all permutations of memory layout checks and error conditions.

Author: emClarity Python Conversion
Date: September 2025
"""

import os
import sys
import unittest
from pathlib import Path

import pytest

cp = pytest.importorskip("cupy")

# Add the python package root to path for proper imports
python_root = Path(__file__).parent.parent.parent
if str(python_root) not in sys.path:
    sys.path.insert(0, str(python_root))

from cuda_ops.memory_utils import create_fortran_array, ensure_c, ensure_f  # noqa: E402


class TestMemoryUtils(unittest.TestCase):
    """Test memory layout utility functions."""

    def setUp(self):
        """Set up test fixtures."""
        # Ensure strict checks are enabled for testing
        os.environ["EMCLARITY_NO_STRICT_CUPY_ORDERING_CHECKS"] = "0"

        # Create test arrays with different memory layouts
        self.test_shape = (3, 4)
        self.test_data = [[1.0, 2.0, 3.0, 4.0],
                         [5.0, 6.0, 7.0, 8.0],
                         [9.0, 10.0, 11.0, 12.0]]

    def test_ensure_f_with_f_contiguous_input(self):
        """Test ensure_f with F-contiguous input."""
        # Create F-contiguous array
        arr = cp.array(self.test_data, order='F', dtype=cp.float32)
        self.assertTrue(arr.flags.f_contiguous)
        self.assertFalse(arr.flags.c_contiguous)

        # Test with allow_copy=False (should return same object)
        result = ensure_f(arr, allow_copy=False)
        self.assertIs(result, arr)  # Same object
        self.assertTrue(result.flags.f_contiguous)

        # Test with allow_copy=True (should return same object)
        result = ensure_f(arr, allow_copy=True)
        self.assertIs(result, arr)  # Same object
        self.assertTrue(result.flags.f_contiguous)

    def test_ensure_f_with_c_contiguous_input_allow_copy_true(self):
        """Test ensure_f with C-contiguous input and allow_copy=True."""
        # Create C-contiguous array
        arr = cp.array(self.test_data, order='C', dtype=cp.float32)
        self.assertTrue(arr.flags.c_contiguous)
        self.assertFalse(arr.flags.f_contiguous)

        # Should create a copy and convert to F-contiguous
        result = ensure_f(arr, allow_copy=True)
        self.assertIsNot(result, arr)  # Different object (copy made)
        self.assertTrue(result.flags.f_contiguous)
        self.assertFalse(result.flags.c_contiguous)

        # Data should be the same
        cp.testing.assert_array_equal(result, arr)

    def test_ensure_f_with_c_contiguous_input_allow_copy_false(self):
        """Test ensure_f with C-contiguous input and allow_copy=False (should fail)."""
        # Create C-contiguous array
        arr = cp.array(self.test_data, order='C', dtype=cp.float32)
        self.assertTrue(arr.flags.c_contiguous)
        self.assertFalse(arr.flags.f_contiguous)

        # Should raise RuntimeError because copy is needed but not allowed
        with self.assertRaises(RuntimeError) as cm:
            ensure_f(arr, allow_copy=False)

        self.assertIn("input was not F-contiguous", str(cm.exception))
        self.assertIn("call site expected F-contiguous input", str(cm.exception))

    def test_ensure_f_with_dtype_conversion(self):
        """Test ensure_f with dtype conversion."""
        # Create F-contiguous array with different dtype
        arr = cp.array(self.test_data, order='F', dtype=cp.float64)
        self.assertTrue(arr.flags.f_contiguous)
        self.assertEqual(arr.dtype, cp.float64)

        # Convert to float32
        result = ensure_f(arr, allow_copy=True, dtype=cp.float32)
        self.assertTrue(result.flags.f_contiguous)
        self.assertEqual(result.dtype, cp.float32)

        # Should be a copy due to dtype change
        self.assertIsNot(result, arr)

    def test_ensure_c_with_c_contiguous_input(self):
        """Test ensure_c with C-contiguous input."""
        # Create C-contiguous array
        arr = cp.array(self.test_data, order='C', dtype=cp.float32)
        self.assertTrue(arr.flags.c_contiguous)
        self.assertFalse(arr.flags.f_contiguous)

        # Test with allow_copy=False (should return same object)
        result = ensure_c(arr, allow_copy=False)
        self.assertIs(result, arr)  # Same object
        self.assertTrue(result.flags.c_contiguous)

    def test_ensure_c_with_f_contiguous_input_allow_copy_true(self):
        """Test ensure_c with F-contiguous input and allow_copy=True."""
        # Create F-contiguous array
        arr = cp.array(self.test_data, order='F', dtype=cp.float32)
        self.assertTrue(arr.flags.f_contiguous)
        self.assertFalse(arr.flags.c_contiguous)

        # Should create a copy and convert to C-contiguous
        result = ensure_c(arr, allow_copy=True)
        self.assertIsNot(result, arr)  # Different object (copy made)
        self.assertTrue(result.flags.c_contiguous)
        self.assertFalse(result.flags.f_contiguous)

        # Data should be the same
        cp.testing.assert_array_equal(result, arr)

    def test_ensure_c_with_f_contiguous_input_allow_copy_false(self):
        """Test ensure_c with F-contiguous input and allow_copy=False (should fail)."""
        # Create F-contiguous array
        arr = cp.array(self.test_data, order='F', dtype=cp.float32)
        self.assertTrue(arr.flags.f_contiguous)
        self.assertFalse(arr.flags.c_contiguous)

        # Should raise RuntimeError because copy is needed but not allowed
        with self.assertRaises(RuntimeError) as cm:
            ensure_c(arr, allow_copy=False)

        self.assertIn("input was not C-contiguous", str(cm.exception))
        self.assertIn("call site expected C-contiguous input", str(cm.exception))

    def test_create_fortran_array(self):
        """Test create_fortran_array function."""
        # Test basic creation
        arr = create_fortran_array((5, 6), dtype=cp.float32)
        self.assertEqual(arr.shape, (5, 6))
        self.assertEqual(arr.dtype, cp.float32)
        self.assertTrue(arr.flags.f_contiguous)
        self.assertFalse(arr.flags.c_contiguous)

        # Test with different dtype
        arr = create_fortran_array((3, 3), dtype=cp.float64)
        self.assertEqual(arr.dtype, cp.float64)
        self.assertTrue(arr.flags.f_contiguous)

        # Test 1D array
        arr = create_fortran_array((10,), dtype=cp.int32)
        self.assertEqual(arr.shape, (10,))
        self.assertEqual(arr.dtype, cp.int32)
        self.assertTrue(arr.flags.f_contiguous)

        # Test 3D array
        arr = create_fortran_array((2, 3, 4), dtype=cp.float32)
        self.assertEqual(arr.shape, (2, 3, 4))
        self.assertTrue(arr.flags.f_contiguous)

    def test_strict_checks_disabled(self):
        """Test behavior when strict checks are disabled."""
        # Disable strict checks
        os.environ["EMCLARITY_NO_STRICT_CUPY_ORDERING_CHECKS"] = "1"

        # Need to reload the module to pick up the new environment variable
        import importlib

        from cuda_ops import memory_utils
        importlib.reload(memory_utils)

        try:
            # Create C-contiguous array
            arr = cp.array(self.test_data, order='C', dtype=cp.float32)
            self.assertTrue(arr.flags.c_contiguous)
            self.assertFalse(arr.flags.f_contiguous)

            # With strict checks disabled, this should NOT raise an error
            result = memory_utils.ensure_f(arr, allow_copy=False)
            self.assertTrue(result.flags.f_contiguous)
            # Should still make a copy to ensure F-contiguous
            self.assertIsNot(result, arr)

        finally:
            # Re-enable strict checks
            os.environ["EMCLARITY_NO_STRICT_CUPY_ORDERING_CHECKS"] = "0"
            importlib.reload(memory_utils)

    def test_non_contiguous_array(self):
        """Test with non-contiguous array (e.g., from slicing)."""
        # Create a larger array and take a slice to make it non-contiguous
        large_arr = cp.arange(60, dtype=cp.float32).reshape(6, 10, order='F')
        sliced_arr = large_arr[::2, ::2]  # Non-contiguous slice

        self.assertFalse(sliced_arr.flags.f_contiguous)
        self.assertFalse(sliced_arr.flags.c_contiguous)

        # ensure_f should make it contiguous
        result = ensure_f(sliced_arr, allow_copy=True)
        self.assertTrue(result.flags.f_contiguous)
        self.assertIsNot(result, sliced_arr)  # Should be a copy

        # Data should match
        cp.testing.assert_array_equal(result, sliced_arr)

    def test_1d_array_special_case(self):
        """Test 1D arrays (which are both C and F contiguous)."""
        arr_1d = cp.array([1, 2, 3, 4, 5], dtype=cp.float32)

        # 1D arrays are both C and F contiguous
        self.assertTrue(arr_1d.flags.f_contiguous)
        self.assertTrue(arr_1d.flags.c_contiguous)

        # Both ensure functions should return same object
        result_f = ensure_f(arr_1d, allow_copy=False)
        result_c = ensure_c(arr_1d, allow_copy=False)

        self.assertIs(result_f, arr_1d)
        self.assertIs(result_c, arr_1d)


if __name__ == "__main__":
    unittest.main()
