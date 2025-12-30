function [batch_size, bytes_per_slice] = emc_estimate_slice_batch_size(projection_size, tomo_size, n_y_chunks, slab_nz, safety_margin)
%emc_estimate_slice_batch_size Estimate how many projected slices fit in GPU memory
%
%   [batch_size, bytes_per_slice] = emc_estimate_slice_batch_size(projection_size, tomo_size, n_y_chunks, slab_nz, safety_margin)
%
%   Determines how many 2D slice arrays (projected slabs) can fit in available
%   GPU memory after reserving memory for slab interpolation operations.
%
%   Nomenclature:
%       Slab  - 3D volume being interpolated (X × Ychunk × Zslab), one at a time
%       Slice - 2D projection of a slab after summing over Z (X × Y)
%
%   Memory reserved for interpolation operations (per Y-chunk):
%       - tomo_chunk: X × Ychunk × Z (tomogram Y-slice loaded to GPU)
%       - x_idx, y_idx, z_idx: 3 × X × Ychunk × Zslab (coordinate grids)
%       - slab_volume: X × Ychunk × Zslab (interpolated slab before projection)
%       Total overhead: tomo_chunk + 4 × slab_size
%
%   Input:
%       projection_size - [nx, ny] size of each slice
%       tomo_size       - [nx, ny, nz] full tomogram dimensions
%       n_y_chunks      - Number of Y-chunks for chunked processing
%       slab_nz         - Z thickness of slab in pixels
%       safety_margin   - Extra safety factor (default: 1.2, means 20% extra margin)
%
%   Output:
%       batch_size      - Number of slices that can fit in a batch
%       bytes_per_slice - Memory per slice in bytes
%
%   Example:
%       batch_size = emc_estimate_slice_batch_size([4096, 4096], [4096, 4096, 384], 4, 20);

if nargin < 5
    safety_margin = 2.0;  % Default: 100% safety margin (conservative)
end

% Validate inputs
if safety_margin < 1.0
    error('EMC:estimate_slice_batch_size', ...
          'safety_margin must be >= 1.0, got %.2f', safety_margin);
end

% Get current GPU memory status
gpu_info = gpuDevice();
available_bytes = gpu_info.AvailableMemory;

% Calculate memory needed for interpolation operations
chunk_ny = ceil(projection_size(2) / n_y_chunks);
bytes_per_element = 4;  % single precision

% tomo_chunk: X × Ychunk × Z (loaded once per Y-chunk)
tomo_chunk_bytes = projection_size(1) * chunk_ny * tomo_size(3) * bytes_per_element;

% Slab dimensions for grids: X × Ychunk × Zslab
slab_elements = projection_size(1) * chunk_ny * slab_nz;

% Pre-created coordinate grids for ALL Y-chunks (gX, gY, gZ stored in structs)
% Each chunk has 3 grids, and we have n_y_chunks sets (plus possibly last_slab grids)
coord_grids_per_chunk = 3 * slab_elements * bytes_per_element;
all_coord_grids_bytes = n_y_chunks * coord_grids_per_chunk * 2;  % *2 for last_slab grids

% Temporaries during interpn: index arrays, slab result, sum (conservative: 10x slab size)
interp_temp_bytes = 10 * slab_elements * bytes_per_element;

% Total overhead for interpolation
interp_overhead = tomo_chunk_bytes + all_coord_grids_bytes + interp_temp_bytes;
interp_overhead_with_safety = interp_overhead * safety_margin;

% Memory per slice: single precision (4 bytes per element)
bytes_per_slice = projection_size(1) * projection_size(2) * bytes_per_element;

% Available memory for slices = total available - reserved for interpolation
available_for_slices = available_bytes - interp_overhead_with_safety;

if available_for_slices <= 0
    warning('EMC:estimate_slice_batch_size', ...
            'Interpolation overhead (%.2f GB) exceeds available GPU memory (%.2f GB). Using batch_size=1.', ...
            interp_overhead_with_safety / 1e9, available_bytes / 1e9);
    batch_size = 1;
else
    batch_size = max(1, floor(available_for_slices / bytes_per_slice));
end

fprintf('  GPU memory: %.2f GB available\n', available_bytes / 1e9);
fprintf('  Interpolation overhead: tomo_chunk=%.2f GB, all_grids=%.2f GB, interp_temp=%.2f GB\n', ...
        tomo_chunk_bytes / 1e9, all_coord_grids_bytes / 1e9, interp_temp_bytes / 1e9);
fprintf('  Total reserved: %.2f GB (with %.0f%% safety margin)\n', ...
        interp_overhead_with_safety / 1e9, (safety_margin - 1) * 100);
fprintf('  Available for slices: %.2f GB, slice size: %.2f MB, batch size: %d slices\n', ...
        available_for_slices / 1e9, bytes_per_slice / 1e6, batch_size);

end
