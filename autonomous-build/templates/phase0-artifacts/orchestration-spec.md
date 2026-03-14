# Orchestration Specification for emClarity

## Document Purpose

This document catalogs all shell scripts, orchestration patterns, external tool dependencies, parallelization strategies, and job scheduling mechanisms in the emClarity codebase. It is organized by functional area.

---

## 1. Main Entry Point: `emClarity.m`

**File**: `/workspaces/cisTEMx/testScripts/emClarity.m`

### Purpose
Central command dispatcher for the entire emClarity pipeline. This MATLAB function acts as the CLI entry point, parsing subcommands and routing to appropriate processing functions.

### Command Dispatch Table

| Command | Handler Function | GPU Required | Parameter File |
|---------|-----------------|-------------|----------------|
| `help` | (inline) | No | No |
| `check` | `BH_checkInstall()` | No | No |
| `init` | `BH_geometryInitialize()` | Yes | Yes |
| `autoAlign` | `BH_runAutoAlign()` | Yes | Yes |
| `ctf estimate` | `BH_ctf_Estimate()` | Yes | Yes |
| `ctf refine` | `BH_ctf_Refine2()` | Yes | Yes |
| `ctf update` | `BH_ctf_Updatefft()` | Yes | Yes |
| `ctf 3d` | `BH_ctf_Correct3d()` | Yes | Yes |
| `ctf ctfRefine` | `EMC_ctf_refine_from_star()` | No | No |
| `templateSearch` | `BH_templateSearch3d_2()` | Yes | Yes |
| `avg` | `BH_average3d()` | Yes | Yes |
| `alignRaw` | `BH_alignRaw3d_v2()` | Yes | Yes |
| `fsc` | `BH_fscGold_class()` | Yes | Yes |
| `plotFSC` | `BH_plotMultiCycleFSC()` | No | No |
| `pca` | `BH_pcaPub()` | Yes | Yes |
| `cluster` | `BH_clusterPub()` | Yes | Yes |
| `tomoCPR` | `BH_synthetic_mapBack()` | Yes | Yes |
| `geometry` | `BH_geometryAnalysis()` | No | Yes |
| `reconstruct` | `BH_to_cisTEM_mapBack()` | Yes | Yes |
| `rescale` | `BH_reScale3d()` | Configurable | No |
| `mask` | `BH_mask3d()` | Yes | No |
| `montage` | (inline) | Yes | Yes |
| `simulate tomogram` | `EMC_syntheticTomogram()` | Yes | No |
| `simulate tlt_file` | `EMC_generate_synthetic_tltFile()` | No | No |
| `simulate projections` | `EMC_generate_projections()` | Yes | No |
| `simulate project` | `EMC_setup_synthetic_project()` | Yes | No |
| `skip` | `BH_skipClassAlignment()` | No | Yes |

### Environment Variable Management

The entry point manages several critical environment variables:

| Variable | Purpose | Set By |
|----------|---------|--------|
| `MATLAB_SHELL` | Forces `/bin/bash` for system() calls | `emClarity.m` |
| `CUDA_VISIBLE_DEVICES` | GPU selection; saved on entry, restored on exit via `onCleanup` | `emClarity.m` / run script |
| `emClarity_ROOT` | Root installation directory | Run script (required) |
| `EMC_AUTOALIGN` | Path to `emC_autoAlign` shell script | `emClarity.m` |
| `EMC_FINDBEADS` | Path to `emC_findBeads` shell script | `emClarity.m` |
| `BH_CHECKINSTALL` | Path to `BH_checkInstall` script | `emClarity.m` |
| `EMC_<DEP>` | cisTEM dependency paths (e.g., `EMC_CTFFIND`, `EMC_TILTXCORR`, `EMC_TILTALIGN`) | `emClarity.m` via `cisTEMDeps.txt` |
| `MCR_CACHE_ROOT` | MATLAB Compiler Runtime cache location (set in run script via `EMC_tmpDir.sh`) | Run script |
| `EMC_CACHE_DIR` | Temporary cache directory (tmpfs or fallback) | `EMC_tmpDir.sh` |
| `EMC_CACHE_MEM` | Available memory in GB on cache filesystem | `EMC_tmpDir.sh` |

