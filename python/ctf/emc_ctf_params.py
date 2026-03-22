"""
Frozen dataclass mirroring the C++ ctfParams struct from core_headers.cuh.

All derived quantities are computed identically to the CUDA constructor,
using np.float32 arithmetic to match GPU float precision.

Original C++ reference: mexFiles/include/core_headers.cuh lines 44-85.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np


@dataclasses.dataclass(frozen=True)
class CTFParams:
    """CTF parameters with pre-computed derived quantities.

    Mirrors the C++ ``ctfParams`` struct.  All floating-point fields are
    stored as ``np.float32`` to match CUDA single-precision behaviour.

    Attributes:
        do_half_grid: Use half-Fourier grid (default True).
        do_sq_ctf: Square the CTF (default False).
        pixel_size: Pixel size in Angstroms.
        wavelength: Electron wavelength in Angstroms.
        cs_mm: Spherical aberration in millimetres (original input units).
        cs_internal: Spherical aberration converted from mm to
            Angstrom-compatible units (CS_mm * 1e7).
        amplitude_contrast: Input amplitude-contrast ratio (stored as
            the original value; the derived *phase shift* is in
            ``amplitude_phase``).
        amplitude_phase: Phase shift derived from amplitude contrast via
            atan(ac / sqrt(1 - ac^2)).
        mean_defocus: Mean of df1 and df2 in Angstroms.
        half_astigmatism: Half the difference (df1 - df2) in Angstroms.
        astigmatism_angle_rad: Astigmatism angle normalised to
            [-pi/2, pi/2] in radians.
        cs_term: Pre-computed Cs coefficient: pi * 0.5 * cs_internal * wavelength^3.
        df_term: Pre-computed defocus coefficient: pi * wavelength.
    """

    do_half_grid: bool
    do_sq_ctf: bool
    pixel_size: np.float32
    wavelength: np.float32
    cs_mm: np.float32
    cs_internal: np.float32
    amplitude_contrast: np.float32
    amplitude_phase: np.float32
    mean_defocus: np.float32
    half_astigmatism: np.float32
    astigmatism_angle_rad: np.float32
    cs_term: np.float32
    df_term: np.float32

    @classmethod
    def from_defocus_pair(
        cls,
        df1: float,
        df2: float,
        angle_degrees: float,
        pixel_size: float,
        wavelength: float,
        cs_mm: float,
        amplitude_contrast: float,
        do_half_grid: bool = True,
        do_sq_ctf: bool = False,
    ) -> CTFParams:
        """Construct a CTFParams from raw defocus values.

        Performs the same unit conversions as the C++ ctfParams constructor
        in core_headers.cuh, using np.float32 arithmetic throughout.

        Args:
            df1: First defocus value in Angstroms.
            df2: Second defocus value in Angstroms.
            angle_degrees: Astigmatism angle in degrees.
            pixel_size: Pixel size in Angstroms.
            wavelength: Electron wavelength in Angstroms.
            cs_mm: Spherical aberration in millimetres.
            amplitude_contrast: Amplitude contrast ratio (0 < ac < 1).
            do_half_grid: Whether to use half-Fourier grid.
            do_sq_ctf: Whether to square the CTF.

        Returns:
            Frozen CTFParams instance with all derived quantities.
        """
        if not (0.0 <= amplitude_contrast < 1.0):
            raise ValueError(
                f"amplitude_contrast must be in [0, 1): got {amplitude_contrast}. "
                "Values >= 1.0 produce NaN via sqrt(1 - ac^2) in the phase formula."
            )

        f32 = np.float32
        pi = f32(math.pi)

        px = f32(pixel_size)
        wl = f32(wavelength)
        ac = f32(amplitude_contrast)
        d1 = f32(df1)
        d2 = f32(df2)
        angle = f32(angle_degrees)
        # cs_mm_f32 keeps the mm-unit value distinct from cs_internal (scaled
        # by 1e7).  Using cs_internal in cs_term; confusing the two causes a
        # 1e7x magnitude error.
        cs_mm_f32 = f32(cs_mm)

        # Unit conversions matching C++ constructor (core_headers.cuh:74-79)
        cs_internal = f32(cs_mm_f32 * f32(1e7))

        # amplitude_phase: atanf(ac / sqrtf(1 - ac^2))
        amplitude_phase = f32(np.arctan(
            ac / np.sqrt(f32(f32(1.0) - ac * ac))
        ))

        mean_defocus = f32(f32(0.5) * (d1 + d2))
        half_astigmatism = f32(f32(0.5) * (d1 - d2))

        # Angle normalisation to [-pi/2, pi/2]:
        #   angle_rad = angle*pi/180 - pi * round(angle/180)
        # round() matches C's lrintf() — round-half-to-even in NumPy.
        angle_ratio = f32(angle / f32(180.0))
        astigmatism_angle_rad = f32(
            angle * pi / f32(180.0) - pi * f32(np.round(angle_ratio))
        )

        # cs_term = pi * 0.5 * cs_internal * wavelength^3
        cs_term = f32(pi * f32(0.5) * cs_internal * (wl * wl * wl))

        # df_term = pi * wavelength
        df_term = f32(pi * wl)

        return cls(
            do_half_grid=do_half_grid,
            do_sq_ctf=do_sq_ctf,
            pixel_size=px,
            wavelength=wl,
            cs_mm=cs_mm_f32,
            cs_internal=cs_internal,
            amplitude_contrast=ac,
            amplitude_phase=amplitude_phase,
            mean_defocus=mean_defocus,
            half_astigmatism=half_astigmatism,
            astigmatism_angle_rad=astigmatism_angle_rad,
            cs_term=cs_term,
            df_term=df_term,
        )

    def to_kernel_args(self) -> dict[str, object]:
        """Return a flat dictionary mapping each field name to its value.

        Keys match the field names of this dataclass.  Boolean fields are
        included as Python bools; numeric fields as np.float32.

        Note:
            This returns a ``dict``, not a positional argument tuple.  For
            direct CuPy kernel dispatch use the positional tuple constructed
            in ``CTFCalculator.compute()``.

        Returns:
            Dictionary mapping parameter names to their values.
        """
        return {
            "do_half_grid": self.do_half_grid,
            "do_sq_ctf": self.do_sq_ctf,
            "pixel_size": self.pixel_size,
            "wavelength": self.wavelength,
            "cs_internal": self.cs_internal,
            "amplitude_contrast": self.amplitude_contrast,
            "amplitude_phase": self.amplitude_phase,
            "mean_defocus": self.mean_defocus,
            "half_astigmatism": self.half_astigmatism,
            "astigmatism_angle_rad": self.astigmatism_angle_rad,
            "cs_term": self.cs_term,
            "df_term": self.df_term,
        }

    def fourier_voxel_size(self, nx: int, ny: int) -> tuple[float, float]:
        """Compute Fourier-space voxel size for the given real-space dimensions.

        Args:
            nx: Number of pixels along x.
            ny: Number of pixels along y.

        Returns:
            Tuple (fx, fy) where fx = 1/(pixel_size*nx), fy = 1/(pixel_size*ny).
        """
        f32 = np.float32
        fx = f32(f32(1.0) / (self.pixel_size * f32(nx)))
        fy = f32(f32(1.0) / (self.pixel_size * f32(ny)))
        return (float(fx), float(fy))
