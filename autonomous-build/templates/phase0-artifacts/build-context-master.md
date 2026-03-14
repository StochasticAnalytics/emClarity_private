# build-context-master.md -- Autonomous Build Context for emClarity GUI

**Version:** 1.0
**Date:** 2026-03-13
**Phase:** 0, Session 4 -- Architecture Confirmation
**Purpose:** Complete context document enabling an autonomous agent to build the emClarity GUI without human intervention.

---

## 1. Executive Summary

### What emClarity Does

emClarity is a comprehensive cryo-electron microscopy (cryo-EM) sub-tomogram averaging package. It processes tilt-series data acquired from electron microscopes to reconstruct high-resolution 3D structures of biological macromolecules, achieving sub-3 Angstrom resolution. The software is primarily written in MATLAB with CUDA MEX extensions for GPU acceleration.

The processing pipeline involves:
- Aligning raw tilt-series images using IMOD integration
- Estimating and correcting the Contrast Transfer Function (CTF)
- Reconstructing 3D tomograms from corrected tilt-series
- Finding particles via 3D template matching
- Iteratively aligning and averaging thousands of sub-tomograms
- Refining tilt-series alignment using particle positions (tomoCPR)
- Classifying structural heterogeneity via PCA/clustering
- Exporting refined particles for high-resolution reconstruction

### What the GUI Needs to Accomplish

The GUI must provide a graphical interface that:

1. **Replaces hand-edited parameter files** -- Present 160+ parameters in logically grouped, validated forms with sensible defaults and inline documentation.
2. **Orchestrates the multi-step pipeline** -- Drive the sequence of 28+ commands with dependency tracking, preventing users from running steps out of order.
3. **Manages iterative refinement cycles** -- Track cycle numbers, sampling rates, and angular search ranges that change between alignment/averaging iterations.
4. **Monitors running jobs** -- Display real-time log output, GPU utilization, and progress indicators for long-running computations.
5. **Visualizes results** -- Show FSC resolution curves, particle distributions, and 3D reconstructions (or link to external viewers).
6. **Protects scientific validity** -- Enforce gold-standard half-set independence, prevent parameter combinations that could introduce artifacts, and surface errors prominently.

---

## 2. Component Map

The GUI requires the following major components:

### 2.1 Project Manager
- **New Project Wizard** -- Collect microscope parameters (PIXEL_SIZE, Cs, VOLTAGE, AMPCONT), project name, and directory structure
- **Project Open/Recent** -- Load existing subTomoMeta.mat files and reconstruct project state
- **Project Status Dashboard** -- At-a-glance view of per-tilt-series completion status and current cycle

### 2.2 Parameter Editor
- **Grouped parameter panels** -- One tab/section per logical parameter group (see Section 3)
- **Per-cycle parameter editing** -- Parameters like `Ali_samplingRate` and `Raw_angleSearch` change between cycles; the editor must handle cycle-specific configurations
- **Validation feedback** -- Real-time validation against ranges, types, and interdependencies defined in the parameter schema
- **Parameter file import/export** -- Read existing MATLAB `param.m` files; write validated parameter files for emClarity consumption
- **Deprecated parameter migration** -- Automatically detect and upgrade deprecated parameter names (e.g., `flgCCCcutoff` -> `ccc_cutoff`)

### 2.3 Tilt-Series Manager
- **Tilt-series table** -- List all tilt-series with status indicators (aligned / CTF estimated / reconstructed)
- **Batch operations** -- Run autoAlign, ctf estimate, ctf 3d across multiple tilt-series
- **Per-tilt-series controls** -- Select/deselect tilt-series, view individual CTF diagnostic plots

### 2.4 Workflow Runner
- **Pipeline state machine** -- Track project state (UNINITIALIZED -> TILT_ALIGNED -> CTF_ESTIMATED -> RECONSTRUCTED -> PARTICLES_PICKED -> INITIALIZED -> CYCLE_N)
- **Command launcher** -- Build correct command-line arguments for each emClarity command
- **Dependency enforcement** -- Disable buttons/menu items for commands whose prerequisites have not been met
- **Cycle manager** -- Track alignment/averaging iterations and tomoCPR refinement loops

### 2.5 Job Monitor
- **Log viewer** -- Tail `logFile/emClarity_<project>.logfile` in real-time
- **Process manager** -- Track running subprocess PID, allow cancellation
- **GPU monitor** -- Query nvidia-smi for GPU utilization and memory usage
- **Progress estimation** -- Parse log output for progress indicators (tilt number, particle count)

### 2.6 Results Viewer
- **FSC curve plotter** -- Display resolution curves from FSC/ directory (matplotlib integration)
- **Particle statistics** -- Number of particles, class distributions, CCC score histograms
- **Reference volume viewer** -- Display 2D slices/projections of reference volumes (cycle*_Ref_*.mrc)
- **Classification results** -- Show class averages and particle distributions across classes

### 2.7 Utilities Panel
- **Mask creator** -- Interface for `emClarity mask` command
- **Volume rescaler** -- Interface for `emClarity rescale` command
- **Geometry operations** -- Interface for `emClarity geometry` operations (RemoveClasses, RemoveFraction, etc.)
- **System check** -- Interface for `emClarity check` to verify installation

---

## 3. Parameter Groups

The 160 parameters from the schema are organized into the following logical groups for GUI presentation. Each group corresponds to a tab or collapsible section in the parameter editor.

### 3.1 Project Identity (3 parameters)
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `subTomoMeta` | string | No | null | Project name |
| `metadata_format` | string | No | "legacy" | Storage format: legacy, partitioned, development |
| `track_stats` | boolean | No | false | Enable processing statistics tracking |

