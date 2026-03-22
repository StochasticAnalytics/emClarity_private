# Development Setup Guide: New Linting Tools

This guide covers the transition from black/isort/flake8/mypy to ruff/pyright/bandit/safety.

## Quick Start

1. **Install the new tools:**
   ```bash
   pip install -e .[dev]  # Installs ruff, pyright, bandit, safety
   ```

2. **Run the migration script:**
   ```bash
   python migrate_to_ruff.py
   ```

3. **Update pre-commit hooks:**
   ```bash
   pre-commit install
   pre-commit run --all-files
   ```

## Tool Overview

### Ruff (Replaces: black + isort + flake8 + many plugins)
- **Purpose**: Linting, formatting, and import sorting in one tool
- **Speed**: 10-100x faster than the old tools
- **Configuration**: `pyproject.toml` under `[tool.ruff]`

**Common commands:**
```bash
# Lint and auto-fix
ruff check python/ --fix

# Format code
ruff format python/

# Check specific rules
ruff check python/ --select F,E,W

# Show what would be fixed
ruff check python/ --diff
```

### Pyright (Replaces: mypy)
- **Purpose**: Static type checking
- **Speed**: Faster than mypy, better editor integration
- **Configuration**: `pyproject.toml` under `[tool.pyright]`

**Common commands:**
```bash
# Type check all files
pyright python/

# Type check specific files
pyright python/metaData/emc_parameter_converter.py

# Watch mode for development
pyright --watch python/
```

### Bandit (Security linting)
- **Purpose**: Find common security issues
- **Configuration**: `pyproject.toml` under `[tool.bandit]`

**Common commands:**
```bash
# Security scan
bandit -r python/ -c pyproject.toml

# Generate detailed report
bandit -r python/ -c pyproject.toml -f json -o security-report.json
```

### Safety (Dependency vulnerability scanning)
- **Purpose**: Check for known vulnerabilities in dependencies
- **Usage**: Scans installed packages

**Common commands:**
```bash
# Check for vulnerabilities
safety check

# Generate report
safety check --json --output safety-report.json
```

## Editor Configuration

### VS Code
Add to your `settings.json`:
```json
{
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "none",
  "python.analysis.typeCheckingMode": "basic",
  "ruff.enable": true,
  "ruff.organizeImports": true,
  "ruff.fixAll": true,
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.fixAll.ruff": true,
    "source.organizeImports.ruff": true
  }
}
```

### PyCharm/IntelliJ
1. Install the Ruff plugin
2. Configure Ruff as the formatter and linter
3. Enable Pyright or configure the built-in type checker

## Rule Configuration

The new setup enables comprehensive checking:

- **E, W, F**: Standard Python style and syntax
- **I**: Import sorting (replaces isort)
- **UP**: Modern Python syntax (pyupgrade equivalent)
- **B**: Bug detection (flake8-bugbear)
- **N**: Naming conventions
- **C90**: Complexity checking
- **PIE, SIM**: Code simplification
- **T20**: Print statement detection
- **PD**: Pandas best practices
- **PL**: Pylint-style checks
- **RUF**: Ruff-specific rules
- **D**: Docstring style

### Ignoring Rules

To ignore specific rules temporarily:
```python
# ruff: noqa: E501  # Line too long
long_line = "This is a very long line that exceeds the limit but is necessary"

# ruff: noqa  # Ignore all rules for this line
problematic_code()
```

For permanent ignores, update `pyproject.toml`:
```toml
[tool.ruff.lint]
ignore = ["E501", "D101"]  # Ignore line length and missing docstrings
```

## Pre-commit Integration

The new pre-commit hooks run automatically on commit:

1. **Ruff linting** with auto-fixes
2. **Ruff formatting** 
3. **Pyright type checking**
4. **Bandit security scanning**
5. **Basic file checks** (trailing whitespace, etc.)

To run manually:
```bash
pre-commit run --all-files
```

To skip hooks temporarily:
```bash
git commit -m "message" --no-verify
```

## Migration Notes

### From Black/isort
- Ruff's formatter is compatible with Black
- Import sorting behavior matches isort with `profile = "black"`
- Line length defaults to 88 characters (Black's default)

### From Flake8
- Most flake8 rules are included in Ruff's default set
- Plugin functionality (bugbear, etc.) is built into Ruff
- Custom ignore lists have been migrated to `pyproject.toml`

### From MyPy
- Pyright provides similar type checking with better performance
- Some mypy-specific annotations may need adjustment
- Pyright is more strict about some type issues

## Troubleshooting

### Common Issues

1. **Too many lint errors**: Use `ruff check --fix` to auto-fix many issues
2. **Type checking failures**: Add type annotations gradually
3. **Import order conflicts**: Ruff handles this automatically now
4. **Performance in large repos**: Ruff is designed for speed

### Getting Help

- **Ruff docs**: https://docs.astral.sh/ruff/
- **Pyright docs**: https://microsoft.github.io/pyright/
- **Bandit docs**: https://bandit.readthedocs.io/

### Reverting Changes

If you need to temporarily revert:
1. Checkout the old configuration files
2. Reinstall old tools: `pip install black isort flake8 mypy`
3. Run `pre-commit clean && pre-commit install`

## Performance Comparison

The new setup is significantly faster:

- **Ruff**: ~100x faster than flake8, ~10x faster than black
- **Pyright**: ~5-10x faster than mypy
- **Overall**: Developer feedback loop improved dramatically

This speed improvement makes it practical to run comprehensive checks on every save/commit.
