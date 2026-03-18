"""Machine-level configuration helpers.

Reads configuration from environment variables. Can be expanded later
for additional machine-specific settings.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_registry_dir() -> Path:
    """Return the registry directory path.

    Reads from ``EMCLARITY_REGISTRY_DIR`` environment variable, defaulting
    to ``~/.emclarity`` if not set or empty.
    """
    env_value = os.environ.get("EMCLARITY_REGISTRY_DIR", "").strip()
    if env_value:
        return Path(env_value)
    return Path.home() / ".emclarity"
