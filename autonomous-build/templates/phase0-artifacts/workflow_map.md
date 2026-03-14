# emClarity Workflow Map for GUI Development

Based on thorough analysis of the following key files:

- **Entry point**: `/workspaces/cisTEMx/testScripts/emClarity.m` (1344 lines)
- **Parameter parser**: `/workspaces/cisTEMx/metaData/BH_parseParameterFile.m` (1183 lines)
- **Key processing functions** across `alignment/`, `ctf/`, `statistics/`, `synthetic/`, `transformations/`, and `metaData/`

---

## 1. All Available Commands

| Command | Category | GPU? | Param File? | MATLAB Function | Source File |
|---------|----------|:---:|:---:|---------|-------------|
| `help` | System | No | No | (inline) | `emClarity.m:224` |
| `check` | System | No | No | `BH_checkInstall()` | `metaData/BH_checkInstall.m` |
| `autoAlign` | Tilt-Series | Yes | Yes | `BH_runAutoAlign()` | `alignment/BH_runAutoAlign.m` |
| `ctf estimate` | Tilt-Series | Yes | Yes | `BH_ctf_Estimate()` | `ctf/BH_ctf_Estimate.m` |
| `ctf refine` | Tilt-Series | Yes | Yes | `BH_ctf_Refine2()` | `ctf/BH_ctf_Refine2.m` |
| `ctf update` | Tilt-Series | No | Yes | `BH_ctf_Updatefft()` | `ctf/BH_ctf_Updatefft.m` |
| `ctf 3d` | Tilt-Series | Yes | Yes | `BH_ctf_Correct3d()` | `ctf/BH_ctf_Correct3d.m` |
| `ctf ctfRefine` | Tilt-Series | Yes | No | `EMC_ctf_refine_from_star()` | `ctf/EMC_ctf_refine_from_star.m` |
| `templateSearch` | Picking | Yes | Yes | `BH_templateSearch3d_2()` | `alignment/BH_templateSearch3d_2.m` |
| `cleanTemplateSearch` | Picking | No | No | `BH_geometry_Constraints()` | `metaData/BH_geometry_Constraints.m` |
| `removeNeighbors` | Picking | No | No | `BH_geometry_Constraints()` | `metaData/BH_geometry_Constraints.m` |
| `init` | Setup | Yes | Yes | `BH_geometryInitialize()` | `metaData/BH_geometryInitialize.m` |
| `segment` | Setup | No | No | `recScript()` | `testScripts/recScript.m` |
| `avg` | Averaging | Yes | Yes | `BH_average3d()` | `transformations/BH_average3d.m` |
| `fsc` | Resolution | Yes | Yes | `BH_fscGold_class()` | `statistics/BH_fscGold_class.m` |
| `plotFSC` | Resolution | No | No | `BH_plotMultiCycleFSC()` | `metaData/BH_plotMultiCycleFSC.m` |
| `alignRaw` | Alignment | Yes | Yes | `BH_alignRaw3d_v2()` | `alignment/BH_alignRaw3d_v2.m` |
| `skip` | Alignment | No | Yes | `BH_skipClassAlignment()` | `metaData/BH_skipClassAlignment.m` |
| `tomoCPR` | Refinement | Yes | Yes | `BH_synthetic_mapBack()` | `synthetic/BH_synthetic_mapBack.m` |
| `pca` | Classification | Yes | Yes | `BH_pcaPub()` | `statistics/BH_pcaPub.m` |
| `cluster` | Classification | No | Yes | `BH_clusterPub()` | `statistics/BH_clusterPub.m` |
| `geometry` | Utilities | No | Yes | `BH_geometryAnalysis()` | `metaData/BH_geometryAnalysis.m` |
| `mask` | Utilities | Yes | No | `BH_mask3d()` | (inline in emClarity.m) |
| `rescale` | Utilities | Yes | No | `BH_reScale3d()` | (via emClarity.m) |
| `reconstruct` | Export | Yes | Yes | `BH_to_cisTEM_mapBack()` | `synthetic/BH_to_cisTEM_mapBack.m` |
| `montage` | Utilities | Yes | Yes | (inline) | `emClarity.m:910` |
| `simulate` | Simulation | Yes | No | Multiple | `synthetic/EMC_*.m` |
| `getActiveTilts` | Utilities | No | Yes | `BH_returnIncludedTilts()` | `metaData/BH_returnIncludedTilts.m` |
| `experimental` | System | No | No | (inline) | `emClarity.m:1191` |

