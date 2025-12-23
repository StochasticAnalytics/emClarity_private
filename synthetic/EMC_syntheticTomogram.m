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

%% Determine particle radius from shape-based mask
fprintf('Detecting particle radius from shape-based mask\n');

% Normalize template
template_normalized = template - min(template(:));
template_normalized = template_normalized / max(template_normalized(:));

% Create binary mask at 10% threshold
binary_mask = template_normalized > 0.1;

% Find furthest non-zero voxel from center
center = ceil((template_size + 1) / 2);
[X, Y, Z] = ndgrid(1:template_size(1), 1:template_size(2), 1:template_size(3));
dist_from_center = sqrt((X - center(1)).^2 + (Y - center(2)).^2 + (Z - center(3)).^2);
particle_radius = max(dist_from_center(binary_mask));

fprintf('Detected particle radius: %.1f pixels\n', particle_radius);

% Calculate exclusion radius
exclusion_radius = exclusion_factor * particle_radius;
fprintf('Exclusion radius (factor %.2f): %.1f pixels\n', exclusion_factor, exclusion_radius);

%% Initialize interpolator on GPU
fprintf('Initializing GPU interpolator\n');
[template_interp, ~] = interpolator(gpuArray(single(template)), ...
                                     [0,0,0], [0,0,0], 'Bah', 'forward', 'C1', false);

%% Initialize output volumes
fprintf('Initializing tomogram [%d, %d, %d] on CPU\n', tomo_size(1), tomo_size(2), tomo_size(3));
tomogram = zeros(tomo_size, 'single');

% Bin the occupancy map to reduce GPU memory (collision detection doesn't need full resolution)
occupancy_bin = 3;
occupancy_size = ceil(tomo_size / occupancy_bin);
fprintf('Initializing occupancy map on GPU [%d, %d, %d] (binned %dx)\n', ...
        occupancy_size(1), occupancy_size(2), occupancy_size(3), occupancy_bin);
occupancy = gpuArray(false(occupancy_size));

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

%% Main placement loop
fprintf('Starting particle placement...\n');
particle_count = 0;
attempts = 0;
consecutive_failures = 0;
max_consecutive_failures = 300;
last_report_time = 0;
report_interval = 5;  % Report every 5 seconds

tic;
while particle_count < max_particles && attempts < max_attempts
    attempts = attempts + 1;

    % Progress reporting every few seconds (even during failed attempts)
    elapsed = toc;
    if elapsed - last_report_time >= report_interval
        if particle_count > 0
            rate = particle_count / elapsed;
            fprintf('  [%.0fs] %d particles placed, %d attempts, %d consecutive failures (%.1f particles/sec)\n', ...
                    elapsed, particle_count, attempts, consecutive_failures, rate);
        else
            fprintf('  [%.0fs] Searching for valid positions... %d attempts, %d consecutive failures\n', ...
                    elapsed, attempts, consecutive_failures);
        end
        last_report_time = elapsed;
    end

    % Generate random position within valid bounds
    pos = [randi([min_bound(1), max_bound(1)]), ...
           randi([min_bound(2), max_bound(2)]), ...
           randi([min_bound(3), max_bound(3)])];

    % Check for collision (using binned occupancy map)
    if ~check_collision(pos(1), pos(2), pos(3), occupancy, exclusion_radius, occupancy_bin)
        consecutive_failures = consecutive_failures + 1;
        if consecutive_failures >= max_consecutive_failures
            fprintf('Volume saturated after %d consecutive failed attempts\n', consecutive_failures);
            break;
        end
        continue;
    end

    consecutive_failures = 0;
    particle_count = particle_count + 1;

    % Generate random rotation (matching BH_defineMatrix method)
    [phi, theta, psi_minus_phi, rotmat] = generate_random_rotation();
    angles = [phi, theta, psi_minus_phi];

    % Generate random subpixel shifts [-1, 1]
    shifts = 2 * rand(1, 3) - 1;

    % Rotate template on GPU with subpixel shifts
    rotated_gpu = template_interp.interp3d(angles, shifts, 'Bah', 'forward', 'C1');

    % Copy back to CPU
    rotated = gather(rotated_gpu);

    % Insert into tomogram (CPU)
    tomogram = insert_particle(tomogram, rotated, pos, template_size);

    % Update occupancy (GPU, binned coordinates)
    occupancy = update_occupancy(pos(1), pos(2), pos(3), occupancy, exclusion_radius, occupancy_bin);

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
        fprintf('  Placed particle %d at [%d, %d, %d] (%.1f particles/sec)\n', ...
                particle_count, pos(1), pos(2), pos(3), rate);
        last_report_time = elapsed;
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
