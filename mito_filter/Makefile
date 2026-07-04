.PHONY: venv fmt lint type test all

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

venv:
	python3.12 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

fmt:
	$(PY) -m isort src tests
	$(PY) -m black src tests

lint:
	$(PY) -m flake8 src tests

type:
	$(PY) -m mypy src

test:
	$(PY) -m pytest -q

all: fmt lint type test