---

## 2. Typical Processing Pipeline Order

```
PHASE 1: DATA PREPARATION (per tilt-series)
 1. autoAlign          -- Align raw tilt-series via IMOD
 2. ctf estimate       -- Estimate defocus/astigmatism
 3. ctf refine         -- (Optional) Refine CTF across tilted images
 4. ctf 3d             -- Reconstruct CTF-corrected tomograms

PHASE 2: PARTICLE PICKING (per tomogram)
 5. templateSearch     -- 3D template matching
 6. cleanTemplateSearch -- (Optional) Remove false positives

PHASE 3: PROJECT INITIALIZATION (once)
 7. init               -- Create subTomoMeta.mat from picks

PHASE 4: ITERATIVE REFINEMENT (cycle 0, 1, 2, ...)
 [Cycle 0]
  8. avg 0 RawAlignment       -- Initial average

 [Cycle N = 1, 2, 3, ...]
  9. alignRaw N               -- Align subtomograms to reference
 10. avg N RawAlignment       -- Average with updated orientations

      --- Optional Classification ---
 11. pca N 0 3                -- PCA decomposition
 12. cluster N                -- K-means/GMM clustering
 13. avg N Cluster_cls        -- Class averages
 14. skip N [RemoveClasses]   -- Update metadata
      ---

 [After several cycles]
 15. tomoCPR N RawAlignment   -- Refine tilt-series alignment
 16. ctf 3d                   -- Re-reconstruct improved tomograms
 [Continue from step 9]

PHASE 5: EXPORT
 17. reconstruct              -- Export to cisTEM stack + star
```

### Visual Data Flow

```
Raw Data (.st + .rawtlt)
     |
[autoAlign] ---------> fixedStacks/ (.fixed, .tlt, .xf, .local)
     |
[ctf estimate] ------> fixedStacks/ (_ctf.tlt)  +  aliStacks/ (_ali1.fixed)
     |
[ctf refine] --------> Updated CTF parameters
     |
[ctf 3d] ------------> cache/ (3D tomograms, odd/eve half-sets)
     |
[templateSearch] ----> convmap/ (CC maps, peak coordinates)
     |
[init] --------------> subTomoMeta.mat (master metadata)
     |
     v
+--[avg]--+   cycle 0: initial average
|         |
|  [alignRaw] --> updated orientations in subTomoMeta.mat
|  [avg] -------> reference volumes + FSC/ curves
|  [pca] -------> PCA coefficients (optional)
|  [cluster] ---> class assignments (optional)
|         |
+----+----+
     |
[tomoCPR] -----------> improved tilt-series alignment in fixedStacks/
[ctf 3d] ------------> improved tomograms in cache/
(iterate)
     |
[reconstruct] -------> cisTEM-compatible stack.mrc + star file
```

---

## 3. Inputs and Outputs Per Command

### autoAlign
- **Input**: `param.m`, `stack.st`, `tilt.rawtlt`, tilt axis rotation angle, [pixel_size]
- **Output**: `fixedStacks/<name>.fixed`, `<name>.tlt`, `<name>.xf`, `<name>.local`

### ctf estimate
- **Input**: `param.m`, tilt base name; reads `fixedStacks/<name>.fixed`, `.tlt`, `.order`
- **Output**: `fixedStacks/<name>_ctf.tlt`, `aliStacks/<name>_ali1.fixed`, diagnostic plots

### ctf refine
- **Input**: `param.m`, tilt base name; reads `aliStacks/<name>_ali<N>.fixed`
- **Output**: Updated CTF parameters in `fixedStacks/`

