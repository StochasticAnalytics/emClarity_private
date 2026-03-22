"""
emClarity refinement package.

Fourier-space utilities and iterative refinement algorithms for cryo-EM
sub-tomogram averaging. Includes FFT handling, bandpass filtering,
normalization routines that replicate the MATLAB fourierTransformer class,
and the per-tilt CTF refinement loop.
"""

from .emc_ctf_gradients import evaluate_score_and_gradient
from .emc_fourier_utils import FourierTransformer
from .emc_refine_tilt_ctf import (
    RefinementOptions,
    RefinementResults,
    compute_half_astig_lower_bound,
    refine_tilt_ctf,
)
from .emc_scoring import create_peak_mask, evaluate_score_and_shifts

__all__ = [
    "FourierTransformer",
    "RefinementOptions",
    "RefinementResults",
    "compute_half_astig_lower_bound",
    "create_peak_mask",
    "evaluate_score_and_gradient",
    "evaluate_score_and_shifts",
    "refine_tilt_ctf",
]
