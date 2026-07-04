"""Feature-extractor plugins package.

The concrete extractor modules use ``@FEATURE_REGISTRY.register(...)`` (from
:mod:`mito_filter.features.engine`) at import time to populate
``FEATURE_REGISTRY``. This package intentionally does NOT import them at
package-load time, so a bare ``import mito_filter.features`` leaves the
registry empty and consumers cannot silently rely on implicit population.

Call :func:`register_all` from a driver (CLI entry point, tests) to execute
the modules for their side effects; it is idempotent — re-invocations hit
Python's module cache and do not re-run the decorators. WHY the explicit
call: the alternative (top-level imports here) forces every consumer of
the package to pay for loading every extractor even when they only need
the engine, and hides the registration side effect behind an ``import``
line that reads as namespace access, not code execution.
"""

from __future__ import annotations

import importlib

# Concrete extractor modules to load for the ``@FEATURE_REGISTRY.register``
# side effect. Adding a new extractor means appending its module name here.
_SIDE_EFFECT_MODULES: tuple[str, ...] = (
    "curvature",
    "isolation",
    "local_stats",
    "membrane",
    "priors",
)


def register_all() -> None:
    """Import every extractor module for its ``@FEATURE_REGISTRY.register`` side effect.

    Populates ``FEATURE_REGISTRY`` with the extractors defined in this
    package. Idempotent: subsequent calls hit Python's module cache and do
    not re-run the decorators.
    """
    for name in _SIDE_EFFECT_MODULES:
        importlib.import_module(f"{__name__}.{name}")