### 3.2 Microscope Parameters (5 parameters)
*Set once per project -- do not change between cycles.*
| Parameter | Type | Required | Default | Units | Description |
|-----------|------|----------|---------|-------|-------------|
| `PIXEL_SIZE` | numeric | **Yes** | -- | meters | Pixel size (e.g., 1.35e-10) |
| `Cs` | numeric | **Yes** | -- | meters | Spherical aberration |
| `VOLTAGE` | numeric | **Yes** | -- | Volts | Accelerating voltage |
| `AMPCONT` | numeric | **Yes** | -- | fraction | Amplitude contrast (0.07-0.10) |
| `mtf_value` | numeric | No | 1 | -- | MTF correction value |

**GUI notes**: Display pixel size also in Angstroms (derived: PIXEL_SIZE * 1e10). Show voltage in kV (derived: VOLTAGE / 1000). Common presets: 300kV/200kV/120kV.

### 3.3 Hardware (6 parameters)
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `nGPUs` | numeric | **Yes** | -- | Number of GPUs |
| `nCpuCores` | numeric | **Yes** | -- | Number of CPU cores |
| `limit_to_one_core` | boolean | No | false | Force single core (overrides nCpuCores) |
| `n_tilt_workers` | numeric | No | 4 | Parallel tilt processes in ctf 3d |
| `flgPrecision` | string | No | null | Float precision (single/double) |
| `enable_profiling` | boolean | No | false | Enable MATLAB profiling |

**GUI notes**: Auto-detect available GPUs via nvidia-smi. Auto-detect CPU cores via os.cpu_count().

### 3.4 Disk Management (3 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fastScratchDisk` | string | "" | Fast scratch path or "ram" |
| `alt_cache` | string | {} | Comma-separated list of cache directories |
| `conserveDiskSpace` | numeric | 0 | 0=keep all, 1=some removal, 2=aggressive |

### 3.5 CTF Parameters (22 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `whitenPS` | [3] | [0,0,0] | Power spectrum whitening [a,b,wiener] |
| `filterDefocus` | [2] | [0,0] | Defocus-dependent downweighting |
| `ctf_tile_size` | numeric | ~680A/px | Tile size for CTF estimation |
| `ctf_tile_overlap` | numeric | 2 | Tile overlap factor |
| `deltaZTolerance` | numeric | 100e-9 | Z tolerance (meters) |
| `zShift` | numeric | 150e-9 | Z shift (meters) |
| `ctfMaxNumberOfTiles` | numeric | 10000 | Max tiles for CTF estimation |
| `paddedSize` | numeric | 768 | Padded size for CTF ops |
| `max_ctf3dDepth` | numeric | 100e-9 | Max slab depth (meters) |
| `PHASE_PLATE_SHIFT` | [2] | [0,0] | Phase plate shift (*pi) |
| `phase_plate_mode` | boolean | false | Enable phase plate mode |
| `erase_beads_after_ctf` | boolean | false | Erase gold beads post-CTF |
| `testFlipSign` | numeric | -1 | Defocus sign flip |
| `force_no_defocus_stretch` | boolean | false | Disable defocus stretch |
| `fraction_of_extra_tilt_data` | numeric | 0.25 | Extra tilt data fraction |
| `useSurfaceFit` | boolean | false | Surface fit for defocus |
| `use_defocus_from_emc` | boolean | false | Use emClarity defocus values |
| `set_defocus_origin_using_subtomos` | boolean | false | Defocus origin from particles |
| `test_flip_defocus_offset` | boolean | false | Test defocus offset sign |
| `test_flip_tilt_offset` | boolean | false | Test tilt offset sign |
| `refine_defocus_cisTEM` | boolean | false | Refine defocus via cisTEM |
| `rerun_refinement_cisTEM` | boolean | false | Re-run cisTEM refinement |

**Sub-group: cisTEM Integration** (3 parameters)
| Parameter | Type | Default | Allowed | Description |
|-----------|------|---------|---------|-------------|
| `cisTEM_invert_tilt_for_defocus_calc` | numeric | 0 | [0,1] | Invert tilt for defocus calc |
| `cisTEM_astigmatism_angle_convention_switch` | numeric | 0 | [0,90] | Angle convention switch |
| `cisTEM_output_tile_size` | numeric | 0 | [32-2048] | Output tile size (0=auto) |

