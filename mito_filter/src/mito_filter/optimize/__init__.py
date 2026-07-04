"""Layer 2 - optimize: fit ONE FilterModel theta jointly over a whole search (DESIGN 8).

Public surface:

* :class:`SearchDataset` - the row-concatenated cached-feature dataset over every convmap.
* :class:`WeakLabelSource` / :class:`WeakLabels` / :func:`parse_class_cull` - SPEC 10 weak labels.
* :class:`SelfSupervisedObjective` (primary) / :class:`WeakLabelObjective` (secondary) /
  :class:`CompositeObjective` - the objectives.
* :class:`ParameterSpace` - the tunable theta space.
* :class:`OptunaOptimizer` (primary) / :class:`RandomOptimizer` - black-box optimizers.
* :class:`Tuner` - fits theta and emits a :class:`~mito_filter.model.config.FittedConfig`.
* :func:`build_report` / :class:`SeparationReport` - separation / PR vs weak labels.
"""

from __future__ import annotations

from .dataset import SearchDataset
from .labels import (
    NEGATIVE,
    POSITIVE,
    UNKNOWN,
    ClassCull,
    WeakLabels,
    WeakLabelSource,
    find_cull_files,
    parse_class_cull,
)
from .objective import (
    AnchorConfig,
    CompositeObjective,
    Objective,
    ObjectiveValue,
    SelfSupervisedObjective,
    WeakLabelObjective,
)
from .optimizers import Optimizer, OptimizeResult, OptunaOptimizer, RandomOptimizer
from .report import SeparationReport, build_report
from .space import Dimension, ParameterSpace
from .tuner import Tuner, TuneResult

__all__ = [
    "SearchDataset",
    "WeakLabelSource",
    "WeakLabels",
    "ClassCull",
    "parse_class_cull",
    "find_cull_files",
    "UNKNOWN",
    "NEGATIVE",
    "POSITIVE",
    "Objective",
    "ObjectiveValue",
    "SelfSupervisedObjective",
    "WeakLabelObjective",
    "CompositeObjective",
    "AnchorConfig",
    "ParameterSpace",
    "Dimension",
    "Optimizer",
    "OptimizeResult",
    "OptunaOptimizer",
    "RandomOptimizer",
    "Tuner",
    "TuneResult",
    "SeparationReport",
    "build_report",
]
