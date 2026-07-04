# mito_filter — Architecture (definitive)

Status: **BUILT and validated on real data** — Phase A (spatial filter), Phase B (dense
orientation), the joint optimizer over all 112 convmaps (`configs/round_4_fitted.yaml`), and
Phase C (membrane reference) are all implemented and pass the full test suite (288 passed,
1 skipped; lint + `mypy src tests` clean). See `docs/STATUS.md` for the capability summary,
real-data validation, and known limitations, and the per-section status notes below. This
document is the single source of truth for the package structure; when code and this doc
disagree, fix one of them in the same change. Companion to `docs/SPEC.md` (authoritative
data/format spec — every convention number below is verified there).

Location: `/sa_shared/git/emClarity_private/mito_filter/` — an **editable-install package with its
own venv** (`./.venv`), independent of the parent `emclarity` package so it is free to add
torch / cupy / scipy / optuna / pyarrow.

---

## 0. One-paragraph thesis

`mito_filter` decides whether a template-matching (TM) hit is a false positive by reasoning about
the **known spatial layout** of the hits — position **and** orientation — read primarily from the
**dense 3D convmap CC volume** (and generated dense angle/membrane fields), not the lossy csv. The
design is three tiers: (1) a **domain-free reusable `core`** of grid/field/point/surface/cluster
tools; (2) pluggable **`FieldProvider`s** (load OR generate: cc, snr, angle→normal, membrane,
gold), **`CandidateSource`s**, and **`Constraint`s**, all registry+YAML instantiated; (3) two thin
drivers over that core — **`scan`** (apply fixed constraints, write verdicts back into emClarity)
and **`optimize`** (tune the same parametric model jointly over all convmaps of a search, and
transfer to other datasets). All fragile emClarity-convention knowledge is quarantined in one
`emclarity/` adapter behind golden-value tests; the `core` never mentions emClarity or
mitochondria.

Backbone = the dense-first `fields`/`core`/`constraints` design. Grafted: from the ML proposal the
**two-phase feature engine** (extract per-candidate features ONCE from dense fields, cache, tune on
cached matrices) + a single differentiable **`FilterModel`** + a **self-supervised physics
objective**; from the pipeline proposal the **emClarity-convention quarantine**, **content-addressed
cache + run manifest**, **golden-value convention tests**, and **registry+YAML**. Six flagged gaps
are closed as first-class components (§9).

---

## 1. Guiding decisions

1. **Dense fields are the primary object; the csv is one candidate source among several.** The unit
   every constraint receives is a `TomogramFields` bundle of co-registered dense volumes on one
   shared `VoxelGrid`, plus an optional sparse `PointCloud`. Even the candidate set can be
   *re-derived from the dense field* (`DenseFieldPeakSource`), recovering the sheets/clusters the csv
   NMS erased (SPEC §6: 291,224 vox ≥6.07 vs 1249 csv peaks for H99_2_100).
2. **`FieldProvider` is the load-vs-generate seam.** Whether a named field is memmapped from disk,
   *derived* from another field (angle→normal), or *generated* on GPU (FFT-CC engine, membrane
   search) is hidden behind `available()` + `materialize()`. An `Availability` tri-state
   (`ON_DISK | GENERATABLE | MISSING`) + a topologically-resolved provider DAG make mixed-availability
   datasets work: a missing generatable field is produced; a truly missing field makes its dependent
   constraint contribute a neutral value.
3. **Everything pluggable is a registry entry instantiated from YAML.** Add a field / candidate
   source / constraint / dataset = one class + one `@register` + one YAML stanza. No core edits. This
   is the "different constraints or additional information, same core tools" requirement.
4. **Two-phase compute makes joint optimization tractable.** Touch the 662×942×448 fp16 volumes
   **once**: the GPU feature engine extracts per-candidate feature vectors and caches them (parquet,
   few MB/tomo). Features split **θ-independent** (cached, never recomputed) vs **θ-dependent** (cheap
   transforms recomputed per optimizer step on the cached matrix). The tuner iterates on cached
   matrices and **never re-reads a volume**.
5. **One `FilterModel` serves scan and both optimizer families.** A θ-parameterized `torch.nn.Module`
   whose `forward` maps the per-candidate feature matrix → keep-probability. Scan runs it forward;
   the optimizer tunes θ. **Black-box optimizers (optuna/CMA/scipy) are the primary path** because
   the load-bearing knobs (cluster CC threshold, coherence radius, surface-fit tolerance) live on the
   non-differentiable feature side; autograd (Adam/LBFGS) is available for the differentiable combiner
   weights only.
6. **emClarity conventions are quarantined.** All column-major unpack, C12-invariant normal
   (cols 23–25), packed-index decode, `csv/5==.pos` frame, mode-12/mode-2 IO, col26 semantics, and
   the `.mat` write path live in `emclarity/`, locked by golden-value tests against SPEC constants.
   `core/` is pure geometry/tensor.
7. **The authoritative filter sink is the subTomoMeta `.mat`, keyed by subtomo id** (§9.1) — the csv
   col26 write is a convenience/debug artifact, not the thing that changes emClarity behavior.
8. **Style per user directive:** this package uses **black + isort + flake8 + mypy @ line-length
   100, fully typed** in its own venv (the parent repo uses ruff@88; the separate venv+config makes
   this a deliberate, self-contained choice — see §11).

---

## 2. Module / file layout

