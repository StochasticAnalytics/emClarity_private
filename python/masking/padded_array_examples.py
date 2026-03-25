"""
Usage examples for PaddedArray class.

This demonstrates how to use PaddedArray following the fourierTransformer.m pattern
for efficient memory management and reuse in image processing pipelines.

Author: emClarity Python Conversion
Date: September 2025
"""

import sys
from pathlib import Path

import numpy as np

# Add the python package root to path for proper imports
python_root = Path(__file__).parent.parent
if str(python_root) not in sys.path:
    sys.path.insert(0, str(python_root))

from masking.padded_array import PaddedArray  # noqa: E402

try:
    import cupy as cp

    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False
    cp = None


def example_single_image_processing():
    """Example 1: Single image processing (use_once=True)."""
    print("Example 1: Single Image Processing")
    print("-" * 40)

    # For one-off operations, use single-use mode
    image = np.random.rand(64, 64, 32).astype(np.float32)

    padder = PaddedArray(
        method="GPU" if HAS_CUPY else "CPU",
        precision="single",
        use_once=True,  # Don't store arrays
        extrap_val=0.0,
    )

    # Simple padding
    result = padder.pad_image(image=image, pad_low=[16, 16, 8], pad_top=[16, 16, 8])

    print(f"Input: {image.shape} -> Output: {result.shape}")
    print("✅ Single-use padding complete\n")


def example_batch_processing():
    """Example 2: Batch processing with memory reuse."""
    print("Example 2: Batch Processing with Reuse")
    print("-" * 40)

    # For batch processing, pre-allocate and reuse
    batch_size = 5
    image_shape = (32, 32, 16)
    pad_low = [8, 8, 4]
    pad_top = [8, 8, 4]
    output_shape = (48, 48, 24)

    # Create persistent padder
    padder = PaddedArray(
        input_shape=image_shape,
        output_shape=output_shape,
        method="GPU" if HAS_CUPY else "CPU",
        precision="single",
        use_once=False,  # Enable reuse
    )

    print(f"Allocated {padder.get_memory_info()['array_size_mb']:.1f}MB for reuse")

    results = []
    for i in range(batch_size):
        # Generate test image
        image = np.random.rand(*image_shape).astype(np.float32) * (i + 1)

        # Zero out previous data (critical for reuse!)
        if i > 0:
            padder.zero_stored_array()

        # Pad the image
        result = padder.pad_image(image, pad_low, pad_top)
        results.append(result)

        print(f"Batch {i + 1}: processed {image.shape} -> {result.shape}")

    print("✅ Batch processing complete\n")


