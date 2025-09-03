#!/bin/bash
# Modern Python development setup for emClarity

set -e

echo "🚀 Setting up emClarity Python development environment"

# Check if we're already in a virtual environment
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "✅ Already in virtual environment: $VIRTUAL_ENV"
else
    echo "📦 Creating virtual environment..."
    python -m venv venv
    echo "🔧 Activating virtual environment..."
    source venv/bin/activate
fi

echo "⬆️  Upgrading pip..."
pip install --upgrade pip

echo "📋 Installing project in development mode with dependencies..."
pip install -e ".[dev,test]"

echo "🔧 Installing pre-commit hooks..."
pre-commit install

echo "✅ Development environment ready!"
echo ""
echo "To activate the environment manually:"
echo "  source venv/bin/activate"
echo ""
echo "To run tests:"
echo "  pytest"
echo ""
echo "To run the GUI:"
echo "  emclarity-gui"
echo ""
echo "To run linting:"
echo "  black python/"
echo "  isort python/"
echo "  flake8 python/"
