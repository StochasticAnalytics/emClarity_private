"""round_4_dense.yaml (Phase-B dense-orientation) config + CLI candidate-source wiring.

The dense config must drive the surface features off the DENSE normal field (``normal_source:
field``, so their ``needs_fields`` pull the ``angle`` -> ``normal`` DAG) and the CLI must honour a
``candidate_source: dense_peaks`` stanza by building a
:class:`~mito_filter.candidates.dense_source.DenseFieldPeakSource` bound to the field registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mito_filter.candidates.csv_source import CsvPeakSource
from mito_filter.candidates.dense_source import DenseFieldPeakSource
from mito_filter.cli import _build_candidate_source, _build_extractors
from mito_filter.core.backend import Device
from mito_filter.features.curvature import _CurvatureBase
from mito_filter.scan.context import build_field_registry

_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "round_4_dense.yaml"


def test_dense_config_surface_features_use_dense_normal_field() -> None:
    cfg = yaml.safe_load(_CONFIG.read_text())
    feats = {f["name"]: f for f in cfg["features"]}
    for name in ("normal_coherence", "surface_fit_residual", "principal_curvature"):
        assert feats[name]["normal_source"] == "field", name
        assert feats[name]["radius_A"] >= 600
    # The active candidate source keeps the sparse csv peaks so the sparse-vs-dense comparison is
    # one-to-one; dense_peaks is documented as the commented alternative.
    assert cfg["candidate_source"] == "csv_peaks"


def test_dense_config_extractors_pull_angle_normal_dag() -> None:
    cfg = yaml.safe_load(_CONFIG.read_text())
    extractors = _build_extractors(cfg)
    surface = [e for e in extractors if isinstance(e, _CurvatureBase)]
    assert surface, "no surface extractors built"
    for e in surface:
        assert e.normal_source == "field"
        # field mode declares the normal + cc field deps (so the pipeline resolves angle->normal).
        assert "normal" in e.needs_fields and "cc" in e.needs_fields


def test_cli_builds_dense_peaks_candidate_source() -> None:
    reg = build_field_registry(convmap_shape=None)
    src = _build_candidate_source(
        {
            "candidate_source": {
                "name": "dense_peaks",
                "field_name": "cc",
                "threshold": 4.5,
                "normal_field_name": "normal",
            }
        },
        reg,
        Device.CPU,
    )
    assert isinstance(src, DenseFieldPeakSource)
    assert src.field_name == "cc"
    assert src.threshold == 4.5
    assert src.normal_field_name == "normal"


def test_cli_defaults_to_csv_peaks_and_rejects_unknown() -> None:
    reg = build_field_registry(convmap_shape=None)
    assert isinstance(_build_candidate_source({}, reg, Device.CPU), CsvPeakSource)
    with pytest.raises(ValueError, match="unknown candidate_source"):
        _build_candidate_source({"candidate_source": "bogus_src"}, reg, Device.CPU)
