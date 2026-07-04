"""Round-4 Phase-A config + curvature defaults (finding-3 regression).

The surface discriminator is inert on the sparse csv candidates at ~300 A (csv peaks are
NMS-separated by the ~[210,210,320] A erase cylinder, so ~44% have zero neighbors). The default
neighborhood radius must be sized for that sparse regime, and the config must wire an isolation
term so the isolated hits (which surface_coherence forces to coherence=1.0) are scored by
SOMETHING.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from mito_filter.features.curvature import NormalCoherence, PrincipalCurvature, SurfaceFitResidual
from mito_filter.features.isolation import NeighborDensity, OffSurfaceIsolation

_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "round_4.yaml"


def test_curvature_defaults_sized_for_sparse_csv() -> None:
    # Default radius must clear the ~300 A erase-radius inert zone (needs >= ~600 A; see finding 3).
    for cls in (NormalCoherence, SurfaceFitResidual, PrincipalCurvature):
        assert cls().radius_A >= 600.0, cls.__name__
    for cls2 in (NeighborDensity, OffSurfaceIsolation):
        assert cls2().radius_A >= 600.0, cls2.__name__


def test_round4_config_radii_and_isolation_wired() -> None:
    cfg = yaml.safe_load(_CONFIG.read_text())
    feats = {f["name"]: f for f in cfg["features"]}
    # Surface features use the sparse-regime radius, not ~300.
    for name in ("normal_coherence", "surface_fit_residual", "principal_curvature"):
        assert feats[name]["radius_A"] >= 600
    # Isolation features present so the isolation constraint has inputs.
    assert "neighbor_density" in feats
    assert "off_surface_isolation" in feats
    # The isolation constraint is wired (catches the isolated FPs surface_coherence cannot).
    con_names = {c["name"] for c in cfg["constraints"]}
    assert "isolation" in con_names
    assert "surface_coherence" in con_names
