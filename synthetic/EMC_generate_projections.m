function [stack_path] = EMC_generate_projections(tomogram_path, tiltfile_path, slab_thickness_angstrom, varargin)
%EMC_generate_projections Generate synthetic tilt series projections from tomogram
%
%   stack_path = EMC_generate_projections(tomogram_path, tiltfile_path, slab_thickness_angstrom)
%
%   Generates a tilt series by projecting a 3D tomogram at each tilt angle
%   specified in the tilt file. Uses slab-based projection for future
%   multi-slice wave propagation.
%
%   Input:
%       tomogram_path          - Path to synthetic tomogram (MRC file)
%       tiltfile_path          - Path to tilt file (_ctf.tlt format, 23 columns)
%       slab_thickness_angstrom - Thickness of each projection slab in Angstroms
%
%   Optional parameters (name-value pairs):
%       'gpu_id'     - GPU device ID (default: 0, maps to MATLAB device 1)
%       'debug_tilt' - Only process the tilt closest to this angle (degrees).
%                      Useful for quick testing. Default: NaN (process all)
%       'dose_scale' - Scale factor for Poisson noise (default: 0)
%                      Applied to per-projection exposure when generating noise.
%                      =0 skips Poisson noise entirely
%                      >0 applies poissrnd(projection * exposure * dose_scale)
%       'st_suffix'  - Optional suffix for output .st filename (default: '')
%                      e.g., '_dose_scale_5' produces '<name>_dose_scale_5.st'
%       'cleanup_tomos' - Delete input tomogram after projection (default: false)
%
%   Output:
%       stack_path - Path to output tilt series stack (MRC file)
%
%   The output stack is saved to the same directory as the tomogram with
%   suffix '_projections.mrc'.
%
%   Convention: Y-axis tilt rotation using BH_defineMatrix with 'TILT' convention
%       Ry(theta) = [ cos(theta),  0,  sin(theta)]
%                   [     0,       1,      0     ]
%                   [-sin(theta),  0,  cos(theta)]
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% Parse inputs
p = inputParser;
addRequired(p, 'tomogram_path', @ischar);
addRequired(p, 'tiltfile_path', @ischar);
addRequired(p, 'slab_thickness_angstrom', @(x) isnumeric(x) && x > 0);
addParameter(p, 'gpu_id', 0, @isnumeric);
addParameter(p, 'debug_tilt', NaN, @isnumeric);  % Only process tilt closest to this angle
addParameter(p, 'dose_scale', 0, @isnumeric);
addParameter(p, 'st_suffix', '', @ischar);
addParameter(p, 'cleanup_tomos', false, @islogical);

parse(p, tomogram_path, tiltfile_path, slab_thickness_angstrom, varargin{:});

gpu_id = p.Results.gpu_id;
debug_tilt = p.Results.debug_tilt;
dose_scale = p.Results.dose_scale;
st_suffix = p.Results.st_suffix;
cleanup_tomos = p.Results.cleanup_tomos;

% Validate dose_scale
if dose_scale < 0
    error('EMC:generate_projections', 'dose_scale must be >= 0, got %.2f', dose_scale);
elseif dose_scale > 0 && dose_scale <= 1
    warning('EMC:generate_projections', ...
            'dose_scale=%.2f is <= 1, will use 1.0 for wave amplitude (Poisson noise still applied)', ...
            dose_scale);
end

%% Validate inputs
if ~isfile(tomogram_path)
    error('EMC:generate_projections', 'Tomogram file not found: %s', tomogram_path);
end

if ~isfile(tiltfile_path)
    error('EMC:generate_projections', 'Tilt file not found: %s', tiltfile_path);
end

%% Initialize GPU
% MATLAB uses 1-based GPU indexing, but allow 0-based for CUDA convention
if gpu_id == 0
    gpuDevice(1);
    fprintf('Using GPU device 0 (MATLAB device 1)\n');
else
    gpuDevice(gpu_id);
    fprintf('Using GPU device %d\n', gpu_id);
end

%% Load tomogram header and volume
fprintf('Loading tomogram from %s\n', tomogram_path);

mrc_obj = MRCImage(tomogram_path, 0);  % Header only first
header = getHeader(mrc_obj);

