"""Derived field providers: cheap transforms of already-materialised fields (DESIGN §5).

The ``DERIVE`` tier. Each provider resolves its ``requires`` through the registry and computes a
new dense field from them on the CPU (numpy/scipy) — importing this module never needs torch or
cupy. All compute is host-side on the field arrays (which are mmap-backed), so GPU acceleration
is a transparent later swap, not a correctness prerequisite.

Providers:

* :class:`SnrFieldProvider` (``snr``) — ``cc / sqrt(noise_variance)`` when the noise-variance
  re-run is present, else a per-tomo :class:`~mito_filter.fields.calibrate.BackgroundModel`
  z-score of ``cc`` (DESIGN §9.2). Makes absolute thresholds portable.
* :class:`NormalFieldProvider` (``normal``) — decode the packed ``angle`` index volume to a
  per-voxel outward-normal :class:`VectorField` (SPEC §5). Requires ``angle`` (Phase B).
* :class:`ClusterDensityProvider` (``cc_cluster``) — local density of thresholded high-CC voxels
  (the gold/ice compact-cluster signature, SPEC §1) via a top-hat / Gaussian convolution.
* :class:`BlobnessProvider` (``blobness``) — a Laplacian-of-Gaussian (or optional skimage Frangi)
  blob response on ``cc`` (compact extreme-CC clusters = gold/ice).
* :class:`MembraneDistanceProvider` (``membrane_sdf``) — signed EDT of a membrane segmentation
  (negative inside). Segments membrane sheets straight from the ``rec`` tomogram by Hessian
  sheetness (:func:`membrane_segmentation`) when no on-disk trace exists, so it is ``GENERATABLE``
  on the real data (Phase C); an on-disk boolean-mask sibling wins if present.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage as ndi

from ..core.backend import Device
from ..core.field import Block, DenseField, VectorField
from ..emclarity.conventions import decode_index_volume_to_normal
from . import _tomo
from .calibrate import BackgroundModel
from .provider import (
    DERIVE,
    Availability,
    Cost,
    FieldProvider,
    FieldRegistry,
    FieldSpec,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..datasets.base import TomogramRef


def whole_array(field: DenseField) -> NDArray[np.float32]:
    """Read a field's entire volume as fp32 ``(nz, ny, nx[, C])`` (via one halo-free block).

    Args:
        field: The dense field to read.

    Returns:
        The full volume as a contiguous fp32 array.
    """
    nz, ny, nx = field.grid.shape
    return np.asarray(field.block(Block((0, nz), (0, ny), (0, nx))), dtype=np.float32)


class SnrFieldProvider(FieldProvider):
    """Derive ``snr``: calibrated SNR from noise-variance, else a background z-score (DESIGN §9.2).

    Args:
        method: Background estimator for the fallback z-score (``"mad"`` / ``"truncated"``).
        max_samples: Sample cap for the background fit.
        cache_dir: If set, the derived field is content-addressed cached here.
    """

    produces = FieldSpec(
        name="snr",
        channels=1,
        dtype=np.dtype(np.float32),
        semantics="cc/sqrt(noise_variance) if present, else per-tomo background z-score (§9.2)",
    )
    requires = ("cc",)

    def __init__(
        self,
        *,
        method: str = "mad",
        max_samples: int = 2_000_000,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.method = method
        self.max_samples = int(max_samples)
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.last_calibration: dict[str, object] = {}

    def available(self, tomo: "TomogramRef") -> Availability:
        return Availability.GENERATABLE

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        cc = reg.resolve("cc", tomo, device=device)
        nv = reg.try_resolve("noise_variance", tomo, device=device)
        cc_arr = whole_array(cc)
        meta: dict[str, object] = {}
        if nv is not None:
            nv_arr = whole_array(nv)
            denom = np.sqrt(np.clip(nv_arr, 1e-12, None))
            snr = (cc_arr / denom).astype(np.float32)
            meta["mode"] = "noise_variance"
        else:
            model = BackgroundModel(self.method, max_samples=self.max_samples)
            stats = model.fit_field(cc)
            snr = stats.zscore(cc_arr)
            meta["mode"] = "zscore"
            meta.update(stats.to_dict())
        field = DenseField.from_array(self.produces.name, cc.grid, snr, channels=1, provider=self)
        # Stash calibration provenance where a caller can pick it up (FittedConfig, §9.2).
        self.last_calibration = meta
        return field

    def cache_path(self, tomo: "TomogramRef") -> Optional[Path]:
        if self._cache_dir is None:
            return None
        return self._cache_dir / _tomo.base_of(tomo) / "snr.mrc"

    def cache_key_inputs(self, tomo: "TomogramRef") -> Sequence[Path]:
        paths = [_tomo.convmap_path_of(tomo)]
        nv = _tomo.sibling(tomo, "_noise_variance.mrc")
        if nv.exists():
            paths.append(nv)
        return paths

    def cost_hint(self) -> Cost:
        return DERIVE


class NormalFieldProvider(FieldProvider):
    """Derive ``normal``: decode the packed ``angle`` index volume to outward normals (SPEC §5).

    The dense field stores the raw argmax, so no C12 symmetry correction is applied. Normals are
    returned in the package ``(z, y, x)`` voxel frame to match the csv normal (which
    ``csv_io`` likewise reverses), so a dense normal at a peak matches csv cols 23-25.

    Note:
        Dense background normals are argmax-of-noise (SPEC §9.3); CC-gating / gold-halo masking
        is applied at feature-extraction time, not baked into this raw field.
    """

    produces = FieldSpec(
        name="normal",
        channels=3,
        dtype=np.dtype(np.float32),
        semantics="per-voxel outward membrane normal (z,y,x) from the packed angle index (§5)",
    )
    requires = ("angle",)

    def available(self, tomo: "TomogramRef") -> Availability:
        return Availability.GENERATABLE

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        from ..emclarity.angles_list import read_angles_list

        angle = reg.resolve("angle", tomo, device=device)
        packed = np.rint(whole_array(angle)).astype(np.int64)
        angles = read_angles_list(_tomo.sibling(tomo, "_angles.list"))
        normal_xyz = decode_index_volume_to_normal(packed, angles)  # (...,3) raw (x,y,z)
        normal_zyx = np.ascontiguousarray(normal_xyz[..., ::-1], dtype=np.float32)
        return VectorField(self.produces.name, angle.grid, normal_zyx, channels=3, provider=self)

    def cost_hint(self) -> Cost:
        return DERIVE


class ClusterDensityProvider(FieldProvider):
    """Derive ``cc_cluster``: local density of thresholded extreme-CC voxels (gold/ice, SPEC §1).

    Thresholds ``cc`` (absolute or percentile) into a high-CC mask, then convolves with a top-hat
    sphere (or a Gaussian) of physical radius ``radius_A`` — a compact cluster of extreme CC
    (gold/ice) produces a strong local density, an isolated true hit does not.

    Args:
        thr: Absolute CC threshold; if None, :attr:`thr_percentile` of the field is used.
        thr_percentile: Percentile threshold when :attr:`thr` is None (default 99.0).
        radius_A: Convolution radius in Angstrom (default 250).
        mode: ``"tophat"`` (mean over a sphere) or ``"gaussian"``.
        cache_dir: If set, content-addressed cache directory.
    """

    produces = FieldSpec(
        name="cc_cluster",
        channels=1,
        dtype=np.dtype(np.float32),
        semantics="local fraction of high-CC voxels in a radius (gold/ice cluster density)",
    )
    requires = ("cc",)

    def __init__(
        self,
        *,
        thr: Optional[float] = None,
        thr_percentile: float = 99.0,
        radius_A: float = 250.0,
        mode: str = "tophat",
        cache_dir: Optional[Path] = None,
    ) -> None:
        if mode not in ("tophat", "gaussian"):
            raise ValueError(f"mode must be 'tophat' or 'gaussian', got {mode!r}")
        self.thr = thr
        self.thr_percentile = float(thr_percentile)
        self.radius_A = float(radius_A)
        self.mode = mode
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.last_threshold: float = 0.0

    def available(self, tomo: "TomogramRef") -> Availability:
        return Availability.GENERATABLE

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        cc = reg.resolve("cc", tomo, device=device)
        arr = whole_array(cc)
        thr = self.thr if self.thr is not None else float(np.percentile(arr, self.thr_percentile))
        mask = (arr >= thr).astype(np.float32)
        density = cluster_density(mask, radius_vox=self.radius_A / cc.grid.apix, mode=self.mode)
        field = DenseField.from_array(
            self.produces.name, cc.grid, density.astype(np.float32), channels=1, provider=self
        )
        self.last_threshold = thr
        return field

    def cache_path(self, tomo: "TomogramRef") -> Optional[Path]:
        if self._cache_dir is None:
            return None
        return self._cache_dir / _tomo.base_of(tomo) / "cc_cluster.mrc"

    def cache_key_inputs(self, tomo: "TomogramRef") -> Sequence[Path]:
        return [_tomo.convmap_path_of(tomo)]

    def cost_hint(self) -> Cost:
        return DERIVE


class BlobnessProvider(FieldProvider):
    """Derive ``blobness``: a blob response on ``cc`` (compact extreme-CC = gold/ice, SPEC §1).

    Default ``method="log"`` uses a negative Laplacian-of-Gaussian (a cheap, O(n) blob detector:
    compact bright blobs give a strong positive response). ``method="frangi"`` uses skimage's
    Hessian-eigenvalue Frangi filter if scikit-image is installed (heavier).

    Args:
        sigma_A: Gaussian scale in Angstrom (default 150, ~gold-bead scale at bin5).
        method: ``"log"`` (default) or ``"frangi"``.
        cache_dir: If set, content-addressed cache directory.
    """

    produces = FieldSpec(
        name="blobness",
        channels=1,
        dtype=np.dtype(np.float32),
        semantics="Laplacian-of-Gaussian / Frangi blob response on cc (gold/ice compactness)",
    )
    requires = ("cc",)

    def __init__(
        self,
        *,
        sigma_A: float = 150.0,
        method: str = "log",
        cache_dir: Optional[Path] = None,
    ) -> None:
        if method not in ("log", "frangi"):
            raise ValueError(f"method must be 'log' or 'frangi', got {method!r}")
        self.sigma_A = float(sigma_A)
        self.method = method
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None

    def available(self, tomo: "TomogramRef") -> Availability:
        return Availability.GENERATABLE

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        cc = reg.resolve("cc", tomo, device=device)
        arr = whole_array(cc)
        sigma_vox = self.sigma_A / cc.grid.apix
        blob = blobness(arr, sigma_vox=sigma_vox, method=self.method)
        field = DenseField.from_array(
            self.produces.name, cc.grid, blob.astype(np.float32), channels=1, provider=self
        )
        return field

    def cache_path(self, tomo: "TomogramRef") -> Optional[Path]:
        if self._cache_dir is None:
            return None
        return self._cache_dir / _tomo.base_of(tomo) / "blobness.mrc"

    def cache_key_inputs(self, tomo: "TomogramRef") -> Sequence[Path]:
        return [_tomo.convmap_path_of(tomo)]

    def cost_hint(self) -> Cost:
        return DERIVE


class MembraneDistanceProvider(FieldProvider):
    """Produce ``membrane_sdf``: signed EDT of a membrane segmentation, negative inside (DESIGN §5).

    Two sources, in priority order:

    1. **On-disk segmentation** — if ``segmentation_suffix`` points at an existing boolean membrane
       MRC sibling of the convmap (e.g. a biologist's trace rasterised to a mask), that is used
       verbatim.
    2. **Derived from ``rec``** (default) — when ``from_rec`` and no seg file exists, the membrane
       is segmented directly from the tomogram reconstruction by :func:`membrane_segmentation`
       (Hessian sheetness of the ``rec`` density → bright bilayer sheets), so no separate membrane
       search or manual trace is required. This is the Phase-C path that makes ``membrane_sdf``
       ``GENERATABLE`` on the real data today.

    The result is the signed Euclidean distance transform (negative inside a closed membrane,
    positive outside), in voxels — the field the membrane features (``membrane_dist``,
    ``inside_sign``, ``closed_shell``) sample.

    Args:
        segmentation_suffix: Sibling suffix of a boolean membrane-segmentation MRC (e.g.
            ``"_membrane.mrc"``). If it exists it wins; else the ``rec`` path is used.
        from_rec: If True (default), derive the segmentation from the ``rec`` field when no seg
            file is present. If False, availability is ``MISSING`` without a seg file.
        sigma_vox: Membraneness Gaussian scale (voxels) for the ``rec`` derivation.
        percentile: Membraneness percentile threshold for the ``rec`` derivation.
        bright: Keep bright density ridges (the membrane material) when deriving from ``rec``.
        min_component_vox: Drop membrane components smaller than this when deriving from ``rec``.
        cache_dir: If set, content-addressed cache directory.
    """

    produces = FieldSpec(
        name="membrane_sdf",
        channels=1,
        dtype=np.dtype(np.float32),
        semantics="signed EDT of a membrane segmentation, negative inside, voxels (§5)",
    )
    requires = ("rec",)

    def __init__(
        self,
        *,
        segmentation_suffix: Optional[str] = None,
        from_rec: bool = True,
        sigma_vox: float = 1.6,
        percentile: float = 99.3,
        bright: bool = True,
        min_component_vox: int = 40,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.segmentation_suffix = segmentation_suffix
        self.from_rec = bool(from_rec)
        self.sigma_vox = float(sigma_vox)
        self.percentile = float(percentile)
        self.bright = bool(bright)
        self.min_component_vox = int(min_component_vox)
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None

    def _seg_path(self, tomo: "TomogramRef") -> Optional[Path]:
        if self.segmentation_suffix is None:
            return None
        return _tomo.sibling(tomo, self.segmentation_suffix)

    def available(self, tomo: "TomogramRef") -> Availability:
        p = self._seg_path(tomo)
        if p is not None and p.exists():
            return Availability.GENERATABLE
        return Availability.GENERATABLE if self.from_rec else Availability.MISSING

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        from ..emclarity.mrc_io import open_dense_field

        p = self._seg_path(tomo)
        if p is not None and p.exists():
            seg_field = open_dense_field(p, "membrane_seg", channels=1)
            seg = whole_array(seg_field) > 0.5
            grid = seg_field.grid
        elif self.from_rec:
            rec = reg.resolve("rec", tomo, device=device)
            seg = membrane_segmentation(
                whole_array(rec),
                sigma_vox=self.sigma_vox,
                percentile=self.percentile,
                bright=self.bright,
                min_component_vox=self.min_component_vox,
            )
            grid = rec.grid
        else:
            raise FileNotFoundError(f"no membrane segmentation for {_tomo.base_of(tomo)}")
        # Fill fully-enclosed cavities so a CLOSED membrane's interior reads as inside (negative
        # SDF) — this is what makes ``inside_sign`` flag interior replication vesicles and makes
        # the SDF gradient the compartment's OUTWARD normal. Open sheets are unaffected (nothing
        # to fill), and |sdf| stays the distance to the nearest membrane surface either way.
        seg = ndi.binary_fill_holes(seg)
        sdf = signed_edt(seg)
        return DenseField.from_array(
            self.produces.name, grid, sdf.astype(np.float32), channels=1, provider=self
        )

    def cache_path(self, tomo: "TomogramRef") -> Optional[Path]:
        if self._cache_dir is None:
            return None
        return self._cache_dir / _tomo.base_of(tomo) / "membrane_sdf.mrc"

    def cost_hint(self) -> Cost:
        return DERIVE


# --- numeric kernels (domain-free, CPU) -------------------------------------------------------


def _sphere_kernel(radius_vox: float) -> NDArray[np.float32]:
    """Return a normalised solid-sphere averaging kernel of the given voxel radius."""
    r = max(int(round(radius_vox)), 1)
    ax = np.arange(-r, r + 1)
    zz, yy, xx = np.meshgrid(ax, ax, ax, indexing="ij")
    sphere = (zz * zz + yy * yy + xx * xx) <= (r * r)
    k = sphere.astype(np.float32)
    s = float(k.sum())
    out: NDArray[np.float32] = (k / s if s > 0 else k).astype(np.float32)
    return out


def cluster_density(
    mask: NDArray[np.generic], *, radius_vox: float, mode: str = "tophat"
) -> NDArray[np.float32]:
    """Local density (fraction) of a boolean mask within a radius (SPEC §1 gold/ice clusters).

    Args:
        mask: A 0/1 (or boolean) high-CC mask volume.
        radius_vox: Convolution radius in voxels.
        mode: ``"tophat"`` (mean over a solid sphere) or ``"gaussian"`` (Gaussian-weighted).

    Returns:
        The local density volume as float32 in ``[0, 1]``.

    Raises:
        ValueError: If ``mode`` is unknown.
    """
    m = np.asarray(mask, dtype=np.float32)
    if mode == "tophat":
        kernel = _sphere_kernel(radius_vox)
        return np.asarray(ndi.convolve(m, kernel, mode="constant", cval=0.0), dtype=np.float32)
    if mode == "gaussian":
        sigma = max(radius_vox / 2.0, 0.5)
        return np.asarray(ndi.gaussian_filter(m, sigma=sigma, mode="constant"), dtype=np.float32)
    raise ValueError(f"unknown mode {mode!r}")


def blobness(
    values: NDArray[np.generic], *, sigma_vox: float, method: str = "log"
) -> NDArray[np.float32]:
    """Blob response of a scalar volume (compact bright blobs -> high response).

    Args:
        values: The scalar volume (e.g. ``cc``).
        sigma_vox: Gaussian scale in voxels.
        method: ``"log"`` (negative Laplacian-of-Gaussian, default) or ``"frangi"`` (skimage).

    Returns:
        The blob response as float32 (clipped at 0 for ``"log"``).

    Raises:
        ValueError: If ``method`` is unknown.
        ImportError: If ``method == "frangi"`` and scikit-image is unavailable.
    """
    v = np.asarray(values, dtype=np.float32)
    sigma = max(float(sigma_vox), 0.5)
    if method == "log":
        # gaussian_laplace is sigma^2-scaled LoG; compact bright blobs give a NEGATIVE response,
        # so negate and clip so "high == blob-like".
        log = ndi.gaussian_laplace(v, sigma=sigma, mode="nearest")
        return np.asarray(np.clip(-log, 0.0, None), dtype=np.float32)
    if method == "frangi":
        try:
            from skimage.filters import frangi
        except Exception as exc:  # pragma: no cover - optional dep
            raise ImportError("blobness(method='frangi') needs scikit-image") from exc
        resp = frangi(v.astype(np.float64), sigmas=[sigma], black_ridges=False)
        return np.asarray(resp, dtype=np.float32)
    raise ValueError(f"unknown method {method!r}")


def signed_edt(mask: NDArray[np.bool_]) -> NDArray[np.float32]:
    """Signed Euclidean distance transform of a boolean mask (negative inside), in voxels.

    Args:
        mask: Boolean volume, True inside the object.

    Returns:
        Signed distance (float32): ``+dist`` to the object outside, ``-dist`` to the boundary
        inside.
    """
    m = np.asarray(mask, dtype=bool)
    outside = np.asarray(ndi.distance_transform_edt(~m), dtype=np.float32)
    inside = np.asarray(ndi.distance_transform_edt(m), dtype=np.float32)
    return np.where(m, -inside, outside).astype(np.float32)


def _eigvals_sym3(
    a11: NDArray[np.float32],
    a22: NDArray[np.float32],
    a33: NDArray[np.float32],
    a12: NDArray[np.float32],
    a13: NDArray[np.float32],
    a23: NDArray[np.float32],
) -> tuple[NDArray[np.float32], NDArray[np.float32], NDArray[np.float32]]:
    """Analytic eigenvalues of a per-voxel symmetric 3x3 field (Smith 1961), ``e1 >= e2 >= e3``.

    Fully vectorised (no ``np.linalg.eigvalsh`` per-voxel loop, which is ~100x slower on a
    ~3e8-voxel volume). Numerically stable for the diagonal-degenerate case (``p == 0``).

    Args:
        a11, a22, a33: The diagonal Hessian components.
        a12, a13, a23: The off-diagonal Hessian components.

    Returns:
        ``(e1, e2, e3)`` eigenvalue volumes sorted **descending** (``e1`` is the largest).
    """
    p1 = a12 * a12 + a13 * a13 + a23 * a23
    q = (a11 + a22 + a33) / 3.0
    d11, d22, d33 = a11 - q, a22 - q, a33 - q
    p2 = d11 * d11 + d22 * d22 + d33 * d33 + 2.0 * p1
    p = np.sqrt(np.maximum(p2 / 6.0, 1e-20)).astype(np.float32)
    b11, b22, b33 = d11 / p, d22 / p, d33 / p
    b12, b13, b23 = a12 / p, a13 / p, a23 / p
    detb = (
        b11 * (b22 * b33 - b23 * b23)
        - b12 * (b12 * b33 - b23 * b13)
        + b13 * (b12 * b23 - b22 * b13)
    )
    phi = (np.arccos(np.clip(detb / 2.0, -1.0, 1.0)) / 3.0).astype(np.float32)
    e1 = (q + 2.0 * p * np.cos(phi)).astype(np.float32)
    e3 = (q + 2.0 * p * np.cos(phi + 2.0 * np.pi / 3.0)).astype(np.float32)
    e2 = (3.0 * q - e1 - e3).astype(np.float32)
    return e1, e2, e3


def hessian_membraneness(
    vol: NDArray[np.generic], *, sigma_vox: float = 1.6
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Plate/sheet response of a scalar volume from its Hessian eigenvalues (membraneness).

    A lipid bilayer is a locally **planar** density structure: at the sheet the Gaussian-smoothed
    Hessian has one large-magnitude eigenvalue (normal to the sheet) and two near-zero ones (in
    the sheet plane). The response is ``|lambda_c| * max(0, 1 - |lambda_b| / |lambda_c|)`` where
    ``lambda_c`` is the largest-magnitude eigenvalue and ``lambda_b`` the middle one — high only
    when a single eigenvalue dominates (planar), scaled by its strength. The **sign** of
    ``lambda_c`` is returned separately: negative at a *bright* density ridge (the membrane
    material), positive at a dark trough.

    Args:
        vol: The scalar volume (e.g. the tomogram ``rec``).
        sigma_vox: Gaussian scale (voxels) for the second-derivative filters (~membrane scale).

    Returns:
        ``(membraneness, dominant_sign)`` as two float32 volumes on ``vol``'s grid.
    """
    v = np.asarray(vol, dtype=np.float32)
    s = float(sigma_vox)
    hzz = ndi.gaussian_filter(v, s, order=[2, 0, 0]).astype(np.float32)
    hyy = ndi.gaussian_filter(v, s, order=[0, 2, 0]).astype(np.float32)
    hxx = ndi.gaussian_filter(v, s, order=[0, 0, 2]).astype(np.float32)
    hyz = ndi.gaussian_filter(v, s, order=[1, 1, 0]).astype(np.float32)
    hxz = ndi.gaussian_filter(v, s, order=[1, 0, 1]).astype(np.float32)
    hxy = ndi.gaussian_filter(v, s, order=[0, 1, 1]).astype(np.float32)
    e1, e2, e3 = _eigvals_sym3(hzz, hyy, hxx, hyz, hxz, hxy)
    lam = np.stack([e1, e2, e3], axis=-1)
    order = np.argsort(np.abs(lam), axis=-1)  # ascending magnitude
    la = np.take_along_axis(lam, order, axis=-1)
    aa = np.abs(la)
    ab, ac = aa[..., 1], aa[..., 2]
    lc = la[..., 2]
    membr = (ac * np.clip(1.0 - ab / (ac + 1e-6), 0.0, None)).astype(np.float32)
    return membr, np.sign(lc).astype(np.float32)


def membrane_segmentation(
    vol: NDArray[np.generic],
    *,
    sigma_vox: float = 1.6,
    percentile: float = 99.3,
    bright: bool = True,
    min_component_vox: int = 40,
    close_iters: int = 1,
) -> NDArray[np.bool_]:
    """Segment membrane sheets from a tomogram by thresholding its Hessian membraneness.

    Keeps only the requested contrast side (``bright`` — the density ridge, ``lambda_c < 0`` — is
    the membrane material in a CTF-corrected reconstruction), thresholds at a high percentile,
    morphologically closes 1-voxel bilayer gaps, and drops sub-threshold connected specks.

    Args:
        vol: The scalar tomogram volume.
        sigma_vox: Membraneness Gaussian scale (voxels).
        percentile: Membraneness percentile threshold (``0..100``); higher keeps less.
        bright: Keep bright density ridges (``True``) or dark troughs (``False``).
        min_component_vox: Drop connected components smaller than this many voxels.
        close_iters: Binary-closing iterations (bridges thin bilayer gaps).

    Returns:
        A boolean membrane segmentation on ``vol``'s grid.
    """
    membr, sign = hessian_membraneness(vol, sigma_vox=sigma_vox)
    sub = membr[::2, ::2, ::2] if membr.size > 8_000_000 else membr
    thr = float(np.percentile(sub, percentile))
    seg = membr > thr
    seg &= (sign < 0) if bright else (sign > 0)
    if close_iters > 0:
        seg = ndi.binary_closing(seg, iterations=int(close_iters))
    if min_component_vox > 1:
        lab, _ = ndi.label(seg, structure=np.ones((3, 3, 3)))
        sizes = np.bincount(lab.ravel())
        sizes[0] = 0
        small = np.where(sizes < int(min_component_vox))[0]
        if small.size:
            seg[np.isin(lab, small)] = False
    return np.asarray(seg, dtype=bool)


def register_derived(
    reg: FieldRegistry, *, cache_dir: Optional[Path] = None
) -> List[FieldProvider]:
    """Register the standard derived providers on ``reg`` and return them.

    Args:
        reg: The :class:`FieldRegistry` to populate.
        cache_dir: Optional content-addressed cache directory for the derived scalar fields.

    Returns:
        The list of registered providers.
    """
    providers: List[FieldProvider] = [
        SnrFieldProvider(cache_dir=cache_dir),
        NormalFieldProvider(),
        ClusterDensityProvider(cache_dir=cache_dir),
        BlobnessProvider(cache_dir=cache_dir),
        MembraneDistanceProvider(cache_dir=cache_dir),
    ]
    for p in providers:
        reg.register(p)
    return providers
