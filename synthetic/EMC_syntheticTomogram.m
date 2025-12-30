function [outputs] = EMC_syntheticTomogram(template_inputs, tomo_size, ...
                                            exclusion_factor, output_path, output_prefix, varargin)
%EMC_syntheticTomogram Generate synthetic tomogram with randomly placed particles
%
%   outputs = EMC_syntheticTomogram(template_inputs, tomo_size, ...
%                                   exclusion_factor, output_path, output_prefix)
%
%   Generates a synthetic 3D tomogram by placing randomly rotated copies of
%   particle template(s) at random positions using collision detection.
%   Supports multiple templates with round-robin placement.
%
%   Input:
%       template_inputs  - Flexible input format:
%                          - Single MRC path (string) - backward compatible
%                          - Cell array of MRC paths - multiple templates
%                          - Cell array of {mrc_path, pdb_path} pairs
%       tomo_size        - [nX, nY, nZ] tomogram dimensions (must be even)
%       exclusion_factor - Multiplier for particle radius (>= 1.0, controls density)
%       output_path      - Directory for output files (must exist)
%       output_prefix    - Output file prefix (must not already exist)
%
%   Optional parameters (name-value pairs):
%       'max_particles'       - Maximum number of particles (default: inf)
%       'max_attempts'        - Maximum placement attempts (default: 100000)
%       'gpu_id'              - GPU device ID (default: 1)
%       'collision_mode'      - 'shape' (default, accurate) or 'sphere' (faster)
%       'build_tomogram'      - Generate tomogram MRC (default: true)
%       'save_projection'     - Save 2D projection sum (default: false)
%       'output_starfile'     - Generate cisTEM starfile (default: false)
%       'add_water_background'- Fill empty voxels with water density (default: false)
%                               Water = avg_protein_density * (0.94/1.35)
%
%   Output:
%       outputs - Struct with fields:
%           .tomo_path     - Path to tomogram (empty if build_tomogram=false)
%           .csv_path      - Path to emClarity CSV
%           .star_path     - Path to starfile (empty if output_starfile=false)
%           .proj_path     - Path to projection (empty if save_projection=false)
%           .tomosize_path - Path to tomosize file
%
%   The CSV file uses emClarity's 31-field format matching template search output.
%   The starfile uses cisTEM-compatible 29-column format with defocus-encoded Z.
%
%   Example (single template):
%       outputs = EMC_syntheticTomogram('particle.mrc', [512,512,256], 1.5, ...
%                                        '/output/', 'synthetic_001');
%
%   Example (multiple templates with starfile):
%       pairs = {{'template1.mrc', 'model1.pdb'}, {'template2.mrc', 'model2.pdb'}};
%       outputs = EMC_syntheticTomogram(pairs, [512,512,256], 1.5, '/output/', 'test', ...
%                                        'output_starfile', true, 'add_water_background', true);
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% Parse inputs
p = inputParser;
addRequired(p, 'template_inputs');
addRequired(p, 'tomo_size', @(x) isnumeric(x) && numel(x) == 3);
addRequired(p, 'exclusion_factor', @(x) isnumeric(x) && x >= 1.0);
addRequired(p, 'output_path', @ischar);
addRequired(p, 'output_prefix', @ischar);
addParameter(p, 'max_particles', inf, @isnumeric);
addParameter(p, 'max_attempts', 100000, @isnumeric);
addParameter(p, 'gpu_id', 1, @isnumeric);
addParameter(p, 'collision_mode', 'shape', @(x) ismember(x, {'shape', 'sphere'}));
addParameter(p, 'build_tomogram', true, @islogical);
addParameter(p, 'save_projection', false, @islogical);
addParameter(p, 'output_starfile', false, @islogical);
addParameter(p, 'add_water_background', false, @islogical);

parse(p, template_inputs, tomo_size, exclusion_factor, output_path, output_prefix, varargin{:});

max_particles = p.Results.max_particles;
max_attempts = p.Results.max_attempts;
gpu_id = p.Results.gpu_id;
collision_mode = p.Results.collision_mode;
build_tomogram = p.Results.build_tomogram;
save_projection = p.Results.save_projection;
output_starfile = p.Results.output_starfile;
add_water_background = p.Results.add_water_background;

