function [tomo_path, csv_path] = EMC_syntheticTomogram(template_path, tomo_size, ...
                                                        exclusion_factor, output_path, output_prefix, varargin)
%EMC_syntheticTomogram Generate synthetic tomogram with randomly placed particles
%
%   [tomo_path, csv_path] = EMC_syntheticTomogram(template_path, tomo_size, ...
%                                                  exclusion_factor, output_path, output_prefix)
%
%   Generates a synthetic 3D tomogram by placing randomly rotated copies of a
%   particle template at random positions. Outputs the tomogram and a CSV file
%   with particle parameters matching emClarity's template search format.
%
%   Input:
%       template_path    - Path to MRC file containing 3D particle template
%       tomo_size        - [nX, nY, nZ] tomogram dimensions (must be even)
%       exclusion_factor - Multiplier for particle radius (>= 1.0, controls density)
%       output_path      - Directory for output files (must exist)
%       output_prefix    - Output file prefix (must not already exist)
%
%   Optional parameters (name-value pairs):
%       'max_particles'  - Maximum number of particles to place (default: inf)
%       'max_attempts'   - Maximum placement attempts (default: 100000)
%       'gpu_id'         - GPU device ID (default: 1)
%
%   Output:
%       tomo_path - Path to output synthetic tomogram MRC file
%       csv_path  - Path to output CSV file with particle parameters
%
%   The CSV file uses emClarity's 31-field format:
%       score, samplingRate, filler, id, 6 flags, posX, posY, posZ (Angstroms),
%       phi, theta, psi-phi (degrees), rotation matrix (9 elements), final flag
%
%   Example:
%       [tomo, csv] = EMC_syntheticTomogram('particle.mrc', [512,512,256], 1.5, ...
%                                            '/output/', 'synthetic_001');
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% Parse inputs
p = inputParser;
addRequired(p, 'template_path', @ischar);
addRequired(p, 'tomo_size', @(x) isnumeric(x) && numel(x) == 3);
addRequired(p, 'exclusion_factor', @(x) isnumeric(x) && x >= 1.0);
addRequired(p, 'output_path', @ischar);
addRequired(p, 'output_prefix', @ischar);
addParameter(p, 'max_particles', inf, @isnumeric);
addParameter(p, 'max_attempts', 100000, @isnumeric);
addParameter(p, 'gpu_id', 1, @isnumeric);

parse(p, template_path, tomo_size, exclusion_factor, output_path, output_prefix, varargin{:});

max_particles = p.Results.max_particles;
max_attempts = p.Results.max_attempts;
gpu_id = p.Results.gpu_id;

%% Validate inputs
% Check tomo_size is even
tomo_size = tomo_size(:)';  % Ensure row vector
if any(mod(tomo_size, 2) ~= 0)
    error('EMC:syntheticTomogram', 'tomo_size must have even dimensions in all axes');
end

% Check template exists
if ~isfile(template_path)
    error('EMC:syntheticTomogram', 'Template file does not exist: %s', template_path);
end

% Check output directory exists
if ~isfolder(output_path)
    error('EMC:syntheticTomogram', 'Output directory does not exist: %s', output_path);
end

% Check output files do not already exist
tomo_path = fullfile(output_path, sprintf('%s.mrc', output_prefix));
csv_path = fullfile(output_path, sprintf('%s.csv', output_prefix));

if isfile(tomo_path)
    error('EMC:syntheticTomogram', 'Output file already exists: %s', tomo_path);
end
if isfile(csv_path)
    error('EMC:syntheticTomogram', 'Output file already exists: %s', csv_path);
end

%% Initialize GPU
gpuDevice(gpu_id);
fprintf('Using GPU device %d\n', gpu_id);

%% Load template and get pixel size from header
fprintf('Loading template from %s\n', template_path);

% Get pixel size from header
mrc_image = MRCImage(template_path, 0);
header = getHeader(mrc_image);
pixel_size = header.cellDimensionX / header.nX;
fprintf('Pixel size: %.3f Angstroms\n', pixel_size);

