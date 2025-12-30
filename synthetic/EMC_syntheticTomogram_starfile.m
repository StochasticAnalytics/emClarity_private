function [star_path, tomo_path, csv_path] = EMC_syntheticTomogram_starfile(template_pdb_pairs, tomo_size, ...
                                                        exclusion_factor, output_path, output_prefix, varargin)
%EMC_syntheticTomogram_starfile Generate synthetic particle positions with cisTEM-compatible starfile
%
%   [star_path, tomo_path, csv_path] = EMC_syntheticTomogram_starfile(template_pdb_pairs, tomo_size, ...
%                                                  exclusion_factor, output_path, output_prefix)
%
%   Generates particle positions for a synthetic tomogram and outputs a cisTEM-compatible
%   starfile. The first template-PDB pair gets one particle placed at a fixed position,
%   while additional pairs are placed round-robin. Optionally generates the actual tomogram.
%
%   Input:
%       template_pdb_pairs - Cell array of {mrc_path, pdb_path} pairs
%                           First pair: special (one copy at fixed position)
%                           Additional pairs: placed round-robin
%       tomo_size          - [nX, nY, nZ] tomogram dimensions (must be even)
%       exclusion_factor   - Multiplier for particle radius (>= 1.0, controls density)
%       output_path        - Directory for output files (must exist)
%       output_prefix      - Output file prefix (must not already exist)
%
%   Optional parameters (name-value pairs):
%       'max_particles'   - Maximum number of particles to place (default: inf)
%       'max_attempts'    - Maximum placement attempts (default: 100000)
%       'gpu_id'          - GPU device ID (default: 1)
%       'build_tomogram'  - Also generate tomogram MRC file (default: false)
%       'save_projection' - Save 2D projection (sum over Z) as MRC (default: false)
%
%   Output:
%       star_path - Path to output cisTEM-compatible starfile
%       tomo_path - Path to output tomogram MRC file (empty if build_tomogram=false)
%       csv_path  - Path to output CSV file with particle parameters
%
%   The starfile includes _cisTEMReference3DFilename column with PDB paths.
%   Z position is encoded via defocus values.
%
%   Example:
%       pairs = {{'template1.mrc', 'model1.pdb'}, {'template2.mrc', 'model2.pdb'}};
%       [star, tomo, csv] = EMC_syntheticTomogram_starfile(pairs, [512,512,256], 1.5, ...
%                                            '/output/', 'synthetic_001');
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% Parse inputs
p = inputParser;
addRequired(p, 'template_pdb_pairs', @iscell);
addRequired(p, 'tomo_size', @(x) isnumeric(x) && numel(x) == 3);
addRequired(p, 'exclusion_factor', @(x) isnumeric(x) && x >= 1.0);
addRequired(p, 'output_path', @ischar);
addRequired(p, 'output_prefix', @ischar);
addParameter(p, 'max_particles', inf, @isnumeric);
addParameter(p, 'max_attempts', 100000, @isnumeric);
addParameter(p, 'gpu_id', 1, @isnumeric);
addParameter(p, 'build_tomogram', false, @islogical);
addParameter(p, 'save_projection', false, @islogical);

parse(p, template_pdb_pairs, tomo_size, exclusion_factor, output_path, output_prefix, varargin{:});

max_particles = p.Results.max_particles;
max_attempts = p.Results.max_attempts;
gpu_id = p.Results.gpu_id;
build_tomogram = p.Results.build_tomogram;
save_projection = p.Results.save_projection;

%% Validate inputs
% Check tomo_size is even
tomo_size = tomo_size(:)';  % Ensure row vector
if any(mod(tomo_size, 2) ~= 0)
    error('EMC:syntheticTomogram_starfile', 'tomo_size must have even dimensions in all axes');
end

% Validate template_pdb_pairs structure
n_templates = numel(template_pdb_pairs);
if n_templates < 1
    error('EMC:syntheticTomogram_starfile', 'At least one template-PDB pair is required');
end

