"""
pytest configuration for python/ctf/tests.

Guards against silent test collapse: if the MATLAB-baseline fixture file
is missing, pytest emits a loud warning at collection time rather than
silently parametrising zero test cases.  Non-baseline tests (CTFParams,
star I/O) still run normally.
"""

import warnings
from pathlib import Path

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_PARAMS_FILE = _FIXTURES_DIR / "ctf_baseline_params.json"


def pytest_configure(config: object) -> None:
    """Warn at collection time if the baseline fixture file is absent.

    Without this guard the module-level try/except in test_ctf_calculator.py
    sets BASELINE_META={} on FileNotFoundError, ALL_BASELINE_IDS becomes [],
    and every @pytest.mark.parametrize collects zero cases — CI reports green
    while zero correctness checks execute.

    We emit a warning (not an error) so that non-baseline tests
    (test_ctf_params, test_star_io) still run.  The warning is visible
    in CI output, providing a signal that baseline coverage is missing.
    """
    if not _PARAMS_FILE.exists():
        warnings.warn(
            f"CTF baseline fixture file not found: {_PARAMS_FILE}\n"
            "Parametrized baseline tests will collect zero cases. "
            "Ensure the fixtures/ directory is committed and present.",
            UserWarning,
            stacklevel=1,
        )
