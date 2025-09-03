"""
emClarity 3D padding functions with GPU support via CuPy

This module provides padding functionality for 3D image volumes with options for:
- CPU and GPU computation
- Different padding modes (zeros, random noise, tapering)
- Fourier oversampling support
- Trimming and padding combinations

Original MATLAB equivalent: masking/BH_padZeros3d.m
"""

import logging
import warnings
from typing import Any, Literal, Optional, Tuple, Union

import numpy as np

# Try to import CuPy for GPU support
try:
    import cupy as cp

    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False
    cp = None

logger = logging.getLogger(__name__)


def emc_pad_zeros_3d(
    image: Union[np.ndarray, Any],
    pad_low: Union[np.ndarray, Tuple, str],
    pad_top: Optional[Union[np.ndarray, Tuple]] = None,
    method: Literal["GPU", "CPU"] = "CPU",
    precision: Literal["single", "double", "singleTaper", "doubleTaper"] = "single",
    extrap_val: Optional[float] = None,
    fourier_oversample: bool = False,
) -> Union[np.ndarray, Any]:
    """
    Pad a 3D image volume with zeros or other values.

    This function provides efficient padding by allocating the full output
    matrix once, which is faster than using multiple padding operations.

    Args:
        image: 3D image array to be padded
        pad_low: Padding amounts for the beginning of each dimension, or mode string
                 - If numeric: [pad_x_low, pad_y_low, pad_z_low]
                 - If 'fwd': use pad_top[0,:]
                 - If 'inv': use pad_top[2,:]
        pad_top: Padding amounts for the end of each dimension OR padding array for modes
                 - If pad_low is numeric: [pad_x_top, pad_y_top, pad_z_top]
                 - If pad_low is 'fwd'/'inv': array with padding specifications
        method: Computation method - "GPU" for GPU acceleration, "CPU" for CPU
        precision: Data precision and optional tapering
                   - "single": 32-bit float
                   - "double": 64-bit float
                   - "singleTaper": 32-bit with edge tapering
                   - "doubleTaper": 64-bit with edge tapering
        extrap_val: Value for padding (0 for zeros, number for constant, 'random' for noise)
        fourier_oversample: Whether to use Fourier oversampling mode

    Returns:
        Padded image array (numpy array or CuPy array depending on method)

    Raises:
        ValueError: If parameters are invalid
        RuntimeError: If GPU method requested but CuPy not available
    """

    # Validate GPU availability
    if method == "GPU" and not HAS_CUPY:
        raise RuntimeError(
            "GPU method requested but CuPy is not available. "
            "Please install CuPy or use method='CPU'"
        )

    # Parse padding specifications
    pad_low_vals, pad_top_vals = _parse_padding_args(pad_low, pad_top)

    # Handle 2D vs 3D images
    is_2d = len(image.shape) == 2
    original_is_2d = is_2d

    if is_2d:
        # Convert 2D to 3D with singleton dimension for processing
        if len(pad_low_vals) == 2:
            pad_low_vals = np.array([*pad_low_vals, 0])
            pad_top_vals = np.array([*pad_top_vals, 0])
        # Don't modify the image shape yet - keep it 2D for now

    # Parse precision and tapering
    use_taper, dtype = _parse_precision(precision)

    # Handle negative padding (trimming)
    trim_low = np.abs(pad_low_vals * (pad_low_vals < 0)).astype(int)
    trim_top = np.abs(pad_top_vals * (pad_top_vals < 0)).astype(int)

    if np.any(trim_low > 0) or np.any(trim_top > 0):
        # Apply trimming
        img_shape = np.array(image.shape)

        # Calculate slice indices, ensuring we don't exceed image bounds
        start_idx = np.minimum(trim_low, img_shape - 1)
        end_idx = img_shape - np.minimum(trim_top, img_shape - 1)
        end_idx = np.maximum(end_idx, start_idx + 1)  # Ensure valid slice

        if len(image.shape) == 3:
            image = image[
                start_idx[0] : end_idx[0],
                start_idx[1] : end_idx[1],
                start_idx[2] : end_idx[2],
            ]
        else:
            image = image[start_idx[0] : end_idx[0], start_idx[1] : end_idx[1]]

    # Update padding values after trimming (remove negative components)
    pad_low_vals = np.maximum(pad_low_vals, 0)
    pad_top_vals = np.maximum(pad_top_vals, 0)

    # Get image dimensions
    if is_2d:
        img_shape = np.array([*image.shape, 1])  # Add singleton Z dimension
    else:
        img_shape = np.array(image.shape)
    pad_shape = tuple(img_shape + pad_low_vals + pad_top_vals)

    # Handle extrapolation value
    do_random, extrap_mean, extrap_std = _parse_extrap_value(extrap_val, image)

    # Create padded array
    padded_img = _create_padded_array(
        pad_shape, method, dtype, do_random, extrap_mean, extrap_std
    )

    # Apply constant extrapolation if needed
    if extrap_val is not None and not do_random and extrap_val != 0:
        padded_img += extrap_val

    # Apply tapering if requested
    if use_taper:
        image = _apply_tapering(
            image, extrap_val if extrap_val is not None else 0, is_2d
        )

    # Place original image in padded array
    if fourier_oversample:
        _apply_fourier_oversampling(padded_img, image, is_2d)
    else:
        _place_image_standard(padded_img, image, pad_low_vals, pad_top_vals, is_2d)

    # Convert back to 2D if input was 2D
    if original_is_2d:
        padded_img = padded_img[:, :, 0]

    return padded_img


