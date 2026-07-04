"""RunManifest: a per-run provenance record (DESIGN §13).

Every scan/optimize run writes a ``run_manifest.json`` capturing exactly what produced the
verdicts so any result is reproducible/traceable:

* the resolved :class:`~mito_filter.config.PipelineConfig`,
* the git revision of **both** ``mito_filter`` and the parent ``emClarity`` tree,
* input-file hashes / sizes / mtimes,
* the backend/device,
* the tuned ``theta`` + ``tau``,
* the field-cache keys in effect.

Hashing is content-addressed (sha256) but skippable for very large inputs (a 559 MB convmap),
in which case ``(size, mtime_ns)`` is the identity — the same key the field cache uses.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

import yaml

__all__ = [
    "FileRecord",
    "RunManifest",
    "git_rev",
    "file_record",
]

# The mito_filter package root (the editable-install checkout):
#   .../emClarity_private/mito_filter/src/mito_filter/manifest.py -> parents[2].
MITO_FILTER_ROOT: Path = Path(__file__).resolve().parents[2]
# The parent emClarity working tree (mito_filter lives inside it) -> parents[3].
EMCLARITY_ROOT: Path = Path(__file__).resolve().parents[3]

# Files at/above this size skip sha256 and key on (size, mtime) instead (a convmap is 559 MB).
_HASH_SIZE_LIMIT: int = 256 * 1024 * 1024


def git_rev(repo_path: Union[str, Path]) -> str:
    """Return the short git revision of the working tree containing ``repo_path``.

    Args:
        repo_path: A path inside a git working tree.

    Returns:
        The short commit hash, suffixed ``"-dirty"`` when the tree has uncommitted changes, or
        ``"unknown"`` if git is unavailable / the path is not a repository.
    """
    p = Path(repo_path)
    cwd = p if p.is_dir() else p.parent
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        dirty = ""
    return f"{rev}-dirty" if dirty else rev


@dataclass(frozen=True)
class FileRecord:
    """Identity of one input file (for provenance + staleness).

    Args:
        path: Absolute path to the file.
        exists: Whether the file was present when the manifest was built.
        size: Size in bytes (``-1`` if absent).
        mtime_ns: Modification time in ns (``-1`` if absent).
        sha256: Content hash, or ``None`` when skipped (too large) or absent.

    Attributes:
        path: The file path.
        exists: Presence flag.
        size: The byte size.
        mtime_ns: The mtime in ns.
        sha256: The content hash (or None).
    """

    path: str
    exists: bool
    size: int
    mtime_ns: int
    sha256: Optional[str] = None


def file_record(path: Union[str, Path], *, hash_contents: bool = True) -> FileRecord:
    """Build a :class:`FileRecord` for one input file.

    Args:
        path: The file path.
        hash_contents: If True, sha256 the contents (skipped automatically above
            :data:`_HASH_SIZE_LIMIT`, where ``(size, mtime)`` is the identity).

    Returns:
        The :class:`FileRecord` (``exists=False`` with ``-1`` fields for a missing file).
    """
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return FileRecord(str(p), exists=False, size=-1, mtime_ns=-1, sha256=None)
    digest: Optional[str] = None
    if hash_contents and st.st_size <= _HASH_SIZE_LIMIT:
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        digest = h.hexdigest()
    return FileRecord(
        str(p.resolve()),
        exists=True,
        size=int(st.st_size),
        mtime_ns=int(st.st_mtime_ns),
        sha256=digest,
    )


@dataclass
class RunManifest:
    """A reproducibility record for one scan/optimize run (DESIGN §13).

    Args:
        created: ISO-8601 UTC timestamp of manifest creation.
        dataset: The dataset id.
        backend: The backend/device string (e.g. ``"cpu"``).
        mito_filter_git: git revision of the ``mito_filter`` tree.
        emclarity_git: git revision of the parent ``emClarity`` tree.
        config: The resolved pipeline config (dict form).
        inputs: The input :class:`FileRecord` list.
        field_cache_keys: Field name -> content-address key in effect.
        theta: The tuned parameter values.
        tau: The keep-probability decision threshold.
        meta: Free-form extra provenance (objective, metrics, host, ...).

    Attributes:
        created: The creation timestamp.
        dataset: The dataset id.
        backend: The backend string.
        mito_filter_git: The mito_filter git rev.
        emclarity_git: The emClarity git rev.
        config: The resolved config dict.
        inputs: The input file records.
        field_cache_keys: The field cache keys.
        theta: The tuned parameters.
        tau: The decision threshold.
        meta: Extra provenance.
    """

    created: str = ""
    dataset: str = ""
    backend: str = "cpu"
    mito_filter_git: str = "unknown"
    emclarity_git: str = "unknown"
    config: Dict[str, Any] = field(default_factory=dict)
    inputs: List[FileRecord] = field(default_factory=list)
    field_cache_keys: Dict[str, str] = field(default_factory=dict)
    theta: Dict[str, float] = field(default_factory=dict)
    tau: float = 0.5
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        config: Mapping[str, Any],
        dataset: str = "",
        backend: str = "cpu",
        input_paths: Sequence[Union[str, Path]] = (),
        theta: Optional[Mapping[str, float]] = None,
        tau: float = 0.5,
        field_cache_keys: Optional[Mapping[str, str]] = None,
        meta: Optional[Mapping[str, Any]] = None,
        hash_inputs: bool = True,
    ) -> "RunManifest":
        """Assemble a :class:`RunManifest`, resolving git revs and hashing inputs.

        Args:
            config: The resolved pipeline config (dict form; e.g.
                :meth:`~mito_filter.config.PipelineConfig.to_dict`).
            dataset: The dataset id.
            backend: The backend/device string.
            input_paths: Input files to record (convmap, csv, templateIDX, fitted config, ...).
            theta: The tuned parameter values.
            tau: The keep-probability decision threshold.
            field_cache_keys: Field name -> cache key in effect.
            meta: Extra provenance.
            hash_inputs: If True, sha256 each input (auto-skipped above the size limit).

        Returns:
            The assembled :class:`RunManifest`.
        """
        return cls(
            created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            dataset=dataset,
            backend=backend,
            mito_filter_git=git_rev(MITO_FILTER_ROOT),
            emclarity_git=git_rev(EMCLARITY_ROOT),
            config=dict(config),
            inputs=[file_record(p, hash_contents=hash_inputs) for p in input_paths],
            field_cache_keys=dict(field_cache_keys or {}),
            theta={str(k): float(v) for k, v in dict(theta or {}).items()},
            tau=float(tau),
            meta=dict(meta or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation (json/yaml ready)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunManifest":
        """Rebuild a :class:`RunManifest` from a mapping (unknown keys ignored).

        Args:
            data: A mapping produced by :meth:`to_dict`.

        Returns:
            The reconstructed :class:`RunManifest`.
        """
        d = dict(data)
        inputs = [
            rec if isinstance(rec, FileRecord) else FileRecord(**rec) for rec in d.get("inputs", [])
        ]
        known = set(cls.__dataclass_fields__)
        kept = {k: v for k, v in d.items() if k in known and k != "inputs"}
        return cls(inputs=inputs, **kept)

    def save(self, path: Union[str, Path]) -> Path:
        """Write the manifest as JSON.

        Args:
            path: Destination ``.json`` path (parent dirs created).

        Returns:
            The written path.
        """
        import json

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n")
        return p

    @classmethod
    def load(cls, path: Union[str, Path]) -> "RunManifest":
        """Read a manifest from a JSON (or YAML) file.

        Args:
            path: Source path.

        Returns:
            The parsed :class:`RunManifest`.
        """
        with Path(path).open("r") as fh:
            data = yaml.safe_load(fh) or {}
        return cls.from_dict(data)
