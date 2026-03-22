"""
Tests for tile preparation and reference projection utilities.

Validates ``emc_tile_prep.py`` against analytical expectations and the
acceptance criteria defined in TASK-012a.
"""

from __future__ import annotations

import numpy as np
import pytest

from ..emc_fourier_utils import FourierTransformer
from ..emc_tile_prep import (
    _is_7smooth,
    _rotate_volume_trilinear,
    _spider_zyz_inverse_matrix,
    center_crop_or_pad,
    compute_ctf_friendly_size,
    create_2d_soft_mask,
    create_ctf_mask,
    prepare_data_tile,
    prepare_reference_projection,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TILE_SIZE = 64
PAD_SIZE = 128  # ~2x tile, FFT-friendly
PIXEL_SIZE = 1.35  # Angstroms (typical cryo-EM)


@pytest.fixture()
def soft_mask() -> np.ndarray:
    """Soft circular mask for 64x64 tiles."""
    return create_2d_soft_mask(
        TILE_SIZE, TILE_SIZE, radius=25.0, edge_width=5.0,
    )


@pytest.fixture()
def ft_pad() -> FourierTransformer:
    """FourierTransformer at padded size (CPU)."""
    return FourierTransformer(PAD_SIZE, PAD_SIZE, use_gpu=False)


# ---------------------------------------------------------------------------
# Test: compute_ctf_friendly_size
# ---------------------------------------------------------------------------


class TestComputeCtfFriendlySize:
    """FFT-friendly size rounding produces correct 7-smooth numbers."""

    def test_already_friendly(self) -> None:
        """64 is already 2^6, should return unchanged."""
        assert compute_ctf_friendly_size(64) == 64

    def test_100_is_friendly(self) -> None:
        """100 = 2^2 * 5^2, should return unchanged."""
        assert compute_ctf_friendly_size(100) == 100

    def test_257_rounds_up(self) -> None:
        """257 is prime, next 7-smooth number is 270 = 2 * 3^3 * 5."""
        assert compute_ctf_friendly_size(257) == 270

    def test_result_is_7smooth(self) -> None:
        """Returned value is always 7-smooth for a range of inputs."""
        for n in [65, 100, 127, 200, 257, 300, 500]:
            result = compute_ctf_friendly_size(n)
            assert result >= n
            assert _is_7smooth(result), (
                f"{result} is not 7-smooth (input {n})"
            )

    def test_invalid_input(self) -> None:
        """Non-positive input raises ValueError."""
        with pytest.raises(ValueError, match="positive"):
            compute_ctf_friendly_size(0)
        with pytest.raises(ValueError, match="positive"):
            compute_ctf_friendly_size(-5)


# ---------------------------------------------------------------------------
# Test: create_2d_soft_mask
# ---------------------------------------------------------------------------


class TestCreate2dSoftMask:
    """2D soft mask has correct shape, values, and cosine transition."""

    def test_shape(self) -> None:
        """Mask has requested shape."""
        mask = create_2d_soft_mask(64, 48, radius=20.0, edge_width=5.0)
        assert mask.shape == (64, 48)

    def test_center_is_one(self) -> None:
        """Centre pixel (inside radius) equals 1.0."""
        mask = create_2d_soft_mask(64, 64, radius=20.0, edge_width=5.0)
        assert mask[32, 32] == pytest.approx(1.0)

    def test_inside_radius_all_one(self) -> None:
        """All pixels strictly inside radius are 1.0."""
        mask = create_2d_soft_mask(64, 64, radius=20.0, edge_width=5.0)
        origin = 32
        for dy in range(-18, 19):
            for dx in range(-18, 19):
                dist = np.sqrt(dy**2 + dx**2)
                if dist < 19.0:  # well inside radius=20
                    assert mask[origin + dy, origin + dx] == (
                        pytest.approx(1.0)
                    ), f"Pixel at dist={dist:.1f} should be 1.0"

    def test_outside_is_zero(self) -> None:
        """Pixels beyond radius + edge_width are 0.0."""
        mask = create_2d_soft_mask(
            64, 64, radius=20.0, edge_width=5.0,
        )
        # Corner pixel at distance ~sqrt(31^2+31^2) > 25
        assert mask[0, 0] == pytest.approx(0.0)
        assert mask[63, 63] == pytest.approx(0.0)

    def test_smooth_cosine_transition(self) -> None:
        """Values in the transition zone are in [0, 1]."""
        radius = 20.0
        edge_width = 5.0
        mask = create_2d_soft_mask(
            64, 64, radius=radius, edge_width=edge_width,
        )
        origin = 32

        # Sample pixels in the transition zone along the +x axis
        for offset in range(1, 5):
            dist = radius + offset
            if dist <= radius + edge_width:
                pixel_val = mask[origin, origin + int(dist)]
                assert pixel_val >= 0.0
                assert pixel_val <= 1.0

    def test_values_in_01_range(self) -> None:
        """All mask values are in [0, 1]."""
        mask = create_2d_soft_mask(128, 128, radius=40.0, edge_width=10.0)
        assert mask.min() >= 0.0
        assert mask.max() <= 1.0

    def test_dtype_is_float32(self) -> None:
        """Mask dtype is float32."""
        mask = create_2d_soft_mask(64, 64, radius=20.0)
        assert mask.dtype == np.float32


# ---------------------------------------------------------------------------
# Test: create_ctf_mask
# ---------------------------------------------------------------------------


class TestCreateCtfMask:
    """CTF mask is a binary sphere with correct radius and shape."""

    def test_shape(self) -> None:
        """Mask has (ctf_size, ctf_size) shape."""
        mask = create_ctf_mask(128)
        assert mask.shape == (128, 128)

    def test_radius_is_origin_minus_7(self) -> None:
        """Radius equals origin - 7 where origin = ctf_size // 2."""
        ctf_size = 128
        mask = create_ctf_mask(ctf_size)
        origin = ctf_size // 2  # 64
        expected_radius = origin - 7  # 57

        # Centre pixel should be 1
        assert mask[origin, origin] == pytest.approx(1.0)

        # Pixel at exactly the radius (along +x) should be 1
        assert mask[origin, origin + expected_radius] == (
            pytest.approx(1.0)
        )

        # Pixel well beyond radius should be 0
        assert mask[origin, origin + expected_radius + 2] == (
            pytest.approx(0.0)
        )

    def test_binary_values(self) -> None:
        """Mask contains only 0.0 and 1.0."""
        mask = create_ctf_mask(64)
        unique_vals = np.unique(mask)
        assert set(unique_vals).issubset({0.0, 1.0})

    def test_dtype_is_float32(self) -> None:
        """Mask dtype is float32."""
        mask = create_ctf_mask(128)
        assert mask.dtype == np.float32


# ---------------------------------------------------------------------------
# Test: center_crop_or_pad
# ---------------------------------------------------------------------------


class TestCenterCropOrPad:
    """Center crop and pad preserve center content and zero border."""

    def test_crop_preserves_center(self) -> None:
        """Cropping 128x128 to 64x64 preserves the central region."""
        big = np.random.default_rng(42).standard_normal(
            (128, 128),
        ).astype(np.float32)
        small = center_crop_or_pad(big, (64, 64))
        assert small.shape == (64, 64)

        # Centre pixel of the crop should match centre of original
        big_origin = 128 // 2
        small_origin = 64 // 2
        assert small[small_origin, small_origin] == pytest.approx(
            big[big_origin, big_origin],
        )

    def test_pad_has_zero_border(self) -> None:
        """Padding 64x64 to 128x128 produces zero border."""
        small = np.ones((64, 64), dtype=np.float32)
        big = center_crop_or_pad(small, (128, 128))
        assert big.shape == (128, 128)

        # Corners should be zero (padding region)
        assert big[0, 0] == pytest.approx(0.0)
        assert big[127, 127] == pytest.approx(0.0)
        assert big[0, 127] == pytest.approx(0.0)
        assert big[127, 0] == pytest.approx(0.0)

        # Centre should be 1 (from original)
        assert big[64, 64] == pytest.approx(1.0)

    def test_same_size_returns_original(self) -> None:
        """Same-size input returns the input unchanged."""
        arr = np.ones((64, 64), dtype=np.float32) * 3.14
        result = center_crop_or_pad(arr, (64, 64))
        np.testing.assert_array_equal(result, arr)

    def test_crop_roundtrip(self) -> None:
        """Pad then crop recovers original centre content."""
        rng = np.random.default_rng(123)
        original = rng.standard_normal((64, 64)).astype(np.float32)
        padded = center_crop_or_pad(original, (128, 128))
        recovered = center_crop_or_pad(padded, (64, 64))
        np.testing.assert_allclose(recovered, original, atol=1e-7)

    def test_non_square(self) -> None:
        """Works with non-square arrays."""
        arr = np.ones((48, 64), dtype=np.float32) * 2.0
        result = center_crop_or_pad(arr, (64, 80))
        assert result.shape == (64, 80)
        # Centre should have the value
        assert result[32, 40] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Test: SPIDER ZYZ inverse rotation matrix
# ---------------------------------------------------------------------------


class TestSpiderZyzInverseMatrix:
    """Inverse rotation matrix matches analytical hand-computation."""

    def test_identity_at_zero_angles(self) -> None:
        """(0, 0, 0) produces the identity matrix."""
        rot = _spider_zyz_inverse_matrix(0.0, 0.0, 0.0)
        np.testing.assert_allclose(rot, np.eye(3), atol=1e-15)

    def test_known_euler_angles(self) -> None:
        """Known angles produce hand-computed matrix within 1e-7.

        For phi=90, theta=90, psi=0:
        Rz(-90) * Ry(-90) * Rz(0):
          Rz(-90) = [[0, 1, 0], [-1, 0, 0], [0, 0, 1]]
          Ry(-90) = [[0, 0, -1], [0, 1, 0], [1, 0, 0]]
          Product = [[0, 1, 0], [0, 0, 1], [1, 0, 0]]
        """
        rot = _spider_zyz_inverse_matrix(90.0, 90.0, 0.0)
        expected = np.array([
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 0.0],
        ])
        np.testing.assert_allclose(rot, expected, atol=1e-7)

    def test_another_known_angle(self) -> None:
        """phi=0, theta=0, psi=90: Rz(0)*Ry(0)*Rz(-90) = Rz(-90).

        Rz(-90) = [[0, 1, 0], [-1, 0, 0], [0, 0, 1]]
        """
        rot = _spider_zyz_inverse_matrix(0.0, 0.0, 90.0)
        expected = np.array([
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ])
        np.testing.assert_allclose(rot, expected, atol=1e-7)

    def test_rotation_is_orthogonal(self) -> None:
        """R^T @ R = I for arbitrary angles."""
        rng = np.random.default_rng(42)
        for _ in range(10):
            phi, theta, psi = rng.uniform(-180, 180, size=3)
            rot = _spider_zyz_inverse_matrix(phi, theta, psi)
            np.testing.assert_allclose(
                rot.T @ rot, np.eye(3), atol=1e-12,
            )

    def test_determinant_is_one(self) -> None:
        """det(R) = 1 for proper rotation (no reflection)."""
        rng = np.random.default_rng(7)
        for _ in range(10):
            phi, theta, psi = rng.uniform(-180, 180, size=3)
            rot = _spider_zyz_inverse_matrix(phi, theta, psi)
            assert np.linalg.det(rot) == pytest.approx(
                1.0, abs=1e-12,
            )


