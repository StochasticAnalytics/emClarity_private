# mito_filter

Cryo-ET template-matching (TM) false-positive spatial/orientation filter.

`mito_filter` decides whether a template-matching hit is a false positive by reasoning about the
known spatial layout of the hits — position **and** orientation — read primarily from the dense 3D
convmap cross-correlation volume (and generated dense angle / membrane fields), not the lossy csv.

See `docs/DESIGN.md` (architecture + status), `docs/STATUS.md` (what is built + validated on real
data + known limitations), and `docs/SPEC.md` (authoritative emClarity TM data/format spec).

## What is built

- **Phase A — spatial filter (dense cc).** Gold/ice compact-cluster + surface-coherence
  (incoherent-normal) + isolation constraints on the dense convmap, per-tomo background
  calibration, gold-fiducial proximity, resumable per-tomo scan, and `.mat`/csv-col26 writeback.
- **Phase B — dense orientation.** Decode the packed dense angle volume to a per-voxel outward
  normal (`NormalFieldProvider`), CC-gate it, and swap the surface features from the sparse csv
  normal to the dense field via one YAML line.
- **Joint optimizer.** Featurize all 112 convmaps to a parquet cache, then jointly tune every
  constraint parameter + the fusion head against a self-supervised objective. The tuned result is
  `configs/round_4_fitted.yaml`. (On this data the label-free tune is degenerate — the shipped
  default is the physics head below, not a self-supervised fit; see `docs/STATUS.md`.)
- **Phase C — membrane reference.** Segment membrane sheets straight from the tomogram
  reconstruction (`rec`) by Hessian sheetness, take the signed EDT, and score four membrane
  features (distance / inside-outside sign / closed-shell curvature / template-vs-membrane facing)
  with the `membrane_geometry` constraint. Config: `configs/round_4_membrane.yaml`.
- **Physics head, gold/ice-dominant (the shipped filter, DEFINITIVE full-112 validation).** The
  false-positive axes rebuilt to read their real physical signatures directly from the dense convmap
  CC + angle + rec (gold/ice = a peak inside a compact cluster of extreme-CC voxels, detected at
  `bg + 8σ` via a 250 Å top-hat; membrane interior-vesicle geometry; de-saturated isolation;
  dense-normal surface coherence), weighted by **measured** discriminative power — gold/ice-dominant,
  **not** fitted to the classification labels. Validated over **all 112 tomos** against the round_4
  classification cull as independent ground truth: gold/ice **axis ROC-AUC 0.681** vs the union cull
  (**0.748** vs the round-1/cyc2 gold-ice cull it targets), **fused 0.657**, OR 4.06, precision 0.826,
  keeps 84.6 % of survivors — up from the old dead-axis 0.535. **Two configs:**
  **`configs/round_4_goldice.yaml`** (the fast validated workhorse — cheap features, use in
  production) and **`configs/round_4_fitted_v2.yaml`** (the full physics head with membrane /
  surface interpretability; sibling `configs/round_4_physics.yaml`). See `docs/STATUS.md`.

## Layout

- `src/mito_filter/core/` — domain-free reusable grid/field/point/registry/backend tools.
- `src/mito_filter/emclarity/` — quarantined emClarity-convention adapter (constants, IO, matrix
  conventions), locked by golden-value tests.
- `src/mito_filter/fields/` — `FieldProvider`s (load OR generate/derive dense fields).
- `src/mito_filter/candidates/`, `features/`, `constraints/`, `model/` — the filter pipeline.
- `src/mito_filter/scan/`, `optimize/`, `validate/` — the two drivers and the validation loop.

## Setup

The package lives in its **own venv** (`./.venv`), independent of the parent `emclarity` package,
so it is free to pull scipy / scikit-image / optuna / pyarrow.

**Python 3.12 is required** and, on this cluster, is only present on **salina** (`/usr/bin/python3.12`;
etna is 3.8, siracusa is 3.10 — neither has 3.12). Create and drive the venv on salina:

```bash
make venv        # python3.12 -m venv .venv + editable-install with dev extras (CPU-only)
make fmt         # isort + black @ line-length 100
make lint        # flake8
make type        # mypy src
make test        # pytest
```

The CPU path (numpy / scipy / scikit-image) works with no GPU. GPU extras are optional:

```bash
.venv/bin/pip install -e ".[gpu,dev]"   # add torch + cupy-cuda12x later
```

## The `mito-filter` CLI

`mito-filter <scan|optimize|gen-field|writeback|validate>`. **`scan` is wired end-to-end**; the
other subcommands dispatch to their driver module when it exposes a `main`, else print a clear
not-yet-wired message (the optimize loop is driven programmatically today — see below).

### Run a scan

```bash
.venv/bin/mito-filter scan \
    --config configs/round_4_goldice.yaml \
    --data-dir /scratch/salina/round4_angle_rerun/convmap_wedgeType_2_bin5 \
    --work-dir ./run_round4 \
    --jobs 4
# round_4_goldice.yaml = the fast validated workhorse (~5-30 s/tomo). Swap in
# round_4_fitted_v2.yaml for the full physics head (surface + membrane; ~20 min/tomo).
# --data-dir overrides the config's dataset; --limit N for a debug subset;
# --dry-run to discover + report only; --force to ignore per-tomo done sentinels.
```