% Load template volume
template = OPEN_IMG('single', template_path);
template_size = size(template);
fprintf('Template size: [%d, %d, %d]\n', template_size(1), template_size(2), template_size(3));

% Pad to even if needed
pad_needed = mod(template_size, 2);
if any(pad_needed)
    fprintf('Padding template to even dimensions\n');
    template = BH_padZeros3d(template, [0,0,0], pad_needed, 'cpu', 'single');
    template_size = size(template);
end

%% Create binary template for shape-based collision detection
fprintf('Creating binary template using EMC_maskReference\n');

% Use EMC_maskReference to create shape-based mask
binary_template = EMC_maskReference(template, pixel_size, {'lowpass', 14; 'threshold', 2.4});
binary_template = binary_template > 0.5;  % Convert to logical
fprintf('Binary template: %d voxels occupied (%.1f%% of volume)\n', ...
        sum(binary_template(:)), 100 * sum(binary_template(:)) / numel(binary_template));

% Dilate binary template by exclusion_factor for collision detection
% This effectively adds a buffer zone around the particle
if exclusion_factor > 1.0
    se_radius = round((exclusion_factor - 1.0) * max(template_size) / 2);
    if se_radius > 0
        se = strel('sphere', se_radius);
        binary_template = imdilate(binary_template, se);
        fprintf('Dilated binary template by %d pixels (exclusion_factor=%.2f): %d voxels\n', ...
                se_radius, exclusion_factor, sum(binary_template(:)));
    end
end

% Bin the binary template for occupancy map
occupancy_bin = 3;
binary_template_binned = bin_volume(binary_template, occupancy_bin) > 0;
fprintf('Binned binary template: [%d, %d, %d] -> [%d, %d, %d]\n', ...
        template_size(1), template_size(2), template_size(3), ...
        size(binary_template_binned, 1), size(binary_template_binned, 2), size(binary_template_binned, 3));

%% Initialize interpolators on GPU
fprintf('Initializing GPU interpolators\n');
[template_interp, ~] = interpolator(gpuArray(single(template)), ...
                                     [0,0,0], [0,0,0], 'Bah', 'forward', 'C1', false);
% Interpolator for binned binary template (for collision detection)
[binary_binned_interp, ~] = interpolator(gpuArray(single(binary_template_binned)), ...
                                          [0,0,0], [0,0,0], 'Bah', 'forward', 'C1', false);

%% Initialize output volumes
fprintf('Initializing tomogram [%d, %d, %d] on CPU\n', tomo_size(1), tomo_size(2), tomo_size(3));
tomogram = zeros(tomo_size, 'single');

% Binned occupancy map (occupancy_bin already set above)
occupancy_size = ceil(tomo_size / occupancy_bin);
binned_template_size = size(binary_template_binned);

% X-chunking: keep full occupancy on CPU, load chunks to GPU
n_x_chunks = 4;
chunk_size_x = ceil(tomo_size(1) / n_x_chunks);
fprintf('Initializing occupancy map on CPU [%d, %d, %d] (binned %dx, %d X-chunks)\n', ...
        occupancy_size(1), occupancy_size(2), occupancy_size(3), occupancy_bin, n_x_chunks);
occupancy_cpu = false(occupancy_size);

%% Calculate valid placement bounds
half_template = ceil(template_size / 2);
min_bound = half_template + 1;
max_bound = tomo_size - half_template;

fprintf('Valid placement bounds: [%d-%d, %d-%d, %d-%d]\n', ...
        min_bound(1), max_bound(1), min_bound(2), max_bound(2), min_bound(3), max_bound(3));

% Check if placement is possible
if any(min_bound > max_bound)
    error('EMC:syntheticTomogram', 'Template is too large for the specified tomogram size');
end

%% Initialize particle storage
particles = struct();
particles.pos = [];
particles.pos_ang = [];
particles.angles = [];
particles.shifts = [];
particles.rotmat = [];

