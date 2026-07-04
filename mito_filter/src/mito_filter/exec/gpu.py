"""GPU device pinning, per-host worker caps, and a live ``free -g`` RAM guard.

The cluster (CLAUDE.md) is **etna 3 + siracusa 3 + salina 2 = 8 GPUs**; etna has 503 GB RAM, the
two 125 GB hosts (siracusa/salina) are memory-bound. Worker counts are config-driven per host
(etna higher, the 125 GB hosts lower) with a live RAM check rather than a fixed blanket
reservation (CLAUDE.md: "no idle GPU on an unverified RAM guess"). This module owns the small,
pure helpers those policies need; :mod:`mito_filter.exec.cluster` composes them into dispatch.

Nothing here imports torch or cupy — pinning is done through ``CUDA_VISIBLE_DEVICES`` in the child
process environment, and the RAM probe shells out to ``free``/``ssh``.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

__all__ = [
    "HostSpec",
    "DEFAULT_GPU_LAYOUT",
    "DEFAULT_WORKER_CAPS",
    "cuda_visible_env",
    "worker_cap",
    "ram_capped_jobs",
    "free_ram_gb",
    "assert_ram_headroom",
]

DEFAULT_GPU_LAYOUT: Dict[str, int] = {"etna": 3, "siracusa": 3, "salina": 2}
"""Live cluster GPU layout (CLAUDE.md; etna's 4th GPU is dead). Detect live in production."""

DEFAULT_WORKER_CAPS: Dict[str, int] = {"etna": 8, "siracusa": 6, "salina": 6}
"""Per-host parpool/worker cap: etna is a 32-thread box (8), the 125 GB hosts use 6 (8
oversubscribes their CPUs and bloats RAM). Config-driven; overridable per call."""

DEFAULT_WORKER_CAP: int = 6
"""Fallback worker cap for a host not present in :data:`DEFAULT_WORKER_CAPS`."""


@dataclass(frozen=True)
class HostSpec:
    """A usable compute host: name, GPU count, total RAM.

    Args:
        host: Hostname (e.g. ``"etna"``).
        ngpu: Number of usable GPUs on the host.
        ram_gb: Total RAM in GB (0 if unknown).

    Attributes:
        host: The hostname.
        ngpu: GPU count.
        ram_gb: Total RAM in GB.
    """

    host: str
    ngpu: int
    ram_gb: int = 0

    @property
    def worker_cap(self) -> int:
        """The default per-host worker cap for this host (see :func:`worker_cap`)."""
        return worker_cap(self.host)


def cuda_visible_env(gpu_id: int, base_env: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Return a child-process environment pinning ``CUDA_VISIBLE_DEVICES`` to ``gpu_id``.

    Args:
        gpu_id: The physical GPU index to expose (as device 0 to the child).
        base_env: The environment to copy (defaults to an empty mapping; callers usually pass
            ``os.environ``).

    Returns:
        A new dict with ``CUDA_VISIBLE_DEVICES`` set to ``str(gpu_id)``.
    """
    env: Dict[str, str] = dict(base_env or {})
    env["CUDA_VISIBLE_DEVICES"] = str(int(gpu_id))
    return env


def worker_cap(
    host: str, caps: Optional[Mapping[str, int]] = None, default: int = DEFAULT_WORKER_CAP
) -> int:
    """Return the per-host worker (parpool) cap.

    Args:
        host: The hostname.
        caps: Optional override map (defaults to :data:`DEFAULT_WORKER_CAPS`).
        default: Value for a host absent from ``caps``.

    Returns:
        The worker cap for ``host``.
    """
    table = caps if caps is not None else DEFAULT_WORKER_CAPS
    return int(table.get(host, default))


def ram_capped_jobs(ngpu: int, ram_gb: int, ram_per_job_gb: Optional[float]) -> int:
    """Return the number of concurrent per-GPU jobs a host should run.

    Mirrors the repo dispatch policy (``cluster.py``): with ``ram_per_job_gb=None`` every GPU
    works (``-j=ngpu``); with a RAM cap, ``-j = clamp(1, ngpu, floor(ram_gb / ram_per_job_gb))``.
    A fixed cap is a fallback lever only — the default is ``None`` (CLAUDE.md).

    Args:
        ngpu: The host's GPU count.
        ram_gb: The host's total RAM in GB.
        ram_per_job_gb: RAM budget per job in GB, or None to run one job per GPU.

    Returns:
        The concurrent job count (at least 1 when ``ngpu >= 1``).
    """
    ngpu = max(0, int(ngpu))
    if ngpu < 1:
        return 0
    if not ram_per_job_gb:
        return ngpu
    by_ram = int(ram_gb // ram_per_job_gb)
    return max(1, min(ngpu, by_ram))


def free_ram_gb(
    host: Optional[str] = None,
    *,
    ssh_user: str = "himesb",
    timeout: float = 15.0,
) -> Optional[int]:
    """Probe available (free) RAM in GB, locally or over ssh.

    Runs ``free -g`` and returns the ``available`` column of the ``Mem:`` row. Returns ``None`` on
    any failure (host unreachable, command missing) so a guard can degrade gracefully rather than
    crash a run.

    Args:
        host: Remote host to probe, or None for the local machine.
        ssh_user: SSH user for a remote probe.
        timeout: Subprocess timeout in seconds.

    Returns:
        Available RAM in GB, or None if it could not be determined.
    """
    free_cmd = "free -g | awk '/Mem:/{print $7}'"
    argv: List[str] = (
        ["bash", "-lc", free_cmd]
        if host is None
        else [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            f"{ssh_user}@{host}",
            free_cmd,
        ]
    )
    try:
        out = subprocess.run(argv, text=True, capture_output=True, timeout=timeout).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None
    return int(out) if out.isdigit() else None


def assert_ram_headroom(
    required_gb: float,
    host: Optional[str] = None,
    *,
    ssh_user: str = "himesb",
) -> None:
    """Raise if a host's free RAM is below ``required_gb`` (a pre-dispatch OOM guard).

    An unknown free-RAM reading (probe failure) is treated as *not blocking* — the guard never
    fabricates a stop from a failed probe.

    Args:
        required_gb: The minimum free RAM the next job needs, in GB.
        host: Host to check (None = local).
        ssh_user: SSH user for a remote probe.

    Raises:
        MemoryError: If the measured free RAM is below ``required_gb``.
    """
    avail = free_ram_gb(host, ssh_user=ssh_user)
    if avail is not None and avail < required_gb:
        where = host or "local"
        raise MemoryError(
            f"insufficient free RAM on {where}: {avail} GB available < {required_gb} GB required"
        )