%% Validate tomo_size
tomo_size = tomo_size(:)';  % Ensure row vector
if any(mod(tomo_size, 2) ~= 0)
    error('EMC:syntheticTomogram', 'tomo_size must have even dimensions in all axes');
end

%% Check output directory exists
if ~isfolder(output_path)
    error('EMC:syntheticTomogram', 'Output directory does not exist: %s', output_path);
end

%% Setup output paths
outputs = struct();
outputs.tomo_path = fullfile(output_path, sprintf('%s.mrc', output_prefix));
outputs.csv_path = fullfile(output_path, sprintf('%s.csv', output_prefix));
outputs.star_path = fullfile(output_path, sprintf('%s.star', output_prefix));
outputs.proj_path = fullfile(output_path, sprintf('%s_projection.mrc', output_prefix));
outputs.tomosize_path = fullfile(output_path, sprintf('%s.tomosize', output_prefix));

% Check output files do not already exist
if build_tomogram && isfile(outputs.tomo_path)
    error('EMC:syntheticTomogram', 'Output file already exists: %s', outputs.tomo_path);
end
if isfile(outputs.csv_path)
    error('EMC:syntheticTomogram', 'Output file already exists: %s', outputs.csv_path);
end
if output_starfile && isfile(outputs.star_path)
    error('EMC:syntheticTomogram', 'Output file already exists: %s', outputs.star_path);
end

%% Initialize GPU
gpuDevice(gpu_id);
fprintf('Using GPU device %d\n', gpu_id);

%% Normalize template inputs and load templates
templates = normalize_template_inputs(template_inputs, exclusion_factor, collision_mode);
n_templates = numel(templates);

fprintf('Loaded %d template(s)\n', n_templates);
for i = 1:n_templates
    fprintf('  Template %d: %s\n', i, templates(i).mrc_path);
    fprintf('    Size: [%d, %d, %d], Pixel size: %.3f Ang\n', ...
            templates(i).size(1), templates(i).size(2), templates(i).size(3), templates(i).pixel_size);
    fprintf('    Particle radius: %.1f px, Exclusion radius: %.1f px\n', ...
            templates(i).particle_radius, templates(i).exclusion_radius);
end

% Use first template's pixel size as reference
pixel_size = templates(1).pixel_size;
fprintf('Reference pixel size: %.3f Angstroms\n', pixel_size);

%% Determine if we need to build the tomogram volume
need_tomogram = build_tomogram || save_projection || add_water_background;

%% Calculate water density if needed
if add_water_background
    % Average protein density across all templates (weighted equally)
    avg_protein_density = mean([templates.avg_protein_density]);
    % Water/protein density ratio: 0.94 g/cm^3 / 1.35 g/cm^3
    water_protein_ratio = 0.94 / 1.35;
    water_density = avg_protein_density * water_protein_ratio;
    fprintf('Water background: avg protein density = %.4f, water density = %.4f (ratio: %.4f)\n', ...
            avg_protein_density, water_density, water_protein_ratio);
else
    water_density = 0;
end

%% Initialize GPU interpolators for templates
if need_tomogram
    for i = 1:n_templates
        [templates(i).interp, ~] = interpolator(gpuArray(single(templates(i).volume)), ...
                                                 [0,0,0], [0,0,0], 'Bah', 'forward', 'C1', false);
        % Shape mask interpolator for masking rotated particles
        [templates(i).shape_mask_interp, ~] = interpolator(gpuArray(single(templates(i).shape_mask)), ...
                                                            [0,0,0], [0,0,0], 'Bah', 'forward', 'C1', false);
    end
end

%% Initialize binary mask interpolators for shape-based collision
if strcmp(collision_mode, 'shape')
    for i = 1:n_templates
        [templates(i).binary_interp, ~] = interpolator(gpuArray(single(templates(i).binary_mask_binned)), ...
                                                        [0,0,0], [0,0,0], 'Bah', 'forward', 'C1', false);
    end
end

%% Initialize output volumes
if need_tomogram
    if add_water_background
        fprintf('Initializing tomogram [%d, %d, %d] with water density %.4f\n', ...
                tomo_size(1), tomo_size(2), tomo_size(3), water_density);
        tomogram = ones(tomo_size, 'single') * water_density;
    else
        fprintf('Initializing tomogram [%d, %d, %d] on CPU\n', tomo_size(1), tomo_size(2), tomo_size(3));
        tomogram = zeros(tomo_size, 'single');
    end
