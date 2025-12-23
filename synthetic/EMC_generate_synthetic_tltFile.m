function EMC_generate_synthetic_tltFile(tomogram_path, defocus_angstrom, varargin)
% EMC_generate_synthetic_tltFile - Generate a synthetic tilt file for simulation
%
% This function creates a _ctf.tlt file that describes how to simulate projections
% from a synthetic tomogram. It generates a dose-symmetric tilt scheme and
% applies random variations to XY shifts, defocus, and astigmatism.
%
% Usage:
%   EMC_generate_synthetic_tltFile(tomogram_path, defocus_angstrom)
%   EMC_generate_synthetic_tltFile(tomogram_path, defocus_angstrom, 'param', value, ...)
%
% Required Inputs:
%   tomogram_path    - Full path to the input tomogram (MRC file)
%   defocus_angstrom - Mean defocus value in Angstroms (positive = underfocus)
%
% Optional Parameters (name-value pairs):
%   'defocus_std_angstrom'     - Std dev for defocus variation per tilt (A), default: 1000
%   'astigmatism_angstrom'     - Mean astigmatism magnitude (A), default: 500
%   'astigmatism_std_angstrom' - Std dev for astigmatism variation (A), default: 200
%   'tilt_range'               - [min_tilt, max_tilt] in degrees, default: [-60, 60]
%   'tilt_step'                - Tilt increment in degrees, default: 3
%   'dose_per_image'           - Dose per image in e-/A^2, default: 3.0
%   'shift_std_pixels'         - Std dev for XY shifts in pixels, default: 5.0
%   'Cs_mm'                    - Spherical aberration in mm, default: 2.7
%   'voltage_kev'              - Accelerating voltage in keV, default: 300
%   'amplitude_contrast'       - Amplitude contrast fraction, default: 0.07
%
% Output:
%   Writes <tomogram_basename>_ctf.tlt in the same directory as the tomogram

%% Parse input parameters
p = inputParser;
addRequired(p, 'tomogram_path', @ischar);
addRequired(p, 'defocus_angstrom', @isnumeric);

% Optional parameters with defaults
addParameter(p, 'defocus_std_angstrom', 100, @isnumeric);
addParameter(p, 'astigmatism_angstrom', 500, @isnumeric);
addParameter(p, 'astigmatism_std_angstrom', 50, @isnumeric);
addParameter(p, 'tilt_range', [-60, 60], @(x) isnumeric(x) && length(x) == 2);
addParameter(p, 'tilt_step', 3, @isnumeric);
addParameter(p, 'dose_per_image', 3.0, @isnumeric);
addParameter(p, 'shift_std_pixels', 5.0, @isnumeric);
addParameter(p, 'Cs_mm', 2.7, @isnumeric);
addParameter(p, 'voltage_kev', 300, @isnumeric);
addParameter(p, 'amplitude_contrast', 0.07, @isnumeric);

parse(p, tomogram_path, defocus_angstrom, varargin{:});
opts = p.Results;

%% Validate input file exists
if ~exist(tomogram_path, 'file')
    error('EMC_generate_synthetic_tltFile:FileNotFound', ...
          'Tomogram file not found: %s', tomogram_path);
end

%% Read tomogram header (do NOT load volume data)
fprintf('Reading header from: %s\n', tomogram_path);
mrc_obj = MRCImage(tomogram_path, 0);  % 0 = header only, no volume loading
header = getHeader(mrc_obj);

tomo_size_x = header.nX;
tomo_size_y = header.nY;
tomo_size_z = header.nZ;

% Get pixel size from header (MRC stores cell dimensions - divide by number of pixels)
if header.cellDimensionX > 0 && header.nX > 0
    pixel_size_angstrom = header.cellDimensionX / header.nX;
else
    error('EMC_generate_synthetic_tltFile:InvalidHeader', ...
          'Could not read valid pixel size from MRC header');
end

fprintf('  Tomogram dimensions: %d x %d x %d\n', tomo_size_x, tomo_size_y, tomo_size_z);
fprintf('  Pixel size: %.4f Angstroms\n', pixel_size_angstrom);

%% Generate dose-symmetric tilt scheme
% Start at 0, then alternate +step, -step, +2*step, -2*step, etc.
tilt_angles = generate_dose_symmetric_tilts(opts.tilt_range(1), ...
                                            opts.tilt_range(2), ...
                                            opts.tilt_step);
n_tilts = length(tilt_angles);

fprintf('  Number of tilts: %d\n', n_tilts);
fprintf('  Tilt range: %.1f to %.1f degrees (step: %.1f)\n', ...
        opts.tilt_range(1), opts.tilt_range(2), opts.tilt_step);