%% Main placement loop - process in X-bands to reduce GPU memory
fprintf('Starting particle placement in %d X-bands...\n', n_x_chunks);
particle_count = 0;
attempts = 0;
consecutive_failures = 0;
max_consecutive_failures = 300;
last_report_time = 0;
report_interval = 5;  % Report every 5 seconds

% Calculate overlap needed for binary mask checks (in binned coords)
overlap_occ = ceil(max(binned_template_size) / 2);

tic;
for iChunk = 1:n_x_chunks
    % Calculate X range for this chunk (in full-resolution coords)
    x_min_chunk = (iChunk - 1) * chunk_size_x + 1;
    x_max_chunk = min(iChunk * chunk_size_x, tomo_size(1));

    % Calculate occupancy chunk range with overlap (in binned coords)
    x_min_occ = max(1, floor(x_min_chunk / occupancy_bin) - overlap_occ);
    x_max_occ = min(occupancy_size(1), ceil(x_max_chunk / occupancy_bin) + overlap_occ);

    % Load chunk of occupancy to GPU
    occupancy_chunk = gpuArray(occupancy_cpu(x_min_occ:x_max_occ, :, :));

    % Update bounds for this chunk
    chunk_min_bound = [max(min_bound(1), x_min_chunk), min_bound(2), min_bound(3)];
    chunk_max_bound = [min(max_bound(1), x_max_chunk), max_bound(2), max_bound(3)];

    fprintf('  Processing X-band %d/%d (x=%d-%d, occ=%d-%d with overlap)\n', ...
            iChunk, n_x_chunks, x_min_chunk, x_max_chunk, x_min_occ, x_max_occ);

    % Reset consecutive failures for new chunk
    consecutive_failures = 0;
    chunk_attempts = 0;

    while particle_count < max_particles && attempts < max_attempts
        attempts = attempts + 1;
        chunk_attempts = chunk_attempts + 1;

        % Progress reporting every few seconds
        elapsed = toc;
        if elapsed - last_report_time >= report_interval
            if particle_count > 0
                rate = particle_count / elapsed;
                fprintf('    [%.0fs] %d particles placed, %d attempts, %d consecutive failures (%.1f particles/sec)\n', ...
                        elapsed, particle_count, attempts, consecutive_failures, rate);
            else
                fprintf('    [%.0fs] Searching for valid positions... %d attempts, %d consecutive failures\n', ...
                        elapsed, attempts, consecutive_failures);
            end
            last_report_time = elapsed;
        end

        % Generate random position within chunk bounds
        pos = [randi([chunk_min_bound(1), chunk_max_bound(1)]), ...
               randi([chunk_min_bound(2), chunk_max_bound(2)]), ...
               randi([chunk_min_bound(3), chunk_max_bound(3)])];

        % Generate random rotation (matching BH_defineMatrix method)
        [phi, theta, psi_minus_phi, rotmat] = generate_random_rotation();
        angles = [phi, theta, psi_minus_phi];

        % Generate random subpixel shifts [-1, 1] (scaled for binned coords)
        shifts = 2 * rand(1, 3) - 1;
        shifts_binned = shifts / occupancy_bin;

        % Rotate binned binary template on GPU (for collision detection)
        rotated_binary_binned_gpu = binary_binned_interp.interp3d(angles, shifts_binned, 'Bah', 'forward', 'C1');
        rotated_binary_binned = gather(rotated_binary_binned_gpu) > 0.5;  % Threshold to binary

        % Check for collision using binary mask shape
        if ~check_collision_binary(pos, rotated_binary_binned, occupancy_chunk, ...
                                   occupancy_bin, x_min_occ, occupancy_size)
            consecutive_failures = consecutive_failures + 1;
            if consecutive_failures >= max_consecutive_failures
                fprintf('    X-band %d saturated after %d consecutive failed attempts\n', ...
                        iChunk, consecutive_failures);
                break;
            end
            continue;
        end

        consecutive_failures = 0;
        particle_count = particle_count + 1;

        % Rotate template on GPU with subpixel shifts
        rotated_gpu = template_interp.interp3d(angles, shifts, 'Bah', 'forward', 'C1');

        % Copy back to CPU
        rotated = gather(rotated_gpu);

        % Insert into tomogram (CPU)
        tomogram = insert_particle(tomogram, rotated, pos, template_size);

        % Update occupancy with binary mask shape (both GPU chunk and CPU full array)
        [occupancy_chunk, occupancy_cpu] = update_occupancy_binary(pos, rotated_binary_binned, ...
            occupancy_chunk, occupancy_cpu, occupancy_bin, x_min_occ, occupancy_size);

        % Store particle data
        origin = ceil((tomo_size + 1) / 2);
        pos_ang = (pos - origin) * pixel_size;  % Position in Angstroms

        particles.pos = [particles.pos; pos];
        particles.pos_ang = [particles.pos_ang; pos_ang];
        particles.angles = [particles.angles; angles];
        particles.shifts = [particles.shifts; shifts];
        particles.rotmat = cat(3, particles.rotmat, rotmat);

        % Report on first particle and every 10 thereafter
        if particle_count == 1 || mod(particle_count, 10) == 0
            elapsed = toc;
            rate = particle_count / elapsed;
            fprintf('    Placed particle %d at [%d, %d, %d] (%.1f particles/sec)\n', ...
                    particle_count, pos(1), pos(2), pos(3), rate);
            last_report_time = elapsed;
        end
    end

    % Check if we've reached limits
    if particle_count >= max_particles
        fprintf('  Reached max_particles limit (%d)\n', max_particles);
        break;
    end
    if attempts >= max_attempts
        fprintf('  Reached max_attempts limit (%d)\n', max_attempts);
        break;
    end