tomo_size = [header.nX, header.nY, header.nZ];
pixel_size = header.cellDimensionX / header.nX;

fprintf('  Tomogram size: [%d, %d, %d]\n', tomo_size(1), tomo_size(2), tomo_size(3));
fprintf('  Pixel size: %.4f Angstroms\n', pixel_size);

% Convert slab thickness to pixels
slab_thickness_pixels = slab_thickness_angstrom / pixel_size;
fprintf('  Slab thickness: %.2f Angstroms = %.2f pixels\n', ...
        slab_thickness_angstrom, slab_thickness_pixels);

% Load the full volume onto 
fprintf('Loading tomogram volume into memory...\n');
tomogram = OPEN_IMG('single', tomogram_path);
fprintf('  Tomogram loaded to cpu: %.2f GB\n', numel(tomogram) * 4 / 1e9);

%% Load tilt file
fprintf('Loading tilt file from %s\n', tiltfile_path);
TLT = load(tiltfile_path);

n_tilts = size(TLT, 1);
fprintf('  Number of tilts: %d\n', n_tilts);

% Column 4 contains tilt angles in degrees
tilt_angles = TLT(:, 4);
fprintf('  Tilt range: %.1f to %.1f degrees\n', min(tilt_angles), max(tilt_angles));

% Shifts from TLT columns 2-3 (pixels)
shift_x = TLT(:, 2);
shift_y = TLT(:, 3);

% Calculate padding needed for Y-shift interpolation (P pixels on each side)
% Y-component of rotated shift = shift_y (unchanged by Y-axis rotation)
shift_y_padding = ceil(max(abs(shift_y))) + 1;
fprintf('  Y-shift padding: %d pixels (max shift: %.1f)\n', shift_y_padding, max(abs(shift_y)));

% CTF parameters from TLT columns for wave propagation
exposure_per_proj = EMC_tlt_get_projection_values(TLT, 'exposure');  % e⁻/Å² per projection
astig_half = TLT(:, 12);           % meters (|df1-df2|/2)
astig_angle = TLT(:, 13);          % radians
defocus = TLT(:, 15);              % meters
pixel_size_meters = TLT(:, 16);    % meters
Cs = TLT(:, 17);                   % meters
wavelength = TLT(:, 18);           % meters
amplitude_contrast = TLT(:, 19);   % 0-1 (e.g., 0.085)

fprintf('  CTF parameters: defocus=%.2f um, Cs=%.1f mm, wavelength=%.2f pm\n', ...
        defocus(1)*1e6, Cs(1)*1e3, wavelength(1)*1e12);

% Debug mode: only process tilt closest to specified angle
if ~isnan(debug_tilt)
    [~, debug_idx] = min(abs(tilt_angles - debug_tilt));
    fprintf('  DEBUG MODE: Only processing tilt %d (%.1f deg, closest to %.1f deg)\n', ...
            debug_idx, tilt_angles(debug_idx), debug_tilt);
    tilt_indices = debug_idx;
else
    tilt_indices = 1:n_tilts;
end

%% Setup output
projection_size = [tomo_size(1), tomo_size(2)];  % XY dimensions of tomogram
output_stack = zeros([projection_size, n_tilts], 'single');

[tomo_dir, tomo_name, ~] = fileparts(tomogram_path);
stack_path = fullfile(tomo_dir, [tomo_name st_suffix '.st']);

%% Calculate tomogram origin using emClarity convention
tomo_origin = emc_get_origin_index(tomo_size);
fprintf('  Tomogram origin: [%d, %d, %d]\n', tomo_origin(1), tomo_origin(2), tomo_origin(3));

%% Calculate slab thickness in pixels (round UP, ensure at least 1 pixel)
slab_nz = max(1, ceil(slab_thickness_pixels));
fprintf('  Slab dimensions: [%d, %d, %d] pixels\n', projection_size(1), projection_size(2), slab_nz);

%% Y-chunking parameters for GPU memory optimization (Y is tilt axis, unchanged by rotation)
n_y_chunks = 16;
chunk_size_y = ceil(projection_size(2) / n_y_chunks);
fprintf('  Y-chunking: %d chunks of ~%d pixels each\n', n_y_chunks, chunk_size_y);

