# mito_filter — Status

Capability summary, real-data validation, reproduction, and known limitations, as of 2026-07-03.
Companion to `docs/DESIGN.md` (architecture) and `docs/SPEC.md` (format spec).

## What the package does

`mito_filter` flags false-positive template-matching hits from an emClarity TM search by reasoning
about the spatial + orientational layout of the hits — read primarily from the **dense convmap CC
volume** and generated dense **angle→normal** and **membrane** fields, not the lossy csv. It is a
registry + YAML pipeline: `FieldProvider`s (load or generate/derive dense fields) → per-candidate
`FeatureExtractor`s → parametric `Constraint`s → a fusion head that outputs a keep-probability, with
two drivers over one shared core — **`scan`** (apply a fitted filter, write verdicts back to the
subTomoMeta `.mat` / csv col26) and the **joint optimizer** (tune every parameter over a whole
search against a self-supervised objective).

### Built and passing

- **Phase A — spatial filter.** Gold/ice compact-cluster (dense `cc`), surface-coherence
  (incoherent-normal + residual + curvature), and isolation constraints; per-tomo `BackgroundModel`
  calibration; gold-fiducial proximity; resumable per-tomo `scan`; `.mat`/col26 writeback.
  Config: `configs/round_4.yaml`.
- **Phase B — dense orientation.** `NormalFieldProvider` decodes the packed angle volume to a
  per-voxel outward normal; the surface features swap from the sparse csv normal to the CC-gated
  dense field with one YAML line. Config: `configs/round_4_dense.yaml`.
- **Joint optimizer.** `optimize/` feature cache (parquet, fan-out) + `Tuner` + the composite
  self-supervised `Objective`. Tuned over all **112 convmaps** → `configs/round_4_fitted.yaml`.
- **Phase C — membrane reference.** `MembraneDistanceProvider` segments membranes from the tomogram
  `rec` by Hessian sheetness, takes the signed EDT, and scores four membrane features
  (distance / inside-outside sign / closed-shell curvature / template-vs-membrane facing) via the
  `membrane_geometry` constraint. Config: `configs/round_4_membrane.yaml`.

## Validated on real data

Ground-truth files (READ-ONLY): convmap + angle at
`/scratch/salina/round4_angle_rerun/convmap_wedgeType_2_bin5/`, reconstructions at
`/scratch/salina/alt_cache/<base>.rec` (662×942×448, apix 12.5 Å, bin5).

### The tuned round_4 filter (`configs/round_4_fitted.yaml`, `meta.report`)

Fit over the whole search — **112 tomograms, 136,418 hits**, 200 optuna trials (best objective
0.00303):

- **Flag rate.** At the fitted threshold `tau = 0.701`, keep-rate = **0.332** (mean keep-prob
  0.366) → **~66.8 % of hits flagged as false positive** across the search. (Aggressive — the fit is
  dominated by the physics term below; a production run can raise `tau` to flag a smaller tail.)
- **Dual-axis separation** — the objective is a two-axis composite:
  - *Axis 1, self-supervised physics* (weight 1.0): target-vs-FP keep-prob **separation = 0.579**
    (physics-anchored targets kept, physics-anchored FPs rejected), align margin −0.373.
  - *Axis 2, weak labels* (weight 0.25): BCE = 0.812 over **78,059 weak negatives** (templateIDX==1
    / col26 −9999); their mean keep-prob is **0.374** (pushed toward reject). There are **0 weak
    positives** — the labels are negatives-only.
- **Fusion head (logit).** `gold_ice_cluster +1.41`, `surface_coherence −7.10`, `isolation +7.43`,
  bias −5.01 — the optimizer leans hardest on the surface-coherence and isolation geometry.
- **Generalization.** The fit is over *all* 112 convmaps with no held-out split recorded; its
  transfer claim rests on the **label-free** physics objective (self-supervised separation, not a
  memorized train set), not on a train/test gap. A proper hold-out / phantom validation loop is not
  yet built (see limitations).

### Membrane segmentation (`H99_2_100_1_bin5`, independently re-run this session)

- Hessian sheetness (`membrane_segmentation`, sigma 1.6 vox, 99.3-pct) on the real `rec`:
  **269,729 membrane voxels (0.097 % of the volume)** in ~77 s; signed EDT in ~72 s, range
  −2.2 … +176.7 vox.
