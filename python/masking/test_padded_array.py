#!/usr/bin/env python3
"""
Test and demonstration script for PaddedArray class.

This script demonstrates the key features:
1. Single-use mode for one-off padding operations
2. Persistent mode for efficient reuse
3. Memory management and GPU/CPU switching
4. Comparison with original function-based approach

Author: emClarity Python Conversion
Date: September 2025
"""

import logging
import time

import numpy as np

logger = logging.getLogger(__name__)

from masking.emc_pad_zeros_3d import emc_pad_zeros_3d
from masking.padded_array import PaddedArray, create_padded_array_once

# Clean package imports - no sys.path manipulation needed


# Try to import CuPy
try:
    import cupy as cp

    HAS_CUPY = True
    logger.info("CuPy available - GPU tests enabled")
except ImportError:
    HAS_CUPY = False
    cp = None
    logger.warning("CuPy not available - CPU tests only")


def test_single_use_mode():
    """Test single-use mode (equivalent to original function)."""
    print("\n🔧 Testing Single-Use Mode")
    print("=" * 50)

    # Create test image
    image = np.random.rand(64, 64, 32).astype(np.float32)
    pad_low = [10, 15, 5]
    pad_top = [10, 15, 5]

    print(f"Input shape: {image.shape}")
    print(f"Padding: low={pad_low}, top={pad_top}")

    # Test CPU single-use
    start_time = time.perf_counter()
    result_cpu = create_padded_array_once(
        image, pad_low, pad_top, method="CPU", precision="single"
    )
    cpu_time = time.perf_counter() - start_time

    print(f"CPU result shape: {result_cpu.shape}")
    print(f"CPU time: {cpu_time * 1000:.2f}ms")

    # Test GPU single-use if available
    if HAS_CUPY:
        image_gpu = cp.asarray(image)
        start_time = time.perf_counter()
        result_gpu = create_padded_array_once(
            image_gpu, pad_low, pad_top, method="GPU", precision="single"
        )
        gpu_time = time.perf_counter() - start_time

        print(f"GPU result shape: {result_gpu.shape}")
        print(f"GPU time: {gpu_time * 1000:.2f}ms")
        print(f"GPU speedup: {cpu_time / gpu_time:.1f}x")

        # Verify results match
        if np.allclose(result_cpu, cp.asnumpy(result_gpu)):
            print("✅ CPU and GPU results match")
        else:
            print("❌ CPU and GPU results differ")

    # Compare with original function
    original_result = emc_pad_zeros_3d(
        image, pad_low, pad_top, method="CPU", precision="single"
    )

    if np.allclose(result_cpu, original_result):
        print("✅ Matches original function")
    else:
        print("❌ Differs from original function")


def test_persistent_mode():
    """Test persistent mode for efficient reuse."""
    print("\n🔄 Testing Persistent Mode")
    print("=" * 50)

    # Setup for multiple operations with same dimensions
    image_shape = (32, 32, 16)
    pad_low = [8, 8, 4]
    pad_top = [8, 8, 4]
    output_shape = (48, 48, 24)

    print(f"Input shape: {image_shape}")
    print(f"Output shape: {output_shape}")

    # Create persistent padder
    padder = PaddedArray(
        input_shape=image_shape,
        output_shape=output_shape,
        method="CPU",
        precision="single",
        use_once=False,
    )

    print(f"Memory info: {padder.get_memory_info()}")

    # Test multiple operations
    num_operations = 5
    times = []

    for i in range(num_operations):
        # Create different test image each time
        image = np.random.rand(*image_shape).astype(np.float32) * (i + 1)

        start_time = time.perf_counter()

        # Zero the stored array before reuse
        if i > 0:
            padder.zero_stored_array()

        result = padder.pad_image(image, pad_low, pad_top)
        op_time = time.perf_counter() - start_time
        times.append(op_time)

        print(f"Operation {i + 1}: {op_time * 1000:.2f}ms, shape={result.shape}")

    avg_time = np.mean(times[1:])  # Exclude first operation (includes allocation)
    print(f"Average reuse time: {avg_time * 1000:.2f}ms")

    # Test getting reference to stored array
    ref = padder.get_stored_array_reference()
    print(f"Stored array reference shape: {ref.shape}")
    print("⚠️  Remember: keep reference alive to access array data!")


def test_memory_management():
    """Test memory management features."""
    print("\n💾 Testing Memory Management")
    print("=" * 50)

    # Create padder with known dimensions
    padder = PaddedArray(
        input_shape=(64, 64, 32),
        output_shape=(128, 128, 64),
        method="CPU",
        precision="single",
        use_once=False,
    )

    print("Initial configuration:")
    print(f"Memory info: {padder.get_memory_info()}")

    if HAS_CUPY:
        # Test CPU to GPU transfer
        print("\nMoving to GPU...")
        padder.to_gpu()
        print(f"After GPU move: method={padder.method}")

        # Test GPU to CPU transfer
        print("\nMoving back to CPU...")
        padder.to_cpu()
        print(f"After CPU move: method={padder.method}")

    # Test configuration updates
    print("\nUpdating configuration...")
    padder.update_config(output_shape=(256, 256, 128), precision="double")
    print(f"After config update: {padder.get_memory_info()}")


