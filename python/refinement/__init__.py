"""
emClarity refinement package.

Fourier-space utilities and iterative refinement algorithms for cryo-EM
sub-tomogram averaging. Includes FFT handling, bandpass filtering,
normalization routines that replicate the MATLAB fourierTransformer class,
and the per-tilt CTF refinement loop.
"""

from .emc_ctf_gradients import CTFCalculatorWithDerivatives, evaluate_score_and_gradient
from .emc_fourier_utils import FourierTransformer
from .emc_refine_tilt_ctf import (
    RefinementOptions,
    RefinementResults,
    compute_half_astig_lower_bound,
    refine_tilt_ctf,
)
from .emc_ctf_refine_pipeline import (
    PipelineOptions,
    PipelineResults,
    TiltGroupResult,
    compute_electron_wavelength,
    refine_ctf_from_star,
)
from .emc_scoring import create_peak_mask, evaluate_score_and_shifts
from .emc_tile_prep import (
    center_crop_or_pad,
    compute_ctf_friendly_size,
    create_2d_soft_mask,
    create_ctf_mask,
    prepare_data_tile,
    prepare_reference_projection,
)

__all__ = [
    "CTFCalculatorWithDerivatives",
    "FourierTransformer",
    "PipelineOptions",
    "PipelineResults",
    "RefinementOptions",
    "RefinementResults",
    "TiltGroupResult",
    "center_crop_or_pad",
    "compute_ctf_friendly_size",
    "compute_electron_wavelength",
    "compute_half_astig_lower_bound",
    "create_2d_soft_mask",
    "create_ctf_mask",
    "create_peak_mask",
    "evaluate_score_and_gradient",
    "evaluate_score_and_shifts",
    "prepare_data_tile",
    "prepare_reference_projection",
    "refine_ctf_from_star",
    "refine_tilt_ctf",
]
