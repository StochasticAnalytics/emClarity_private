"""
pytest configuration for python/ctf/tests.

Guards against silent test collapse: if the MATLAB-baseline fixture file
is missing, pytest fails loudly at collection time rather than silently
parametrising zero test cases.
"""

from pathlib import Path

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_PARAMS_FILE = _FIXTURES_DIR / "ctf_baseline_params.json"


def pytest_configure(config: object) -> None:  # noqa: ARG001
    """Abort collection if the baseline fixture file is absent.

    Without this guard the module-level try/except in test_ctf_calculator.py
    sets BASELINE_META={} on FileNotFoundError, ALL_BASELINE_IDS becomes [],
    and every @pytest.mark.parametrize collects zero cases — CI reports green
    while zero correctness checks execute.
    """
    if not _PARAMS_FILE.exists():
        raise FileNotFoundError(
            f"CTF baseline fixture file not found: {_PARAMS_FILE}\n"
            "Parametrized baseline tests would collect zero cases without it. "
            "Ensure the fixtures/ directory is committed and present."
        )
