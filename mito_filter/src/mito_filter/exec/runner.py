"""TomogramRunner: map a per-tomo job over a search, resumable via sentinels + a cache probe.

The per-tomo unit of work (feature extraction, scan, field generation) is embarrassingly parallel
across tomograms (DESIGN §11). :class:`TomogramRunner` drives one such job over a list of
:class:`~mito_filter.datasets.base.TomogramRef` and makes it **resumable** two ways:

1. a per-tomo **done sentinel** file (``<work_dir>/<sentinel_subdir>/<base>.done``) written after a
   tomo succeeds — a re-run skips any tomo whose sentinel exists;
2. an optional **cache probe** ``cache_exists(tomo) -> bool`` (the content-addressed field/feature
   cache) — a tomo whose output already exists is skipped even without a sentinel.

Either signal skips a tomo (``force=True`` overrides both). The mapping is delegated to an executor
exposing ``map(fn, items)`` (default :class:`~mito_filter.exec.cluster.LocalProcess` sequential), so
the same driver runs locally, over joblib, or — with a suitable executor — across the cluster.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Generic, List, Optional, Protocol, Sequence, TypeVar

from ..datasets.base import TomogramRef

__all__ = ["Executor", "TomoResult", "RunReport", "TomogramRunner"]

R = TypeVar("R")
_T = TypeVar("_T")
_U = TypeVar("_U")


class Executor(Protocol):
    """Minimal executor protocol: apply a callable over items, preserving order."""

    def map(self, fn: Callable[[_T], _U], items: Sequence[_T]) -> List[_U]:
        """Return ``[fn(x) for x in items]`` (possibly in parallel)."""
        ...


@dataclass
class TomoResult(Generic[R]):
    """The outcome of one tomogram in a run.

    Args:
        base: The tomogram basename.
        status: One of ``"done"`` (ran now), ``"skipped"`` (sentinel/cache hit), ``"failed"``.
        value: The job's return value (None when skipped or failed).
        error: The stringified exception when ``status == "failed"``, else None.

    Attributes:
        base: The basename.
        status: The status string.
        value: The job result.
        error: The error string.
    """

    base: str
    status: str
    value: Optional[R] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        """True if the tomo ran successfully or was skipped (i.e. not failed)."""
        return self.status in ("done", "skipped")


@dataclass
class RunReport(Generic[R]):
    """Aggregate result of a :meth:`TomogramRunner.run` over a search.

    Args:
        results: Per-tomo :class:`TomoResult` in input order.

    Attributes:
        results: The per-tomo results.
    """

    results: List[TomoResult[R]] = field(default_factory=list)

    @property
    def n_done(self) -> int:
        """Count of tomograms that ran successfully this invocation."""
        return sum(1 for r in self.results if r.status == "done")

    @property
    def n_skipped(self) -> int:
        """Count of tomograms skipped (sentinel or cache hit)."""
        return sum(1 for r in self.results if r.status == "skipped")

    @property
    def n_failed(self) -> int:
        """Count of tomograms that raised."""
        return sum(1 for r in self.results if r.status == "failed")

    @property
    def failures(self) -> List[TomoResult[R]]:
        """The failed results (for reporting / retry)."""
        return [r for r in self.results if r.status == "failed"]

    @property
    def ok(self) -> bool:
        """True if no tomogram failed."""
        return self.n_failed == 0


class TomogramRunner:
    """Drive a resumable per-tomo job over a search (sentinels + optional cache probe).

    Args:
        work_dir: Directory the run writes into; sentinels live under
            ``<work_dir>/<sentinel_subdir>``.
        executor: An object exposing ``map(fn, items)`` (default a sequential
            :class:`~mito_filter.exec.cluster.LocalProcess`).
        sentinel_subdir: Subdirectory (relative to ``work_dir``) holding ``<base>.done`` sentinels.

    Attributes:
        work_dir: The run directory.
        sentinel_dir: The resolved sentinel directory.
        executor: The mapping executor.
    """

    def __init__(
        self,
        work_dir: Path,
        *,
        executor: Optional[Executor] = None,
        sentinel_subdir: str = ".mito_done",
    ) -> None:
        self.work_dir = Path(work_dir)
        self.sentinel_dir = self.work_dir / sentinel_subdir
        if executor is None:
            from .cluster import LocalProcess

            executor = LocalProcess(n_jobs=1)
        self.executor: Executor = executor

    def sentinel_path(self, tomo: TomogramRef) -> Path:
        """Return the done-sentinel path for ``tomo`` (``<sentinel_dir>/<base>.done``)."""
        return self.sentinel_dir / f"{tomo.base}.done"

    def is_done(self, tomo: TomogramRef) -> bool:
        """Return True if ``tomo``'s done sentinel exists."""
        return self.sentinel_path(tomo).exists()

    def mark_done(self, tomo: TomogramRef) -> None:
        """Write ``tomo``'s done sentinel (creating the sentinel directory)."""
        self.sentinel_dir.mkdir(parents=True, exist_ok=True)
        self.sentinel_path(tomo).touch()

    def clear_done(self, tomo: TomogramRef) -> None:
        """Remove ``tomo``'s done sentinel if present (for a forced re-run of one tomo)."""
        self.sentinel_path(tomo).unlink(missing_ok=True)

    def _should_skip(
        self,
        tomo: TomogramRef,
        cache_exists: Optional[Callable[[TomogramRef], bool]],
    ) -> bool:
        """Return True if ``tomo`` is already complete (sentinel or cache hit)."""
        if self.is_done(tomo):
            return True
        if cache_exists is not None and cache_exists(tomo):
            return True
        return False

    def run(
        self,
        tomos: Sequence[TomogramRef],
        job: Callable[[TomogramRef], R],
        *,
        force: bool = False,
        cache_exists: Optional[Callable[[TomogramRef], bool]] = None,
    ) -> RunReport[R]:
        """Run ``job`` over ``tomos``, skipping already-complete ones, and report per-tomo outcomes.

        Only the pending tomograms are dispatched to the executor. Each pending tomo runs inside a
        try/except so one failure does not abort the batch; a tomo that succeeds gets its sentinel
        written (so a later re-run skips it). A failing tomo leaves no sentinel and is re-tried on
        the next invocation — the resume contract.

        Args:
            tomos: The tomograms to process.
            job: The per-tomo callable; its return value is captured in the report.
            force: If True, ignore sentinels and the cache probe and run every tomo.
            cache_exists: Optional probe; a tomo for which it returns True is skipped (unless
                ``force``). This is the content-addressed cache hook (DESIGN §11, §13).

        Returns:
            A :class:`RunReport` with one :class:`TomoResult` per input tomogram (input order).
        """
        tomos = list(tomos)
        pending: List[TomogramRef] = []
        skipped_bases: set[str] = set()
        for t in tomos:
            if not force and self._should_skip(t, cache_exists):
                skipped_bases.add(t.base)
            else:
                pending.append(t)

        def _run_one(t: TomogramRef) -> TomoResult[R]:
            try:
                value = job(t)
            except Exception as exc:  # noqa: BLE001 - isolate one tomo's failure from the batch
                return TomoResult(base=t.base, status="failed", error=repr(exc))
            self.mark_done(t)
            return TomoResult(base=t.base, status="done", value=value)

        ran: List[TomoResult[R]] = self.executor.map(_run_one, pending) if pending else []
        ran_by_base = {r.base: r for r in ran}

        results: List[TomoResult[R]] = []
        for t in tomos:
            if t.base in skipped_bases:
                results.append(TomoResult(base=t.base, status="skipped"))
            else:
                results.append(ran_by_base[t.base])
        return RunReport(results=results)
