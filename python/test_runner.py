#!/usr/bin/env python3
"""
Unified test runner for emClarity Python modules.

Usage:
    python test_runner.py                    # Run all tests
    python test_runner.py metaData           # Run specific module tests
    python test_runner.py --coverage         # Run with coverage report
    python test_runner.py --ci               # CI mode with JUnit XML output
"""

import argparse
import os
import sys
import unittest
from pathlib import Path
from typing import List, Optional

# Add python directory to path
python_dir = Path(__file__).parent
sys.path.insert(0, str(python_dir))


def discover_test_modules() -> List[str]:
    """Discover all test modules in the python directory."""
    test_modules = []

    for module_dir in python_dir.iterdir():
        if module_dir.is_dir() and not module_dir.name.startswith("."):
            tests_dir = module_dir / "tests"
            if tests_dir.exists():
                for test_file in tests_dir.glob("test_*.py"):
                    module_name = f"{module_dir.name}.tests.{test_file.stem}"
                    test_modules.append(module_name)

    return test_modules


def run_tests(
    module_filter: Optional[str] = None,
    coverage: bool = False,
    ci_mode: bool = False,
    verbose: bool = True,
) -> bool:
    """
    Run tests with optional module filtering and coverage.

    Args:
        module_filter: Only run tests for modules containing this string
        coverage: Generate coverage report
        ci_mode: Enable CI-friendly output (JUnit XML, etc.)
        verbose: Enable verbose output

    Returns:
        True if all tests passed, False otherwise
    """
    test_modules = discover_test_modules()

    if module_filter:
        test_modules = [m for m in test_modules if module_filter in m]

    if not test_modules:
        print(
            f"No test modules found{' for filter: ' + module_filter if module_filter else ''}"
        )
        return False

    if verbose:
        print(f"Running tests for modules: {', '.join(test_modules)}")

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for module_name in test_modules:
        try:
            module = __import__(module_name, fromlist=[""])
            module_suite = loader.loadTestsFromModule(module)
            suite.addTest(module_suite)
        except ImportError as e:
            if verbose:
                print(f"Warning: Could not import {module_name}: {e}")
            continue

    # Configure test runner
    if ci_mode:
        # Try to use XMLTestRunner for CI
        try:
            import xmlrunner

            runner = xmlrunner.XMLTestRunner(
                output="test-reports", verbosity=2 if verbose else 1
            )
        except ImportError:
            if verbose:
                print("xmlrunner not available, using standard runner")
            runner = unittest.TextTestRunner(
                verbosity=2 if verbose else 1, stream=sys.stdout, buffer=True
            )
    else:
        runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)

    # Run tests with optional coverage
    if coverage:
        try:
            import coverage

            cov = coverage.Coverage(source=[str(python_dir)])
            cov.start()

            result = runner.run(suite)

            cov.stop()
            cov.save()

            if verbose:
                print("\nCoverage Report:")
                cov.report()

            # Generate XML report for CI
            if ci_mode:
                try:
                    cov.xml_report(outfile="coverage.xml")
                    if verbose:
                        print("Coverage XML report saved to coverage.xml")
                except Exception as e:
                    if verbose:
                        print(f"Could not generate coverage XML: {e}")

        except ImportError:
            if verbose:
                print("Coverage not available, running tests without coverage")
            result = runner.run(suite)
    else:
        result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run emClarity Python tests")
    parser.add_argument("module", nargs="?", help="Module filter (e.g., 'metaData')")
    parser.add_argument(
        "--coverage", action="store_true", help="Generate coverage report"
    )
    parser.add_argument("--ci", action="store_true", help="CI mode (XML output, etc.)")
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Reduce output verbosity"
    )

    args = parser.parse_args()

    verbose = not args.quiet
    success = run_tests(
        module_filter=args.module,
        coverage=args.coverage,
        ci_mode=args.ci,
        verbose=verbose,
    )

    if success:
        if verbose:
            print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        if verbose:
            print("\n❌ Some tests failed!")
        sys.exit(1)
