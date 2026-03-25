"""
Tile preparation and reference projection utilities for CTF refinement.

Prepares 2D particle tiles and 3D reference projections for cross-correlation
scoring in the CTF refinement pipeline.  Mirrors the tile-preparation loop in
``ctf/EMC_ctf_refine_from_star.m`` lines 300-317.

Pipeline (data tile)::

    raw tile → soft mask → mean-subtract → RMS-normalize → pad to CTFSIZE
    → forward FFT → swap_phase → bandpass → pre-normalize

Pipeline (reference projection)::

    3D volume → inverse-rotate by SPIDER ZYZ Euler angles → project (sum
    along Z) → soft mask → mean-subtract → pad → forward FFT → conjugate

GPU/CPU dispatch
~~~~~~~~~~~~~~~~
All public functions accept both :mod:`numpy` and :mod:`cupy` arrays.
Dispatch is performed via ``isinstance(x, cp.ndarray)``; the deprecated
``cupy.get_array_module`` is **not** used.
"""

from __future__ import annotations

import types
from typing import TYPE_CHECKING

import numpy as np
from scipy.ndimage import map_coordinates

try:
    import cupy as cp

    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False
    cp = None

if TYPE_CHECKING:
    import cupy

    NDArray = np.ndarray | cupy.ndarray
else:
    NDArray = np.ndarray

from .emc_fourier_utils import FourierTransformer


def _xp_for(x: NDArray) -> types.ModuleType:
    """Return the array module (numpy or cupy) that owns *x*."""
    if HAS_CUPY and isinstance(x, cp.ndarray):
        return cp
    return np


# ---------------------------------------------------------------------------
# FFT-friendly size computation
# ---------------------------------------------------------------------------


def compute_ctf_friendly_size(n: int) -> int:
    """Round *n* up to the next FFT-friendly size.

    An FFT-friendly size is one whose prime factorisation contains only the
    primes 2, 3, 5, and 7.  These are sometimes called *7-smooth* or
    *humble* numbers and correspond to sizes that FFT libraries (FFTW, cuFFT)
    handle most efficiently.

    Args:
        n: Minimum required size (positive integer).

    Returns:
        Smallest integer >= *n* that is a product of powers of 2, 3, 5, 7.

    Raises:
        ValueError: If *n* is not a positive integer.
    """
    if n < 1:
        raise ValueError(f"n must be a positive integer, got {n}")

    candidate = n
    while True:
        if _is_7smooth(candidate):
            return candidate
        candidate += 1


def _is_7smooth(n: int) -> bool:
    """Return True if *n* is a positive integer with no prime factor larger than 7."""
    if n <= 0:
        return False
    for p in (2, 3, 5, 7):
        while n % p == 0:
            n //= p
    return n == 1


# ---------------------------------------------------------------------------
# 2-D soft circular mask
# ---------------------------------------------------------------------------


def create_2d_soft_mask(
    nx: int,
    ny: int,
    radius: float,
    edge_width: float = 5.0,
) -> np.ndarray:
    """Create a 2D circular mask with cosine-edge rolloff.

    The mask is 1.0 inside *radius*, falls smoothly to 0.0 over
    *edge_width* pixels using a raised-cosine profile, and is 0.0
    outside ``radius + edge_width``.

    The centre of the mask is placed at the Fourier-convention origin
    ``(nx // 2, ny // 2)`` (0-indexed), matching the MATLAB
    ``emc_get_origin_index`` convention translated to 0-based indexing.

    Args:
        nx: Number of rows.
        ny: Number of columns.
        radius: Inner radius where the mask equals 1.0.
        edge_width: Width of the cosine rolloff zone in pixels.

    Returns:
        Float32 array of shape ``(nx, ny)`` with values in [0, 1].
    """
    origin_x = nx // 2
    origin_y = ny // 2

    iy = np.arange(nx, dtype=np.float32)
    ix = np.arange(ny, dtype=np.float32)
    gy, gx = np.meshgrid(iy, ix, indexing="ij")

    dist = np.sqrt((gy - origin_x) ** 2 + (gx - origin_y) ** 2)

    mask = np.ones((nx, ny), dtype=np.float32)

    # Cosine taper in the transition zone
    taper_region = (dist > radius) & (dist <= radius + edge_width)
    mask[taper_region] = 0.5 * (
        1.0 + np.cos(np.pi * (dist[taper_region] - radius) / edge_width)
    )

    # Zero outside
    mask[dist > radius + edge_width] = 0.0

    return mask


# ---------------------------------------------------------------------------
# Spherical CTF mask
# ---------------------------------------------------------------------------