### ctf update
- **Input**: `param.m`
- **Output**: Regenerated CTF correction files

### ctf 3d
- **Input**: `param.m`, [scratch_dir]; reads aligned stacks and CTF files
- **Output**: `cache/<name>_<bin>_<iter>.rec` (odd/eve split tomograms)

### templateSearch
- **Input**: `param.m`, tomo name, tomo index, template MRC, symmetry, GPU index, [threshold]
- **Output**: `convmap/` (correlation maps, peak coordinate files)

### init
- **Input**: `param.m`, [tomoCPR_cycle, iteration, start_tilt]
- **Output**: `subTomoMeta.mat` (master project metadata)

### avg
- **Input**: `param.m`, cycle, stage (`RawAlignment` or `Cluster_cls`); reads subTomoMeta, tomograms
- **Output**: Reference volumes (`cycle<NNN>_*_Ref_{ODD,EVE,STD}.mrc`), FSC/ curves, updated subTomoMeta

### alignRaw
- **Input**: `param.m`, cycle, [scoring_method]; reads subTomoMeta, references, tomograms
- **Output**: Updated `subTomoMeta.mat` with refined orientations and translations

### fsc
- **Input**: `param.m`, cycle, stage; reads half-map references
- **Output**: `FSC/` curve data and resolution estimates

### tomoCPR
- **Input**: `param.m`, cycle, stage (`Avg`/`RawAlignment`/`Cluster_cls`), [start_tilt]; reads references and tilt-series
- **Output**: Updated tilt-series alignment in `fixedStacks/`, incremented `subTomoMeta.currentTomoCPR`

### pca
- **Input**: `param.m`, cycle, randomSubset, mask_option; reads subTomoMeta, references, tomograms
- **Output**: PCA coefficient files stored in subTomoMeta

### cluster
- **Input**: `param.m`, cycle; reads PCA coefficients from subTomoMeta
- **Output**: Updated class assignments in subTomoMeta

### reconstruct
- **Input**: `param.m`, cycle, output_prefix, symmetry, max_exposure, classIDX
- **Output**: `<prefix>.mrc` (particle stack), `<prefix>.star` (star file)

---

## 4. Most Relevant Parameters from BH_parseParameterFile.m

The parameter file (`param.m`) uses `name=value` format. All parameters are parsed by `BH_parseParameterFile()` at `metaData/BH_parseParameterFile.m`.

### Required (Every param.m)

| Parameter | Type | Units | Example |
|-----------|------|-------|---------|
| `subTomoMeta` | string | - | `myProject` |
| `nGPUs` | int | - | `2` |
| `nCpuCores` | int | - | `16` |
| `symmetry` | string | - | `C1` |
| `PIXEL_SIZE` | float | meters | `1.35e-10` |
| `Cs` | float | meters | `2.7e-3` |
| `VOLTAGE` | float | Volts | `300e3` |
| `AMPCONT` | float | 0-1 | `0.07` |
| `Pca_clusters` | int | - | `4` |

### Template Matching (Tmp_ prefix)

| Parameter | Default | Used By |
|-----------|---------|---------|
| `Tmp_samplingRate` | required | templateSearch, ctf 3d (templateSearch mode), init |
| `Tmp_threshold` | required | templateSearch |
| `Tmp_targetSize` | required | templateSearch |
| `Tmp_angleSearch` | required | templateSearch |
| `Tmp_bandpass` | [0.001,1200,28] | templateSearch |
| `Tmp_medianFilter` | - | templateSearch |
| `Tmp_half_precision` | false | templateSearch |
| `particleRadius` | required | templateSearch, alignRaw, avg, tomoCPR, reconstruct, init |

### Alignment / Averaging (Ali_, Raw_ prefixes)

