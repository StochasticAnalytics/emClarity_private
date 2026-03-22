"""
Tests for CTFParams frozen dataclass.

Validates that all derived quantities match hand-computed values using
np.float32 arithmetic, mirroring the C++ ctfParams constructor in
mexFiles/include/core_headers.cuh lines 44-85.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from ..emc_ctf_params import CTFParams

# ---------------------------------------------------------------------------
# Helper: reference computations in float32 (mirrors C++ exactly)
# ---------------------------------------------------------------------------


def _ref_amplitude_phase(ac: float) -> np.float32:
    """atanf(ac / sqrtf(1 - ac^2)) in float32."""
    ac32 = np.float32(ac)
    return np.float32(np.arctan(ac32 / np.sqrt(np.float32(1.0) - ac32 * ac32)))


def _ref_angle_norm(angle_deg: float) -> np.float32:
    """Normalise angle to [-pi/2, pi/2] matching C++ lrintf convention."""
    pi = np.float32(math.pi)
    a = np.float32(angle_deg)
    ratio = np.float32(a / np.float32(180.0))
    return np.float32(a * pi / np.float32(180.0) - pi * np.float32(np.round(ratio)))


def _ref_cs_term(cs_mm: float, wavelength: float) -> np.float32:
    pi = np.float32(math.pi)
    cs = np.float32(np.float32(cs_mm) * np.float32(1e7))
    wl = np.float32(wavelength)
    return np.float32(pi * np.float32(0.5) * cs * (wl * wl * wl))


def _ref_df_term(wavelength: float) -> np.float32:
    return np.float32(np.float32(math.pi) * np.float32(wavelength))


# ---------------------------------------------------------------------------
# Fixtures: representative parameter sets
# ---------------------------------------------------------------------------

# Typical 300 kV conditions
PARAMS_300KV = dict(
    df1=15000.0,
    df2=14000.0,
    angle_degrees=45.0,
    pixel_size=1.34,
    wavelength=0.0197,
    cs_mm=2.7,
    amplitude_contrast=0.07,
)

# Typical 200 kV conditions
PARAMS_200KV = dict(
    df1=20000.0,
    df2=18000.0,
    angle_degrees=30.0,
    pixel_size=1.06,
    wavelength=0.0251,
    cs_mm=2.0,
    amplitude_contrast=0.10,
)


class TestFromDefocusPair:
    """Test the classmethod constructor."""

    def test_returns_ctf_params_instance(self) -> None:
        p = CTFParams.from_defocus_pair(**PARAMS_300KV)
        assert isinstance(p, CTFParams)

    def test_frozen(self) -> None:
        p = CTFParams.from_defocus_pair(**PARAMS_300KV)
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.pixel_size = np.float32(2.0)  # type: ignore[misc]

    def test_defaults(self) -> None:
        p = CTFParams.from_defocus_pair(**PARAMS_300KV)
        assert p.do_half_grid is True
        assert p.do_sq_ctf is False

    def test_explicit_flags(self) -> None:
        p = CTFParams.from_defocus_pair(
            **PARAMS_300KV, do_half_grid=False, do_sq_ctf=True
        )
        assert p.do_half_grid is False
        assert p.do_sq_ctf is True


class TestMeanDefocus:
    """mean_defocus = 0.5 * (df1 + df2)."""

    @pytest.mark.parametrize(
        "df1, df2, expected",
        [
            (15000.0, 14000.0, np.float32(14500.0)),
            (20000.0, 18000.0, np.float32(19000.0)),
            (10000.0, 10000.0, np.float32(10000.0)),  # no astigmatism
            (0.0, 0.0, np.float32(0.0)),
            (50000.0, 30000.0, np.float32(40000.0)),
            (-5000.0, -3000.0, np.float32(-4000.0)),  # negative defocus
        ],
    )
    def test_mean_defocus(self, df1: float, df2: float, expected: np.float32) -> None:
        p = CTFParams.from_defocus_pair(
            df1=df1, df2=df2, angle_degrees=0.0, pixel_size=1.0,
            wavelength=0.02, cs_mm=2.7, amplitude_contrast=0.07,
        )
        assert p.mean_defocus == expected


class TestHalfAstigmatism:
    """half_astigmatism = 0.5 * (df1 - df2)."""

    @pytest.mark.parametrize(
        "df1, df2, expected",
        [
            (15000.0, 14000.0, np.float32(500.0)),
            (20000.0, 18000.0, np.float32(1000.0)),
            (10000.0, 10000.0, np.float32(0.0)),
            (14000.0, 15000.0, np.float32(-500.0)),
        ],
    )
    def test_half_astigmatism(
        self, df1: float, df2: float, expected: np.float32
    ) -> None:
        p = CTFParams.from_defocus_pair(
            df1=df1, df2=df2, angle_degrees=0.0, pixel_size=1.0,
            wavelength=0.02, cs_mm=2.7, amplitude_contrast=0.07,
        )
        assert p.half_astigmatism == expected


class TestAmplitudePhase:
    """amplitude_phase = atanf(ac / sqrtf(1 - ac^2))."""

    @pytest.mark.parametrize(
        "ac",
        [0.07, 0.10, 0.05, 0.15, 0.20, 0.01, 0.50],
    )
    def test_matches_reference(self, ac: float) -> None:
        p = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0, pixel_size=1.0,
            wavelength=0.02, cs_mm=2.7, amplitude_contrast=ac,
        )
        ref = _ref_amplitude_phase(ac)
        assert abs(float(p.amplitude_phase) - float(ref)) < 1e-7

    def test_ac_007_specific(self) -> None:
        """Acceptance criterion: ac=0.07 matches atanf(0.07/sqrtf(1-0.07^2))."""
        p = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0, pixel_size=1.0,
            wavelength=0.02, cs_mm=2.7, amplitude_contrast=0.07,
        )
        ref = _ref_amplitude_phase(0.07)
        assert abs(float(p.amplitude_phase) - float(ref)) < 1e-7


class TestAngleNormalization:
    """astigmatism_angle_rad normalised to [-pi/2, pi/2]."""

    @pytest.mark.parametrize(
        "angle_deg, expected_rad",
        [
            (45.0, np.float32(math.pi / 4)),
            (135.0, np.float32(-math.pi / 4)),
            (-90.0, np.float32(-math.pi / 2)),
            (0.0, np.float32(0.0)),
            (90.0, np.float32(math.pi / 2)),      # boundary
            (-45.0, np.float32(-math.pi / 4)),
            (180.0, np.float32(0.0)),              # wraps to 0
            (-180.0, np.float32(0.0)),
            (270.0, np.float32(-math.pi / 2)),     # 270: round(1.5)=2 -> -pi/2
            (360.0, np.float32(0.0)),              # full wrap
        ],
    )
    def test_angle_normalization(
        self, angle_deg: float, expected_rad: np.float32
    ) -> None:
        p = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=angle_deg,
            pixel_size=1.0, wavelength=0.02, cs_mm=2.7,
            amplitude_contrast=0.07,
        )
        ref = _ref_angle_norm(angle_deg)
        # Check against both the hand-computed expectation and the reference
        assert abs(float(p.astigmatism_angle_rad) - float(ref)) < 1e-7
        assert abs(float(p.astigmatism_angle_rad) - float(expected_rad)) < 1e-6


class TestCsTerm:
    """cs_term = pi * 0.5 * cs_internal * wavelength^3."""

    def test_300kv_cs27(self) -> None:
        """Acceptance criterion: 300 kV, Cs=2.7 mm."""
        p = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0, pixel_size=1.0,
            wavelength=0.0197, cs_mm=2.7, amplitude_contrast=0.07,
        )
        ref = _ref_cs_term(2.7, 0.0197)
        assert abs(float(p.cs_term) - float(ref)) < 1e-7

    @pytest.mark.parametrize(
        "cs_mm, wavelength",
        [
            (2.7, 0.0197),
            (2.0, 0.0251),
            (1.2, 0.0197),
            (0.001, 0.0197),
            (2.7, 0.0335),
        ],
    )
    def test_cs_term_matches_reference(
        self, cs_mm: float, wavelength: float
    ) -> None:
        p = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0, pixel_size=1.0,
            wavelength=wavelength, cs_mm=cs_mm, amplitude_contrast=0.07,
        )
        ref = _ref_cs_term(cs_mm, wavelength)
        assert abs(float(p.cs_term) - float(ref)) < 1e-7


class TestDfTerm:
    """df_term = pi * wavelength."""

    @pytest.mark.parametrize(
        "wavelength",
        [0.0197, 0.0251, 0.0335],
    )
    def test_df_term(self, wavelength: float) -> None:
        p = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0, pixel_size=1.0,
            wavelength=wavelength, cs_mm=2.7, amplitude_contrast=0.07,
        )
        ref = _ref_df_term(wavelength)
        assert abs(float(p.df_term) - float(ref)) < 1e-7


class TestCsInternal:
    """cs_internal = CS_mm * 1e7."""

    @pytest.mark.parametrize(
        "cs_mm, expected",
        [
            (2.7, np.float32(2.7e7)),
            (2.0, np.float32(2.0e7)),
            (0.001, np.float32(1e4)),
        ],
    )
    def test_cs_conversion(self, cs_mm: float, expected: np.float32) -> None:
        p = CTFParams.from_defocus_pair(
            df1=15000.0, df2=14000.0, angle_degrees=0.0, pixel_size=1.0,
            wavelength=0.02, cs_mm=cs_mm, amplitude_contrast=0.07,
        )
        assert p.cs_internal == expected


class TestToKernelArgs:
    """to_kernel_args() returns a complete flat dictionary."""

    REQUIRED_KEYS = {
        "do_half_grid",
        "do_sq_ctf",
        "pixel_size",
        "wavelength",
        "cs_internal",
        "amplitude_contrast",
        "amplitude_phase",
        "mean_defocus",
        "half_astigmatism",
        "astigmatism_angle_rad",
        "cs_term",
        "df_term",
    }

    def test_has_all_keys(self) -> None:
        p = CTFParams.from_defocus_pair(**PARAMS_300KV)
        kargs = p.to_kernel_args()
        assert set(kargs.keys()) == self.REQUIRED_KEYS

    def test_values_match_fields(self) -> None:
        p = CTFParams.from_defocus_pair(**PARAMS_300KV)
        kargs = p.to_kernel_args()
        for key in self.REQUIRED_KEYS:
            assert kargs[key] == getattr(p, key), f"Mismatch for {key}"

    def test_returns_dict(self) -> None:
        p = CTFParams.from_defocus_pair(**PARAMS_300KV)
        assert isinstance(p.to_kernel_args(), dict)


class TestFourierVoxelSize:
    """fourier_voxel_size(nx, ny) = (1/(px*nx), 1/(px*ny))."""

    def test_256_symmetric(self) -> None:
        """Acceptance criterion: pixel_size=1.34, 256x256."""
        p = CTFParams.from_defocus_pair(**PARAMS_300KV)
        fx, fy = p.fourier_voxel_size(256, 256)
        expected = 1.0 / (1.34 * 256)
        assert abs(fx - expected) < 1e-7
        assert abs(fy - expected) < 1e-7

    def test_asymmetric(self) -> None:
        p = CTFParams.from_defocus_pair(**PARAMS_300KV)
        fx, fy = p.fourier_voxel_size(256, 512)
        assert abs(fx - 1.0 / (1.34 * 256)) < 1e-7
        assert abs(fy - 1.0 / (1.34 * 512)) < 1e-7

    def test_returns_float_tuple(self) -> None:
        p = CTFParams.from_defocus_pair(**PARAMS_300KV)
        result = p.fourier_voxel_size(128, 128)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], float)


class TestParameterSets:
    """Validate 10+ parameter sets against hand-computed float32 values."""

    PARAM_SETS = [
        # (df1, df2, angle, px, wl, cs, ac)
        (15000.0, 14000.0, 45.0, 1.34, 0.0197, 2.7, 0.07),
        (20000.0, 18000.0, 30.0, 1.06, 0.0251, 2.0, 0.10),
        (10000.0, 10000.0, 0.0, 1.00, 0.0197, 2.7, 0.07),
        (25000.0, 22000.0, 90.0, 0.88, 0.0197, 2.7, 0.05),
        (30000.0, 28000.0, 135.0, 1.50, 0.0251, 1.2, 0.15),
        (5000.0, 3000.0, -45.0, 2.00, 0.0335, 2.7, 0.20),
        (40000.0, 35000.0, 180.0, 1.34, 0.0197, 0.001, 0.07),
        (12000.0, 11500.0, -90.0, 1.10, 0.0197, 2.7, 0.10),
        (18000.0, 17000.0, 270.0, 1.34, 0.0251, 2.0, 0.07),
        (8000.0, 6000.0, 360.0, 1.00, 0.0197, 2.7, 0.50),
        (0.0, 0.0, 0.0, 1.00, 0.0197, 2.7, 0.01),
    ]

    @pytest.mark.parametrize("params", PARAM_SETS)
    def test_all_derived_quantities(
        self, params: tuple[float, ...]
    ) -> None:
        df1, df2, angle, px, wl, cs, ac = params
        p = CTFParams.from_defocus_pair(
            df1=df1, df2=df2, angle_degrees=angle,
            pixel_size=px, wavelength=wl, cs_mm=cs,
            amplitude_contrast=ac,
        )

        f32 = np.float32
        assert p.mean_defocus == f32(f32(0.5) * (f32(df1) + f32(df2)))
        assert p.half_astigmatism == f32(f32(0.5) * (f32(df1) - f32(df2)))
        assert abs(float(p.amplitude_phase) - float(_ref_amplitude_phase(ac))) < 1e-7
        assert abs(float(p.astigmatism_angle_rad) - float(_ref_angle_norm(angle))) < 1e-7
        assert abs(float(p.cs_term) - float(_ref_cs_term(cs, wl))) < 1e-7
        assert abs(float(p.df_term) - float(_ref_df_term(wl))) < 1e-7
        assert p.cs_internal == f32(f32(cs) * f32(1e7))
