"""Pipeline configuration: YAML -> typed dataclasses, ``!include``, env expansion (DESIGN §13).

This is the *run recipe* loader — distinct from :class:`mito_filter.model.config.FittedConfig`
(the tuned-parameter artifact). A :class:`PipelineConfig` records which candidate source, field
providers, constraints, combiner, and writeback settings a scan/optimize run uses; ``scan``
combines it with a :class:`~mito_filter.model.config.FittedConfig` (theta / tau) to build the
model.

Three YAML conveniences are supported (DESIGN §13):

* ``!include path`` — splice another YAML document (a reusable constraint fragment); the path is
  resolved relative to the including file, then recursively loaded (nested includes allowed).
* ``${VAR}`` / ``$VAR`` — expanded from the process environment in every string scalar (an
  unset variable expands to empty, matching ``os.path.expandvars``).
* every pluggable component is a ``{name: ..., **params}`` stanza (a bare string is shorthand for
  ``{name: <string>}``), so it round-trips through the registries.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union, cast

import yaml

__all__ = [
    "ComponentSpec",
    "WritebackConfig",
    "PipelineConfig",
    "expand_env",
    "load_yaml",
]


# --------------------------------------------------------------------------- #
# YAML loading: !include + ${ENV} expansion.                                   #
# --------------------------------------------------------------------------- #
class _IncludeLoader(yaml.SafeLoader):
    """A ``SafeLoader`` that resolves ``!include`` relative to the source file's directory."""

    def __init__(self, stream: Any) -> None:
        # ``stream.name`` is the file path when loading from an open file handle.
        self._root: Path = Path(getattr(stream, "name", ".")).resolve().parent
        super().__init__(stream)


def _construct_include(loader: _IncludeLoader, node: yaml.Node) -> Any:
    """Construct an ``!include`` node by loading the referenced YAML document.

    Args:
        loader: The active include-aware loader.
        node: The scalar node carrying the (possibly relative, env-expandable) path.

    Returns:
        The parsed contents of the included YAML document.

    Raises:
        FileNotFoundError: If the included path does not exist.
    """
    raw = str(loader.construct_scalar(cast(yaml.ScalarNode, node)))
    inc = Path(os.path.expandvars(raw))
    if not inc.is_absolute():
        inc = loader._root / inc
    return load_yaml(inc)


_IncludeLoader.add_constructor("!include", _construct_include)