### GPU Selection Logic (`select_gpus` function)

When more GPUs are visible than requested:
1. Queries `nvidia-smi --list-gpus` for GPU UUIDs
2. Queries memory per GPU via `nvidia-smi --query-gpu=memory.total`
3. Sorts by memory (descending)
4. Sets `CUDA_VISIBLE_DEVICES` to selected UUIDs, with blocked UUIDs appended after `-1,`
5. Exits after printing recommended export command

### Logging

- Creates `logFile/` directory at startup
- Opens MATLAB diary to `logFile/emClarity_<subTomoMeta>.logfile`
- Uses `onCleanup` to ensure diary is closed on exit/error
- Timestamps run start/end

### Parameter Parsing (`emC_testParse` subfunction)

- Calls `BH_parseParameterFile()` to validate parameter file
- Sets global variables needed by masking functions:
  - `bh_global_binary_mask_low_pass` (default: 14)
  - `bh_global_binary_mask_threshold` (default: 2.5)
  - `bh_global_vol_est_scaling` (default: 1.0)
  - `emc_debug_print` (default: false)

---

## 2. Shell Scripts in `alignment/`

### 2.1 `emC_autoAlign` -- Iterative Tilt-Series Alignment

**File**: `/workspaces/cisTEMx/alignment/emC_autoAlign`

**Purpose**: Core tilt-series alignment via iterative patch tracking with progressive binning refinement. Called by `BH_runAutoAlign.m`.

**Parameters** (19 positional arguments from MATLAB):
1. `inp` - base name of tilt-series
2. `pixelSize` - pixel size in Angstroms
3. `tiltAxisRotation` - tilt axis rotation in degrees
4. `binHigh` / `binLow` / `binInc` - binning range and step
5. `nX`, `nY`, `nZ` - stack dimensions
6. `ext` - file extension
7. `PATCH_SIZE_FACTOR`, `N_ITERS_NO_ROT`, `BORDER_SIZE_PIXELS`, `PATCH_OVERLAP`
8. `RESOLUTION_CUTOFF`, `LOW_RES_CUTOFF`
9. `ITERATIONS_PER_BIN`, `FIRST_ITER_SHIFT_LIMIT_PIXELS`, `DIVIDE_SHIFT_LIMIT_BY`

**External Tools Called** (all IMOD):

| Tool | Purpose |
|------|---------|
| `tiltxcorr` | Cross-correlation alignment of tilt images (initial and patch-based) |
| `xftoxg` | Convert pre-alignment transforms |
| `newstack` | Apply transforms and bin stacks |
| `imodchopconts` | Chop contour models into shorter pieces |
| `tiltalign` | Full tilt alignment with rotation, magnification, local alignment |
| `xfproduct` | Combine sequential transforms |

**Algorithm Flow**:
1. Outer loop over binning values (high to low, i.e., coarse to fine)
2. Inner loop over iterations per bin level
3. **Iteration 1**: Simple `tiltxcorr` cumulative correlation alignment
4. **Iterations 2+**:
   - Create binned pre-aligned stack via `newstack`
   - Run patch-tracking `tiltxcorr` with overlap, borders, shift limits
   - Chop contours via `imodchopconts`
   - Run `tiltalign` (without local alignment for first `N_ITERS_NO_ROT` iterations, with local alignment thereafter)
   - Scale transforms back to unbinned coordinates
5. Final: Copy local alignment, combined transforms, and tilt angles to `fixedStacks/`

**Error Handling**: Minimal -- relies on IMOD tool exit codes. No explicit error trapping.

**Output Files**:
- `fixedStacks/<baseName>.xf` - final global transforms
- `fixedStacks/<baseName>.tlt` - final tilt angles
- `fixedStacks/<baseName>.local` - local alignment transforms
- `fixedStacks/baseName.list` - appends base name to list

### 2.2 `emC_findBeads` -- Gold Bead Finding and Erasure

**File**: `/workspaces/cisTEMx/alignment/emC_findBeads`

**Purpose**: Find gold fiducial beads in 3D reconstruction and create bead-erased projections.

**Parameters**: `baseName`, `NX`, `NY`, `thickness`, `bead_size`

