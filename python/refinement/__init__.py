"""
emClarity refinement package.

Fourier-space utilities and iterative refinement algorithms for cryo-EM
sub-tomogram averaging. Includes FFT handling, bandpass filtering,
and normalization routines that replicate the MATLAB fourierTransformer class.
"""

from .emc_ctf_gradients import evaluate_score_and_gradient
from .emc_fourier_utils import FourierTransformer
from .emc_scoring import create_peak_mask, evaluate_score_and_shifts

__all__ = [
    "FourierTransformer",
    "create_peak_mask",
    "evaluate_score_and_gradient",
    "evaluate_score_and_shifts",
]