def expand_env(obj: Any) -> Any:
    """Recursively expand ``${VAR}`` / ``$VAR`` in every string within a nested structure.

    Args:
        obj: A scalar, list, or dict (typically a parsed YAML tree).

    Returns:
        The same structure with environment variables expanded in every string leaf.
    """
    if isinstance(obj, str):
        return os.path.expandvars(obj)
    if isinstance(obj, Mapping):
        return {k: expand_env(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [expand_env(v) for v in obj]
    return obj


def load_yaml(path: Union[str, Path]) -> Any:
    """Load a YAML document with ``!include`` support and environment expansion.

    Args:
        path: Path to the YAML file.

    Returns:
        The parsed document (typically a dict), with ``!include`` spliced and ``${VAR}``
        expanded. An empty file yields ``{}``.
    """
    p = Path(path)
    with p.open("r") as fh:
        data = yaml.load(fh, Loader=_IncludeLoader)  # noqa: S506 - _IncludeLoader is SafeLoader
    if data is None:
        return {}
    return expand_env(data)


# --------------------------------------------------------------------------- #
# Typed config dataclasses.                                                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ComponentSpec:
    """A named, parameterised pluggable component (a provider / source / constraint stanza).

    Args:
        name: The registry name of the component.
        params: The remaining keyword parameters passed to its constructor.

    Attributes:
        name: The component name.
        params: The constructor parameters.
    """

    name: str
    params: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_obj(cls, obj: Union[str, Mapping[str, Any], "ComponentSpec"]) -> "ComponentSpec":
        """Build a :class:`ComponentSpec` from a string, a ``{name, **params}`` mapping, or itself.

        Args:
            obj: A bare component name, a mapping with a ``name`` key plus params, or an existing
                :class:`ComponentSpec`.

        Returns:
            The parsed :class:`ComponentSpec`.

        Raises:
            ValueError: If a mapping is given without a ``name`` key.
            TypeError: If ``obj`` is not a string, mapping, or :class:`ComponentSpec`.
        """
        if isinstance(obj, ComponentSpec):
            return obj
        if isinstance(obj, str):
            return cls(obj, {})
        if isinstance(obj, Mapping):
            data = dict(obj)
            if "name" not in data:
                raise ValueError(f"component stanza missing 'name': {obj!r}")
            name = str(data.pop("name"))
            return cls(name, data)
        raise TypeError(f"cannot parse a ComponentSpec from {obj!r}")

    def to_dict(self) -> Dict[str, Any]:
        """Return the ``{name: ..., **params}`` dict form."""
        return {"name": self.name, **dict(self.params)}


def _spec_list(objs: Optional[Sequence[Any]]) -> List[ComponentSpec]:
    """Parse a list of component stanzas into :class:`ComponentSpec` objects."""
    return [ComponentSpec.from_obj(o) for o in (objs or [])]


@dataclass
class WritebackConfig:
    """Where and how a scan writes its verdicts (DESIGN §9.1).

    Args:
        debug_csv: If True, mirror the keep/remove decision into col26 of a debug csv.
        removal_json: If True, emit the subtomo-id-keyed removal list as JSON (a runnable output).
        removal_table: If True, also emit the ``matio`` text removal table.
        mat_apply: If True, render (but never execute) the MATLAB-on-salina apply stub.
        cycle: The classification cycle whose ``.mat`` geometry the apply stub edits.
        mat_path: Path to the subTomoMeta ``.mat`` (only used to render the stub).
        out_dir: Output directory for the generated artifacts (relative to CWD when unset).

    Attributes:
        debug_csv: Whether the col26 debug csv is written.
        removal_json: Whether the JSON removal list is written.
        removal_table: Whether the text removal table is written.
        mat_apply: Whether the MATLAB apply stub is rendered.
        cycle: The classification cycle number.
        mat_path: The ``.mat`` path.
        out_dir: The output directory.
    """

    debug_csv: bool = True
    removal_json: bool = True
    removal_table: bool = False
    mat_apply: bool = False
    cycle: Optional[int] = None
    mat_path: Optional[str] = None
    out_dir: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> "WritebackConfig":
        """Build a :class:`WritebackConfig` from a mapping (ignoring unknown keys)."""
        data = data or {}
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class PipelineConfig:
    """A resolved scan/optimize run recipe (DESIGN §13).

    Args:
        dataset: Name/id of the dataset the run targets.
        data_root: Directory holding the per-tomo ``<base>_convmap.mrc`` (+ siblings).
        rec_dir: Directory holding the searched ``<base>.rec`` (per-host ``alt_cache``).
        device: Backend device selector (``"cpu"`` / ``"cupy"`` / ``"torch"`` / ``"auto"``).
        cache_dir: Root of the content-addressed field/feature cache (resumability).
        candidate_source: The candidate source stanza (defaults to ``csv_peaks``).
        providers: Field-provider stanzas.
        constraints: Constraint stanzas.
        combiner: Combiner/head configuration.
        features: Explicit feature column list (usually derived from the constraints).
        theta: Tuned parameter overrides (name -> value).
        tau: Keep-probability decision threshold.
        writeback: Writeback settings.
        meta: Free-form provenance.

    Attributes:
        dataset: The dataset id.
        data_root: The convmap directory.
        rec_dir: The rec directory.
        device: The device selector.
        cache_dir: The cache root.
        candidate_source: The candidate-source spec.
        providers: The provider specs.
        constraints: The constraint specs.
        combiner: The combiner config.
        features: The explicit feature list.
        theta: The tuned parameters.
        tau: The decision threshold.
        writeback: The writeback config.
        meta: Provenance metadata.
    """

    dataset: str = ""
    data_root: Optional[str] = None
    rec_dir: Optional[str] = None
    device: str = "cpu"
    cache_dir: Optional[str] = None
    candidate_source: ComponentSpec = field(default_factory=lambda: ComponentSpec("csv_peaks", {}))
    providers: List[ComponentSpec] = field(default_factory=list)
    constraints: List[ComponentSpec] = field(default_factory=list)
    combiner: Dict[str, Any] = field(default_factory=dict)
    features: List[str] = field(default_factory=list)
    theta: Dict[str, float] = field(default_factory=dict)
    tau: float = 0.5
    writeback: WritebackConfig = field(default_factory=WritebackConfig)
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PipelineConfig":
        """Build a :class:`PipelineConfig` from a parsed YAML mapping.

        Args:
            data: The mapping (typically from :func:`load_yaml`); unknown keys are ignored.

        Returns:
            The typed :class:`PipelineConfig`.
        """
        d = dict(data)
        cs = d.get("candidate_source")
        candidate_source = (
            ComponentSpec.from_obj(cs) if cs is not None else ComponentSpec("csv_peaks", {})
        )
        return cls(
            dataset=str(d.get("dataset", "")),
            data_root=d.get("data_root"),
            rec_dir=d.get("rec_dir"),
            device=str(d.get("device", "cpu")),
            cache_dir=d.get("cache_dir"),
            candidate_source=candidate_source,
            providers=_spec_list(d.get("providers")),
            constraints=_spec_list(d.get("constraints")),
            combiner=dict(d.get("combiner", {})),
            features=[str(x) for x in d.get("features", [])],
            theta={str(k): float(v) for k, v in dict(d.get("theta", {})).items()},
            tau=float(d.get("tau", 0.5)),
            writeback=WritebackConfig.from_dict(d.get("writeback")),
            meta=dict(d.get("meta", {})),
        )

    @classmethod
    def load(cls, path: Union[str, Path]) -> "PipelineConfig":
        """Load and parse a pipeline-config YAML file (``!include`` + env expansion applied).

        Args:
            path: Path to the config YAML.

        Returns:
            The typed :class:`PipelineConfig`.

        Raises:
            TypeError: If the document root is not a mapping.
        """
        data = load_yaml(path)
        if not isinstance(data, Mapping):
            raise TypeError(f"{path}: config root must be a mapping, got {type(data).__name__}")
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation (yaml/json ready, provenance-friendly)."""
        out = asdict(self)
        out["candidate_source"] = self.candidate_source.to_dict()
        out["providers"] = [p.to_dict() for p in self.providers]
        out["constraints"] = [c.to_dict() for c in self.constraints]
        return out