**Sub-group: tomoCPR CTF Refinement** (6 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tomo_cpr_defocus_range` | numeric | 500e-9 | Defocus search range |
| `tomo_cpr_defocus_step` | numeric | 100e-9 | Defocus step size |
| `tomo_cpr_defocus_refine` | boolean | false | Enable defocus refinement |
| `tomo_cpr_astigmatism_angle_range` | numeric | pi/4 | Max astigmatism angle change |
| `tomo_cpr_upsample_factor` | numeric | 8 | Sub-pixel upsampling factor |
| `tomo_cpr_upsample_window` | numeric | 8 | Upsampling half-window |
| `tomo_cpr_maximum_iterations` | numeric | 15 | Max ADAM optimizer iterations |
| `tomo_cpr_z_offset_bound_factor` | numeric | 5 | Z offset bound multiplier |

### 3.6 Alignment Parameters (16 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symmetry` | string | **Required** | Particle symmetry (C1, C2, ..., O, I) |
| `force_no_symmetry` | boolean | true* | Force C1 symmetry (*BUG: default should be false) |
| `symmetry_constrained_search` | string/bool | false | Constrain search by symmetry |
| `CUTPADDING` | numeric | 20 | Extra padding when cutting subtomos |
| `ccc_cutoff` | numeric | 0.0 | CCC threshold for particle selection |
| `projectVolumes` | boolean | false | Project volumes |
| `multi_reference_alignment` | numeric | 0 | Multi-ref mode (0=off, 1, 2) |
| `scale_calc_size` | numeric | 1.5 | Zero padding factor [1.0-2.0] |
| `update_class_by_ccc` | boolean | true | Update class by best CCC |
| `move_reference_by_com` | boolean | true | Center reference by COM |
| `use_new_grid_search` | boolean | true | New angular grid search |
| `flgCutOutVolumes` | boolean | false | Cut out sub-volumes |
| `remove_duplicates` | boolean | true | Remove duplicate particles |
| `removeBottomPercent` | numeric | 0.0 | Remove bottom % by score |
| `autoAli_switchAxes` | boolean | true | Switch axes in auto-alignment |
| `use_fourier_interp` | boolean | true | Fourier interpolation for 2D |
| `print_alignment_stats` | boolean | false | Print alignment statistics |
| `printShiftsInParticleBasis` | boolean | true | Print shifts in particle basis |
| `ML_compressByFactor` | numeric | 2.0 | ML compression factor |
| `ML_angleTolerance` | numeric | 2.0 | ML angular tolerance (degrees) |

### 3.7 Template Matching (7 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `nPeaks` | numeric | 1 | Orientations to store |
| `tmp_model_scale` | numeric | 1 | Template scale (-1 inverts) |
| `tmp_scan` | [3] | [1,1,0] | Scan direction/mode |
| `Tmp_bandpass` | [3] | [0.001,1200,28] | Bandpass [HP,LP,rolloff] (Angstroms) |
| `Tmp_half_precision` | boolean | false | Half-precision for GPU memory |
| `helical_search_theta_constraint` | numeric | 0 | Helical theta constraint (degrees) |
| `Tmp_xcfScale` | string | null | XCF scaling method |
| `Tmp_eraseMaskType` | string | null | Erase mask type |

### 3.8 Classification (17 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `Pca_clusters` | numeric | **Required** | Number of PCA clusters |
| `classification` | boolean | false | Classification mode |
| `Pca_constrain_symmetry` | boolean | false | Constrain symmetry in PCA |
| `pca_scale_spaces` | numeric | 22.0 | Scale-space parameter(s) |
| `Pca_maxEigs` | numeric | 36 | Max eigenvalues |
| `Pca_randSubset` | numeric | 0 | Random subset size (0=all) |
| `Pca_bandpass` | [3] | [0.001,1200,28] | PCA bandpass filter |
| `Pca_refineKmeans` | boolean | false | Refine K-means |
| `Pca_flattenEigs` | boolean | true | Normalize eigenvalue magnitudes |
| `Pca_use_real_space_conv` | boolean | false | Real-space convolution |
| `distance_metric` | string | "sqeuclidean" | Clustering distance metric |
| `n_replicates` | numeric | 64 | K-means replicates |
| `gmm_covariance_type` | string | "full" | GMM covariance type |
| `gmm_covariance_shared_between_clusters` | boolean | false | Shared GMM covariance |
| `gmm_regularize_value` | numeric | 0.01 | GMM regularization |
| `spike_prior` | boolean | false | Apply spike prior |
| `pca_mask_threshold` | numeric | 0.5 | PCA mask threshold |

**Sub-group: SOM Classification** (3 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `Pca_som_coverSteps` | numeric | 100 | SOM covering steps |
| `Pca_som_initNeighbor` | numeric | 3 | SOM initial neighborhood |
| `Pca_som_topologyFcn` | string | "hextop" | SOM topology function |

### 3.9 FSC / Resolution (7 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `Fsc_bfactor` | numeric | 40.0 | B-factor for sharpening |
| `flgCones` | boolean | false | Cone-based FSC |
| `flgQualityWeight` | numeric | 5.0 | Quality weight for high-freq |
| `fsc_with_chimera` | boolean | false | FSC visualization with Chimera |
| `minimum_particle_for_fsc_weighting` | numeric | 0.1 | Min particle fraction |
| `fsc_shape_mask` | numeric | 1.0 | Shape mask scaling |
| `lowResCut` | numeric | 40 | Low resolution cutoff (Angstroms) |
| `particle_volume_scaling` | numeric | 1.0 | Volume estimation scaling |

### 3.10 Masking (5 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `shape_mask_lowpass` | numeric | 14 | Lowpass cutoff (Angstroms) |
| `shape_mask_threshold` | numeric | 2.4 | Binarization threshold (sigma) |
| `shape_mask_test` | boolean | false | Write masks for inspection |
| `shape_mask_lowpass_override` | numeric | 0 | Override lowpass (0=use default) |
| `shape_mask_threshold_override` | numeric | 0 | Override threshold (0=use default) |

### 3.11 TomoCPR / Tilt Refinement (25 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `eucentric_fit` | boolean | false | Use eucentric fit |
| `eucentric_minTilt` | numeric | 50.0 | Max tilt for eucentric fit |
| `save_mapback_classes` | boolean | false | Save per-class map-back |
| `only_use_reference_classes` | boolean | false | Use reference classes only |
| `tomoCprLowPass` | numeric | 22 | Low-pass cutoff |
| `tomoCPR_random_subset` | numeric | -1 | Random subset (-1=all) |
| `tomoCPR_n_particles_minimum` | numeric | 10 | Min particles required |
| `tomoCPR_target_n_patches_x_y` | [2] | [2,2] | Target patches X,Y |
| `run_tomocpr_alignments` | numeric | 0 | Parallel tiltalign processes |
| `shift_z_to_to_centroid` | boolean | true | Shift Z to centroid |
| `expand_lines` | boolean | true | Expand lines in reconstruction |
| `super_sample` | numeric | 3 | Super-sampling factor [2-5] |
| `mapBackIter` | numeric | 0 | Map back iteration counter |
| `probabilityPeakiness` | numeric | 0 | Probability peakiness |
| `whitenProjections` | numeric | 0 | Projection whitening |
| `peak_mask_fraction` | numeric | 0.4 | Peak mask fraction |
| `min_overlap` | numeric | 0.5 | Minimum overlap fraction |

**Sub-group: IMOD tiltalign Parameters** (12 parameters)
| Parameter | Default | Description |
|-----------|---------|-------------|
| `rot_option_global` | 1 | Global rotation option |
| `rot_option_local` | 1 | Local rotation option |
| `rot_default_grouping_global` | 3 | Global rotation grouping |
| `rot_default_grouping_local` | 3 | Local rotation grouping |
| `mag_option_global` | 1 | Global magnification option |
| `mag_option_local` | 1 | Local magnification option |
| `mag_default_grouping_global` | 5 | Global mag grouping |
| `mag_default_grouping_local` | 5 | Local mag grouping |
| `tilt_option_global` | 5 | Global tilt option |
| `tilt_option_local` | 5 | Local tilt option |
| `tilt_default_grouping_global` | 5 | Global tilt grouping |
| `tilt_default_grouping_local` | 5 | Local tilt grouping |

### 3.12 Dose Weighting (5 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `k_factor_scaling` | numeric | NaN | K-factor (NaN=auto) |
| `oneOverCosineDose` | boolean | false | 1/cos(tilt) dose weighting |
| `startingAngle` | numeric | 0 | Starting tilt angle (degrees) |
| `startingDirection` | string | "pos" | Starting direction (pos/neg) |
| `doseSymmetricIncrement` | numeric | 0 | Dose-symmetric tilts per sweep |
| `doseAtMinTilt` | numeric | 0 | Dose at min tilt (e-/A^2) |

### 3.13 Coordinate System (3 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `flgPreShift` | [3] | [-0.5,-0.5,0.5] | IMOD/emClarity pre-shift |
| `flgPostShift` | [2] | [1.0,-1.0] | IMOD/emClarity post-shift |
| `prjVectorShift` | [3] | [0.5,0.5,1.5] | Projection vector shift |
| `pixelShift` | numeric | 0 | Pixel shift offset |
| `pixelMultiplier` | numeric | -1 | Pixel multiplier |

### 3.14 Mask Types (6 string parameters)
| Parameter | Description |
|-----------|-------------|
| `Ali_mType` | Alignment mask type |
| `Cls_mType` | Classification mask type |
| `Raw_mType` | Raw alignment mask type |
| `Fsc_mType` | FSC mask type |
| `Kms_mType` | K-means mask type |
| `Peak_mType` | Peak mask type |

### 3.15 Debug / Diagnostics (3 parameters)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `debug_print` | boolean | false | Debug print mode |
| `save_tomocpr_diagnostics` | boolean | false | Save tomoCPR diagnostics |

---

## 4. Workflow Integration

### 4.1 Pipeline State Machine

The GUI must implement the following state machine. Each state transition is triggered by successful completion of the corresponding command(s).

```
UNINITIALIZED
  |
  | [autoAlign per tilt-series]
  v
TILT_ALIGNED
  |
  | [ctf estimate per tilt-series]
  v
CTF_ESTIMATED
  |
  | [ctf 3d]
  v
RECONSTRUCTED
  |
  | [templateSearch per tomogram]
  v
PARTICLES_PICKED
  |
  | [init]
  v
INITIALIZED (subTomoMeta.mat exists)
  |
  | [avg 0 RawAlignment]
  v
CYCLE_0_COMPLETE
  |
  +---> ITERATIVE REFINEMENT LOOP (cycles 1, 2, 3, ...)
  |     |
  |     | [alignRaw N]
  |     | [avg N RawAlignment]
  |     |
  |     +---> OPTIONAL CLASSIFICATION BRANCH
  |     |     | [pca N 0 3]
  |     |     | [cluster N]
  |     |     | [avg N Cluster_cls]
  |     |     | [skip N] (update metadata)
  |     |     +---> return to main loop
  |     |
  |     +---> TOMOCPR REFINEMENT (every few cycles)
  |           | [tomoCPR N RawAlignment]
  |           | [ctf 3d] (re-reconstruct)
  |           +---> return to alignRaw
  |
  v
EXPORT
  | [reconstruct]
  v
DONE
```

### 4.2 Command Dispatch

The GUI builds CLI commands using the following signatures. Arguments in `[]` are optional.

| Command | CLI Signature |
|---------|--------------|
| autoAlign | `emClarity autoAlign param.m stack.st tilt.rawtlt tilt_axis [pixel_size]` |
| ctf estimate | `emClarity ctf estimate param.m tilt_basename [gpu_idx]` |
| ctf refine | `emClarity ctf refine param.m tilt_basename` |
| ctf update | `emClarity ctf update param.m` |
| ctf 3d | `emClarity ctf 3d param.m [scratch_dir]` |
| templateSearch | `emClarity templateSearch param.m tomo_name tomo_idx template.mrc symmetry gpu_idx [threshold]` |
| init | `emClarity init param.m [tomoCPR_cycle] [iteration] [start_tilt]` |
| avg | `emClarity avg param.m cycle stage` |
| alignRaw | `emClarity alignRaw param.m cycle [scoring_method]` |
| fsc | `emClarity fsc param.m cycle stage` |
| tomoCPR | `emClarity tomoCPR param.m cycle stage [start_tilt]` |
| pca | `emClarity pca param.m cycle randomSubset mask_option` |
| cluster | `emClarity cluster param.m cycle` |
| skip | `emClarity skip param.m cycle [operation]` |
| reconstruct | `emClarity reconstruct param.m cycle output_prefix symmetry max_exposure classIDX` |
| geometry | `emClarity geometry param.m cycle stage operation vectOP halfset` |

### 4.3 Per-Tilt-Series vs. Global Operations

**Per-tilt-series** (must track individual completion): autoAlign, ctf estimate, ctf refine, templateSearch

**Global** (operate on entire project): ctf 3d, init, avg, alignRaw, fsc, tomoCPR, pca, cluster, skip, reconstruct

The GUI should maintain a tilt-series table with per-series completion checkmarks.

### 4.4 Cycle-Dependent Parameters

These parameters typically change between processing cycles and the GUI must support cycle-specific values:

- `Ali_samplingRate` -- Decreases (less binning) as resolution improves
- `Cls_samplingRate` -- Decreases with resolution
- `Raw_angleSearch` -- Narrows as alignment converges
- `Raw_className` / `Raw_classes_odd` / `Raw_classes_eve` -- Class identifiers
- `Pca_clusters` -- Adjusted based on heterogeneity

### 4.5 Parameters Set Once (Project Constants)

These never change after project creation:
- `PIXEL_SIZE`, `Cs`, `VOLTAGE`, `AMPCONT` -- Microscope constants
- `symmetry`, `subTomoMeta` -- Project identity
- `particleRadius`, `particleMass` -- Particle properties

---

## 5. Data Flow

### 5.1 Directory Structure

```
project_root/
  param.m                    -- Parameter file (created/edited by GUI)
  subTomoMeta.mat            -- Master project metadata (MATLAB struct)
  rawData/                   -- Original tilt-series (.st files)
  fixedStacks/               -- Aligned tilt-series and metadata
    <name>.fixed             -- Aligned stack
    <name>.tlt               -- Tilt angles
    <name>.xf                -- Per-tilt transforms
    <name>.local             -- Local alignment file
    <name>_ctf.tlt           -- CTF-annotated tilt file
    <name>.order             -- Tilt acquisition order
  aliStacks/                 -- CTF-corrected aligned stacks
    <name>_ali<N>.fixed
  cache/                     -- Reconstructed tomograms
    <name>_<bin>_<iter>.rec
    <name>_<bin>_<iter>_ODD.rec
    <name>_<bin>_<iter>_EVE.rec
  convmap/                   -- Template search results
    <name>_convmap.mrc
    <name>_peak.mat
  FSC/                       -- Resolution curves
  logFile/                   -- Processing logs
  cycle<NNN>_*.mrc           -- Reference volumes per cycle
```

### 5.2 Stage-by-Stage Data Flow

```
Input Files (.st + .rawtlt)
    |
[autoAlign] --> fixedStacks/ (.fixed, .tlt, .xf, .local)
    |
[ctf estimate] --> fixedStacks/ (_ctf.tlt) + aliStacks/ (_ali1.fixed)
    |
[ctf refine] --> Updated CTF parameters in fixedStacks/
    |
[ctf 3d] --> cache/ (3D tomograms: _ODD.rec, _EVE.rec)
    |
[templateSearch] --> convmap/ (CC maps, peak coordinates)
    |
[init] --> subTomoMeta.mat (master project metadata)
    |
[avg] --> cycle<NNN>_*_Ref_{ODD,EVE,STD}.mrc + FSC/ curves
    |
[alignRaw] --> Updated subTomoMeta.mat (refined orientations)
    |
[tomoCPR] --> Updated fixedStacks/ (refined tilt alignment)
    |
[reconstruct] --> output.mrc (particle stack) + output.star (star file)
```

### 5.3 subTomoMeta.mat Structure (Critical)

The master metadata file is a MATLAB struct with these key fields:

| Field | Type | Description |
|-------|------|-------------|
| `subTomoMeta.cycle` | int | Current processing cycle |
| `subTomoMeta.currentTomoCPR` | int | TomoCPR iteration counter |
| `subTomoMeta.mapBackGeometry.<tomo>.coords` | Nx26 matrix | Per-particle coordinates/metadata |
| `subTomoMeta.tiltGeometry` | struct | Per-tilt-series alignment parameters |
| `subTomoMeta.reconGeometry` | struct | Reconstruction geometry |

**Particle Coordinate Matrix (Nx26 columns):**
- Cols 1-3: X, Y, Z position
- Cols 4-6: Euler angles (phi, theta, psi)
- Cols 7-9: Translational shifts
- Col 10: Cross-correlation coefficient
- Col 11: Class assignment
- Cols 12-14: Euler angle changes from last cycle
- Cols 15-17: Translation changes
- Col 18: Weight factor
- Cols 19-20: Defocus values
- Col 21: Astigmatism angle
- Col 22: Exposure filter weight
- Col 23: Tilt index
- Col 24: Half-set assignment (1=ODD, 2=EVE)
- Cols 25-26: Reserved

---

## 6. Technology Stack Recommendation

### 6.1 Current State Assessment

**Established infrastructure (as of Phase 0 baseline):**
- **React 19 + TypeScript 5 + Vite 8** scaffold at `gui/`
- **FastAPI + Pydantic v2** backend at `backend/`
- **E2E test suite** at `tests/` (35 tests defining API contract)
- **Backend unit tests** at `backend/tests/` (27 tests)
- **Tailwind CSS v4** for styling
- **@tanstack/react-query** for server state management
- **@tanstack/react-table** for data tables
- **react-hook-form + zod** for form validation
- **recharts** for FSC curve plotting
- **lucide-react** for icons

### 6.2 Technology Stack

**Primary: React + TypeScript Web Application with FastAPI Backend**

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **GUI Framework** | React 19 + TypeScript 5 | Modern component-based UI with strong typing; rich ecosystem for forms, tables, charts |
| **Build Tool** | Vite 8 | Fast HMR, TypeScript-native, production builds |
| **Styling** | Tailwind CSS v4 | Utility-first CSS; consistent scientific UI |
| **Routing** | react-router-dom v7 | Client-side routing for feature pages |
| **Data Fetching** | @tanstack/react-query v5 | Caching, background refetch, optimistic updates |
| **Forms** | react-hook-form + zod | Type-safe forms with schema validation |
| **Tables** | @tanstack/react-table v8 | Headless table for tilt-series, jobs |
| **Charts** | recharts v2 | FSC curves, histograms, statistics |
| **Icons** | lucide-react | Clean scientific icons |
| **Backend** | FastAPI + Pydantic v2 | Python API server with auto-generated OpenAPI |
| **Process Mgmt** | Python subprocess | Launch emClarity commands, track PIDs |
| **GPU Monitoring** | nvidia-smi subprocess | GPU detection and utilization |
| **File I/O** | Python pathlib + custom MATLAB parser | Read/write param.m files, project directories |
| **Testing** | vitest (frontend) + pytest (backend/E2E) | Comprehensive test coverage |

**Why web-based (React/FastAPI) for this project:**
1. Modern development ecosystem with rich tooling for forms, validation, and data visualization
2. Separation of concerns: frontend presentation logic cleanly separated from backend process management
3. FastAPI auto-generates OpenAPI documentation, enabling contract-first development
4. React ecosystem has mature libraries for every GUI component needed (tables, forms, charts)
5. TypeScript strict mode catches parameter handling bugs at compile time
6. Backend still runs locally alongside emClarity -- filesystem and GPU access via API endpoints
7. CryoSPARC has demonstrated that web-based GUIs work well for cryo-EM pipelines

### 6.3 Module Structure

```
gui/                              -- React + TypeScript frontend
  src/
    main.tsx                      -- Entry point (React Query provider, BrowserRouter)
    App.tsx                       -- Root component with routes
    index.css                     -- Tailwind CSS imports

    api/
      client.ts                   -- Typed fetch wrapper for backend API
      types.ts                    -- Shared API response types

    components/
      layout/
        MainLayout.tsx            -- App shell (sidebar + header + content area)
        Sidebar.tsx               -- Navigation sidebar with icons
        Header.tsx                -- Top header bar with project info
      common/
        LoadingSpinner.tsx        -- Loading indicator
        ErrorBoundary.tsx         -- Error boundary wrapper

    features/
      project/
        ProjectPage.tsx           -- New project wizard, status dashboard
      parameters/
        ParametersPage.tsx        -- Tabbed parameter editor with validation
      tilt-series/
        TiltSeriesPage.tsx        -- Sortable/filterable tilt-series table
      workflow/
        WorkflowPage.tsx          -- Pipeline state machine + command launcher
      jobs/
        JobsPage.tsx              -- Job table, log viewer, cancel controls
      results/
        ResultsPage.tsx           -- FSC curves, particle stats, system info
      utilities/
        UtilitiesPage.tsx         -- Mask creator, rescaler, geometry ops

    hooks/
      useApi.ts                   -- React Query wrappers (useApiQuery, useApiMutation)

    types/
      parameters.ts               -- ParameterDefinition, ParameterSet, ParameterGroup
      workflow.ts                  -- WorkflowStep, PipelineStep, PipelineState
      project.ts                   -- ProjectInfo, ProjectDirectories, CreateProjectRequest

    lib/
      validation.ts                -- Zod schemas for form validation

backend/                           -- FastAPI + Python backend
  main.py                          -- FastAPI app with CORS, router includes
  requirements.txt                 -- Python dependencies

  api/
    router.py                      -- Main API router
    parameters.py                  -- Parameter CRUD endpoints
    projects.py                    -- Project management endpoints
    workflow.py                    -- Workflow/command endpoints
    jobs.py                        -- Job monitoring endpoints
    system.py                      -- System info endpoints

  models/
    parameter.py                   -- Pydantic parameter models
    project.py                     -- Pydantic project/state models
    workflow.py                    -- Pydantic workflow/command models
    job.py                         -- Pydantic job models

  services/
    parameter_service.py           -- Schema loading, validation, file I/O
    project_service.py             -- Project CRUD, state detection
    workflow_service.py            -- Command building, state machine
    job_service.py                 -- Subprocess management
    system_service.py              -- GPU/CPU detection

tests/                             -- E2E acceptance tests (READ-ONLY)
  conftest.py                      -- Shared fixtures
  test_parameter_schema.py         -- Parameter schema API contract
  test_parameter_validation.py     -- Parameter validation logic
  test_project_management.py       -- Project CRUD operations
  test_workflow_state.py           -- Pipeline state machine enforcement
  test_system_info.py              -- System hardware detection
  test_job_management.py           -- Job lifecycle management
```

---

## 7. Key Constraints

### 7.1 Scientific Validity (Non-Negotiable)

These constraints are inherited from the emClarity design philosophy and must be enforced by the GUI:

1. **Gold-standard FSC independence**: The GUI must never allow operations that mix ODD and EVE half-sets. Half-set assignments (column 24 of coordinate matrix) are set at initialization and must not be modified.

2. **Prevent overfitting**: The GUI should warn or prevent running alignment at unreasonably low sampling rates (high resolution) before sufficient cycles have been completed.

3. **Fail-fast philosophy**: All errors from emClarity subprocesses must be displayed prominently. The GUI must never silently ignore errors or allow users to proceed when a step has failed.

4. **Parameter validation before launch**: Every parameter must be validated against the schema (type, range, required status) before the command is dispatched. Invalid parameters must prevent command execution.

5. **No shortcut execution paths**: The GUI must enforce the pipeline dependency order. Users cannot skip steps even if they are "experienced."

### 7.2 GPU Requirements

- emClarity requires NVIDIA GPUs with CUDA support for most operations (autoAlign, ctf estimate/3d, templateSearch, avg, alignRaw, tomoCPR, pca)
- The GUI must detect available GPUs and validate `nGPUs` against actual hardware
- GPU memory should be displayed to help users size their jobs
- Commands that do NOT require GPUs: check, init, cluster, skip, plotFSC, geometry, cleanTemplateSearch, removeNeighbors, segment, getActiveTilts

### 7.3 Error Handling

- All subprocess output (stdout and stderr) must be captured and displayed in the log viewer
- The log file at `logFile/emClarity_<project>.logfile` must be tailed in real-time
- MATLAB errors (beginning with `Error using` or containing `error(`) must be parsed and highlighted
- Non-zero exit codes from subprocesses must prevent state transitions

### 7.4 Known Bugs in Parameter Handling

The GUI should work around or warn about these documented bugs from the parameter schema:

| Bug ID | Severity | Description | GUI Mitigation |
|--------|----------|-------------|----------------|
| BUG-001 | High | `flgCones` default writes to `Fsc_bfactor` instead of `flgCones` | GUI should always explicitly set both `flgCones` and `Fsc_bfactor` |
| BUG-003 | High | `force_no_symmetry` defaults to true, silently overriding `symmetry` | GUI should default `force_no_symmetry` to false and warn when true |
| BUG-004 | Medium | `peak_mask_fraction` assert references wrong variable | GUI should validate `peak_mask_fraction` range [0,1] before writing to param file |
| BUG-002 | Medium | `eucentric_minTilt`/`eucentric_maxTilt` name mismatch | GUI should use `eucentric_maxTilt` in the parameter file |

### 7.5 Process Management

- emClarity is invoked as a compiled MATLAB executable or via MATLAB runtime
- Long-running operations (ctf 3d, alignRaw, avg, tomoCPR) can take hours to days
- The GUI must handle detached processes that survive GUI restarts
- `CUDA_VISIBLE_DEVICES` environment variable must be set correctly before launching GPU operations

---

## 8. Open Questions / Assumptions

### Questions Requiring Human Confirmation

1. **MATLAB runtime vs. compiled**: Will the GUI invoke emClarity as a compiled binary (`emClarity` script) or through MATLAB directly? The entry point code handles both (`isdeployed` checks). The GUI should support invoking the compiled binary via subprocess.

2. **Parameter file format migration**: The GUI will generate `param.m` files in MATLAB format (name=value). Should we also support a JSON parameter format? The `ParameterConverter` in `python_bridge.py` already supports JSON conversion.

3. **subTomoMeta.mat reading in Python**: The GUI needs to read `.mat` files to reconstruct project state. `scipy.io.loadmat` handles v5 MAT files, but v7.3 MAT files (HDF5-based) require `h5py`. Which format does emClarity use? Assumption: v5 format (standard MATLAB save).

4. **Multi-project support**: Should the GUI support multiple open projects simultaneously, or one project at a time? Assumption: one project at a time (simpler, matches scientific workflow).

5. **Remote execution**: Should the GUI support launching jobs on remote HPC nodes via SSH/SLURM? Or is it expected to run on the same machine as emClarity? Assumption: same machine (local execution via subprocess).

6. **PCA mask options 1 and 2**: These are documented as "broken" in emClarity.m (lines 549-556). Should the GUI hide these options entirely? Assumption: yes, only expose option 3 (user-supplied mask).

7. **`force_no_symmetry` default bug (BUG-003)**: The default is `true`, which silently forces `symmetry=C1` for all users. Should the GUI override this to `false` by default? Assumption: yes, the GUI should default to `false` and always explicitly write `force_no_symmetry=0` in the parameter file.

8. **Cycle-specific parameter files**: Does emClarity expect a single `param.m` that is edited between cycles, or separate files per cycle? Assumption: single file edited between cycles (based on code analysis).

### Assumptions Made

- A1: The GUI runs on the same Linux workstation/HPC node as emClarity
- A2: NVIDIA GPU(s) with CUDA support are available on the host
- A3: IMOD is installed and accessible in `$PATH` (required for autoAlign)
- A4: The `emClarity_ROOT` environment variable is set correctly
- A5: Users have basic familiarity with cryo-EM concepts but not command-line tools
- A6: React + TypeScript + Vite is the GUI framework with FastAPI backend
- A7: The GUI communicates with emClarity exclusively via subprocess execution
- A8: subTomoMeta.mat uses MATLAB v5 format (readable by scipy.io.loadmat)

---

## 9. Risk Assessment

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **subTomoMeta.mat format incompatibility** | Cannot read project state; GUI is blind to progress | Test with real .mat files early; support both v5 and v7.3 via scipy.io and h5py |
| **Parameter interdependencies not captured** | GUI allows invalid parameter combinations | Build comprehensive validation layer from parameter_schema.json; test against known-good param.m files |
| **MATLAB runtime path/environment complexity** | Cannot launch emClarity subprocess | Require `emClarity_ROOT` and `CUDA_VISIBLE_DEVICES` to be set; provide environment validation on startup |
| **Long-running process management** | GUI hangs or loses track of jobs | Use QProcess with non-blocking I/O; persist PID to file for crash recovery |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Parameter file format changes** | GUI-generated param.m not parseable | Strict adherence to `name=value` format; test roundtrip: GUI write -> MATLAB parse -> compare |
| **Missing per-cycle parameter tracking** | Users accidentally use wrong sampling rate for cycle | Implement cycle-specific parameter presets; warn when parameters seem inappropriate for cycle number |
| **GPU detection failures** | Cannot determine available GPU count/memory | Graceful fallback to manual GPU count entry; try pynvml, then nvidia-smi, then manual |
| **FSC file format variations** | Cannot parse/plot resolution curves | Inspect actual FSC output files to determine format before building plotter |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Qt version compatibility** | Widget rendering issues | Pin PySide6 version in pyproject.toml; test on target OS |
| **matplotlib backend conflicts** | Plotting crashes in Qt embedding | Use explicit `backend_qtagg` import; test embedding early |
| **Large log files** | Memory issues tailing logs | Use file seek + read tail (not full file load); limit displayed log lines |

---

## Appendix A: Parameters NOT in the Schema (Parsed Externally)

These parameters appear in workflow_map.md as "required" by specific commands but are not part of the 160 parameters in parameter_schema.json. They are likely parsed directly by individual command functions rather than by BH_parseParameterFile:

| Parameter | Used By | Description |
|-----------|---------|-------------|
| `Tmp_samplingRate` | templateSearch, ctf 3d, init | Template matching sampling rate |
| `Tmp_threshold` | templateSearch | CC threshold for picking |
| `Tmp_targetSize` | templateSearch | Target extraction size |
| `Tmp_angleSearch` | templateSearch | Angular search range |
| `Tmp_medianFilter` | templateSearch | Median filter for noise reduction |
| `Ali_samplingRate` | alignRaw, avg, fsc, tomoCPR, ctf 3d, pca | Alignment sampling rate |
| `Ali_mRadius` | templateSearch, avg | Alignment mask radius |
| `Raw_angleSearch` | alignRaw | Raw alignment angular search |
| `Raw_className` | alignRaw, avg, pca, tomoCPR | Class name identifier |
| `Raw_classes_odd` | alignRaw, avg, pca, tomoCPR | Odd half-set classes |
| `Raw_classes_eve` | alignRaw, avg, pca, tomoCPR | Even half-set classes |
| `Cls_samplingRate` | pca | Classification sampling rate |
| `Cls_className` | fsc | Classification class name |
| `particleRadius` | templateSearch, alignRaw, avg, tomoCPR, reconstruct, init | Particle radius |
| `particleMass` | tomoCPR | Particle mass in MDa |

**GUI implication**: The parameter editor must include these as additional required fields even though they are not in the parsed schema. They follow similar `name=value` format in the param.m file.

## Appendix B: Deprecated Parameter Name Mapping

The GUI should accept both old and new names, but write new names to param.m files:

| New Name | Deprecated Name |
|----------|----------------|
| `ccc_cutoff` | `flgCCCcutoff` |
| `projectVolumes` | `flgProjectVolumes` |
| `classification` | `flgClassify` |
| `multi_reference_alignment` | `flgMultiRefAlignment` |
| `scale_calc_size` | `scaleCalcSize` |
| `limit_to_one_core` | `flgLimitToOneProcess` |
| `fsc_with_chimera` | `fscWithChimera` |
| `minimum_particle_for_fsc_weighting` | `minimumparticleVolume` |
| `fsc_shape_mask` | `flgFscShapeMask` |
| `pca_scale_spaces` | `pcaScaleSpace` |
| `distance_metric` | `Pca_distMeasure` |
| `n_replicates` | `Pca_nReplicates` |
| `update_class_by_ccc` | `updateClassByBestReferenceScore` |
| `move_reference_by_com` | `flgCenterRefCOM` |
| `save_mapback_classes` | `flgColorMap` |
| `tomo_cpr_defocus_range` | `tomoCprDefocusRange` |
| `tomo_cpr_defocus_step` | `tomoCprDefocusStep` |
| `tomo_cpr_defocus_refine` | `tomoCprDefocusRefine` |
| `shape_mask_lowpass_override` | `setMaskLowPass` |
| `shape_mask_threshold_override` | `setMaskThreshold` |
| `pca_mask_threshold` | `setPcaMaskThreshold` |
| `particle_volume_scaling` | `setParticleVolumeScaling` |
| `phase_plate_mode` | `phakePhasePlate` |
| `use_fourier_interp` | `useFourierInterp` |
| `enable_profiling` | `doProfile` |
| `save_tomocpr_diagnostics` | `tomoCprDiagnostics` |

## Appendix C: Complete Category Distribution

Summary of parameters by category (from parameter_schema.json):

| Category | Count | Required |
|----------|-------|----------|
| alignment | ~20 | symmetry |
| ctf | ~25 | -- |
| classification | ~17 | Pca_clusters |
| tomoCPR | ~25 | -- |
| fsc | ~7 | -- |
| microscope | ~5 | PIXEL_SIZE, Cs, VOLTAGE, AMPCONT |
| hardware | ~6 | nGPUs, nCpuCores |
| masking | ~5 | -- |
| template_matching | ~7 | -- |
| dose | ~5 | -- |
| disk_management | ~3 | -- |
| metadata | ~3 | -- |
| **Total** | **~160** | **9** |

---

*End of build-context-master.md*