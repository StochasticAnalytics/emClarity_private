#!/bin/bash
# claude-launcher.sh — Launch claude with orchestrator-compatible flags + local memory
#
# Usage:
#   ./claude-launcher.sh                     # interactive session with memory
#   ./claude-launcher.sh "your prompt"       # one-shot with memory
#   ./claude-launcher.sh --print "prompt"    # print mode with memory
#
# This ensures every claude session (interactive or orchestrated) has access
# to the accumulated project knowledge in memories/MEMORY.md.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_FILE="${SCRIPT_DIR}/memories/MEMORY.md"

# Build the append-system-prompt from local memory compendium
MEMORY_ARGS=()
if [ -f "$MEMORY_FILE" ]; then
    MEMORY_CONTENT=$(cat "$MEMORY_FILE")
    if [ -n "$MEMORY_CONTENT" ]; then
        MEMORY_ARGS=("--append-system-prompt" "$MEMORY_CONTENT")
    fi
else
    echo "Warning: No memory file found at ${MEMORY_FILE}" >&2
fi

exec claude \
    --dangerously-skip-permissions \
    --chrome \
    --effort high \
    "${MEMORY_ARGS[@]}" \
    "$@"