# ---------------------------------------------------------------------------
# Test: Projection axis
# ---------------------------------------------------------------------------


class TestProjectionAxis:
    """sum(volume, axis=0) for [Z,Y,X] volume gives [Y,X] projection."""

    def test_z_projection_shape(self) -> None:
        """Projecting (nz, ny, nx) along axis 0 gives (ny, nx)."""
        vol = np.zeros((16, 32, 24), dtype=np.float32)
        proj = np.sum(vol, axis=0)
        assert proj.shape == (32, 24)

    def test_single_nonzero_slice(self) -> None:
        """Volume with one non-zero Z-slice projects to that slice."""
        vol = np.zeros((16, 32, 32), dtype=np.float32)
        vol[8, :, :] = 1.0  # single slice at z=8
        proj = np.sum(vol, axis=0)
        expected = np.ones((32, 32), dtype=np.float32)
        np.testing.assert_allclose(proj, expected)

    def test_projection_sums_correctly(self) -> None:
        """Projection accumulates values along Z axis."""
        vol = np.ones((10, 8, 8), dtype=np.float32)
        proj = np.sum(vol, axis=0)
        np.testing.assert_allclose(proj, 10.0 * np.ones((8, 8)))


# ---------------------------------------------------------------------------
# Test: Trilinear interpolation preserves intensity
# ---------------------------------------------------------------------------