%% Calculate cumulative dose (accounting for cosine weighting)
% Images at higher tilt receive more dose per unit thickness
cumulative_dose = zeros(n_tilts, 1);
for i = 1:n_tilts
    cos_factor = 1.0 / cosd(tilt_angles(i));  % Dose scales with 1/cos(tilt)
    if i == 1
        cumulative_dose(i) = opts.dose_per_image * cos_factor;
    else
        cumulative_dose(i) = cumulative_dose(i-1) + opts.dose_per_image * cos_factor;
    end
end

fprintf('  Total dose: %.1f e-/A^2\n', cumulative_dose(end));

%% Convert units to SI (meters)
pixel_size_m = pixel_size_angstrom * 1e-10;       % Angstrom to meters
Cs_m = opts.Cs_mm * 1e-3;                         % mm to meters
wavelength_m = calculate_wavelength(opts.voltage_kev);

% Defocus: convert Angstroms to meters (positive = underfocus)
mean_defocus_m = opts.defocus_angstrom * 1e-10;
defocus_std_m = opts.defocus_std_angstrom * 1e-10;

% Astigmatism in meters
mean_astigmatism_m = opts.astigmatism_angstrom * 1e-10;
astigmatism_std_m = opts.astigmatism_std_angstrom * 1e-10;

%% Generate random variations for each tilt
% XY shifts (in pixels, from normal distribution)
shift_x = opts.shift_std_pixels * randn(n_tilts, 1);
shift_y = opts.shift_std_pixels * randn(n_tilts, 1);

% Defocus variation per tilt (in meters)
defocus_values = mean_defocus_m + defocus_std_m * randn(n_tilts, 1);

% Astigmatism magnitude and angle
% Column 12 stores defocus offset (astigmatism magnitude / 2)
% Column 13 stores astigmatism angle in radians
astigmatism_mag = abs(mean_astigmatism_m + astigmatism_std_m * randn(n_tilts, 1));
astigmatism_angle = 2 * pi * rand(n_tilts, 1);  % Random angle 0 to 2*pi

%% Build TLT matrix (23 columns)
% Column definitions from BH_ctf_Estimate.m:
%  1:  Projection index (1-based)
%  2:  dX shift (pixels)
%  3:  dY shift (pixels)
%  4:  Tilt angle (degrees)
%  5:  Projection rotation (degrees)
%  6:  Tilt azimuth (degrees)
%  7:  Tilt elevation e1 (unitless)
%  8:  Tilt elevation e2 (unitless)
%  9:  Tilt elevation e3 (unitless)
% 10:  (unused)
% 11:  Cumulative dose (e-/A^2)
% 12:  Defocus offset / astigmatism half (meters)
% 13:  Astigmatism angle (radians)
% 14:  Scale factor
% 15:  Defocus (meters)
% 16:  Pixel size (meters)
% 17:  Cs (meters)
% 18:  Wavelength (meters)
% 19:  Amplitude contrast
% 20:  Output X dimension
% 21:  Output Y dimension
% 22:  Output Z dimension
% 23:  Additional parameter (original index for sorting)

TLT = zeros(n_tilts, 23);

% Column 4: Tilt angle (degrees) - assign first so we can sort
TLT(:, 4) = tilt_angles;

% Column 1: Projection index based on tilt angle order
% Most negative tilt = projection 1, most positive = projection N
[~, tilt_sort_idx] = sort(tilt_angles, 'ascend');
projection_indices = zeros(n_tilts, 1);
projection_indices(tilt_sort_idx) = 1:n_tilts;
TLT(:, 1) = projection_indices;

% Columns 2-3: XY shifts (pixels)
TLT(:, 2) = shift_x;
TLT(:, 3) = shift_y;

% Columns 5-10: Rotation and elevation parameters (standard defaults)
TLT(:, 5) = 0;    % Projection rotation
TLT(:, 6) = 90.0; % Tilt azimuth
TLT(:, 7) = 1.0;  % e1
TLT(:, 8) = 0.0;  % e2
TLT(:, 9) = 0.0;  % e3
TLT(:,10) = 1.0;  % unused

% Column 11: Cumulative dose
TLT(:, 11) = cumulative_dose;

% Columns 12-13: Astigmatism (half-magnitude in meters, angle in radians)
TLT(:, 12) = astigmatism_mag / 2;  % Half because this represents offset from mean
TLT(:, 13) = astigmatism_angle;

% Column 14: Scale factor (default 1.0)
TLT(:, 14) = 1.0;

% Column 15: Defocus (meters)
TLT(:, 15) = defocus_values;

% Columns 16-18: CTF parameters
TLT(:, 16) = pixel_size_m;
TLT(:, 17) = Cs_m;
TLT(:, 18) = wavelength_m;

% Column 19: Amplitude contrast
TLT(:, 19) = opts.amplitude_contrast;

