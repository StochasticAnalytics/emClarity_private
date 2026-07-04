"""Constraint plugins package.

The concrete constraint modules use ``@register_constraint(...)`` (from
:mod:`mito_filter.constraints.combine`) at import time to populate
``CONSTRAINT_REGISTRY``. This package intentionally does NOT import them at
package-load time, so a bare ``import mito_filter.constraints`` leaves the
registry empty and consumers cannot silently rely on implicit population.

Call :func:`register_all` from a driver (CLI entry point, tests) to execute
the modules for their side effects; it is idempotent — re-invocations hit
Python's module cache and do not re-run the decorators. WHY the explicit
call: the alternative (top-level imports here) forces every consumer of
the package to pay for loading every constraint even when they only need
the base classes, and hides the registration side effect behind an
``import`` line that reads as namespace access, not code execution.
"""

from __future__ import annotations

import importlib

# Concrete constraint modules to load for the ``@register_constraint`` side
# effect. Adding a new constraint means appending its module name here.
_SIDE_EFFECT_MODULES: tuple[str, ...] = (
    "curvature",
    "gold_ice",
    "isolation",
    "membrane",
    "template_prior",
)


def register_all() -> None:
    """Import every constraint module for its ``@register_constraint`` side effect.

    Populates ``CONSTRAINT_REGISTRY`` with the constraints defined in this
    package. Idempotent: subsequent calls hit Python's module cache and do
    not re-run the decorators.
    """
    for name in _SIDE_EFFECT_MODULES:
        importlib.import_module(f"{__name__}.{name}")