```
/sa_shared/git/emClarity_private/mito_filter/
├── pyproject.toml                  # editable install; deps; black+isort config @100
├── setup.cfg                       # flake8 + mypy config (line-length 100, strict)
├── Makefile                        # venv / fmt / lint / type / test targets
├── README.md
├── docs/
│   ├── SPEC.md                     # (exists) authoritative TM-format spec
│   ├── DESIGN.md                   # this document
│   └── onboarding_new_dataset.md   # new-dataset / new-field / new-constraint recipe
├── configs/
│   ├── round_4.yaml                # primary dev-set scan pipeline
│   ├── engine.yaml                 # host/GPU pool, block/halo, cache dirs
│   ├── constraints/                # reusable !include-able constraint fragments
│   │   ├── gold_ice_cluster.yaml
│   │   ├── membrane_geometry.yaml
│   │   └── surface_coherence.yaml
│   └── optimize/
│       └── round_4_sweep.yaml      # search space + objective + weak labels
│
├── src/mito_filter/
│   ├── __init__.py
│   ├── py.typed                    # PEP 561 typed marker
│   │
│   ├── core/                       # ── DOMAIN-FREE, REUSABLE ──────────────────
│   │   ├── grid.py                 # VoxelGrid: dims, apix, world<->voxel, same_grid
│   │   ├── field.py                # DenseField, VectorField, IndexField, TomogramFields
│   │   ├── points.py               # PointCloud (SoA: positions + scalar/vector attrs)
│   │   ├── neighbors.py            # NeighborIndex: radius/knn (KD-tree cpu | grid-hash gpu)
│   │   ├── clustering.py           # dense connected-components (union-find seam merge) + DBSCAN
│   │   ├── surfaces.py             # normal_coherence, local_curvature, fit_surface (quadric/plane)
│   │   ├── sampling.py             # trilinear gather at points; ±1-nbhd reduce (center/max/mean)
│   │   ├── backend.py              # array backend shim: numpy | cupy | torch (.xp(), device mgmt)
│   │   ├── chunking.py             # BlockPlan: halo-aware chunked iteration of big volumes
│   │   └── registry.py             # generic Registry[T] + @register decorators
│   │
│   ├── emclarity/                  # ── CONVENTION ADAPTER (quarantined) ───────
│   │   ├── constants.py            # verified SPEC numbers (nTemplates=3, apix=12.5, byte sizes…)
│   │   ├── mrc_io.py               # mode-12 fp16 / mode-2 fp32 mmap+chunked IO; REFUSE fp16 packed idx
│   │   ├── csv_io.py               # 26-col read/write, col-major unpack, col26 round-trip
│   │   ├── conventions.py          # euler<->matrix<->normal, packed-index decode, C12 note
│   │   ├── angles_list.py          # _angles.list (864×3) parse; angleIdx -> euler
│   │   ├── templateidx.py          # .templateIDX / .pos / .mod / .erase readers
│   │   └── matio.py                # subTomoMeta .mat write bridge (MATLAB-on-salina, by subtomo_id)
│   │
│   ├── fields/                     # ── FIELD PROVIDERS (load OR generate) ─────
│   │   ├── provider.py             # FieldProvider ABC, Availability, FieldSpec, FieldRegistry(DAG)
│   │   ├── loaders.py              # ConvmapProvider, RecProvider, AngleIndexLoader, NoiseVarLoader
│   │   ├── derived.py              # NormalFieldProvider, SnrFieldProvider, ClusterDensityProvider,
│   │   │                           #   BlobnessProvider, MembraneDistanceProvider
│   │   ├── calibrate.py            # BackgroundModel (per-tomo robust N(mu,sigma) fit; z-score)
│   │   ├── gold.py                 # GoldFiducialProvider (.erase / IMOD bead models -> gold mask)
│   │   └── generate/
│   │       ├── emclarity_angle.py  # EmClarityAngleProvider: drive salina patch+recompile+rerun -> load
│   │       ├── fft_cc_engine.py    # TorchCCAngleProvider: cupy/torch FFT-CC fallback (SPEC §7c)
│   │       └── membrane_search.py  # MembraneSearchProvider: bilayer template gen + separate search
│   │
│   ├── candidates/
│   │   ├── source.py               # CandidateSource ABC, CandidateSet
│   │   ├── csv_source.py           # CsvPeakSource (the sparse peaks)
│   │   └── dense_source.py         # DenseFieldPeakSource (+ oriented NMS de-dup, §9.6)
│   │
│   ├── features/                   # ── TWO-PHASE GPU FEATURE ENGINE ───────────
│   │   ├── extractor.py            # FeatureExtractor ABC, FeatureSpec, FeatureMatrix, theta_dependent
│   │   ├── engine.py               # FeatureEngine: block-stream fields once -> per-candidate rows -> cache
│   │   ├── local_stats.py          # score-cluster density, Frangi/Hessian blobness (gold/ice)
│   │   ├── membrane.py             # membrane distance, inside/outside sign, closed-shell test
│   │   ├── curvature.py            # normal-coherence, surface-fit residual, principal curvature
│   │   ├── isolation.py            # neighbor density / off-surface isolation
│   │   └── priors.py               # templateIDX prior, raw/SNR score, physical position
│   │
│   ├── constraints/                # ── CONSTRAINT PLUGINS ─────────────────────
│   │   ├── base.py                 # Constraint ABC, ConstraintResult
│   │   ├── gold_ice.py             # GoldIceClusterConstraint (dense extreme-CC clusters + fiducials)
│   │   ├── membrane.py             # MembraneGeometryConstraint (inside/outside, interior vesicle)
│   │   ├── curvature.py            # SurfaceCoherenceConstraint (sparse-OR-dense normals, CC-gated)
│   │   ├── isolation.py            # IsolationConstraint
│   │   ├── template_prior.py       # TemplateIdxPriorConstraint (templateIDX==1 weak-negative)
│   │   └── combine.py              # ScoreCombiner (weighted/logit fusion; the FilterModel head)
│   │
│   ├── model/
│   │   ├── filter_model.py         # FilterModel(nn.Module): constraints/features + θ -> keep_prob
│   │   └── config.py               # FittedConfig (providers+features+constraints+θ+calib) yaml I/O
│   │
│   ├── scan/                       # ── LAYER 1: SCAN + FILTER ─────────────────
│   │   ├── context.py              # RunContext: grid, provider cache, backend, config
│   │   ├── pipeline.py             # ScanPipeline: resolve providers -> features -> model -> verdicts
│   │   ├── verdicts.py             # HitVerdicts: per-hit score/flag/removed + provenance
│   │   └── writeback.py            # verdicts -> col26 (csv) AND -> .mat removal list (authoritative)
│   │
│   ├── optimize/                   # ── LAYER 2: JOINT OPTIMIZATION / TRAINING ─
│   │   ├── dataset.py              # SearchDataset: cached FeatureMatrix over ALL convmaps of a search
│   │   ├── labels.py               # WeakLabelSource (templateIDX / cull / .mat v6 snapshots)
│   │   ├── objective.py            # Objective ABC: self-supervised (primary) + weak-label (secondary)
│   │   ├── space.py                # ParameterSpace: named θ -> pipeline overrides + bounds
│   │   ├── optimizers.py           # OptunaOptimizer / ScipyOptimizer / TorchTrainer
│   │   ├── tuner.py                # Tuner: fit θ jointly -> FittedConfig; warm-start transfer
│   │   └── report.py               # PR/ROC vs weak labels, separation, chosen θ, plots
│   │
│   ├── validate/                   # ── DOWNSTREAM-QUALITY LOOP (§9.5) ─────────
│   │   ├── phantom.py              # synthetic phantom: curved membrane + planted gold + true hits
│   │   ├── holdout.py              # small hand-labeled hold-out ROC harness
│   │   └── reconstruction.py       # FSC/resolution proxy: filtered vs unfiltered subtomo average
│   │
│   ├── datasets/
│   │   ├── base.py                 # DataSource ABC, TomogramRef, SearchRef
│   │   └── emclarity_tm.py         # EmclarityTMSource: discover a round's 7-file/tomo sets
│   │
│   ├── exec/                       # ── PARALLEL EXECUTION ─────────────────────
│   │   ├── runner.py               # TomogramRunner: map a per-tomo job over N tomos (resumable)
│   │   ├── cluster.py              # SSHParallel (GNU parallel --sshlogin) + LocalProcess (joblib)
│   │   └── gpu.py                  # CUDA_VISIBLE_DEVICES pinning, per-host worker caps, RAM guard
│   │
│   ├── config.py                   # YAML -> typed dataclasses; !include; env expansion
│   ├── manifest.py                 # RunManifest: resolved config + git revs + param/file hashes
│   ├── logging.py                  # structured logging
│   └── cli.py                      # mito-filter scan | optimize | gen-field | writeback | validate
│
└── tests/
    ├── conftest.py                 # tiny synthetic fixtures (64^3 fp16 vol, fake 26-col csv)
    ├── unit/
    │   ├── test_conventions.py     # golden-value: |MM^T-I|, csv/5==.pos, packed-idx->normal 6.4e-5
    │   ├── test_mrc_io.py          # byte size 558,750,208; mode-12 refusal for packed idx
    │   ├── test_grid_sampling.py   # trilinear + ±1 nbhd reproduces csv col1
    │   ├── test_clustering.py      # union-find seam merge across a straddling cluster
    │   └── test_model_grad.py      # finite-diff check of the differentiable combiner head
    ├── integration/
    │   ├── test_provider_parity.py # load-vs-generate parity on a crop
    │   ├── test_dense_vs_csv_normal.py  # §9.3 acceptance: dense-decoded normal == csv 23-25 @peaks
    │   └── test_scan_end_to_end.py # csv-only scan on one small tomo -> verdicts -> col26
    └── data/                       # committed micro-fixtures only (never 62 GB recs)
```

