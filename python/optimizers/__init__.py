"""
emClarity optimizers package.

Parameter optimization algorithms for iterative refinement in cryo-EM
data processing. Includes ADAM (Adaptive Moment Estimation) with optional
AMSGrad variant and learning rate decay, and L-BFGS-B (Limited-memory
BFGS with Bounds) with curvature rejection for handling discrete
cross-correlation peak jumps.
"""

from .emc_adam_optimizer import AdamOptimizer
from .emc_lbfgsb_optimizer import LBFGSBOptimizer
from .emc_optimizer_base import OptimizerBase

__all__ = ["AdamOptimizer", "LBFGSBOptimizer", "OptimizerBase"]
