"""
Tests for CTF calculator (GPU and CPU implementations).

Validates against MATLAB-generated baseline .npy files, verifies
GPU-vs-CPU agreement, checks hand-computed ground-truth values, and
exercises negative controls.

Baseline files live in fixtures/ as .npy arrays with shape
(nx_half, ny) — the MATLAB column-major convention.  We transpose
to (ny, nx_half) before comparing against our row-major output.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ..emc_ctf_params import CTFParams

# ---------------------------------------------------------------------------
# Try to import GPU calculator; skip GPU tests if CuPy unavailable
# ---------------------------------------------------------------------------
try:
    import cupy as cp

    from ..emc_ctf_calculator import CTFCalculator

    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False

from ..emc_ctf_cpu import CTFCalculatorCPU

# ---------------------------------------------------------------------------
# Constants — tolerance budgets
# ---------------------------------------------------------------------------
GPU_VS_MATLAB_ATOL = 1e-4   # GPU vs MATLAB: both use --use_fast_math
CPU_VS_MATLAB_ATOL = 2e-4   # CPU uses standard math, not --use_fast_math
GPU_VS_CPU_RTOL = 1e-5      # GPU vs CPU relative tolerance
GPU_VS_CPU_ATOL = 1e-6      # near-zero absolute tolerance for GPU vs CPU

# ---------------------------------------------------------------------------
# Fixtures path
# ---------------------------------------------------------------------------
FIXTURES_DIR = Path(__file__).parent / "fixtures"
PARAMS_FILE = FIXTURES_DIR / "ctf_baseline_params.json"


def _load_baseline_params() -> dict:
    """Load the JSON that describes every baseline."""
    with open(PARAMS_FILE) as f:
        return json.load(f)


try:
    BASELINE_META = _load_baseline_params()
except FileNotFoundError:
    BASELINE_META = {}
FIXED = BASELINE_META.get("fixed_params", {})


def _make_ctf_params(bl: dict) -> CTFParams:
    """Build a CTFParams from one baseline entry + shared fixed params."""
    return CTFParams.from_defocus_pair(
        df1=bl["df1"],
        df2=bl["df2"],
        angle_degrees=bl["angle_deg"],
        pixel_size=FIXED["pixel_size"],
        wavelength=FIXED["wavelength"],
        cs_mm=FIXED["cs_mm"],
        amplitude_contrast=FIXED["amplitude_contrast"],
        do_half_grid=bl["do_half_grid"],
        do_sq_ctf=bl["do_sq_ctf"],
    )


def _load_baseline_array(index: int) -> np.ndarray:
    """Load a baseline .npy and transpose from (nx_half, ny) to (ny, nx_half)."""
    npy_path = FIXTURES_DIR / f"ctf_baseline_{index:03d}.npy"
    raw = np.load(npy_path)
    # Baselines are stored in MATLAB column-major convention (nx_half, ny).
    # Transpose to our C-contiguous convention (ny, nx_half).
    return raw.T


# ---------------------------------------------------------------------------
# Parameterised baseline IDs
# ---------------------------------------------------------------------------
ALL_BASELINE_IDS = [bl["index"] for bl in BASELINE_META.get("baselines", [])]


def _baseline_by_index(index: int) -> dict:
    for bl in BASELINE_META["baselines"]:
        if bl["index"] == index:
            return bl
    raise KeyError(f"No baseline with index {index}")


# ===================================================================
# CPU baseline tests — always run
# ===================================================================


class TestCPUBaselines:
    """CPU implementation vs MATLAB baselines."""

    @pytest.fixture()
    def cpu_calc(self) -> CTFCalculatorCPU:
        return CTFCalculatorCPU()

    @pytest.mark.parametrize("bl_index", ALL_BASELINE_IDS)
    def test_cpu_matches_baseline(
        self, cpu_calc: CTFCalculatorCPU, bl_index: int
    ) -> None:
        bl = _baseline_by_index(bl_index)
        params = _make_ctf_params(bl)
        expected = _load_baseline_array(bl_index)

        result = cpu_calc.compute(params, dims=(bl["nx"], bl["ny"]))

        assert result.shape == expected.shape, (
            f"Shape mismatch: got {result.shape}, expected {expected.shape}"
        )
        np.testing.assert_allclose(
            result,
            expected,
            atol=CPU_VS_MATLAB_ATOL,
            err_msg=f"CPU vs baseline {bl_index:03d}",
        )


# ===================================================================
# GPU baseline tests — skip if no CuPy
# ===================================================================


@pytest.mark.skipif(not HAS_CUPY, reason="CuPy not available")
class TestGPUBaselines:
    """GPU implementation vs MATLAB baselines."""

    @pytest.fixture()
    def gpu_calc(self) -> CTFCalculator:
        return CTFCalculator()

    @pytest.mark.parametrize("bl_index", ALL_BASELINE_IDS)
    def test_gpu_matches_baseline(
        self, gpu_calc: CTFCalculator, bl_index: int
    ) -> None:
        bl = _baseline_by_index(bl_index)
        params = _make_ctf_params(bl)
        expected = _load_baseline_array(bl_index)

        result_gpu = gpu_calc.compute(params, dims=(bl["nx"], bl["ny"]))
        result = cp.asnumpy(result_gpu)

        assert result.shape == expected.shape, (
            f"Shape mismatch: got {result.shape}, expected {expected.shape}"
        )
        np.testing.assert_allclose(
            result,
            expected,
            atol=GPU_VS_MATLAB_ATOL,
            err_msg=f"GPU vs baseline {bl_index:03d}",
        )


# ===================================================================
# GPU vs CPU agreement — skip if no CuPy
# ===================================================================


@pytest.mark.skipif(not HAS_CUPY, reason="CuPy not available")
class TestGPUvsCPU:
    """GPU and CPU implementations must agree to within tolerance."""

    @pytest.fixture()
    def calculators(self) -> tuple:
        return CTFCalculator(), CTFCalculatorCPU()

    @pytest.mark.parametrize("bl_index", ALL_BASELINE_IDS)
    def test_gpu_cpu_agreement(
        self, calculators: tuple, bl_index: int
    ) -> None:
        gpu_calc, cpu_calc = calculators
        bl = _baseline_by_index(bl_index)
        params = _make_ctf_params(bl)

        gpu_result = cp.asnumpy(
            gpu_calc.compute(params, dims=(bl["nx"], bl["ny"]))
        )
        cpu_result = cpu_calc.compute(params, dims=(bl["nx"], bl["ny"]))

        np.testing.assert_allclose(
            gpu_result,
            cpu_result,
            rtol=GPU_VS_CPU_RTOL,
            atol=GPU_VS_CPU_ATOL,
            err_msg=f"GPU vs CPU for baseline {bl_index:03d}",
        )


# ===================================================================
# Hand-computed ground truth
# ===================================================================


class TestHandComputedGroundTruth:
    """Validate specific CTF values computed by hand."""

    @pytest.fixture()
    def cpu_calc(self) -> CTFCalculatorCPU:
        return CTFCalculatorCPU()

    def test_dc_value_non_squared(self, cpu_calc: CTFCalculatorCPU) -> None:
        """DC (s=0): CTF = -sin(amplitude_phase) for non-squared CTF."""
        params = CTFParams.from_defocus_pair(
            df1=15500.0, df2=14500.0, angle_degrees=45.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07, do_half_grid=True, do_sq_ctf=False,
        )
        result = cpu_calc.compute(params, dims=(256, 256))
        dc_value = result[0, 0]
        expected_dc = -np.sin(np.float32(params.amplitude_phase))

        np.testing.assert_allclose(
            dc_value, expected_dc, atol=1e-6,
            err_msg="DC value for non-squared CTF",
        )

    def test_dc_value_squared(self, cpu_calc: CTFCalculatorCPU) -> None:
        """DC (s=0): CTF = sin^2(amplitude_phase) for squared CTF."""
        params = CTFParams.from_defocus_pair(
            df1=15500.0, df2=14500.0, angle_degrees=45.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07, do_half_grid=True, do_sq_ctf=True,
        )
        result = cpu_calc.compute(params, dims=(256, 256))
        dc_value = result[0, 0]
        expected_dc = np.float32(
            np.sin(np.float32(params.amplitude_phase)) ** 2
        )

        np.testing.assert_allclose(
            dc_value, expected_dc, atol=1e-6,
            err_msg="DC value for squared CTF",
        )

    def test_along_theta_axis_uses_df1(
        self, cpu_calc: CTFCalculatorCPU
    ) -> None:
        """Along phi=theta: effective defocus = mean + half_astig = df1.

        We verify this by computing a 1-D CTF along the astigmatism axis
        and comparing the defocus used in the phase formula.
        """
        # Use angle=0 so theta axis is along x (phi=0).
        # Then effective defocus = mean + half_astig * cos(0) = df1.
        df1, df2 = 20000.0, 18000.0
        params = CTFParams.from_defocus_pair(
            df1=df1, df2=df2, angle_degrees=0.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07, do_half_grid=True, do_sq_ctf=False,
        )
        result = cpu_calc.compute(params, dims=(256, 256))

        # Along y=0 (row 0), phi=0 except at x=0.
        # Pick a pixel along x-axis (y=0, x>0).
        x_test = 50
        fx = 1.0 / (float(params.pixel_size) * 256)
        sx = x_test * fx
        radius_sq = np.float32(sx * sx)

        expected_phase = (
            float(params.cs_term) * float(radius_sq) ** 2
            - float(params.df_term) * float(radius_sq) * df1
            - float(params.amplitude_phase)
        )
        expected_ctf = np.sin(np.float32(expected_phase))

        np.testing.assert_allclose(
            result[0, x_test], expected_ctf, atol=1e-5,
            err_msg="Along theta axis should use df1",
        )

    def test_perpendicular_to_theta_uses_df2(
        self, cpu_calc: CTFCalculatorCPU
    ) -> None:
        """Along phi=theta+pi/2: effective defocus = mean - half_astig = df2.

        With angle=0, the perpendicular axis is along y (phi=pi/2).
        cos(2*(pi/2 - 0)) = cos(pi) = -1, so
        defocus_eff = mean + half_astig * (-1) = mean - half_astig = df2.
        """
        df1, df2 = 20000.0, 18000.0
        params = CTFParams.from_defocus_pair(
            df1=df1, df2=df2, angle_degrees=0.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07, do_half_grid=True, do_sq_ctf=False,
        )
        result = cpu_calc.compute(params, dims=(256, 256))

        # Along x=0 (column 0), phi=pi/2 for y>0 (first half of y).
        # In non-centered layout, y=1 maps to frequency y=1.
        y_test = 50
        fy = 1.0 / (float(params.pixel_size) * 256)
        sy = y_test * fy
        radius_sq = np.float32(sy * sy)

        # At x=0, phi=atan2(sy, 0) = pi/2
        # cos(2*(pi/2 - 0)) = cos(pi) = -1
        # defocus_eff = mean + half_astig * (-1) = df2
        expected_phase = (
            float(params.cs_term) * float(radius_sq) ** 2
            - float(params.df_term) * float(radius_sq) * df2
            - float(params.amplitude_phase)
        )
        expected_ctf = np.sin(np.float32(expected_phase))

        np.testing.assert_allclose(
            result[y_test, 0], expected_ctf, atol=1e-5,
            err_msg="Perpendicular to theta should use df2",
        )


# ===================================================================
# Output shape and layout
# ===================================================================


class TestOutputShape:
    """Verify output shapes and C-contiguous layout."""

    @pytest.fixture()
    def cpu_calc(self) -> CTFCalculatorCPU:
        return CTFCalculatorCPU()

    def test_half_grid_shape(self, cpu_calc: CTFCalculatorCPU) -> None:
        params = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07, do_half_grid=True,
        )
        result = cpu_calc.compute(params, dims=(256, 256))
        assert result.shape == (256, 129)  # (ny, nx//2+1)

    def test_full_grid_shape(self, cpu_calc: CTFCalculatorCPU) -> None:
        params = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07, do_half_grid=False,
        )
        result = cpu_calc.compute(params, dims=(256, 256))
        assert result.shape == (256, 256)  # (ny, nx)

    def test_c_contiguous(self, cpu_calc: CTFCalculatorCPU) -> None:
        params = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07,
        )
        result = cpu_calc.compute(params, dims=(256, 256))
        assert result.flags["C_CONTIGUOUS"]

    def test_dtype_float32(self, cpu_calc: CTFCalculatorCPU) -> None:
        params = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07,
        )
        result = cpu_calc.compute(params, dims=(256, 256))
        assert result.dtype == np.float32

    def test_asymmetric_dims(self, cpu_calc: CTFCalculatorCPU) -> None:
        """128x128 and 512x512 dimensions."""
        params = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07, do_half_grid=True,
        )
        r128 = cpu_calc.compute(params, dims=(128, 128))
        assert r128.shape == (128, 65)

        r512 = cpu_calc.compute(params, dims=(512, 512))
        assert r512.shape == (512, 257)


# ===================================================================
# Negative controls
# ===================================================================


class TestNegativeControls:
    """Verify that invalid inputs raise appropriate errors."""

    @pytest.fixture()
    def cpu_calc(self) -> CTFCalculatorCPU:
        return CTFCalculatorCPU()

    def test_zero_pixel_size_raises(self, cpu_calc: CTFCalculatorCPU) -> None:
        params = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0,
            pixel_size=0.0, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07,
        )
        with pytest.raises(ValueError, match="pixel_size"):
            cpu_calc.compute(params, dims=(256, 256))

    def test_zero_wavelength_raises(self, cpu_calc: CTFCalculatorCPU) -> None:
        params = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0,
            pixel_size=1.5, wavelength=0.0, cs_mm=2.7,
            amplitude_contrast=0.07,
        )
        with pytest.raises(ValueError, match="wavelength"):
            cpu_calc.compute(params, dims=(256, 256))

    @pytest.mark.skipif(not HAS_CUPY, reason="CuPy not available")
    def test_gpu_zero_pixel_size_raises(self) -> None:
        calc = CTFCalculator()
        params = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0,
            pixel_size=0.0, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07,
        )
        with pytest.raises(ValueError, match="pixel_size"):
            calc.compute(params, dims=(256, 256))

    @pytest.mark.skipif(not HAS_CUPY, reason="CuPy not available")
    def test_gpu_zero_wavelength_raises(self) -> None:
        calc = CTFCalculator()
        params = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0,
            pixel_size=1.5, wavelength=0.0, cs_mm=2.7,
            amplitude_contrast=0.07,
        )
        with pytest.raises(ValueError, match="wavelength"):
            calc.compute(params, dims=(256, 256))


# ===================================================================
# Squared CTF
# ===================================================================


class TestSquaredCTF:
    """Verify squared CTF produces sin^2(phase) element-wise."""

    @pytest.fixture()
    def cpu_calc(self) -> CTFCalculatorCPU:
        return CTFCalculatorCPU()

    def test_squared_is_sin_squared(self, cpu_calc: CTFCalculatorCPU) -> None:
        """sin^2(phase) == (non-squared result)^2 element-wise."""
        base_kwargs = dict(
            df1=15500.0, df2=14500.0, angle_degrees=45.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07, do_half_grid=True,
        )
        params_nosq = CTFParams.from_defocus_pair(**base_kwargs, do_sq_ctf=False)
        params_sq = CTFParams.from_defocus_pair(**base_kwargs, do_sq_ctf=True)

        nosq = cpu_calc.compute(params_nosq, dims=(256, 256))
        sq = cpu_calc.compute(params_sq, dims=(256, 256))

        np.testing.assert_allclose(
            sq, nosq ** 2, atol=1e-7,
            err_msg="Squared CTF should be sin^2(phase)",
        )


# ===================================================================
# GPU-specific tests
# ===================================================================


@pytest.mark.skipif(not HAS_CUPY, reason="CuPy not available")
class TestGPUSpecific:
    """GPU-only tests: compilation, shape, layout."""

    def test_kernel_compilation(self) -> None:
        """RawModule compilation succeeds with --use_fast_math."""
        calc = CTFCalculator()
        assert calc.is_ready()

    def test_gpu_output_c_contiguous(self) -> None:
        calc = CTFCalculator()
        params = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07, do_half_grid=True,
        )
        result = calc.compute(params, dims=(256, 256))
        assert result.flags["C_CONTIGUOUS"]
        assert result.shape == (256, 129)

    def test_gpu_squared_ctf(self) -> None:
        calc = CTFCalculator()
        base_kwargs = dict(
            df1=15500.0, df2=14500.0, angle_degrees=45.0,
            pixel_size=1.5, wavelength=0.0197, cs_mm=2.7,
            amplitude_contrast=0.07, do_half_grid=True,
        )
        params_nosq = CTFParams.from_defocus_pair(**base_kwargs, do_sq_ctf=False)
        params_sq = CTFParams.from_defocus_pair(**base_kwargs, do_sq_ctf=True)

        nosq = cp.asnumpy(calc.compute(params_nosq, dims=(256, 256)))
        sq = cp.asnumpy(calc.compute(params_sq, dims=(256, 256)))

        np.testing.assert_allclose(
            sq, nosq ** 2, atol=1e-6,
            err_msg="GPU squared CTF should be sin^2(phase)",
        )