else
    fprintf('Skipping tomogram generation (build_tomogram=false)\n');
    tomogram = [];
    outputs.tomo_path = '';
end

if ~save_projection
    outputs.proj_path = '';
end
if ~output_starfile
    outputs.star_path = '';
end

%% Initialize occupancy map
occupancy_bin = 3;
occupancy_size = ceil(tomo_size / occupancy_bin);
n_x_chunks = 4;
chunk_size_x = ceil(tomo_size(1) / n_x_chunks);
max_exclusion_radius = max([templates.exclusion_radius]);

fprintf('Initializing occupancy map on CPU [%d, %d, %d] (binned %dx, %d X-chunks)\n', ...
        occupancy_size(1), occupancy_size(2), occupancy_size(3), occupancy_bin, n_x_chunks);
occupancy_cpu = false(occupancy_size);

%% Calculate valid placement bounds (using largest template)
max_template_size = max(cat(1, templates.size), [], 1);
half_template = ceil(max_template_size / 2);
min_bound = half_template + 1;
max_bound = tomo_size - half_template;

fprintf('Valid placement bounds: [%d-%d, %d-%d, %d-%d]\n', ...
        min_bound(1), max_bound(1), min_bound(2), max_bound(2), min_bound(3), max_bound(3));

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
particles.template_idx = [];
particles.pdb_path = {};

%% Main placement loop - process in X-bands
fprintf('Starting particle placement in %d X-bands (collision_mode: %s)...\n', n_x_chunks, collision_mode);

particle_count = 0;
attempts = 0;
consecutive_failures = 0;
max_consecutive_failures = 300;
last_report_time = 0;
report_interval = 5;

current_template_idx = 1;  % Round-robin starting point
origin = ceil((tomo_size + 1) / 2);

% Calculate overlap needed for collision checks (in binned coords)
if strcmp(collision_mode, 'shape')
    max_binned_mask_size = 0;
    for i = 1:n_templates
        max_binned_mask_size = max(max_binned_mask_size, max(size(templates(i).binary_mask_binned)));
    end
    overlap_occ = ceil(max_binned_mask_size / 2);
else
    overlap_occ = ceil(max_exclusion_radius / occupancy_bin);