end

elapsed = toc;
fprintf('Placement complete: %d particles in %.1f seconds\n', particle_count, elapsed);

%% Save outputs
fprintf('Saving tomogram to %s\n', tomo_path);
SAVE_IMG(tomogram, tomo_path, pixel_size);

fprintf('Saving CSV to %s\n', csv_path);
write_csv(csv_path, particles, 1);

% Save tomogram size/pixel info for reference (in case tomogram is deleted)
[tomo_dir, tomo_name, ~] = fileparts(tomo_path);
tomosize_path = fullfile(tomo_dir, sprintf('%s.tomosize', tomo_name));  % <tomogram_name>.tomosize
fprintf('Saving tomosize to %s\n', tomosize_path);
fid = fopen(tomosize_path, 'w');
fprintf(fid, '%d\n', tomo_size(1));
fprintf(fid, '%d\n', tomo_size(2));
fprintf(fid, '%d\n', tomo_size(3));
fprintf(fid, '%.6f\n', pixel_size);
fclose(fid);

% Cleanup
template_interp.delete();
binary_binned_interp.delete();

fprintf('Done. Output files:\n');
fprintf('  Tomogram: %s\n', tomo_path);
fprintf('  CSV: %s\n', csv_path);
fprintf('  Tomosize: %s\n', tomosize_path);

end

%% Helper functions

function [phi, theta, psi_minus_phi, R] = generate_random_rotation()
%GENERATE_RANDOM_ROTATION Generate uniform random rotation matching BH_defineMatrix
%   Matches the random rotation generation in BH_defineMatrix.m lines 55-66

    % Generate random point on unit sphere
    randXYZ = rand(1, 3) - 0.5;
    randXYZ = randXYZ ./ sqrt(sum(randXYZ.^2));

    % Convert to angles (radians)
    angles_rad = [atan2(randXYZ(2), randXYZ(1)), ...
                  acos(randXYZ(3)), ...
                  (2 * pi * (rand(1) - 0.5))];

    % Convert to degrees
    angles_deg = angles_rad * (180 / pi);

    phi = angles_deg(1);
    theta = angles_deg(2);
    psi = angles_deg(3);
    psi_minus_phi = psi - phi;

    % Get rotation matrix for CSV output (using 'inv' direction as in template search)
    R = BH_defineMatrix([phi, theta, psi_minus_phi], 'Bah', 'inv');
end

