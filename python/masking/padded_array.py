"""
PaddedArray class for efficient 3D image padding with GPU support

This module provides a class-based approach to padding operations that allows
for memory reuse and efficient GPU processing. Inspired by fourierTransformer.m
pattern for managing persistent GPU arrays and operations.

Author: emClarity Python Conversion
Date: September 2025
"""

import numpy as np
import warnings
from typing import Union, Tuple, Optional, Literal, Any, Dict
import logging
from pathlib import Path

# Try to import CuPy for GPU support
try:
    import cupy as cp
    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False
    cp = None

logger = logging.getLogger(__name__)


class PaddedArray:
    """
    Manages padded arrays with efficient memory reuse for 3D image processing.
    
    This class follows the pattern established by fourierTransformer.m:
    - Manages persistent GPU/CPU arrays
    - Allows for efficient reuse across multiple operations
    - Provides methods to zero out and access stored arrays
    - Handles different padding modes and precision types
    
    Key features:
    - Optional single-use mode for one-off operations
    - Persistent storage for repeated operations with same dimensions
    - GPU/CPU backend support
    - Multiple padding modes (zeros, random, tapering)
    - Memory-efficient array management
    """
    
    def __init__(
        self,
        input_shape: Optional[Tuple[int, ...]] = None,
        output_shape: Optional[Tuple[int, ...]] = None,
        method: Literal["GPU", "CPU"] = "CPU",
        precision: Literal["single", "double", "singleTaper", "doubleTaper"] = "single",
        use_once: bool = False,
        extrap_val: Optional[Union[float, str]] = None
    ):
        """
        Initialize PaddedArray for efficient padding operations.
        
        Args:
            input_shape: Expected input array dimensions (nz, ny, nx)
            output_shape: Expected output array dimensions (nz, ny, nx)
            method: Processing backend - 'GPU' or 'CPU'
            precision: Data precision and taper mode
            use_once: If True, optimize for single use (don't store arrays)
            extrap_val: Extrapolation value for padding (number, 'random', or None)
        """
        # Validate GPU availability
        if method == "GPU" and not HAS_CUPY:
            warnings.warn("CuPy not available, falling back to CPU")
            method = "CPU"
        
        # Store configuration
        self.method = method
        self.precision = precision
        self.use_once = use_once
        self.extrap_val = extrap_val
        
        # Parse precision settings
        self.use_taper = precision.lower() in ['singletaper', 'doubletaper']
        self.dtype = np.float32 if 'single' in precision.lower() else np.float64
        
        # Storage for persistent arrays
        self.input_shape = input_shape
        self.output_shape = output_shape
        self._stored_array = None
        self._array_is_initialized = False
        self._array_needs_zeroing = True
        
        # Padding configuration
        self._current_pad_config = None
        self._extrap_params = {'do_random': False, 'mean': 0.0, 'std': 0.0}
        
        # Initialize persistent array if dimensions provided
        if not use_once and input_shape is not None and output_shape is not None:
            self._initialize_stored_array()
    
    def _initialize_stored_array(self):
        """Initialize the persistent padded array storage."""
        if self.output_shape is None:
            raise ValueError("Cannot initialize storage without output_shape")
        
        # Create array with appropriate backend
        if self.method == "GPU":
            self._stored_array = cp.zeros(self.output_shape, dtype=self.dtype)
        else:
            self._stored_array = np.zeros(self.output_shape, dtype=self.dtype)
        
        self._array_is_initialized = True
        self._array_needs_zeroing = False
        
        logger.debug(f"Initialized {self.method} padded array with shape {self.output_shape}")
    
    def zero_stored_array(self):
        """Zero out the stored padded array."""
        if not self._array_is_initialized:
            raise RuntimeError("Stored array not initialized")
        
        if self.method == "GPU":
            self._stored_array.fill(0)
        else:
            self._stored_array.fill(0)
        
        self._array_needs_zeroing = False
        logger.debug("Zeroed stored padded array")
    
    def get_stored_array_reference(self):
        """
        Get a reference to the stored padded array.
        
        WARNING: The returned reference must be kept alive by the caller.
        The array remains valid as long as this PaddedArray instance exists
        and zero_stored_array() is not called.
        
        Returns:
            Reference to the stored padded array
        """
        if not self._array_is_initialized:
            raise RuntimeError("Stored array not initialized")
        
        return self._stored_array
    
    def pad_image(
        self,
        image: Union[np.ndarray, Any],
        pad_low: Union[np.ndarray, Tuple, str],
        pad_top: Optional[Union[np.ndarray, Tuple]] = None,
        fourier_oversample: bool = False,
        force_new_array: bool = False
    ) -> Union[np.ndarray, Any]:
        """
        Pad an image using the configured settings.
        
        Args:
            image: Input image to pad
            pad_low: Low padding values or mode string ('fwd', 'inv')
            pad_top: High padding values or padding configuration array
            fourier_oversample: Use Fourier-space oversampling
            force_new_array: Create new array even if using persistent storage
            
        Returns:
            Padded image array
        """
        # Parse input image
        original_is_gpu = False
        if self.method == "GPU":
            if not isinstance(image, cp.ndarray):
                image = cp.asarray(image, dtype=self.dtype)
            else:
                image = image.astype(self.dtype)
            original_is_gpu = True
        else:
            if isinstance(image, cp.ndarray):
                image = cp.asnumpy(image)
            image = np.asarray(image, dtype=self.dtype)
        
        # Parse padding arguments
        pad_low_vals, pad_top_vals = self._parse_padding_args(pad_low, pad_top)
        
        # Handle negative padding (trimming)
        image, pad_low_vals, pad_top_vals = self._apply_trimming(
            image, pad_low_vals, pad_top_vals
        )
        
        # Calculate output shape
        img_shape = np.array(image.shape)
        if len(img_shape) == 2:
            img_shape = np.array([*img_shape, 1])  # Add Z dimension
            is_2d = True
            original_is_2d = True
        else:
            is_2d = False
            original_is_2d = False
        
        output_shape = tuple(img_shape + pad_low_vals + pad_top_vals)
        
        # Decide whether to use stored array or create new one
        use_stored = (
            not self.use_once and 
            not force_new_array and
            self._array_is_initialized and
            self.output_shape == output_shape
        )
        
        if use_stored:
            # Use persistent storage
            if self._array_needs_zeroing:
                self.zero_stored_array()
            padded_img = self._stored_array
        else:
            # Create new array
            padded_img = self._create_new_padded_array(output_shape, image)
        
        # Apply padding operations
        self._apply_padding_operations(
            padded_img, image, pad_low_vals, pad_top_vals, 
            fourier_oversample, is_2d
        )
        
        # Mark that array needs zeroing for next use if using stored array
        if use_stored:
            self._array_needs_zeroing = True
        
        # Convert back to 2D if needed
        if original_is_2d and len(padded_img.shape) == 3:
            padded_img = padded_img[:, :, 0]
        
        return padded_img
    
    def _create_new_padded_array(self, shape: Tuple[int, ...], image=None):
        """Create a new padded array with the specified shape."""
        # Parse extrapolation parameters
        self._update_extrap_params(image)
        
        if self.method == "GPU":
            if self._extrap_params['do_random']:
                # Create random array
                padded_img = cp.random.normal(
                    self._extrap_params['mean'],
                    self._extrap_params['std'],
                    shape
                ).astype(self.dtype)
            else:
                # Create zeros array
                padded_img = cp.zeros(shape, dtype=self.dtype)
                if self.extrap_val is not None and self.extrap_val != 0:
                    padded_img += self.extrap_val
        else:
            if self._extrap_params['do_random']:
                # Create random array
                padded_img = np.random.normal(
                    self._extrap_params['mean'],
                    self._extrap_params['std'],
                    shape
                ).astype(self.dtype)
            else:
                # Create zeros array
                padded_img = np.zeros(shape, dtype=self.dtype)
                if self.extrap_val is not None and self.extrap_val != 0:
                    padded_img += self.extrap_val
        
        return padded_img
    
    def _apply_padding_operations(
        self, 
        padded_img, 
        image, 
        pad_low_vals, 
        pad_top_vals, 
        fourier_oversample, 
        is_2d
    ):
        """Apply the actual padding operations to place image in padded array."""
        # Apply tapering if needed
        if self.use_taper:
            extrap_val_for_taper = self.extrap_val if self.extrap_val is not None else 0
            image = self._apply_tapering(image, extrap_val_for_taper, is_2d)
        
        # Place image in padded array
        if fourier_oversample:
            self._apply_fourier_oversampling(padded_img, image, is_2d)
        else:
            self._place_image_standard(padded_img, image, pad_low_vals, pad_top_vals, is_2d)
    
    def _parse_padding_args(self, pad_low, pad_top):
        """Parse padding arguments into low/high values."""
        if isinstance(pad_low, str):
            if pad_low.lower() == 'fwd':
                if pad_top is None or len(pad_top) < 2:
                    raise ValueError("For 'fwd' mode, pad_top must have at least 2 rows")
                return np.array(pad_top[0]), np.array(pad_top[1])
            elif pad_low.lower() == 'inv':
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
    
    def _apply_trimming(self, image, pad_low_vals, pad_top_vals):
        """Handle negative padding values by trimming the image."""
        # Calculate trimming amounts (negative padding)
        trim_low = np.maximum(-pad_low_vals, 0)
        trim_top = np.maximum(-pad_top_vals, 0)
        
        # Apply trimming if needed
        if np.any(trim_low > 0) or np.any(trim_top > 0):
            img_shape = np.array(image.shape)
            
            # Calculate slice indices
            start_idx = np.minimum(trim_low, img_shape - 1)
            end_idx = img_shape - np.minimum(trim_top, img_shape - 1)
            end_idx = np.maximum(end_idx, start_idx + 1)  # Ensure valid slice
            
            if len(image.shape) == 3:
                image = image[
                    start_idx[0]:end_idx[0],
                    start_idx[1]:end_idx[1], 
                    start_idx[2]:end_idx[2]
                ]
            else:
                image = image[start_idx[0]:end_idx[0], start_idx[1]:end_idx[1]]
        
        # Update padding values after trimming
        pad_low_vals = np.maximum(pad_low_vals, 0)
        pad_top_vals = np.maximum(pad_top_vals, 0)
        
        return image, pad_low_vals, pad_top_vals
    
    def _update_extrap_params(self, image=None):
        """Update extrapolation parameters based on current settings."""
        if self.extrap_val is None:
            self._extrap_params = {'do_random': False, 'mean': 0.0, 'std': 0.0}
        elif isinstance(self.extrap_val, str) and self.extrap_val.lower() == 'random':
            # Random extrapolation - use image statistics if available
            if image is not None:
                if hasattr(image, 'get'):  # CuPy array
                    img_cpu = image.get()
                else:
                    img_cpu = image
                mean_val = float(np.mean(img_cpu))
                std_val = float(np.std(img_cpu))
            else:
                mean_val = 0.0
                std_val = 1.0
            self._extrap_params = {'do_random': True, 'mean': mean_val, 'std': std_val}
        else:
            self._extrap_params = {'do_random': False, 'mean': 0.0, 'std': 0.0}
    
    def _apply_tapering(self, image, extrap_val, is_2d):
        """Apply tapering to image edges (placeholder - needs full implementation)."""
        # TODO: Implement full tapering logic from original MATLAB
        logger.warning("Tapering not fully implemented yet")
        return image
    
    def _apply_fourier_oversampling(self, padded_img, image, is_2d):
        """Apply Fourier oversampling padding (placeholder - needs full implementation)."""
        # TODO: Implement full Fourier oversampling logic
        logger.warning("Fourier oversampling not fully implemented yet")
        # For now, just center the image
        self._place_image_center(padded_img, image, is_2d)
    
    def _place_image_standard(self, padded_img, image, pad_low, pad_top, is_2d):
        """Place image in padded array using standard padding."""
        if is_2d:
            # For 2D images, we need to handle the expanded Z dimension
            if len(image.shape) == 2:
                padded_img[
                    pad_low[0]:padded_img.shape[0] - pad_top[0],
                    pad_low[1]:padded_img.shape[1] - pad_top[1],
                    0  # Place in first Z slice
                ] = image
            else:
                # Image already has Z dimension
                padded_img[
                    pad_low[0]:padded_img.shape[0] - pad_top[0],
                    pad_low[1]:padded_img.shape[1] - pad_top[1],
                    pad_low[2]:padded_img.shape[2] - pad_top[2]
                ] = image
        else:
            padded_img[
                pad_low[0]:padded_img.shape[0] - pad_top[0],
                pad_low[1]:padded_img.shape[1] - pad_top[1], 
                pad_low[2]:padded_img.shape[2] - pad_top[2]
            ] = image
    
    def _place_image_center(self, padded_img, image, is_2d):
        """Center image in padded array."""
        pad_shape = np.array(padded_img.shape)
        img_shape = np.array(image.shape)
        
        if is_2d:
            img_shape = np.array([*img_shape, 1])
        
        # Calculate centering offsets
        start_idx = (pad_shape - img_shape) // 2
        end_idx = start_idx + img_shape
        
        if is_2d:
            padded_img[
                start_idx[0]:end_idx[0],
                start_idx[1]:end_idx[1],
                0
            ] = image
        else:
            padded_img[
                start_idx[0]:end_idx[0],
                start_idx[1]:end_idx[1],
                start_idx[2]:end_idx[2]
            ] = image
    
    def update_config(
        self,
        input_shape: Optional[Tuple[int, ...]] = None,
        output_shape: Optional[Tuple[int, ...]] = None,
        method: Optional[str] = None,
        precision: Optional[str] = None,
        extrap_val: Optional[Union[float, str]] = None
    ):
        """
        Update configuration parameters. May trigger reallocation of stored array.
        
        Args:
            input_shape: New input shape
            output_shape: New output shape  
            method: New processing method
            precision: New precision setting
            extrap_val: New extrapolation value
        """
        needs_reallocation = False
        
        if method is not None and method != self.method:
            self.method = method
            needs_reallocation = True
        
        if precision is not None and precision != self.precision:
            self.precision = precision
            self.use_taper = precision.lower() in ['singletaper', 'doubletaper']
            old_dtype = self.dtype
            self.dtype = np.float32 if 'single' in precision.lower() else np.float64
            if old_dtype != self.dtype:
                needs_reallocation = True
        
        if output_shape is not None and output_shape != self.output_shape:
            self.output_shape = output_shape
            needs_reallocation = True
        
        if input_shape is not None:
            self.input_shape = input_shape
        
        if extrap_val is not None:
            self.extrap_val = extrap_val
        
        # Reallocate stored array if needed
        if needs_reallocation and not self.use_once and self.output_shape is not None:
            self._stored_array = None
            self._array_is_initialized = False
            self._initialize_stored_array()
    
    def to_cpu(self):
        """Move stored arrays to CPU memory (like fourierTransformer)."""
        if self._array_is_initialized and self.method == "GPU":
            if hasattr(self._stored_array, 'get'):
                self._stored_array = self._stored_array.get()
            self.method = "CPU"
            logger.debug("Moved PaddedArray to CPU")
    
    def to_gpu(self):
        """Move stored arrays to GPU memory (like fourierTransformer)."""
        if not HAS_CUPY:
            warnings.warn("CuPy not available, cannot move to GPU")
            return
        
        if self._array_is_initialized and self.method == "CPU":
            self._stored_array = cp.asarray(self._stored_array)
            self.method = "GPU"
            logger.debug("Moved PaddedArray to GPU")
    
    def get_memory_info(self) -> Dict[str, Any]:
        """Get information about memory usage."""
        info = {
            'method': self.method,
            'dtype': self.dtype,
            'input_shape': self.input_shape,
            'output_shape': self.output_shape,
            'array_initialized': self._array_is_initialized,
            'use_once': self.use_once
        }
        
        if self._array_is_initialized:
            array_size = np.prod(self.output_shape) * np.dtype(self.dtype).itemsize
            info['array_size_bytes'] = array_size
            info['array_size_mb'] = array_size / (1024 * 1024)
        
        return info
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        try:
            if self._array_is_initialized:
                self._stored_array = None
                if logger is not None:
                    logger.debug("PaddedArray cleanup completed")
        except:
            # Ignore cleanup errors during shutdown
            pass