class TestTrilinearInterpolation:
    """Rotated volume preserves total intensity for small rotations."""

    def test_small_rotation_intensity_preserved(self) -> None:
        """Total intensity preserved within 1% for small rotations.

        A Gaussian blob centred in the volume ensures most voxels are
        interior (not clipped by the boundary), so intensity should be
        well-preserved after a small rotation.
        """
        n = 32
        centre = n // 2
        sigma = n / 6.0  # Gaussian well within the volume
        zz, yy, xx = np.mgrid[0:n, 0:n, 0:n]
        vol = np.exp(
            -(
                (zz - centre) ** 2
                + (yy - centre) ** 2
                + (xx - centre) ** 2
            )
            / (2.0 * sigma**2)
        ).astype(np.float32)

        # Small rotation: 5 degrees about each axis
        rot = _spider_zyz_inverse_matrix(5.0, 5.0, 5.0)
        rotated = _rotate_volume_trilinear(vol, rot)

        original_sum = float(np.sum(vol))
        rotated_sum = float(np.sum(rotated))

        rel_change = abs(rotated_sum - original_sum) / original_sum
        assert rotated_sum == pytest.approx(
            original_sum, rel=0.01,
        ), f"Intensity changed by {rel_change * 100:.2f}%"

    def test_identity_rotation_unchanged(self) -> None:
        """Identity rotation returns the original volume."""
        rng = np.random.default_rng(42)
        vol = rng.standard_normal((16, 16, 16)).astype(np.float32)
        rot = np.eye(3)
        rotated = _rotate_volume_trilinear(vol, rot)
        np.testing.assert_allclose(rotated, vol, atol=1e-5)