function is_valid = check_collision(cx, cy, cz, occupancy, radius, bin_factor)
%CHECK_COLLISION Check if position conflicts with existing particles (GPU, binned)

    % Scale coordinates and radius to binned space
    cx_bin = round(cx / bin_factor);
    cy_bin = round(cy / bin_factor);
    cz_bin = round(cz / bin_factor);
    radius_bin = radius / bin_factor;

    r = ceil(radius_bin);
    radius_sq = radius_bin^2;

    % Get bounding box for exclusion sphere in binned coordinates
    x_range = max(1, cx_bin-r):min(size(occupancy, 1), cx_bin+r);
    y_range = max(1, cy_bin-r):min(size(occupancy, 2), cy_bin+r);
    z_range = max(1, cz_bin-r):min(size(occupancy, 3), cz_bin+r);

    % Extract local region (stays on GPU if occupancy is gpuArray)
    local = occupancy(x_range, y_range, z_range);

    % Create sphere mask on GPU
    [dx, dy, dz] = ndgrid(gpuArray(single(x_range - cx_bin)), ...
                          gpuArray(single(y_range - cy_bin)), ...
                          gpuArray(single(z_range - cz_bin)));
    sphere_mask = (dx.^2 + dy.^2 + dz.^2) <= radius_sq;

    % Check if any occupied voxels within sphere (gather single boolean)
    is_valid = ~gather(any(local(sphere_mask)));
end

function is_valid = check_collision_chunked(cx, cy, cz, occupancy_chunk, radius, bin_factor, x_offset_occ)
%CHECK_COLLISION_CHUNKED Check collision against GPU occupancy chunk with X offset
%   x_offset_occ is the starting index of the chunk in the full occupancy array (binned coords)

    % Scale coordinates and radius to binned space
    cx_bin = round(cx / bin_factor);
    cy_bin = round(cy / bin_factor);
    cz_bin = round(cz / bin_factor);
    radius_bin = radius / bin_factor;

    % Convert to chunk-local coordinates
    cx_local = cx_bin - x_offset_occ + 1;

    r = ceil(radius_bin);
    radius_sq = radius_bin^2;

    % Get bounding box for exclusion sphere in chunk-local coordinates
    x_range = max(1, cx_local-r):min(size(occupancy_chunk, 1), cx_local+r);
    y_range = max(1, cy_bin-r):min(size(occupancy_chunk, 2), cy_bin+r);
    z_range = max(1, cz_bin-r):min(size(occupancy_chunk, 3), cz_bin+r);

    % Check if range is valid (sphere might be partially outside chunk)
    if isempty(x_range) || isempty(y_range) || isempty(z_range)
        is_valid = true;  % Can't check, assume valid (will be checked by next chunk)
        return;
    end

    % Extract local region from GPU chunk
    local = occupancy_chunk(x_range, y_range, z_range);

    % Create sphere mask on GPU
    [dx, dy, dz] = ndgrid(gpuArray(single(x_range - cx_local)), ...
                          gpuArray(single(y_range - cy_bin)), ...
                          gpuArray(single(z_range - cz_bin)));
    sphere_mask = (dx.^2 + dy.^2 + dz.^2) <= radius_sq;

    % Check if any occupied voxels within sphere
    is_valid = ~gather(any(local(sphere_mask)));
end

function occupancy = update_occupancy(cx, cy, cz, occupancy, radius, bin_factor)
%UPDATE_OCCUPANCY Mark spherical region as occupied (GPU, binned)

    % Scale coordinates and radius to binned space
    cx_bin = round(cx / bin_factor);
    cy_bin = round(cy / bin_factor);
    cz_bin = round(cz / bin_factor);
    radius_bin = radius / bin_factor;

    r = ceil(radius_bin);
    radius_sq = radius_bin^2;

    % Get bounding box for exclusion sphere in binned coordinates
    x_range = max(1, cx_bin-r):min(size(occupancy, 1), cx_bin+r);
    y_range = max(1, cy_bin-r):min(size(occupancy, 2), cy_bin+r);
    z_range = max(1, cz_bin-r):min(size(occupancy, 3), cz_bin+r);

    % Create sphere mask on GPU
    [dx, dy, dz] = ndgrid(gpuArray(single(x_range - cx_bin)), ...
                          gpuArray(single(y_range - cy_bin)), ...
                          gpuArray(single(z_range - cz_bin)));
    sphere_mask = (dx.^2 + dy.^2 + dz.^2) <= radius_sq;

    % Mark as occupied (stays on GPU)
    local = occupancy(x_range, y_range, z_range);
    local(sphere_mask) = true;
    occupancy(x_range, y_range, z_range) = local;
