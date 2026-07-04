"""Distributed dispatch: GNU ``parallel --sshlogin`` fan-out and a local joblib executor.

Two executors, mirroring the repo's ``scripts/cluster.py`` conventions (CLAUDE.md):

* :class:`SSHParallel` — fan a per-tomo (or per-partition) job across every GPU on every host
  (etna 3 + siracusa 3 + salina 2 = 8) via GNU ``parallel --sshlogin``, GPU-pinned with
  ``CUDA_VISIBLE_DEVICES=$(({%} % ngpu))``, prefixed with the ``ENV_SETUP`` PATH/IMOD prelude that
  SSH's bare login shells lack, with ``--joblog``/``--resume`` and ``--wd .`` on the shared
  ``/scratch`` + ``/sa_shared`` mounts. The command **composition** is pure and unit-testable
  (assert the argv/remote strings) — no ssh happens until :meth:`SSHParallel.run`.
* :class:`LocalProcess` — a single-host joblib map for one multi-GPU box (or CI). Falls back to a
  sequential map when joblib is unavailable, so importing this module never requires joblib.

Resumability is the caller's (per-tomo done sentinels + content-addressed cache, see
:mod:`mito_filter.exec.runner`); ``--joblog`` here is a record, not the resume mechanism (a stale
joblog would skip a buggy no-op exit — CLAUDE.md).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple, TypeVar

from .gpu import HostSpec

__all__ = [
    "ENV_SETUP",
    "SSH_OPTS",
    "PartitionSlot",
    "partition_map",
    "SSHParallel",
    "LocalProcess",
]

T = TypeVar("T")
R = TypeVar("R")

ENV_SETUP: str = (
    "export PATH=/sa_shared/software/current_emClarity/bin:"
    "/sa_shared/software/current_cistem_dir:/usr/local/cuda/bin:$PATH; "
    "source /sa_shared/software/IMOD/imod_4.12.49/IMOD-linux.sh"
)
"""PATH/IMOD prelude prepended to every remote command (SSH shells get a bare PATH; the shared
IMOD path resolves on every host, unlike the per-``/home`` ones). Mirrors the repo (CLAUDE.md)."""

SSH_OPTS: Tuple[str, ...] = ("-o", "BatchMode=yes", "-o", "ConnectTimeout=8")
"""Non-interactive ssh options."""


@dataclass(frozen=True)
class PartitionSlot:
    """One GPU slot in the fan-out: a host, its 1-based global partition index, and its GPU count.

    Args:
        host: The hostname.
        idx: 1-based global partition index (contiguous host blocks, e.g. etna 1-3, siracusa 4-6).
        ngpu: The host's GPU count (for the ``{%} % ngpu`` CUDA modulo).

    Attributes:
        host: The hostname.
        idx: The global partition index.
        ngpu: The host's GPU count.
    """

    host: str
    idx: int
    ngpu: int


def partition_map(hosts: Sequence[HostSpec]) -> Tuple[int, List[PartitionSlot]]:
    """Assign contiguous 1-based partition indices across every GPU of every host.

    Mirrors the repo ``partition_map``: host order is preserved and each host owns a contiguous
    block of indices (etna 1-3, siracusa 4-6, salina 7-8 for the standard layout).

    Args:
        hosts: The usable hosts, in priority order.

    Returns:
        ``(N, slots)`` where ``N`` is the total GPU/partition count and ``slots`` the per-GPU
        :class:`PartitionSlot` list.
    """
    slots: List[PartitionSlot] = []
    idx = 0
    for h in hosts:
        for _ in range(h.ngpu):
            idx += 1
            slots.append(PartitionSlot(host=h.host, idx=idx, ngpu=h.ngpu))
    return idx, slots


@dataclass
class SSHParallel:
    """Compose and (optionally) run a GNU ``parallel --sshlogin`` fan-out over hosts.

    Args:
        ssh_user: SSH user for every remote (default ``"himesb"``).
        env_setup: The PATH/IMOD prelude prepended to each remote command (default
            :data:`ENV_SETUP`).
        ssh_opts: Non-interactive ssh options (default :data:`SSH_OPTS`).
        retries: ``parallel --retries`` value (default 1).
        workdir: The shared working directory passed as ``--wd`` (default ``"."``).
        joblog_dir: Directory for per-host ``--joblog`` files (default ``.mito/joblogs``).
        sshdelay: ``parallel --sshdelay`` in seconds (default 0.1).

    Attributes:
        ssh_user: The SSH user.
        env_setup: The env prelude.
        ssh_opts: The ssh options.
        retries: The retry count.
        workdir: The shared working directory.
        joblog_dir: The joblog directory.
        sshdelay: The ssh delay.
    """

    ssh_user: str = "himesb"
    env_setup: str = ENV_SETUP
    ssh_opts: Tuple[str, ...] = SSH_OPTS
    retries: int = 1
    workdir: str = "."
    joblog_dir: str = ".mito/joblogs"
    sshdelay: float = 0.1

    def remote_command(self, cmd: str, ngpu: int) -> str:
        """Wrap a job command with the env prelude and per-slot CUDA pin.

        The GNU-parallel slot token ``{%}`` is evaluated remotely: the visible GPU is
        ``{%} % ngpu`` (so pinned indices stay valid when jobs < ngpu). Any inherited
        ``CUDA_VISIBLE_DEVICES`` is unset first.

        Args:
            cmd: The job command (may contain a literal ``{}`` for the partition index).
            ngpu: The host's GPU count (the CUDA modulo base).

        Returns:
            The fully-composed remote shell string.
        """
        return (
            f"{self.env_setup}; unset CUDA_VISIBLE_DEVICES && "
            f"export CUDA_VISIBLE_DEVICES=$(({{%}} % {ngpu})) && {cmd}"
        )

    def parallel_argv(
        self,
        host: str,
        remote: str,
        njobs: int,
        joblog: str,
    ) -> List[str]:
        """Build the local ``parallel`` argv that drives one host's slice of the fan-out.

        Args:
            host: The target host.
            remote: The remote command (from :meth:`remote_command`).
            njobs: ``-j`` concurrency for this host (typically its GPU count).
            joblog: Path to this host's ``--joblog`` file.

        Returns:
            The ``parallel`` command as an argv list (ready for :mod:`subprocess`).
        """
        return [
            "parallel",
            "-j",
            str(njobs),
            "--lb",
            "--wd",
            self.workdir,
            "--sshdelay",
            str(self.sshdelay),
            "--sshlogin",
            f"{self.ssh_user}@{host}",
            "--joblog",
            joblog,
            "--retries",
            str(self.retries),
            remote,
        ]

    def joblog_path(self, prefix: str, host: str) -> str:
        """Return the per-host joblog path ``<joblog_dir>/<prefix>_<host>.joblog``."""
        return os.path.join(self.joblog_dir, f"{prefix}_{host}.joblog")

    def plan(
        self,
        cmd_template: str,
        hosts: Sequence[HostSpec],
        *,
        joblog_prefix: str = "mito",
        ram_per_job_gb: Optional[float] = None,
    ) -> List[Tuple[str, List[str], str]]:
        """Compose (without running) the per-host dispatch: argv + the index feed for each host.

        Each host is fed its contiguous block of 1-based partition indices on stdin; GNU parallel
        substitutes them into the ``{}`` in ``cmd_template``.

        Args:
            cmd_template: The job command with a literal ``{}`` partition-index placeholder, e.g.
                ``"mito-filter scan-one --index {} --total 8"``.
            hosts: The usable hosts.
            joblog_prefix: Prefix for the per-host joblog filenames.
            ram_per_job_gb: Optional RAM cap; None runs one job per GPU (see
                :func:`mito_filter.exec.gpu.ram_capped_jobs`).

        Returns:
            One ``(host, parallel_argv, stdin_feed)`` triple per host.
        """
        from .gpu import ram_capped_jobs

        _, slots = partition_map(hosts)
        by_host: dict[str, Tuple[int, List[int], int]] = {}
        for s in slots:
            entry = by_host.setdefault(s.host, (s.ngpu, [], 0))
            entry[1].append(s.idx)
        plans: List[Tuple[str, List[str], str]] = []
        ram_by_host = {h.host: h.ram_gb for h in hosts}
        for host, (ngpu, idxs, _z) in by_host.items():
            njobs = ram_capped_jobs(ngpu, ram_by_host.get(host, 0), ram_per_job_gb)
            remote = self.remote_command(cmd_template, ngpu)
            argv = self.parallel_argv(host, remote, njobs, self.joblog_path(joblog_prefix, host))
            feed = "\n".join(str(i) for i in idxs) + "\n"
            plans.append((host, argv, feed))
        return plans

    def run(
        self,
        cmd_template: str,
        hosts: Sequence[HostSpec],
        *,
        joblog_prefix: str = "mito",
        ram_per_job_gb: Optional[float] = None,
        dry_run: bool = False,
    ) -> bool:
        """Dispatch ``cmd_template`` across all hosts and wait for completion.

        Starts every host's ``parallel`` master concurrently (feed stdin first, then wait) so no
        host idles waiting for another — the imbalance bug from serial feed/wait (CLAUDE.md).

        Args:
            cmd_template: The job command with a ``{}`` partition-index placeholder.
            hosts: The usable hosts.
            joblog_prefix: Prefix for per-host joblog files.
            ram_per_job_gb: Optional RAM cap (None = one job per GPU).
            dry_run: If True, compose and print only — run nothing.

        Returns:
            True if every host's ``parallel`` exited 0 (always True for a dry run).
        """
        plans = self.plan(
            cmd_template, hosts, joblog_prefix=joblog_prefix, ram_per_job_gb=ram_per_job_gb
        )
        if dry_run:
            for host, argv, _feed in plans:
                print(f"  [dry {host}] {' '.join(argv)}")
            return True
        os.makedirs(self.joblog_dir, exist_ok=True)
        procs: List[Tuple[str, "subprocess.Popen[str]", str]] = []
        for host, argv, feed in plans:
            procs.append((host, subprocess.Popen(argv, stdin=subprocess.PIPE, text=True), feed))
        for _host, proc, feed in procs:
            assert proc.stdin is not None
            proc.stdin.write(feed)
            proc.stdin.close()
        ok = True
        for host, proc, _feed in procs:
            if proc.wait() != 0:
                ok = False
        return ok


@dataclass
class LocalProcess:
    """A single-host executor mapping a callable over items (joblib, sequential fallback).

    Use for one multi-GPU box or for CI. When joblib is unavailable the map runs sequentially, so
    importing this module never requires joblib (the CPU path always works).

    Args:
        n_jobs: Worker count (``1`` = sequential; ``-1`` = all cores under joblib).
        prefer: joblib backend hint (``"processes"`` or ``"threads"``); ignored without joblib.

    Attributes:
        n_jobs: The worker count.
        prefer: The joblib backend preference.
    """

    n_jobs: int = 1
    prefer: str = "processes"
    _joblib_ok: bool = field(default=False, init=False, repr=False)

    def map(self, fn: Callable[[T], R], items: Sequence[T]) -> List[R]:
        """Apply ``fn`` to each item, returning results in input order.

        Args:
            fn: The per-item callable.
            items: The input items.

        Returns:
            ``[fn(item) for item in items]``, computed in parallel when joblib is available and
            ``n_jobs != 1``.
        """
        items = list(items)
        if self.n_jobs == 1:
            return [fn(x) for x in items]
        try:
            from joblib import Parallel, delayed
        except ImportError:
            return [fn(x) for x in items]
        results = Parallel(n_jobs=self.n_jobs, prefer=self.prefer)(delayed(fn)(x) for x in items)
        return list(results)
