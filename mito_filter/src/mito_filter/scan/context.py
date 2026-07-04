"""RunContext: the assembled, ready-to-run scan bundle (DESIGN §8, §13).

A :class:`RunContext` holds everything :class:`~mito_filter.scan.pipeline.ScanPipeline` needs and
nothing per-tomo: the field-provider :class:`~mito_filter.fields.provider.FieldRegistry` (with its
per-tomo cache), the :class:`~mito_filter.candidates.source.CandidateSource`, the
:class:`~mito_filter.features.engine.FeatureEngine` (the exact extractors), the
:class:`~mito_filter.model.filter_model.FilterModel`, the resolved backend/device, the decision
threshold ``tau``, and per-tomo calibration stats. It is built once and reused across every tomo.

Two constructors: :meth:`RunContext.build` (explicit components — the typed, primary path) and
:meth:`RunContext.from_pipeline_config` (a convenience that wires a
:class:`~mito_filter.config.PipelineConfig` through the registries, given the concrete extractors).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Mapping, Optional, Sequence, Tuple

from ..candidates.source import CandidateSource
from ..config import PipelineConfig
from ..constraints.base import Constraint
from ..constraints.combine import CONSTRAINT_REGISTRY
from ..core.backend import Backend, Device
from ..core.grid import VoxelGrid
from ..emclarity.constants import APIX_A, CONVMAP_SHAPE
from ..emclarity.mrc_io import read_header
from ..features.engine import FeatureEngine
from ..features.extractor import BlockCtx, FeatureExtractor
from ..fields import _tomo
from ..fields.provider import FieldRegistry
from ..model.config import FittedConfig
from ..model.filter_model import Combiner, FilterModel

__all__ = [
    "RunContext",
    "device_from_string",
    "build_field_registry",
    "constraints_from_specs",
]

_DEVICE_BY_NAME: Dict[str, Device] = {
    "cpu": Device.CPU,
    "cupy": Device.CUPY,
    "torch": Device.TORCH,
}


def device_from_string(name: str) -> Device:
    """Resolve a device name to a :class:`Device` (``"auto"`` picks the best available).

    Args:
        name: One of ``"cpu"``, ``"cupy"``, ``"torch"``, ``"auto"`` (case-insensitive).

    Returns:
        The resolved :class:`Device`.

    Raises:
        ValueError: If ``name`` is not a recognised device selector.
    """
    key = str(name).lower()
    if key == "auto":
        return Backend.auto().device
    try:
        return _DEVICE_BY_NAME[key]
    except KeyError:
        raise ValueError(f"unknown device '{name}' (cpu|cupy|torch|auto)") from None


def build_field_registry(
    *,
    rec_dir: Optional[Path] = None,
    with_derived: bool = True,
    convmap_shape: Optional[Tuple[int, int, int]] = CONVMAP_SHAPE,
) -> FieldRegistry:
    """Build a :class:`FieldRegistry` populated with the standard providers (DESIGN §5).

    Registers the Phase-A loaders (``cc``, ``rec``, ``noise_variance``, ``angle``) and, by
    default, the derived providers (``snr``, ``normal``, cluster density, blobness, membrane
    distance). Providers that cannot produce their field on the current data simply report
    ``MISSING`` and their dependent features/constraints go neutral.

    Args:
        rec_dir: Optional override for the ``rec`` provider's directory.
        with_derived: If True, also register the derived providers.
        convmap_shape: Shape the ``cc`` loader asserts (pass the discovered header shape so any
            round loads; None skips the check). Defaults to the SPEC convmap shape.

    Returns:
        The populated registry.
    """
    from ..fields.loaders import register_loaders

    reg = FieldRegistry()
    register_loaders(reg, rec_dir=rec_dir, convmap_shape=convmap_shape)
    if with_derived:
        from ..fields.derived import register_derived

        register_derived(reg)
    return reg


def constraints_from_specs(specs: Sequence[Any]) -> list[Constraint]:
    """Instantiate constraints from ``{name, **params}`` stanzas via the constraint registry.

    Args:
        specs: A sequence of :class:`~mito_filter.config.ComponentSpec` (or objects exposing
            ``name`` / ``params``).

    Returns:
        The instantiated constraints, in stanza order.
    """
    out: list[Constraint] = []
    for spec in specs:
        name = spec.name
        params = dict(getattr(spec, "params", {}))
        out.append(CONSTRAINT_REGISTRY.create(name, **params))
    return out


def combiner_from_block(names: Sequence[str], block: Mapping[str, Any]) -> Optional[Combiner]:
    """Build a uniform :class:`Combiner` from a pipeline-config ``combiner:`` scalar stanza.

    The fusion head is **canonical FilterModel convention** ``keep = sigmoid(bias + S @ w)``, so a
    false-positive axis carries a *negative* weight. Only the **uniform scalar** form
    ``{weight: <float>, bias: <float>}`` is materialized here (every axis gets ``weight`` and the
    scalar ``bias`` -> :meth:`Combiner.default`). Before this, that scalar form was silently dropped
    and the head fell back to the built-in default ``bias=0`` (ignoring a config's ``bias``).

    A per-axis ``weights`` **list** stanza is intentionally *not* materialized here -- list weights
    travel through ``theta`` (``combiner::w::<axis>`` / ``combiner::bias``), the authoritative
    machine channel every fitted config already uses (e.g. ``round_4_fitted.yaml``). A list block is
    treated as human-readable documentation of that theta, so there is no silent-override ambiguity
    between the two. ``theta`` is applied by the caller after this and always wins.

    Args:
        names: Constraint names in column order (the model's constraint order).
        block: The parsed ``combiner`` mapping (may be empty).

    Returns:
        A uniform :class:`Combiner` for the scalar form, else ``None`` (list form / empty block ->
        weights come from ``theta``).
    """
    if not block:
        return None
    if "weight" in block and block["weight"] is not None:
        return Combiner.default(
            list(names),
            weight=float(block["weight"]),
            bias=float(block.get("bias", 0.0)),
        )
    return None


@dataclass
class RunContext:
    """The shared, per-run scan context (DESIGN §8).

    Args:
        field_registry: The field-provider DAG registry (with per-tomo cache).
        candidate_source: The candidate source (csv peaks / dense peaks).
        engine: The feature engine (the exact extractors to run).
        model: The fitted :class:`FilterModel` (constraints + combiner).
        backend: The resolved array backend.
        device: The compute device (drives ``FieldRegistry.resolve``).
        tau: The keep-probability decision threshold.
        dataset: The subTomoMeta project label.
        apix: Physical voxel size in Angstrom for the tomogram grids.
        cache_dir: Root of the per-tomo field/feature/verdict cache (resumability); None disables.
        calibration: Per-tomo background stats keyed by basename (``{base: {bg_mean, bg_std}}``).
        meta: Free-form run metadata folded into every :class:`BlockCtx`.

    Attributes:
        field_registry: The registry.
        candidate_source: The candidate source.
        engine: The feature engine.
        model: The filter model.
        backend: The backend.
        device: The device.
        tau: The decision threshold.
        dataset: The project label.
        apix: The voxel size.
        cache_dir: The cache root.
        calibration: The per-tomo calibration stats.
        meta: The run metadata.
    """

    field_registry: FieldRegistry
    candidate_source: CandidateSource
    engine: FeatureEngine
    model: FilterModel
    backend: Backend = field(default_factory=Backend.cpu)
    device: Device = Device.CPU
    tau: float = 0.5
    dataset: str = ""
    apix: float = APIX_A
    cache_dir: Optional[Path] = None
    calibration: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tau = float(self.tau)
        self.apix = float(self.apix)
        if self.cache_dir is not None:
            self.cache_dir = Path(self.cache_dir)

    # -- requirements -----------------------------------------------------------------
    @property
    def needed_fields(self) -> FrozenSet[str]:
        """The union of dense-field names the engine's extractors require."""
        return self.engine.needed_fields

    @property
    def needed_features(self) -> tuple[str, ...]:
        """The ordered union of feature columns the model's constraints consume."""
        return self.model.needs_features

    # -- per-tomo helpers -------------------------------------------------------------
    def grid_for(self, tomo: object) -> VoxelGrid:
        """Build the tomogram's :class:`VoxelGrid` from its convmap header (SPEC §1).

        Args:
            tomo: The tomogram reference (exposes ``convmap_path``).

        Returns:
            The convmap voxel grid at :attr:`apix`.
        """
        hdr = read_header(_tomo.convmap_path_of(tomo))
        return VoxelGrid(shape=hdr.shape_zyx, apix=self.apix)

    def block_meta(self, tomo: object) -> Dict[str, Any]:
        """Assemble the per-tomo :class:`BlockCtx` metadata (calibration + run meta).

        Args:
            tomo: The tomogram reference.

        Returns:
            A metadata dict: the run ``meta``, the tomo basename/dataset, and any per-tomo
            ``bg_mean`` / ``bg_std`` calibration stats.
        """
        base = _tomo.base_of(tomo)
        out: Dict[str, Any] = dict(self.meta)
        out.setdefault("dataset", self.dataset)
        out["tomo"] = base
        cal = self.calibration.get(base)
        if cal is not None:
            out.update({str(k): float(v) for k, v in cal.items()})
        return out

    def block_ctx(self, grid: VoxelGrid, tomo: object) -> BlockCtx:
        """Build the :class:`BlockCtx` handed to feature extractors for one tomogram.

        Args:
            grid: The tomogram voxel grid.
            tomo: The tomogram reference (supplies calibration/meta).

        Returns:
            The configured :class:`BlockCtx`.
        """
        return BlockCtx(grid=grid, backend=self.backend, meta=self.block_meta(tomo))

    def tomo_cache_dir(self, tomo: object) -> Optional[Path]:
        """Return the per-tomo cache directory (``<cache_dir>/<base>``), or None if disabled."""
        if self.cache_dir is None:
            return None
        return Path(self.cache_dir) / _tomo.base_of(tomo)

    def csv_path_for(self, tomo: object) -> Path:
        """Return the tomogram's ``<base>.csv`` sibling path."""
        return _tomo.sibling(tomo, ".csv")

    # -- constructors -----------------------------------------------------------------
    @classmethod
    def build(
        cls,
        *,
        field_registry: FieldRegistry,
        candidate_source: CandidateSource,
        engine: FeatureEngine,
        model: FilterModel,
        device: Device = Device.CPU,
        tau: float = 0.5,
        dataset: str = "",
        apix: float = APIX_A,
        cache_dir: Optional[Path] = None,
        calibration: Optional[Mapping[str, Mapping[str, float]]] = None,
        meta: Optional[Mapping[str, Any]] = None,
    ) -> "RunContext":
        """Assemble a :class:`RunContext` from explicit components (the primary, typed path).

        Args:
            field_registry: The populated field registry.
            candidate_source: The candidate source.
            engine: The feature engine.
            model: The filter model.
            device: The compute device.
            tau: The decision threshold.
            dataset: The project label.
            apix: The voxel size in Angstrom.
            cache_dir: The cache root (None disables caching/resume).
            calibration: Per-tomo background stats keyed by basename.
            meta: Run metadata.

        Returns:
            The assembled :class:`RunContext`.
        """
        return cls(
            field_registry=field_registry,
            candidate_source=candidate_source,
            engine=engine,
            model=model,
            backend=Backend(device),
            device=device,
            tau=tau,
            dataset=dataset,
            apix=apix,
            cache_dir=cache_dir,
            calibration=dict(calibration or {}),
            meta=dict(meta or {}),
        )

    @classmethod
    def from_pipeline_config(
        cls,
        config: PipelineConfig,
        *,
        extractors: Sequence[FeatureExtractor],
        candidate_source: Optional[CandidateSource] = None,
        field_registry: Optional[FieldRegistry] = None,
        fitted: Optional[FittedConfig] = None,
    ) -> "RunContext":
        """Wire a :class:`~mito_filter.config.PipelineConfig` into a :class:`RunContext`.

        Constraints are instantiated from the constraint registry; the model uses a default
        (uniform-weight) combiner then applies ``config.theta`` (overridden by ``fitted.theta``
        when a :class:`FittedConfig` is supplied). The caller passes the concrete ``extractors``
        (feature selection stays explicit — the DESIGN feature/alias names do not always match an
        extractor's ``produces``, so auto-selection is out of scope here).

        Args:
            config: The resolved pipeline config.
            extractors: The feature extractors to run.
            candidate_source: Explicit candidate source (defaults to :class:`CsvPeakSource`).
            field_registry: Explicit registry (defaults to the standard providers).
            fitted: Optional fitted config supplying ``theta``/``tau`` overrides.

        Returns:
            The assembled :class:`RunContext`.
        """
        device = device_from_string(config.device)
        reg = field_registry
        if reg is None:
            rec = Path(config.rec_dir) if config.rec_dir else None
            reg = build_field_registry(rec_dir=rec)

        source = candidate_source
        if source is None:
            from ..candidates.csv_source import CsvPeakSource

            src_params = dict(config.candidate_source.params)
            source = CsvPeakSource(**src_params)

        constraints = constraints_from_specs(config.constraints)
        model = FilterModel(constraints)
        block_combiner = combiner_from_block([c.name for c in constraints], config.combiner)
        if block_combiner is not None:
            model.combiner = block_combiner
        if config.theta:
            model.set_theta(config.theta)
        tau = config.tau
        if fitted is not None:
            if fitted.theta:
                model.set_theta(fitted.theta)
            tau = fitted.tau

        return cls.build(
            field_registry=reg,
            candidate_source=source,
            engine=FeatureEngine(list(extractors)),
            model=model,
            device=device,
            tau=tau,
            dataset=config.dataset,
            cache_dir=Path(config.cache_dir) if config.cache_dir else None,
            meta=dict(config.meta),
        )
