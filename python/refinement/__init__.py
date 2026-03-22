"""
emClarity refinement package.

Fourier-space utilities and iterative refinement algorithms for cryo-EM
sub-tomogram averaging. Includes FFT handling, bandpass filtering,
and normalization routines that replicate the MATLAB fourierTransformer class.
"""

from .emc_fourier_utils import FourierTransformer

__all__ = ["FourierTransformer"]