def example_fourierTransformer_pattern():
    """Example 3: Following fourierTransformer.m memory management pattern."""
    print("Example 3: fourierTransformer Pattern")
    print("-" * 40)

    class ImageProcessor:
        """
        Example class following fourierTransformer.m pattern.

        Manages persistent PaddedArray instances.
        """

        def __init__(self, method="CPU"):
            self.method = method
            self.padder = None
            self.is_initialized = False

        def initialize_for_size(self, input_shape, pad_low, pad_top):
            """Initialize padder for specific dimensions."""
            img_shape = np.array(input_shape)
            if len(img_shape) == 2:
                img_shape = np.array([*img_shape, 1])

            output_shape = tuple(img_shape + np.array(pad_low) + np.array(pad_top))

            self.padder = PaddedArray(
                input_shape=input_shape,
                output_shape=output_shape,
                method=self.method,
                precision="single",
                use_once=False,
            )
            self.is_initialized = True
            print(f"Initialized processor for {input_shape} -> {output_shape}")

        def process_image(self, image, pad_low, pad_top, zero_first=True):
            """Process image with padding."""
            if not self.is_initialized:
                raise RuntimeError("Processor not initialized")

            if zero_first:
                self.padder.zero_stored_array()

            return self.padder.pad_image(image, pad_low, pad_top)

        def get_stored_reference(self):
            """Get reference to stored array (like fourierTransformer)."""
            if not self.is_initialized:
                raise RuntimeError("Processor not initialized")
            return self.padder.get_stored_array_reference()

        def to_cpu(self):
            """Move to CPU (like fourierTransformer)."""
            if self.padder is not None:
                self.padder.to_cpu()
                self.method = "CPU"

        def to_gpu(self):
            """Move to GPU (like fourierTransformer)."""
            if self.padder is not None:
                self.padder.to_gpu()
                self.method = "GPU"

    # Use the processor
    processor = ImageProcessor(method="GPU" if HAS_CUPY else "CPU")

    # Initialize for specific size
    processor.initialize_for_size(
        input_shape=(64, 64, 32), pad_low=[16, 16, 8], pad_top=[16, 16, 8]
    )

    # Process multiple images
    for i in range(3):
        image = np.random.rand(64, 64, 32).astype(np.float32)
        result = processor.process_image(
            image, pad_low=[16, 16, 8], pad_top=[16, 16, 8], zero_first=(i > 0)
        )
        print(f"Processed image {i + 1}: {result.shape}")

    # Get reference to work with stored array directly
    stored_ref = processor.get_stored_reference()
    print(f"Direct access to stored array: {stored_ref.shape}")

    # Test CPU/GPU switching
    if HAS_CUPY:
        print("Moving to CPU...")
        processor.to_cpu()
        print(f"Now on: {processor.method}")

    print("✅ fourierTransformer pattern complete\n")


def example_advanced_usage():
    """Example 4: Advanced usage with different modes."""
    print("Example 4: Advanced Usage")
    print("-" * 40)

    image = np.random.rand(32, 32, 16).astype(np.float32)

    # Example: Processing with different extrapolation modes
    modes = [
        ("zeros", None),
        ("constant", 0.5),
        ("random", "random"),
    ]

    for mode_name, extrap_val in modes:
        padder = PaddedArray(
            method="CPU",  # Use CPU for consistency
            precision="single",
            use_once=True,
            extrap_val=extrap_val,
        )

        result = padder.pad_image(image=image, pad_low=[8, 8, 4], pad_top=[8, 8, 4])

        # Check padding region
        padding_region = result[:8, :8, :4]
        mean_val = np.mean(padding_region)

        print(f"{mode_name:8s}: padding mean = {mean_val:.3f}")

    # Example: Fourier oversampling mode
    padder = PaddedArray(method="CPU", precision="single", use_once=True)
    result = padder.pad_image(
        image=image,
        pad_low=[16, 16, 8],
        pad_top=[16, 16, 8],
        fourier_oversample=True,  # Centers image instead of offset padding
    )
    print(f"Fourier:  centered in {result.shape}")

    # Example: Configuration updates
    padder = PaddedArray(
        input_shape=(32, 32, 16),
        output_shape=(64, 64, 32),
        method="CPU",
        precision="single",
        use_once=False,
    )

    print(f"Initial: {padder.get_memory_info()['array_size_mb']:.1f}MB")

    # Update to larger size
    padder.update_config(output_shape=(128, 128, 64), precision="double")

    print(f"Updated: {padder.get_memory_info()['array_size_mb']:.1f}MB")
    print("✅ Advanced usage complete\n")


def main():
    """Run all usage examples."""
    print("🔬 PaddedArray Usage Examples")
    print("=" * 50)
    print("Demonstrating fourierTransformer.m-style usage patterns")
    print(f"GPU available: {HAS_CUPY}\n")

    example_single_image_processing()
    example_batch_processing()
    example_fourierTransformer_pattern()
    example_advanced_usage()

    print("📝 Key Takeaways:")
    print("• Use use_once=True for single operations")
    print("• Use use_once=False for repeated operations")
    print("• Always zero_stored_array() before reuse")
    print("• get_stored_array_reference() for direct access")
    print("• to_cpu()/to_gpu() for memory management")
    print("• update_config() for changing dimensions")
    print("\n🎯 Perfect for emClarity batch processing workflows!")


if __name__ == "__main__":
    main()
