#!/usr/bin/env python3
"""
emClarity Python Environment Checker.

Quick dependency verification for emClarity Python development.
Run this to verify all required packages are available.

Usage:
    python check_environment.py
    python check_environment.py --verbose
"""

import argparse
import sys


def check_dependencies(verbose: bool = False) -> dict[str, bool]:
    """Check all emClarity dependencies and return status."""
    # Core dependencies with correct import names
    required_packages = [
        ("numpy", "numpy"),
        ("scipy", "scipy"),
        ("mrcfile", "mrcfile"),
        ("jsonschema", "jsonschema"),
        ("cupy", "cupy"),
        ("matplotlib", "matplotlib"),
        ("PIL", "pillow"),  # Pillow imports as PIL
    ]

    # Development tools
    dev_packages = [
        ("pytest", "pytest"),
        ("coverage", "coverage"),
        ("black", "black"),
        ("flake8", "flake8"),
    ]

    status = {"core": True, "dev": True, "details": {}}

    if verbose:
        print("=== emClarity Python Environment Status ===\n")

    # Check core dependencies
    if verbose:
        print("📦 CORE DEPENDENCIES")

    for import_name, display_name in required_packages:
        try:
            module = __import__(import_name)
            if hasattr(module, "__version__"):
                version = module.__version__
            elif import_name == "PIL":
                from PIL import Image

                version = getattr(Image, "__version__", "unknown")
            else:
                version = "unknown"

            status["details"][display_name] = {"available": True, "version": version}
            if verbose:
                print(f"  ✓ {display_name:<12} {version}")

        except ImportError:
            status["core"] = False
            status["details"][display_name] = {"available": False, "version": None}
            if verbose:
                print(f"  ❌ {display_name:<12} MISSING (REQUIRED)")

    # Check development tools
    if verbose:
        print("\n🛠️  DEVELOPMENT TOOLS")

    dev_available = 0
    for import_name, display_name in dev_packages:
        try:
            module = __import__(import_name)
            version = getattr(module, "__version__", "unknown")
            status["details"][f"dev_{display_name}"] = {
                "available": True,
                "version": version,
            }
            dev_available += 1
            if verbose:
                print(f"  ✓ {display_name:<12} {version}")
        except ImportError:
            status["details"][f"dev_{display_name}"] = {
                "available": False,
                "version": None,
            }
            if verbose:
                print(f"  ⚠️ {display_name:<12} missing (dev tool)")

    status["dev"] = dev_available == len(dev_packages)

    # Summary
    if verbose:
        print()
        if status["core"]:
            print("🎉 READY: All core dependencies available!")
            print("🚀 emClarity Python environment is fully functional!")
            if status["dev"]:
                print("🔧 BONUS: All development tools available!")
        else:
            print("⚠️ WARNING: Missing required dependencies.")
            print("Run: pip install -r requirements.txt")

        print("\nStatus Summary:")
        print(
            f"  - Core packages: {'✓' if status['core'] else '❌'} {'Ready' if status['core'] else 'Missing dependencies'}"
        )
        print(
            f"  - Dev tools: {'✓' if status['dev'] else '⚠️'} {'Ready' if status['dev'] else 'Some missing'}"
        )

    return status


def main():
    parser = argparse.ArgumentParser(description="Check emClarity Python environment")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Only show errors")

    args = parser.parse_args()

    if args.quiet and args.verbose:
        print("Cannot use --quiet and --verbose together")
        sys.exit(1)

    verbose = args.verbose or not args.quiet
    status = check_dependencies(verbose=verbose)

    # Exit codes: 0 = all good, 1 = missing core deps, 2 = missing dev tools
    if not status["core"]:
        sys.exit(1)
    elif not status["dev"] and not args.quiet:
        print("Core dependencies OK, but some dev tools missing")
        sys.exit(0)
    else:
        if args.quiet:
            print("✓ Ready")
        sys.exit(0)


if __name__ == "__main__":
    main()
