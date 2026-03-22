"""
Tests for defect-fix guards added to FourierTransformer.

Covers:
- Dimensionality validation on inverse_fft and compute_ref_norm (defect 4)
- Shape validation on apply_bandpass (defect 3)
- compute_ref_norm behavior when inv_trim == 0 (defect 6)
"""

from __future__ import annotations

import numpy as np
import pytest

from ..emc_fourier_utils import FourierTransformer


NX, NY = 64, 64


@pytest.fixture()
def ft() -> FourierTransformer:
    """Standard 64x64 transformer (CPU)."""
    return FourierTransformer(NX, NY, use_gpu=False)


# ---------------------------------------------------------------------------
# Defect 4: inverse_fft dimensionality guard
# ---------------------------------------------------------------------------


class TestInverseFFTDimGuard:
    """inverse_fft rejects non-2D input."""

    def test_raises_on_3d(self, ft: FourierTransformer) -> None:
        spectrum_3d = np.zeros((NX // 2 + 1, NY, 3), dtype=complex)
        with pytest.raises(ValueError, match="2-D"):
            ft.inverse_fft(spectrum_3d)

    def test_raises_on_1d(self, ft: FourierTransformer) -> None:
        spectrum_1d = np.zeros((NX // 2 + 1,), dtype=complex)
        with pytest.raises(ValueError, match="2-D"):
            ft.inverse_fft(spectrum_1d)

    def test_accepts_2d(self, ft: FourierTransformer) -> None:
        """Positive control: valid 2-D input succeeds."""
        spectrum = np.zeros((NX // 2 + 1, NY), dtype=complex)
        result = ft.inverse_fft(spectrum)
        assert result.shape == (NX, NY)


# ---------------------------------------------------------------------------
# Defect 4: compute_ref_norm dimensionality guard
# ---------------------------------------------------------------------------


class TestComputeRefNormDimGuard:
    """compute_ref_norm rejects non-2D input."""

    def test_raises_on_3d(self, ft: FourierTransformer) -> None:
        ref_3d = np.ones((NX // 2 + 1, NY, 2), dtype=complex)
        with pytest.raises(ValueError, match="2-D"):
            ft.compute_ref_norm(ref_3d)

    def test_raises_on_1d(self, ft: FourierTransformer) -> None:
        ref_1d = np.ones((NX // 2 + 1,), dtype=complex)
        with pytest.raises(ValueError, match="2-D"):
            ft.compute_ref_norm(ref_1d)

    def test_accepts_2d(self, ft: FourierTransformer) -> None:
        """Positive control: valid 2-D input succeeds."""
        ref = np.ones((NX // 2 + 1, NY), dtype=complex)
        result = ft.compute_ref_norm(ref)
        assert result > 0.0


# ---------------------------------------------------------------------------
# Defect 3: apply_bandpass shape validation
# ---------------------------------------------------------------------------


class TestBandpassShapeValidation:
    """apply_bandpass rejects spectra whose shape mismatches the transformer."""

    def test_raises_on_wrong_shape(self, ft: FourierTransformer) -> None:
        """Spectrum shape (65, 128) does not match transformer (33, 64)."""
        wrong_spectrum = np.ones((65, 128), dtype=complex)
        with pytest.raises(ValueError, match="does not match"):
            ft.apply_bandpass(wrong_spectrum, 1.0, 128.0, 8.0)

    def test_raises_on_swapped_dims(self, ft: FourierTransformer) -> None:
        """Transposed shape should also be rejected."""
        # Shape (NY, NX//2+1) instead of (NX//2+1, NY)
        wrong_spectrum = np.ones((NY, NX // 2 + 1), dtype=complex)
        with pytest.raises(ValueError, match="does not match"):
            ft.apply_bandpass(wrong_spectrum, 1.0, 128.0, 8.0)

    def test_accepts_correct_shape(self, ft: FourierTransformer) -> None:
        """Positive control: correct shape succeeds."""
        spectrum = np.ones((NX // 2 + 1, NY), dtype=complex)
        result = ft.apply_bandpass(spectrum, 1.0, 128.0, 8.0)
        assert result.shape == spectrum.shape


# ---------------------------------------------------------------------------
# Defect 6: compute_ref_norm with inv_trim == 0
# ---------------------------------------------------------------------------


class TestComputeRefNormInvTrimZero:
    """compute_ref_norm handles inv_trim == 0 without silent-zero bug."""

    def test_inv_trim_zero_uses_all_rows(self) -> None:
        """When inv_trim == 0, all rows contribute to the energy sum.

        With inv_trim == 0, the result should be sqrt(2 * sum(|x|^2))
        over the ENTIRE array (no rows excluded).
        """
        ft = FourierTransformer(NX, NY, use_gpu=False)
        ft._inv_trim = 0  # Override for testing

        ref = np.ones((NX // 2 + 1, NY), dtype=complex)
        result = ft.compute_ref_norm(ref)

        n_elements = (NX // 2 + 1) * NY
        expected = np.sqrt(2.0 * n_elements)
        np.testing.assert_allclose(result, expected, rtol=1e-12)

    def test_inv_trim_zero_vs_one_difference(self) -> None:
        """inv_trim == 0 includes the last row that inv_trim == 1 excludes.

        Negative control: the two values should differ by the energy
        contribution of the last row.
        """
        rng = np.random.default_rng(42)
        ref = rng.standard_normal((NX // 2 + 1, NY)) + 1j * rng.standard_normal(
            (NX // 2 + 1, NY)
        )

        ft_trim1 = FourierTransformer(NX, NY, use_gpu=False)
        ft_trim0 = FourierTransformer(NX, NY, use_gpu=False)
        ft_trim0._inv_trim = 0

        norm_trim1 = ft_trim1.compute_ref_norm(ref)
        norm_trim0 = ft_trim0.compute_ref_norm(ref)

        # trim0 includes the last row, so should be larger
        assert norm_trim0 > norm_trim1
