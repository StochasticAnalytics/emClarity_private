#!/usr/bin/env bash
# postCreateCommand for devcontainer — runs once after container creation.
# Extracted from devcontainer.json for readability and maintainability.
#
# BOOTSTRAP EXCEPTION: This script is the one legitimate self-locator in
# the project. It runs BEFORE `pip install -e dot-claude` (step 2 below),
# so claude_core.paths is not yet importable. PROJECT_ROOT and
# DOT_CLAUDE_DIR are derived from BASH_SOURCE here; every other script
# resolves paths via claude_core.paths after step 2 completes.
#
# Cluster 4 step 7 of the permissions audit removed these variables from
# devcontainer.json containerEnv and remoteEnv. They exist in this
# script's local scope only — they are NOT exported to the environment
# of any other process.
set -euo pipefail

# Self-locate: this file lives at $PROJECT_ROOT/.devcontainer/post-create.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOT_CLAUDE_DIR="$PROJECT_ROOT/dot-claude"

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

# 2. Install claude_core in editable mode — also installs all project
#    Python deps (scientific, GPU, dashboard, dev tooling) via setup.py.
#    This MUST run before any subsequent step that depends on claude_core
#    being importable. Cluster 4 of the permissions audit makes
#    claude_core.paths the single source of truth for project paths,
#    so any later step can safely import from claude_core.
pip install -e "$DOT_CLAUDE_DIR" --quiet

# 3. GitHub CLI auth probe — runs on first interactive terminal open.
#    Moved from build-time (where gh credentials aren't available) to
#    first interactive shell, where the user can run `gh auth login`.
#    The sentinel file prevents the check from repeating on every shell.
cat >> ~/.bashrc << 'GH_AUTH_CHECK'
if [ ! -f /tmp/.gh-auth-checked ]; then
    if ! gh api /user --silent 2>/dev/null; then
        echo "" >&2
        echo "WARNING: gh CLI is not authenticated in this container." >&2
        echo "  pipeline_add and GitHub-issue-backed tooling will fail." >&2
        echo "  Fix: run 'gh auth login' in this terminal." >&2
        echo "" >&2
    fi
    touch /tmp/.gh-auth-checked
fi
GH_AUTH_CHECK

# 4. Wire safe-cp/safe-mv aliases before interactive guard
#    Pre-guard placement: aliases protect both interactive and non-interactive shells.
#    Double quotes: variable expands at write time to concrete path.
#    Full-path overrides (/usr/bin/cp, /usr/bin/mv) are in step 5 below.
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

# 5. Override /usr/bin/cp and /usr/bin/mv as bash functions.
#    Closes the backdoor where scripts call the full path directly.
#    Safe wrappers' subprocess.run uses execve (no shell), so the real
#    binary is still reachable — no infinite loop.
cat >> ~/.bashrc << FUNCS
/usr/bin/cp() { ${PROJECT_ROOT}/dot-claude/usr/bin/safe-cp.py "\$@"; }
/usr/bin/mv() { ${PROJECT_ROOT}/dot-claude/usr/bin/safe-mv.py "\$@"; }
FUNCS

# 6. Add bashrc function to route `claude` through the launcher.
#    Note the unquoted heredoc terminator ("BASHRC" rather than 'BASHRC'):
#    this lets ${DOT_CLAUDE_DIR} expand NOW (write time) to a literal
#    absolute path, while \$launcher and \$@ stay as runtime references.
#    Cluster 4 step 7 removed $DOT_CLAUDE_DIR from the session environment,
#    so the bashrc function cannot read it at call time — the path must
#    be baked in here instead.
cat >> ~/.bashrc << BASHRC
claude() {
    local launcher="${DOT_CLAUDE_DIR}/.claude/scripts/claude-launcher.py"
    if [[ -f "\$launcher" ]]; then
        python3 "\$launcher" "\$@"
    else
        echo "ERROR: claude-launcher.py not found at \$launcher" >&2
        return 1
    fi
}
export -f claude
BASHRC

echo "✓ Claude integration setup complete"
