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

# 1. Symlink ~/.claude so IDE plugins find config at default path
ln -sfn "$CLAUDE_CONFIG_DIR" ~/.claude

# 2. Install claude_core in editable mode so skill scripts can import it
pip install -e "$DOT_CLAUDE_DIR" --quiet

# 3. Add bashrc function to route `claude` through the launcher
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

# 4. Run interactive mount access validator on first terminal open
echo 'python3 $DOT_CLAUDE_DIR/.claude/scripts/validate_mount_access.py 2>/dev/null' >> ~/.bashrc

echo "✓ Claude integration setup complete"