**External Tools Called** (all IMOD):

| Tool | Purpose |
|------|---------|
| `newstack` | Create binned aligned stack (bin 15) |
| `tilt` | Create 3D reconstruction for bead finding |
| `findbeads3d` | Locate beads in 3D reconstruction |
| `tilt` (second call) | Create bead-erased reconstruction via `-ProjectModel` |

**Output Files**:
- `<baseName>.erase` - bead-erased projections

**Cleanup**: Removes intermediate `.rec`, `.mod` files; keeps `.ali` and `.erase`.

### 2.3 MATLAB Wrapper: `BH_runAutoAlign.m`

**File**: `/workspaces/cisTEMx/alignment/BH_runAutoAlign.m`

**Purpose**: MATLAB orchestrator that preprocesses the tilt-series and invokes the shell scripts.

**Pre-processing Steps** (in MATLAB with GPU):
1. Load input stack
2. Optionally skip specified tilts
3. Check axis-switching heuristic (GPU-based overlap calculation)
4. Apply bandpass filter + median filter to each projection
5. Save preprocessed stack

**Shell Script Invocation**:
```matlab
system(sprintf('%s %s %f %f %d %d %d %d %d %d %s %d %d %d %f %f %f %d %d %d > ./emC_autoAliLog_%s.txt', ...
  runPath, baseName, pixelSize, imgRotation, ...))
```

**Post-processing**:
- Optionally runs `BH_refine_on_beads()` for bead-based refinement
- Falls back to `emC_findBeads` if too few beads found
- Cleans up preprocessed stack file

---

## 3. Compilation and Testing Scripts

### 3.1 `mCompile.sh` -- Main Compilation Script

**File**: `/workspaces/cisTEMx/testScripts/mCompile.sh`

**Purpose**: Compile emClarity MATLAB code into standalone binary distribution.

**Environment Variables Required**:
- `emC_DEPS` - path to cisTEM dependency binaries
- `EMC_SOURCE_ROOT` - source code root directory

**Compilation Flow**:
1. Validate input `.m` file exists
2. Extract git short hash for versioning
3. Optionally compile CUDA MEX files via `mexCompile.m`
4. Run `mcc` (MATLAB Compiler) with:
   - Included assets: `fitInMap.py`, `emC_autoAlign`, `emC_findBeads`, `BH_checkInstall`
   - `-R -nodisplay` runtime flag
5. Generate run script (includes `EMC_tmpDir.sh` inline)
6. Package binary + dependencies + docs into versioned directory
7. Optionally create zip distribution

**Generated Run Script Structure**:
- Sets `MCR_BASH` library paths
- Sets `emClarity_ROOT`
- Embeds `EMC_tmpDir.sh` for temp cache management
- Supports `int`/`interactive` mode for MATLAB console
- Passes git short-hash as first argument for version logging

### 3.2 `mexCompile.m` -- CUDA MEX Compilation

**File**: `/workspaces/cisTEMx/mexFiles/mexCompile.m`

**Purpose**: Compile CUDA MEX files for GPU-accelerated operations.

**MEX Files Compiled**:
- `mexCTF` - CTF calculations
- `mexFFT` - FFT operations
- `mexXform3d` - 3D transformations
- `mexSF3D` - Structure factor 3D
- `mexFP16` - Half-precision operations

**CUDA Architecture Targets**: `compute_70` (V100), `compute_75` (Turing), `compute_80` (A100), `compute_86` (A6000/RTX 3090), `compute_89` (Ada)

**Libraries Linked**: `cufft_static_nocallback`, `culibos`, `cudart_static`, `mwlapack`

### 3.3 `EMC_tmpDir.sh` -- Temporary Directory Management

**File**: `/workspaces/cisTEMx/testScripts/EMC_tmpDir.sh`

**Purpose**: Automatically locate tmpfs filesystem for MATLAB Compiler Runtime cache, avoiding slow filesystem I/O and parpool conflicts.

