"""Regression tests for zero-particle handling (KI-280).

KI-280 reported a crash when a tilt group contains zero particles.
Guards exist at ``emc_scoring.py`` line 179 and ``emc_ctf_gradients.py``
line 161.  These tests verify that both functions return well-typed
empty results instead of crashing.

Test organisation
~~~~~~~~~~~~~~~~~
* **TestZeroParticlesScoring** — empty ``data_fts``/``ref_fts`` returns
  ``(0.0, array(shape=(0,)), array(shape=(0, 2)))``
* **TestZeroParticlesGradient** — empty lists return 4-tuple with
  ``gradient.shape == (3,)``
"""

from __future__ import annotations

import numpy as np
import pytest

from ...ctf.emc_ctf_cpu import CTFCalculatorCPU
from ...ctf.emc_ctf_params import CTFParams
from ..emc_ctf_gradients import evaluate_score_and_gradient
from ..emc_fourier_utils import FourierTransformer
from ..emc_scoring import create_peak_mask, evaluate_score_and_shifts

# ---------------------------------------------------------------------------
# Constants (match existing test modules)
# ---------------------------------------------------------------------------

NX, NY = 64, 64
PIXEL_SIZE = 1.5  # Angstroms
WAVELENGTH = 0.0197  # Angstroms (300 kV)
CS_MM = 2.7
AMP_CONTRAST = 0.07
DF1 = 20000.0  # Angstroms
DF2 = 18000.0  # Angstroms
ANGLE_DEG = 45.0
SEARCH_RADIUS = NX // 4  # 16 pixels


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ft() -> FourierTransformer:
    """Standard 64x64 CPU FourierTransformer."""
    return FourierTransformer(NX, NY, use_gpu=False)


@pytest.fixture()
def ctf_calc() -> CTFCalculatorCPU:
    return CTFCalculatorCPU()


@pytest.fixture()
def base_ctf() -> CTFParams:
    return CTFParams.from_defocus_pair(
        df1=DF1,
        df2=DF2,
        angle_degrees=ANGLE_DEG,
        pixel_size=PIXEL_SIZE,
        wavelength=WAVELENGTH,
        cs_mm=CS_MM,
        amplitude_contrast=AMP_CONTRAST,
    )


@pytest.fixture()
def peak_mask() -> np.ndarray:
    return create_peak_mask(NX, NY, radius=SEARCH_RADIUS)


# =========================================================================
# Test: Zero-particle scoring (KI-280 regression)
# =========================================================================


class TestZeroParticlesScoring:
    """Empty data_fts/ref_fts must return well-typed zero results.

    Hypothesis: when a tilt group has zero particles, ``evaluate_score_and_shifts``
    returns ``(0.0, array(shape=(0,)), array(shape=(0, 2)))`` without raising.
    """

    def test_returns_without_error(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Zero-particle call must not raise."""
        params = np.zeros(3)  # 3 global deltas, 0 per-particle
        evaluate_score_and_shifts(
            params=params,
            data_fts=[],
            ref_fts=[],
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )

    def test_total_score_is_zero(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Total score must be exactly 0.0 with no particles."""
        params = np.zeros(3)
        total_score, _, _ = evaluate_score_and_shifts(
            params=params,
            data_fts=[],
            ref_fts=[],
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )
        assert total_score == 0.0, f"Expected 0.0, got {total_score}"

    def test_per_particle_scores_shape(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Per-particle scores array must have shape (0,)."""
        params = np.zeros(3)
        _, scores, _ = evaluate_score_and_shifts(
            params=params,
            data_fts=[],
            ref_fts=[],
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )
        assert scores.shape == (0,), f"Expected shape (0,), got {scores.shape}"

    def test_shifts_shape(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Shifts array must have shape (0, 2)."""
        params = np.zeros(3)
        _, _, shifts = evaluate_score_and_shifts(
            params=params,
            data_fts=[],
            ref_fts=[],
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )
        assert shifts.shape == (0, 2), f"Expected shape (0, 2), got {shifts.shape}"

    def test_return_dtypes(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Return arrays must be float64, consistent with the non-empty path."""
        params = np.zeros(3)
        total_score, scores, shifts = evaluate_score_and_shifts(
            params=params,
            data_fts=[],
            ref_fts=[],
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )
        assert isinstance(total_score, float)
        assert scores.dtype == np.float64
        assert shifts.dtype == np.float64


# =========================================================================
# Test: Zero-particle gradient (KI-280 regression)
# =========================================================================


class TestZeroParticlesGradient:
    """Empty data_fts/ref_fts must return well-typed 4-tuple with gradient.shape==(3,).

    Hypothesis: when a tilt group has zero particles, ``evaluate_score_and_gradient``
    returns a 4-tuple where gradient has exactly 3 elements (global params only,
    no per-particle entries) and all numerical outputs are zero.
    """

    def test_returns_without_error(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Zero-particle gradient call must not raise."""
        params = np.zeros(3)
        evaluate_score_and_gradient(
            params=params,
            data_fts=[],
            ref_fts=[],
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )

    def test_gradient_shape(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Gradient must have shape (3,) — one entry per global param."""
        params = np.zeros(3)
        _, _, _, gradient = evaluate_score_and_gradient(
            params=params,
            data_fts=[],
            ref_fts=[],
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )
        assert gradient.shape == (3,), f"Expected shape (3,), got {gradient.shape}"

    def test_gradient_is_zero(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Gradient must be all zeros with no particles contributing."""
        params = np.zeros(3)
        _, _, _, gradient = evaluate_score_and_gradient(
            params=params,
            data_fts=[],
            ref_fts=[],
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )
        np.testing.assert_array_equal(
            gradient, np.zeros(3),
            err_msg="Gradient must be zero with no particles",
        )

    def test_total_score_is_zero(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Total score from gradient function must also be 0.0."""
        params = np.zeros(3)
        total_score, _, _, _ = evaluate_score_and_gradient(
            params=params,
            data_fts=[],
            ref_fts=[],
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )
        assert total_score == 0.0, f"Expected 0.0, got {total_score}"

    def test_per_particle_scores_and_shifts_shapes(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Scores and shifts from gradient function must match scoring shapes."""
        params = np.zeros(3)
        _, scores, shifts, _ = evaluate_score_and_gradient(
            params=params,
            data_fts=[],
            ref_fts=[],
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )
        assert scores.shape == (0,), f"Expected scores shape (0,), got {scores.shape}"
        assert shifts.shape == (0, 2), f"Expected shifts shape (0, 2), got {shifts.shape}"

    def test_gradient_dtype(
        self,
        ft: FourierTransformer,
        ctf_calc: CTFCalculatorCPU,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
    ) -> None:
        """Gradient dtype must be float64, consistent with non-empty path."""
        params = np.zeros(3)
        _, _, _, gradient = evaluate_score_and_gradient(
            params=params,
            data_fts=[],
            ref_fts=[],
            base_ctf_params=base_ctf,
            ctf_calculator=ctf_calc,
            fourier_handler=ft,
            tilt_angle_degrees=0.0,
            peak_mask=peak_mask,
        )
        assert gradient.dtype == np.float64