for i = 1:n_templates
    if ~iscell(template_pdb_pairs{i}) || numel(template_pdb_pairs{i}) ~= 2
        error('EMC:syntheticTomogram_starfile', 'Each template_pdb_pair must be a cell array {mrc_path, pdb_path}');
    end
    mrc_path = template_pdb_pairs{i}{1};
    pdb_path = template_pdb_pairs{i}{2};
    if ~isfile(mrc_path)
        error('EMC:syntheticTomogram_starfile', 'Template file does not exist: %s', mrc_path);
    end
    if ~isfile(pdb_path)
        error('EMC:syntheticTomogram_starfile', 'PDB file does not exist: %s', pdb_path);
    end
end

% Check output directory exists
if ~isfolder(output_path)
    error('EMC:syntheticTomogram_starfile', 'Output directory does not exist: %s', output_path);
end

% Check output files do not already exist
star_path = fullfile(output_path, sprintf('%s.star', output_prefix));
tomo_path = fullfile(output_path, sprintf('%s.mrc', output_prefix));
csv_path = fullfile(output_path, sprintf('%s.csv', output_prefix));

if isfile(star_path)
    error('EMC:syntheticTomogram_starfile', 'Output file already exists: %s', star_path);
end
if build_tomogram && isfile(tomo_path)
    error('EMC:syntheticTomogram_starfile', 'Output file already exists: %s', tomo_path);
end
if isfile(csv_path)
    error('EMC:syntheticTomogram_starfile', 'Output file already exists: %s', csv_path);
end

%% Initialize GPU
gpuDevice(gpu_id);
fprintf('Using GPU device %d\n', gpu_id);

% Determine if we need to build the tomogram (for saving or projection)
need_tomogram = build_tomogram || save_projection;

%% Load all templates and detect radii
fprintf('Loading %d template-PDB pairs\n', n_templates);

templates = cell(1, n_templates);
pdb_paths = cell(1, n_templates);
template_sizes = zeros(n_templates, 3);
particle_radii = zeros(1, n_templates);
exclusion_radii = zeros(1, n_templates);
pixel_sizes = zeros(1, n_templates);
template_interps = cell(1, n_templates);

for i = 1:n_templates
    mrc_path = template_pdb_pairs{i}{1};
    pdb_paths{i} = template_pdb_pairs{i}{2};

    fprintf('  Loading template %d: %s\n', i, mrc_path);

    % Get pixel size from header
    mrc_image = MRCImage(mrc_path, 0);
    header = getHeader(mrc_image);
    pixel_sizes(i) = header.cellDimensionX / header.nX;

    % Load template volume
    templates{i} = OPEN_IMG('single', mrc_path);
    template_sizes(i, :) = size(templates{i});

    % Pad to even if needed
    pad_needed = mod(template_sizes(i, :), 2);
    if any(pad_needed)
        fprintf('    Padding template to even dimensions\n');
        templates{i} = BH_padZeros3d(templates{i}, [0,0,0], pad_needed, 'cpu', 'single');
        template_sizes(i, :) = size(templates{i});
    end

    % Detect particle radius from shape-based mask
    template_normalized = templates{i} - min(templates{i}(:));
    template_normalized = template_normalized / max(template_normalized(:));
    binary_mask = template_normalized > 0.1;

    center = ceil((template_sizes(i, :) + 1) / 2);
    [X, Y, Z] = ndgrid(1:template_sizes(i,1), 1:template_sizes(i,2), 1:template_sizes(i,3));
    dist_from_center = sqrt((X - center(1)).^2 + (Y - center(2)).^2 + (Z - center(3)).^2);
    particle_radii(i) = max(dist_from_center(binary_mask));
    exclusion_radii(i) = exclusion_factor * particle_radii(i);

    fprintf('    Size: [%d, %d, %d], Pixel size: %.3f Ang, Radius: %.1f px, Exclusion: %.1f px\n', ...
            template_sizes(i,1), template_sizes(i,2), template_sizes(i,3), ...
            pixel_sizes(i), particle_radii(i), exclusion_radii(i));

    % Initialize interpolator on GPU (needed for tomogram generation)
    if need_tomogram
        [template_interps{i}, ~] = interpolator(gpuArray(single(templates{i})), ...
                                         [0,0,0], [0,0,0], 'Bah', 'forward', 'C1', false);
    end