end

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

        % Generate random rotation
        [phi, theta, psi_minus_phi, rotmat] = generate_random_rotation();
        angles = [phi, theta, psi_minus_phi];

        % Generate random subpixel shifts
        shifts = 2 * rand(1, 3) - 1;

        % Collision check (mode-dependent)
        if strcmp(collision_mode, 'shape')
            % Rotate binned binary template and check overlap
            shifts_binned = shifts / occupancy_bin;
            rotated_binary_gpu = templates(current_template_idx).binary_interp.interp3d(angles, shifts_binned, 'Bah', 'forward', 'C1');
            rotated_binary = gather(rotated_binary_gpu) > 0.5;

            is_valid = check_collision_binary(pos, rotated_binary, occupancy_chunk, ...
                                               occupancy_bin, x_min_occ, occupancy_size);
        else
            % Sphere-based collision check
            is_valid = check_collision_sphere(pos(1), pos(2), pos(3), occupancy_chunk, ...
                                               templates(current_template_idx).exclusion_radius, ...
                                               occupancy_bin, x_min_occ);
        end

        if ~is_valid
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

        % Insert particle into tomogram if needed
        if need_tomogram
            % Rotate particle volume
            rotated_gpu = templates(current_template_idx).interp.interp3d(angles, shifts, 'Bah', 'forward', 'C1');

            % Rotate shape mask and threshold to get clean binary mask
            rotated_mask_gpu = templates(current_template_idx).shape_mask_interp.interp3d(angles, shifts, 'Bah', 'forward', 'C1');
            rotated_mask = gather(rotated_mask_gpu) > 0.5;

            % Apply mask: zero outside protein, subtract water inside protein
            rotated = gather(rotated_gpu);
            rotated(~rotated_mask) = 0;  % Zero outside protein boundary
            rotated(rotated_mask) = rotated(rotated_mask) - water_density;  % Subtract water inside

            tomogram = insert_particle(tomogram, rotated, pos, templates(current_template_idx).size);
        end

        % Update occupancy (both GPU chunk and CPU full array)
        if strcmp(collision_mode, 'shape')
            [occupancy_chunk, occupancy_cpu] = update_occupancy_binary(pos, rotated_binary, ...
                occupancy_chunk, occupancy_cpu, occupancy_bin, x_min_occ, occupancy_size);
        else
            [occupancy_chunk, occupancy_cpu] = update_occupancy_sphere(pos(1), pos(2), pos(3), ...
                occupancy_chunk, occupancy_cpu, templates(current_template_idx).exclusion_radius, ...
                occupancy_bin, x_min_occ);
        end

        % Store particle data
        pos_ang = (pos - origin) * pixel_size;  % Position in Angstroms

        particles.pos = [particles.pos; pos];
        particles.pos_ang = [particles.pos_ang; pos_ang];
        particles.angles = [particles.angles; angles];
        particles.shifts = [particles.shifts; shifts];
        particles.rotmat = cat(3, particles.rotmat, rotmat);
        particles.template_idx = [particles.template_idx; current_template_idx];
        particles.pdb_path = [particles.pdb_path; {templates(current_template_idx).pdb_path}];

        % Report progress
        if particle_count == 1 || mod(particle_count, 10) == 0
            elapsed = toc;
            rate = particle_count / elapsed;
            if n_templates > 1
                fprintf('    Placed particle %d (template %d) at [%d, %d, %d] (%.1f particles/sec)\n', ...
                        particle_count, current_template_idx, pos(1), pos(2), pos(3), rate);
            else
                fprintf('    Placed particle %d at [%d, %d, %d] (%.1f particles/sec)\n', ...
                        particle_count, pos(1), pos(2), pos(3), rate);
            end
            last_report_time = elapsed;
        end

        % Advance to next template (round-robin)
        current_template_idx = mod(current_template_idx, n_templates) + 1;
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
% Always save CSV
fprintf('Saving CSV to %s\n', outputs.csv_path);
write_csv(outputs.csv_path, particles, 1);

% Always save tomosize
fprintf('Saving tomosize to %s\n', outputs.tomosize_path);
write_tomosize(outputs.tomosize_path, tomo_size, pixel_size);

% Optional: tomogram
if build_tomogram
    fprintf('Saving tomogram to %s\n', outputs.tomo_path);
    SAVE_IMG(tomogram, outputs.tomo_path, pixel_size);
end

% Optional: projection
if save_projection
    fprintf('Saving projection to %s\n', outputs.proj_path);
    projection = sum(tomogram, 3);
    SAVE_IMG(projection, outputs.proj_path, pixel_size);
end

% Optional: starfile
if output_starfile
    fprintf('Saving starfile to %s\n', outputs.star_path);
    defocus_values = calculate_defocus_from_z(particles, pixel_size);
    write_starfile(outputs.star_path, particles, defocus_values, pixel_size);
end

%% Cleanup GPU interpolators
if need_tomogram
    for i = 1:n_templates
        templates(i).interp.delete();
        templates(i).shape_mask_interp.delete();
    end
end
if strcmp(collision_mode, 'shape')
    for i = 1:n_templates
        templates(i).binary_interp.delete();
    end
end

%% Print summary
fprintf('Done. Output files:\n');
if build_tomogram
    fprintf('  Tomogram: %s\n', outputs.tomo_path);
end
fprintf('  CSV: %s\n', outputs.csv_path);
if output_starfile
    fprintf('  Starfile: %s\n', outputs.star_path);
end
if save_projection
    fprintf('  Projection: %s\n', outputs.proj_path);
end
fprintf('  Tomosize: %s\n', outputs.tomosize_path);

end

%% ========================================================================
%% Helper Functions
%% ========================================================================

