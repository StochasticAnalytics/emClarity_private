#!/usr/bin/env bash
#
# Configure git identity inside the devcontainer.
#
# Priority:
#   1. GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL env vars (if set)
#   2. Fall through — let VS Code's default forwarding handle it
#
# Called by devcontainer.json postCreateCommand.

configure_if_unset() {
    local current_name current_email

    current_name="$(git config --global user.name 2>/dev/null)"
    current_email="$(git config --global user.email 2>/dev/null)"

    # If git identity is already configured (e.g., VS Code forwarded it), done
    if [ -n "$current_name" ] && [ -n "$current_email" ]; then
        echo "Git identity already configured: ${current_name} <${current_email}>"
        return 0
    fi

    # Try env vars
    if [ -n "$GIT_AUTHOR_NAME" ] && [ -n "$GIT_AUTHOR_EMAIL" ]; then
        git config --global user.name "$GIT_AUTHOR_NAME"
        git config --global user.email "$GIT_AUTHOR_EMAIL"
        echo "Git identity set from env: ${GIT_AUTHOR_NAME} <${GIT_AUTHOR_EMAIL}>"
        return 0
    fi

    echo "WARNING: Git identity not configured."
    echo "  Set GIT_AUTHOR_NAME and GIT_AUTHOR_EMAIL in devcontainer.json remoteEnv,"
    echo "  or configure git globally on your local machine."
    return 0  # Non-fatal — don't block container creation
}

configure_if_unset