| Parameter | Default | Used By |
|-----------|---------|---------|
| `Ali_samplingRate` | required | alignRaw, avg, fsc, tomoCPR, ctf 3d, pca |
| `Ali_mRadius` | required | templateSearch, avg |
| `Raw_angleSearch` | required | alignRaw |
| `Raw_className` | required | alignRaw, avg, pca, tomoCPR |
| `Raw_classes_odd` | required | alignRaw, avg, pca, tomoCPR |
| `Raw_classes_eve` | required | alignRaw, avg, pca, tomoCPR |
| `scale_calc_size` | 1.5 | alignRaw |
| `flgQualityWeight` | 5.0 | avg, alignRaw |
| `ccc_cutoff` | 0.0 | avg |
| `particleMass` | required | tomoCPR |

### Classification (Cls_, Pca_ prefixes)

| Parameter | Default | Used By |
|-----------|---------|---------|
| `Cls_samplingRate` | required | pca |
| `Cls_className` | required | fsc |
| `Pca_clusters` | required | cluster |
| `Pca_maxEigs` | 36 | pca |
| `Pca_bandpass` | [0.001,1200,28] | pca |
| `distance_metric` | sqeuclidean | cluster |
| `n_replicates` | 64 | cluster |

### CTF Parameters

| Parameter | Default | Used By |
|-----------|---------|---------|
| `ctf_tile_size` | ~680A/pixelSize | ctf estimate |
| `ctf_tile_overlap` | 2 | ctf estimate |
| `deltaZTolerance` | 100e-9 | ctf estimate |
| `paddedSize` | 768 | ctf estimate |
| `max_ctf3dDepth` | 100e-9 | ctf 3d |
| `n_tilt_workers` | 4 | ctf 3d |
| `super_sample` | 3 | ctf 3d |

### TomoCPR Parameters

| Parameter | Default | Used By |
|-----------|---------|---------|
| `tomoCprLowPass` | 22 | tomoCPR |
| `tomoCPR_random_subset` | -1 | tomoCPR |
| `tomoCPR_n_particles_minimum` | 10 | tomoCPR |
| `tomoCPR_target_n_patches_x_y` | [2,2] | tomoCPR |
| `tomo_cpr_defocus_range` | 500e-9 | tomoCPR |
| `tomo_cpr_defocus_step` | 100e-9 | tomoCPR |
| `tomo_cpr_defocus_refine` | false | tomoCPR |
| `tomo_cpr_maximum_iterations` | 15 | tomoCPR |

### FSC / Output

| Parameter | Default | Used By |
|-----------|---------|---------|
| `Fsc_bfactor` | 40.0 | avg, fsc |
| `fsc_shape_mask` | 1.0 | avg, fsc |
| `shape_mask_lowpass` | 14 | avg |
| `shape_mask_threshold` | 2.4 | avg |

### Parameters That Change Between Cycles

- `Ali_samplingRate` -- decrease (less binning) as resolution improves
- `Raw_angleSearch` -- narrow as alignment converges
- `Pca_clusters` -- adjust based on heterogeneity seen in class averages

### Parameters Set Once

- `PIXEL_SIZE`, `Cs`, `VOLTAGE`, `AMPCONT` -- microscope constants
- `symmetry`, `subTomoMeta` -- project identity
- `particleRadius`, `particleMass` -- particle properties

---

## 5. GUI State Machine

```
UNINITIALIZED
  -> TILT_ALIGNED (after autoAlign)
    -> CTF_ESTIMATED (after ctf estimate)
      -> RECONSTRUCTED (after ctf 3d)
        -> PARTICLES_PICKED (after templateSearch)
          -> INITIALIZED (after init)
            -> CYCLE_0_AVG (after avg 0 RawAlignment)
              -> [ALIGN -> AVG -> (PCA -> CLUSTER -> AVG_CLS)?
                  -> TOMOCPR -> RE-RECONSTRUCT]*
                -> EXPORT (reconstruct)
```

Each state transition corresponds to one or more command executions. The GUI should track per-tilt-series completion status and only enable commands whose prerequisites are met.

---

## 6. Project Directory Structure

emClarity expects and creates the following directory structure:

