#!/bin/bash
# Development environment setup script for emClarity Python code quality

set -e  # Exit on any error

echo "🔧 Setting up emClarity Python development environment..."

# Check if we're in the right directory
if [ ! -f "python/setup.py" ]; then
    echo "❌ Error: Please run this script from the emClarity repository root"
    exit 1
fi

# Install Python development dependencies
echo "📦 Installing Python development dependencies..."
pip install black isort flake8 mypy autopep8 pre-commit

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
pre-commit install

# Run initial code quality check
echo "🔍 Running initial code quality checks..."
cd python/

echo "  - Running Black (code formatting)..."
black . --quiet

echo "  - Running isort (import sorting)..."
isort . --quiet

echo "  - Checking Black compliance..."
if black --check . --quiet; then
    echo "    ✅ Black: PASSED"
else
    echo "    ❌ Black: FAILED"
fi

echo "  - Checking isort compliance..."
if isort --check-only . --quiet; then
    echo "    ✅ isort: PASSED"
else
    echo "    ❌ isort: FAILED"
fi

echo "  - Running flake8 (style checking)..."
if flake8 . --max-line-length=100 --ignore=E203,W503 --quiet; then
    echo "    ✅ flake8: PASSED"
else
    echo "    ❌ flake8: Some issues found (see above)"
fi

cd ..

# Create VS Code settings if .vscode directory exists
if [ -d ".vscode" ]; then
    echo "⚙️  Creating VS Code settings..."
    cat > .vscode/settings.json << 'EOF'
{
    "python.formatting.provider": "black",
    "python.sortImports.provider": "isort",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.mypyEnabled": true,
    "python.linting.flake8Args": [
        "--max-line-length=100",
        "--ignore=E203,W503"
    ],
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    },
    "python.defaultInterpreterPath": "./python"
}
EOF
    echo "    ✅ VS Code settings created"
fi

echo ""
echo "🎉 Development environment setup complete!"
echo ""
echo "📝 Quick commands:"
echo "  - Format code:           cd python/ && black . && isort ."
echo "  - Check code quality:    cd python/ && black --check . && isort --check-only . && flake8 ."
echo "  - Run pre-commit:        pre-commit run --all-files"
echo ""
echo "📖 See PYTHON_STYLE_GUIDE.md for detailed coding standards"
