"""
Tests for FourierTransformer.

Validates the Python port of testScripts/fourierTransformer.m against
analytical expectations and behavioral acceptance criteria.  Each test
class maps to a specific acceptance criterion or behavioral contract.
"""

from __future__ import annotations

import numpy as np
import pytest

from ..emc_fourier_utils import HAS_CUPY, FourierTransformer, _xp_for

if HAS_CUPY:
    import cupy as cp


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

NX, NY = 256, 256
PIXEL_SIZE = 1.0  # Angstroms, for simplicity in bandpass tests


@pytest.fixture()
def ft() -> FourierTransformer:
    """Standard 256x256 transformer (CPU)."""
    return FourierTransformer(NX, NY, use_gpu=False)


# ---------------------------------------------------------------------------
# Test: inv_trim property
# ---------------------------------------------------------------------------


class TestInvTrim:
    """inv_trim equals 1 for standard half-grid layout."""

    def test_inv_trim_is_one(self, ft: FourierTransformer) -> None:
        """Acceptance criterion: inv_trim property equals 1."""
        assert ft.inv_trim == 1

    def test_inv_trim_is_one_non_square(self) -> None:
        """inv_trim is 1 regardless of image dimensions."""
        ft_rect = FourierTransformer(128, 64, use_gpu=False)
        assert ft_rect.inv_trim == 1


# ---------------------------------------------------------------------------
# Test: forward_fft
# ---------------------------------------------------------------------------