def _parse_padding_args(pad_low, pad_top):
    """Parse padding arguments into low/high values."""
    if isinstance(pad_low, str):
        if pad_low.lower() == "fwd":
            if pad_top is None or len(pad_top) < 2:
                raise ValueError("For 'fwd' mode, pad_top must have at least 2 rows")
            return np.array(pad_top[0]), np.array(pad_top[1])
        elif pad_low.lower() == "inv":
            if pad_top is None or len(pad_top) < 4:
                raise ValueError("For 'inv' mode, pad_top must have at least 4 rows")
            return np.array(pad_top[2]), np.array(pad_top[3])
        else:
            raise ValueError("pad_low string must be 'fwd' or 'inv'")
    else:
        # Numeric padding
        if pad_top is None:
            raise ValueError("When pad_low is numeric, pad_top must be provided")
        return np.array(pad_low), np.array(pad_top)


def _parse_precision(precision):
    """Parse precision string into taper flag and dtype."""
    if precision.lower() in ["singletaper", "doubletaper"]:
        use_taper = True
        dtype = np.float32 if "single" in precision.lower() else np.float64
    else:
        use_taper = False
        dtype = np.float32 if precision.lower() == "single" else np.float64

    return use_taper, dtype


def _parse_extrap_value(extrap_val, image):
    """Parse extrapolation value into random flag and parameters."""
    if extrap_val is None:
        return False, 0.0, 0.0
    elif extrap_val == "random":
        return True, float(np.mean(image)), float(np.std(image))
    elif isinstance(extrap_val, str) and extrap_val.lower() == "random":
        return True, float(np.mean(image)), float(np.std(image))
    else:
        return False, 0.0, 0.0


def _create_padded_array(shape, method, dtype, do_random, mean_val, std_val):
    """Create the padded array with appropriate backend."""
    if method == "GPU":
        if do_random:
            padded = cp.random.randn(*shape, dtype=dtype) * std_val + mean_val
        else:
            padded = cp.zeros(shape, dtype=dtype)
    else:
        if do_random:
            padded = np.random.randn(*shape).astype(dtype) * std_val + mean_val
        else:
            padded = np.zeros(shape, dtype=dtype)

    return padded


def _apply_tapering(image, extrap_val, is_2d):
    """Apply edge tapering using cosine window."""
    # Create 7-point cosine taper: 0.5 + 0.5*cos(π*i/6) for i=0..6
    taper = 0.5 + 0.5 * np.cos(np.pi * np.arange(7) / 6)
    inv_taper = 1 - taper

    # Get image dimensions
    d1, d2 = image.shape[:2]
    d3 = 1 if is_2d else image.shape[2]

    # Apply tapering to all edges
    if len(image.shape) == 3 or not is_2d:
        # 3D tapering
        # X dimension edges
        image[:7, :, :] = (
            image[:7, :, :] * taper[:, None, None]
            + extrap_val * inv_taper[:, None, None]
        )
        image[-7:, :, :] = (
            image[-7:, :, :] * taper[::-1, None, None]
            + extrap_val * inv_taper[::-1, None, None]
        )

        # Y dimension edges
        image[:, :7, :] = (
            image[:, :7, :] * taper[None, :, None]
            + extrap_val * inv_taper[None, :, None]
        )
        image[:, -7:, :] = (
            image[:, -7:, :] * taper[None, ::-1, None]
            + extrap_val * inv_taper[None, ::-1, None]
        )

        # Z dimension edges (if 3D)
        if not is_2d and image.shape[2] > 7:
            image[:, :, :7] = (
                image[:, :, :7] * taper[None, None, :]
                + extrap_val * inv_taper[None, None, :]
            )
            image[:, :, -7:] = (
                image[:, :, -7:] * taper[None, None, ::-1]
                + extrap_val * inv_taper[None, None, ::-1]
            )
    else:
        # 2D tapering
        image[:7, :] = image[:7, :] * taper[:, None] + extrap_val * inv_taper[:, None]
        image[-7:, :] = (
            image[-7:, :] * taper[::-1, None] + extrap_val * inv_taper[::-1, None]
        )
        image[:, :7] = image[:, :7] * taper[None, :] + extrap_val * inv_taper[None, :]
        image[:, -7:] = (
            image[:, -7:] * taper[None, ::-1] + extrap_val * inv_taper[None, ::-1]
        )

    return image


