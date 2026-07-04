"""Golden-value tests for the emClarity convention adapter against the REAL dev-set files.

Locks (SPEC §2-§5) using ``H99_2_100_1_bin5``:

- cols 17-25 column-major -> orthonormal, det +1 (``|M Mᵀ − I| ~ 1e-6``);
- matrix col 3 == ``normal_from_euler`` (~1e-6) == ``normal_from_matrix``;
- ``decode_packed_index`` round-trips, and the angles.list-decoded normal matches the csv (~6.4e-5);
- csv positions / 5 == ``.pos`` (~1e-6);
- a csv peak, mapped to the ``(z, y, x)`` voxel frame, lands on a convmap local max.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mito_filter.emclarity import constants as C
from mito_filter.emclarity.angles_list import normal_for_angle_idx, read_angles_list
from mito_filter.emclarity.conventions import (
    decode_packed_index,
    matrix_from_row,
    normal_from_euler,
    normal_from_matrix,
)
from mito_filter.emclarity.csv_io import read_csv_matrix, read_peaks
from mito_filter.emclarity.mrc_io import open_dense_mmap
from mito_filter.emclarity.templateidx import read_pos, read_template_idx


def _base(csv_path: Path) -> tuple[Path, str]:
    return csv_path.parent, csv_path.stem


def test_matrix_column_major_orthonormal(real_csv_path: Path) -> None:
    a = read_csv_matrix(real_csv_path)
    assert a.shape[1] == C.N_CSV_COLS
    for row in a[:50]:
        m = matrix_from_row(row)
        assert np.abs(m @ m.T - np.eye(3)).max() < 5e-6
        assert abs(np.linalg.det(m) - 1.0) < 5e-6
        # 3rd column == normal helpers (raw x,y,z order)
        assert np.allclose(m[:, 2], normal_from_matrix(row), atol=1e-12)
        n_eul = normal_from_euler(row[C.EULER_COLS[0]], row[C.EULER_COLS[1]])
        assert np.abs(m[:, 2] - n_eul).max() < 1e-5


def test_normal_from_euler_vectorized(real_csv_path: Path) -> None:
    a = read_csv_matrix(real_csv_path)
    phi = a[:50, C.EULER_COLS[0]]
    theta = a[:50, C.EULER_COLS[1]]
    n = normal_from_euler(phi, theta)
    assert n.shape == (50, 3)
    assert np.abs(n - a[:50][:, list(C.NORMAL_COLS)]).max() < 1e-5
    assert np.allclose(np.linalg.norm(n, axis=1), 1.0, atol=1e-9)


def test_decode_packed_index_roundtrip() -> None:
    # p = (angleIdx-1)*N_TEMPLATES + refIdx ; decode must invert it.
    for angle_idx in (1, 2, 288, 864):
        for ref_idx in range(1, C.N_TEMPLATES + 1):
            p = (angle_idx - 1) * C.N_TEMPLATES + ref_idx
            ai, ri = decode_packed_index(p)
            assert int(ai) == angle_idx and int(ri) == ref_idx
    # max packed index == PACKED_INDEX_MAX
    assert (864 - 1) * C.N_TEMPLATES + C.N_TEMPLATES == C.PACKED_INDEX_MAX
    # vectorized
    ps = np.array([1, 2, 3, 4, C.PACKED_INDEX_MAX])
    ai, ri = decode_packed_index(ps)
    assert list(ri) == [1, 2, 3, 1, 3]
    assert list(ai) == [1, 1, 1, 2, 864]


def test_angleslist_decoded_normal_matches_csv(real_csv_path: Path) -> None:
    parent, stem = _base(real_csv_path)
    al = read_angles_list(parent / f"{stem}_angles.list")
    assert al.shape == (C.N_ANGLES, 3)
    a = read_csv_matrix(real_csv_path)
    csv_eul = a[:50][:, list(C.EULER_COLS)]
    # match each csv euler to its angles.list row (they are exactly the grid, SPEC §5)
    matched = []
    for e in csv_eul:
        j = int(np.abs(al - e).sum(1).argmin())
        matched.append(j + 1)  # 1-based angle_idx
    n = normal_for_angle_idx(al, np.asarray(matched))
    # limited by the list's 2-decimal rounding -> SPEC's ~6.4e-5
    assert np.abs(n - a[:50][:, list(C.NORMAL_COLS)]).max() < 1e-4


def test_csv_positions_over_five_equals_pos(real_csv_path: Path) -> None:
    parent, stem = _base(real_csv_path)
    a = read_csv_matrix(real_csv_path)
    pos = read_pos(parent / f"{stem}.pos")
    # SPEC §3: csv cols 11-13 (bin1 px) / 5 == .pos (convmap voxel, raw x,y,z)
    assert np.abs(a[:, list(C.POS_COLS)] / C.SAMPLING_RATE - pos).max() < 1e-5


def test_read_peaks_pointcloud_frame_and_localmax(real_csv_path: Path) -> None:
    parent, stem = _base(real_csv_path)
    pc = read_peaks(real_csv_path)
    a = read_csv_matrix(real_csv_path)
    assert pc.n == a.shape[0]
    # positions are (z, y, x): reverse of pos(x, y, z); csv/5 vs .pos differ ~6e-7 (SPEC §3)
    pos = read_pos(parent / f"{stem}.pos")
    assert np.abs(pc.xyz - pos[:, ::-1]).max() < 1e-5
    # normals are unit and reversed-consistent with raw cols 23-25
    nrm = pc.get("normal")
    assert np.allclose(np.linalg.norm(nrm, axis=1), 1.0, atol=1e-6)
    assert np.abs(nrm - a[:, list(C.NORMAL_COLS)][:, ::-1]).max() < 1e-12
    # template_idx attached from the sibling and matches
    assert np.array_equal(pc.get("template_idx"), read_template_idx(parent / f"{stem}.templateIDX"))
    # a mapped peak lands on a convmap local max (±1 neighborhood, SPEC §3)
    mm = open_dense_mmap(parent / f"{stem}_convmap.mrc", expected_shape=C.CONVMAP_SHAPE)
    cc = pc.get("cc")
    order = np.argsort(cc)[::-1][:15]
    for i in order:
        z, y, x = np.round(pc.xyz[i]).astype(int)
        nb = np.asarray(mm[z - 1 : z + 2, y - 1 : y + 2, x - 1 : x + 2], np.float32)
        assert abs(float(nb.max()) - float(cc[i])) < 0.02


def test_normal_c12_invariance_note(real_csv_path: Path) -> None:
    # cols 23-25 (normal) are C12-invariant; the FULL matrix is scrambled by the per-peak mate.
    # Sanity: normal has unit length regardless, and equals the analytic euler normal.
    a = read_csv_matrix(real_csv_path)
    row = a[0]
    n = normal_from_matrix(row)
    assert abs(np.linalg.norm(n) - 1.0) < 1e-6
    # row1 theta == 72 deg -> cos(72) == col25 exactly (SPEC §4)
    assert abs(np.cos(np.radians(row[C.EULER_COLS[1]])) - row[C.NORMAL_COLS[2]]) < 1e-5