# Convenience functions for backward compatibility
def create_padded_array_once(
    image: Union[np.ndarray, Any],
    pad_low: Union[np.ndarray, Tuple, str],
    pad_top: Optional[Union[np.ndarray, Tuple]] = None,
    method: Literal["GPU", "CPU"] = "CPU",
    precision: Literal["single", "double", "singleTaper", "doubleTaper"] = "single",
    extrap_val: Optional[Union[float, str]] = None,
    fourier_oversample: bool = False
) -> Union[np.ndarray, Any]:
    """
    Convenience function for single-use padding (matches original interface).
    
    This creates a PaddedArray in single-use mode and returns the padded result.
    """
    padder = PaddedArray(
        method=method,
        precision=precision,
        use_once=True,
        extrap_val=extrap_val
    )
    
    return padder.pad_image(
        image=image,
        pad_low=pad_low,
        pad_top=pad_top,
        fourier_oversample=fourier_oversample
    )


# Alias for MATLAB compatibility
def BH_padZeros3d_class(
    IMAGE, PADLOW, PADTOP, METHOD='CPU', PRECISION='single', *varargin
):
    """
    MATLAB-compatible interface using PaddedArray class.
    
    Returns a configured PaddedArray instance for reuse.
    """
    # Parse optional arguments
    extrap_val = None
    fourier_oversample = False
    
    if len(varargin) > 0:
        if isinstance(varargin[0], (int, float)):
            extrap_val = varargin[0]
        elif isinstance(varargin[0], str) and varargin[0].lower() == 'random':
            extrap_val = 'random'
        
        if len(varargin) > 1:
            extrap_val = 0  # Reset for Fourier oversampling
            fourier_oversample = True
    
    # Determine output shape for persistent storage
    if isinstance(IMAGE, (np.ndarray, type(cp.ndarray if HAS_CUPY else np.ndarray))):
        input_shape = IMAGE.shape
        # Calculate rough output shape (will be refined during first use)
        if isinstance(PADLOW, str):
            output_shape = None  # Will be determined dynamically
        else:
            pad_low_vals = np.array(PADLOW)
            pad_top_vals = np.array(PADTOP) if PADTOP is not None else np.array(PADLOW)
            img_shape = np.array(input_shape)
            if len(img_shape) == 2:
                img_shape = np.array([*img_shape, 1])
            output_shape = tuple(img_shape + pad_low_vals + pad_top_vals)
    else:
        input_shape = None
        output_shape = None
    
    return PaddedArray(
        input_shape=input_shape,
        output_shape=output_shape,
        method=METHOD,
        precision=PRECISION,
        use_once=False,  # Allow reuse
        extrap_val=extrap_val
    )
