"""Verified emClarity template-matching (TM) constants (quarantined conventions).

Every value here is cross-checked against ``docs/SPEC.md`` and, where marked, verified
empirically against the real dev-set files under
``/scratch/siracusa/full_enchilada_3/six_hours_round_4/convmap_wedgeType_2_bin5``.

This is the single home for the fragile convention numbers; ``core/`` never imports them.
The column-index constants are **0-indexed** (ready for ``numpy`` array access
``A[:, COL]``); each carries its 1-indexed SPEC column number in the comment for
cross-reference with ``docs/SPEC.md`` §2.
"""

from __future__ import annotations

from typing import Final, Tuple

# --- Search / template geometry (SPEC §1, §9) --------------------------------

N_TEMPLATES: Final[int] = 3
"""Number of references in the multi-reference search (SPEC §1, §9). VS+VE."""

N_ANGLES: Final[int] = 864
"""Number of sampled orientations in ``_angles.list`` (SPEC §2, Tmp_angleSearch). VS+VE."""

SAMPLING_RATE: Final[int] = 5
"""``Tmp_samplingRate`` — bin factor from full-tomo (bin1) px to convmap voxels. VS+VE."""

APIX_A: Final[float] = 12.5
"""True convmap voxel size in Angstrom (2.5 A x samplingRate 5). Header's 1.0 is cosmetic. VS+VE."""

# --- Dense convmap (SPEC §1) -------------------------------------------------

CONVMAP_SHAPE: Final[Tuple[int, int, int]] = (448, 942, 662)
"""Convmap volume shape ``(nz, ny, nx)`` in C / numpy order (x fastest). MRC mode 12 fp16. VE."""

CONVMAP_MODE: Final[int] = 12
"""MRC mode of the convmap: 12 == float16. VE."""

CONVMAP_BYTES: Final[int] = 558_750_208
"""Exact convmap file size: 279,374,592 vox x 2 B + 1024 B header. VE."""

# --- Per-tomo background statistics (SPEC §1; H99_2_100 subsample) -----------

BACKGROUND_MEAN: Final[float] = 3.28
"""Convmap background mode mean ~ N(3.28, 0.48). Drifts per tomo; calibrate. VE."""

BACKGROUND_STD: Final[float] = 0.48
"""Convmap background mode std. VE."""

# --- Peak-erase geometry (SPEC §6) ------------------------------------------

ERASE_RADIUS_A: Final[Tuple[int, int, int]] = (210, 210, 320)
"""``Peak_mRadius`` in Angstrom (x, y, z); bin5 ~ [16, 16, 26] vox oriented cylinder. VS+VE."""

PARTICLE_RADIUS_A: Final[Tuple[int, int, int]] = (180, 180, 150)
"""``particleRadius`` in Angstrom (x, y, z) (SPEC §9). VE."""

# --- CSV layout (SPEC §2) ----------------------------------------------------
# 0-indexed column positions into the 26-column peak csv. 1-indexed SPEC column
# in each comment. cols 17-25 (1-idx) are a COLUMN-MAJOR 3x3 rotation matrix.

N_CSV_COLS: Final[int] = 26
"""Number of columns in the peak csv (SPEC §2). VE."""

SCORE_COL: Final[int] = 0
"""CC score = convmap value at the peak argmax voxel. SPEC col 1. VS+VE."""

SUBTOMO_ID_COL: Final[int] = 3
"""Per-tomo peak id (reassigned to a global id at init). SPEC col 4. VS+VE."""

POS_COLS: Final[Tuple[int, int, int]] = (10, 11, 12)
"""Peak X, Y, Z in FULL-tomo (bin1) px. SPEC cols 11-13. /SAMPLING_RATE -> voxel frame. VS+VE."""

EULER_COLS: Final[Tuple[int, int, int]] = (13, 14, 15)
"""Euler ``[phi, theta, psi-phi]`` in degrees (winning orientation). SPEC cols 14-16. VS+VE."""

ROTMAT_COLS: Final[Tuple[int, ...]] = (16, 17, 18, 19, 20, 21, 22, 23, 24)
"""3x3 rotation matrix, COLUMN-MAJOR. SPEC cols 17-25. Reshape order='F'. VS+VE."""

NORMAL_COLS: Final[Tuple[int, int, int]] = (22, 23, 24)
"""Outward normal = 3rd column of the rotation matrix. SPEC cols 23-25. C12-invariant. VS+VE."""

ACTIVE_COL: Final[int] = 25
"""Active flag (all raw rows == 1; set to REMOVED_FLAG downstream). SPEC col 26. VS+VE."""

REMOVED_FLAG: Final[int] = -9999
"""Sentinel value marking a removed / inactive peak in col26 / geometry. VS+VE."""

# --- Packed dense-index decode (SPEC §5) ------------------------------------

PACKED_INDEX_MAX: Final[int] = N_ANGLES * N_TEMPLATES  # 2592
"""Max packed argmax index = N_ANGLES * N_TEMPLATES = 2592. Exceeds fp16 integer-exact
limit (2048) -> a dense IndexField MUST be stored fp32/int16, never mode-12. SPEC §5, §7."""

FP16_INT_EXACT_MAX: Final[int] = 2048
"""Largest integer float16 represents exactly. Indices above this corrupt in mode-12. SPEC §7."""