Per tomogram it fits the background (`meta.calibrate`), runs the forward filter, and writes a
col26 debug csv + a subtomo-id-keyed removal JSON into `<work-dir>/scan_out/` (resumable via
per-tomo done sentinels). `writeback` behaviour is controlled by the config's `writeback:` block
(`debug_csv`, `removal_json`, and optionally `mat_apply`/`mat_path`/`cycle` to write the
authoritative subTomoMeta `.mat` col26 directly).

## Config files

All configs are plain YAML; `features` are `FEATURE_REGISTRY` names and `constraints` are
`CONSTRAINT_REGISTRY` names, each a bare string or a `{name, **params}` stanza (DESIGN §3).

| config | what it does |
| --- | --- |
| `round_4.yaml` | **Phase A** — existing convmaps only, no re-run. Sparse csv candidates + dense `cc`; gold/ice-cluster + surface-coherence (on **sparse csv normals**) + isolation. The day-one filter. |
| `round_4_dense.yaml` | **Phase B** — same recipe, but the surface features consume the **dense per-voxel normal field** (`angle` → `normal`) with CC-gating instead of the csv normal. One YAML swap, zero constraint changes. |
| `round_4_fitted.yaml` | **The old tuned filter.** The joint optimizer's output over all 112 convmaps. **Superseded** — its cross-tab fused ROC-AUC was only 0.535 (its gold/ice axis was dead: fired on 16/136,418 hits). Kept for provenance; not the default. |
| `round_4_membrane.yaml` | **Phase C** — adds the membrane-reference geometry: segments membranes from the `rec` (`rec_dir: /scratch/salina/alt_cache`), derives `membrane_sdf`, and adds the four membrane features + the `membrane_geometry` constraint on top of the round_4 base. |
| **`round_4_goldice.yaml`** | **The fast validated workhorse — use in production.** Lean gold/ice-dominant head (gold/ice cluster + light isolation only; cheap CC + candidate-position features, ~5–30 s/tomo — drops the slow surface/membrane decodes). Weights mirror the physics head exactly on the two kept axes (`w = [-3,-0.3]`, bias +1.5). **DEFINITIVE full-112 validation:** gold/ice axis ROC-AUC **0.681** vs the union cull (**0.748** vs the round-1/cyc2 cull it targets), fused **0.657**, OR 4.06, precision 0.826, keeps 84.6 % of survivors. |
| `round_4_fitted_v2.yaml` | **The full physics head** (identical to `round_4_physics.yaml`). All four FP axes live + physically-directed; gold/ice-dominant head (`w = [-3,-1,-0.3,-0.5]`, bias +1.5) set from measured discriminative power, **not** fitted to labels. Adds the dense-normal surface-coherence + membrane interior-vesicle diagnostics (~20 min/tomo) for interpretability; holds beyond 11 tomos (fused 0.666 on 19 full-feature parquets) but does **not** beat the lean head on this data. |
| `round_4_physics.yaml` | Documented sibling of `round_4_fitted_v2.yaml` (identical head): carries the full per-axis physics rationale in comments + the fp-logit `combiner:` documentation block. |

## The joint optimize over a search

The optimizer is a two-step, fan-out-then-tune flow (there is no single `optimize` CLI entry yet;
it is driven from Python, and produced `round_4_fitted.yaml`).

**1. Build the per-tomo feature cache** (embarrassingly parallel; fan out `--index/--total` across
salina — the only 3.12 host — one slot per core):

```bash
.venv/bin/python -m mito_filter.optimize.feature_cache \
    --data-dir /scratch/salina/round4_angle_rerun/convmap_wedgeType_2_bin5 \
    --config   configs/round_4.yaml \
    --cache-dir ./feat_cache \
    --index 1 --total 8            # run slots 1..8 in parallel
```

**2. Tune jointly and save a fitted config:**

```python
from mito_filter.optimize.dataset import SearchDataset
from mito_filter.optimize.objective import Objective        # self-supervised primary objective
from mito_filter.optimize.tuner import Tuner
from mito_filter.model.filter_model import FilterModel       # built from the config's constraints

dataset = SearchDataset.from_cache_dir("./feat_cache")
tuner   = Tuner(model, Objective(...))                       # ParameterSpace.from_model(model)
result  = tuner.fit(dataset, n_trials=200)                   # searches theta + tau, builds a report
result.config.save("configs/round_4_fitted.yaml")           # -> the fitted YAML scan consumes
```

`FittedConfig.save/load` round-trips the yaml; the `meta.report` block records the separation /
keep-rate / objective components at the best theta.

## Add a NEW constraint / field

The registry + YAML design means a new discriminator is three small isolated additions — a
`FieldProvider` (load or generate a dense field), a `FeatureExtractor` (sample it per candidate),
and a `Constraint` (score it) — with **no edit to `core/` or either driver**. Register the three
`@register_*` classes, add a stanza to a config, and re-run `optimize` to fit the new parameters
jointly. The membrane geometry (`fields/derived.py:MembraneDistanceProvider` →
`features/membrane.py` → `constraints/membrane.py` → `configs/round_4_membrane.yaml`) is a live
worked example; **DESIGN §7.1** walks the pattern end-to-end with a traced-membrane variant. A
provider whose input is absent for some tomos reports `MISSING` → the dependent constraint goes
neutral for those candidates (DESIGN §5 mixed-availability rule), so partial datasets still work.
