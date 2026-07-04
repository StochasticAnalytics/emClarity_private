"""FieldProvider: the load-vs-generate seam for dense fields.

A provider produces ONE named :class:`~mito_filter.core.field.DenseField` for a tomogram by
LOADING it from disk, DERIVING it from another field, or GENERATING it on GPU. An
:class:`Availability` tri-state plus a topologically-resolved :class:`FieldRegistry` DAG
make mixed-availability datasets work: a missing-but-generatable field is produced; a truly
missing field lets its dependent constraint go neutral.

``Availability``, :class:`FieldSpec`, and :class:`Cost` are FULLY implemented and frozen.
The :class:`FieldRegistry` topo-sort (``plan``) is implemented; ``resolve`` (with the
content-addressed cache) is a frozen-signature stub filled in downstream.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

from ..core.backend import Device
from ..core.field import Block, DenseField

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..datasets.base import TomogramRef


class FieldUnavailable(RuntimeError):
    """Raised by :meth:`FieldRegistry.resolve` when a field cannot be produced.

    A field is unavailable when its provider reports :attr:`Availability.MISSING`, or when a
    field it (transitively) ``requires`` is itself unavailable. Callers that want the neutral
    "skip the dependent constraint" behaviour use :meth:`FieldRegistry.try_resolve` instead,
    which returns ``None`` rather than raising.

    Args:
        field: The unresolvable field name.
        reason: Human-readable cause (which provider / dependency was missing).

    Attributes:
        field: The field name.
        reason: The cause string.
    """

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"field '{field}' unavailable: {reason}")


class Availability(Enum):
    """Tri-state describing whether a provider can produce its field for a tomogram."""

    ON_DISK = auto()
    """A file exists to load directly."""

    GENERATABLE = auto()
    """Inputs exist to derive or generate it."""

    MISSING = auto()
    """Cannot be produced -> dependent constraints contribute a neutral value."""


class CostTier(Enum):
    """Coarse cost class of materializing a field, cheapest first."""

    CHEAP_LOAD = auto()
    """mmap an existing file — negligible."""

    DERIVE = auto()
    """A cheap transform of already-materialized field(s)."""

    GPU_GENERATE = auto()
    """A full GPU generation (FFT-CC search, membrane search) — expensive."""


@dataclass(frozen=True)
class Cost:
    """A materialization cost hint used to order / schedule provider work.

    Args:
        tier: The coarse :class:`CostTier`.
        relative: A relative numeric weight within/across tiers (default 1.0), for
            schedulers that want a finer ordering than the tier alone.

    Attributes:
        tier: The cost tier.
        relative: The relative weight.
    """

    tier: CostTier
    relative: float = 1.0


CHEAP_LOAD: Cost = Cost(CostTier.CHEAP_LOAD, 1.0)
"""Preset cost for a plain mmap load."""

DERIVE: Cost = Cost(CostTier.DERIVE, 10.0)
"""Preset cost for a cheap derive."""

GPU_GENERATE: Cost = Cost(CostTier.GPU_GENERATE, 1000.0)
"""Preset cost for a full GPU generation."""


@dataclass(frozen=True)
class FieldSpec:
    """Static description of the field a provider produces.

    Args:
        name: The field name (e.g. ``"cc"``, ``"normal"``).
        channels: 1 scalar / 3 vector / 1 index.
        dtype: The on-disk / in-memory dtype.
        semantics: One-line human description of what the values mean.

    Attributes:
        name: The field name.
        channels: Channel count.
        dtype: The dtype.
        semantics: The semantics string.
    """

    name: str
    channels: int
    dtype: np.dtype
    semantics: str


class FieldProvider(ABC):
    """Produces ONE named :class:`DenseField` by loading, deriving, or generating.

    Subclasses set the class attributes :attr:`produces` and (optionally) :attr:`requires`
    and implement :meth:`available` and :meth:`materialize`.

    Attributes:
        produces: The :class:`FieldSpec` this provider yields.
        requires: Names of other fields it derives from (resolved first by the registry).
    """

    produces: FieldSpec
    requires: Tuple[str, ...] = ()

    @abstractmethod
    def available(self, tomo: "TomogramRef") -> Availability:
        """Report whether this provider can produce its field for ``tomo``.

        Args:
            tomo: The tomogram to check inputs for.

        Returns:
            The :class:`Availability` tri-state.
        """
        raise NotImplementedError

    @abstractmethod
    def materialize(
        self, tomo: "TomogramRef", reg: "FieldRegistry", *, device: Device
    ) -> DenseField:
        """Produce the field, resolving any ``requires`` through ``reg``.

        Args:
            tomo: The tomogram to materialize the field for.
            reg: The registry (used to resolve required upstream fields).
            device: The compute backend/device.

        Returns:
            The materialized :class:`DenseField`.
        """
        raise NotImplementedError

    def cache_path(self, tomo: "TomogramRef") -> Optional[Path]:
        """Return the on-disk cache path for a generated/derived field, or None.

        Args:
            tomo: The tomogram.

        Returns:
            A content-addressed cache path, or None for pure loaders.
        """
        return None

    def cost_hint(self) -> Cost:
        """Return the :class:`Cost` of materializing this field (default: DERIVE)."""
        return DERIVE


class FieldRegistry:
    """Name -> provider map, resolved as a DAG with per-tomo memoization.

    Providers are resolved in dependency order (``requires`` first) and the result is
    memoized per tomogram. Content-addressed on-disk caching keyed on
    ``(provider, params, source mtimes)`` is applied inside :meth:`resolve`.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, FieldProvider] = {}
        self._cache: Dict[Tuple[str, str], DenseField] = {}

    def register(self, p: FieldProvider) -> None:
        """Register a provider under its produced field name.

        Args:
            p: The provider. ``p.produces.name`` is the key.

        Raises:
            ValueError: If a provider for that field name is already registered.
        """
        name = p.produces.name
        if name in self._providers:
            raise ValueError(f"field '{name}' already has a provider")
        self._providers[name] = p

    def get_provider(self, name: str) -> FieldProvider:
        """Return the provider registered for field ``name``.

        Args:
            name: The field name.

        Returns:
            The registered provider.

        Raises:
            KeyError: If no provider is registered for ``name``.
        """
        try:
            return self._providers[name]
        except KeyError:
            known = ", ".join(sorted(self._providers)) or "<none>"
            raise KeyError(f"no provider for field '{name}'. Known: {known}") from None

    def plan(self, needed: Set[str], tomo: "TomogramRef") -> List[FieldProvider]:
        """Topologically order the providers needed to materialize ``needed``.

        Resolves the transitive ``requires`` closure and returns providers in an order
        where every provider's dependencies precede it.

        Args:
            needed: The set of top-level field names required.
            tomo: The tomogram (available for future availability-aware planning).

        Returns:
            Providers in dependency order (dependencies first).

        Raises:
            KeyError: If a required field has no registered provider.
            ValueError: If a dependency cycle is detected.
        """
        order: List[FieldProvider] = []
        seen: Set[str] = set()
        visiting: Set[str] = set()

        def visit(name: str) -> None:
            if name in seen:
                return
            if name in visiting:
                raise ValueError(f"field dependency cycle at '{name}'")
            visiting.add(name)
            prov = self.get_provider(name)
            for dep in prov.requires:
                visit(dep)
            visiting.discard(name)
            seen.add(name)
            order.append(prov)

        for n in sorted(needed):
            visit(n)
        return order

    def effective_availability(self, name: str, tomo: "TomogramRef") -> Availability:
        """Availability of ``name`` accounting for its transitive ``requires`` (DAG-aware).

        A derive/generate provider whose own inputs exist is only truly producible if every
        field it ``requires`` is also producible. This folds the dependency tri-state up the
        DAG: any ``MISSING`` (transitive) dependency makes ``name`` ``MISSING``; otherwise the
        provider's own :meth:`FieldProvider.available` verdict stands.

        Args:
            name: The field name.
            tomo: The tomogram.

        Returns:
            The effective :class:`Availability` for ``name`` on ``tomo``.

        Raises:
            KeyError: If ``name`` (or a dependency) has no registered provider.
        """
        prov = self.get_provider(name)
        own = prov.available(tomo)
        if own is Availability.MISSING:
            return Availability.MISSING
        for dep in prov.requires:
            if self.effective_availability(dep, tomo) is Availability.MISSING:
                return Availability.MISSING
        return own

    def resolve(self, name: str, tomo: "TomogramRef", *, device: Device) -> DenseField:
        """Materialize (or load from cache) field ``name`` for ``tomo``.

        Resolves the provider DAG (``requires`` first), memoizes per tomogram, and applies an
        opt-in content-addressed on-disk cache (only for providers that return a
        :meth:`FieldProvider.cache_path`; pure loaders skip it). The cache is keyed on the
        provider name, its parameters, and the mtime/size of its declared source files (via the
        optional ``cache_key_inputs(tomo)`` provider hook); a sidecar ``*.manifest.json`` stores
        the key and stale entries are rebuilt.

        Args:
            name: The field name to resolve.
            tomo: The tomogram.
            device: The compute backend/device.

        Returns:
            The materialized :class:`DenseField`.

        Raises:
            FieldUnavailable: If ``name`` or a required upstream field is ``MISSING``.
        """
        key = (name, self._tomo_key(tomo))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        prov = self.get_provider(name)
        if prov.available(tomo) is Availability.MISSING:
            raise FieldUnavailable(name, f"provider {type(prov).__name__}.available == MISSING")

        # Resolve dependencies first so materialize() can reg.resolve() them, and so a MISSING
        # dependency surfaces as FieldUnavailable rather than a materialize crash.
        for dep in prov.requires:
            try:
                self.resolve(dep, tomo, device=device)
            except FieldUnavailable as exc:
                raise FieldUnavailable(name, f"required field '{dep}' unavailable") from exc

        field = self._resolve_uncached(prov, tomo, device=device)
        self._cache[key] = field
        return field

    def try_resolve(
        self, name: str, tomo: "TomogramRef", *, device: Device
    ) -> Optional[DenseField]:
        """Like :meth:`resolve` but return ``None`` (not raise) when the field is unavailable.

        This is the "dependent constraint goes neutral" path (DESIGN §5): a ``MISSING`` field —
        or one with **no registered provider at all** (an optional field a config never wired) —
        yields ``None`` so the caller can skip/neutralise the constraint that wanted it. (A
        *required* dependency with no provider still fails loudly, because :meth:`resolve`'s
        dependency loop uses :meth:`resolve`, not this method.)

        Args:
            name: The field name.
            tomo: The tomogram.
            device: The compute backend/device.

        Returns:
            The resolved field, or ``None`` if it is unavailable / unregistered.
        """
        try:
            return self.resolve(name, tomo, device=device)
        except (FieldUnavailable, KeyError):
            return None

    # -- internal: cache-aware single-provider materialization ---------------------------------

    def _resolve_uncached(
        self, prov: FieldProvider, tomo: "TomogramRef", *, device: Device
    ) -> DenseField:
        """Materialize one provider, consulting/writing the on-disk cache when configured."""
        cpath = prov.cache_path(tomo)
        if cpath is None or prov.produces.channels != 1:
            # No cache dir configured, or a multi-channel field (scalar-mrc cache only).
            return prov.materialize(tomo, self, device=device)

        want_key = self._cache_key(prov, tomo)
        if cpath.exists() and self._manifest_key(cpath) == want_key:
            return self._load_cached_scalar(prov, cpath)

        field = prov.materialize(tomo, self, device=device)
        try:
            self._write_cached_scalar(prov, cpath, field, want_key)
        except OSError:
            # A cache-write failure must never fail resolution; return the live field.
            pass
        return field

    @staticmethod
    def _tomo_key(tomo: "TomogramRef") -> str:
        """Stable per-tomo memo key (the basename, else the object id)."""
        base = getattr(tomo, "base", None)
        return str(base) if base is not None else f"id{id(tomo)}"

    @staticmethod
    def _provider_params(prov: FieldProvider) -> Dict[str, object]:
        """Public, JSON-serialisable scalar parameters of a provider (for the cache key)."""
        params: Dict[str, object] = {}
        for k, v in sorted(vars(prov).items()):
            if k.startswith("_"):
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                params[k] = v
            elif isinstance(v, Path):
                params[k] = str(v)
        return params

    def _cache_key(self, prov: FieldProvider, tomo: "TomogramRef") -> str:
        """Content-addressed key over (field, provider params, source mtimes/sizes)."""
        inputs = getattr(prov, "cache_key_inputs", None)
        sources: List[List[object]] = []
        if callable(inputs):
            paths: Sequence[Path] = inputs(tomo)
            for p in sorted(Path(x) for x in paths):
                try:
                    st = p.stat()
                    sources.append([str(p), int(st.st_mtime_ns), int(st.st_size)])
                except OSError:
                    sources.append([str(p), -1, -1])
        payload = {
            "field": prov.produces.name,
            "provider": type(prov).__name__,
            "params": self._provider_params(prov),
            "sources": sources,
        }
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    @staticmethod
    def _manifest_path(cpath: Path) -> Path:
        """Sidecar manifest path for a cached field file."""
        return cpath.with_name(cpath.name + ".manifest.json")

    def _manifest_key(self, cpath: Path) -> Optional[str]:
        """Read the stored cache key from the sidecar manifest, or None if absent/broken."""
        mpath = self._manifest_path(cpath)
        try:
            data = json.loads(mpath.read_text())
            k = data.get("key")
            return str(k) if k is not None else None
        except (OSError, ValueError):
            return None

    def _load_cached_scalar(self, prov: FieldProvider, cpath: Path) -> DenseField:
        """Load a cached scalar field back as a memmap-backed :class:`DenseField`."""
        from ..emclarity.mrc_io import open_dense_field

        field = open_dense_field(cpath, prov.produces.name, channels=1)
        field.provider = prov
        return field

    def _write_cached_scalar(
        self, prov: FieldProvider, cpath: Path, field: DenseField, key: str
    ) -> None:
        """Write a scalar field + its manifest to the content-addressed cache."""
        from ..emclarity.mrc_io import write_dense_mrc

        cpath.parent.mkdir(parents=True, exist_ok=True)
        nz, ny, nx = field.grid.shape
        whole = field.block(Block((0, nz), (0, ny), (0, nx)))
        write_dense_mrc(cpath, np.asarray(whole, dtype=np.float32), apix=field.grid.apix)
        manifest = {
            "key": key,
            "field": prov.produces.name,
            "provider": type(prov).__name__,
            "params": self._provider_params(prov),
        }
        self._manifest_path(cpath).write_text(json.dumps(manifest, sort_keys=True, indent=2))
