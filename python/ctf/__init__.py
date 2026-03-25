"""
emClarity CTF package.

Modules for Contrast Transfer Function estimation, correction, and refinement
in cryo-electron microscopy data processing.
"""

from .emc_ctf_params import CTFParams

# Optional CUDA support — fall back to pure-NumPy CPU implementation
try:
    from .emc_ctf_calculator import CTFCalculator

    HAS_CTF_CUDA = True
except ImportError:
    from .emc_ctf_cpu import (
        CTFCalculatorCPU as CTFCalculator,  # type: ignore[assignment,misc]
    )

    HAS_CTF_CUDA = False

__all__ = [
    "HAS_CTF_CUDA",
    "CTFCalculator",
    "CTFParams",
]
