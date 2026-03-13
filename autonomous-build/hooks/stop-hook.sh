#!/bin/bash
# Stop Hook - Prevents premature task completion claims

# Check if tests actually pass
echo "Running validation before allowing completion..."

# TypeScript compile
echo "→ TypeScript compilation..."
npx tsc --noEmit
if [ $? -ne 0 ]; then
    echo "✗ TypeScript compilation failed"
    echo "Cannot mark task complete while TypeScript has errors"
    exit 1
fi

# Backend tests
echo "→ Backend tests..."
pytest backend/ -v
if [ $? -ne 0 ]; then
    echo "✗ Backend tests failed"
    echo "Cannot mark task complete while tests failing"
    exit 1
fi

# E2E tests
echo "→ E2E tests..."
pytest tests/ -v
if [ $? -ne 0 ]; then
    echo "✗ E2E tests failed"
    echo "Cannot mark task complete while tests failing"
    exit 1
fi

echo "✓ All validations passed"
exit 0
