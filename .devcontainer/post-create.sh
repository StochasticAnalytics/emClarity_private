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

# 2. Install claude_core in editable mode — also installs all project
#    Python deps (scientific, GPU, dashboard, dev tooling) via setup.py.
#    This MUST run before any subsequent step that depends on claude_core
#    being importable. Cluster 4 of the permissions audit makes
#    claude_core.paths the single source of truth for project paths,
#    so any later step (including the gh auth probe in step 3) can
#    safely import from claude_core.
pip install -e "$DOT_CLAUDE_DIR" --quiet

# 3. GitHub CLI auth probe (F44 from the permissions audit)
#    Build-time check that gh is authenticated. The session-time check
#    (F43) at on_session_startup.sh fires too late — by the time you
#    notice gh is broken, you've already wasted setup work. Failing
#    here means the user fixes auth while still watching container
#    build output, before any session is ever launched.
#    No escape hatch: same rule as F43. The original WI-128 spec_draft
#    proposed CLAUDE_SKIP_GH_CHECK=1 as a placeholder; that was overruled
#    2026-04-07 because it recreates the silent-fallback class of bug.
if ! gh api /user --silent 2>/dev/null; then
    echo "ERROR: gh CLI is not authenticated." >&2
    echo "  pipeline_add and any GitHub-issue-backed tooling will fail." >&2
    echo "  Fix: run 'gh auth login' on the host, then rebuild the container." >&2
    exit 1
fi

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

# 6. Add bashrc function to route `claude` through the launcher
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