---

## 3. Core (domain-free, reusable) — key classes

The core knows nothing about emClarity, mitochondria, or false positives. It manipulates grids,
dense fields, and oriented point clouds. This is what a *different* spatial task reuses verbatim.

### `core/grid.py`
```python
@dataclass(frozen=True)
class VoxelGrid:
    shape: tuple[int, int, int]        # (nz, ny, nx) = (448, 942, 662), C order == mrc mmap
    apix: float                        # Å/voxel (12.5); NOT the header's cosmetic 1.0
    order: str = "zyx"
    def world(self, ijk: NDArray) -> NDArray: ...   # voxel -> Å
    def voxel(self, xyz: NDArray) -> NDArray: ...    # Å -> voxel
    def same_grid(self, other: "VoxelGrid") -> bool: ...
```

### `core/field.py`
```python
class DenseField:
    """One co-registered dense volume on a VoxelGrid. Lazy, memmap-backed, chunk/GPU streamable.
    NEVER hot-loads the whole 559 MB volume."""
    name: str
    grid: VoxelGrid
    dtype: np.dtype
    channels: int                              # 1 scalar, 3 vector (normal), 1 index
    provider: "FieldProvider"                  # who materialized it (provenance)
    def block(self, plan: "Block", *, xp=np) -> ArrayT: ...       # halo-aware chunk read, cast fp32
    def iter_blocks(self, block_shape, halo=0) -> Iterator[tuple["Block", ArrayT]]: ...
    def sample_at(self, pts: NDArray, *, xp=np, reduce="max", radius=1) -> ArrayT: ...  # ±1 nbhd
    def as_memmap(self) -> np.memmap: ...

class VectorField(DenseField): ...             # 3-channel (e.g. per-voxel normal)
class IndexField(DenseField):                  # packed argmax p (SPEC §5); decode delegated to emclarity/
    def decode_normal(self, angles_list) -> VectorField: ...
    def decode_template(self) -> DenseField: ...   # refIdx = (p-1) % 3 + 1

class TomogramFields:
    """Named bundle of DenseFields sharing one grid + the optional sparse PointCloud.
    THE object every constraint / feature extractor receives."""
    grid: VoxelGrid
    fields: dict[str, DenseField]              # "cc","snr","angle","normal","membrane","gold",...
    points: PointCloud | None
    meta: Mapping[str, object]
    def require(self, name: str) -> DenseField: ...   # helpful KeyError if a provider was skipped
```

### `core/points.py`
```python
class PointCloud:
    """Positions (voxel frame) + arbitrary per-point scalar & vector attrs. SoA, vectorized."""
    xyz: NDArray                    # (N,3) convmap-voxel coords
    attrs: dict[str, NDArray]       # "cc","normal"(N,3),"template_idx","subtomo_id","active",...
    def with_attr(self, k, v) -> "PointCloud": ...
    def subset(self, mask) -> "PointCloud": ...
    def to_active_flag(self) -> NDArray: ...    # keep=1 / remove=-9999
```

### Reusable spatial tools (the "core analysis tools reusable for other tasks")
- `core/neighbors.py` — `NeighborIndex.radius(pts, r_A)`, `.knn(pts, k)`; KD-tree (cpu, sparse) or
  grid-hash (gpu, dense). All radii in physical Å (grid.apix aware).
- `core/clustering.py` — `dense_clusters(field, thr, min_size, connectivity)` = connected components
  of a thresholded dense volume with **union-find seam-merge across halo block boundaries** (graft
  from fields; the correctness detail others gloss); `point_clusters(cloud, eps, min_pts)` = DBSCAN.
- `core/surfaces.py` — `normal_coherence(normals, neighbors)`, `local_curvature(normals, pos,
  neighbors)`, `fit_surface(pos, normals) -> (residual, k1, k2)` (quadric/plane fit). **Consumes
  normals from either a `PointCloud` attr (sparse csv) or a `VectorField` (dense) — one API, two
  feeds.** This is the "curvature from sparse csv normals AND the dense angle field" requirement.
- `core/sampling.py` — trilinear sampling (torch `grid_sample` | cupy `map_coordinates` | scipy
  fallback) + the ±1-neighborhood reduce that reproduces the csv score (SPEC §3, <0.02).
- `core/backend.py` — `Backend.xp()` returns numpy | cupy | torch by `Device`; CPU path always works
  so tests run anywhere.
- `core/chunking.py` — `BlockPlan(volume_shape, block_shape, halo)` yields halo-padded `Block`s;
  halo ≥ the largest constraint reach (cluster/coherence radius, the ~[16,16,26]-vox erase cylinder).

**Extensibility guarantee:** every core tool takes a `DenseField`/`PointCloud` + explicit params.
"Set different constraints or supply additional information" = call with a different config or attach
a new attr/field. No mito assumptions inside.

---

## 4. `emclarity/` — the convention adapter (quarantine)

All fragile spec knowledge lives here and nowhere else; `core/` is domain-free. Locked by
golden-value tests (`tests/unit/test_conventions.py`) against the exact SPEC constants.

