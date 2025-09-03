# emClarity Python masking Module

This directory contains Python conversions of emClarity's image masking and padding functionality, originally found in the MATLAB `masking/` directory.

## Purpose

The masking module handles image padding, masking operations, and related image processing tasks for emClarity workflows.

## Modules

### emc_pad_zeros_3d.py

**Original MATLAB equivalent**: `masking/BH_padZeros3d.m`

Provides efficient 3D (and 2D) image padding with GPU acceleration via CuPy.

#### Key Features:
- **GPU acceleration**: Optional CuPy support for high-performance GPU computation
- **Flexible padding modes**: Zero padding, constant values, random noise
- **Edge tapering**: Cosine-windowed edge tapering to reduce artifacts
- **Trimming support**: Negative padding values for image trimming
- **Fourier oversampling**: Special mode for frequency domain operations
- **2D/3D compatibility**: Handles both 2D and 3D image arrays
- **Multiple precisions**: Single and double precision support

#### Usage:

```python
from emc_pad_zeros_3d import emc_pad_zeros_3d, BH_padZeros3d
import numpy as np

# Basic 3D padding
image = np.random.randn(64, 64, 32).astype(np.float32)
padded = emc_pad_zeros_3d(
    image,
    pad_low=[10, 10, 5],    # Padding at start of each dimension
    pad_top=[10, 10, 5],    # Padding at end of each dimension
    method="CPU",           # or "GPU" if CuPy available
    precision="single"      # or "double"
)

# GPU-accelerated padding (requires CuPy)
gpu_padded = emc_pad_zeros_3d(
    image,
    pad_low=[8, 8, 4],
    pad_top=[8, 8, 4], 
    method="GPU",
    precision="single"
)

# Padding with constant value
const_padded = emc_pad_zeros_3d(
    image,
    pad_low=[5, 5, 2],
    pad_top=[5, 5, 2],
    extrap_val=1.5  # Pad with constant value
)

# Padding with random noise matching image statistics
noise_padded = emc_pad_zeros_3d(
    image,
    pad_low=[5, 5, 2],
    pad_top=[5, 5, 2],
    extrap_val='random'  # Pad with noise
)

# Edge tapering to reduce artifacts
tapered = emc_pad_zeros_3d(
    image,
    pad_low=[10, 10, 5],
    pad_top=[10, 10, 5],
    precision="singleTaper"  # Apply cosine tapering
)

# Trimming (negative padding)
trimmed = emc_pad_zeros_3d(
    image,
    pad_low=[-5, -5, -2],   # Trim from beginning
    pad_top=[0, 0, 0]       # No padding at end
)

# MATLAB-compatible interface
matlab_result = BH_padZeros3d(
    image,
    [10, 10, 5],    # PADLOW
    [10, 10, 5],    # PADTOP  
    'CPU',          # METHOD
    'single'        # PRECISION
)
```

#### Advanced Features:

**Forward/Inverse Modes:**
```python
# Create padding specification array
pad_specs = np.array([
    [2, 4, 1],  # Forward low padding
    [4, 2, 3],  # Forward high padding
    [1, 1, 2],  # Inverse low padding
    [3, 3, 1]   # Inverse high padding
])

# Forward mode
fwd_padded = emc_pad_zeros_3d(image, 'fwd', pad_specs)

# Inverse mode  
inv_padded = emc_pad_zeros_3d(image, 'inv', pad_specs)
```

**Fourier Oversampling:**
```python
# Special mode for frequency domain operations
fourier_padded = emc_pad_zeros_3d(
    image,
    pad_low=[32, 32, 16],
    pad_top=[32, 32, 16],
    fourier_oversample=True
)
```

#### Performance Considerations:

- **Memory allocation**: Uses single allocation approach for better performance than multiple padding operations
- **GPU memory**: CuPy arrays remain on GPU to avoid transfer overhead
- **Data types**: Use `single` precision for memory efficiency unless `double` precision required
- **Large volumes**: GPU acceleration most beneficial for volumes > 128³

## Testing

Unit tests are located in `tests/test_emc_pad_zeros_3d.py`. Run tests with:

```bash
cd masking/tests
python test_emc_pad_zeros_3d.py
```

Tests include:
- Basic 2D and 3D padding functionality
- GPU vs CPU consistency (when CuPy available)
- Different precision modes and data types
- Edge cases (trimming, constant padding, random padding)
- MRC file I/O integration
- MATLAB compatibility interface
- Round-trip testing with real image data

## Dependencies

### Required:
- `numpy` - Core array operations
- `mrcfile` - MRC file I/O (for testing)

### Optional:
- `cupy` - GPU acceleration (highly recommended for large volumes)

## GPU Support

GPU acceleration is automatically available when CuPy is installed:

```bash
# Install CuPy (requires CUDA)
pip install cupy-cuda11x  # For CUDA 11.x
# or
pip install cupy-cuda12x  # For CUDA 12.x
```

GPU operations maintain the same interface but return CuPy arrays. Use `cp.asnumpy()` to convert back to NumPy arrays when needed.

## File Format Compatibility

The module integrates seamlessly with MRC file format through the `mrcfile` package:

```python
import mrcfile
from emc_pad_zeros_3d import emc_pad_zeros_3d

# Read MRC file
with mrcfile.open('input.mrc', mode='r') as mrc:
    volume = mrc.data.copy()

# Apply padding
padded_volume = emc_pad_zeros_3d(
    volume,
    pad_low=[20, 20, 10],
    pad_top=[20, 20, 10]
)

# Save result
with mrcfile.new('padded_output.mrc', overwrite=True) as mrc:
    mrc.set_data(padded_volume.astype(np.float32))
```

## Algorithm Details

The padding implementation follows these steps:

1. **Parse parameters**: Handle different input modes (numeric, 'fwd', 'inv')
2. **Apply trimming**: Process negative padding values first
3. **Allocate output**: Single allocation for efficiency
4. **Apply tapering**: Optional edge windowing using cosine function
5. **Place image**: Standard or Fourier oversampling placement
6. **Handle formats**: Convert between 2D/3D as needed

The tapering uses a 7-point cosine window: `0.5 + 0.5*cos(π*i/6)` for i=0..6.

## Future Development

Planned enhancements:
- Additional padding modes (reflection, wrap)
- Optimized kernels for common operations
- Integration with other masking operations
- Memory usage optimizations for very large volumes