end

function [occupancy_chunk, occupancy_cpu] = update_occupancy_chunked(cx, cy, cz, ...
    occupancy_chunk, occupancy_cpu, radius, bin_factor, x_offset_occ)
%UPDATE_OCCUPANCY_CHUNKED Mark spherical region as occupied in both GPU chunk and CPU full array
%   x_offset_occ is the starting index of the chunk in the full occupancy array (binned coords)

    % Scale coordinates and radius to binned space
    cx_bin = round(cx / bin_factor);
    cy_bin = round(cy / bin_factor);
    cz_bin = round(cz / bin_factor);
    radius_bin = radius / bin_factor;

    % Convert to chunk-local coordinates
    cx_local = cx_bin - x_offset_occ + 1;

    r = ceil(radius_bin);
    radius_sq = radius_bin^2;

    % Get bounding box in full occupancy coordinates (for CPU update)
    x_range_full = max(1, cx_bin-r):min(size(occupancy_cpu, 1), cx_bin+r);
    y_range = max(1, cy_bin-r):min(size(occupancy_cpu, 2), cy_bin+r);
    z_range = max(1, cz_bin-r):min(size(occupancy_cpu, 3), cz_bin+r);

    % Get bounding box in chunk-local coordinates (for GPU update)
    x_range_chunk = max(1, cx_local-r):min(size(occupancy_chunk, 1), cx_local+r);

    % Create sphere mask (CPU version for full array)
    [dx_full, dy, dz] = ndgrid(single(x_range_full - cx_bin), ...
                               single(y_range - cy_bin), ...
                               single(z_range - cz_bin));
    sphere_mask_cpu = (dx_full.^2 + dy.^2 + dz.^2) <= radius_sq;

    % Update CPU full array
    local_cpu = occupancy_cpu(x_range_full, y_range, z_range);
    local_cpu(sphere_mask_cpu) = true;
    occupancy_cpu(x_range_full, y_range, z_range) = local_cpu;

    % Update GPU chunk (only if sphere overlaps with chunk)
    if ~isempty(x_range_chunk)
        % Create sphere mask (GPU version for chunk)
        [dx_chunk, dy_gpu, dz_gpu] = ndgrid(gpuArray(single(x_range_chunk - cx_local)), ...
                                            gpuArray(single(y_range - cy_bin)), ...
                                            gpuArray(single(z_range - cz_bin)));
        sphere_mask_gpu = (dx_chunk.^2 + dy_gpu.^2 + dz_gpu.^2) <= radius_sq;

        % Mark as occupied in GPU chunk
        local_gpu = occupancy_chunk(x_range_chunk, y_range, z_range);
        local_gpu(sphere_mask_gpu) = true;
        occupancy_chunk(x_range_chunk, y_range, z_range) = local_gpu;
    end
end

function tomogram = insert_particle(tomogram, rotated, pos, template_size)
%INSERT_PARTICLE Insert rotated particle into tomogram at specified position

    half = floor(template_size / 2);

    x1 = pos(1) - half(1);
    x2 = x1 + template_size(1) - 1;

    y1 = pos(2) - half(2);
    y2 = y1 + template_size(2) - 1;

    z1 = pos(3) - half(3);
    z2 = z1 + template_size(3) - 1;

    % Add rotated particle to tomogram (allows density to accumulate)
    tomogram(x1:x2, y1:y2, z1:z2) = tomogram(x1:x2, y1:y2, z1:z2) + rotated;
end