def _apply_fourier_oversampling(padded_img, image, is_2d):
    """Apply Fourier oversampling placement (splits DC component)."""
    img_shape = image.shape

    if is_2d:
        # 2D Fourier oversampling
        sx1 = (img_shape[0] + 1) // 2
        sx2 = img_shape[0] - sx1 - 1
        sy1 = (img_shape[1] + 1) // 2
        sy2 = img_shape[1] - sy1 - 1

        # Place the four quadrants
        padded_img[:sx1, :sy1] = image[:sx1, :sy1]
        padded_img[-sx2:, :sy1] = image[-sx2:, :sy1]
        padded_img[:sx1, -sy2:] = image[:sx1, -sy2:]
        padded_img[-sx2:, -sy2:] = image[-sx2:, -sy2:]
    else:
        # 3D Fourier oversampling
        sx1 = (img_shape[0] + 1) // 2
        sx2 = img_shape[0] - sx1 - 1
        sy1 = (img_shape[1] + 1) // 2
        sy2 = img_shape[1] - sy1 - 1
        sz1 = (img_shape[2] + 1) // 2
        sz2 = img_shape[2] - sz1 - 1

        # Place all eight octants
        padded_img[:sx1, :sy1, :sz1] = image[:sx1, :sy1, :sz1]
        padded_img[-sx2:, :sy1, :sz1] = image[-sx2:, :sy1, :sz1]
        padded_img[:sx1, -sy2:, :sz1] = image[:sx1, -sy2:, :sz1]
        padded_img[-sx2:, -sy2:, :sz1] = image[-sx2:, -sy2:, :sz1]
        padded_img[:sx1, :sy1, -sz2:] = image[:sx1, :sy1, -sz2:]
        padded_img[-sx2:, :sy1, -sz2:] = image[-sx2:, :sy1, -sz2:]
        padded_img[:sx1, -sy2:, -sz2:] = image[:sx1, -sy2:, -sz2:]
        padded_img[-sx2:, -sy2:, -sz2:] = image[-sx2:, -sy2:, -sz2:]


def _place_image_standard(padded_img, image, pad_low, pad_top, is_2d):
    """Place image in padded array using standard padding."""
    pad_shape = padded_img.shape

    if is_2d:
        # For 2D images, place directly in the 2D slice of 3D padded array
        padded_img[
            pad_low[0] : pad_shape[0] - pad_top[0],
            pad_low[1] : pad_shape[1] - pad_top[1],
            0,  # Place in first Z slice
        ] = image
    else:
        padded_img[
            pad_low[0] : pad_shape[0] - pad_top[0],
            pad_low[1] : pad_shape[1] - pad_top[1],
            pad_low[2] : pad_shape[2] - pad_top[2],
        ] = image


# Convenience function matching MATLAB interface more closely
def BH_padZeros3d(IMAGE, PADLOW, PADTOP, METHOD="CPU", PRECISION="single", *varargin):
    """
    MATLAB-compatible interface for padding function.

    Args:
        IMAGE: 3D image array
        PADLOW: Low padding values or mode string
        PADTOP: High padding values or padding array
        METHOD: 'GPU' or 'CPU' (default: 'CPU')
        PRECISION: 'single', 'double', 'singleTaper', 'doubleTaper'
        *varargin: Additional arguments (extrap_val, fourier_oversample)

    Returns:
        Padded image array
    """
    # Parse optional arguments
    extrap_val = None
    fourier_oversample = False

    if len(varargin) > 0:
        if isinstance(varargin[0], (int, float)):
            extrap_val = varargin[0]
        elif isinstance(varargin[0], str) and varargin[0].lower() == "random":
            extrap_val = "random"

        if len(varargin) > 1:
            extrap_val = 0  # Reset for Fourier oversampling
            fourier_oversample = True

    return emc_pad_zeros_3d(
        image=IMAGE,
        pad_low=PADLOW,
        pad_top=PADTOP,
        method=METHOD,
        precision=PRECISION,
        extrap_val=extrap_val,
        fourier_oversample=fourier_oversample,
    )
