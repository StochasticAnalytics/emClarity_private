"""FittedConfig: the portable, serializable result of tuning the filter.

A :class:`FittedConfig` bundles everything scan needs to reconstruct the model and
everything transfer needs to warm-start on a new dataset: the provider list, the feature
spec, the constraint stanzas, the tuned parameters (theta), and per-tomo calibration stats.
It is the unit both drivers exchange (SPEC / DESIGN §8). Fully implemented with yaml I/O.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping

import yaml


@dataclass
class FittedConfig:
    """A fitted filter configuration (serializable to/from yaml).

    Args:
        version: Schema version tag.
        dataset: Name/id of the dataset this was fitted on.
        providers: Field-provider stanzas (``[{name: ..., **params}, ...]``).
        features: The feature column names the model consumes.
        constraints: Constraint stanzas (``[{name: ..., **params}, ...]``).
        combiner: The combiner/head configuration.
        theta: The tuned parameter values name -> value.
        calibration: Per-tomo calibration stats (e.g. background mean/std) keyed by tomo id.
        tau: The keep-probability decision threshold.
        meta: Free-form provenance (git revs, timestamps, objective, metrics).

    Attributes:
        version: Schema version.
        dataset: Dataset id.
        providers: Provider stanzas.
        features: Feature names.
        constraints: Constraint stanzas.
        combiner: Combiner config.
        theta: Tuned parameters.
        calibration: Per-tomo calibration stats.
        tau: Decision threshold.
        meta: Provenance metadata.
    """

    version: str = "0.1.0"
    dataset: str = ""
    providers: List[Dict[str, Any]] = field(default_factory=list)
    features: List[str] = field(default_factory=list)
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    combiner: Dict[str, Any] = field(default_factory=dict)
    theta: Dict[str, float] = field(default_factory=dict)
    calibration: Dict[str, Dict[str, float]] = field(default_factory=dict)
    tau: float = 0.5
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation (yaml/json ready)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FittedConfig":
        """Build a FittedConfig from a plain mapping (ignores unknown keys).

        Args:
            data: A mapping produced by :meth:`to_dict` (or hand-written yaml).

        Returns:
            The reconstructed :class:`FittedConfig`.
        """
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path) -> None:
        """Write this config to a yaml file.

        Args:
            path: Destination ``.yaml`` path (parent dirs created).
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            yaml.safe_dump(self.to_dict(), fh, sort_keys=False)

    @classmethod
    def load(cls, path: Path) -> "FittedConfig":
        """Read a FittedConfig from a yaml file.

        Args:
            path: Source ``.yaml`` path.

        Returns:
            The loaded :class:`FittedConfig`.
        """
        with Path(path).open("r") as fh:
            data = yaml.safe_load(fh) or {}
        return cls.from_dict(data)
