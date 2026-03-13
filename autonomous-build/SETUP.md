# Setup Guide - Detailed Installation

## System Requirements

### Software

- **Python:** 3.10 or later
- **Node.js:** 18 or later
- **Git:** Any recent version
- **Claude API Access:** Anthropic API key with sufficient credits

### Hardware

- **CPU:** Multi-core recommended (parallel oracle checks)
- **RAM:** 8GB minimum, 16GB recommended
- **Disk:** 10GB free (for node_modules, Python env, build artifacts)

### Operating System

Tested on:
- macOS 12+
- Ubuntu 20.04+
- Windows 10+ (WSL2 required)

## Installation Steps

### 1. Extract Archive

```bash
# Navigate to your project repository
cd /path/to/your-project

# Create .claude directory
mkdir -p .claude
cd .claude

# Extract autonomous build system
tar -xzf autonomous-build-system.tar.gz

# Navigate into extracted directory
cd autonomous-build
```

You should now see:

```
autonomous-build/
├── README.md
├── QUICKSTART.md
├── SETUP.md (this file)
├── orchestrator.py
├── oracle.py
├── task_splitter.py
├── prompts/
├── hooks/
├── templates/
├── guides/
└── config.example.json
```

### 2. Python Environment

**Option A: System Python**

```bash
# Install dependencies globally
pip install anthropic pytest pytest-cov

# Verify
python -c "import anthropic; print('✓ Anthropic SDK installed')"
python -c "import pytest; print('✓ pytest installed')"
```

**Option B: Virtual Environment (Recommended)**

```bash
# Create virtual environment
python -m venv venv

# Activate
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install anthropic pytest pytest-cov

# Verify
which python  # Should point to venv/bin/python
```

### 3. Node.js Environment

```bash
# Verify Node.js installed
node --version  # Should be 18+
npm --version

# If not installed:
# - macOS: brew install node
# - Ubuntu: apt install nodejs npm
# - Windows: Download from nodejs.org

# Initialize package.json in your project root
cd ../../  # Back to project root
npm init -y

# Install TypeScript and testing tools
npm install -D typescript @types/node
npm install -D pytest  # If using playwright for E2E
```

### 4. Configuration

```bash
cd .claude/autonomous-build

# Copy example config
cp config.example.json config.json

# Edit config.json
nano config.json  # or vim, code, etc.
```

**Edit these fields:**

```json
{
  "claude_api_key": "sk-ant-api03-YOUR-ACTUAL-API-KEY-HERE",
  "model": "claude-sonnet-4-20250514",
  "developer_tools": ["read", "write", "edit", "bash", "grep", "glob"],
  "qa_tools": ["read", "bash", "grep", "glob"],
  "max_context_tokens": 200000,
  "context_warning_threshold": 0.70,
  "context_split_threshold": 0.85
}
```

**Get API key from:** https://console.anthropic.com/

### 5. Test Directory Setup

```bash
# Navigate to project root
cd ../../

# Create tests directory if doesn't exist
mkdir -p tests backend

# Write a simple initial test
cat > tests/test_basic.py << 'EOF'
def test_placeholder():
    """Placeholder test for baseline"""
    assert True
EOF

# Lock tests directory (critical!)
chmod -R 444 tests/

# Verify lock
ls -la tests/  # Should show r--r--r-- (read-only)
```

**Why lock tests:**  
Prevents Developer agent from modifying tests to make them pass. This is a hard constraint, not a prompt suggestion.

### 6. Initialize Baseline Metrics

```bash
cd .claude/autonomous-build

# Run oracle in initialization mode
python oracle.py --init-baseline
```

**Expected output:**

```
Initializing baseline metrics...
✓ Baseline initialized:
  Assert count: 1
  Coverage: 100.0%
```

This records:
- Current number of assertions in test suite
- Current test coverage percentage

Oracle will ensure these don't decrease during development.

### 7. Git Hooks (Optional but Recommended)

```bash
# Copy pre-commit hook
cp hooks/pre-commit-hook.sh ../../.git/hooks/pre-commit

# Make executable
chmod +x ../../.git/hooks/pre-commit
```

**What the hook does:**
- Blocks commits that modify `tests/` directory
- Warns about suspicious patterns (commented assertions, operator overloads)
- Catches cheating before it reaches QA/Oracle

### 8. Verify Installation

```bash
# Run orchestrator help
python orchestrator.py --help

# Should see:
# usage: orchestrator.py --phase {0,1,2} [--max-iterations N] [--resume]

# Test oracle (without task ID - should fail gracefully)
python oracle.py --help

# Should see usage message

# Test task splitter
python task_splitter.py

# Should see example splitting strategies
```

## First Run Test

### Minimal Test Run

```bash
# Create minimal PRD for testing
cat > templates/prd-test.json << 'EOF'
{
  "_metadata": {
    "phase": "0",
    "created": "2026-03-11T00:00:00Z"
  },
  "_current_task_id": null,
  "tasks": []
}
EOF

# Try dry run (no tasks, should exit immediately)
python orchestrator.py --phase 0 --max-iterations 10 2>&1 | head -20
```

**Expected output:**

```
[Iteration 1/10] No unblocked tasks remaining
✓ No unblocked tasks remaining

Stopped after 0 iterations

=== Orchestrator Run Summary ===
Phase: 0
Iterations: 0
Tasks completed: 0/0
```

**If you see this, installation successful!**

## Troubleshooting Installation

### Python Import Errors

**Problem:** `ModuleNotFoundError: No module named 'anthropic'`

**Fix:**

```bash
# Ensure you're in correct Python environment
which python

# Reinstall dependencies
pip install --upgrade anthropic pytest pytest-cov

# Verify
python -c "import anthropic; import pytest"
```

### Permission Errors on tests/

**Problem:** `chmod: tests/: No such file or directory`

**Fix:**

```bash
# Create tests directory
mkdir -p tests

# Add placeholder test
echo "def test_placeholder(): assert True" > tests/test_basic.py

# Then lock
chmod -R 444 tests/
```

### Node.js Not Found

**Problem:** `npx: command not found`

**Fix:**

```bash
# Install Node.js
# macOS:
brew install node

# Ubuntu:
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify
node --version
npm --version
```

### API Key Issues

**Problem:** `anthropic.AuthenticationError`

**Fix:**

1. Verify key is correct (check https://console.anthropic.com/)
2. Check `config.json` has key in quotes
3. Verify no extra spaces/newlines
4. Test key directly:

```python
import anthropic
client = anthropic.Anthropic(api_key="sk-ant-api03-...")
print(client.models.list())  # Should not error
```

### Git Hooks Not Working

**Problem:** Hook doesn't run on commit

**Fix:**

```bash
# Ensure hook file is executable
chmod +x .git/hooks/pre-commit

# Verify it exists
ls -la .git/hooks/pre-commit

# Test manually
.git/hooks/pre-commit
# Should run checks
```

## Next Steps

✅ Installation complete

**Now proceed to:**

1. **[QUICKSTART.md](QUICKSTART.md)** for rapid first run
2. **[guides/PHASE_0_GUIDE.md](guides/PHASE_0_GUIDE.md)** for detailed Phase 0 workflow
3. **[README.md](README.md)** for complete system reference

## Uninstallation

To remove autonomous build system:

```bash
cd your-project-repo

# Remove autonomous build directory
rm -rf .claude/autonomous-build

# Remove git hooks (if installed)
rm .git/hooks/pre-commit

# Keep or remove baseline data
# rm templates/prd.json templates/progress.txt templates/ci-results.json
```

Your application code is untouched (all autonomous build state is in `.claude/` and `templates/`).