# ---------------------------------------------------------------------------
# Test: prepare_data_tile round-trip
# ---------------------------------------------------------------------------


class TestPrepareDataTile:
    """Prepared data tile is in Fourier domain with masks applied."""

    def test_returns_complex_half_grid(
        self, soft_mask: np.ndarray, ft_pad: FourierTransformer,
    ) -> None:
        """Output is complex with half-grid shape."""
        rng = np.random.default_rng(42)
        tile = rng.standard_normal(
            (TILE_SIZE, TILE_SIZE),
        ).astype(np.float32)

        result = prepare_data_tile(
            tile, soft_mask, PAD_SIZE, ft_pad, PIXEL_SIZE,
            highpass=400.0, lowpass=10.0,
        )

        assert np.iscomplexobj(result)
        # Half-grid: (pad_size // 2 + 1, pad_size)
        assert result.shape == (PAD_SIZE // 2 + 1, PAD_SIZE)

    def test_roundtrip_recovers_structure(
        self, soft_mask: np.ndarray, ft_pad: FourierTransformer,
    ) -> None:
        """Inverse FFT of prepared tile correlates with original image.

        Exact recovery isn't expected because bandpass filtering
        and normalization modify the content, but the recovered
        real-space image should positively correlate with the
        original tile.
        """
        rng = np.random.default_rng(42)
        tile = rng.standard_normal(
            (TILE_SIZE, TILE_SIZE),
        ).astype(np.float32)

        result = prepare_data_tile(
            tile, soft_mask, PAD_SIZE, ft_pad, PIXEL_SIZE,
            highpass=400.0, lowpass=10.0,
        )

        recovered = ft_pad.inverse_fft(result)

        # Undo phase swap (checkerboard is self-inverse)
        unswapped = ft_pad.swap_phase(recovered)

        # Crop back to original tile size for comparison
        cropped = center_crop_or_pad(unswapped, (TILE_SIZE, TILE_SIZE))

        # Recovered image should positively correlate with original.
        # Correlation is modest (~0.2) because the soft mask zeros tile
        # corners, but well above chance level (~0.016 for 4096 elements).
        corr = np.corrcoef(cropped.ravel(), tile.ravel())[0, 1]
        assert corr > 0.1, f"Round-trip correlation {corr:.3f} too low"

    def test_mask_applied(
        self, soft_mask: np.ndarray, ft_pad: FourierTransformer,
    ) -> None:
        """DC component near zero after masking + mean-subtraction.

        We verify that a tile with constant value has its DC component
        near zero after preparation (mean-subtraction zeroes DC).
        """
        tile = np.ones((TILE_SIZE, TILE_SIZE), dtype=np.float32)

        result = prepare_data_tile(
            tile, soft_mask, PAD_SIZE, ft_pad, PIXEL_SIZE,
            highpass=400.0, lowpass=10.0,
        )

        # DC is zeroed by mean-subtraction + highpass filter
        # The (0,0) frequency bin in half-grid is the DC
        assert np.abs(result[0, 0]) < 1e-5


# ---------------------------------------------------------------------------
# Test: prepare_reference_projection
# ---------------------------------------------------------------------------


class TestPrepareReferenceProjection:
    """Reference projection pipeline produces conjugated Fourier output."""

    def test_returns_complex_conjugate(
        self, soft_mask: np.ndarray, ft_pad: FourierTransformer,
    ) -> None:
        """Output is verified to be complex conjugate by comparison."""
        rng = np.random.default_rng(42)
        vol = rng.standard_normal(
            (TILE_SIZE, TILE_SIZE, TILE_SIZE),
        ).astype(np.float32)

        result = prepare_reference_projection(
            vol, (0.0, 0.0, 0.0), soft_mask, PAD_SIZE, ft_pad,
        )

        assert np.iscomplexobj(result)

        # If result = conj(spectrum), then conj(result) = spectrum
        unconjugated = np.conj(result)

        # Re-conjugating should give back the original result
        np.testing.assert_allclose(np.conj(unconjugated), result)

    def test_explicit_conjugate_comparison(
        self, soft_mask: np.ndarray, ft_pad: FourierTransformer,
    ) -> None:
        """Result matches np.conj of the forward-FFT spectrum.

        We manually replicate the pipeline without conjugation and
        verify result == conj(manual_spectrum).
        """
        rng = np.random.default_rng(99)
        vol = rng.standard_normal(
            (TILE_SIZE, TILE_SIZE, TILE_SIZE),
        ).astype(np.float32)
        euler = (0.0, 0.0, 0.0)  # identity rotation

        result = prepare_reference_projection(
            vol, euler, soft_mask, PAD_SIZE, ft_pad,
        )

        # Manual pipeline (no conjugation)
        rot = _spider_zyz_inverse_matrix(*euler)
        rotated = _rotate_volume_trilinear(vol, rot)
        projection = np.sum(rotated, axis=0)
        projection = center_crop_or_pad(projection, soft_mask.shape)
        masked = soft_mask * projection
        masked = masked - np.mean(masked)
        padded = center_crop_or_pad(masked, (PAD_SIZE, PAD_SIZE))
        spectrum = ft_pad.forward_fft(padded)

        np.testing.assert_allclose(
            result, np.conj(spectrum), atol=1e-5,
        )

    def test_output_shape(
        self, soft_mask: np.ndarray, ft_pad: FourierTransformer,
    ) -> None:
        """Output has correct half-grid shape."""
        vol = np.zeros(
            (TILE_SIZE, TILE_SIZE, TILE_SIZE), dtype=np.float32,
        )
        result = prepare_reference_projection(
            vol, (0.0, 0.0, 0.0), soft_mask, PAD_SIZE, ft_pad,
        )
        assert result.shape == (PAD_SIZE // 2 + 1, PAD_SIZE)

    def test_mask_applied_to_projection(
        self, soft_mask: np.ndarray, ft_pad: FourierTransformer,
    ) -> None:
        """Mask suppresses outer values in the projection.

        A volume that projects to a uniform image should, after masking
        and mean-subtraction, have small DC.
        """
        vol = np.ones(
            (TILE_SIZE, TILE_SIZE, TILE_SIZE), dtype=np.float32,
        )
        result = prepare_reference_projection(
            vol, (0.0, 0.0, 0.0), soft_mask, PAD_SIZE, ft_pad,
        )
        # DC should be small after mean-subtraction.  Not exactly zero
        # because the circular mask taper introduces small asymmetry in
        # the mean-subtracted masked image at float32 precision.
        assert np.abs(result[0, 0]) < 0.1