% Columns 20-22: Output dimensions (make odd for FFT)
odd_x = tomo_size_x + mod(tomo_size_x + 1, 2);
odd_y = tomo_size_y + mod(tomo_size_y + 1, 2);
odd_z = n_tilts;  % Number of projections
TLT(:, 20) = odd_x;
TLT(:, 21) = odd_y;
TLT(:, 22) = odd_z;

% Column 23: Original index (for tracking after sorting)
TLT(:, 23) = (1:n_tilts)';

%% Sort by absolute tilt angle (descending) - standard emClarity convention
[~, sort_idx] = sort(abs(TLT(:, 4)), 'descend');
TLT = TLT(sort_idx, :);

%% Write output file
[tomo_dir, tomo_name, ~] = fileparts(tomogram_path);
output_filename = fullfile(tomo_dir, [tomo_name '_ctf.tlt']);

fprintf('Writing tilt file: %s\n', output_filename);

fid = fopen(output_filename, 'w');
if fid == -1
    error('EMC_generate_synthetic_tltFile:FileWriteError', ...
          'Could not open file for writing: %s', output_filename);
end

% Format string matching BH_ctf_Estimate.m output format
fmt = ['%d\t%08.2f\t%08.2f\t%07.3f\t%07.3f\t%07.3f\t%07.7f\t%07.7f\t', ...
       '%07.7f\t%07.7f\t%5e\t%5e\t%5e\t%7e\t%5e\t%5e\t%5e\t%5e\t%5e\t', ...
       '%d\t%d\t%d\t%8.2f\n'];

for i = 1:n_tilts
    fprintf(fid, fmt, TLT(i, :));
end

fclose(fid);

fprintf('Done. Generated tilt file with %d projections.\n', n_tilts);
fprintf('  Mean defocus: %.0f A\n', opts.defocus_angstrom);
fprintf('  Defocus std: %.0f A\n', opts.defocus_std_angstrom);
fprintf('  Mean astigmatism: %.0f A\n', opts.astigmatism_angstrom);
fprintf('  XY shift std: %.1f pixels\n', opts.shift_std_pixels);

end  % main function


%% Helper function: Generate dose-symmetric tilt scheme
function tilt_angles = generate_dose_symmetric_tilts(min_tilt, max_tilt, step)
% Generate tilt angles in dose-symmetric order
% Starts at 0, then alternates: +step, -step, +2*step, -2*step, ...

% Generate all unique tilt angles in the range
all_angles = min_tilt:step:max_tilt;

% Find the index closest to zero (our starting point)
[~, zero_idx] = min(abs(all_angles));
start_angle = all_angles(zero_idx);

% Build dose-symmetric sequence
tilt_angles = start_angle;
used = false(size(all_angles));
used(zero_idx) = true;

% Alternate positive and negative from center
positive_idx = zero_idx + 1;
negative_idx = zero_idx - 1;
go_positive = true;  % Start with positive direction

while positive_idx <= length(all_angles) || negative_idx >= 1
    if go_positive && positive_idx <= length(all_angles)
        tilt_angles(end + 1) = all_angles(positive_idx); %#ok<AGROW>
        used(positive_idx) = true;
        positive_idx = positive_idx + 1;
    elseif ~go_positive && negative_idx >= 1
        tilt_angles(end + 1) = all_angles(negative_idx); %#ok<AGROW>
        used(negative_idx) = true;
        negative_idx = negative_idx - 1;
    elseif positive_idx <= length(all_angles)
        % Negative exhausted, continue positive
        tilt_angles(end + 1) = all_angles(positive_idx); %#ok<AGROW>
        positive_idx = positive_idx + 1;
    elseif negative_idx >= 1
        % Positive exhausted, continue negative
        tilt_angles(end + 1) = all_angles(negative_idx); %#ok<AGROW>
        negative_idx = negative_idx - 1;
    end
    go_positive = ~go_positive;  % Alternate direction
end

tilt_angles = tilt_angles(:);  % Column vector

end  % generate_dose_symmetric_tilts


%% Helper function: Calculate electron wavelength
function wavelength_m = calculate_wavelength(voltage_kev)
% Calculate relativistic electron wavelength from accelerating voltage
%
% λ = h / sqrt(2 * m_e * e * V * (1 + e*V / (2 * m_e * c^2)))
%
% For 300 keV: λ ≈ 1.969 pm = 1.969e-12 m

% Physical constants
h = 6.62607015e-34;     % Planck's constant (J·s)
m_e = 9.1093837e-31;    % Electron mass (kg)
e = 1.602176634e-19;    % Elementary charge (C)
c = 2.99792458e8;       % Speed of light (m/s)

% Convert keV to Volts
V = voltage_kev * 1000;

% Relativistic wavelength formula
eV = e * V;
m_e_c2 = m_e * c^2;
wavelength_m = h / sqrt(2 * m_e * eV * (1 + eV / (2 * m_e_c2)));

end  % calculate_wavelength