**Algorithm**:
1. Scan mounted tmpfs filesystems via `findmnt -t tmpfs`
2. Select the one with maximum available space
3. If no tmpfs found, fall back to `$TMPDIR` or `/tmp`
4. Create unique directory: `EMC_CACHE_DIR/emC_tmp_${RANDOM}${RANDOM}`
5. Set `MCR_CACHE_ROOT` to this directory
6. Spawn background cleanup process that:
   - Monitors parent PID every 60 seconds
   - Removes cache directory when parent exits or after `MAX_TIME` (7 days default)
   - Handles crash cleanup

### 3.4 `BH_checkInstall.sh` -- Installation Verification

**File**: `/workspaces/cisTEMx/testScripts/BH_checkInstall.sh`

**Purpose**: Dump environment variables to `emClarity_checkInstall.txt` for debugging.

**Variables Checked**:
- CUDA: `CUDA_VISIBLE_DEVICES`, `CUDA_HOME`, `CUDA_BIN_PATH`, `CUDA_CACHE_*`
- IMOD: `IMOD_DIR`
- emClarity: `EMC_CACHE_DIR`, `EMC_CACHE_MEM`, `MCR_CACHE_ROOT`, `emClarity_ROOT`, `IMOD_FORCE_OMP_THREADS`
- System: `SHELL`, `TERM`, `USER`, `PWD`, `PATH`, `LANG`, `HOME`
- Internal: `EMC_AUTOALIGN`, `EMC_FINDBEADS`

### 3.5 `cleanBin.sh` -- Binary Cleanup from Git History

**File**: `/workspaces/cisTEMx/testScripts/cleanBin.sh`

**Purpose**: Remove accidentally committed binaries from git history.

**Commands**: `git filter-branch`, `git gc --aggressive --prune=now`

---

## 4. CTF Processing Scripts and Patterns

### 4.1 `BH_runCtfFind.m` -- CTF Estimation via CTFFIND4

**File**: `/workspaces/cisTEMx/ctf/BH_runCtfFind.m`

**Purpose**: Run CTFFIND4 on individual tilt images to estimate defocus.

**Orchestration Pattern**:
1. Split stack into individual projection images
2. Generate a bash script with `ctffind --amplitude-spectrum-input` heredocs for each image
3. All CTFFIND4 calls launched with `&` (background) for parallelism
4. `wait` at end of script
5. Execute generated script via `system()`
6. Retry mechanism: if script fails, copy and re-run
7. Parse results with `awk` to extract defocus values
8. Merge results into `.tlt` file with column replacement

**External Tools**: `ctffind` (via `EMC_CTFFIND` env var), `newstack` (IMOD)

**Handedness Check**: Runs on both regular and inverted stacks; compares scores to detect inverted handedness.

### 4.2 `BH_ctf_Correct3d.m` -- 3D CTF Correction

**Uses `parfor`** with one worker per GPU for parallel tilt-series processing. Each parfor iteration selects a GPU via `gpuDevice(iGPU+1)`.

### 4.3 `BH_ctf_Updatefft.m` -- CTF Update

**Uses `parfor`** with workers assigned to GPUs. Contains comment about MATLAB confusion with function-vs-variable naming in parfor.

---

## 5. Documentation and Reference Scripts

### 5.1 `recScript2.sh` / `docs/recScript2.sh` -- Tomogram Reconstruction

**Files**: `/workspaces/cisTEMx/docs/additionalScriptsForIdeas/recScript2.sh`, `/workspaces/cisTEMx/docs/recScript2.sh`

**Purpose**: Create bin-10 tomograms for visual inspection and define sub-regions for reconstruction.

**Two Modes**:
- `-1`: Batch bin-10 reconstruction of all tilt-series using `newstack` + `tilt`
- `<baseName>`: Parse IMOD model file to define sub-region reconstructions

**External Tools**: `newstack`, `tilt`, `model2point`, `header` (all IMOD), `python` (for calculations)

**Output**: Per-region reconstruction scripts in `recon/` directory with `tilt` commands.

### 5.2 `runCtfFind4.sh` -- Standalone CTFFIND4 Runner

**File**: `/workspaces/cisTEMx/docs/additionalScriptsForIdeas/runCtfFind4.sh`

**Purpose**: Run CTFFIND4 on split amplitude spectra with heredoc input.

**External Tools**: `ctffind` (cistem), `newstack`, `header` (IMOD)

**Parallelism**: All CTFFIND4 processes launched with `&`, then `wait`.