```
project_root/
  rawData/           -- Original tilt-series (.st files)
  fixedStacks/       -- Aligned tilt-series and metadata
    <name>.fixed     -- Aligned stack
    <name>.tlt       -- Tilt angles
    <name>.xf        -- Per-tilt transforms
    <name>.local     -- Local alignment file
    <name>_ctf.tlt   -- CTF-annotated tilt file
    <name>.order     -- Tilt acquisition order
  aliStacks/         -- CTF-corrected aligned stacks
    <name>_ali<N>.fixed
  cache/             -- Reconstructed tomograms (temp storage)
    <name>_<bin>_<iter>.rec
    <name>_<bin>_<iter>_ODD.rec
    <name>_<bin>_<iter>_EVE.rec
  convmap/           -- Template search results
    <name>_convmap.mrc    -- Cross-correlation maps
    <name>_peak.mat       -- Peak coordinates
  subTomoMeta.mat    -- Master project metadata (MATLAB struct)
  FSC/               -- Resolution curves and statistics
  logFile/           -- Processing logs
  cycle<NNN>_*.mrc   -- Reference volumes per cycle
```

---

## 7. Key Files Analyzed

| File | Lines | Purpose |
|------|-------|---------|
| `testScripts/emClarity.m` | 1344 | Main entry point, switch/case dispatch for all 28+ commands |
| `metaData/BH_parseParameterFile.m` | 1183 | Parameter parser with ~120+ parameters, types, defaults, validation |
| `alignment/BH_runAutoAlign.m` | ~500 | autoAlign implementation (IMOD integration) |
| `alignment/BH_alignRaw3d_v2.m` | ~1200 | Subtomogram alignment engine |
| `alignment/BH_templateSearch3d_2.m` | ~800 | 3D template matching for particle picking |
| `ctf/BH_ctf_Estimate.m` | ~600 | CTF estimation (defocus + astigmatism) |
| `ctf/BH_ctf_Correct3d.m` | ~900 | 3D CTF correction and tomogram reconstruction |
| `ctf/BH_ctf_Refine2.m` | ~400 | CTF refinement across tilted images |
| `transformations/BH_average3d.m` | ~800 | Subtomogram averaging |
| `statistics/BH_fscGold_class.m` | ~500 | Fourier Shell Correlation calculation |
| `statistics/BH_pcaPub.m` | ~600 | PCA decomposition for classification |
| `statistics/BH_clusterPub.m` | ~300 | K-means/GMM clustering |
| `synthetic/BH_synthetic_mapBack.m` | ~700 | tomoCPR (constrained projection refinement) |
| `synthetic/BH_to_cisTEM_mapBack.m` | ~500 | Export to cisTEM format |
| `metaData/BH_geometryInitialize.m` | ~400 | Project initialization from template search picks |
| `metaData/BH_geometryAnalysis.m` | ~600 | Geometry operations (add/remove/update particles) |
| `metaData/BH_skipClassAlignment.m` | ~200 | Skip alignment cycle, update metadata |

---

## 8. Command Argument Signatures

Each command is dispatched from `emClarity.m` with specific argument patterns:

```matlab
% autoAlign: param_file, stack, rawtlt, tilt_axis_angle, [pixel_size]
emClarity autoAlign param.m tilt1.st tilt1.rawtlt 0

% ctf estimate: param_file, tilt_basename
emClarity ctf estimate param.m tilt1

% ctf refine: param_file, tilt_basename
emClarity ctf refine param.m tilt1

% ctf 3d: param_file, [scratch_directory]
emClarity ctf 3d param.m /scratch

% templateSearch: param_file, tomo_name, tomo_index, template.mrc, symmetry, gpu_id, [threshold]
emClarity templateSearch param.m tilt1 1 template.mrc C1 0

% init: param_file, [tomoCPR_cycle, iteration, start_tilt]
emClarity init param.m

% avg: param_file, cycle, stage
emClarity avg param.m 0 RawAlignment

% alignRaw: param_file, cycle, [scoring_method]
emClarity alignRaw param.m 1

% tomoCPR: param_file, cycle, [stage, start_tilt]
emClarity tomoCPR param.m 4 RawAlignment

% pca: param_file, cycle, randomSubset, mask_option
emClarity pca param.m 1 0 3

% cluster: param_file, cycle
emClarity cluster param.m 1

% reconstruct: param_file, cycle, output_prefix, symmetry, max_exposure, classIDX
emClarity reconstruct param.m 4 output C1 60 1

% fsc: param_file, cycle, stage
emClarity fsc param.m 1 RawAlignment

% skip: param_file, cycle, [removeClasses]
emClarity skip param.m 1

% geometry: param_file, operation, ...args
emClarity geometry param.m AddTomograms new_tomos.csv

% plotFSC: (multiple cycles)
emClarity plotFSC

% mask: size, shape, radius, center, ...
emClarity mask 128 sphere 40 64,64,64

% rescale: input.mrc, output.mrc, scale_factor, [method]
emClarity rescale input.mrc output.mrc 2
```

