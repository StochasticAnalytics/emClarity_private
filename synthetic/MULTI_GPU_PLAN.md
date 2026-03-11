# Implementation Plan: Multi-GPU Parallelization for EMC_generate_projections

## Overview
Add multi-GPU support to `EMC_generate_projections.m` using `parfor` over tilts, with configurable memory vs disk mode for loading tomogram chunks.

## File to Modify
- `/sa_shared/git/emClarity_private/synthetic/EMC_generate_projections.m`

---

## Design

### Two Operating Modes (Configurable)

1. **Memory Mode** (default when RAM allows):
   - Load tomogram once into memory before parfor
   - Workers extract Y-chunks from the in-memory copy
   - Faster, but requires ~1 extra copy of tomogram in RAM

2. **Disk Mode** (for limited RAM):
   - Workers load Y-chunks directly from disk via `OPEN_IMG`
   - Uses `getVolume` subregion loading: `OPEN_IMG('single', path, [], [y_start, y_end], [])`
   - Zero memory duplication, slightly slower due to disk I/O

### Parallelization Strategy

- **Outer loop**: `parfor` over tilts (embarrassingly parallel - each tilt is independent)
- **Inner loop**: Sequential over Y-chunks and slab batches (same as current)
- **GPU assignment**: Round-robin across available GPUs

---

## Changes Required

### 1. Add New Parameters

```matlab
addParameter(p, 'n_gpus', 1, @isnumeric);  % Number of GPUs to use
addParameter(p, 'use_disk_mode', false, @islogical);  % Load chunks from disk vs memory
```

### 2. GPU Pool Initialization

```matlab
n_gpus = p.Results.n_gpus;
use_disk_mode = p.Results.use_disk_mode;

if n_gpus > 1
    % Ensure parallel pool exists with enough workers
    pool = gcp('nocreate');
    if isempty(pool) || pool.NumWorkers < n_gpus
        delete(pool);
        parpool('Processes', n_gpus);
    end
end
```

### 3. Conditional Tomogram Loading

```matlab
if ~use_disk_mode
    % Memory mode: load full tomogram once
    fprintf('Loading tomogram into memory...\n');
    tomogram = OPEN_IMG('single', tomogram_path);
    fprintf('  Tomogram loaded: %.2f GB\n', numel(tomogram) * 4 / 1e9);
else
    % Disk mode: workers will load chunks on-demand
    fprintf('Using disk mode: chunks loaded on-demand\n');
    tomogram = [];  % Placeholder
end
```

### 4. Restructure Main Loop for parfor

**Current structure:**
```matlab
for iProc = 1:n_to_process
    iTilt = tilt_indices(iProc);
    % ... process tilt
    output_stack(:,:,prj_index) = gather(projection);
end
```

**New structure:**
```matlab
% Pre-allocate output as cell array for parfor
output_cells = cell(n_to_process, 1);
prj_indices = zeros(n_to_process, 1);

parfor iProc = 1:n_to_process
    % Assign GPU (round-robin)
    gpu_id = mod(iProc - 1, n_gpus) + 1;
    gpuDevice(gpu_id);

    iTilt = tilt_indices(iProc);
    % ... compute rotation matrices, z_extent, etc.

    % Process Y-chunks
    for iChunk = 1:n_y_chunks
        y_range = [y_load_start, y_load_end];

        if use_disk_mode
            % Load chunk from disk
            tomo_chunk = OPEN_IMG('single', tomogram_path, [], y_range, []);
        else
            % Extract chunk from memory
            tomo_chunk = tomogram(:, y_range(1):y_range(2), :);
        end

        tomo_chunk = gpuArray(tomo_chunk);
        % ... process chunk (same as current)
    end

    % Store result
    output_cells{iProc} = gather(projection);
    prj_indices(iProc) = TLT(iTilt, 1);
end

% Combine results into output stack
for iProc = 1:n_to_process
    output_stack(:,:,prj_indices(iProc)) = output_cells{iProc};
end
```

### 5. Handle Broadcast Variables for parfor

Variables that need to be broadcast to all workers:
- `tomogram` (if memory mode) - large, but only sent once per worker
- `TLT` - small
- `tilt_angles`, `shift_x`, `shift_y` - small
- `in_plane_rotations` - small
- Various constants (tomo_size, tomo_origin, etc.)

For the tomogram in memory mode, consider using `parallel.pool.Constant`:
```matlab
if ~use_disk_mode && n_gpus > 1
    tomo_const = parallel.pool.Constant(tomogram);
    % Inside parfor: tomo_chunk = tomo_const.Value(:, y_range, :);
end
```

### 6. Pre-compute Tilt-Dependent Values

Move computations that don't depend on Y-chunks outside the inner loop:
- Rotation matrices (rTilt_coordinate, rTilt_sample)
- Z extent (z_min, z_max)
- Y-rotation padding
- Slab centers
- Fresnel propagator
- Wave amplitude

These can be pre-computed for all tilts before the parfor or computed once per worker.

---

## Key Considerations

### Memory Usage
- Memory mode: ~2x tomogram size (original + one copy per unique worker process)
- Disk mode: Only chunk size per worker at any time

### Performance
- Memory mode: Faster chunk access, but limited by RAM
- Disk mode: Slower (disk I/O), but scales to any tomogram size
- NVMe SSDs should make disk mode reasonably fast

### parfor Restrictions
- No nested parfor
- Output must be via sliced arrays or cell arrays
- Cannot modify broadcast variables

---

## Testing

1. Single GPU (n_gpus=1): Should match current behavior exactly
2. Multi-GPU memory mode: Verify correct results, measure speedup
3. Multi-GPU disk mode: Verify correct results, compare performance to memory mode
4. Edge cases: Different tilt counts, chunk sizes, GPU counts
