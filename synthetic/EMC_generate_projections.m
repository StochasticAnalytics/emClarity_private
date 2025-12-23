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

parse(p, tomogram_path, tiltfile_path, slab_thickness_angstrom, varargin{:});

gpu_id = p.Results.gpu_id;
debug_tilt = p.Results.debug_tilt;

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

% Load the full volume onto GPU
fprintf('Loading tomogram volume into GPU memory...\n');
tomogram = gpuArray(OPEN_IMG('single',tomogram_path));
fprintf('  Tomogram loaded to GPU: %.2f GB\n', numel(tomogram) * 4 / 1e9);

%% Load tilt file
fprintf('Loading tilt file from %s\n', tiltfile_path);
TLT = load(tiltfile_path);

n_tilts = size(TLT, 1);
fprintf('  Number of tilts: %d\n', n_tilts);

% Column 4 contains tilt angles in degrees
tilt_angles = TLT(:, 4);
fprintf('  Tilt range: %.1f to %.1f degrees\n', min(tilt_angles), max(tilt_angles));

% CTF parameters from TLT columns for wave propagation
cumulative_dose = TLT(:, 11);      % e⁻/Å² total for tilt series
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
stack_path = fullfile(tomo_dir, [tomo_name '.st']);

%% Calculate tomogram origin using emClarity convention
tomo_origin = emc_get_origin_index(tomo_size);
fprintf('  Tomogram origin: [%d, %d, %d]\n', tomo_origin(1), tomo_origin(2), tomo_origin(3));

%% Calculate slab thickness in pixels (ensure at least 1 pixel)
slab_nz = max(1, round(slab_thickness_pixels));
fprintf('  Slab dimensions: [%d, %d, %d] pixels\n', projection_size(1), projection_size(2), slab_nz);

%% Main projection loop
fprintf('\nGenerating projections...\n');
tic;