- `constants.py` — `N_TEMPLATES=3`, `APIX_A=12.5`, `SAMPLING_RATE=5`, `CONVMAP_BYTES=558_750_208`,
  `CONVMAP_SHAPE=(448,942,662)`, `BACKGROUND=(3.28,0.48)`, column indices, `ERASE_RADIUS_A=(210,210,320)`.
- `conventions.py` —
  - `normal_from_matrix(row) -> n` : cols 23–25 (0-idx 22:25), **C12-invariant**; never cols 17–22.
  - `normal_from_euler(phi, theta) -> n = [sinφ·sinθ, −cosφ·sinθ, cosθ]`.
  - `decode_packed_index(p) -> (angle_idx, ref_idx)` : `angle_idx=(p-1)//3+1`, `ref_idx=(p-1)%3+1`.
  - `matrix_from_row(row) -> 3×3` column-major unpack. **Do not re-sign the normal** (raw sign is the
    outward-vs-inward signal).
- `mrc_io.py` — mmap read (mode-12 fp16, cast per-block to fp32), mode-2 fp32 write. **Hard-refuses
  writing/reading a packed-index field as mode-12** (2592 > 2048 fp16 integer-exact limit → silent
  corruption); asserts fp32/int16 for `IndexField`.
- `csv_io.py` — read 26-col csv into a `PointCloud` (positions cols 11–13 **÷5** → voxel frame,
  normals cols 23–25, score col 1, template_idx from sibling `.templateIDX`, subtomo_id col 4);
  write col26 back preserving row order.
- `angles_list.py` — parse `_angles.list` (864×3 deg); `angle_idx → (phi, theta, psi−phi)`.
- `templateidx.py` — read `.templateIDX`, `.pos`, `.mod`, and `fixedStacks/*.erase` bead models.
- `matio.py` — the **authoritative** filter sink (§9.1): emit a removal list keyed by subtomo_id and
  drive a MATLAB-on-salina apply step that writes −9999 into the subTomoMeta `.mat` (scipy `loadmat`
  fails zlib CRC; positions drift → key by subtomo_id / angle triple, never position).

---

## 5. `FieldProvider` — the load-vs-generate abstraction (central)

### `fields/provider.py`
```python
class Availability(Enum):
    ON_DISK = auto()        # a file exists to load
    GENERATABLE = auto()    # inputs exist to generate (or derive) it
    MISSING = auto()        # cannot be produced -> dependent constraints go neutral

@dataclass(frozen=True)
class FieldSpec:
    name: str
    channels: int
    dtype: np.dtype
    semantics: str

class FieldProvider(ABC):
    """Produces ONE named DenseField for a tomogram, by LOADING, DERIVING, or GENERATING."""
    produces: FieldSpec
    requires: tuple[str, ...] = ()                       # other field names it derives from
    @abstractmethod
    def available(self, tomo: "TomogramRef") -> Availability: ...
    @abstractmethod
    def materialize(self, tomo: "TomogramRef", reg: "FieldRegistry",
                    *, device: Device) -> DenseField: ...
    def cache_path(self, tomo) -> Path | None: ...       # generated/derived fields persist here
    def cost_hint(self) -> Cost: ...                     # CHEAP_LOAD | DERIVE | GPU_GENERATE

class FieldRegistry:
    """name -> provider, resolved as a DAG (requires resolved first), memoized per tomo,
    with content-addressed on-disk caching keyed on (provider, params, source mtimes)."""
    def register(self, p: FieldProvider) -> None: ...
    def resolve(self, name: str, tomo: TomogramRef, *, device) -> DenseField: ...
    def plan(self, needed: set[str], tomo) -> list[FieldProvider]: ...   # topo-sort
```

### Concrete providers

| Provider | name(s) | Kind | How |
|---|---|---|---|
| `ConvmapProvider` | `cc` | **load** | mmap `<base>_convmap.mrc` (SPEC §1) |
| `RecProvider` | `rec` | **load** | mmap `/scratch/salina/alt_cache/<base>.rec` |
| `NoiseVarLoader` | `noise_variance` | **load** | `<base>_noise_variance.mrc` if the `measure_noise_variance=1` re-run emitted it |
| `SnrFieldProvider` | `snr` | **derive** | `cc / sqrt(noise_variance)` if present, else per-tomo z-score via `BackgroundModel` (§9.2) |
| `AngleIndexLoader` | `angle` | **load** | regenerated `<base>_angles.mrc` (mode-2 fp32) after the §7 patch |
| `EmClarityAngleProvider` | `angle` | **generate→load** | drive salina patch+recompile+rerun, then load (SPEC §7b) |
| `TorchCCAngleProvider` | `angle` | **generate** | cupy/torch FFT-CC over 864 angles × 3 templates + wedge (SPEC §7c fallback) |
| `NormalFieldProvider` | `normal` | **derive** | `IndexField.decode_normal(angles_list)` — pure GPU map, requires `angle` |
| `MembraneSearchProvider` | `membrane`, `membrane_normal` | **generate** | synthetic bilayer template (§8) → separate GPU search |
| `MembraneDistanceProvider` | `membrane_sdf` | **derive** | signed EDT from a membrane segmentation (+inside/outside) |
| `ClusterDensityProvider` | `cc_cluster` | **derive** | GPU top-hat/Gaussian conv of thresholded high-CC mask (gold/ice density) |
| `BlobnessProvider` | `blobness` | **derive** | GPU Hessian-eigenvalue (Frangi) on `cc` → cluster compactness |
| `GoldFiducialProvider` | `gold` | **load** | rasterize `fixedStacks/*.erase` / IMOD bead models → gold mask (§9.4) |

A constraint asking for `"normal"` transparently triggers: load `angle` mrc if present, else generate
it, else FFT-CC fallback; then derive normals. The constraint code is identical in all cases —
load-vs-generate is a **config choice**, not a code change.

**Provenance & reuse:** generated/derived fields are written to a content-addressed cache
(`<cache>/<tomo>/<field>@<hash>.mrc`) with a sidecar manifest (provider, param hash, source files +
mtimes, git rev). A second run — and every Layer-2 trial that doesn't change generation params —
loads instead of regenerating.

---

## 6. Two-phase feature engine

The load-bearing scalability idea (graft from ml). Dense volumes are touched **once**.

### `features/extractor.py`
```python
class FeatureExtractor(ABC):
    produces: tuple[str, ...]              # feature column names
    needs_fields: tuple[str, ...]          # field names required (drive FieldRegistry.plan)
    theta_dependent: bool = False          # True -> recomputed per optimizer step, NOT cached
    @abstractmethod
    def extract(self, cand: CandidateSet, fields: Mapping[str, DenseField],
                ctx: "BlockCtx") -> dict[str, ArrayT]: ...
```