### 5.3 `runUnblur.sh` -- Frame Alignment

**File**: `/workspaces/cisTEMx/docs/additionalScriptsForIdeas/runUnblur.sh`, `/workspaces/cisTEMx/docs/runUnblur.sh`

**Purpose**: Run Unblur for movie frame alignment (motion correction).

**External Tools**: `unblur_openmp_7_17_15.exe`

### 5.4 `catCTFresults.sh` -- CTF Result Concatenation

**File**: `/workspaces/cisTEMx/docs/additionalScriptsForIdeas/catCTFresults.sh`

**Purpose**: Combine per-projection CTFFIND4 results into a single stack and merge defocus values into `.tlt` file.

**External Tools**: `newstack` (IMOD), `awk`

### 5.5 `runMatFile_ultron.sh` -- PBS Cluster Job Submission

**Files**: `/workspaces/cisTEMx/docs/additionalScriptsForIdeas/runMatFile_ultron.sh`, `/workspaces/cisTEMx/docs/runMatFile_ultron.sh`

**Purpose**: Generate and submit PBS batch jobs for emClarity processing.

**Cluster Details**:
- PBS/Torque scheduler
- Resources: `nodes=1:ppn=28:gpus=4`, walltime 4 days
- Modules: `cuda75/toolkit/7.5.18`, `cryoem/IMOD/4.8.57`
- Job dependencies via `-W depend=afterany:<jobID>`
- Saves job ID to `lastSubmissionIDX.txt` for chaining

**Job Scheduling Pattern**:
```bash
qsub ${depend} -d ${BH_wrkdir} ${jobName} -N BH_${dT}
```

---

## 6. Parallelization Patterns

### 6.1 MATLAB `parfor` Usage

The codebase uses MATLAB's `parfor` (parallel for loops) in 8 files:

| File | Function | Workers | Pattern |
|------|----------|---------|---------|
| `alignment/BH_alignRaw3d_v2.m` | Sub-tomogram alignment | nGPUs | One tomogram per GPU worker |
| `transformations/BH_average3d.m` | Sub-tomogram averaging | nGPUs | Each worker owns a GPU |
| `ctf/BH_ctf_Correct3d.m` | 3D CTF correction | nGPUs (x2 loops) | First loop: reconstruction; second loop: correction |
| `ctf/BH_ctf_Updatefft.m` | CTF FFT update | nWorkers | One GPU per worker |
| `metaData/BH_geometryInitialize.m` | Template matching init | nGPUs | Each worker on a GPU |
| `synthetic/BH_synthetic_mapBack.m` | TomoCPR map-back | nPrjs | Per-projection parallel |
| `testScripts/recScript.m` | Reconstruction | 4 | Per-stack parallel |
| `testScripts/BH_benchmark.m` | Performance testing | nWorkers | GPU memory benchmarks |

### 6.2 `EMC_parpool.m` -- Parallel Pool Management

**File**: `/workspaces/cisTEMx/metaData/EMC_parpool.m`

**Purpose**: Create MATLAB parallel pool with job storage on local cache (tmpfs).

**Key Design**:
- Uses `MCR_CACHE_ROOT` for job storage (avoids slow NFS and parpool conflicts)
- Creates named profile from `MCR_CACHE_ROOT` directory name
- Reuses existing profile if already created in current session
- Cleans up any existing pool before creating new one

### 6.3 GPU Device Selection Pattern

All GPU-using functions follow a consistent pattern:
```matlab
% Inside parfor loop:
iGPUidx = mod(iParProc-1, nGPUs) + 1;
gpuDevice(iGPUidx);
```

The entry point handles initial GPU selection/filtering by:
1. Checking `nGPUs` from parameter file
2. Comparing against `gpuDeviceCount`
3. Selecting highest-memory GPUs if more visible than needed
4. Setting `CUDA_VISIBLE_DEVICES` with UUID-based selection

---

## 7. Temporary File and Cache Management

### 7.1 `EMC_setup_tmp_cache.m`

**File**: `/workspaces/cisTEMx/metaData/EMC_setup_tmp_cache.m`

**Purpose**: Set up per-module cache directories within the main cache hierarchy.

