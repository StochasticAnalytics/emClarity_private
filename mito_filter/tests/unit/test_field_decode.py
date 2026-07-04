"""IndexField decode-hook wiring (the emClarity convention stays quarantined)."""

from __future__ import annotations

from typing import cast

import numpy as np

from mito_filter.core import field as field_mod
from mito_filter.core.field import (
    Block,
    DenseField,
    IndexField,
    VectorField,
    register_index_decoders,
)
from mito_filter.core.grid import VoxelGrid


def test_register_and_dispatch_decoders() -> None:
    saved = (field_mod._normal_decoder, field_mod._template_decoder)
    try:
        grid = VoxelGrid((2, 3, 4), 12.5)
        packed = np.ones((2, 3, 4), dtype=np.int16)
        idxf = cast(IndexField, IndexField.from_array("angle", grid, packed))

        def _norm(f: IndexField, angles: np.ndarray) -> VectorField:
            vol = np.zeros(f.grid.shape + (3,), dtype=np.float32)
            vol[..., 2] = 1.0
            return cast(VectorField, VectorField.from_array("normal", f.grid, vol, channels=3))

        def _tmpl(f: IndexField) -> DenseField:
            return DenseField.from_array(
                "template", f.grid, np.zeros(f.grid.shape, dtype=np.float32)
            )

        register_index_decoders(normal=_norm, template=_tmpl)
        n = idxf.decode_normal(np.zeros((864, 3)))
        t = idxf.decode_template()
        assert isinstance(n, VectorField) and n.channels == 3
        assert isinstance(t, DenseField)
        assert n.shape == (2, 3, 4, 3)
    finally:
        field_mod._normal_decoder, field_mod._template_decoder = saved


def test_production_wiring_installs_decoders() -> None:
    # Regression (finding 7): decode_normal/decode_template must work in production with NO
    # test-injected fakes -- importing the emClarity adapter must call register_index_decoders.
    # Clear any registration then import conventions to prove the side-effect installs real ones.
    import importlib

    saved = (field_mod._normal_decoder, field_mod._template_decoder)
    try:
        field_mod._normal_decoder = None
        field_mod._template_decoder = None
        conv = importlib.import_module("mito_filter.emclarity.conventions")
        importlib.reload(conv)  # re-run the module body -> register_index_decoders(...)
        assert field_mod._normal_decoder is not None
        assert field_mod._template_decoder is not None

        grid = VoxelGrid((2, 3, 4), 12.5)
        # packed=1 -> angle_idx 1, ref 1. angles row 0 = [0,0,0] -> normal [0,0,1] raw (x,y,z),
        # reversed to (z,y,x) = [1,0,0].
        packed = np.ones((2, 3, 4), dtype=np.int16)
        idxf = cast(IndexField, IndexField.from_array("angle", grid, packed))
        angles = np.zeros((864, 3), dtype=np.float64)
        n = idxf.decode_normal(angles)
        t = idxf.decode_template()
        assert isinstance(n, VectorField) and n.shape == (2, 3, 4, 3)
        nvol = np.asarray(n.block(Block((0, 2), (0, 3), (0, 4))))
        assert np.allclose(nvol[..., 0], 1.0)  # (z,y,x) normal[0] == 1 for the theta=0 grid row
        assert isinstance(t, DenseField) and t.shape == (2, 3, 4)
        tvol = np.asarray(t.block(Block((0, 2), (0, 3), (0, 4))))
        assert np.allclose(tvol, 1.0)  # ref_idx == 1
    finally:
        field_mod._normal_decoder, field_mod._template_decoder = saved