n_to_process = length(tilt_indices);
for iProc = 1:n_to_process
    iTilt = tilt_indices(iProc);
    tilt_angle = tilt_angles(iTilt);

    % Get rotation matrix using emClarity convention
    % 'TILT' gives Ry matrix, 'fwdVector' transforms tomo coords to projection coords
    % For sampling, we need 'inv' to go from projection coords back to tomo coords
    rTilt_fwd = BH_defineMatrix(tilt_angle, 'TILT', 'fwdVector');
    rTilt_inv = BH_defineMatrix(tilt_angle, 'TILT', 'inv');

    % Calculate bounding box of rotated tomogram in microscope Z
    % Corner coordinates relative to origin (centered)
    half_x = (tomo_size(1) - 1) / 2;
    half_z = (tomo_size(3) - 1) / 2;
    corners = [-half_x, half_x; -half_z, half_z];

    % After Y-axis rotation, Z in microscope frame is:
    % Z_mic = X_tomo * sin(theta) + Z_tomo * cos(theta)  (from rTilt_fwd)
    z_rotated = [];
    for cx = corners(1,:)
        for cz = corners(2,:)
            coord_tomo = [cx; 0; cz];
            coord_mic = rTilt_fwd * coord_tomo;
            z_rotated = [z_rotated, coord_mic(3)];
        end
    end

    z_min = min(z_rotated);
    z_max = max(z_rotated);

    % Number of slabs to process
    total_thickness = z_max - z_min;
    n_slabs = ceil(total_thickness / slab_thickness_pixels);
    if n_slabs < 1
        n_slabs = 1;
    end

    prj_index = TLT(iTilt, 1);  % Projection index from TLT column 1
    fprintf('  Tilt %d -> prj %d (%.1f deg): processing %d slabs (z: %.1f to %.1f pixels)\n', ...
            iTilt, prj_index, tilt_angle, n_slabs, z_min, z_max);

    % Create Fresnel propagator for this tilt using complex mode
    % exp(+i * chi) where chi = -π * λ * Δz * q² (pure Fresnel, no Cs, no AMPCONT)
    % BH_ctfCalc expects all units in METERS (converts to Angstroms internally)
    fresnel_defocus_meters = slab_thickness_angstrom * 1e-10;  % Convert Angstroms to meters
    [~, fresnel_propagator] = BH_ctfCalc(pixel_size_meters(iTilt), ...
        0, ...                          % Cs = 0 for pure Fresnel
        wavelength(iTilt), ...          % Already in meters from TLT
        fresnel_defocus_meters, ...     % Defocus = slab thickness in meters
        projection_size, ...
        0, ...                          % AMPCONT = 0 (no phase shift)
        -1, ...
        'complex');                     % Triggers complex mode

    % Initialize wave function: amplitude = sqrt(dose_per_projection * pixel_area)
    % Dose for this projection = cumulative(i) - cumulative(prev in exposure order)
    % TLT is sorted by tilt angle, but cumulative_dose reflects acquisition order
    this_cumulative = cumulative_dose(iTilt);
    % Find doses smaller than this one (earlier in exposure order)
    earlier_doses = cumulative_dose(cumulative_dose < this_cumulative);
    if isempty(earlier_doses)
        % This is the first exposure
        dose_this_projection = this_cumulative;
    else
        % Previous exposure is the max of all earlier doses
        dose_this_projection = this_cumulative - max(earlier_doses);
    end
    pixel_area_angstrom2 = (pixel_size)^2;  % pixel_size is already in Angstroms
    wave_amplitude = sqrt(dose_this_projection * pixel_area_angstrom2);

    % Complex wave on GPU: real = amplitude, imag = 0
    wave_func = gpuArray(complex(wave_amplitude * ones(projection_size, 'single'), 0));
    slab_tic = tic;
    % Process each slab from top (z_max) to bottom (z_min) with wave propagation
    for iSlab = 1:n_slabs
        % Z position of this slab center in microscope frame
        z_slab_center = z_max - (iSlab - 0.5) * slab_thickness_pixels;

        % Create 3D coordinate grids for this slab [nx, ny, slab_nz] on GPU
        slab_size = [projection_size, slab_nz];
        [slab_gX, slab_gY, slab_gZ] = EMC_coordGrids('cartesian', slab_size, 'gpu', {});

        % Offset slab Z coordinates to this slab's position in microscope frame
        % slab_gZ is centered around 0, shift to be centered at z_slab_center
        slab_gZ_mic = slab_gZ + z_slab_center;

        % Transform microscope coordinates back to tomogram coordinates using rTilt_inv
        % The inverse tilt rotation: microscope -> tomogram
        % x_tomo = x_mic * cos(theta) + z_mic * sin(theta)
        % y_tomo = y_mic
        % z_tomo = -x_mic * sin(theta) + z_mic * cos(theta)
        x_tomo = slab_gX * rTilt_inv(1,1) + slab_gZ_mic * rTilt_inv(1,3);
        y_tomo = slab_gY;  % Y unchanged (rotation axis)
        z_tomo = slab_gX * rTilt_inv(3,1) + slab_gZ_mic * rTilt_inv(3,3);

        % Convert from centered coordinates to array indices (1-based)
        x_idx = x_tomo + tomo_origin(1);
        y_idx = y_tomo + tomo_origin(2);
        z_idx = z_tomo + tomo_origin(3);

        % Sample 3D slab from tomogram using interpn (GPU compatible)
        % interpn with default grid uses ndgrid ordering: dim1=X, dim2=Y, dim3=Z
        slab_volume = interpn(tomogram, x_idx, y_idx, z_idx, 'linear', 0);

        % Project the slab: sum over the slab's Z dimension (dimension 3)
        slab_projection = sum(slab_volume, 3);


        % Wave propagation: phase grating transmission then Fresnel propagation
        % Phase grating: exp(i * projected_potential) - already on GPU from interpn
        phase_grating = exp(1i * slab_projection);

        % Transmission: multiply wave by phase grating
        wave_func = wave_func .* phase_grating;

        % Propagation: FFT -> multiply by Fresnel propagator -> IFFT
        % BH_ctfCalc returns arrays with origin at (0,0), native FFT layout
        wave_func = ifft2(fft2(wave_func).* fresnel_propagator);

        % Slab progress (every 10% or every 50 slabs, whichever is less frequent)
        if mod(iSlab, max(1, floor(n_slabs/10))) == 0 || iSlab == n_slabs
            slab_elapsed = toc(slab_tic);
            fprintf('    Slab %d/%d (%.0f%%) - z=%.1f - %.2f sec\n', ...
                    iSlab, n_slabs, 100*iSlab/n_slabs, z_slab_center, slab_elapsed);
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

    % Create complex CTF with full parameters (Cs, astigmatism, amplitude contrast)
    % All units in METERS - BH_ctfCalc converts internally
    [~, complex_ctf] = BH_ctfCalc(pixel_size_meters(iTilt), ...
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
    projection = real(ifft2(fft2(projection) .* exposure_filter));
    
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

end
