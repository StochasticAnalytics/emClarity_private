#!/usr/bin/env python3
"""
External Oracle Validation Script

Runs outside agent context to provide unforgeable ground truth validation.
Checks: TypeScript compilation, backend tests, E2E tests, test immutability, coverage.

Checks are configurable via config.json "oracle_checks" to allow early tasks
(e.g. scaffold creation) to pass before the full test harness exists.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class OracleValidator:
    """External validation oracle"""

    def __init__(
        self,
        baseline_path: Path = Path("templates/baseline.json"),
        results_path: Path = Path("templates/ci-results.json"),
        config_path: Path = Path("config.json"),
        cwd: Path | None = None,
    ):
        self.baseline_path = baseline_path
        self.results_path = results_path
        self.cwd = str(cwd) if cwd else None
        self.baseline = self._load_baseline()
        self.enabled_checks = self._load_enabled_checks(config_path)

    def _load_baseline(self) -> Dict:
        """Load baseline metrics from dedicated baseline file."""
        if not self.baseline_path.exists():
            return {
                "assert_count": 0,
                "coverage": 0.0,
            }

        try:
            with open(self.baseline_path) as f:
                data = json.load(f)
                return data.get("baseline", {})
        except (json.JSONDecodeError, KeyError):
            return {"assert_count": 0, "coverage": 0.0}

    def _load_enabled_checks(self, config_path: Path) -> Dict[str, bool]:
        """Load which checks are enabled from config.json."""
        defaults = {
            "typescript": True,
            "backend_tests": True,
            "e2e_tests": True,
            "test_immutability": True,
            "assert_count": True,
            "coverage": True,
        }
        try:
            with open(config_path) as f:
                config = json.load(f)
            return config.get("oracle_checks", defaults)
        except (FileNotFoundError, json.JSONDecodeError):
            return defaults

    def _save_results(self, results: Dict):
        """Append validation results to results file.

        Stores a list of per-task result records so previous results
        are not overwritten.
        """
        existing: List[Dict] = []
        if self.results_path.exists():
            try:
                with open(self.results_path) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    existing = data
                elif isinstance(data, dict):
                    # Migrate from old single-result format
                    existing = [data]
            except (json.JSONDecodeError, KeyError):
                existing = []

        existing.append(results)

        with open(self.results_path, "w") as f:
            json.dump(existing, f, indent=2)

    def validate(self, task_id: str) -> Dict:
        """Run all enabled validation checks."""

        results: Dict = {
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
            "passed": True,
            "checks": [],
        }

        check_map = {
            "typescript": self._check_typescript,
            "backend_tests": self._check_backend_tests,
            "e2e_tests": self._check_e2e_tests,
            "test_immutability": self._check_test_immutability,
            "assert_count": self._check_assert_count,
            "coverage": self._check_coverage,
        }

        for name, check_fn in check_map.items():
            if not self.enabled_checks.get(name, True):
                results["checks"].append({
                    "name": name,
                    "passed": True,
                    "skipped": True,
                })
                continue

            check_result = check_fn()
            results["checks"].append(check_result)
            if not check_result["passed"]:
                results["passed"] = False

        # Summary
        failed = sum(
            1 for c in results["checks"]
            if not c["passed"] and not c.get("skipped", False)
        )
        total = sum(1 for c in results["checks"] if not c.get("skipped", False))
        if failed > 0:
            results["summary"] = f"{failed} of {total} checks failed"
        else:
            results["summary"] = "All checks passed"

        self._save_results(results)
        return results

    def _check_typescript(self) -> Dict:
        """Validate TypeScript compilation from the gui/ subdirectory."""
        start = time.time()

        gui_cwd = str(Path(self.cwd or ".") / "gui")

        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=gui_cwd,
            )

            duration_ms = int((time.time() - start) * 1000)

            if result.returncode == 0:
                return {
                    "name": "typescript",
                    "passed": True,
                    "duration_ms": duration_ms,
                }
            else:
                return {
                    "name": "typescript",
                    "passed": False,
                    "duration_ms": duration_ms,
                    "error": result.stderr or result.stdout,
                }

        except subprocess.TimeoutExpired:
            return {
                "name": "typescript",
                "passed": False,
                "error": "TypeScript compilation timed out after 60s",
            }
        except FileNotFoundError:
            return {
                "name": "typescript",
                "passed": False,
                "error": "npx/tsc not found - ensure Node.js is installed",
            }

    def _check_backend_tests(self) -> Dict:
        """Run backend pytest suite"""
        start = time.time()

        try:
            result = subprocess.run(
                ["pytest", "backend/", "-v"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.cwd,
            )

            duration_ms = int((time.time() - start) * 1000)

            if result.returncode == 0:
                return {
                    "name": "backend_tests",
                    "passed": True,
                    "duration_ms": duration_ms,
                }
            else:
                return {
                    "name": "backend_tests",
                    "passed": False,
                    "duration_ms": duration_ms,
                    "error": result.stdout,
                }

        except subprocess.TimeoutExpired:
            return {
                "name": "backend_tests",
                "passed": False,
                "error": "Backend tests timed out after 120s",
            }
        except FileNotFoundError:
            return {
                "name": "backend_tests",
                "passed": False,
                "error": "pytest not found - ensure Python dependencies installed",
            }

    def _check_e2e_tests(self) -> Dict:
        """Run E2E test suite"""
        start = time.time()

        try:
            result = subprocess.run(
                ["pytest", "tests/", "-v"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.cwd,
            )

            duration_ms = int((time.time() - start) * 1000)

            if result.returncode == 0:
                return {
                    "name": "e2e_tests",
                    "passed": True,
                    "duration_ms": duration_ms,
                }
            else:
                return {
                    "name": "e2e_tests",
                    "passed": False,
                    "duration_ms": duration_ms,
                    "error": result.stdout,
                }

        except subprocess.TimeoutExpired:
            return {
                "name": "e2e_tests",
                "passed": False,
                "error": "E2E tests timed out after 300s",
            }

    def _check_test_immutability(self) -> Dict:
        """Verify tests/ directory unchanged.

        Uses ``git diff HEAD`` when only one commit exists (avoids
        ``HEAD~1`` failure on first commit).
        """
        try:
            # Check if HEAD~1 is valid
            ancestor_check = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD~1"],
                capture_output=True,
                text=True,
                cwd=self.cwd,
            )

            if ancestor_check.returncode == 0:
                diff_ref = "HEAD~1"
            else:
                # Only one commit — diff against the empty tree
                diff_ref = "4b825dc642cb6eb9a060e54bf899d69f82cf7657"

            result = subprocess.run(
                ["git", "diff", diff_ref, "--", "tests/"],
                capture_output=True,
                text=True,
                cwd=self.cwd,
            )

            if len(result.stdout.strip()) == 0:
                return {"name": "test_immutability", "passed": True}
            else:
                return {
                    "name": "test_immutability",
                    "passed": False,
                    "error": "tests/ directory was modified - this is not allowed",
                }

        except Exception as e:
            return {
                "name": "test_immutability",
                "passed": False,
                "error": f"Git check failed: {e}",
            }

    def _check_assert_count(self) -> Dict:
        """Verify assert count hasn't decreased"""
        try:
            result = subprocess.run(
                ["grep", "-r", "assert", "tests/"],
                capture_output=True,
                text=True,
                cwd=self.cwd,
            )

            current_count = (
                len(result.stdout.strip().split("\n"))
                if result.stdout.strip()
                else 0
            )
            baseline_count = self.baseline.get("assert_count", 0)

            if current_count >= baseline_count:
                return {
                    "name": "assert_count",
                    "passed": True,
                    "baseline": baseline_count,
                    "current": current_count,
                }
            else:
                return {
                    "name": "assert_count",
                    "passed": False,
                    "baseline": baseline_count,
                    "current": current_count,
                    "error": f"Assert count decreased from {baseline_count} to {current_count}",
                }

        except Exception as e:
            return {
                "name": "assert_count",
                "passed": False,
                "error": f"Assert count check failed: {e}",
            }

    def _check_coverage(self) -> Dict:
        """Verify test coverage hasn't dropped significantly"""
        try:
            subprocess.run(
                ["pytest", "--cov", "--cov-report=json"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.cwd,
            )

            # Parse coverage from JSON report
            cov_file = Path(self.cwd or ".") / "coverage.json"
            try:
                with open(cov_file) as f:
                    cov_data = json.load(f)
                    current_cov = cov_data["totals"]["percent_covered"]
            except Exception:
                current_cov = 0.0

            baseline_cov = self.baseline.get("coverage", 0.0)

            # Allow 1% drop
            if current_cov >= baseline_cov - 1.0:
                return {
                    "name": "coverage",
                    "passed": True,
                    "baseline": baseline_cov,
                    "current": current_cov,
                }
            else:
                return {
                    "name": "coverage",
                    "passed": False,
                    "baseline": baseline_cov,
                    "current": current_cov,
                    "error": f"Coverage dropped from {baseline_cov:.1f}% to {current_cov:.1f}%",
                }

        except Exception as e:
            return {
                "name": "coverage",
                "passed": False,
                "error": f"Coverage check failed: {e}",
            }

    def init_baseline(self):
        """Initialize baseline metrics and save to dedicated baseline file."""
        print("Initializing baseline metrics...")

        # Get assert count
        try:
            result = subprocess.run(
                ["grep", "-r", "assert", "tests/"],
                capture_output=True,
                text=True,
                cwd=self.cwd,
            )
            assert_count = (
                len(result.stdout.strip().split("\n"))
                if result.stdout.strip()
                else 0
            )
        except Exception:
            assert_count = 0

        # Get coverage
        try:
            subprocess.run(
                ["pytest", "--cov", "--cov-report=json"],
                capture_output=True,
                timeout=120,
                cwd=self.cwd,
            )
            cov_file = Path(self.cwd or ".") / "coverage.json"
            with open(cov_file) as f:
                cov_data = json.load(f)
                coverage = cov_data["totals"]["percent_covered"]
        except Exception:
            coverage = 0.0

        baseline_doc = {
            "initialized": datetime.now().isoformat(),
            "baseline": {
                "assert_count": assert_count,
                "coverage": coverage,
            },
        }

        with open(self.baseline_path, "w") as f:
            json.dump(baseline_doc, f, indent=2)

        print(f"Baseline saved to {self.baseline_path}")
        print(f"  Assert count: {assert_count}")
        print(f"  Coverage: {coverage:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="External Oracle Validator")
    parser.add_argument("--task-id", help="Task ID being validated")
    parser.add_argument(
        "--init-baseline",
        action="store_true",
        help="Initialize baseline metrics",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file",
    )

    args = parser.parse_args()

    # Determine project_root from config for cwd
    project_cwd = None
    config_path = Path(args.config)
    try:
        with open(config_path) as f:
            config = json.load(f)
        raw_root = config.get("project_root")
        if raw_root:
            project_cwd = Path(raw_root).resolve()
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    oracle = OracleValidator(
        config_path=config_path,
        cwd=project_cwd,
    )

    if args.init_baseline:
        oracle.init_baseline()
        sys.exit(0)

    if not args.task_id:
        print("Error: --task-id required (or use --init-baseline)")
        sys.exit(1)

    # Run validation
    results = oracle.validate(args.task_id)

    # Print summary
    print(f"\n{'='*60}")
    print(f"Oracle Validation: {args.task_id}")
    print(f"{'='*60}")

    for check in results["checks"]:
        if check.get("skipped"):
            print(f"- {check['name']} (skipped)")
            continue
        status = "PASS" if check["passed"] else "FAIL"
        print(f"{status} {check['name']}")
        if not check["passed"] and "error" in check:
            print(f"  Error: {check['error'][:200]}")

    print(f"\n{results['summary']}")
    print(f"{'='*60}\n")

    sys.exit(0 if results["passed"] else 1)


if __name__ == "__main__":
    main()
