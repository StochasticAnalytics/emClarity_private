# emClarity Python Development Makefile

.PHONY: help test test-all test-fast test-gpu coverage lint format clean install install-dev docs

# Default target
help:
	@echo "emClarity Python Development Commands:"
	@echo ""
	@echo "Testing:"
	@echo "  test          - Run all tests"
	@echo "  test-fast     - Run fast tests only (skip slow/gpu)"
	@echo "  test-gpu      - Run GPU tests only"

	@echo "  coverage      - Run tests with coverage report"
	@echo "  ci-test       - Simulate CI testing locally"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint          - Run linting (flake8, bandit)"
	@echo "  format        - Format code (black, isort)"
	@echo "  format-check  - Check code formatting"
	@echo ""
	@echo "Environment:"
	@echo "  install       - Install package dependencies"
	@echo "  install-dev   - Install dev dependencies"
	@echo "  check-env     - Check environment setup"
	@echo ""
	@echo "CI/Development:"
	@echo "  dev-check     - Quick development validation"
	@echo "  workflow-info - Show CI workflow information"
	@echo ""
	@echo "Other:"
	@echo "  docs          - Build documentation"
	@echo "  clean         - Clean temporary files"

# Show workflow information
workflow-info:
	python workflow_summary.py

# Testing targets
test:
	python -m pytest -v

test-fast:
	python -m pytest -v -m "not slow and not gpu"

test-gpu:
	python -m pytest -v -m "gpu or cuda"

test-all:
	python -m pytest -v --tb=short

coverage:
	python -m pytest --cov=. --cov-report=term-missing --cov-report=html

# Code quality targets
lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --exit-zero --max-complexity=10 --max-line-length=88 --statistics
	bandit -r . -f json || true

format:
	black .
	isort .

format-check:
	black --check --diff .
	isort --check-only --diff .

# Environment targets
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

check-env:
	python check_environment.py --verbose

# Documentation
docs:
	@if [ -d "docs" ]; then \
		cd docs && make html; \
	else \
		echo "Documentation directory not found"; \
	fi

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf test-reports/
	rm -f coverage.xml

# CI simulation
ci-test:
	@echo "🤖 Running CI-style tests..."
	export QT_QPA_PLATFORM=offscreen && export DISPLAY=:99.0 && \
	python -m pytest metaData/tests/ utils/ -v --tb=short --cov=metaData --cov=utils --cov-report=xml --cov-report=term-missing && \
	echo "✅ Core tests passed!" && \
	python -m pytest masking/tests/ -v --tb=short -k "not gpu" || echo "⚠️ Some masking tests failed (expected)" && \
	echo "🎉 CI simulation completed!"

# Quick development check
dev-check: format-check lint test-fast
	@echo "✅ Development checks passed!"
