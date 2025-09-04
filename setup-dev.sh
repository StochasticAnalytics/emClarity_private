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

echo "🔢 Installing CUDA dependencies..."
# Detect CUDA version and install appropriate CuPy
if command -v nvcc &> /dev/null; then
    CUDA_VERSION=$(nvcc --version | grep "release" | sed -n 's/.*release \([0-9]\+\.[0-9]\+\).*/\1/p')
    echo "   Detected CUDA version: $CUDA_VERSION"
    
    # Install CuPy based on CUDA version
    if [[ "$CUDA_VERSION" == "12."* ]]; then
        echo "   Installing CuPy for CUDA 12.x..."
        pip install cupy-cuda12x fastrlock
    elif [[ "$CUDA_VERSION" == "11."* ]]; then
        echo "   Installing CuPy for CUDA 11.x..."
        pip install cupy-cuda11x fastrlock
    else
        echo "   ⚠️  Unsupported CUDA version, installing CuPy for CUDA 12.x..."
        pip install cupy-cuda12x fastrlock
    fi
else
    echo "   ⚠️  NVCC not found, installing CuPy for CUDA 12.x (may not work without CUDA)..."
    pip install cupy-cuda12x fastrlock
fi

# Install additional packages commonly needed for CUDA and scientific computing
echo "📊 Installing additional scientific packages..."
pip install psutil joblib

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
echo "  black python/ && isort python/ && ruff python/"
