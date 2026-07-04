"""Golden-value tests for emClarity MRC IO against the REAL convmap + the fp16 refusal.

Locks (SPEC §1, §5, §7):

- the real convmap is ``558_750_208`` B, shape ``(448, 942, 662)``, mode 12 (float16);
- a memmap reads native fp16 and a block casts to fp32 matching a direct read;
- a packed-index field is **refused** as mode-12 (dtype guard + write guard + read guard),
  and fp16 is not integer-exact above 2048;
- mode-2 fp32 write round-trips and an fp32 index round-trips value 2592 exactly.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from mito_filter.emclarity import constants as C
from mito_filter.emclarity.mrc_io import (
    MODE_FLOAT16,
    MODE_FLOAT32,
    assert_index_dtype,
    fp16_integer_exact,
    open_dense_field,
    open_dense_mmap,
    read_block,
    read_header,
    write_dense_mrc,
)


def test_real_convmap_header(real_convmap_path: Path) -> None:
    hdr = read_header(real_convmap_path)
    assert hdr.shape_zyx == C.CONVMAP_SHAPE
    assert hdr.mode == C.CONVMAP_MODE == MODE_FLOAT16
    assert real_convmap_path.stat().st_size == C.CONVMAP_BYTES
    assert hdr.expected_bytes == C.CONVMAP_BYTES
    assert hdr.dtype == np.dtype("<f2")


def test_real_convmap_mmap_and_block(real_convmap_path: Path) -> None:
    mm = open_dense_mmap(real_convmap_path, expected_shape=C.CONVMAP_SHAPE)
    assert mm.shape == C.CONVMAP_SHAPE
    assert mm.dtype == np.float16
    blk = read_block(mm, (60, 70), (820, 830), (640, 650))
    assert blk.dtype == np.float32
    assert blk.shape == (10, 10, 10)
    direct = np.asarray(mm[60:70, 820:830, 640:650], np.float32)
    assert np.array_equal(blk, direct)


def test_open_dense_field(real_convmap_path: Path) -> None:
    fld = open_dense_field(real_convmap_path, "cc", expected_shape=C.CONVMAP_SHAPE)
    assert fld.name == "cc"
    assert fld.grid.shape == C.CONVMAP_SHAPE
    assert fld.grid.apix == C.APIX_A
    # DenseField.block casts fp16 -> fp32
    from mito_filter.core.field import Block

    out = fld.block(Block((0, 4), (0, 4), (0, 4)))
    assert out.dtype == np.float32 and out.shape == (4, 4, 4)


def test_index_dtype_refusal() -> None:
    # fp16 packed index -> refused (2592 > fp16 integer-exact 2048)
    with pytest.raises(ValueError):
        assert_index_dtype(np.dtype(np.float16))
    # fp32 / int16 are allowed
    assert_index_dtype(np.dtype(np.float32))
    assert_index_dtype(np.dtype(np.int16))


def test_write_refuses_fp16_index(tmp_path: Path) -> None:
    vol = np.full((4, 4, 4), C.PACKED_INDEX_MAX, dtype=np.float16)
    with pytest.raises(ValueError):
        write_dense_mrc(tmp_path / "idx.mrc", vol, is_index=True)


def test_read_refuses_mode12_index(real_convmap_path: Path) -> None:
    # the convmap is mode-12; reading it AS a packed-index field must be refused
    with pytest.raises(ValueError):
        open_dense_mmap(real_convmap_path, is_index=True)


def test_fp16_integer_exact_boundary() -> None:
    vals = np.array([2048, 2049, 2590, 2591, 2592], dtype=np.int64)
    exact = fp16_integer_exact(vals)
    assert bool(exact[0])  # 2048 exact
    assert not bool(exact[1])  # 2049 (odd) corrupts
    assert not bool(exact[3])  # 2591 (odd) corrupts
    # a fp16 store of an odd index above 2048 changes its value
    assert int(np.float16(2591).astype(np.int64)) != 2591


def test_mode2_fp32_write_roundtrip(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    vol = rng.standard_normal((5, 6, 7)).astype(np.float32)
    p = tmp_path / "field.mrc"
    write_dense_mrc(p, vol, apix=C.APIX_A)
    hdr = read_header(p)
    assert hdr.mode == MODE_FLOAT32
    assert hdr.shape_zyx == (5, 6, 7)
    back = np.asarray(open_dense_mmap(p), np.float32)
    assert np.allclose(back, vol, atol=1e-6)


def test_fp32_index_write_exact(tmp_path: Path) -> None:
    # an fp32 index round-trips 2592 exactly (contrast with the refused fp16)
    vol = np.full((3, 3, 3), C.PACKED_INDEX_MAX, dtype=np.float32)
    p = tmp_path / "idx32.mrc"
    write_dense_mrc(p, vol, is_index=True)
    back = np.asarray(open_dense_mmap(p, is_index=True), np.float32)
    assert int(back.flat[0]) == C.PACKED_INDEX_MAX