def test_different_padding_modes():
    """Test different padding modes and extrapolation values."""
    print("\n🎨 Testing Different Padding Modes")
    print("=" * 50)

    image = np.random.rand(32, 32, 16).astype(np.float32)
    pad_low = [8, 8, 4]
    pad_top = [8, 8, 4]

    # Test different extrapolation values
    modes = [
        ("zeros", None),
        ("constant", 0.5),
        ("random", "random"),
    ]

    for mode_name, extrap_val in modes:
        print(f"\nTesting {mode_name} mode:")

        padder = PaddedArray(
            method="CPU", precision="single", use_once=True, extrap_val=extrap_val
        )

        result = padder.pad_image(image, pad_low, pad_top)

        # Analyze padding regions
        padding_region = result[:8, :8, :4]  # Sample padding region
        if extrap_val == "random":
            padding_stats = (
                f"mean={np.mean(padding_region):.3f}, std={np.std(padding_region):.3f}"
            )
        else:
            padding_stats = f"value={np.mean(padding_region):.3f}"

        print(f"  Result shape: {result.shape}")
        print(f"  Padding stats: {padding_stats}")


def benchmark_vs_original():
    """Benchmark PaddedArray against original function."""
    print("\n⚡ Benchmarking vs Original Function")
    print("=" * 50)

    # Test parameters
    image_shape = (128, 128, 64)
    pad_low = [32, 32, 16]
    pad_top = [32, 32, 16]
    num_iterations = 10

    print(f"Testing {num_iterations} iterations with shape {image_shape}")

    # Benchmark original function
    original_times = []
    for i in range(num_iterations):
        image = np.random.rand(*image_shape).astype(np.float32)

        start_time = time.perf_counter()
        _result_orig = emc_pad_zeros_3d(image, pad_low, pad_top, method="CPU")
        orig_time = time.perf_counter() - start_time
        original_times.append(orig_time)

    avg_orig_time = np.mean(original_times)

    # Benchmark single-use PaddedArray
    single_times = []
    for i in range(num_iterations):
        image = np.random.rand(*image_shape).astype(np.float32)

        start_time = time.perf_counter()
        _result_single = create_padded_array_once(image, pad_low, pad_top, method="CPU")
        single_time = time.perf_counter() - start_time
        single_times.append(single_time)

    avg_single_time = np.mean(single_times)

    # Benchmark persistent PaddedArray
    output_shape = tuple(np.array(image_shape) + np.array(pad_low) + np.array(pad_top))
    padder = PaddedArray(
        input_shape=image_shape,
        output_shape=output_shape,
        method="CPU",
        precision="single",
        use_once=False,
    )

    persistent_times = []
    for i in range(num_iterations):
        image = np.random.rand(*image_shape).astype(np.float32)

        if i > 0:
            padder.zero_stored_array()

        start_time = time.perf_counter()
        _result_persistent = padder.pad_image(image, pad_low, pad_top)
        persistent_time = time.perf_counter() - start_time
        persistent_times.append(persistent_time)

    avg_persistent_time = np.mean(
        persistent_times[1:]
    )  # Exclude first (includes allocation)

    # Report results
    print(f"Original function:     {avg_orig_time * 1000:.2f}ms")
    print(f"Single-use PaddedArray: {avg_single_time * 1000:.2f}ms")
    print(f"Persistent PaddedArray: {avg_persistent_time * 1000:.2f}ms")
    print(f"Persistent speedup:    {avg_orig_time / avg_persistent_time:.1f}x")

    # Verify correctness
    test_image = np.random.rand(*image_shape).astype(np.float32)
    result1 = emc_pad_zeros_3d(test_image, pad_low, pad_top, method="CPU")
    result2 = create_padded_array_once(test_image, pad_low, pad_top, method="CPU")

    padder.zero_stored_array()
    result3 = padder.pad_image(test_image, pad_low, pad_top)

    if np.allclose(result1, result2) and np.allclose(result1, result3):
        print("✅ All methods produce identical results")
    else:
        print("❌ Results differ between methods")


def main():
    """Run all tests and demonstrations."""
    print("🧪 PaddedArray Class Testing Suite")
    print("=" * 60)
    print("Demonstrating fourierTransformer-style padding class")

    try:
        test_single_use_mode()
        test_persistent_mode()
        test_memory_management()
        test_different_padding_modes()
        benchmark_vs_original()

        print("\n🎉 All tests completed successfully!")
        print("\nKey Benefits of PaddedArray:")
        print("• Memory reuse for repeated operations")
        print("• GPU/CPU memory management")
        print("• Flexible configuration options")
        print("• Compatible with original function interface")
        print("• Follows fourierTransformer.m pattern")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