end

% Use first template's pixel size as reference
pixel_size = pixel_sizes(1);
fprintf('Using pixel size from first template: %.3f Angstroms\n', pixel_size);

%% Initialize output volumes
if need_tomogram
    fprintf('Initializing tomogram [%d, %d, %d] on CPU\n', tomo_size(1), tomo_size(2), tomo_size(3));
    tomogram = zeros(tomo_size, 'single');
else
    tomogram = [];
end
if ~build_tomogram
    tomo_path = '';
end

% Bin the occupancy map to reduce GPU memory
occupancy_bin = 3;
occupancy_size = ceil(tomo_size / occupancy_bin);

% X-chunking: keep full occupancy on CPU, load chunks to GPU
n_x_chunks = 4;
chunk_size_x = ceil(tomo_size(1) / n_x_chunks);
max_exclusion_radius = max(exclusion_radii);  % Use largest exclusion radius for overlap calculation
fprintf('Initializing occupancy map on CPU [%d, %d, %d] (binned %dx, %d X-chunks)\n', ...
        occupancy_size(1), occupancy_size(2), occupancy_size(3), occupancy_bin, n_x_chunks);
occupancy_cpu = false(occupancy_size);

%% Calculate valid placement bounds (using largest template)
max_template_size = max(template_sizes, [], 1);
half_template = ceil(max_template_size / 2);
min_bound = half_template + 1;
max_bound = tomo_size - half_template;

fprintf('Valid placement bounds: [%d-%d, %d-%d, %d-%d]\n', ...
        min_bound(1), max_bound(1), min_bound(2), max_bound(2), min_bound(3), max_bound(3));

% Check if placement is possible
if any(min_bound > max_bound)
    error('EMC:syntheticTomogram_starfile', 'Template is too large for the specified tomogram size');
end

%% Initialize particle storage
particles = struct();
particles.pos = [];
particles.pos_ang = [];
particles.angles = [];
particles.shifts = [];
particles.rotmat = [];
particles.template_idx = [];
particles.pdb_path = {};

%% Place first particle (SPECIAL)
fprintf('Placing first particle at fixed position (+10, +30 Angstroms)...\n');

% Convert fixed position from Angstroms to voxels
origin = ceil((tomo_size + 1) / 2);
fixed_pos_ang = [10, 30, 0];  % X=+10 Ang, Y=+30 Ang, Z=0
pos = round(fixed_pos_ang / pixel_size + origin);

% Ensure position is within bounds
pos = max(pos, min_bound);
pos = min(pos, max_bound);

% Generate random rotation
[phi, theta, psi_minus_phi, rotmat] = generate_random_rotation();
angles = [phi, theta, psi_minus_phi];

% Generate random subpixel shifts
shifts = 2 * rand(1, 3) - 1;

% Insert into tomogram if enabled
if need_tomogram
    rotated_gpu = template_interps{1}.interp3d(angles, shifts, 'Bah', 'forward', 'C1');
    rotated = gather(rotated_gpu);
    tomogram = insert_particle(tomogram, rotated, pos, template_sizes(1, :));
end

% Update occupancy (CPU array - first particle is placed before X-band processing)
occupancy_cpu = update_occupancy_cpu(pos(1), pos(2), pos(3), occupancy_cpu, exclusion_radii(1), occupancy_bin);

% Store particle data
pos_ang = (pos - origin) * pixel_size;  % Position in Angstroms

particles.pos = pos;
particles.pos_ang = pos_ang;
particles.angles = angles;
particles.shifts = shifts;
particles.rotmat = rotmat;
particles.template_idx = 1;
particles.pdb_path = {pdb_paths{1}};

fprintf('  Placed first particle at [%d, %d, %d] (%.1f, %.1f, %.1f Ang)\n', ...
        pos(1), pos(2), pos(3), pos_ang(1), pos_ang(2), pos_ang(3));