**Cache Hierarchy**:
```
<cache_root>/
  cache/
    ctf3d/          # CTF 3D correction workspace
    to_cisTEM/      # cisTEM export workspace
    to_cisTEM_<X>/  # Custom cisTEM sub-workspaces
```

**Logic**:
- If `fastScratchDisk` (from parameter file) is set, uses it as cache root
- Otherwise falls back to local `cache/` directory
- Validates `fixedStacks/` directory exists for local mode
- Creates directories via `system('mkdir -p ...')`

### 7.2 `EMC_setCacheForFile.m`

**File**: `/workspaces/cisTEMx/metaData/EMC_setCacheForFile.m`

**Purpose**: Select optimal cache location based on available disk space.

**Algorithm**:
- Accepts list of alternate cache directories from parameter file
- Queries free space via `df --output=avail --block-size=1`
- Selects directory with maximum free bytes
- Returns full path for file writing

### 7.3 `BH_imodWait.m` -- Filesystem Synchronization

**File**: `/workspaces/cisTEMx/logicals/BH_imodWait.m`

**Purpose**: Wait for IMOD output files to be fully written to disk.

**Problem Addressed**: IMOD `system()` calls sometimes return before file I/O is complete, especially on network filesystems.

**Algorithm**:
1. Loop checking `header` command success (validates MRC header)
2. Monitor file size growth
3. Extended pause (30s) if filesystem appears slow
4. Error if file stops growing and header still fails

---

## 8. External Tool Dependencies

### 8.1 IMOD Tools (Required)

All accessed via system PATH or wrapped as cisTEM dependencies:

| Tool | Used By | Purpose |
|------|---------|---------|
| `tiltxcorr` | `emC_autoAlign` | Cross-correlation alignment |
| `tiltalign` | `emC_autoAlign` | Full geometric alignment |
| `newstack` | Multiple | Stack manipulation, binning, transforms |
| `tilt` | `emC_findBeads`, `recScript2.sh` | Weighted back-projection |
| `findbeads3d` | `emC_findBeads` | 3D bead detection |
| `xftoxg` | `emC_autoAlign` | Transform conversion |
| `xfproduct` | `emC_autoAlign`, `BH_runAutoAlign.m` | Transform combination |
| `imodchopconts` | `emC_autoAlign` | Contour model editing |
| `imodtrans` | `BH_runAutoAlign.m` | Transform model coordinates |
| `model2point` | `recScript2.sh`, `recScript.m` | Convert model to point data |
| `header` | `recScript2.sh`, `BH_imodWait.m` | MRC header inspection |
| `clip` | `emC_autoAlign` (commented out) | Image filtering |
| `ccderaser` | `emC_autoAlign` (commented out) | CCD artifact removal |

### 8.2 cisTEM Tools (Bundled)

Distributed as dependencies in `bin/deps/`, listed in `cisTEMDeps.txt`:

| Tool | Environment Variable | Purpose |
|------|---------------------|---------|
| `ctffind` | `EMC_CTFFIND` | CTF parameter estimation |
| `tiltxcorr` | `EMC_TILTXCORR` | (cisTEM-modified version) |
| `tiltalign` | `EMC_TILTALIGN` | (cisTEM-modified version) |

### 8.3 Other External Tools

| Tool | Used By | Purpose |
|------|---------|---------|
| `nvidia-smi` | `emClarity.m` (select_gpus) | GPU enumeration and memory query |
| `python` | `emC_autoAlign`, `recScript2.sh` | Inline math calculations |
| `unblur` | `runUnblur.sh` | Movie frame alignment (legacy) |
| `awk` | Multiple scripts | Text processing, column extraction |
| `df` | `EMC_tmpDir.sh`, `EMC_setCacheForFile.m` | Disk space queries |
| `findmnt` | `EMC_tmpDir.sh` | Locate tmpfs mounts |

---

## 9. Python Orchestration

### 9.1 Autonomous Build Orchestrator

**File**: `/workspaces/cisTEMx/autonomous-build/orchestrator.py`

**Purpose**: Multi-agent autonomous development system for coordinating Developer, QA, and Oracle validation agents.

