#!/usr/bin/env bash
# Validate X11 environment before container launch.
# Called from devcontainer.json initializeCommand.
# Exits non-zero with clear message if DISPLAY or XAUTHORITY are missing.

set -euo pipefail

errors=0

if [ -z "${DISPLAY:-}" ]; then
    echo "ERROR: DISPLAY is not set on the host." >&2
    echo "  X11 forwarding requires a running X server." >&2
    echo "  Check that your display manager is active and DISPLAY is exported." >&2
    errors=1
fi

if [ -z "${XAUTHORITY:-}" ]; then
    echo "ERROR: XAUTHORITY is not set on the host." >&2
    echo "  X11 auth requires an .Xauthority file path." >&2
    echo "  Typically: export XAUTHORITY=\$HOME/.Xauthority" >&2
    errors=1
elif [ ! -f "${XAUTHORITY}" ]; then
    echo "ERROR: XAUTHORITY points to '${XAUTHORITY}' but file does not exist." >&2
    errors=1
fi

if [ "$errors" -ne 0 ]; then
    echo "" >&2
    echo "Container launch aborted. Fix X11 environment and retry." >&2
    exit 1
fi

echo "✓ X11 environment validated (DISPLAY=${DISPLAY}, XAUTHORITY=${XAUTHORITY})"