function write_csv(csv_path, particles, sampling_rate)
%WRITE_CSV Write particle parameters in emClarity 31-field format
%   Matches format from BH_templateSearch3d_2.m lines 992-995

    fid = fopen(csv_path, 'w');

    n_particles = size(particles.pos, 1);

    for i = 1:n_particles
        r = reshape(particles.rotmat(:,:,i), 1, 9);

        % Format: score, samplingRate, filler, id, 6 flags, posXYZ (Ang),
        %         phi/theta/psi (deg), rotation matrix (9), final flag
        fprintf(fid, ['%1.2f %d %d %d %d %d %d %d %d %d ' ...
                      '%f %f %f %d %d %d ' ...
                      '%f %f %f %f %f %f %f %f %f %d '], ...
                1.0, ...                              % score
                sampling_rate, ...                    % sampling rate
                0, ...                                % filler
                i, ...                                % particle ID
                1, 1, 1, 1, 1, 0, ...                % 6 flags
                particles.pos_ang(i, 1), ...         % posX (Angstroms)
                particles.pos_ang(i, 2), ...         % posY (Angstroms)
                particles.pos_ang(i, 3), ...         % posZ (Angstroms)
                particles.angles(i, 1), ...          % phi (degrees)
                particles.angles(i, 2), ...          % theta (degrees)
                particles.angles(i, 3), ...          % psi-phi (degrees)
                r, ...                                % 9 rotation matrix elements
                1);                                   % final flag

        fprintf(fid, '\n');
    end

    fclose(fid);

    fprintf('Wrote %d particles to CSV\n', n_particles);
end

function is_valid = check_collision_binary(pos, binary_mask, occupancy_chunk, ...
                                           bin_factor, x_offset_occ, occupancy_size)
%CHECK_COLLISION_BINARY Check if rotated binary mask overlaps with occupancy
%   pos - particle position in full resolution coords
%   binary_mask - rotated binned binary template
%   occupancy_chunk - GPU chunk of occupancy map
%   bin_factor - binning factor
%   x_offset_occ - X offset of chunk in binned coords
%   occupancy_size - full occupancy size

    mask_size = size(binary_mask);
    half_mask = floor(mask_size / 2);

    % Convert position to binned coordinates
    pos_binned = round(pos / bin_factor);

    % Calculate bounding box in binned occupancy coords
    x1 = pos_binned(1) - half_mask(1);
    x2 = x1 + mask_size(1) - 1;
    y1 = pos_binned(2) - half_mask(2);
    y2 = y1 + mask_size(2) - 1;
    z1 = pos_binned(3) - half_mask(3);
    z2 = z1 + mask_size(3) - 1;

    % Clamp to occupancy bounds
    x1_clamped = max(1, x1);
    x2_clamped = min(occupancy_size(1), x2);
    y1_clamped = max(1, y1);
    y2_clamped = min(occupancy_size(2), y2);
    z1_clamped = max(1, z1);
    z2_clamped = min(occupancy_size(3), z2);

    % Convert to chunk-local X coordinates
    x1_local = x1_clamped - x_offset_occ + 1;
    x2_local = x2_clamped - x_offset_occ + 1;

    % Check if region overlaps with chunk
    if x2_local < 1 || x1_local > size(occupancy_chunk, 1)
        is_valid = true;  % Outside chunk, can't check here
        return;
    end

    % Clamp to chunk bounds
    x1_local = max(1, x1_local);
    x2_local = min(size(occupancy_chunk, 1), x2_local);

    % Extract corresponding region from binary mask
    mask_x1 = x1_clamped - x1 + 1;
    mask_x2 = x2_clamped - x1 + 1;
    mask_y1 = y1_clamped - y1 + 1;
    mask_y2 = y2_clamped - y1 + 1;
    mask_z1 = z1_clamped - z1 + 1;
    mask_z2 = z2_clamped - z1 + 1;

    % Get the overlapping regions
    mask_region = binary_mask(mask_x1:mask_x2, mask_y1:mask_y2, mask_z1:mask_z2);
    occ_region = occupancy_chunk(x1_local:x2_local, y1_clamped:y2_clamped, z1_clamped:z2_clamped);

    % Check for any overlap
    is_valid = ~gather(any(mask_region(:) & occ_region(:)));