---

## 9. subTomoMeta.mat Structure

The `subTomoMeta.mat` file is the master metadata store for the entire project. It is a MATLAB struct with the following key fields:

| Field | Type | Description |
|-------|------|-------------|
| `subTomoMeta.cycle` | int | Current processing cycle number |
| `subTomoMeta.currentTomoCPR` | int | Counter for tomoCPR iterations |
| `subTomoMeta.mapBackGeometry` | struct | Per-tomogram geometry info |
| `subTomoMeta.mapBackGeometry.<tomo>.coords` | Nx26 matrix | Particle coordinates and metadata |
| `subTomoMeta.mapBackGeometry.<tomo>.nSubTomo` | int | Number of subtomograms per tomogram |
| `subTomoMeta.tiltGeometry` | struct | Per-tilt-series alignment parameters |
| `subTomoMeta.reconGeometry` | struct | Reconstruction geometry |
| `subTomoMeta.Raw_className` | cell | Class name identifiers |
| `subTomoMeta.Raw_classes_odd` | cell | Odd-set class assignments |
| `subTomoMeta.Raw_classes_eve` | cell | Even-set class assignments |

### Coordinate Matrix (Nx26) Columns

The 26-column coordinate matrix stores per-particle information:

| Columns | Content |
|---------|---------|
| 1-3 | X, Y, Z position in tomogram |
| 4-6 | Euler angles (phi, theta, psi) |
| 7-9 | Translational shifts (dx, dy, dz) |
| 10 | Cross-correlation coefficient (CCC) |
| 11 | Particle class assignment |
| 12-14 | Euler angle changes from last cycle |
| 15-17 | Translation changes from last cycle |
| 18 | Weight factor |
| 19-20 | Defocus values (underfocus1, underfocus2) |
| 21 | Astigmatism angle |
| 22 | Exposure filter weight |
| 23 | Tilt index |
| 24 | Random half-set assignment (1=ODD, 2=EVE) |
| 25-26 | Reserved / additional metadata |

---

## 10. Inter-Command Dependencies

```
autoAlign      -> ctf estimate (requires .fixed, .tlt)
ctf estimate   -> ctf 3d (requires _ctf.tlt, _ali1.fixed)
ctf refine     -> ctf 3d (optional, updates CTF params)
ctf 3d         -> templateSearch (requires reconstructed tomograms)
templateSearch -> init (requires convmap/ peak files)
init           -> avg (requires subTomoMeta.mat)
avg            -> alignRaw (requires reference volumes)
alignRaw       -> avg (requires updated subTomoMeta.mat)
avg            -> pca (requires reference volumes)
pca            -> cluster (requires PCA coefficients)
cluster        -> avg (requires class assignments)
avg/alignRaw   -> tomoCPR (requires reference volumes + subTomoMeta)
tomoCPR        -> ctf 3d (updated tilt alignment, re-reconstruct)
any avg        -> reconstruct (requires final reference + subTomoMeta)
```

### Circular Dependencies (Iterative Loops)

The pipeline has two main iterative loops:

1. **Alignment loop**: `alignRaw -> avg -> alignRaw -> avg -> ...`
2. **Refinement loop**: `tomoCPR -> ctf 3d -> alignRaw -> avg -> tomoCPR -> ...`

The GUI must track cycle numbers to manage these loops correctly.