%% Main projection loop
fprintf('\nGenerating projections...\n');
tic;

first_tilt_process = true;
slice_batch_size = 0;
n_batches = 0; 

n_to_process = length(tilt_indices);
for iProc = 1:n_to_process
    iTilt = tilt_indices(iProc);
    tilt_angle = tilt_angles(iTilt);

    % Get rotation matrix using emClarity convention ('TILT' = Ry matrix)
    % 'fwdVector': active transform on vectors - use for transforming coordinates directly
    % 'fwd': active transform on specimen - use for interpolation/sampling
    rTilt_coordinate = BH_defineMatrix(tilt_angle, 'TILT', 'fwdVector');
    rTilt_sample = BH_defineMatrix(tilt_angle, 'TILT', 'fwd');

    % Calculate bounding box of rotated tomogram in microscope Z
    % Corner coordinates relative to origin (use pre-calculated tomo_origin)
    corners = [1 - tomo_origin(1), tomo_size(1) - tomo_origin(1); ...
               1 - tomo_origin(3), tomo_size(3) - tomo_origin(3)];

    % After Y-axis rotation, Z in microscope frame is:
    % Z_mic = X_tomo * sin(theta) + Z_tomo * cos(theta)  (from rTilt_fwd)
    z_rotated = [];
    for cx = corners(1,:)
        for cz = corners(2,:)
            coord_tomo = [cx; 0; cz];
            coord_mic = rTilt_coordinate * coord_tomo;
            z_rotated = [z_rotated, coord_mic(3)];
        end
    end

    z_min = min(z_rotated);
    z_max = max(z_rotated);

    % Number of slabs to process
    % If the last slab would be undersized, combine it with the second-to-last
    total_thickness = z_max - z_min;
    n_slabs = ceil(total_thickness / slab_thickness_pixels);
    if n_slabs < 1
        n_slabs = 1;
    end

    % Check if last slab would be undersized (less than full slab thickness)
    remainder = total_thickness - (n_slabs - 1) * slab_thickness_pixels;
    if n_slabs > 1 && remainder < slab_thickness_pixels
        % Combine last slab with second-to-last
        n_slabs = n_slabs - 1;
        last_slab_thickness = total_thickness - (n_slabs - 1) * slab_thickness_pixels;
    else
        last_slab_thickness = slab_thickness_pixels;
    end
    % Round up to integer pixels
    last_slab_nz = max(1, ceil(last_slab_thickness));

    prj_index = TLT(iTilt, 1);  % Projection index from TLT column 1
    fprintf('  Tilt %d -> prj %d (%.1f deg): processing %d slabs (z: %.1f to %.1f pixels, last slab: %d px)\n', ...
            iTilt, prj_index, tilt_angle, n_slabs, z_min, z_max, last_slab_nz);

    % Create Fresnel propagator for this tilt using complex mode
    % exp(+i * chi) where chi = -π * λ * Δz * q² (pure Fresnel, no Cs, no AMPCONT)
    % BH_ctfCalc expects all units in METERS (converts to Angstroms internally)
    fresnel_defocus_meters = slab_thickness_angstrom * 1e-10;  % Convert Angstroms to meters
    [fresnel_propagator, ~] = BH_ctfCalc(pixel_size_meters(iTilt), ...
        0, ...                          % Cs = 0 for pure Fresnel
        wavelength(iTilt), ...          % Already in meters from TLT
        fresnel_defocus_meters, ...     % Defocus = slab thickness in meters
        projection_size, ...
        0, ...                          % AMPCONT = 0 (no phase shift)
        -1, ...
        'complex');                     % Triggers complex mode

    % Initialize wave function: amplitude = sqrt(dose_per_projection * pixel_area)
    % exposure_per_proj was pre-calculated outside the loop using helper function
    dose_this_projection = exposure_per_proj(iTilt);
    % Scale dose by dose_scale for wave amplitude (use 1.0 if dose_scale==0 to avoid zero amplitude)
    effective_dose = dose_this_projection * max(dose_scale, 1.0);
    pixel_area_angstrom2 = (pixel_size)^2;  % pixel_size is already in Angstroms
    wave_amplitude = sqrt(effective_dose * pixel_area_angstrom2);
    fprintf('Wave amplitude %f\n', wave_amplitude);

    % Complex wave on GPU: real = amplitude, imag = 0
    wave_func = gpuArray(complex(wave_amplitude * ones(projection_size, 'single'), 0));
    slab_tic = tic;

    % Pre-compute slab parameters
    z_slab_centers = zeros(n_slabs, 1);
    for iSlab = 1:n_slabs
        if iSlab < n_slabs
            z_slab_centers(iSlab) = z_max - (iSlab - 0.5) * slab_thickness_pixels;
        else
            z_prev_end = z_max - (n_slabs - 1) * slab_thickness_pixels;
            z_slab_centers(iSlab) = (z_prev_end + z_min) / 2;
        end
    end


    % Determine batch size for slices based on available GPU memory
    % Accounts for tomo_chunk, coordinate grids, and slab_volume overhead
    if (first_tilt_process)
        slice_batch_size = emc_estimate_slice_batch_size(projection_size, tomo_size, n_y_chunks, slab_nz);
        slice_batch_size = floor(slice_batch_size .* 0.7);
        n_batches = ceil(n_slabs / slice_batch_size);
        first_tilt_process = false
    end
    fprintf('    Processing %d slabs in %d batches (batch size: %d slices)\n', ...
            n_slabs, n_batches, slice_batch_size);

    shifts_rot = rTilt_sample * [shift_x(iTilt); shift_y(iTilt); 0];

    % Y-shift for this tilt (Y unchanged by Y-axis rotation)
    this_shift_y = shifts_rot(2);
    P = shift_y_padding;  % Pre-computed padding for max shift coverage

    % Pre-create coordinate grids for each Y-chunk (reuse across all slabs/batches)
    % Grids are sized for output (chunk_ny), but tomo_chunk will be larger (chunk_ny + 2P)
    chunk_grids = cell(n_y_chunks, 1);
    chunk_grids_last = cell(n_y_chunks, 1);
    for iChunk = 1:n_y_chunks
        y_start = (iChunk - 1) * chunk_size_y + 1;
        y_end = min(iChunk * chunk_size_y, projection_size(2));
        chunk_ny = y_end - y_start + 1;

        % Calculate Y range to load (with P-pixel margins for shift interpolation)
        y_load_start = y_start - P;
        y_load_end = y_end + P;

        % Calculate padding needed for out-of-bounds regions
        pad_before_y = max(0, 1 - y_load_start);
        pad_after_y = max(0, y_load_end - tomo_size(2));

        % Clamp to valid tomogram range
        y_load_start_clamped = max(1, y_load_start);
        y_load_end_clamped = min(tomo_size(2), y_load_end);

        % Origin adjusted for padded tomo_chunk: P + base_origin
        base_origin_y = emc_get_origin_index([1, chunk_ny, 1]);
        origin_y_padded = P + base_origin_y(2);

        % Standard grids (sized for output chunk_ny, NOT the padded load size)
        [gX, gY, gZ] = EMC_coordGrids('cartesian', [projection_size(1), chunk_ny, slab_nz], 'gpu', {});
        chunk_grids{iChunk} = struct('gX', gX, 'gY', gY, 'gZ', gZ, ...
            'origin_y', origin_y_padded, ...
            'y_start', y_start, 'y_end', y_end, ...
            'y_load_start', y_load_start_clamped, 'y_load_end', y_load_end_clamped, ...
            'pad_before_y', pad_before_y, 'pad_after_y', pad_after_y);

        % Last slab grids (if different thickness)
        if last_slab_nz ~= slab_nz
            [gX, gY, gZ] = EMC_coordGrids('cartesian', [projection_size(1), chunk_ny, last_slab_nz], 'gpu', {});
            chunk_grids_last{iChunk} = struct('gX', gX, 'gY', gY, 'gZ', gZ, ...
                'origin_y', origin_y_padded, ...
                'y_start', y_start, 'y_end', y_end, ...
                'y_load_start', y_load_start_clamped, 'y_load_end', y_load_end_clamped, ...
                'pad_before_y', pad_before_y, 'pad_after_y', pad_after_y);
        end
    end



    % Process slabs in batches
    for iBatch = 1:n_batches
        % Determine slab range for this batch
        slab_start = (iBatch - 1) * slice_batch_size + 1;
        slab_end = min(iBatch * slice_batch_size, n_slabs);
        n_slabs_this_batch = slab_end - slab_start + 1;

        fprintf('    Batch %d/%d: slabs %d-%d (%d slices)\n', ...
                iBatch, n_batches, slab_start, slab_end, n_slabs_this_batch);

        % Pre-allocate slices for this batch only
        batch_slices = cell(n_slabs_this_batch, 1);
        for iLocal = 1:n_slabs_this_batch
            batch_slices{iLocal} = gpuArray(zeros(projection_size, 'single'));
        end

        % Process all Y-chunks for this batch
        for iChunk = 1:n_y_chunks
            y_start = chunk_grids{iChunk}.y_start;
            y_end = chunk_grids{iChunk}.y_end;
            origin_y = chunk_grids{iChunk}.origin_y;

            % Load shifted Y-chunk of tomogram (integer shift pre-applied)
            y_load_start = chunk_grids{iChunk}.y_load_start;
            y_load_end = chunk_grids{iChunk}.y_load_end;
            pad_before = chunk_grids{iChunk}.pad_before_y;
            pad_after = chunk_grids{iChunk}.pad_after_y;

            tomo_chunk = tomogram(:, y_load_start:y_load_end, :);

            % Apply padding for out-of-bounds regions (replicate edge values)
            if pad_before > 0
                tomo_chunk = padarray(tomo_chunk, [0, pad_before, 0], 'replicate', 'pre');
            end
            if pad_after > 0
                tomo_chunk = padarray(tomo_chunk, [0, pad_after, 0], 'replicate', 'post');
            end

            tomo_chunk = gpuArray(tomo_chunk);

            % Process all slabs in this batch for this Y-chunk
            % origin_y already includes P offset; use full this_shift_y (not decomposed)
            for iLocal = 1:n_slabs_this_batch
                iSlab = slab_start + iLocal - 1;
                z_offset = z_slab_centers(iSlab);

                % Sample slab and project - use last slab grids if different thickness
                if iSlab == n_slabs && last_slab_nz ~= slab_nz
                    batch_slices{iLocal}(:, y_start:y_end) = sum(interpn(tomo_chunk, ...
                        chunk_grids_last{iChunk}.gX * rTilt_sample(1,1) + (chunk_grids_last{iChunk}.gZ + z_offset) * rTilt_sample(1,3) + tomo_origin(1) + shifts_rot(1), ...
                        chunk_grids_last{iChunk}.gY + origin_y + this_shift_y, ...
                        chunk_grids_last{iChunk}.gX * rTilt_sample(3,1) + (chunk_grids_last{iChunk}.gZ + z_offset) * rTilt_sample(3,3) + tomo_origin(3) + shifts_rot(3), ...
                        'linear', 0), 3);
                else
                    batch_slices{iLocal}(:, y_start:y_end) = sum(interpn(tomo_chunk, ...
                        chunk_grids{iChunk}.gX * rTilt_sample(1,1) + (chunk_grids{iChunk}.gZ + z_offset) * rTilt_sample(1,3) + tomo_origin(1) + shifts_rot(1), ...
                        chunk_grids{iChunk}.gY + origin_y + this_shift_y, ...
                        chunk_grids{iChunk}.gX * rTilt_sample(3,1) + (chunk_grids{iChunk}.gZ + z_offset) * rTilt_sample(3,3) + tomo_origin(3) + shifts_rot(3), ...
                        'linear', 0), 3);
                end
            end

        end
        
        % Wave propagation for this batch of slices
        for iLocal = 1:n_slabs_this_batch
            iSlab = slab_start + iLocal - 1;

            % Phase grating transmission
            phase_grating = exp(1i * batch_slices{iLocal} * dose_scale);
            wave_func = wave_func .* phase_grating;

            % Fresnel propagation
            wave_func = ifft2(fft2(wave_func) .* fresnel_propagator);

            % Progress reporting
            if mod(iSlab, max(1, floor(n_slabs/10))) == 0 || iSlab == n_slabs
                slab_elapsed = toc(slab_tic);
                fprintf('      Slab %d/%d (%.0f%%) - z=%.1f - %.2f sec\n', ...
                        iSlab, n_slabs, 100*iSlab/n_slabs, z_slab_centers(iSlab), slab_elapsed);
            end
        end

    end

    % Calculate mean CTF defocus: original defocus - half of total propagation
    total_propagation = n_slabs * slab_thickness_angstrom * 1e-10;  % meters
    mean_defocus = defocus(iTilt) - total_propagation / 2;

    % Astigmatic defocus vector: df1 > df2 required by BH_ctfCalc
    % All values in METERS (BH_ctfCalc converts to Angstroms internally)
    df1 = mean_defocus + astig_half(iTilt);
    df2 = mean_defocus - astig_half(iTilt);
    ctf_defocus_vector = [df1, df2, astig_angle(iTilt)];  % meters, meters, radians
    fprintf('defocus vector %3.3g %3.3g\n', ctf_defocus_vector);

    % Create complex CTF with full parameters (Cs, astigmatism, amplitude contrast)
    % All units in METERS - BH_ctfCalc converts internally
    [complex_ctf, ~] = BH_ctfCalc(pixel_size_meters(iTilt), ...
        Cs(iTilt), ...                  % Cs in meters (from TLT column 17)
        wavelength(iTilt), ...          % Wavelength in meters (from TLT column 18)
        ctf_defocus_vector, ...         % [df1, df2, angle] in meters/radians
        projection_size, ...
        amplitude_contrast(iTilt), ...  % Actual AMPCONT from TLT (0-1)
        -1, ...
        'complex');
    % Apply CTF to exit wave
    wave_func = ifft2(fft2(wave_func).* complex_ctf);

    % Probability distribution: |wave|² = wave * conj(wave)
    projection = real(wave_func .* conj(wave_func));

    % Apply exposure filter for radiation damage (Grant & Grigorieff 2015)
    % Uses cumulative dose from TLT column 11
    exposure_filter = BH_exposureFilter(projection_size, TLT(iTilt, :), 'GPU', 1, 0);
    %projection = real(ifft2(fft2(projection) .* exposure_filter));