def create_ctf_mask(ctf_size: int) -> np.ndarray:
    """Create a real-space spherical CTF mask at the given CTFSIZE.

    The mask is a 2D binary circle of radius ``origin - 7`` where
    ``origin = ctf_size // 2`` (image centre, 0-indexed).  It is applied
    in **real space** after padding and before the forward FFT, matching
    the MATLAB convention at ``EMC_ctf_refine_from_star.m`` lines 308
    and 317::

        local_ctf_mask .* BH_padZeros3d(data_tile, 'fwd', padCTF, ...)

    The underlying MATLAB call is ``BH_mask3d('sphere', CTFSIZE,
    ctfOrigin - 7, [0,0], '2d')`` with ``ctfOrigin = floor(CTFSIZE/2)
    + 1`` (1-indexed), translated here to 0-based indexing.

    Args:
        ctf_size: Side length of the square CTF-padded image.

    Returns:
        Float32 binary mask of shape ``(ctf_size, ctf_size)``.
    """
    origin = ctf_size // 2
    radius = origin - 7

    if radius <= 0:
        raise ValueError(
            f"ctf_size={ctf_size} yields non-positive mask radius "
            f"({origin} - 7 = {radius}); ctf_size must be >= 16"
        )

    iy = np.arange(ctf_size, dtype=np.float32)
    ix = np.arange(ctf_size, dtype=np.float32)
    gy, gx = np.meshgrid(iy, ix, indexing="ij")

    dist = np.sqrt((gy - origin) ** 2 + (gx - origin) ** 2)

    mask = np.zeros((ctf_size, ctf_size), dtype=np.float32)
    mask[dist <= radius] = 1.0

    return mask


# ---------------------------------------------------------------------------
# Center crop / pad
# ---------------------------------------------------------------------------


def center_crop_or_pad(
    image: NDArray,
    target_size: tuple[int, int],
) -> NDArray:
    """Center-crop if *image* is larger, or zero-pad if smaller.

    Mirrors the MATLAB ``center_crop_or_pad`` helper in
    ``ctf/EMC_ctf_refine_from_star.m`` lines 806-831.  Uses the
    Fourier-convention origin ``n // 2`` (0-indexed).

    Args:
        image: 2-D input array.
        target_size: Desired ``(rows, cols)`` output shape.

    Returns:
        Array of shape *target_size* with the same dtype as *image*.
    """
    xp = _xp_for(image)
    in_h, in_w = image.shape[:2]
    out_h, out_w = target_size

    if in_h == out_h and in_w == out_w:
        return image

    output = xp.zeros(target_size, dtype=image.dtype)

    # Origins (0-indexed Fourier convention: floor(n/2))
    in_oy, in_ox = in_h // 2, in_w // 2
    out_oy, out_ox = out_h // 2, out_w // 2

    # Overlapping region in input coordinates
    in_y0 = max(0, in_oy - out_oy)
    in_x0 = max(0, in_ox - out_ox)
    in_y1 = min(in_h, in_oy + (out_h - out_oy))
    in_x1 = min(in_w, in_ox + (out_w - out_ox))

    # Corresponding output coordinates
    out_y0 = max(0, out_oy - in_oy)
    out_x0 = max(0, out_ox - in_ox)
    out_y1 = out_y0 + (in_y1 - in_y0)
    out_x1 = out_x0 + (in_x1 - in_x0)

    output[out_y0:out_y1, out_x0:out_x1] = image[in_y0:in_y1, in_x0:in_x1]

    return output


# ---------------------------------------------------------------------------
# Euler rotation (SPIDER ZYZ, inverse)
# ---------------------------------------------------------------------------


def spider_zyz_inverse_matrix(
    phi: float, theta: float, psi: float,
) -> np.ndarray:
    """Build 3x3 inverse rotation matrix for SPIDER ZYZ Euler angles.

    The inverse rotation is R = Rz(-phi) * Ry(-theta) * Rz(-psi),
    which is the transpose of the forward SPIDER ZYZ rotation
    R_fwd = Rz(psi) * Ry(theta) * Rz(phi).

    All angles are in **degrees** (SPIDER convention).

    Args:
        phi: First Euler angle (rotation about Z).
        theta: Second Euler angle (rotation about Y').
        psi: Third Euler angle (rotation about Z'').

    Returns:
        3x3 rotation matrix as float64 numpy array.
    """
    phi_r = np.radians(-phi)
    theta_r = np.radians(-theta)
    psi_r = np.radians(-psi)

    # Rz(-phi)
    cphi, sphi = np.cos(phi_r), np.sin(phi_r)
    rz_phi = np.array([
        [cphi, -sphi, 0.0],
        [sphi, cphi, 0.0],
        [0.0, 0.0, 1.0],
    ])

    # Ry(-theta)
    ctheta, stheta = np.cos(theta_r), np.sin(theta_r)
    ry_theta = np.array([
        [ctheta, 0.0, stheta],
        [0.0, 1.0, 0.0],
        [-stheta, 0.0, ctheta],
    ])

    # Rz(-psi)
    cpsi, spsi = np.cos(psi_r), np.sin(psi_r)
    rz_psi = np.array([
        [cpsi, -spsi, 0.0],
        [spsi, cpsi, 0.0],
        [0.0, 0.0, 1.0],
    ])

    return rz_phi @ ry_theta @ rz_psi


