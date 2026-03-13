#!/bin/bash
# Pre-commit Hook - Validates changes before allowing commit
# Designed for non-interactive (autonomous) use: warnings auto-fail.

# Check for test modifications
echo "Checking test immutability..."
MODIFIED_TESTS=$(git diff --cached --name-only | grep "^tests/")

if [ ! -z "$MODIFIED_TESTS" ]; then
    echo "ERROR: Cannot commit changes to tests/ directory"
    echo ""
    echo "Modified test files:"
    echo "$MODIFIED_TESTS"
    echo ""
    echo "The tests/ directory is read-only. If tests are failing,"
    echo "fix your implementation, not the tests."
    echo ""
    exit 1
fi

# Check for suspicious patterns
echo "Checking for cheat patterns..."

# Check for commented assertions
COMMENTED_ASSERTS=$(git diff --cached | grep "^+.*# *assert")
if [ ! -z "$COMMENTED_ASSERTS" ]; then
    echo "ERROR: Found commented assertions in diff:"
    echo "$COMMENTED_ASSERTS"
    echo ""
    echo "Commenting out assertions is not allowed."
    exit 1
fi

# Check for __eq__ override
EQ_OVERRIDE=$(git diff --cached | grep "def __eq__")
if [ ! -z "$EQ_OVERRIDE" ]; then
    echo "ERROR: Found __eq__ override in diff"
    echo "Overloading __eq__ is not allowed as it may fake test passage."
    exit 1
fi

echo "Pre-commit checks passed"
exit 0
