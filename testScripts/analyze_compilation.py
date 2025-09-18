#!/usr/bin/env python3
"""
Analyze emClarity compilation output to show only important information.
Filters out repetitive warnings while preserving errors and key milestones.
"""

import sys
import re


def main():
    # Counters for different message types
    temp_var_warnings = 0
    mex_compiled = 0
    errors = []
    other_warnings = []
    important_lines = []

    # Patterns to identify different message types
    temp_var_pattern = re.compile(r"The temporary variable .* will be cleared")
    depfun_pattern = re.compile(r"In matlab\.depfun\.internal")
    mex_success_pattern = re.compile(r"MEX completed successfully")
    error_pattern = re.compile(r"Error:|error:|ERROR:|Error in|Error using|Undefined.*variable|Undefined.*function|{Error|contains the following syntax error")
    building_pattern = re.compile(r"Building with")

    # Read from stdin or file
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines
        if not line:
            i += 1
            continue

        # Count temporary variable warnings but don't print them
        if temp_var_pattern.search(line):
            temp_var_warnings += 1
            # Skip the next few lines that are part of this warning
            while i < len(lines) - 1:
                i += 1
                next_line = lines[i].strip()
                if not next_line or not (depfun_pattern.search(next_line) or
                                        "runtime error" in next_line or
                                        "Uninitialized Temporaries" in next_line or
                                        "> In" in next_line):
                    i -= 1
                    break

        # Track MEX compilations
        elif mex_success_pattern.search(line):
            mex_compiled += 1
            important_lines.append(f"✓ MEX file compiled (#{mex_compiled})")

        # Capture errors
        elif error_pattern.search(line):
            if "runtime error will occur" not in line:
                errors.append(line)
                # Get context
                if i > 0:
                    errors.append(f"  Context: {lines[i-1].strip()}")
                if i < len(lines) - 1:
                    errors.append(f"  Next: {lines[i+1].strip()}")

        # Track build starts
        elif building_pattern.search(line):
            important_lines.append("⚙ Building MEX file...")

        # Other warnings (not temp variables)
        elif "Warning:" in line and "Name is nonexistent" not in line:
            if temp_var_pattern.search(line):
                temp_var_warnings += 1
            else:
                other_warnings.append(line[:100] + "..." if len(line) > 100 else line)

        # Compilation progress indicators
        elif any(keyword in line for keyword in ["Analyzing", "Packaging", "Creating"]):
            important_lines.append(line)

        i += 1

    # Print summary
    print("=" * 80)
    print("EMCLARITY COMPILATION ANALYSIS")
    print("=" * 80)

    # Errors first
    if errors:
        print("\n❌ ERRORS FOUND:")
        print("-" * 40)
        for error in errors:
            print(error)
        print()
    else:
        print("\n✅ No compilation errors detected")

    # Summary statistics
    print("\n📊 SUMMARY:")
    print(f"  • MEX files compiled: {mex_compiled}")
    print(f"  • Temporary variable warnings: {temp_var_warnings} (filtered)")
    print(f"  • Other warnings: {len(other_warnings)}")

    # Show first few other warnings
    if other_warnings:
        print("\n⚠ OTHER WARNINGS (first 5):")
        for warning in other_warnings[:5]:
            print(f"  • {warning}")
        if len(other_warnings) > 5:
            print(f"  ... and {len(other_warnings) - 5} more")

    # Key milestones
    if important_lines:
        print("\n📍 KEY MILESTONES:")
        for line in important_lines[-10:]:  # Last 10 important events
            print(f"  {line}")

    print("\n" + "=" * 80)

    # Return exit code based on errors
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())