### `features/engine.py`
```python
class FeatureEngine:
    """Block-stream every needed field ONCE (halo-aware) -> gather per-candidate feature rows on GPU
    -> concatenate into a (N_candidates, N_features) FeatureMatrix + column index -> cache to parquet."""
    def run(self, tomo: TomogramRef, ctx: RunContext) -> FeatureMatrix: ...
    def run_cached(self, tomo: TomogramRef, cache_dir: Path) -> FeatureMatrix: ...
```

Concrete extractors map to the false-positive physics:
- `local_stats.py`: `ScoreClusterDensity`, `Blobness` (Frangi/Hessian) → gold/ice = compact clusters
  of extreme CC. Also `GoldFiducialProximity` (distance to a `gold` fiducial, §9.4).
- `membrane.py`: `MembraneDistance`, `InsideOutsideSign`, `ClosedShellScore` → membrane hits +
  interior replication vesicles.
- `curvature.py`: `NormalCoherence`, `SurfaceFitResidual` (RANSAC quadric on neighborhood normals),
  `PrincipalCurvature`. **CC-gated** (§9.3): dense-normal features are masked/weighted by the
  co-located `cc`/`snr` so background argmax-of-noise normals don't swamp the fit. Sparse (csv) and
  dense (field) normals both flow through the same `core/surfaces.py` calls.
- `isolation.py`: `NeighborDensity`, `OffSurfaceIsolation`.
- `priors.py`: `TemplateIdxPrior` (templateIDX==1 weak-negative, SPEC §10), `RawScore`, `SnrScore`,
  `PhysicalPosition`.

θ-independent features (cluster density, blobness, membrane distance, raw normals, coherence at a
fixed radius) are cached once; θ-dependent transforms (e.g. thresholding a cached cluster-density at
a tunable level, re-weighting by a tunable coherence sharpness) are cheap functions of the cached
matrix recomputed per optimizer step — the tuner never re-reads a volume.

---

## 7. Constraint plugin API + the model

### `constraints/base.py`
```python
@dataclass
class ConstraintResult:
    per_hit_score: NDArray          # (N,) continuous FP-likelihood contribution
    per_hit_flag: NDArray | None    # (N,) bool hard reject, optional
    diagnostics: Mapping[str, object]
    params_used: Mapping[str, float]
    name: str

class Constraint(ABC):
    name: str
    needs_features: tuple[str, ...]           # -> FeatureSpec for the engine
    param_schema: dict[str, "ParamSpec"]      # θ names, bounds, init, log-scale -> exposed to tuner
    def __init__(self, **params: object) -> None: ...     # from YAML
    @abstractmethod
    def forward(self, feats: FeatureMatrix, theta: "ParamDict") -> Tensor:
        """Per-candidate penalty/support. Torch-diffable where possible; combinatorial pieces
        (cluster labels, RANSAC fit) are precomputed features, so `forward` sees numbers."""
```

### The physics constraints (SPEC §1, §6)
- `GoldIceClusterConstraint` (`needs_features=("cc_cluster_density","blobness","gold_dist")`) —
  compact over-large-CC clusters (~8–13) AND proximity to known gold fiducials → FP. **Clusters
  expected but not required**: a hit needs no cluster to survive; a hit *inside* one is penalized
  (soft).
- `MembraneGeometryConstraint` (`needs_features=("membrane_dist","inside_sign","closed_shell")`) —
  membrane-lattice hits and wrong-side hits; separates extended low-curvature outer membrane from
  small closed interior replication vesicles.
- `SurfaceCoherenceConstraint` (`needs_features=("normal_coherence","surface_residual","curvature")`)
  — true targets sit in a smooth curved membrane with template +Z = outward normal; incoherent
  neighborhood normals → FP. Works from sparse csv normals **or** the dense normal field (CC-gated).
- `IsolationConstraint`, `TemplateIdxPriorConstraint` — soft weak priors.

### `model/filter_model.py`
```python
class FilterModel(nn.Module):
    """θ-parameterized combination of constraints -> per-candidate keep-probability.
    ONE object serves scan (forward), optuna/scipy (black-box eval), and autograd (combiner head)."""
    def __init__(self, constraints: list[Constraint], combiner: "Combiner") -> None: ...
    def forward(self, feats: FeatureMatrix) -> Tensor:     # keep_prob in (0,1)
        # combiner = weighted-logit sum OR small MLP over constraint outputs -> sigmoid
    def decide(self, feats: FeatureMatrix, tau: float) -> NDArray:   # bool keep mask
    @property
    def theta(self) -> ParamDict: ...                      # constraint params + combiner weights
```
`FeatureSpec = ∪ c.needs_features` → the engine computes exactly the needed features;
`FieldRegistry.plan(∪ extractor.needs_fields)` → exactly the needed fields get built.

### 7.1 Worked example — add a NEW field + NEW constraint + NEW information

Scenario: a biologist hand-traces the outer mito membrane as an IMOD `.mod` mesh per tomo (new
external information); we want "signed distance to the traced surface, outward-facing" as a new FP
discriminator. Three small isolated additions; **nothing in `core/` or either driver changes.**

```python
# fields/loaders.py
@register_provider("traced_membrane_sdf")
class TracedMembraneProvider(FieldProvider):
    produces = FieldSpec("traced_membrane_sdf", channels=1, dtype=np.float32,
                         semantics="signed EDT, negative inside")
    def __init__(self, mod_glob: str) -> None: self.mod_glob = mod_glob
    def available(self, tomo):
        return Availability.GENERATABLE if mesh_exists(tomo, self.mod_glob) else Availability.MISSING
    def materialize(self, tomo, reg, *, device):
        mesh = load_imod_mesh(tomo, self.mod_glob)                 # new INFORMATION
        sdf = signed_edt(rasterize(mesh, tomo.grid), xp=backend(device).xp)
        return DenseField.from_array("traced_membrane_sdf", tomo.grid, sdf, provider=self)

# features/membrane.py
@register_extractor
class TracedMembraneDistance(FeatureExtractor):
    produces = ("d_traced", "inside_traced")
    needs_fields = ("traced_membrane_sdf",)
    def extract(self, cand, fields, ctx):
        d = fields["traced_membrane_sdf"].sample_at(cand.coords_zyx, xp=ctx.xp)
        return {"d_traced": d, "inside_traced": (d < 0).astype(np.float32)}

# constraints/membrane.py
@register_constraint("traced_membrane")
class TracedMembraneConstraint(Constraint):
    name = "traced_membrane"
    needs_features = ("d_traced", "inside_traced")
    param_schema = {"shell_A": ParamSpec(0.0, 200.0, 50.0),
                    "sharpness": ParamSpec(0.1, 10.0, 1.0)}
    def forward(self, feats, theta):
        d = feats["d_traced"]                                       # true targets in a shell, outward
        return torch.sigmoid(theta["sharpness"] * (d.abs() - theta["shell_A"] / APIX_A))
```
```yaml
# configs/round_4.yaml  (append — no core edits)
providers:
  - {name: traced_membrane_sdf, mod_glob: "traces/{tomo}.membrane.mod"}
constraints:
  - {name: traced_membrane, shell_A: 50, sharpness: 1.0}
```
Register + configure, then re-run `optimize` to fit the two new params jointly with the rest; scan
picks up the new θ automatically. If a trace is absent for some tomos, `available()==MISSING` → the
planner skips the provider and the constraint contributes a neutral value (masked) — mixed-
availability datasets still work. The same recipe onboards a segmentation, a second search's convmap,
external fiducials, or a different symmetry.