def rotate_volume_trilinear(
    volume: np.ndarray,
    rotation_matrix: np.ndarray,
) -> np.ndarray:
    """Rotate a 3D volume using trilinear interpolation.

    The volume has shape ``[Z, Y, X]`` with origin at
    ``(nz//2, ny//2, nx//2)`` (0-indexed Fourier convention).

    Uses output-to-input coordinate mapping: for each output voxel at
    position ``r_out`` (relative to origin), the source position is
    ``r_in = R_inv @ r_out``.  Since *rotation_matrix* is already the
    inverse rotation (``R_fwd^T``), applying it as the coordinate map
    rotates volume content by the forward rotation — matching the MATLAB
    ``interp3d(..., 'inv')`` convention.

    Args:
        volume: 3-D array of shape ``(nz, ny, nx)``.
        rotation_matrix: 3x3 inverse rotation matrix (``R_fwd^T``).

    Returns:
        Rotated volume of the same shape.
    """
    nz, ny, nx = volume.shape
    oz, oy, ox = nz // 2, ny // 2, nx // 2

    # Build output coordinate grid (centred on origin)
    zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    zz = zz.astype(np.float64) - oz
    yy = yy.astype(np.float64) - oy
    xx = xx.astype(np.float64) - ox

    # Stack as [x, y, z] to match the rotation matrix convention
    # (Rz/Ry are built for standard [x, y, z] basis).
    coords_xyz = np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=0)

    # Apply inverse rotation (output→input mapping) in [x, y, z] space
    rotated_xyz = rotation_matrix @ coords_xyz

    # Reorder [x', y', z'] → [z', y', x'] for map_coordinates (array
    # index order) and shift back to grid coordinates.
    input_coords = rotated_xyz[[2, 1, 0], :]
    input_coords[0] += oz
    input_coords[1] += oy
    input_coords[2] += ox

    # Trilinear interpolation (order=1), out-of-bounds → 0
    rotated = map_coordinates(
        volume.astype(np.float64),
        input_coords,
        order=1,
        mode="constant",
        cval=0.0,
    )

    return rotated.reshape(volume.shape).astype(volume.dtype)


# ---------------------------------------------------------------------------
# Data tile preparation
# ---------------------------------------------------------------------------


def prepare_data_tile(
    tile: NDArray,
    mask: NDArray,
    pad_size: int,
    fourier_handler: FourierTransformer,
    pixel_size: float,
    highpass: float,
    lowpass: float,
) -> NDArray:
    """Prepare a data tile for cross-correlation scoring.

    Applies the full pipeline: soft mask → mean-subtract → RMS-normalize
    → pad to *pad_size* → forward FFT → swap_phase → bandpass →
    pre-normalize.

    Mirrors ``ctf/EMC_ctf_refine_from_star.m`` lines 305-308.

    Args:
        tile: Raw 2D particle image, shape ``(tile_ny, tile_nx)``.
        mask: 2D soft circular mask, same shape as *tile*.
        pad_size: Target padded size (square: ``pad_size x pad_size``).
        fourier_handler: :class:`FourierTransformer` configured for
            *pad_size* dimensions.
        pixel_size: Pixel size in Angstroms.
        highpass: High-pass cutoff in Angstroms (e.g. 400).
        lowpass: Low-pass cutoff in Angstroms (e.g. 10).

    Returns:
        Complex Fourier-domain tile (half-grid layout) ready for
        cross-correlation.
    """
    xp = _xp_for(tile)

    # Ensure mask is on the same device as tile
    if xp is not np:
        mask = cp.asarray(mask)
    elif HAS_CUPY and isinstance(mask, cp.ndarray):
        mask = mask.get()

    # Apply soft mask
    masked = mask * tile

    # Mean-subtract
    masked = masked - xp.mean(masked)

    # RMS-normalize
    rms_val = xp.sqrt(xp.mean(masked ** 2))
    if float(rms_val) > 0.0:
        masked = masked / rms_val

    # Center-crop or pad to CTFSIZE
    padded = center_crop_or_pad(masked, (pad_size, pad_size))

    # Forward FFT
    spectrum = fourier_handler.forward_fft(padded)

    # Swap phase in spectral domain (checkerboard multiply for DC centering).
    # Applied AFTER FFT so the checkerboard modulates frequency bins directly,
    # shifting the cross-correlation peak from (0,0) to (nx//2, ny//2) in the
    # IFFT output.  Applying the checkerboard in real-space before FFT (the
    # previous implementation) shifts the spectrum itself, which decorrelates
    # the cross-correlation rather than centering it.
    spectrum = fourier_handler.swap_phase(spectrum)

    # Apply bandpass filter
    filtered = fourier_handler.apply_bandpass(
        spectrum, pixel_size, highpass, lowpass,
    )

    # Pre-normalize (divide by half-grid energy)
    norm = fourier_handler.compute_ref_norm(filtered)
    if norm > 0.0:
        filtered = filtered / norm

    return filtered