end

function [occupancy_chunk, occupancy_cpu] = update_occupancy_binary(pos, binary_mask, ...
    occupancy_chunk, occupancy_cpu, bin_factor, x_offset_occ, occupancy_size)
%UPDATE_OCCUPANCY_BINARY Insert rotated binary mask into occupancy maps
%   Updates both GPU chunk and CPU full array

    mask_size = size(binary_mask);
    half_mask = floor(mask_size / 2);

    % Convert position to binned coordinates
    pos_binned = round(pos / bin_factor);

    % Calculate bounding box in binned occupancy coords
    x1 = pos_binned(1) - half_mask(1);
    x2 = x1 + mask_size(1) - 1;
    y1 = pos_binned(2) - half_mask(2);
    y2 = y1 + mask_size(2) - 1;
    z1 = pos_binned(3) - half_mask(3);
    z2 = z1 + mask_size(3) - 1;

    % Clamp to occupancy bounds
    x1_clamped = max(1, x1);
    x2_clamped = min(occupancy_size(1), x2);
    y1_clamped = max(1, y1);
    y2_clamped = min(occupancy_size(2), y2);
    z1_clamped = max(1, z1);
    z2_clamped = min(occupancy_size(3), z2);

    % Extract corresponding region from binary mask
    mask_x1 = x1_clamped - x1 + 1;
    mask_x2 = x2_clamped - x1 + 1;
    mask_y1 = y1_clamped - y1 + 1;
    mask_y2 = y2_clamped - y1 + 1;
    mask_z1 = z1_clamped - z1 + 1;
    mask_z2 = z2_clamped - z1 + 1;

    mask_region = binary_mask(mask_x1:mask_x2, mask_y1:mask_y2, mask_z1:mask_z2);

    % Update CPU full array
    cpu_region = occupancy_cpu(x1_clamped:x2_clamped, y1_clamped:y2_clamped, z1_clamped:z2_clamped);
    cpu_region = cpu_region | mask_region;
    occupancy_cpu(x1_clamped:x2_clamped, y1_clamped:y2_clamped, z1_clamped:z2_clamped) = cpu_region;

    % Update GPU chunk (only if region overlaps with chunk)
    x1_local = x1_clamped - x_offset_occ + 1;
    x2_local = x2_clamped - x_offset_occ + 1;

    if x2_local >= 1 && x1_local <= size(occupancy_chunk, 1)
        x1_local = max(1, x1_local);
        x2_local = min(size(occupancy_chunk, 1), x2_local);

        % Adjust mask region for chunk
        chunk_mask_x1 = x1_local - (x1_clamped - x_offset_occ + 1) + mask_x1;
        chunk_mask_x2 = chunk_mask_x1 + (x2_local - x1_local);

        chunk_mask = binary_mask(chunk_mask_x1:chunk_mask_x2, mask_y1:mask_y2, mask_z1:mask_z2);
        gpu_region = occupancy_chunk(x1_local:x2_local, y1_clamped:y2_clamped, z1_clamped:z2_clamped);
        gpu_region = gpu_region | gpuArray(chunk_mask);
        occupancy_chunk(x1_local:x2_local, y1_clamped:y2_clamped, z1_clamped:z2_clamped) = gpu_region;
    end
end

function binned = bin_volume(vol, bin_factor)
%BIN_VOLUME Bin a 3D volume by averaging
    sz = size(vol);
    new_sz = ceil(sz / bin_factor);

    % Pad to make divisible
    pad_sz = new_sz * bin_factor - sz;
    if any(pad_sz > 0)
        vol = padarray(vol, pad_sz, 0, 'post');
    end

    % Reshape and average
    vol = reshape(vol, bin_factor, new_sz(1), bin_factor, new_sz(2), bin_factor, new_sz(3));
    binned = squeeze(mean(mean(mean(vol, 1), 3), 5));
end
