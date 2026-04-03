#!/usr/bin/env bash
# postCreateCommand for devcontainer — runs once after container creation.
# Extracted from devcontainer.json for readability and maintainability.
set -euo pipefail

# Allow disabling Claude integration entirely
if [ "${CLAUDE_CONFIG_DIR:-}" = "0" ] || [ "${CLAUDE_CONFIG_DIR:-}" = "false" ]; then
    echo "Claude integration disabled — skipping Claude setup"
    exit 0
fi

# Fail fast if CLAUDE_CONFIG_DIR not set
if [ -z "${CLAUDE_CONFIG_DIR:-}" ]; then
    echo "ERROR: CLAUDE_CONFIG_DIR not set. Run: devcontainer-launch.py <user> <workspace>" >&2
    echo "Or set CLAUDE_CONFIG_DIR=0 in host env to skip Claude setup entirely." >&2
    exit 1
fi

# 1. Install system packages not in base image
#    lsof: required by start-dashboard.sh for port diagnostics
if ! command -v lsof &>/dev/null; then
    sudo apt-get update -qq && sudo apt-get install -y -qq lsof
fi

# 2. Symlink ~/.claude so IDE plugins find config at default path
ln -sfn "$CLAUDE_CONFIG_DIR" ~/.claude

# 3. Install claude_core in editable mode — also installs all project
#    Python deps (scientific, GPU, dashboard, dev tooling) via setup.py
pip install -e "$DOT_CLAUDE_DIR" --quiet

# 3b. Wire safe-cp/safe-mv aliases before interactive guard
#     Pre-guard placement: aliases protect both interactive and non-interactive shells.
#     Double quotes: variable expands at write time to concrete path.
_SAFE_CP="alias cp=\"${PROJECT_ROOT}/dot-claude/usr/bin/safe-cp.py \""
_SAFE_MV="alias mv=\"${PROJECT_ROOT}/dot-claude/usr/bin/safe-mv.py \""
_MARKER="# If not running interactively"

if grep -qF "$_MARKER" ~/.bashrc; then
    sed -i "/${_MARKER}/i\\${_SAFE_CP}\n${_SAFE_MV}" ~/.bashrc
else
    # Marker not found — prepend to top of file as fail-safe
    printf '%s\n%s\n' "${_SAFE_CP}" "${_SAFE_MV}" | cat - ~/.bashrc > ~/.bashrc.tmp
    /usr/bin/mv ~/.bashrc.tmp ~/.bashrc
fi

# 4. Add bashrc function to route `claude` through the launcher
cat >> ~/.bashrc << 'BASHRC'
claude() {
    local launcher="$DOT_CLAUDE_DIR/.claude/scripts/claude-launcher.py"
    if [[ -f "$launcher" ]]; then
        python3 "$launcher" "$@"
    else
        echo "ERROR: claude-launcher.py not found at $launcher" >&2
        return 1
    fi
}
export -f claude
BASHRC

echo "✓ Claude integration setup complete"
