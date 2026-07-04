"""Read/write the 26-column emClarity peak csv (SPEC §2), quarantined here.

Reading yields a core :class:`~mito_filter.core.points.PointCloud` in the package's
``(z, y, x)`` voxel frame: positions cols 11-13 are FULL-tomo (bin1) px, so they are
**divided by SAMPLING_RATE** to reach the convmap-voxel frame and **reversed** from the raw
``(x, y, z)`` to ``(z, y, x)`` (proven: indexing the convmap at these coords lands on a local
max). The outward normal (cols 23-25, C12-invariant) is likewise reversed to ``(z, y, x)`` so
positions and normals share one axis order. The raw ``(x, y, z)`` convention stays in
``conventions.py``.

Writing only rewrites col26 (the active flag) preserving row order — a debug/mirror artifact;
the authoritative removal sink is the subTomoMeta ``.mat`` (``matio.py``, SPEC §9.1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
from numpy.typing import NDArray

from ..core.points import PointCloud
from .constants import (
    ACTIVE_COL,
    EULER_COLS,
    N_CSV_COLS,
    NORMAL_COLS,
    POS_COLS,
    REMOVED_FLAG,
    SAMPLING_RATE,
    SCORE_COL,
    SUBTOMO_ID_COL,
)
from .templateidx import read_template_idx


def read_csv_matrix(path: Path) -> NDArray[np.float64]:
    """Read the raw 26-column csv into a float matrix (no reordering).

    Args:
        path: Path to ``<base>.csv``.

    Returns:
        Array ``(N, 26)`` of the raw csv values.

    Raises:
        ValueError: If the csv does not have :data:`N_CSV_COLS` columns.
    """
    arr = np.loadtxt(path, dtype=np.float64)
    arr = np.atleast_2d(arr)
    if arr.shape[1] != N_CSV_COLS:
        raise ValueError(f"{path}: expected {N_CSV_COLS} columns, got {arr.shape[1]}")
    return arr


def read_peaks(path: Path, *, load_template_idx: bool = True) -> PointCloud:
    """Read the peak csv into a :class:`PointCloud` (``(z, y, x)`` voxel frame).

    Attributes attached:

    - ``cc``: score (col 1) — the convmap value at the peak.
    - ``normal``: outward normal ``(N, 3)`` in ``(z, y, x)`` (reversed cols 23-25).
    - ``euler``: raw ``[phi, theta, psi−phi]`` degrees ``(N, 3)`` (cols 14-16), for the
      ``matio`` angle-triple cross-check.
    - ``subtomo_id``: per-tomo peak id (col 4), int64.
    - ``active``: bool, ``col26 != REMOVED_FLAG`` (all True in raw TM output).
    - ``row_id``: 0-based csv row index (stable key aligning every sibling file).
    - ``template_idx``: winning template id from the sibling ``.templateIDX`` (if present).

    Args:
        path: Path to ``<base>.csv``.
        load_template_idx: If True, attach ``template_idx`` from ``<base>.templateIDX`` when
            that sibling exists.

    Returns:
        A :class:`PointCloud` with positions in ``(z, y, x)`` convmap voxels.
    """
    a = read_csv_matrix(path)
    n = a.shape[0]
    pos_xyz = a[:, list(POS_COLS)] / SAMPLING_RATE  # (x, y, z) voxel frame
    xyz_zyx = np.ascontiguousarray(pos_xyz[:, ::-1])  # -> (z, y, x)
    normal_zyx = np.ascontiguousarray(a[:, list(NORMAL_COLS)][:, ::-1])  # (x,y,z)->(z,y,x)
    attrs: Dict[str, NDArray[np.generic]] = {
        "cc": a[:, SCORE_COL].astype(np.float64),
        "normal": normal_zyx,
        "euler": np.ascontiguousarray(a[:, list(EULER_COLS)]),
        "subtomo_id": a[:, SUBTOMO_ID_COL].astype(np.int64),
        "active": a[:, ACTIVE_COL] != REMOVED_FLAG,
        "row_id": np.arange(n, dtype=np.int64),
    }
    if load_template_idx:
        tpath = path.with_suffix(".templateIDX")
        if tpath.exists():
            tidx = read_template_idx(tpath)
            if tidx.shape[0] == n:
                attrs["template_idx"] = tidx
    return PointCloud(xyz_zyx, attrs)


def write_active_column(
    src_csv: Path,
    active_flags: NDArray[np.generic],
    dst_csv: Optional[Path] = None,
) -> Path:
    """Rewrite col26 (the active flag) of a csv, preserving exact row order (SPEC §2, §9.1).

    Only column 26 is changed; every other column's textual token is copied verbatim (values
    unchanged). ``active_flags`` may be booleans (``True``->1, ``False``->``REMOVED_FLAG``) or
    the integer flags ``{1, REMOVED_FLAG}`` directly.

    Args:
        src_csv: Source ``<base>.csv``.
        active_flags: Length-``N`` array of booleans or ``{1, REMOVED_FLAG}`` ints, aligned to
            csv rows (row order == read order).
        dst_csv: Destination path (defaults to overwriting ``src_csv``).

    Returns:
        The written path.

    Raises:
        ValueError: If ``active_flags`` length does not match the csv row count, or a row does
            not have :data:`N_CSV_COLS` columns.
    """
    lines = [ln for ln in src_csv.read_text().splitlines() if ln.strip()]
    flags = np.asarray(active_flags)
    if flags.shape[0] != len(lines):
        raise ValueError(f"active_flags length {flags.shape[0]} != csv rows {len(lines)}")
    if flags.dtype == bool:
        ints = np.where(flags, 1, REMOVED_FLAG)
    else:
        ints = flags.astype(np.int64)
    out_lines = []
    for line, flag in zip(lines, ints):
        toks = line.split()
        if len(toks) != N_CSV_COLS:
            raise ValueError(f"{src_csv}: row has {len(toks)} columns, expected {N_CSV_COLS}")
        toks[ACTIVE_COL] = str(int(flag))
        out_lines.append(" ".join(toks))
    out = dst_csv if dst_csv is not None else src_csv
    out.write_text("\n".join(out_lines) + "\n")
    return out