- The segmentation is **fragmented**: **2,373 connected components** (largest ~25.8 k vox), and the
  signed-EDT **inside fraction is only ~0.001** — i.e. very few *closed* shells, so the
  interior-vesicle (`inside_outside_sign` / `closed_shell`) signal is weak on this tomogram.
- Against the real csv hits: median distance to the nearest membrane is **506 Å**, and only
  **49 / 1249 hits (3.9 %)** fall within the 75 Å on-membrane shell. At those on-membrane hits the
  template-vs-membrane **facing median is 0.27** (weakly positive), not a clean outer-membrane
  alignment.
- **Honest verdict:** the membrane machinery is correct and neutral-safe (a hit with no nearby
  segmented membrane contributes nothing, per DESIGN §5), but on the *current sparse csv hit set* it
  is **mostly inert** and its per-hit discrimination is weak. It is wired, tested, and ready to
  strengthen (denser candidate source, a dedicated membrane search, or better sheet segmentation),
  but it does not, today, add a strong axis of separation on this data. Reported as-is rather than
  claimed as a win.

## How to reproduce

Run on **salina** (the only Python-3.12 host — see DESIGN §16.1). All paths below are READ-ONLY
inputs; nothing under `/scratch` is modified.

```bash
cd /sa_shared/git/emClarity_private/mito_filter
make venv                                   # python3.12 venv + editable install (once)

# --- test / lint / type gate ---
.venv/bin/python -m pytest -q               # 288 passed, 1 skipped
.venv/bin/black --check src tests
.venv/bin/isort --check-only src tests
.venv/bin/flake8 src tests
.venv/bin/mypy src tests                    # Success: no issues in 114 files

# --- a scan with the tuned filter ---
.venv/bin/mito-filter scan \
    --config configs/round_4_fitted.yaml \
    --data-dir /scratch/salina/round4_angle_rerun/convmap_wedgeType_2_bin5 \
    --work-dir ./run_round4 --jobs 4

# --- membrane geometry on one tomo (Phase C) ---
.venv/bin/mito-filter scan \
    --config configs/round_4_membrane.yaml \
    --data-dir /scratch/salina/round4_angle_rerun/convmap_wedgeType_2_bin5 \
    --work-dir ./run_membrane --limit 1
```

The joint optimize (feature-cache fan-out + `Tuner.fit` → `FittedConfig.save`) is in the README
("The joint optimize over a search"); it regenerates `configs/round_4_fitted.yaml`.

## Known limitations

1. **Weak labels are negatives-only, no per-hit ground truth.** There is **no spatial ground truth**
   for which TM hits are real. Supervision is the label-free physics objective plus **negatives-only**
   weak labels (templateIDX==1 / col26 −9999; 78,059 negatives, 0 positives in round_4). True per-hit
   labels would require reading the subTomoMeta `.mat` (scipy cannot; needs the MATLAB-on-salina path,
   DESIGN §9.1) and a hand-curated set. So AUC/AP against real positives is unavailable, and the
   reported separation is physics/weak-label separation, not a labeled accuracy.
2. **No held-out generalization split.** `round_4_fitted.yaml` is fit over all 112 convmaps; the
   `validate/` downstream-quality loop (phantom + hold-out + FSC, DESIGN §9.5) is a namespace stub
   only. Generalization is argued from the self-supervised objective, not measured.
3. **Membrane signal is weak on the current data** (see above): fragmented Hessian segmentation, few
   closed shells, ~4 % of csv hits near a membrane, median on-membrane facing 0.27. The constraint is
   ready but low-yield until the candidate source is denser or the segmentation is improved; the
   originally-planned dedicated synthetic-bilayer membrane search (DESIGN §10.2) was **not** built —
   the simpler rec-segmentation path was used instead.
4. **Cross-host Python heterogeneity — salina only.** The venv needs Python 3.12, present only on
   salina (etna 3.8, siracusa 3.10). So the CLI, tests, and the feature-cache fan-out run on salina
   only; the feature extraction does not spread across hosts like the emClarity split stages. Fix by
   a shared relocatable 3.12 on `/sa_shared`, or lowering the floor to 3.10 (DESIGN §16.1).
5. **`NormalFieldProvider` is memory-heavy — ~31.7 GB RSS/tomo** (measured, DESIGN §16.2), so
   dense-orientation / membrane-facing concurrency is capped at ~3 tomos even on salina's 125 GB.
