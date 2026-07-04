"""Internal tomogram-reference accessors for field providers.

Field providers are handed a ``TomogramRef`` (owned by ``datasets/base.py``, built by
``datasets/emclarity_tm.py``). That module is not a dependency of ``fields/`` — providers only
need to *locate files* for one tomogram, so this helper defines the small structural surface a
``TomogramRef`` must expose and resolves per-tomo sibling paths from it.

**Attribute contract a ``TomogramRef`` must satisfy for ``fields/`` to consume it:**

* ``base: str`` — the convmap basename, e.g. ``"H99_2_100_1_bin5"``.
* ``convmap_path`` — path to ``<base>_convmap.mrc`` (its parent is the convmap dir; every
  ``<base><suffix>`` sibling is resolved relative to it).

Optional (used when present, else providers fall back to their configured defaults):

* ``rec_dir`` — dir holding ``<base>.rec`` (default ``/scratch/salina/alt_cache``).
* ``fixedstacks_dir`` — dir holding ``*.erase`` gold bead models.

:class:`TomoRef` is a concrete, ready-to-use implementation of that contract (used by tests and
by any caller that has not yet built the full ``datasets`` layer). Access is via the module
helpers, which duck-type any object exposing the attributes above.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_REC_DIR: Path = Path("/scratch/salina/alt_cache")
"""Default directory holding the searched ``<base>.rec`` volumes (SPEC §3)."""


@dataclass(frozen=True)
class TomoRef:
    """A concrete, filesystem-backed tomogram reference (the ``fields/`` consumption contract).

    Args:
        base: Convmap basename, e.g. ``"H99_2_100_1_bin5"``.
        convmap_path: Path to ``<base>_convmap.mrc``.
        rec_dir: Directory holding ``<base>.rec`` (defaults to :data:`DEFAULT_REC_DIR`).
        fixedstacks_dir: Directory holding ``*.erase`` gold bead models, if any.

    Attributes:
        base: The basename.
        convmap_path: The convmap path.
        rec_dir: The rec directory.
        fixedstacks_dir: The fixedStacks directory (or None).
    """

    base: str
    convmap_path: Path
    rec_dir: Optional[Path] = None
    fixedstacks_dir: Optional[Path] = None


def base_of(tomo: object) -> str:
    """Return the convmap basename of ``tomo``.

    Args:
        tomo: A tomogram reference exposing ``base``.

    Returns:
        The basename string.

    Raises:
        AttributeError: If ``tomo`` has no ``base``.
    """
    return str(getattr(tomo, "base"))


def convmap_path_of(tomo: object) -> Path:
    """Return the ``<base>_convmap.mrc`` path of ``tomo``.

    Args:
        tomo: A tomogram reference exposing ``convmap_path``.

    Returns:
        The convmap path.

    Raises:
        AttributeError: If ``tomo`` has no ``convmap_path``.
    """
    return Path(getattr(tomo, "convmap_path"))


def dir_of(tomo: object) -> Path:
    """Return the convmap directory (parent of ``convmap_path``)."""
    return convmap_path_of(tomo).parent


def sibling(tomo: object, suffix: str) -> Path:
    """Return the ``<dir>/<base><suffix>`` sibling path for ``tomo``.

    Args:
        tomo: The tomogram reference.
        suffix: The suffix to append to the basename (e.g. ``".csv"``, ``"_angles.list"``,
            ``"_noise_variance.mrc"``).

    Returns:
        The resolved sibling path.
    """
    return dir_of(tomo) / f"{base_of(tomo)}{suffix}"


def rec_path_of(tomo: object, rec_dir: Optional[Path] = None) -> Path:
    """Return the ``<base>.rec`` path for ``tomo``.

    Resolution order for the directory: the explicit ``rec_dir`` argument, then the tomo's own
    ``rec_dir`` attribute, then :data:`DEFAULT_REC_DIR`.

    Args:
        tomo: The tomogram reference.
        rec_dir: Explicit override for the rec directory.

    Returns:
        The resolved ``<base>.rec`` path.
    """
    d = rec_dir if rec_dir is not None else getattr(tomo, "rec_dir", None)
    d = Path(d) if d is not None else DEFAULT_REC_DIR
    return d / f"{base_of(tomo)}.rec"
