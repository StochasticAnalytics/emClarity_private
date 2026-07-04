"""Unit tests for exec/cluster.py and exec/gpu.py (command composition, no ssh)."""

from __future__ import annotations

from mito_filter.exec.cluster import (
    ENV_SETUP,
    LocalProcess,
    SSHParallel,
    partition_map,
)
from mito_filter.exec.gpu import (
    HostSpec,
    cuda_visible_env,
    ram_capped_jobs,
    worker_cap,
)

HOSTS = [HostSpec("etna", 3, 503), HostSpec("siracusa", 3, 125), HostSpec("salina", 2, 125)]


def _square(x: int) -> int:
    return x * x


def _njobs(argv: list[str]) -> int:
    return int(argv[argv.index("-j") + 1])


# --------------------------------------------------------------------------- partition_map


def test_partition_map_contiguous_blocks() -> None:
    n, slots = partition_map(HOSTS)
    assert n == 8
    assert [s.idx for s in slots] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert [s.idx for s in slots if s.host == "etna"] == [1, 2, 3]
    assert [s.idx for s in slots if s.host == "siracusa"] == [4, 5, 6]
    assert [s.idx for s in slots if s.host == "salina"] == [7, 8]
    # each slot carries its host GPU count for the CUDA modulo
    assert {s.host: s.ngpu for s in slots} == {"etna": 3, "siracusa": 3, "salina": 2}


# --------------------------------------------------------------------------- SSHParallel strings


def test_remote_command_env_and_cuda_pin() -> None:
    sp = SSHParallel()
    remote = sp.remote_command("emClarity scan-one {}", ngpu=3)
    assert remote.startswith(ENV_SETUP)
    assert "unset CUDA_VISIBLE_DEVICES" in remote
    assert "export CUDA_VISIBLE_DEVICES=$(({%} % 3))" in remote
    assert remote.rstrip().endswith("emClarity scan-one {}")


def test_parallel_argv_shape() -> None:
    sp = SSHParallel(ssh_user="himesb", retries=2)
    remote = sp.remote_command("cmd {}", ngpu=3)
    argv = sp.parallel_argv("etna", remote, njobs=3, joblog=".mito/joblogs/mito_etna.joblog")
    assert argv[0] == "parallel"
    assert _njobs(argv) == 3
    assert "--sshlogin" in argv and "himesb@etna" in argv
    assert argv[argv.index("--wd") + 1] == "."
    assert argv[argv.index("--joblog") + 1] == ".mito/joblogs/mito_etna.joblog"
    assert argv[argv.index("--retries") + 1] == "2"
    assert argv[-1] == remote  # the remote command is the final positional


def test_plan_feeds_contiguous_indices() -> None:
    sp = SSHParallel()
    plans = sp.plan("mito-filter scan-one --index {} --total 8", HOSTS, joblog_prefix="scan")
    by_host = {host: (argv, feed) for host, argv, feed in plans}
    assert set(by_host) == {"etna", "siracusa", "salina"}
    assert by_host["etna"][1] == "1\n2\n3\n"
    assert by_host["siracusa"][1] == "4\n5\n6\n"
    assert by_host["salina"][1] == "7\n8\n"
    # default: one job per GPU on every host (no RAM cap)
    assert _njobs(by_host["etna"][0]) == 3
    assert _njobs(by_host["salina"][0]) == 2
    # per-host joblog path
    assert ".mito/joblogs/scan_etna.joblog" in by_host["etna"][0]


def test_plan_ram_cap_throttles_small_hosts() -> None:
    sp = SSHParallel()
    plans = sp.plan("cmd {}", HOSTS, ram_per_job_gb=50)
    njobs = {host: _njobs(argv) for host, argv, _feed in plans}
    assert njobs["etna"] == 3  # 503//50 clamped to 3 GPUs
    assert njobs["siracusa"] == 2  # 125//50 = 2
    assert njobs["salina"] == 2  # min(2 GPUs, 125//50)


def test_run_dry_run_executes_nothing() -> None:
    sp = SSHParallel()
    assert sp.run("cmd {}", HOSTS, dry_run=True) is True


# --------------------------------------------------------------------------- LocalProcess


def test_local_process_sequential() -> None:
    lp = LocalProcess(n_jobs=1)
    assert lp.map(_square, [1, 2, 3, 4]) == [1, 4, 9, 16]


def test_local_process_parallel_threads_order_preserved() -> None:
    lp = LocalProcess(n_jobs=2, prefer="threads")
    assert lp.map(_square, list(range(6))) == [0, 1, 4, 9, 16, 25]


# --------------------------------------------------------------------------- gpu helpers


def test_worker_caps() -> None:
    assert worker_cap("etna") == 8
    assert worker_cap("siracusa") == 6
    assert worker_cap("salina") == 6
    assert worker_cap("unknown") == 6
    assert worker_cap("x", caps={"x": 12}) == 12


def test_ram_capped_jobs() -> None:
    assert ram_capped_jobs(3, 503, None) == 3  # no cap -> one per GPU
    assert ram_capped_jobs(3, 125, 50) == 2  # 125//50
    assert ram_capped_jobs(2, 125, 50) == 2  # min(2 GPU, 2)
    assert ram_capped_jobs(3, 40, 50) == 1  # clamps up to at least 1
    assert ram_capped_jobs(0, 500, None) == 0  # no GPU -> no jobs


def test_cuda_visible_env() -> None:
    env = cuda_visible_env(2, {"PATH": "/x"})
    assert env["CUDA_VISIBLE_DEVICES"] == "2"
    assert env["PATH"] == "/x"  # base env preserved