class TestForwardFFT:
    """Forward FFT of single-frequency cosine produces correct peak."""

    def test_cosine_peak_position(self, ft: FourierTransformer) -> None:
        """Acceptance criterion: peak at correct position for frequency-10 cosine.

        Tests a 256x256 image. A cosine with frequency k=10 along axis 0:
            cos(2*pi*10*x/256)
        should produce peaks at frequency index 10 along the halved axis.
        """
        x = np.arange(NX, dtype=np.float64)
        freq_idx = 10
        image = np.cos(2.0 * np.pi * freq_idx * x / NX)[:, None] * np.ones(
            (1, NY), dtype=np.float64
        )

        spectrum = ft.forward_fft(image)

        # Output shape is (nx//2+1, ny)
        assert spectrum.shape == (NX // 2 + 1, NY)

        # The peak should be at (freq_idx, 0) in the half-grid
        mag = np.abs(spectrum)
        peak_loc = np.unravel_index(np.argmax(mag), mag.shape)
        assert peak_loc == (freq_idx, 0), (
            f"Expected peak at ({freq_idx}, 0), got {peak_loc}"
        )

    def test_cosine_peak_magnitude(self, ft: FourierTransformer) -> None:
        """Peak magnitude matches analytical expectation.

        For rfft2 of cos(2*pi*k*x/N) with N=256, ny=256:
        The peak at (k, 0) should have magnitude N*ny/2 = 256*256/2 = 32768.
        """
        x = np.arange(NX, dtype=np.float64)
        freq_idx = 10
        image = np.cos(2.0 * np.pi * freq_idx * x / NX)[:, None] * np.ones(
            (1, NY), dtype=np.float64
        )

        spectrum = ft.forward_fft(image)
        peak_mag = np.abs(spectrum[freq_idx, 0])
        expected_mag = NX * NY / 2.0

        np.testing.assert_allclose(peak_mag, expected_mag, rtol=1e-10)

    def test_output_shape_non_square(self) -> None:
        """Half-grid shape is (nx//2+1, ny) for non-square input."""
        ft_rect = FourierTransformer(128, 64, use_gpu=False)
        image = np.random.randn(128, 64)
        spectrum = ft_rect.forward_fft(image)
        assert spectrum.shape == (65, 64)

    def test_raises_on_non_2d(self, ft: FourierTransformer) -> None:
        """Negative control: forward_fft raises on non-2D input."""
        with pytest.raises(ValueError, match="2-D"):
            ft.forward_fft(np.zeros((NX, NY, 3)))

        with pytest.raises(ValueError, match="2-D"):
            ft.forward_fft(np.zeros((NX,)))


# ---------------------------------------------------------------------------
# Test: inverse_fft (round-trip)
# ---------------------------------------------------------------------------


class TestInverseFFT:
    """Inverse FFT recovers original signal within float roundoff."""

    def test_roundtrip_float64(self, ft: FourierTransformer) -> None:
        """Acceptance criterion: relative error < 1e-5 on round-trip."""
        rng = np.random.default_rng(42)
        image = rng.standard_normal((NX, NY))

        spectrum = ft.forward_fft(image)
        recovered = ft.inverse_fft(spectrum)

        np.testing.assert_allclose(recovered, image, rtol=1e-10)

    def test_roundtrip_float32(self, ft: FourierTransformer) -> None:
        """Round-trip with float32 stays within spec (relative error < 1e-5).

        numpy.fft computes internally in float64, so the recovered array
        is float64.  Near-zero values have large *relative* error but
        tiny absolute error.  We add atol=1e-6 (well within float32
        machine epsilon x sqrt(N)) to handle the near-zero case.
        """
        rng = np.random.default_rng(99)
        image = rng.standard_normal((NX, NY)).astype(np.float32)

        spectrum = ft.forward_fft(image)
        recovered = ft.inverse_fft(spectrum)

        np.testing.assert_allclose(
            recovered, image, rtol=1e-5, atol=1e-6,
            err_msg="float32 round-trip exceeded tolerance"
        )

    def test_roundtrip_non_square(self) -> None:
        """Round-trip works for non-square images."""
        ft_rect = FourierTransformer(128, 64, use_gpu=False)
        rng = np.random.default_rng(7)
        image = rng.standard_normal((128, 64))
        recovered = ft_rect.inverse_fft(ft_rect.forward_fft(image))
        np.testing.assert_allclose(recovered, image, rtol=1e-10)


# ---------------------------------------------------------------------------
# Test: swap_phase
# ---------------------------------------------------------------------------


class TestSwapPhase:
    """swap_phase produces centered DC when applied before inverse FFT."""

    def test_checkerboard_pattern(self, ft: FourierTransformer) -> None:
        """The checkerboard is (-1)^(i+j) — alternates ±1."""
        # Apply to an all-ones array to extract the checkerboard
        ones = np.ones((NX // 2 + 1, NY))
        cb = ft.swap_phase(ones)
        # Corners: (0,0)→+1, (0,1)→-1, (1,0)→-1, (1,1)→+1
        assert cb[0, 0] == pytest.approx(1.0)
        assert cb[0, 1] == pytest.approx(-1.0)
        assert cb[1, 0] == pytest.approx(-1.0)
        assert cb[1, 1] == pytest.approx(1.0)

    def test_dc_centered_after_swap_and_ifft(
        self, ft: FourierTransformer
    ) -> None:
        """Acceptance criterion: DC at image center after swap + inverse.

        A delta function at the origin has a *flat* spectrum (all ones).
        Applying the checkerboard multiplies every frequency bin by
        (-1)^(i+j), and the inverse FFT of that is a delta shifted to
        (NX/2, NY/2) — confirming the swap centers the origin.
        """
        delta = np.zeros((NX, NY), dtype=np.float64)
        delta[0, 0] = 1.0
        spectrum = ft.forward_fft(delta)

        swapped = ft.swap_phase(spectrum)
        result = ft.inverse_fft(swapped)

        # Peak should be at the center of the image
        peak_loc = np.unravel_index(np.argmax(np.abs(result)), result.shape)
        center = (NX // 2, NY // 2)
        assert peak_loc == center, (
            f"Expected peak at center {center}, got {peak_loc}"
        )

    def test_swap_equivalent_to_fftshift(
        self, ft: FourierTransformer
    ) -> None:
        """swap_phase + inverse_fft equals inverse_fft + np.fft.fftshift.

        This is the defining property: multiplying a half-grid spectrum
        by (-1)^(i+j) before inverse FFT is equivalent to applying
        fftshift to the real-space result of the un-swapped inverse.
        """
        rng = np.random.default_rng(33)
        image = rng.standard_normal((NX, NY))
        spectrum = ft.forward_fft(image)

        # Path 1: swap then inverse
        result_swap = ft.inverse_fft(ft.swap_phase(spectrum))
        # Path 2: inverse then fftshift
        result_shift = np.fft.fftshift(ft.inverse_fft(spectrum))

        np.testing.assert_allclose(result_swap, result_shift, atol=1e-12)

    def test_double_swap_is_identity(self, ft: FourierTransformer) -> None:
        """Applying swap_phase twice recovers the original spectrum."""
        rng = np.random.default_rng(12)
        spectrum = rng.standard_normal((NX // 2 + 1, NY)) + 1j * rng.standard_normal(
            (NX // 2 + 1, NY)
        )
        double_swapped = ft.swap_phase(ft.swap_phase(spectrum))
        np.testing.assert_allclose(double_swapped, spectrum, atol=1e-14)


# ---------------------------------------------------------------------------
# Test: apply_bandpass
# ---------------------------------------------------------------------------


class TestApplyBandpass:
    """Bandpass filter zeroes outside and preserves inside the passband."""

    def test_invalid_range_raises(self, ft: FourierTransformer) -> None:
        """Acceptance criterion: ValueError when highpass <= lowpass."""
        spectrum = np.ones((NX // 2 + 1, NY), dtype=complex)
        with pytest.raises(ValueError, match="must be greater"):
            ft.apply_bandpass(spectrum, PIXEL_SIZE, 10.0, 10.0)  # equal
        with pytest.raises(ValueError, match="must be greater"):
            ft.apply_bandpass(spectrum, PIXEL_SIZE, 5.0, 10.0)   # hp < lp

    def test_interior_unchanged(self, ft: FourierTransformer) -> None:
        """Frequencies well inside the passband are not attenuated.

        With pixel_size=1.0 Å for a 256x256 image, frequency index k
        has resolution 256/k Å.  Passband [8, 128] Å corresponds to
        frequency indices ~[2, 32].  Index 16 (resolution=16 Å) is
        well inside the band.
        """
        highpass = 128.0  # 128 Å resolution (low freq edge)
        lowpass = 8.0     #   8 Å resolution (high freq edge)

        # Place a spike at (16, 0) — resolution = 256/16 = 16 Å, inside band
        spectrum = np.zeros((NX // 2 + 1, NY), dtype=complex)
        spectrum[16, 0] = 1.0 + 0.0j

        filtered = ft.apply_bandpass(spectrum, PIXEL_SIZE, highpass, lowpass)
        # Should be unchanged (mask ≈ 1.0 at this frequency)
        np.testing.assert_allclose(
            np.abs(filtered[16, 0]), 1.0, atol=1e-10,
            err_msg="Interior frequency was attenuated"
        )

    def test_exterior_zeroed(self, ft: FourierTransformer) -> None:
        """Frequencies outside the passband are zeroed.

        Frequency index 2 → resolution 128 Å → outside highpass at 64 Å.
        Frequency index 100 → resolution 2.56 Å → outside lowpass at 4 Å.
        """
        highpass = 64.0
        lowpass = 4.0

        spectrum = np.zeros((NX // 2 + 1, NY), dtype=complex)
        # Below highpass: index 2 → resolution = 256/2 = 128 Å > 64 Å (blocked)
        spectrum[2, 0] = 1.0 + 0.0j
        # Above lowpass: index 100 → resolution = 256/100 = 2.56 Å < 4 Å (blocked)
        spectrum[100, 0] = 1.0 + 0.0j

        filtered = ft.apply_bandpass(spectrum, PIXEL_SIZE, highpass, lowpass)

        assert np.abs(filtered[2, 0]) < 1e-10, "Low-freq component not zeroed"
        assert np.abs(filtered[100, 0]) < 1e-10, "High-freq component not zeroed"

    def test_dc_zeroed(self, ft: FourierTransformer) -> None:
        """DC component (index 0,0) is always zeroed by the highpass."""
        highpass = 200.0
        lowpass = 5.0
        spectrum = np.ones((NX // 2 + 1, NY), dtype=complex)

        filtered = ft.apply_bandpass(spectrum, PIXEL_SIZE, highpass, lowpass)
        assert np.abs(filtered[0, 0]) < 1e-10, "DC was not zeroed"

    def test_cosine_rolloff_is_soft(self, ft: FourierTransformer) -> None:
        """The edge region uses soft cosine rolloff, not a hard cutoff.

        Near the lowpass edge, mask values should be strictly between 0
        and 1, confirming the cosine taper.
        """
        highpass = 128.0
        lowpass = 8.0

        # Lowpass cutoff freq: 1/8 = 0.125 Å⁻¹
        # Rolloff width: 2/(256*1.0) = 0.0078125 Å⁻¹
        # Frequency at the edge center: ~0.125 Å⁻¹ → index 32
        # Within the rolloff band [0.125, 0.125+0.0078] some mask values
        # should be strictly between 0 and 1.
        spectrum = np.ones((NX // 2 + 1, NY), dtype=complex)
        filtered = ft.apply_bandpass(spectrum, PIXEL_SIZE, highpass, lowpass)
        mask_col0 = np.abs(filtered[:, 0])

        # Find values in (0.01, 0.99) — these are the soft-edge pixels
        soft_edge = (mask_col0 > 0.01) & (mask_col0 < 0.99)
        assert np.any(soft_edge), "No soft-edge values found — rolloff may be hard"


# ---------------------------------------------------------------------------
# Test: compute_ref_norm
# ---------------------------------------------------------------------------


class TestComputeRefNorm:
    """compute_ref_norm matches sqrt(2*sum(|X[:-1,:]|^2)) for known input."""

    def test_known_value(self, ft: FourierTransformer) -> None:
        """Acceptance criterion: correct value for known input."""
        rng = np.random.default_rng(77)
        ref = rng.standard_normal((NX // 2 + 1, NY)) + 1j * rng.standard_normal(
            (NX // 2 + 1, NY)
        )

        expected = np.sqrt(2.0 * np.sum(np.abs(ref[:-1, :]) ** 2))
        result = ft.compute_ref_norm(ref)

        np.testing.assert_allclose(result, expected, rtol=1e-12)

    def test_all_ones(self, ft: FourierTransformer) -> None:
        """Sanity check: all-ones array gives sqrt(2 * (half_nx-1) * ny)."""
        ref = np.ones((NX // 2 + 1, NY), dtype=complex)
        n_elements = (NX // 2 + 1 - 1) * NY  # exclude last row
        expected = np.sqrt(2.0 * n_elements)
        result = ft.compute_ref_norm(ref)
        np.testing.assert_allclose(result, expected, rtol=1e-12)

    def test_positive_result(self, ft: FourierTransformer) -> None:
        """Norm is always non-negative."""
        ref = np.zeros((NX // 2 + 1, NY), dtype=complex)
        assert ft.compute_ref_norm(ref) >= 0.0


# ---------------------------------------------------------------------------
# Test: GPU/CPU equivalence (skip when CuPy unavailable)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_CUPY, reason="CuPy not available")
class TestGpuCpuEquivalence:
    """GPU and CPU paths produce identical results."""

    def test_forward_fft_gpu_cpu(self) -> None:
        """Acceptance criterion: GPU and CPU forward FFT match."""
        ft_obj = FourierTransformer(NX, NY, use_gpu=True)
        rng = np.random.default_rng(55)
        image_np = rng.standard_normal((NX, NY))
        image_cp = cp.asarray(image_np)

        spec_np = ft_obj.forward_fft(image_np)
        spec_cp = ft_obj.forward_fft(image_cp)

        np.testing.assert_allclose(
            cp.asnumpy(spec_cp), spec_np, rtol=1e-12
        )

    def test_inverse_fft_gpu_cpu(self) -> None:
        """GPU and CPU inverse FFT match."""
        ft_obj = FourierTransformer(NX, NY, use_gpu=True)
        rng = np.random.default_rng(56)
        spectrum_np = rng.standard_normal((NX // 2 + 1, NY)) + 1j * rng.standard_normal(
            (NX // 2 + 1, NY)
        )
        spectrum_cp = cp.asarray(spectrum_np)

        result_np = ft_obj.inverse_fft(spectrum_np)
        result_cp = ft_obj.inverse_fft(spectrum_cp)

        np.testing.assert_allclose(
            cp.asnumpy(result_cp), result_np, rtol=1e-10
        )

    def test_swap_phase_gpu_cpu(self) -> None:
        """GPU and CPU swap_phase match."""
        ft_obj = FourierTransformer(NX, NY, use_gpu=True)
        rng = np.random.default_rng(57)
        spectrum_np = rng.standard_normal((NX // 2 + 1, NY))
        spectrum_cp = cp.asarray(spectrum_np)

        result_np = ft_obj.swap_phase(spectrum_np)
        result_cp = ft_obj.swap_phase(spectrum_cp)

        np.testing.assert_allclose(
            cp.asnumpy(result_cp), result_np, atol=1e-14
        )

    def test_compute_ref_norm_gpu_cpu(self) -> None:
        """GPU and CPU compute_ref_norm match."""
        ft_obj = FourierTransformer(NX, NY, use_gpu=True)
        rng = np.random.default_rng(58)
        ref_np = rng.standard_normal((NX // 2 + 1, NY)) + 1j * rng.standard_normal(
            (NX // 2 + 1, NY)
        )
        ref_cp = cp.asarray(ref_np)

        norm_np = ft_obj.compute_ref_norm(ref_np)
        norm_cp = ft_obj.compute_ref_norm(ref_cp)

        np.testing.assert_allclose(norm_cp, norm_np, rtol=1e-10)

    def test_apply_bandpass_gpu_cpu(self) -> None:
        """GPU and CPU apply_bandpass match."""
        ft_obj = FourierTransformer(NX, NY, use_gpu=True)
        rng = np.random.default_rng(59)
        spectrum_np = rng.standard_normal((NX // 2 + 1, NY)) + 1j * rng.standard_normal(
            (NX // 2 + 1, NY)
        )
        spectrum_cp = cp.asarray(spectrum_np)

        result_np = ft_obj.apply_bandpass(spectrum_np, 1.0, 128.0, 8.0)
        result_cp = ft_obj.apply_bandpass(spectrum_cp, 1.0, 128.0, 8.0)

        np.testing.assert_allclose(
            cp.asnumpy(result_cp), result_np, rtol=1e-10
        )


# ---------------------------------------------------------------------------
# Test: Array dispatch uses isinstance, NOT get_array_module
# ---------------------------------------------------------------------------


class TestArrayDispatch:
    """Acceptance criterion: dispatch uses isinstance(x, cp.ndarray)."""

    def test_xp_for_numpy(self) -> None:
        """Numpy array dispatches to numpy module."""
        arr = np.zeros(5)
        assert _xp_for(arr) is np

    @pytest.mark.skipif(not HAS_CUPY, reason="CuPy not available")
    def test_xp_for_cupy(self) -> None:
        """Cupy array dispatches to cupy module."""
        arr = cp.zeros(5)
        assert _xp_for(arr) is cp