---

## 8. How scan (Layer 1) and optimize (Layer 2) share the reusable core

```
              ┌──────────────────────── CORE (reusable) ────────────────────────┐
              │ DataSource -> FieldRegistry(providers) -> CandidateSource        │
              │  -> FeatureEngine(extractors) [CACHED] -> FilterModel(θ)         │
              └──────────────────────────────────────────────────────────────────┘
  LAYER 1  scan/filter  (consumer)                LAYER 2  optimize  (producer)
  ────────────────────────────────               ──────────────────────────────────
  FittedConfig(θ) --load--> FilterModel           SearchDataset: cached FeatureMatrix
  ScanPipeline: per tomo, forward only              over ALL 112 convmaps (one unit)
  model.decide(τ) -> keep/flag/remove             WeakLabelSource + self-sup Objective
  writeback: subtomo_id -> -9999 into .mat        Tuner: fit θ (optuna/scipy | autograd)
    (authoritative) + col26 csv (debug)             -> FittedConfig (yaml) ─────────────┐
        ▲                                                                                │
        └──────────────── SAME FilterModel object, SAME cached features ◄───────────────┘
```

- **Scan** (`scan/pipeline.py`): load `FittedConfig`, build the model, `FeatureEngine.run_cached`
  per tomo, `model.decide(τ)`, `writeback` maps decisions to −9999 **by subtomo_id / angle triple**
  (never position) into the `.mat` (authoritative, §9.1) and mirrors col26 into a debug csv. Pure
  forward; no labels, no gradients. Resumable per-tomo.
- **Optimize** (`optimize/tuner.py`): build `SearchDataset` from the cached per-tomo `FeatureMatrix`
  of **every** tomo, evaluate the `Objective`, fit θ **jointly across all convmaps**. Emits the same
  `FittedConfig` scan consumes. Heavy dense GPU work (feature extraction) is amortized once via the
  cache; trials iterate on cached matrices.

**Objectives** (`optimize/objective.py`):
- **Self-supervised (PRIMARY, graft from ml)** — a contrastive/margin objective + a 2-component
  (target vs FP) mixture that exploits the dense physics the SPEC describes: push compact extreme-CC
  clusters (gold/ice) and off-surface incoherent-normal isolated hits to low keep-prob; reward
  normal-coherent membrane-surface membership. **Works with no `.mat`.** This avoids the circular
  trap of merely reproducing the classification culls.
- **Weak-label (SECONDARY / regularizing)** — BCE/focal on the SPEC §10 labels: cyc2/5/8 culls
  (negatives/positives, confidence-weighted by cull stage), templateIDX==1 negative prior. Read via
  the v6 `.mat` snapshots / templateIDX (never scipy `loadmat`).

**Optimizers** (`optimize/optimizers.py`), all over the SAME `FilterModel`:
- `OptunaOptimizer` (TPE/CMA-ES) — **primary**; global search over `param_schema` bounds; handles the
  non-differentiable knobs (cluster threshold, coherence radius, surface-fit tolerance).
- `ScipyOptimizer` (L-BFGS-B / Nelder-Mead) — robustness/refinement over `model.theta`.
- `TorchTrainer` (Adam/LBFGS) — autograd through the differentiable combiner head only.

**Transfer** (`Tuner.fit(..., warm_start=FittedConfig)`): re-fit or fine-tune on a new dataset/round;
`FittedConfig` (providers + feature spec + constraints + θ + per-tomo calibration stats) is the
portable unit. A new dataset needs only its own `DataSource` + `WeakLabelSource`.

**Seam:** `optimize/` imports `scan/`, `constraints/`, `model/`, `core/`. Nothing in Layer 1 imports
Layer 2.

---

## 9. Closing the six flagged gaps (first-class components)

### 9.1 Authoritative sink = the subTomoMeta `.mat`, not csv col26
emClarity writes −9999 into the `.mat` at classification and (per SPEC §6) **never back into the raw
csv** — so a csv col26 write is likely a no-op for downstream behavior. `emclarity/matio.py` is the
real R6 deliverable: `writeback` emits a removal list keyed by **subtomo_id** (+ angle triple as a
cross-check), and drives a **MATLAB-on-salina** apply step (scipy can't read the 480 MB v7 `.mat`;
positions drift across cycles) that sets col26=−9999 in the geometry. The csv col26 mirror is kept as
a human-readable debug/diff artifact and for the `--dry-run` gate. A golden test enforces the
subtomo_id keying.

### 9.2 Cross-tomo / cross-search calibration (`SnrFieldProvider` + `BackgroundModel`)
The convmap is per-orientation σ-normalized, **not** SNR, with a per-tomo background that drifts, so
absolute thresholds (gold/ice ~8–13, membrane ~4–6) don't transfer. Two concrete, physics-tied
mechanisms:
1. **`NoiseVarLoader` + `SnrFieldProvider`** — the cleanest fix is a one-flag re-run
   (`measure_noise_variance=1`, done alongside the §7 angle patch) emitting `<base>_noise_variance.mrc`;
   `snr = cc / sqrt(noise_variance)` is a calibrated per-voxel SNR field, a first-class provider.
2. **`fields/calibrate.py::BackgroundModel`** — when noise-variance is absent, robustly fit each
   tomo's background mode `N(≈3.28, ≈0.48)` (median/MAD or a truncated Gaussian below p95) and
   z-score the convmap against it, so any shared absolute threshold becomes dataset-portable.
Constraints consume `snr` (or z-scored `cc`) by default, not raw `cc`. `FittedConfig` stores the
per-tomo calibration stats so transfer re-fits/rescales rather than reusing raw thresholds.

