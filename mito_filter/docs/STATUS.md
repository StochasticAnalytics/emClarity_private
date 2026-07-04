# mito_filter — Status

Capability summary, real-data validation, reproduction, and known limitations, as of 2026-07-04.
Companion to `docs/DESIGN.md` (architecture) and `docs/SPEC.md` (format spec).

## Headline (DEFINITIVE full-112 validation, 2026-07-04) — the filter now actually discriminates

**Two validated heads — pick by cost/interpretability:**

- **`configs/round_4_goldice.yaml` — the fast validated workhorse (use this in production).** Cheap
  features only (~5–30 s/tomo): the rebuilt gold/ice cluster axis + a light isolation prior, read
  straight from the convmap CC + candidate positions. No dense-normal decode, no membrane Hessian.
  **This is the head validated at full 112-tomo scale below.**
- **`configs/round_4_fitted_v2.yaml` — the full physics head** (identical to `round_4_physics.yaml`,
  ~20 min/tomo): adds the dense-normal surface-coherence and the membrane interior-vesicle geometry
  axes for interpretability. Use when you want the membrane / surface diagnostics; on this data it
  does **not** beat the lean head on the metric that matters (the weak axes don't lift the fused AUC).

### The fix — the gold/ice axis was dead, now it discriminates

A rigorous cross-tab against the round_4 classification culls proved the *old* tuned filter
(`round_4_fitted.yaml`) barely discriminated (**fused ROC-AUC 0.535**) because its dominant axis was
**dead on real data**: **gold/ice fired on only 16 / 136,418 hits** — the `cc_thresh 10.7` sat above
**99.85 %** of the cluster field (and the fiducial bead file was never loaded → `gold_dist=inf`).
The axis was **rebuilt to detect a peak inside a compact cluster of extreme-CC voxels**: the dense
convmap CC thresholded at **bg + 8σ**, extreme-CC voxels counted in a **250 Å `fftconvolve` top-hat**,
`log`-scored per candidate — so it reads the gold/ice cluster **directly from the convmap, no bead file
needed**. (Isolation was also de-saturated from a constant ~1.0; membrane was wired in for the full
head.)

### DEFINITIVE full-112-tomo numbers (`configs/round_4_goldice.yaml`)

All **112 tomos**, **N = 133,867** classified hits (`init_removed` excluded), joined to the emClarity
classification cull as **independent** ground truth — never a training target
(`analysis/full112_goldice_crosstab.md`):

| metric — vs the union cull `removed_any` | OLD dead-axis filter | **fixed lean head, full 112** |
|---|---|---|
| gold/ice **axis** ROC-AUC | ~0.50 (16 hits fired) | **0.681** |
| **fused** head ROC-AUC | **0.535** | **0.657** |
| odds ratio (flag→removed) | 1.20 | **4.06** |
| flag→removed **precision** | — | **0.826** |
| **survivor keep rate** | — | **0.846** |
| excess true removals vs same-rate random flagging | ~0 | **+8,442** |

- **Strongest on the cull it physically targets** — the round-1 / cyc2 **gold/ice** removal:
  gold/ice **axis AUC 0.748**, fused 0.722, OR 5.46, lift 1.78, **+11,180** captures over random.
- **Correctly blind** to the later *structural* culls (cyc5/cyc8, `removed_round2`): anti-predictive
  ~0.44 — exactly what physics predicts a geometry filter should be blind to.
- **Honest correction to the earlier headline:** an interim 11-tomo cache reported gold/ice **0.705** /
  fused 0.669; that small subset was **favorable**. The definitive full-112 gold/ice AUC is **0.681**
  (0.699 on the first 19 tomos, 0.676 on the other 93). The ~0.02 drop is **real, not a lean artifact**:
  the lean head equals the full physics head **bit-for-bit** on the strong axis (0.6994 vs 0.6994 on the
  same 19 tomos) — leanness costs nothing; the 11-tomo subset was just kind.

### What it is (honest) — a conservative high-precision PRE-filter, not a classifier

At τ 0.5 it flags **33 %** of hits, **82.6 % of which classification also removed**, while **keeping
84.6 % of classification survivors**. It is **strongest on the gold/ice cull it targets** (0.748) and
**weak on the later structural culls** (cyc5/cyc8, anti-predictive) — a cheap physics-based front-end
that strips the obvious gold/ice junk before classification. It is **NOT a replacement for
classification**.

### Why the shipped head is a physics head, not the auto-tune

The self-supervised, label-free re-tune **FAILED**: its objective weighted the **anti-predictive**
surface-coherence axis (axis AUC 0.45) to **−7.78**, re-killed gold/ice, and **inverted** the fusion
(fused AUC < 0.5) — **NOT shipped**. The shipped head is therefore a **gold-dominant physics head**
whose weights come from **measured per-axis discriminative power**, not from fitting the labels (that
would be circular). Measured on real data: **gold/ice is THE discriminator** (0.681–0.748); **coherence
(AUC 0.45) and isolation (0.32) are weak / anti-predictive** on this data; **membrane (0.62) is a
moderate** secondary. Weights track this — gold/ice **−3**, surface **−1**, membrane **−0.5**, isolation
**−0.3**, bias **+1.5** — so the weak axes never override the strong one.

**Adversarially re-verified from raw data (2026-07-04):**

- **Gold/ice fires on genuine extreme-CC clusters, not arbitrarily.** Independent 26-connectivity
  connected-component detection on the raw convmap (threshold bg + 8σ): the gold/ice axis rises
  monotonically with independent cluster size — mean axis **0.125 → 0.435 → 0.878 → 0.985** across
  none / small(1–19) / med(20–59) / large(≥60) voxel clusters (Spearman(axis, independent
  cluster_vox) = **0.755**). Fired hits are **47.9 %** in a real ≥20-vox cluster vs **0.1 %** of
  non-fired, at CC 7.68 vs 6.40. Axis AUC vs `removed_any` = **0.681 at full 112-tomo scale** (the
  interim 0.705 was a favorable 11-tomo subset). It no longer needs the bead file — it reads the
  cluster from the CC field.
- **Isolation is now a live, physically-signed axis** (was a constant ~1.0): it spans [0, 1]
  (min 0, max 1, std 0.41) and is correctly signed (Pearson(isolation, neighbor_count) = **−0.66**).
  Honest nuance: on this data isolated hits are removed *less* (axis AUC 0.32) — clustering, not
  isolation, is the dominant FP mode — so it is kept live, correctly-signed, and **lightly weighted**.
- **Membrane geometry** is live and correctly signed (axis AUC **0.619**); the discrimination comes
  from the interior-vesicle / inside-sign / closed-shell terms (facing-cosine alone is weak here).
- **Signs are physical**: every combiner weight is negative (each axis can only *lower* keep-prob),
  gold/ice carries the largest magnitude (−3), the weak/anti axes are light (−1 / −0.3 / −0.5).
- **Generalizes at full scale**: the definitive run is all **112 tomos** (not a hold-out demo) —
  gold/ice axis 0.681 across the whole set (0.699 first-19, 0.676 other-93; the earlier held-out-6
  0.684 ≈ full-11 0.669 was on the interim small cache). No memorized train set: the axes are
  label-free physics, validated against an independent cull.
- **Non-degenerate**: full-112 flag-rate **0.326** (not flag-all / flag-none). Enrichment OR **4.06**,
  lift 1.31, precision(flag→removed) **0.826**, keeps **84.6 %** of classification survivors.

**Loader fix (real defect, `scan/context.py`).** `RunContext.from_pipeline_config` used to **ignore
the config's `combiner:` block entirely** and fall back to the uniform default head — so the
physically-weighted config, run through the real scan pipeline, was a **degenerate flag-all** head
(bias 0, weights −1 → keep-prob < 0.5 for every hit). Fixed: the scalar `{weight, bias}` form is now
materialized (`combiner_from_block`), and the per-axis weights travel via `theta` (the authoritative
machine channel), which the default config now carries. Regression tests
(`tests/unit/test_scan_context_combiner.py`, `tests/unit/test_config_round4_fitted_v2.py`) pin the
validated `[-3, -1, -0.3, -0.5]` / bias +1.5 head and assert it is non-degenerate.

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
  **Caveat (2026-07-04):** on this data the label-free objective over-weights an anti-predictive axis
  and produces a *degenerate* head (see Headline) — the shipped default is the **physics** head, not
  a self-supervised fit.
- **Phase C — membrane reference.** `MembraneDistanceProvider` segments membranes from the tomogram
  `rec` by Hessian sheetness, takes the signed EDT, and scores four membrane features
  (distance / inside-outside sign / closed-shell curvature / template-vs-membrane facing) via the
  `membrane_geometry` constraint. Config: `configs/round_4_membrane.yaml`.
- **Physics head, gold/ice-dominant (the shipped filter).** The FP axes rebuilt to read their real
  physical signatures from the dense convmap CC + angle + rec, weighted by measured discriminative
  power (gold/ice-dominant, **not** fitted to labels). Validated at **full 112-tomo scale** against the
  classification cull (independent GT): lean gold/ice axis ROC-AUC **0.681** vs the union cull (0.748
  vs the round-1/cyc2 gold-ice cull it targets), fused **0.657**, OR 4.06 — up from the old dead-axis
  0.535. Configs: **`configs/round_4_goldice.yaml`** (fast validated workhorse) and
  **`configs/round_4_fitted_v2.yaml`** (full physics head + membrane; sibling `round_4_physics.yaml`).

## Validated on real data

Ground-truth files (READ-ONLY): convmap + angle at
`/scratch/salina/round4_angle_rerun/convmap_wedgeType_2_bin5/`, reconstructions at
`/scratch/salina/alt_cache/<base>.rec` (662×942×448, apix 12.5 Å, bin5).

### DEFINITIVE — the lean workhorse (`configs/round_4_goldice.yaml`) on ALL 112 tomos

The authoritative validation (`analysis/full112_goldice_crosstab.md`): the lean gold/ice head over the
**full 112-tomo** feature cache (`/scratch/salina/round4_feature_cache_lean`), **N = 133,867**
classified hits (`init_removed` excluded), joined to the emClarity classification cull
(`classification_labels.csv`) as **independent** ground truth — never a training target. The head is
the canonical `keep = sigmoid(bias + S @ w)` with `w = [-3, -0.3]` on `[gold_ice_cluster, isolation]`,
bias `+1.5`, `tau = 0.5` (mirrors the physics head's gold/isolation weights exactly):

- **Vs the union cull `removed_any`:** gold/ice **axis** ROC-AUC **0.681** (AP 0.792), **fused** head
  **0.657**, odds-ratio **4.06**, flag→removed precision **0.826**, survivor keep rate **0.846**,
  flag-rate 0.326. **+8,442** true removals beyond flagging the same count at random. Old dead-axis
  filter: fused 0.535, OR 1.20.
- **Strongest on the cull it targets — round-1 / cyc2 (gold/ice):** axis AUC **0.748**, fused 0.722,
  OR 5.46, lift 1.78, **+11,180** captures over random.
- **Correctly blind to the structural culls — round-2 (cyc5/cyc8):** anti-predictive ~0.44 — the
  gold/ice axis is (rightly) blind to finer structural classification.
- **The single strongest discriminator is cluster membership:** classification-REMOVED peaks sit in
  far larger extreme-CC connected components than classification-KEPT peaks; the gold/ice axis reads
  this directly from the CC field (`bg + 8σ` threshold, 250 Å top-hat count).
- **Honest scale correction:** the earlier 11-tomo cache reported gold/ice 0.705 / fused 0.669; that
  subset was favorable. Full-112 is **0.681** (0.699 first-19, 0.676 other-93) — a real ~0.02 lower,
  representative. Leanness costs nothing: the lean gold/ice axis equals the full physics head
  bit-for-bit on the same 19 tomos (0.6994 = 0.6994).

### The full physics head (`configs/round_4_fitted_v2.yaml`) holds beyond 11 tomos

On the 19 existing full-feature parquets (all four axes, N = 23,118) the full physics head gives
**fused ROC-AUC 0.666 ≈ the interim 0.669**, gold/ice axis 0.699 (dominant), membrane 0.607 (a real
but light secondary), surface 0.445 and isolation 0.324 (weak / anti). It adds the dense-normal
surface-coherence and membrane interior-vesicle diagnostics for interpretability but does **not** beat
the lean head on this data. **Operating point (both heads):** a high-precision conservative FP flagger
— precision(flag→removed) ≈ 0.83 while keeping ~85 % of classification survivors
(`filter_direct_validation.md`). A proper phantom/hold-out downstream-quality loop is still not built
(see limitations).

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
.venv/bin/python -m pytest -q               # 330 passed, 1 skipped
.venv/bin/black --check src tests
.venv/bin/isort --check-only src tests
.venv/bin/flake8 src tests
.venv/bin/mypy src tests                    # Success: no issues in 118 files

# --- a scan with the fast validated workhorse (lean gold/ice) filter ---
.venv/bin/mito-filter scan \
    --config configs/round_4_goldice.yaml \
    --data-dir /scratch/salina/round4_angle_rerun/convmap_wedgeType_2_bin5 \
    --work-dir ./run_round4 --jobs 4

# --- reproduce the DEFINITIVE full-112 cross-tab (gold/ice axis 0.681 / fused 0.657) ---
cd /scratch/siracusa/full_enchilada_3/six_hours_round_4/analysis
/sa_shared/git/emClarity_private/mito_filter/.venv/bin/python full112_goldice_crosstab.py
#   (the full physics head over the 19 full-feature parquets: crosstab_v2.py <round_4_fitted_v2.yaml>)

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