%% Main placement loop (round-robin for templates 2+) - process in X-bands
if n_templates > 1
    fprintf('Starting round-robin placement for templates 2-%d in %d X-bands...\n', n_templates, n_x_chunks);
    particle_count = 1;  % Already placed first particle
    attempts = 0;
    consecutive_failures = 0;
    max_consecutive_failures = 300;
    last_report_time = 0;
    report_interval = 5;

    current_template_idx = 2;  % Start with second template

    % Calculate overlap needed for exclusion radius checks (in binned coords)
    overlap_occ = ceil(max_exclusion_radius / occupancy_bin);

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

        while particle_count < max_particles && attempts < max_attempts
            attempts = attempts + 1;

            % Progress reporting
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

            % Check for collision (using GPU occupancy chunk with offset)
            if ~check_collision_chunked(pos(1), pos(2), pos(3), occupancy_chunk, ...
                                        exclusion_radii(current_template_idx), occupancy_bin, x_min_occ)
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

            % Generate random rotation
            [phi, theta, psi_minus_phi, rotmat] = generate_random_rotation();
            angles = [phi, theta, psi_minus_phi];

            % Generate random subpixel shifts
            shifts = 2 * rand(1, 3) - 1;

            % Insert into tomogram if enabled
            if need_tomogram
                rotated_gpu = template_interps{current_template_idx}.interp3d(angles, shifts, 'Bah', 'forward', 'C1');
                rotated = gather(rotated_gpu);
                tomogram = insert_particle(tomogram, rotated, pos, template_sizes(current_template_idx, :));
            end

            % Update occupancy (both GPU chunk and CPU full array)
            [occupancy_chunk, occupancy_cpu] = update_occupancy_chunked(pos(1), pos(2), pos(3), ...
                occupancy_chunk, occupancy_cpu, exclusion_radii(current_template_idx), occupancy_bin, x_min_occ);

            % Store particle data
            pos_ang = (pos - origin) * pixel_size;

            particles.pos = [particles.pos; pos];
            particles.pos_ang = [particles.pos_ang; pos_ang];
            particles.angles = [particles.angles; angles];
            particles.shifts = [particles.shifts; shifts];
            particles.rotmat = cat(3, particles.rotmat, rotmat);
            particles.template_idx = [particles.template_idx; current_template_idx];
            particles.pdb_path = [particles.pdb_path; pdb_paths{current_template_idx}];

            % Report progress
            if mod(particle_count, 10) == 0
                elapsed = toc;
                rate = particle_count / elapsed;
                fprintf('    Placed particle %d (template %d) at [%d, %d, %d] (%.1f particles/sec)\n', ...
                        particle_count, current_template_idx, pos(1), pos(2), pos(3), rate);
                last_report_time = elapsed;
            end

            % Advance to next template (round-robin among templates 2+)
            current_template_idx = current_template_idx + 1;
            if current_template_idx > n_templates
                current_template_idx = 2;  % Wrap back to second template
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
else
    fprintf('Only one template-PDB pair provided; no round-robin placement.\n');
    particle_count = 1;
end

%% Calculate defocus values from Z positions
fprintf('Calculating defocus values from Z positions...\n');

n_particles = size(particles.pos_ang, 1);
z_offsets = particles.pos_ang(:, 3) - particles.pos_ang(1, 3);  % Relative to first particle

% Nominal defocus (2 microns = 20000 Angstroms)
nominal_defocus = 20000;
defocus_values = nominal_defocus - z_offsets;

% Adjust so first particle's defocus equals the average
offset_adj = mean(defocus_values) - defocus_values(1);
defocus_values = defocus_values + offset_adj;

fprintf('  First particle defocus: %.1f Ang (average: %.1f Ang)\n', ...
        defocus_values(1), mean(defocus_values));
fprintf('  Defocus range: %.1f to %.1f Ang\n', min(defocus_values), max(defocus_values));