### 9.3 Dense normal field is argmax-of-noise in the background → CC-gate everything
The regenerated angle field stores an argmax orientation at **every** voxel; at low-CC background
voxels that argmax is the argmax of noise → random normals. **Rule (enforced in `features/curvature.py`
and `NormalFieldProvider`):** all dense-normal operations (coherence, curvature, surface fit) are
**masked or weighted by the co-located `cc`/`snr`** — only voxels in the elevated-CC band (≥ ~p99, or
SNR-thresholded) contribute; background normals are excluded. A dedicated
`tests/integration/test_dense_vs_csv_normal.py` acceptance test cross-checks that the **dense-decoded
normal at a csv peak voxel equals csv cols 23–25 to ~1e-4** before any constraint trusts the field —
the single check that catches a handedness/packing/convention error across the whole dense-orientation
pipeline (also the fallback-engine frame/handedness acceptance test, science gap). Related coupling
(handled here): a gold cluster's extreme CC can win the MIP argmax in a **halo** around the gold,
corrupting neighboring normals → the `gold`/cluster mask is subtracted from the normal field **before**
surface fitting. And a per-voxel winning `ref_idx` that disagrees with a hit's `template_idx` flags
the dense normal at that voxel as untrusted (template-consistency check).

### 9.4 Use existing gold-fiducial information (`GoldFiducialProvider`)
Tilt-series alignment already located the gold beads (`fixedStacks/*.erase` / IMOD bead models) —
exactly the compact extreme-CC gold/ice clusters the gold/ice constraint hunts. `fields/gold.py`
rasterizes them into a `gold` mask/`gold_dist` field: a cheap, high-precision, already-computed prior
feeding `GoldIceClusterConstraint` (and the §9.3 halo exclusion) with no re-detection.

### 9.5 Downstream-quality validation loop (`validate/`)
Weak labels are circular (culls came from classification, not spatial truth). Three near-truth checks:
- `validate/phantom.py` — a **synthetic phantom** (known curved membrane + planted gold + planted
  true hits at known orientations) to measure a true FP-detection ROC and validate the fallback
  FFT-CC engine's calibration.
- `validate/holdout.py` — a small **hand-labeled** hold-out set of a few tomos as a spatially-labeled
  gold standard; report ROC separately from the weak-label agreement.
- `validate/reconstruction.py` — the ultimate proxy: does the **subtomogram average improve**
  (FSC/resolution) with the filter applied vs not? Closes the loop to reconstruction quality so the
  filter isn't just reproducing prior culls.

### 9.6 De-duplication for dense candidate sources (`DenseFieldPeakSource`)
Re-detecting hits from the dense field must not emit multiple candidates per particle.
`candidates/dense_source.py` applies **oriented non-max suppression** matching the csv's rotated
erase cylinder (`Peak_mRadius=[210,210,320] Å ≈ [16,16,26] vox`, rotated to each peak's own
orientation, SPEC §6) before emitting candidates, so dense candidate counts and any count-based
cluster statistics don't double-count a single particle.

---

## 10. Dense-field generation plan + phasing

Generation is a provider concern, so the pipeline is useful **immediately on existing convmaps** and
gains dense orientation/membrane fields later without touching constraints.

### 10.1 Angle field (SPEC §7 — recommended path b)
Patch the commented `BH_templateSearch3d_2.m:806` to a **mode-2 fp32** save of the already-computed
`RESULTS_angle` argmax volume: `SAVE_IMG(single(RESULTS_angle), anglesOUT);` — **never `'half'`**
(2592 > 2048). Recompile **salina-only** (`testScripts/mCompile.sh`, `skipMex=1`; watch the NFS
symlink attr-cache on `current_emClarity`). Re-run the 112-tomo bin5 search (recs + templates +
`_angles.list` + ctf/tilt geom all on disk). Output: one ~0.5 GB/tomo fp32 volume, voxel-exact to the
convmap, encoding best-angle (→ per-voxel normal via §5) **and** best-template. Do the
`measure_noise_variance=1` re-run in the same pass (→ `<base>_noise_variance.mrc`, §9.2).
`TorchCCAngleProvider` is the in-package fallback (SPEC §7c) if recompile is blocked — it must
replicate the per-orientation σ-normalization (divide each orientation's CC by its own std, no mean
subtraction, BH:640), apply the missing-wedge from tilt geometry, and match the rec bandpass, then
pass the §9.3 dense-vs-csv-normal acceptance test before its field is trusted.

### 10.2 Membrane field (SPEC §8)
`MembraneSearchProvider` builds a synthetic bilayer template — **physically parameterized**: two
density lamellae at the mito-membrane headgroup spacing, low-passed to 12.5 Å (bin5), in a **288³
box** (hard-fail on mismatch, rescaled to ~58³ internally). Run it as a **separate** membrane-only
search (avoids the combined-MIP masking caveat) → `membrane` (CC strength) + `membrane_normal`.
Bootstrap mito-membrane-vs-interior-vesicle labels via normal-coherence/closed-shell heuristics on
`bin10/*.rec` (the only substrate on disk), validated by the phantom (§9.5).

### 10.3 Phasing — what to build first
- **Phase A (existing convmaps only, no re-run):** `core/` + `emclarity/` + `ConvmapProvider` +
  `CsvPeakSource` + `BackgroundModel` calibration + `SurfaceCoherenceConstraint` on **sparse csv
  normals** + `GoldIceClusterConstraint` on the dense `cc` field + `GoldFiducialProvider` +
  `scan` + `.mat` writeback. End-to-end csv+cc filter on day one.
- **Phase B (after the salina re-run):** `AngleIndexLoader` + `NormalFieldProvider` +
  `NoiseVarLoader`/`SnrFieldProvider` + dense (CC-gated) curvature + `DenseFieldPeakSource`. Swap
  sparse→dense normals via YAML; zero constraint changes.
- **Phase C:** `MembraneSearchProvider` + `MembraneGeometryConstraint`; then the `optimize` layer
  (feature cache + joint tuner + self-sup objective) and `validate/`.

---

## 11. Parallel / GPU strategy (100+ tomos, 662×942×448 fp16)

Three nested, optional levels:
1. **Across tomos (primary, embarrassingly parallel).** `exec/cluster.py` maps a per-tomo job over
   the 112 tomos via GNU `parallel --sshlogin` across **etna 3 + siracusa 3 + salina 2 = 8 GPUs**,
   GPU-pinned `CUDA_VISIBLE_DEVICES={%} % ngpu`, the `ENV_SETUP` PATH/IMOD prelude for SSH jobs,
   `--joblog --resume`, `--wd .` on the shared `/scratch`+`/sa_shared` mounts — mirroring the repo's
   `cluster.py`. `LocalProcess` (joblib) for a single multi-GPU host. Resumable via per-tomo done
   sentinels + the content-addressed field/feature cache (a tomo whose cache exists is skipped).
2. **Within a volume (chunked, halo-aware).** `core/chunking.py::BlockPlan` tiles each
   662×942×448 volume into halo-padded blocks (halo ≥ max constraint reach: cluster/coherence radius,
   the [16,16,26] erase cylinder) so cluster/EDT/coherence/Hessian ops stream through GPU memory
   without loading 0.5–1 GB at once; per-block fp16→fp32 cast. Union-find merges cluster labels across
   seams (§3). Peak host RSS ≈ a few blocks, not a volume — critical on the **125 GB hosts**
   (siracusa/salina), which are memory-bound (CLAUDE.md).