# ---------------------------------------------------------------------------
# Reference projection preparation
# ---------------------------------------------------------------------------


def prepare_reference_projection(
    volume: NDArray,
    euler_angles: tuple[float, float, float],
    mask: NDArray,
    pad_size: int,
    fourier_handler: FourierTransformer,
) -> NDArray:
    """Generate a reference projection from a 3D volume.

    Rotates the volume by SPIDER ZYZ Euler angles using the **inverse
    rotation** convention, projects along the Z-axis (axis 0 for [Z,Y,X]
    ordered volumes), applies a soft mask, mean-subtracts, RMS-normalizes,
    pads, transforms to Fourier space, and returns the **complex conjugate**
    (pre-conjugated for cross-correlation).

    Mirrors ``ctf/EMC_ctf_refine_from_star.m`` lines 311-317.

    .. note:: **Phase-centering asymmetry with data tiles.**
       Data tiles receive :meth:`FourierTransformer.swap_phase` (checkerboard
       multiply) after the forward FFT, while reference projections do **not**.
       This intentional asymmetry shifts the cross-correlation peak from the
       array corner to the image centre, allowing sub-pixel peak extraction
       without an ``fftshift``.  See :func:`emc_scoring.score_ctf_candidates`
       for the consumer contract.

    Args:
        volume: 3-D reference volume, shape ``(nz, ny, nx)`` in [Z,Y,X]
            order.
        euler_angles: ``(phi, theta, psi)`` in degrees (SPIDER ZYZ).
        mask: 2D soft circular mask matching the projection size.
        pad_size: Target padded size (square).
        fourier_handler: :class:`FourierTransformer` configured for
            *pad_size* dimensions.

    Returns:
        Complex conjugate of the Fourier-domain projection (half-grid).
    """
    xp = _xp_for(volume)

    # KI-313/319: CPU-only rotation is intentional — scipy.ndimage.map_coordinates
    # has no CuPy equivalent, so the volume is moved to host for rotation and the
    # resulting projection is re-uploaded to GPU after masking/padding.
    vol_np = volume if isinstance(volume, np.ndarray) else volume.get()

    phi, theta, psi = euler_angles

    # Build inverse rotation matrix
    rot_matrix = spider_zyz_inverse_matrix(phi, theta, psi)

    # Rotate volume with trilinear interpolation
    rotated = rotate_volume_trilinear(vol_np, rot_matrix)

    # Project along Z (axis 0) for [Z,Y,X] volumes → 2D [Y,X]
    projection = np.sum(rotated, axis=0)

    # Convert mask to NumPy for CPU-side work (mask may be CuPy when
    # volume was on GPU, but projection is always NumPy from scipy).
    mask_np = mask if isinstance(mask, np.ndarray) else mask.get()

    # Match mask shape via center crop/pad
    tile_ny, tile_nx = mask_np.shape
    projection = center_crop_or_pad(projection, (tile_ny, tile_nx))

    # Apply soft mask
    masked = mask_np * projection

    # Mean-subtract
    masked = masked - np.mean(masked)

    # RMS-normalize (MATLAB: ref_tile ./ rms(ref_tile(:)))
    rms_val = np.sqrt(np.mean(masked ** 2))
    if float(rms_val) > 0.0:
        masked = masked / rms_val

    # Pad to CTFSIZE
    padded = center_crop_or_pad(masked, (pad_size, pad_size))

    # Move to GPU if original volume was on GPU
    if xp is not np:
        padded = cp.asarray(padded)

    # Forward FFT
    spectrum = fourier_handler.forward_fft(padded)

    # Return complex conjugate (pre-conjugated for cross-correlation)
    return xp.conj(spectrum)