%% Save starfile
fprintf('Saving starfile to %s\n', star_path);
write_starfile(star_path, particles, defocus_values, pixel_size);

%% Save tomogram if enabled
if build_tomogram
    fprintf('Saving tomogram to %s\n', tomo_path);
    SAVE_IMG(tomogram, tomo_path, pixel_size);
end

%% Save projection if enabled (sum over Z)
if save_projection
    projection_path = fullfile(output_path, sprintf('%s_projection.mrc', output_prefix));
    fprintf('Saving projection to %s\n', projection_path);
    projection = sum(tomogram, 3);
    SAVE_IMG(projection, projection_path, pixel_size);
end

%% Save CSV (emClarity format)
fprintf('Saving CSV to %s\n', csv_path);
write_csv(csv_path, particles, 1);

%% Save tomosize file
[tomo_dir, tomo_name, ~] = fileparts(star_path);
tomosize_path = fullfile(tomo_dir, sprintf('%s.tomosize', output_prefix));
fprintf('Saving tomosize to %s\n', tomosize_path);
fid = fopen(tomosize_path, 'w');
fprintf(fid, '%d\n', tomo_size(1));
fprintf(fid, '%d\n', tomo_size(2));
fprintf(fid, '%d\n', tomo_size(3));
fprintf(fid, '%.6f\n', pixel_size);
fclose(fid);

%% Cleanup
if need_tomogram
    for i = 1:n_templates
        template_interps{i}.delete();
    end
end

fprintf('Done. Output files:\n');
fprintf('  Starfile: %s\n', star_path);
if build_tomogram
    fprintf('  Tomogram: %s\n', tomo_path);
end
if save_projection
    fprintf('  Projection: %s\n', projection_path);
end
fprintf('  CSV: %s\n', csv_path);
fprintf('  Tomosize: %s\n', tomosize_path);

end

%% Helper functions

function [phi, theta, psi_minus_phi, R] = generate_random_rotation()
%GENERATE_RANDOM_ROTATION Generate uniform random rotation matching BH_defineMatrix

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

function occupancy_cpu = update_occupancy_cpu(cx, cy, cz, occupancy_cpu, radius, bin_factor)
%UPDATE_OCCUPANCY_CPU Mark spherical region as occupied (CPU only)

    % Scale coordinates and radius to binned space
    cx_bin = round(cx / bin_factor);
    cy_bin = round(cy / bin_factor);
    cz_bin = round(cz / bin_factor);
    radius_bin = radius / bin_factor;

    r = ceil(radius_bin);
    radius_sq = radius_bin^2;

    % Get bounding box for exclusion sphere in binned coordinates
    x_range = max(1, cx_bin-r):min(size(occupancy_cpu, 1), cx_bin+r);
    y_range = max(1, cy_bin-r):min(size(occupancy_cpu, 2), cy_bin+r);
    z_range = max(1, cz_bin-r):min(size(occupancy_cpu, 3), cz_bin+r);

    % Create sphere mask (CPU)
    [dx, dy, dz] = ndgrid(single(x_range - cx_bin), ...
                          single(y_range - cy_bin), ...
                          single(z_range - cz_bin));
    sphere_mask = (dx.^2 + dy.^2 + dz.^2) <= radius_sq;

    % Mark as occupied
    local = occupancy_cpu(x_range, y_range, z_range);
    local(sphere_mask) = true;
    occupancy_cpu(x_range, y_range, z_range) = local;
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

