"""round_4_membrane.yaml (Phase-C membrane-geometry) config + provider wiring.

The membrane config must (a) name the four membrane features so their extractors build, (b) carry
a `membrane_geometry` constraint whose params reach the tuner, and (c) point `rec_dir` at the
alt_cache so `membrane_sdf` is DERIVABLE from the reconstruction (no separate membrane search or
manual trace). The MembraneDistanceProvider registered by the standard registry must report the
membrane SDF as producible-from-`rec`, not MISSING.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from mito_filter.cli import _build_extractors
from mito_filter.constraints.membrane import MembraneGeometryConstraint
from mito_filter.fields.derived import MembraneDistanceProvider
from mito_filter.model.filter_model import FilterModel
from mito_filter.optimize.space import ParameterSpace
from mito_filter.scan.context import build_field_registry

_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "round_4_membrane.yaml"


def test_membrane_config_names_all_membrane_features() -> None:
    cfg = yaml.safe_load(_CONFIG.read_text())
    feats = {f["name"] for f in cfg["features"]}
    for name in (
        "membrane_distance",
        "inside_outside_sign",
        "closed_shell_score",
        "membrane_facing",
    ):
        assert name in feats, name
    # rec_dir points at the alt_cache so membrane_sdf can be derived from the reconstruction.
    assert cfg["rec_dir"] == "/scratch/salina/alt_cache"


def test_membrane_config_builds_extractors() -> None:
    cfg = yaml.safe_load(_CONFIG.read_text())
    names = {type(e).__name__ for e in _build_extractors(cfg)}
    assert {"MembraneDistance", "InsideOutsideSign", "ClosedShellScore", "MembraneFacing"} <= names


def test_membrane_config_constraint_params_reach_tuner() -> None:
    cfg = yaml.safe_load(_CONFIG.read_text())
    spec = next(c for c in cfg["constraints"] if c["name"] == "membrane_geometry")
    con = MembraneGeometryConstraint(**{k: v for k, v in spec.items() if k != "name"})
    space = ParameterSpace.from_model(FilterModel([con]))
    names = set(space.names)
    assert "membrane_geometry::misface_weight" in names
    assert "membrane_geometry::wrong_side_weight" in names


def test_registry_membrane_sdf_is_generatable_from_rec() -> None:
    reg = build_field_registry(rec_dir=Path("/scratch/salina/alt_cache"), convmap_shape=None)
    prov = reg.get_provider("membrane_sdf")
    assert isinstance(prov, MembraneDistanceProvider)
    assert prov.from_rec and prov.requires == ("rec",)