**Architecture**:
- `OrchestratorConfig`: Loads from `config.json`, validates Claude CLI availability
- `ClaudeCodeRunner`: Launches Claude Code CLI sessions with JSON output parsing
- `TaskManager`: Manages task state machine (pending -> in_progress -> complete/deferred)
- `ProgressLogger`: Append-only progress logging
- `Orchestrator`: Main loop with signal handling for graceful shutdown

**Pipeline**: Developer -> QA Review -> Oracle Validation

**Context Management**:
- Warning threshold at 70% context usage
- Split threshold at 85% context usage
- Task splitting via `TaskSplitter` when context exhausted or 3+ retries

**Not part of the cryo-EM processing pipeline** -- this is development infrastructure.

### 9.2 Python Auto-Align Conversion

**File**: `/workspaces/cisTEMx/python/alignment/emc_run_auto_align.py`

**Purpose**: Python equivalent of `BH_runAutoAlign.m` with integrated shell script logic.

**Status**: Partial implementation. GPU preprocessing (bandpass, median filter, axis switching) marked as TODO. IMOD tool calls fully translated to `subprocess.run()` with proper timeout and error handling.

**Key Improvements Over MATLAB Version**:
- Explicit timeout on every subprocess call (60s-1800s depending on operation)
- Structured error handling with `subprocess.CalledProcessError`
- Proper cleanup in `finally` blocks
- Logging throughout
- Command-line interface via `argparse`

### 9.3 GUI Launcher

**File**: `/workspaces/cisTEMx/python/gui/run_gui.sh`

**Purpose**: Launch PySide6-based GUI with proper virtual environment.

**Features**:
- Auto-creates `.venv` if missing
- Detects display availability
- Supports `--rubber-band-mode` for development
- Sets `PYTHONPATH` to include GUI directory

---

## 10. CI/CD Workflows

### 10.1 GitHub Actions Workflows

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| Code Style | `code-style.yml` | Push/PR on Python changes | Ruff linting + formatting |
| Type Checking | `type-checking.yml` | Push/PR on Python changes | Pyright static analysis |
| Unit Tests | `unit-tests.yml` | Push/PR on Python changes | pytest + coverage |
| GPU Tests | `gpu-tests.yml` | Push/PR on CUDA/masking changes | CuPy/GPU validation |
| Security Scan | `security-scan.yml` | Push/PR | Bandit + Safety checks |

**Auto-fix Pattern** (code-style.yml):
- On push to `*_ci` branches, auto-applies Ruff fixes and commits

**GPU Tests**:
- Uses self-hosted runner with GPU
- Installs CuPy (CUDA 12.x or 11.x fallback)
- Tests `CudaBasicOps` and `BasicArrayOps` modules
- Runs performance benchmarks (GPU vs CPU)

### 10.2 Local Quality Checks

**File**: `/workspaces/cisTEMx/scripts/check-python-quality.sh`

**Purpose**: Run same checks as CI locally. Supports `--fix`, `--fast`, `--style-only`, `--types-only`, `--security-only` flags.

**Tools Used**: `ruff`, `pyright`, `bandit`, `safety`

### 10.3 Autonomous Build Hooks

**Pre-commit Hook** (`autonomous-build/hooks/pre-commit-hook.sh`):
- Blocks commits to `tests/` directory
- Checks for commented-out assertions
- Checks for `__eq__` overrides (anti-cheat)

**Stop Hook** (`autonomous-build/hooks/stop-hook.sh`):
- Validates TypeScript compilation
- Runs backend and E2E tests before allowing task completion

---

## 11. Development Environment Setup

### 11.1 `setup-dev.sh`

**File**: `/workspaces/cisTEMx/setup-dev.sh`

**Purpose**: Modern Python development setup with CUDA detection.

**Steps**:
1. Create/activate virtual environment
2. Detect CUDA version via `nvcc --version`
3. Install appropriate CuPy (`cupy-cuda12x` or `cupy-cuda11x`)
4. Install project in development mode (`pip install -e ".[dev,test]"`)
5. Install pre-commit hooks

### 11.2 `setup-dev-env.sh`

**File**: `/workspaces/cisTEMx/setup-dev-env.sh`

**Purpose**: Legacy setup script using Black/isort/flake8 (superseded by Ruff).

