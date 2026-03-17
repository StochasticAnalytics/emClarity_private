"""Thread-safe and process-safe JSON persistence utilities.

Provides two core primitives:

* :func:`atomic_write` -- write JSON to disk atomically via temp-file + ``os.replace()``.
* :func:`locked_json_read_write` -- read-modify-write a JSON file under dual locking
  (``threading.Lock`` for in-process thread safety *and* ``fcntl.flock`` for
  cross-process safety).

Why dual locking
~~~~~~~~~~~~~~~~
``fcntl.flock()`` is process-level only -- concurrent threads within a single FastAPI
worker are **not** protected by fcntl alone.  The ``threading.Lock`` prevents in-process
races; ``fcntl.flock`` prevents cross-process races.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

# Module-level thread lock -- one per import (i.e. one per process).
_lock = threading.Lock()


def atomic_write(path: Path | str, data: Any, *, indent: int = 2) -> None:
    """Write *data* as JSON to *path* atomically.

    Writes to a temporary file in the same directory, then uses
    ``os.replace()`` which is atomic on POSIX filesystems.  This avoids
    partial/corrupt reads if the process is interrupted mid-write.

    Args:
        path: Destination file path.
        data: JSON-serialisable data.
        indent: JSON indentation level (default 2).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=indent))
        os.replace(tmp, path)
    except Exception:
        # Clean up the temp file on failure if it exists
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def locked_json_read_write(
    path: Path | str,
    transform_fn: Callable[[Any], T],
) -> T:
    """Thread-safe AND process-safe JSON read-modify-write.

    Acquires a ``threading.Lock`` (for in-process thread safety among
    FastAPI async workers) **and** an exclusive ``fcntl.flock`` (for
    cross-process safety when multiple backend instances share a file).

    The *transform_fn* receives the parsed JSON data and must return the
    new data to be written back.  The return value of *transform_fn* is
    also returned from this function.

    If the file does not exist, *transform_fn* receives ``None`` so the
    caller can initialise the file.

    Args:
        path: Path to the JSON file.
        transform_fn: ``data_in -> data_out`` callback.

    Returns:
        The value returned by *transform_fn* (i.e. the new file contents).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with _lock:
        # Open in "a+" so the file is created if it doesn't exist,
        # then seek back to read.  We hold the flock for the entire
        # read-modify-write cycle.
        with open(path, "a+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                content = f.read()
                if content.strip():
                    data = json.loads(content)
                else:
                    data = None

                result = transform_fn(data)
                atomic_write(path, result)
                return result
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