%    % Apply XY shifts (Fourier-domain for sub-pixel accuracy)
%    % TLT shifts are what's needed to align; we apply OPPOSITE to simulate raw projections
%    % BH_multi_gridCoordinates with flgFreqSpace=1 returns normalized frequencies
%    [dU, dV] = BH_multi_gridCoordinates(projection_size, 'Cartesian', 'GPU', {'none'}, 1, 0, 0);
%    shift_phase = exp(-2i * pi * (dU * (-shift_x(iTilt)) + dV * (-shift_y(iTilt))));
%    projection = real(ifft2(fft2(projection) .* shift_phase));
%    clear dU dV shift_phase

    % Apply Poisson noise if dose_scale > 0 (data already on GPU)
    if dose_scale > 0
        fprintf('    Adding Poisson noise: exposure_per_proj=%.2f, dose_this_projection=%.2f, dose_scale=%.2f\n', ...
                exposure_per_proj(iTilt), dose_this_projection, dose_scale);
        projection = poissrnd(projection);
    end

    % Store result using projection index from TLT column 1
    output_stack(:,:,prj_index) = gather(projection);

    % Progress reporting
    if mod(iProc, 5) == 0 || iProc == 1 || iProc == n_to_process
        elapsed = toc;
        rate = iProc / elapsed;
        eta = (n_to_process - iProc) / rate;
        fprintf('  [%d/%d] Tilt %d (%.1f deg), %d slabs (%.1f projections/sec, ETA: %.0f sec)\n', ...
                iProc, n_to_process, iTilt, tilt_angle, n_slabs, rate, eta);
    end
end

elapsed = toc;
fprintf('Projection complete: %d tilts in %.1f seconds (%.2f sec/tilt)\n', ...
        n_to_process, elapsed, elapsed/n_to_process);

%% Save output stack
fprintf('Saving projection stack to %s\n', stack_path);
SAVE_IMG(output_stack, stack_path, pixel_size);



fprintf('Done.\n');

if (cleanup_tomos)
    fprintf('Removing 3d')
    system(sprintf('rm %s\n', tomogram_path))
end

end