### 11.3 DevContainer Version Check

**File**: `/workspaces/cisTEMx/.devcontainer/check-version.sh`

**Purpose**: Validate devcontainer image matches `CONTAINER_VERSION_TOP` and `CONTAINER_REPO_NAME` configuration files.

---

## 12. Processing Pipeline Directory Structure

emClarity expects and creates the following directory layout:

```
project_root/
  rawData/              # Original tilt-series (input)
  fixedStacks/          # CCD-corrected and aligned stacks
    *.fixed             # Corrected stacks
    *.fixed.preprocessed # Bandpass-filtered stacks (temporary)
    *.rawtlt            # Raw tilt angles
    *.tlt               # Refined tilt angles
    *.xf                # Global alignment transforms
    *.local             # Local alignment transforms
    *.erase             # Bead-erased projections
    ctf/                # CTF estimation results
      forCtfFind/       # Temporary CTFFIND4 input/output
    baseName.list       # List of processed tilt-series
  aliStacks/            # CTF-corrected aligned stacks
  cache/                # Temporary processing files
    ctf3d/              # CTF 3D correction workspace
    to_cisTEM/          # cisTEM export workspace
  bin10/                # Bin-10 tomograms for visual inspection
  recon/                # Sub-region reconstruction coordinates and scripts
  convmap/              # Template matching results
  FSC/                  # Resolution curves and statistics
  logFile/              # Processing logs and diary files
  alignResume/          # Alignment checkpoint files (per-tomogram)
  paramRecord/          # Parameter file copies (from cluster submission)
  emC_autoAlign_*/      # Per-tilt-series alignment working directories
    round_1/ ... round_N/  # Iterative alignment results
```

---

## 13. Error Handling Summary

| Component | Error Strategy |
|-----------|---------------|
| `emClarity.m` | MATLAB `error()` for invalid args; `onCleanup` for resource restoration |
| `emC_autoAlign` | None explicit; relies on IMOD exit codes |
| `emC_findBeads` | None explicit; relies on IMOD exit codes |
| `BH_runAutoAlign.m` | Fallback logic (bead refinement -> patch tracking -> findBeads) |
| `BH_runCtfFind.m` | Retry on failure (copy and re-run script); `error()` on second failure |
| `BH_imodWait.m` | Polling loop with extended pause; `error()` on timeout |
| `EMC_parpool.m` | Checks environment variables; `error()` on missing cache |
| `mCompile.sh` | Checks exit codes; `exit 1` on failure |
| `Python emc_run_auto_align.py` | `subprocess.CalledProcessError` catching; timeouts; `RuntimeError` raising |
| `orchestrator.py` | Signal handling; task state checkpointing; retry with splitting |

---

## 14. Key Observations for Build System Design

1. **Heavy IMOD Dependency**: Almost all tilt-series alignment and reconstruction operations delegate to IMOD command-line tools via `system()` calls. Any Python conversion must maintain these subprocess invocations.

2. **GPU-per-Worker Pattern**: The parfor parallelization consistently assigns one GPU to one worker. The `nGPUs` parameter from the config file controls both parallel pool size and GPU allocation.

3. **Filesystem as IPC**: Workers communicate through files on disk (aligned stacks, transform files, checkpoint files). There is no in-memory inter-process communication.

4. **tmpfs Optimization**: Significant engineering effort went into using tmpfs for MATLAB Compiler Runtime cache to avoid parpool conflicts on shared filesystems.

5. **No Job Scheduler Integration**: The production code has no built-in cluster scheduler integration. The PBS scripts in `docs/` are user-provided examples, not part of the main codebase.

6. **Resume Capability**: Alignment (`BH_alignRaw3d_v2.m`) supports resume via per-tomogram checkpoint files in `alignResume/`.

7. **cisTEM Dependencies**: Some IMOD tools are distributed as custom cisTEM-built versions (listed in `cisTEMDeps.txt`), accessed via `EMC_*` environment variables rather than system PATH.

8. **Dual Script Generation**: Several MATLAB functions generate bash scripts on-the-fly (for CTFFIND4 calls, reconstruction commands), then execute them. This pattern enables parallelism and logging but complicates error handling.