3. **Backend shim.** `core/backend.py` picks torch (FFT-CC generation, `grid_sample` trilinear),
   cupy (`cupyx.scipy.ndimage`: map_coordinates, EDT, connected components), or numpy/scipy fallback
   (CPU-only / CI).

**RAM discipline:** per-host worker caps are config-driven (etna higher; siracusa/salina lower) with
a live `free -g` guard — **no fixed blanket cap** (CLAUDE.md); dense-field *generation* (FFT-CC,
membrane search) is the RAM/VRAM hog and gets a conservative per-host job count, like TM. The
**train step is cheap and single-node**: features are cached (few MB/tomo), so the whole search's
matrix (136 k csv candidates × ~20 features, or millions of dense candidates) fits in GPU memory on
one host and the optimizer never touches a volume.

**Resource budget (size before the first run):** one convmap = 559 MB; a whole tomo's fields
(cc+angle+normal+membrane) ≈ 1.5–2 GB → land generated fields on `/scratch/salina` (~6.9 T free),
~200 GB total for 112 tomos. Block+halo of e.g. 128³+16 → ~10 MB fp32/block → per-worker peak RSS a
few hundred MB, safe at ≥6 workers on the 125 G hosts. The emClarity re-run is "hours across 8 GPUs"
(params exist). A tuning sweep is GPU map-reduce over cached matrices → minutes/trial, not volume
I/O.

---

## 12. Dependencies & venv plan

Own venv at `/sa_shared/git/emClarity_private/mito_filter/.venv`, editable install, independent of the
parent package.

```
python >= 3.12
# runtime core
numpy, scipy, mrcfile, pyyaml, typing-extensions
# GPU / fields / model
torch                 # differentiable combiner head, FFT-CC generation, grid_sample sampling
cupy-cuda12x          # [gpu] cupyx.scipy.ndimage: EDT, CC, map_coordinates (matches repo CUDA 12)
# features / tabular cache
pandas, pyarrow       # cached FeatureMatrix (parquet)
# optimize
optuna                # primary black-box tuner (TPE/CMA-ES); scipy.optimize as fallback
scikit-learn          # baselines, metrics, mixture model (self-supervised objective)
# membrane/segmentation bootstrap + validation
scikit-image          # Frangi/Hessian, marching cubes, EDT reference
h5py                  # v6 .mat snapshots (scipy loadmat fails CRC, SPEC §10)
# dev
black, isort, flake8, mypy, pytest, pytest-cov
```

`pyproject.toml`: `[project.optional-dependencies]` `gpu=["cupy-cuda12x"]`, `dev=[...]`;
`[project.scripts] mito-filter="mito_filter.cli:main"`; black/isort line-length 100.
`setup.cfg`: flake8 `max-line-length=100`; mypy `strict=True`, `python_version=3.12`; ship `py.typed`.
Base deps stay CPU-installable (torch/cupy in the `gpu` extra) so a CPU-only checkout still installs
and runs the unit tests.

Setup:
```bash
cd /sa_shared/git/emClarity_private/mito_filter
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[gpu,dev]"
```

---

## 13. Reproducibility & config

- **Config-driven:** `configs/round_4.yaml` lists `dataset`, `providers`, `candidate_source`,
  `constraints`, `combiner`, `writeback`; `!include` pulls reusable constraint fragments; read once
  into typed dataclasses (`config.py`).
- **Run manifest** (`manifest.py`): every scan/optimize writes `run_manifest.json` — resolved config,
  git rev of **both** mito_filter and emClarity, param + input-file hashes/mtimes, backend/device,
  field-cache keys. Every verdict is traceable to the exact fields and params that produced it.
- **Content-addressed field/feature cache** keyed on `(provider, params, source-mtimes)` → generated
  fields and feature matrices reused across runs and across Layer-2 trials that don't touch generation
  params (the big tuning speedup).
- **Golden-value tests** lock the SPEC constants (`|MMᵀ−I|`, `csv/5==.pos` to 6e-7, packed-index→
  normal to 6.4e-5, `558,750,208`-byte size, mode-12 refusal for packed idx) so a refactor can't
  silently break the adapter.

---

## 14. Ordered build plan (parallel-agent decomposable)

See `build_phases` in the structured output. Phase P0 (core + emclarity adapter + tests) has no
internal cross-file dependencies beyond `core/registry.py` and `emclarity/constants.py`, so its files
fan out to parallel agents. Each later phase depends only on the interfaces (ABCs) frozen by P0/P1,
so providers, constraints, features, and datasets are independently implementable once the ABCs land.

---

## 15. Top risks & mitigations

1. **Angle/membrane fields need a salina-only MATLAB recompile + 112-tomo re-run** (SPEC §7/§8), with
   the NFS symlink attr-cache stale-binary trap. → Providers make load-vs-generate swappable; Phase A
   is fully useful on sparse csv normals + dense cc today; `TorchCCAngleProvider` is the fallback;
   verify `readlink -f $(command -v emClarity)` before the re-run.
2. **fp16 packed-index corruption** (2592 > 2048). → `emclarity/mrc_io.py` hard-refuses mode-12 for
   any `IndexField`; asserts fp32/int16; golden test.
3. **No spatial ground truth; weak labels are circular.** → Self-supervised physics objective is
   primary; weak labels secondary; the `validate/` loop (phantom + hand-labeled hold-out + FSC) is
   the real check; hold-out tomos guard overfitting.
4. **Dense normal field = argmax-of-noise in background; gold halo corrupts nearby normals.** → §9.3:
   CC-gate all dense-normal ops, subtract gold/cluster mask before surface fitting, dense-vs-csv
   acceptance test, template-consistency check.
5. **Calibration doesn't transfer across tomos/searches.** → §9.2: SNR provider (noise-variance
   re-run) + per-tomo `BackgroundModel` z-score; `FittedConfig` stores calibration stats.
6. **`.mat` unreadable by scipy; positions drift.** → §9.1: MATLAB-on-salina write keyed by
   subtomo_id / angle triple; v6 snapshots / templateIDX for labels; csv col26 is debug-only.
7. **Combined-MIP membrane masking** (SPEC §8). → default to a separate membrane-only search;
   combined-vs-separate is a provider flag.
8. **RAM/VRAM OOM on 125 G hosts during dense generation** (TM history). → chunked halo streaming +
   config-driven per-host worker caps + live `free -g` guard; generate-once-cache amortizes it.
9. **Cross-block cluster split.** → union-find seam merge (§3); unit test on a straddling cluster.