function write_starfile(star_path, particles, defocus_values, pixel_size)
%WRITE_STARFILE Write cisTEM-compatible starfile with 29 columns

    fid = fopen(star_path, 'w');

    % Write header
    fprintf(fid, [ ...
      '# Written by emClarity Version 2.0.0-alpha on %s\n\n' ...
      'data_\n\n' ...
      'loop_\n\n' ...
      '_cisTEMPositionInStack #1\n' ...
      '_cisTEMAnglePsi #2\n' ...
      '_cisTEMAngleTheta #3\n' ...
      '_cisTEMAnglePhi #4\n' ...
      '_cisTEMXShift #5\n' ...
      '_cisTEMYShift #6\n' ...
      '_cisTEMDefocus1 #7\n' ...
      '_cisTEMDefocus2 #8\n' ...
      '_cisTEMDefocusAngle #9\n' ...
      '_cisTEMPhaseShift #10\n' ...
      '_cisTEMOccupancy #11\n' ...
      '_cisTEMLogP #12\n' ...
      '_cisTEMSigma #13\n' ...
      '_cisTEMScore #14\n' ...
      '_cisTEMScoreChange #15\n' ...
      '_cisTEMPixelSize #16\n' ...
      '_cisTEMMicroscopeVoltagekV #17\n' ...
      '_cisTEMMicroscopeCsMM #18\n' ...
      '_cisTEMAmplitudeContrast #19\n' ...
      '_cisTEMBeamTiltX #20\n' ...
      '_cisTEMBeamTiltY #21\n' ...
      '_cisTEMImageShiftX #22\n' ...
      '_cisTEMImageShiftY #23\n' ...
      '_cisTEMBest2DClass #24\n' ...
      '_cisTEMBeamTiltGroup #25\n' ...
      '_cisTEMParticleGroup #26\n' ...
      '_cisTEMPreExposure #27\n' ...
      '_cisTEMTotalExposure #28\n' ...
      '_cisTEMReference3DFilename #29\n' ...
      ], datetime);

    n_particles = size(particles.pos_ang, 1);

    % Default optical parameters (voltage=1, Cs=1, AmpC=0)
    micVoltage = 1;
    micCS = 1;
    ampContrast = 0;
    phaseShift = 0;
    occupancy = 100;
    logp = -1000;
    sigma = 10;
    score = 10;
    scoreChange = 0;
    beamTiltX = 0;
    beamTiltY = 0;
    beamTiltShiftX = 0;
    beamTiltShiftY = 0;
    beamTiltGroup = 1;
    particleGroup = 1;
    preExposure = 0;
    totalExposure = 0;

    for i = 1:n_particles
        % Get rotation matrix and convert to ZYZ Euler angles
        R = particles.rotmat(:, :, i);
        eul = rotm2eul(R, 'ZYZ');

        % Convert to degrees and NEGATE for cisTEM convention
        e1 = -180 / pi * eul(1);
        e2 = -180 / pi * eul(2);
        e3 = -180 / pi * eul(3);

        % Position in Angstroms (XShift, YShift)
        xShift = particles.pos_ang(i, 1);
        yShift = particles.pos_ang(i, 2);

        % Defocus (same for df1 and df2, no astigmatism)
        df1 = defocus_values(i);
        df2 = defocus_values(i);
        dfA = 0;  % No astigmatism angle

        % Best 2D class based on template index
        best2dClass = particles.template_idx(i);

        % PDB path in single quotes (required by cisTEM)
        pdb_path_quoted = sprintf('''%s''', particles.pdb_path{i});

        % Write data line
        fprintf(fid, '%8u %7.2f %7.2f %7.2f %9.2f %9.2f %8.1f %8.1f %7.2f %7.2f %5i %7.2f %9i %10.4f %7.2f %8.5f %7.2f %7.2f %7.4f %7.3f %7.3f %7.3f %7.3f %5i %5i %8u %7.2f %7.2f %s\n', ...
            i, e1, e2, e3, xShift, yShift, ...
            df1, df2, dfA, ...
            phaseShift, occupancy, logp, sigma, score, scoreChange, ...
            pixel_size, micVoltage, micCS, ampContrast, ...
            beamTiltX, beamTiltY, beamTiltShiftX, beamTiltShiftY, ...
            best2dClass, beamTiltGroup, particleGroup, preExposure, totalExposure, ...
            pdb_path_quoted);
    end

    fclose(fid);

    fprintf('Wrote %d particles to starfile\n', n_particles);
end

function write_csv(csv_path, particles, sampling_rate)
%WRITE_CSV Write particle parameters in emClarity 31-field format

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
