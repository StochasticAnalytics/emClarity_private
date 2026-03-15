"""V1 Filesystem browse API endpoint.

Provides a directory listing endpoint for server-side filesystem navigation.
The endpoint returns only real (non-symlink) subdirectories, allowing frontend
components to let users pick project directories without exposing files.

Response contract (documented for TASK-002b stub):
    GET /api/v1/filesystem/browse?path=<absolute-path>
    200 OK:
        {
            "path":    "/absolute/real/path",
            "parent":  "/absolute/real" | null,   // null only at filesystem root "/"
            "entries": [
                {"name": "subdir", "type": "directory", "path": "/absolute/real/path/subdir"}
            ]
        }

    Error responses all use FastAPI's standard HTTPException body:
        {"detail": "<human-readable string containing the offending path>"}
    with Content-Type: application/json.

    400: path traversal ('..'), null byte, relative path, not-a-directory, too long
    403: permission denied reading the directory
    404: path does not exist (including race-condition removal during listing)
"""

from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/filesystem", tags=["filesystem-v1"])

# Linux PATH_MAX
_PATH_MAX = 4096


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class FilesystemEntry(BaseModel):
    """A single directory entry returned by the browse endpoint."""

    name: str
    type: Literal["directory"]
    path: str


class BrowseResponse(BaseModel):
    """Response body for GET /api/v1/filesystem/browse."""

    path: str
    parent: str | None
    entries: list[FilesystemEntry]


# ---------------------------------------------------------------------------
# Path validation helper
# ---------------------------------------------------------------------------


@dataclass
class _BrowsePath:
    """Holds both the OS-level real path and a display path for error messages.

    ``real``    – fully resolved via os.path.realpath; used for all OS
                  operations (stat, scandir) and the response ``path`` field.
    ``display`` – normalised (os.path.normpath) but *not* symlink-resolved;
                  used in error-message detail strings so that the path shown
                  to the caller matches what they sent, even on systems where
                  the temp-dir prefix crosses a symlink boundary (e.g. macOS
                  where /tmp → /private/tmp).
    """

    real: Path
    display: str


def _validate_browse_path(path: str | None) -> _BrowsePath:
    """Validate and normalise a browse path, returning a ``_BrowsePath``.

    Applies the following checks in order:
      1. Empty / missing → default to home directory.
      2. Length >= PATH_MAX → 400.
      3. Null byte present → 400.
      4. '..' component present (after URL-decode, which FastAPI already did) → 400.
      5. No leading '/' (relative path) → 400.
      6. os.path.normpath to collapse duplicates / trailing slashes.
      7. os.path.realpath to resolve any symlinks in the path itself.

    Existence / type / permission checks are left to the route handler so that
    the error responses (404, 400, 403) come from the right layer.
    """
    # 1. Empty / missing → home directory
    if path is None or not path.strip():
        try:
            home = Path.home()
        except RuntimeError as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Cannot determine user home directory: "
                    "no HOME environment variable is set"
                ),
            ) from exc
        real = Path(os.path.realpath(str(home)))
        return _BrowsePath(real=real, display=str(real))

    path = path.strip()

    # 2. Length guard (Linux PATH_MAX = 4096 bytes; measure in UTF-8 bytes, not
    #    Unicode code points, so multi-byte characters are counted correctly).
    #    Use >= so that exactly 4096 bytes is also rejected: PATH_MAX includes
    #    the NUL terminator, meaning valid paths are at most 4095 bytes long.
    #    A path of exactly 4096 bytes reaches the OS and triggers ENAMETOOLONG,
    #    which would otherwise surface as a 404 rather than a proper 400.
    if len(path.encode("utf-8")) >= _PATH_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Path too long: maximum length is {_PATH_MAX - 1} bytes",
        )

    # 3. Null byte guard
    if "\x00" in path:
        raise HTTPException(
            status_code=400,
            detail="Path contains invalid null byte",
        )

    # 4. Path traversal guard: check each component for literal '..'
    #    FastAPI URL-decodes query parameters before the handler runs, so
    #    %2e%2e%2f will already be decoded to '../' when we receive it here.
    if ".." in path.split("/"):
        raise HTTPException(
            status_code=400,
            detail="Path traversal via '..' components is not allowed",
        )

    # 5. Must be absolute (start with '/')
    if not path.startswith("/"):
        raise HTTPException(
            status_code=400,
            detail="Path must be absolute",
        )

    # 6. Normalise: collapse '//', remove trailing '/', etc.
    normalized = os.path.normpath(path)

    # 7. Resolve any symlinks in the path itself so the response always shows
    #    the real on-disk location.
    real = os.path.realpath(normalized)

    return _BrowsePath(real=Path(real), display=normalized)


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


