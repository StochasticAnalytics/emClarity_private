"""Regression test for the pipeline-level NaN score guard.

The guard at ``emc_refine_tilt_ctf.py`` lines 385-400 catches non-finite
``total_score`` returned by ``evaluate_score_and_gradient`` and:

  (a) sets ``nan_break = True`` (aborting the optimisation loop),
  (b) prevents ``optimizer.step()`` from being called,
  (c) sanitises ``per_particle_scores`` and ``shifts_xy`` to 0.0.

Positive control — finite score:  ``optimizer.step()`` IS called.
Negative control — NaN score:     ``optimizer.step()`` is NOT called,
                                  outputs are sanitised, and the abort
                                  warning is emitted.
"""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ...ctf.emc_ctf_cpu import CTFCalculatorCPU
from ...ctf.emc_ctf_params import CTFParams
from ..emc_fourier_utils import FourierTransformer
from ..emc_refine_tilt_ctf import (
    RefinementOptions,
    refine_tilt_ctf,
)
from ..emc_scoring import create_peak_mask

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NX, NY = 64, 64
PIXEL_SIZE = 1.5  # Angstroms
WAVELENGTH = 0.0197  # 300 kV
N_PARTICLES = 3


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ft() -> FourierTransformer:
    """Standard 64x64 CPU FourierTransformer."""
    return FourierTransformer(NX, NY, use_gpu=False)


@pytest.fixture()
def base_ctf() -> CTFParams:
    return CTFParams.from_defocus_pair(
        df1=20000.0,
        df2=18000.0,
        angle_degrees=45.0,
        pixel_size=PIXEL_SIZE,
        wavelength=WAVELENGTH,
        cs_mm=2.7,
        amplitude_contrast=0.07,
    )


@pytest.fixture()
def peak_mask() -> np.ndarray:
    return create_peak_mask(NX, NY, radius=float(NX // 4))


@pytest.fixture()
def dummy_fts() -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Minimal valid FTs — content is irrelevant since evaluate is mocked."""
    half_nx = NX // 2 + 1
    data = [np.zeros((half_nx, NY), dtype=np.complex64) for _ in range(N_PARTICLES)]
    refs = [np.zeros((half_nx, NY), dtype=np.complex64) for _ in range(N_PARTICLES)]
    return data, refs


def _make_mock_optimizer(n_params: int) -> MagicMock:
    """Create a mock optimizer with working ``get_current_parameters``."""
    mock = MagicMock()
    mock.get_current_parameters.return_value = np.zeros(n_params, dtype=np.float64)
    mock.has_converged.return_value = False
    return mock


# ---------------------------------------------------------------------------
# Negative control: NaN score aborts optimisation
# ---------------------------------------------------------------------------


class TestNanScoreTriggersNanBreak:
    """Verify the NaN-score guard aborts optimisation correctly (KI-218).

    The guard uses ``not np.isfinite()``, which catches NaN *and* ±inf.
    All three non-finite values are exercised via parametrize below.
    """

    @pytest.mark.parametrize(
        "bad_score",
        [float("nan"), float("inf"), float("-inf")],
        ids=["nan", "+inf", "-inf"],
    )
    def test_nan_score_triggers_nan_break(
        self,
        bad_score: float,
        ft: FourierTransformer,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
        dummy_fts: tuple[list[np.ndarray], list[np.ndarray]],
    ) -> None:
        """Verify a non-finite total_score triggers the abort guard.

        (a) nan_break is set -- converged=False + abort warning emitted,
        (b) optimizer.step() is never called,
        (c) per_particle_scores and shifts are sanitised to 0.0.
        """
        data_fts, ref_fts = dummy_fts
        n = len(data_fts)
        # 3 tilt-global params (delta_defocus, half_astig, angle) + N per-particle z-offsets
        n_params = 3 + n

        # evaluate returns a non-finite score with non-finite per-particle arrays
        bad_return = (
            bad_score,
            np.full(n, bad_score),
            np.full((n, 2), bad_score),
            np.zeros(n_params, dtype=np.float64),  # gradient (unused on abort)
        )

        mock_optimizer = _make_mock_optimizer(n_params)

        options = RefinementOptions(
            optimizer_type="adam",
            maximum_iterations=5,
        )

        with (
            patch(
                "python.refinement.emc_refine_tilt_ctf.evaluate_score_and_gradient",
                return_value=bad_return,
            ),
            patch(
                "python.refinement.emc_refine_tilt_ctf._create_adam_optimizer",
                return_value=mock_optimizer,
            ),
            # Captures UserWarning emitted via warnings.warn() inside the NaN guard
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            result = refine_tilt_ctf(
                data_fts,
                ref_fts,
                base_ctf,
                0.0,
                options,
                ctf_calculator=CTFCalculatorCPU(),
                fourier_handler=ft,
                peak_mask=peak_mask,
            )

        # (a) nan_break was set — converged is False, abort warning emitted
        assert result.converged is False
        nan_warnings = [
            w for w in caught if "non-finite score" in str(w.message).lower()
        ]
        assert len(nan_warnings) == 1, (
            f"Expected 1 non-finite score warning, got {len(nan_warnings)}: "
            f"{[str(w.message) for w in caught]}"
        )

        # (b) optimizer.step() was never called
        mock_optimizer.step.assert_not_called()

        # (c) per_particle_scores sanitised to 0.0 (non-finite replaced)
        assert np.all(np.isfinite(result.per_particle_scores))
        np.testing.assert_array_equal(result.per_particle_scores, 0.0)

        # shifts sanitised to 0.0
        assert np.all(np.isfinite(result.shift_x))
        assert np.all(np.isfinite(result.shift_y))
        np.testing.assert_array_equal(result.shift_x, 0.0)
        np.testing.assert_array_equal(result.shift_y, 0.0)


# ---------------------------------------------------------------------------
# Positive control: finite score proceeds normally
# ---------------------------------------------------------------------------


class TestFiniteScoreCallsStep:
    """Positive control: when score is finite, optimizer.step() IS called."""

    def test_finite_score_calls_step(
        self,
        ft: FourierTransformer,
        base_ctf: CTFParams,
        peak_mask: np.ndarray,
        dummy_fts: tuple[list[np.ndarray], list[np.ndarray]],
    ) -> None:
        """A finite score must reach optimizer.step() — proves mock wiring works."""
        data_fts, ref_fts = dummy_fts
        n = len(data_fts)
        # 3 tilt-global params (delta_defocus, half_astig, angle) + N per-particle z-offsets
        n_params = 3 + n

        finite_return = (
            0.5,  # finite total_score
            np.full(n, 0.5),
            np.zeros((n, 2)),
            np.zeros(n_params, dtype=np.float64),
        )

        mock_optimizer = _make_mock_optimizer(n_params)
        # Converge after first step to keep test fast
        mock_optimizer.has_converged.return_value = True

        options = RefinementOptions(
            optimizer_type="adam",
            maximum_iterations=5,
        )

        with (
            patch(
                "python.refinement.emc_refine_tilt_ctf.evaluate_score_and_gradient",
                return_value=finite_return,
            ),
            patch(
                "python.refinement.emc_refine_tilt_ctf._create_adam_optimizer",
                return_value=mock_optimizer,
            ),
        ):
            result = refine_tilt_ctf(
                data_fts,
                ref_fts,
                base_ctf,
                0.0,
                options,
                ctf_calculator=CTFCalculatorCPU(),
                fourier_handler=ft,
                peak_mask=peak_mask,
            )

        # optimizer.step() was called (at least once)
        assert mock_optimizer.step.call_count >= 1
        assert result.converged is True
