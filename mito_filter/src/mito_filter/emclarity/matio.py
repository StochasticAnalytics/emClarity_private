"""Authoritative removal sink: the subTomoMeta ``.mat`` (SPEC §9.1), quarantined here.

emClarity writes ``-9999`` into the ``.mat`` geometry (col26) at classification and **never
back into the raw csv**, so a csv col26 write is debug-only. This module is the real sink: it
emits a **per-tomo** removal list scoped to one tomogram and keyed by the csv/geometry **row
index** (csv row ``k`` == subTomoMeta geometry row ``k``), with the euler **angle triple** as a
cross-check, and renders a **MATLAB-on-salina** apply step that sets col26 = ``-9999``.

**Why row index, not col4 (the bug this module used to have):** the csv col4 peak id is a
per-tomo ``1..N`` id **reset per tomo**, but the ``.mat`` col4 is a **global** unique id assigned
at init — so a ``g(:,4) == csv_col4`` match targets the wrong id space and silently mis-hits.
The apply therefore scopes to a single tomo's geometry (``G.(tomo)``) and keys by row index. That
is valid only because col9 is constant in this TM output (emClarity's ``sortrows`` on it is a
stable no-op, preserving row order); the rendered script **asserts** col9 is constant so a future
non-constant col9 (which would permute the ``.mat``) fails loudly instead of mis-applying.

Why not scipy: ``scipy.io.loadmat`` **fails the zlib CRC** on the ~480 MB v7 ``.mat`` (SPEC
§10), so the actual apply must run under MATLAB on salina (where the license lives). The
apply here is a **documented, un-executed stub** — it renders the script/command; it does not
run MATLAB. Keys are row index / angle, **never position** (positions drift across cycles,
SPEC §3, §10).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
from numpy.typing import NDArray

from ..core.points import PointCloud
from .constants import REMOVED_FLAG

SCIPY_LOADMAT_UNSUPPORTED: str = (
    "scipy.io.loadmat fails the zlib CRC on the v7 subTomoMeta .mat (SPEC §10); "
    "apply removals via MATLAB on salina, per-tomo, keyed by row index / angle triple, "
    "never position"
)

_REMOVAL_HEADER: str = (
    "# row_index subtomo_id phi theta psi_minus_phi  "
    "(key=row_index[1-based]; angle=cross-check; subtomo_id=per-tomo provenance, NOT the key)"
)


@dataclass(frozen=True)
class RemovalList:
    """A per-tomo set of hits to mark removed, scoped to one tomo and keyed by ROW INDEX.

    The apply scopes to a **single** tomogram's geometry (``tomo`` == the ``.mat`` geometry
    struct field name) and keys by the csv/geometry **row index** (csv row ``k`` == geometry row
    ``k``), with the euler triple as a cross-check. It deliberately does **not** key on the csv
    col4 id: that is a per-tomo ``1..N`` id reset per tomo, whereas the ``.mat`` col4 is a global
    id assigned at init, so a col4==col4 match targets the wrong id space. Positions are never
    used (they drift across cycles).

    Args:
        subtomo_ids: Per-tomo csv col4 peak ids of the removed hits, shape ``(M,)`` —
            provenance/cross-reference only, **NOT** the ``.mat`` match key.
        euler: Matching euler triples ``[phi, theta, psi−phi]`` degrees, shape ``(M, 3)`` — the
            angle cross-check.
        row_ids: 0-based csv row indices of the removed hits, shape ``(M,)`` == geometry row
            indices; **the key**.
        tomo: The tomogram basename == the geometry struct field name (single tomo).
        dataset: subTomoMeta project label (e.g. ``full_enchilada_3_4``).
        source: Free-form provenance (e.g. ``"scan:round_4"``).

    Attributes:
        subtomo_ids: The per-tomo cross-reference ids.
        euler: The cross-check angle triples.
        row_ids: The 0-based row-index keys.
        tomo: The tomogram / geometry field name.
        dataset: Project label.
        source: Provenance string.
    """

    subtomo_ids: NDArray[np.int64]
    euler: NDArray[np.float64]
    row_ids: NDArray[np.int64]
    tomo: str = ""
    dataset: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        ids = np.asarray(self.subtomo_ids, dtype=np.int64).reshape(-1)
        eul = (
            np.atleast_2d(np.asarray(self.euler, dtype=np.float64))
            if ids.shape[0]
            else (np.zeros((0, 3), dtype=np.float64))
        )
        rows = np.asarray(self.row_ids, dtype=np.int64).reshape(-1)
        if eul.shape != (ids.shape[0], 3):
            raise ValueError(f"euler {eul.shape} incompatible with {ids.shape[0]} ids")
        if rows.shape[0] != ids.shape[0]:
            raise ValueError(f"row_ids {rows.shape[0]} incompatible with {ids.shape[0]} ids")
        object.__setattr__(self, "subtomo_ids", ids)
        object.__setattr__(self, "euler", eul)
        object.__setattr__(self, "row_ids", rows)

    @property
    def n(self) -> int:
        """Number of removals."""
        return int(self.subtomo_ids.shape[0])


def build_removal_list(
    points: PointCloud, *, tomo: str = "", dataset: str = "", source: str = "scan"
) -> RemovalList:
    """Build a :class:`RemovalList` from the inactive points of a :class:`PointCloud`.

    Selects points whose ``"active"`` attr is False and keys them by ``"row_id"`` (scoped to
    ``tomo``) with the ``"euler"`` triple as a cross-check; ``"subtomo_id"`` is carried as
    per-tomo provenance only. Requires those attrs (populated by
    :func:`~mito_filter.emclarity.csv_io.read_peaks`).

    Args:
        points: The scored/decided candidate cloud.
        tomo: The tomogram basename (the geometry struct field the apply scopes to).
        dataset: subTomoMeta project label.
        source: Provenance string.

    Returns:
        The :class:`RemovalList` (empty if nothing is inactive).

    Raises:
        KeyError: If ``points`` lacks ``subtomo_id``, ``euler``, ``row_id``, or ``active`` attrs.
    """
    active = np.asarray(points.get("active")).astype(bool)
    remove = ~active
    ids = np.asarray(points.get("subtomo_id"), dtype=np.int64)[remove]
    eul = np.asarray(points.get("euler"), dtype=np.float64)[remove]
    rows = np.asarray(points.get("row_id"), dtype=np.int64)[remove]
    return RemovalList(ids, eul, rows, tomo=tomo, dataset=dataset, source=source)


def write_removal_list(path: Path, removals: RemovalList) -> Path:
    """Write a removal list to a headered text table (subtomo_id + angle triple).

    Args:
        path: Destination path.
        removals: The list to serialize.

    Returns:
        The written path.
    """
    lines: List[str] = [
        _REMOVAL_HEADER,
        f"# dataset={removals.dataset} source={removals.source} "
        f"tomo={removals.tomo} n={removals.n}",
    ]
    for row, sid, (phi, theta, psi) in zip(removals.row_ids, removals.subtomo_ids, removals.euler):
        # row+1: 1-based row index for MATLAB (1-based geometry rows).
        lines.append(f"{int(row) + 1} {int(sid)} {phi:.6g} {theta:.6g} {psi:.6g}")
    path.write_text("\n".join(lines) + "\n")
    return path


def read_removal_list(path: Path) -> RemovalList:
    """Read a removal list written by :func:`write_removal_list`.

    Args:
        path: Path to the removal-list file.

    Returns:
        The parsed :class:`RemovalList` (dataset/source recovered from the ``#`` metadata line
        when present).
    """
    dataset = ""
    source = ""
    tomo = ""
    rows: List[int] = []
    ids: List[int] = []
    eul: List[List[float]] = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            for tok in s.lstrip("#").split():
                if tok.startswith("dataset="):
                    dataset = tok.split("=", 1)[1]
                elif tok.startswith("source="):
                    source = tok.split("=", 1)[1]
                elif tok.startswith("tomo="):
                    tomo = tok.split("=", 1)[1]
            continue
        parts = s.split()
        rows.append(int(parts[0]) - 1)  # back to 0-based
        ids.append(int(parts[1]))
        eul.append([float(parts[2]), float(parts[3]), float(parts[4])])
    return RemovalList(
        np.asarray(ids, dtype=np.int64),
        np.asarray(eul, dtype=np.float64).reshape(-1, 3),
        np.asarray(rows, dtype=np.int64),
        tomo=tomo,
        dataset=dataset,
        source=source,
    )


def render_matlab_apply_script(
    mat_path: Path,
    removal_path: Path,
    *,
    tomo: str,
    cycle: int,
    angle_tol_deg: float = 1.0,
    subtomometa_var: str = "subTomoMeta",
) -> str:
    """Render the MATLAB-on-salina apply script (SPEC §9.1) — a documented, un-executed stub.

    The script loads the v7 ``.mat`` under MATLAB (scipy cannot — see
    :data:`SCIPY_LOADMAT_UNSUPPORTED`), scopes to **this tomo's** geometry
    (``subTomoMeta.cycleNNN.RawAlign.(tomo)``), and for each removal edits the geometry row **by
    row index** (col4 is a per-tomo id in the csv but a global id in the ``.mat`` — matching it
    would target the wrong id space) with an **angle-triple cross-check** (cols 14-16 within
    ``angle_tol_deg``), then sets col26 = ``-9999``. Row-index keying is valid only while col9 is
    constant (emClarity's ``sortrows`` on it is a stable no-op); the script **asserts** that so a
    permuted geometry fails loudly. It is returned as text for review; nothing here runs MATLAB.

    Args:
        mat_path: Path to the subTomoMeta ``.mat`` on salina.
        removal_path: Path to the :func:`write_removal_list` file.
        tomo: The tomogram basename == the geometry struct field name to scope to.
        cycle: The classification cycle number whose geometry is edited.
        angle_tol_deg: Max per-angle degree deviation for the cross-check.
        subtomometa_var: The struct variable name in the ``.mat``.

    Returns:
        A MATLAB script (string).
    """
    cyc = f"cycle{cycle:03d}"
    return f"""% AUTO-GENERATED apply stub (mito_filter.emclarity.matio) -- REVIEW before running.
% Run on salina under MATLAB: {SCIPY_LOADMAT_UNSUPPORTED}
R = readmatrix('{removal_path}', 'FileType', 'text', 'CommentStyle', '#');
rows = R(:,1); ids = R(:,2); ang = R(:,3:5);   % key = 1-based ROW INDEX; cross-check = angle triple
S = load('{mat_path}'); {subtomometa_var} = S.{subtomometa_var};
g = {subtomometa_var}.{cyc}.RawAlign.('{tomo}');   % SCOPED to this tomo's geometry
tol = {angle_tol_deg};
% Row-index keying requires geometry row order == csv row order. col9 is constant in this TM
% output so emClarity's sortrows on it is a stable no-op; assert it (a non-constant col9 would
% permute the .mat and silently break row-index keying).
assert(all(g(:,9) == g(1,9)), 'col9 not constant for {tomo}: row order may differ; keying unsafe');
nApplied = 0;
for k = 1:numel(rows)
    r = rows(k);                                          % 1-based geometry row == csv row
    if r >= 1 && r <= size(g,1) && all(abs(g(r,14:16) - ang(k,:)) <= tol)   % angle cross-check
        g(r,26) = {REMOVED_FLAG};
        nApplied = nApplied + 1;
    end
end
{subtomometa_var}.{cyc}.RawAlign.('{tomo}') = g;
fprintf('applied %d / %d removals to %s\\n', nApplied, numel(rows), '{tomo}');
% save('-v7', '{mat_path}', '{subtomometa_var}');   % uncomment to write back
"""


def render_salina_apply_command(
    mat_path: Path, removal_path: Path, *, cycle: int, script_path: Path
) -> str:
    """Render the shell command to run the apply script on salina (documented stub).

    Args:
        mat_path: subTomoMeta ``.mat`` path.
        removal_path: Removal-list path.
        cycle: Classification cycle number.
        script_path: Where the rendered ``.m`` script is written.

    Returns:
        A shell command string (not executed here). Write the script via
        :func:`render_matlab_apply_script` to ``script_path`` first.
    """
    stem = script_path.stem
    return (
        f'ssh salina "cd {script_path.parent} && '
        f"matlab -nodisplay -nosplash -batch '{stem}'\"  "
        f"# applies {removal_path} to {mat_path} (cycle {cycle:03d})"
    )