function templates = normalize_template_inputs(template_inputs, exclusion_factor, collision_mode)
%NORMALIZE_TEMPLATE_INPUTS Convert various input formats to struct array
%
%   Handles:
%     - Single MRC path (string)
%     - Cell array of MRC paths
%     - Cell array of {mrc_path, pdb_path} pairs

    if ischar(template_inputs)
        % Single MRC path
        mrc_paths = {template_inputs};
        pdb_paths = {''};
    elseif iscell(template_inputs)
        if isempty(template_inputs)
            error('EMC:syntheticTomogram', 'template_inputs cannot be empty');
        end

        % Check if it's cell of pairs or cell of strings
        if iscell(template_inputs{1}) && numel(template_inputs{1}) == 2
            % Cell array of {mrc, pdb} pairs
            n = numel(template_inputs);
            mrc_paths = cell(1, n);
            pdb_paths = cell(1, n);
            for i = 1:n
                mrc_paths{i} = template_inputs{i}{1};
                pdb_paths{i} = template_inputs{i}{2};
            end
        else
            % Cell array of MRC paths (assume strings)
            mrc_paths = template_inputs(:)';
            pdb_paths = repmat({''}, 1, numel(mrc_paths));
        end
    else
        error('EMC:syntheticTomogram', 'template_inputs must be a string or cell array');
    end

    n_templates = numel(mrc_paths);
    templates = struct('mrc_path', cell(1, n_templates), ...
                       'pdb_path', cell(1, n_templates), ...
                       'volume', cell(1, n_templates), ...
                       'size', cell(1, n_templates), ...
                       'pixel_size', cell(1, n_templates), ...
                       'particle_radius', cell(1, n_templates), ...
                       'exclusion_radius', cell(1, n_templates), ...
                       'avg_protein_density', cell(1, n_templates), ... % For water calculation
                       'shape_mask', cell(1, n_templates), ...          % Undilated mask for volume masking
                       'binary_mask', cell(1, n_templates), ...         % Dilated mask for collision (full-res)
                       'binary_mask_binned', cell(1, n_templates), ...  % Dilated mask for collision (binned)
                       'interp', cell(1, n_templates), ...
                       'shape_mask_interp', cell(1, n_templates), ...   % For rotating shape mask
                       'binary_interp', cell(1, n_templates));

    occupancy_bin = 3;

    for i = 1:n_templates
        templates(i).mrc_path = mrc_paths{i};
        templates(i).pdb_path = pdb_paths{i};

        % Validate files exist
        if ~isfile(mrc_paths{i})
            error('EMC:syntheticTomogram', 'Template file does not exist: %s', mrc_paths{i});
        end
        if ~isempty(pdb_paths{i}) && ~isfile(pdb_paths{i})
            error('EMC:syntheticTomogram', 'PDB file does not exist: %s', pdb_paths{i});
        end

        % Get pixel size from header
        mrc_image = MRCImage(mrc_paths{i}, 0);
        header = getHeader(mrc_image);
        templates(i).pixel_size = header.cellDimensionX / header.nX;

        % Load template volume
        templates(i).volume = OPEN_IMG('single', mrc_paths{i});
        templates(i).size = size(templates(i).volume);

        % Pad to even if needed
        pad_needed = mod(templates(i).size, 2);
        if any(pad_needed)
            templates(i).volume = BH_padZeros3d(templates(i).volume, [0,0,0], pad_needed, 'cpu', 'single');
            templates(i).size = size(templates(i).volume);
        end

        % Create shape mask using EMC_maskReference (always needed for volume masking)
        templates(i).shape_mask = EMC_maskReference(templates(i).volume, templates(i).pixel_size, ...
                                                      {'lowpass', 14; 'threshold', 2.4});
        templates(i).shape_mask = templates(i).shape_mask > 0.5;

        % Detect particle radius from shape mask
        center = ceil((templates(i).size + 1) / 2);
        [X, Y, Z] = ndgrid(1:templates(i).size(1), 1:templates(i).size(2), 1:templates(i).size(3));
        dist_from_center = sqrt((X - center(1)).^2 + (Y - center(2)).^2 + (Z - center(3)).^2);
        templates(i).particle_radius = max(dist_from_center(templates(i).shape_mask));
        templates(i).exclusion_radius = exclusion_factor * templates(i).particle_radius;

        % Calculate average protein density (for water background calculation)
        templates(i).avg_protein_density = mean(templates(i).volume(templates(i).shape_mask));

        % Create binary mask for collision detection
        if strcmp(collision_mode, 'shape')
            % Dilate shape mask by exclusion_factor for collision detection
            if exclusion_factor > 1.0
                se_radius = round((exclusion_factor - 1.0) * max(templates(i).size) / 2);
                if se_radius > 0
                    se = strel('sphere', se_radius);
                    templates(i).binary_mask = imdilate(templates(i).shape_mask, se);
                else
                    templates(i).binary_mask = templates(i).shape_mask;
                end
            else
                templates(i).binary_mask = templates(i).shape_mask;
            end

            % Bin the binary mask for occupancy checking
            templates(i).binary_mask_binned = bin_volume(templates(i).binary_mask, occupancy_bin) > 0;
        else
            % Sphere mode: no binary mask needed for collision
            templates(i).binary_mask = [];
            templates(i).binary_mask_binned = [];
        end
    end
