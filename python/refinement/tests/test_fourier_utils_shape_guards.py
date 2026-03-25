"""
Tests for shape-validation guards on forward_fft and swap_phase.

These guards reject 2-D arrays whose shape does not match the
transformer's configured dimensions, preventing silent misprocessing
when the caller supplies an image or spectrum of the wrong size.
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
# forward_fft: wrong-shaped 2D input
# ---------------------------------------------------------------------------


class TestForwardFFTShapeGuard:
    """forward_fft rejects 2-D arrays whose shape != (nx, ny)."""

    def test_raises_on_wrong_rows(self, ft: FourierTransformer) -> None:
        """Extra row should be caught."""
        wrong = np.zeros((NX + 1, NY), dtype=np.float64)
        with pytest.raises(ValueError, match="does not match"):
            ft.forward_fft(wrong)

    def test_raises_on_wrong_cols(self, ft: FourierTransformer) -> None:
        """Extra column should be caught."""
        wrong = np.zeros((NX, NY + 1), dtype=np.float64)
        with pytest.raises(ValueError, match="does not match"):
            ft.forward_fft(wrong)

    def test_raises_on_half_grid_shape(self, ft: FourierTransformer) -> None:
        """Passing the half-grid shape to forward_fft is an error."""
        wrong = np.zeros((NX // 2 + 1, NY), dtype=np.float64)
        with pytest.raises(ValueError, match="does not match"):
            ft.forward_fft(wrong)

    def test_accepts_correct_shape(self, ft: FourierTransformer) -> None:
        """Positive control: correct (nx, ny) shape succeeds."""
        correct = np.zeros((NX, NY), dtype=np.float64)
        result = ft.forward_fft(correct)
        assert result.shape == (NX // 2 + 1, NY)


# ---------------------------------------------------------------------------
# swap_phase: wrong-shaped 2D input
# ---------------------------------------------------------------------------


class TestSwapPhaseShapeGuard:
    """swap_phase rejects 2-D arrays that match neither (nx, ny) nor (half_nx, ny)."""

    def test_raises_on_arbitrary_shape(self, ft: FourierTransformer) -> None:
        """A shape that matches neither real-space nor half-grid."""
        wrong = np.zeros((NX + 5, NY + 3), dtype=np.float64)
        with pytest.raises(ValueError, match="does not match"):
            ft.swap_phase(wrong)

    def test_raises_on_transposed_half_grid(self, ft: FourierTransformer) -> None:
        """Transposed half-grid (ny, half_nx) should be rejected."""
        wrong = np.zeros((NY, NX // 2 + 1), dtype=np.float64)
        with pytest.raises(ValueError, match="does not match"):
            ft.swap_phase(wrong)

    def test_accepts_real_space_shape(self, ft: FourierTransformer) -> None:
        """Positive control: real-space (nx, ny) succeeds."""
        correct = np.ones((NX, NY), dtype=np.float64)
        result = ft.swap_phase(correct)
        assert result.shape == (NX, NY)

    def test_accepts_half_grid_shape(self, ft: FourierTransformer) -> None:
        """Positive control: half-grid (half_nx, ny) succeeds."""
        correct = np.ones((NX // 2 + 1, NY), dtype=np.float64)
        result = ft.swap_phase(correct)
        assert result.shape == (NX // 2 + 1, NY)