@router.get("/browse", response_model=BrowseResponse)
def browse_filesystem(
    path: str | None = Query(default=None, description="Absolute path to browse"),
) -> BrowseResponse:
    """List subdirectories at the given path.

    Only real directories are returned; regular files and symbolic links are
    excluded.  Non-UTF-8 filenames are silently skipped so they never cause a
    500 JSON-serialization error.

    Query parameters:
        path: Absolute filesystem path to browse.
              Empty or missing → server user's home directory.
              Whitespace-only  → stripped to empty, treated as missing.
    """
    browse_path = _validate_browse_path(path)
    real_path = browse_path.real
    # display_path is the caller-supplied path after normpath (but before
    # realpath), used in error-detail strings so they match what the caller
    # sent even when the path crosses a symlink boundary (e.g. macOS /tmp →
    # /private/tmp).
    display_path = browse_path.display

    # --- Existence check -----------------------------------------------------------
    # Use os.stat() rather than Path.exists() because Path.exists() swallows
    # PermissionError (returns False) on Python 3.10+, which would incorrectly
    # produce a 404 instead of a 403 when the caller lacks permission to stat the
    # path (e.g. a non-traversable parent directory).
    try:
        path_stat = real_path.stat()
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied accessing: {display_path}",
        )
    except OSError:
        # Covers FileNotFoundError, NotADirectoryError, and other stat failures.
        raise HTTPException(
            status_code=404,
            detail=f"Path not found: {display_path}",
        )

    # --- Must be a directory -------------------------------------------------------
    # Reuse the stat result so there is no additional syscall and no risk of an
    # unguarded PermissionError from a separate Path.is_dir() call.
    if not stat.S_ISDIR(path_stat.st_mode):
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: {display_path}",
        )

    # --- Compute parent and response path -----------------------------------------
    # The response `path` field uses the realpath so that symlink targets are
    # resolved transparently (test: test_symlink_path_resolves_to_real).
    real_path_str = str(real_path)
    parent: str | None = None if real_path_str == "/" else str(real_path.parent)

    # Entry paths are built from real_path_str (the fully-resolved real path)
    # so they remain consistent with response.path.  This is essential when the
    # browse target is itself a symlink: using display_path (pre-realpath) would
    # produce entry paths rooted at the symlink path while response.path is the
    # resolved real path, violating the documented response contract.
    entry_base = real_path_str

    # --- Scan entries --------------------------------------------------------------
    entries: list[FilesystemEntry] = []
    try:
        with os.scandir(real_path) as it:
            for entry in it:
                # Only include real (non-symlink) directories.
                # DirEntry.is_dir(follow_symlinks=False) returns False for symlinks
                # even when they point to directories, so this single check excludes
                # both regular files and all symlinks.
                if not entry.is_dir(follow_symlinks=False):
                    continue

                # Guard against non-UTF-8 names that would break JSON serialization.
                # Python represents such names using surrogateescape, which cannot be
                # encoded to valid UTF-8.
                try:
                    name: str = entry.name
                    name.encode("utf-8")
                except UnicodeEncodeError:
                    log.debug("Skipping non-UTF-8 directory entry in %s", real_path)
                    continue

                # Build the absolute path without introducing double slashes at root.
                if entry_base == "/":
                    entry_path = f"/{name}"
                else:
                    entry_path = f"{entry_base}/{name}"

                entries.append(
                    FilesystemEntry(name=name, type="directory", path=entry_path)
                )

    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied reading directory: {display_path}",
        )
    except FileNotFoundError:
        # Race condition: directory was removed between the existence check above
        # and the scandir call.  Surface as 404, never 500.
        raise HTTPException(
            status_code=404,
            detail=f"Path not found (removed during listing): {display_path}",
        )
    except OSError as exc:
        # Catch remaining OS-level errors (e.g. EIO, ENAMETOOLONG from the
        # kernel) so they never bubble up as an unhandled 500.
        log.warning("OS error scanning directory %s: %s", real_path, exc)
        raise HTTPException(
            status_code=500,
            detail=f"I/O error reading directory: {display_path}",
        ) from exc

    return BrowseResponse(path=real_path_str, parent=parent, entries=entries)