end

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

    % Get rotation matrix (using 'inv' direction as in template search)
    R = BH_defineMatrix([phi, theta, psi_minus_phi], 'Bah', 'inv');
end

function is_valid = check_collision_binary(pos, binary_mask, occupancy_chunk, ...
                                           bin_factor, x_offset_occ, occupancy_size)
%CHECK_COLLISION_BINARY Check if rotated binary mask overlaps with occupancy

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

function is_valid = check_collision_sphere(cx, cy, cz, occupancy_chunk, radius, bin_factor, x_offset_occ)
%CHECK_COLLISION_SPHERE Check collision using spherical exclusion zone

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

    % Check if range is valid
    if isempty(x_range) || isempty(y_range) || isempty(z_range)
        is_valid = true;
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

function [occupancy_chunk, occupancy_cpu] = update_occupancy_binary(pos, binary_mask, ...
    occupancy_chunk, occupancy_cpu, bin_factor, x_offset_occ, occupancy_size)
%UPDATE_OCCUPANCY_BINARY Insert rotated binary mask into occupancy maps

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

function [occupancy_chunk, occupancy_cpu] = update_occupancy_sphere(cx, cy, cz, ...
    occupancy_chunk, occupancy_cpu, radius, bin_factor, x_offset_occ)
%UPDATE_OCCUPANCY_SPHERE Mark spherical region as occupied in both arrays

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

function write_csv(csv_path, particles, sampling_rate)
%WRITE_CSV Write particle parameters in emClarity 31-field format

    fid = fopen(csv_path, 'w');

    n_particles = size(particles.pos, 1);

    for i = 1:n_particles
        r = reshape(particles.rotmat(:,:,i), 1, 9);

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

function write_tomosize(tomosize_path, tomo_size, pixel_size)
%WRITE_TOMOSIZE Write tomogram size and pixel size to file

    fid = fopen(tomosize_path, 'w');
    fprintf(fid, '%d\n', tomo_size(1));
    fprintf(fid, '%d\n', tomo_size(2));
    fprintf(fid, '%d\n', tomo_size(3));
    fprintf(fid, '%.6f\n', pixel_size);
    fclose(fid);
end

function defocus_values = calculate_defocus_from_z(particles, pixel_size)
%CALCULATE_DEFOCUS_FROM_Z Encode Z positions as defocus values

    n_particles = size(particles.pos_ang, 1);

    % Get Z offsets relative to first particle
    z_offsets = particles.pos_ang(:, 3) - particles.pos_ang(1, 3);

    % Nominal defocus (2 microns = 20000 Angstroms)
    nominal_defocus = 20000;
    defocus_values = nominal_defocus - z_offsets;

    % Adjust so first particle's defocus equals the average
    offset_adj = mean(defocus_values) - defocus_values(1);
    defocus_values = defocus_values + offset_adj;
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

    % Default optical parameters
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

        % Position in Angstroms
        xShift = particles.pos_ang(i, 1);
        yShift = particles.pos_ang(i, 2);

        % Defocus (same for df1 and df2, no astigmatism)
        df1 = defocus_values(i);
        df2 = defocus_values(i);
        dfA = 0;

        % Best 2D class based on template index
        best2dClass = particles.template_idx(i);

        % PDB path in single quotes (required by cisTEM)
        pdb_path = particles.pdb_path{i};
        if isempty(pdb_path)
            pdb_path_quoted = '''none''';
        else
            pdb_path_quoted = sprintf('''%s''', pdb_path);
        end

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
