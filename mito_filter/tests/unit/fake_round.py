"""Test helper: build a tiny on-disk fake emClarity TM round (real MRC headers, stub siblings).

Used by the exec / datasets / cli unit tests so they run fully offline (no 559 MB real convmaps),
while still exercising the real header read + sibling / ``.path`` resolution in
:mod:`mito_filter.datasets.emclarity_tm`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Tuple

import mrcfile
import numpy as np

CORE_SIBLINGS: Tuple[str, ...] = (".pos", "_angles.list", ".mod")
"""Siblings written as inert stubs; ``.csv`` and ``.templateIDX`` get real content below."""


def _write_peak_csv(csv_path: Path, shape: Tuple[int, int, int]) -> int:
    """Write a minimal valid 26-column peak csv (+ sibling ``.templateIDX``); return the row count.

    A handful of peaks on in-bounds voxels of the tiny convmap, with an identity rotation
    (outward normal ``[0, 0, 1]``) so :func:`mito_filter.emclarity.csv_io.read_peaks` parses them
    and a real ``scan`` produces genuine per-hit verdicts on the fake round.
    """
    nz, ny, nx = shape
    # (x, y, z) voxels strictly inside the tiny volume.
    vox = np.array(
        [(1, 1, 1), (2, 2, 1), (min(3, nx - 1), min(3, ny - 1), min(2, nz - 1))],
        dtype=np.float64,
    )
    n = int(vox.shape[0])
    rows = np.zeros((n, 26), dtype=np.float64)
    rows[:, 0] = np.array([5.0, 6.0, 7.0])[:n]  # col1 CC score
    rows[:, 1] = 5  # col2 sampling rate
    rows[:, 3] = np.arange(1, n + 1)  # col4 subtomo id
    rows[:, 4:9] = 1  # cols5-9 const flags
    rows[:, 10] = 5.0 * vox[:, 0]  # col11 X full px
    rows[:, 11] = 5.0 * vox[:, 1]  # col12 Y full px
    rows[:, 12] = 5.0 * vox[:, 2]  # col13 Z full px
    rows[:, 16] = 1.0  # identity rotation matrix (column-major): M[0,0]
    rows[:, 20] = 1.0  # M[1,1]
    rows[:, 24] = 1.0  # M[2,2] == normal_z
    rows[:, 25] = 1  # col26 active
    np.savetxt(csv_path, rows, fmt="%.6g")
    csv_path.with_suffix(".templateIDX").write_text(
        "\n".join(str(int(i)) for i in np.arange(1, n + 1)) + "\n"
    )
    return n


def make_fake_round(
    root: Path,
    bases: Sequence[str],
    *,
    shape: Tuple[int, int, int] = (4, 5, 6),
    with_angles_mrc: bool = False,
    convmap_subdir: str = "convmap_wedgeType_2_bin5",
) -> Path:
    """Create a fake round directory tree and return its convmap directory.

    Args:
        root: The round directory (the convmap dir's parent; ``fixedStacks/ctf`` also lands here).
        bases: The tomogram basenames (e.g. ``"H99_2_100_1_bin5"``).
        shape: The tiny convmap shape ``(nz, ny, nx)`` written into each MRC header.
        with_angles_mrc: If True, also write a ``<base>_angles.mrc`` (mode-2) per base.
        convmap_subdir: Name of the convmap subdirectory under ``root``.

    Returns:
        The convmap directory path (``root/<convmap_subdir>``).
    """
    convdir = root / convmap_subdir
    convdir.mkdir(parents=True, exist_ok=True)
    ctf_dir = root / "fixedStacks" / "ctf"
    ctf_dir.mkdir(parents=True, exist_ok=True)
    vol = np.zeros(shape, dtype=np.float32)
    for b in bases:
        with mrcfile.new(str(convdir / f"{b}_convmap.mrc"), overwrite=True) as m:
            m.set_data(vol)
        for suf in CORE_SIBLINGS:
            (convdir / f"{b}{suf}").write_text("stub\n")
        _write_peak_csv(convdir / f"{b}.csv", shape)
        (convdir / f"{b}.path").write_text(f"{b},./cache,.rec,fixedStacks/ctf/{b}_ali1_ctf.tlt")
        (ctf_dir / f"{b}_ali1_ctf.tlt").write_text("tilt\n")
        if with_angles_mrc:
            with mrcfile.new(str(convdir / f"{b}_angles.mrc"), overwrite=True) as m:
                m.set_data(vol)
    return convdir
