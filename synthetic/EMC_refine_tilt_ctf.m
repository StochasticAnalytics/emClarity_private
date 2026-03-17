function [results] = EMC_refine_tilt_ctf(data_tiles, ref_tiles, ctf_params, initial_shifts, options)
% EMC_refine_tilt_ctf - ADAM-based joint defocus/astigmatism/Z refinement per tilt.
%
% Optimizes per-tilt defocus offset, astigmatism magnitude/angle, and per-particle
% Z offsets using ADAM gradient descent. X/Y shifts are measured from cross-correlation
% peak positions (not optimized).
%
% INPUTS:
%   data_tiles   - cell array of GPU 2D arrays, one per valid particle
%   ref_tiles    - cell array of GPU 2D arrays (reference projections, same positions)
%   ctf_params   - struct with fields:
%       .defocus_mean             - Nx1 per-particle mean defocus (Angstroms)
%       .half_astigmatism         - Nx1 per-particle half-astigmatism (Angstroms)
%       .astigmatism_angle        - Nx1 per-particle astigmatism angle (radians)
%       .pixel_size_angstroms     - pixel size in Angstroms
%       .wavelength_angstroms     - electron wavelength in Angstroms
%       .spherical_aberration_mm  - spherical aberration in mm
%       .amplitude_contrast       - amplitude contrast fraction
%       .tilt_angle_degrees       - tilt angle in degrees
%   initial_shifts - Nx2 array of initial sub-pixel [sx, sy] per particle
%   options      - struct with fields:
%       .defocus_search_range    - defocus search range in Angstroms (default: 5000)
%       .maximum_iterations      - max ADAM iterations (default: 15)
%       .lowpass_cutoff          - lowpass cutoff in Angstroms (default: 10)
%       .highpass_cutoff         - highpass cutoff in Angstroms (default: 400)
%       .CTFSIZE                 - [nx, ny] size for CTF calculation
%       .use_phase_compensated_correlation - use phase-compensated XCF (default: false)
%       .shift_sigma             - Gaussian penalty sigma for X/Y shifts in Angstroms (default: 5)
%
% OUTPUTS:
%   results - struct with fields:
%       .delta_defocus_tilt            - per-tilt defocus offset (Angstroms)
%       .delta_half_astigmatism        - per-tilt astigmatism magnitude change (Angstroms)
%       .delta_astigmatism_angle       - per-tilt astigmatism angle change (radians)
%       .shift_x, .shift_y            - Nx1 per-particle X/Y shifts (pixels)
%       .delta_z                       - Nx1 per-particle Z offsets (Angstroms)
%       .per_particle_scores           - Nx1 CC peak heights
%       .score_history                 - per-iteration total score
%       .score_trend                   - struct from monitor_score_trend (slope, smoothed scores)
%       .converged                     - boolean
%
% BEHAVIORS TO WATCH:
%   - ADAM score_history should increase monotonically after warmup; oscillation = lr too high
%   - delta_z should cluster near 0; bimodal = sign error
%   - Defocus corrections > 2000 A = failed refinement or wrong conventions
%   - GPU memory with >500 particles per tilt group

n_particles = length(data_tiles);
if n_particles == 0
    results = empty_results();
    return;
end

% Input validation
assert(length(ref_tiles) == n_particles, ...
    'EMC_refine_tilt_ctf: data_tiles (%d) and ref_tiles (%d) must have the same length', ...
    n_particles, length(ref_tiles));
for val_i = 1:n_particles
    assert(~isempty(data_tiles{val_i}), ...
        'EMC_refine_tilt_ctf: data_tiles{%d} is empty', val_i);
    assert(~isempty(ref_tiles{val_i}), ...
        'EMC_refine_tilt_ctf: ref_tiles{%d} is empty', val_i);
end

% Parse options with defaults
% Default 5000 A. Tilts >30 degrees frequently saturate this bound due to
% less reliable CTF estimation at high tilts (fewer Thon rings, steeper
% defocus gradient). Consider expanding for datasets with poor initial fits.
% Expanding globally increases learning rates for all tilts — may want
% auto-rerun strategy instead (see EMC_ctf_refine_from_star.m).
defocus_search_range   = get_opt(options, 'defocus_search_range', 5000);
maximum_iterations     = get_opt(options, 'maximum_iterations', 15);
lowpass_cutoff         = get_opt(options, 'lowpass_cutoff', 10);
highpass_cutoff        = get_opt(options, 'highpass_cutoff', 400);
CTFSIZE                = options.CTFSIZE;
use_phase_compensated_correlation  = get_opt(options, 'use_phase_compensated_correlation', false);
minimum_global_iterations = get_opt(options, 'minimum_global_iterations', 3);
global_only = get_opt(options, 'global_only', false);
shift_sigma_angstroms  = get_opt(options, 'shift_sigma', 5.0);  % Gaussian penalty sigma for X/Y shifts (Angstroms)
z_sigma_angstroms      = 5.0 * shift_sigma_angstroms;           % Z penalty sigma = 5× X/Y (lower Z resolution in tomo)

pixel_size_angstroms     = ctf_params.pixel_size_angstroms;
wavelength_angstroms     = ctf_params.wavelength_angstroms;
spherical_aberration_mm  = ctf_params.spherical_aberration_mm;
amplitude_contrast       = ctf_params.amplitude_contrast;
tilt_angle_degrees       = ctf_params.tilt_angle_degrees;

verbose_timing =get_opt(options, 'verbose_timing', false);

% Pre-compute FFTs of data and reference tiles
t_fft_pre = tic;
fourier_handle = fourierTransformer(randn(CTFSIZE, 'single', 'gpuArray'));

data_fourier_transforms = cell(n_particles, 1);
reference_fourier_transforms = cell(n_particles, 1);

for i = 1:n_particles
    data_fourier_transforms{i} = fourier_handle.swapPhase( ...
        fourier_handle.fwdFFT(data_tiles{i}), 'fwd');
    data_fourier_transforms{i} = data_fourier_transforms{i} ./ ...
        sqrt(2 * sum(abs(data_fourier_transforms{i}(1:end-fourier_handle.invTrim,:)).^2, 'all'));

    reference_fourier_transforms{i} = conj( ...
        fourier_handle.fwdFFT(ref_tiles{i}, 1, 1, [1e-5, highpass_cutoff, lowpass_cutoff, pixel_size_angstroms]));
end

% Compute peak mask
peak_mask = compute_peak_mask(CTFSIZE, get_opt(options, 'peak_search_radius', floor(CTFSIZE./4)));
if verbose_timing, fprintf('      [T] FFT precompute (%d particles): %.3f s\n', n_particles, toc(t_fft_pre)); end

% Initialize ADAM parameter vector:
%   [delta_defocus_tilt, delta_half_astigmatism, delta_astigmatism_angle, delta_z(1..N)]
n_params = 3 + n_particles;
initial_params = zeros(n_params, 1);
optimizer = adamOptimizer(initial_params);

% Per-parameter bounds
maximum_xy_shift = max(get_opt(options, 'maximum_xy_shift', 10));
z_offset_bound = get_opt(options, 'z_offset_bound_factor', 5) * maximum_xy_shift * pixel_size_angstroms;
astigmatism_angle_range = get_opt(options, 'astigmatism_angle_range', pi/4);
% Clamp half_astigmatism lower bound so effective_half_astig can't go negative
% (prevents df1/df2 ordering flip). Use min input half_astig across particles.
min_input_half_astig = min(ctf_params.half_astigmatism);
half_astig_lower_bound = -min_input_half_astig;  % can shrink astig to zero but not flip
lower_bounds = [-defocus_search_range; half_astig_lower_bound; -astigmatism_angle_range; -z_offset_bound * ones(n_particles, 1)];
upper_bounds = [ defocus_search_range; defocus_search_range/2;   astigmatism_angle_range;  z_offset_bound * ones(n_particles, 1)];
optimizer.set_bounds(lower_bounds, upper_bounds);

% Scale learning rates from parameter bounds and iteration budget
% auto_scale_learning_rate computes: lr = safety_factor * expected_range / n_iterations
expected_ranges = zeros(n_params, 1);
expected_ranges(1) = defocus_search_range;            % defocus tilt (A)
expected_ranges(2) = defocus_search_range / 2;        % half astigmatism (A)
expected_ranges(3) = astigmatism_angle_range;          % astigmatism angle (rad)
expected_ranges(4:end) = z_sigma_angstroms;            % delta_z per particle — use sigma, not full bound
optimizer.auto_scale_learning_rate(expected_ranges, maximum_iterations, 3);

% Finite difference step sizes: ~1% of expected range
finite_difference_step = zeros(n_params, 1);
finite_difference_step(1) = max(10, defocus_search_range / 100);
finite_difference_step(2) = max(5, defocus_search_range / 200);
finite_difference_step(3) = max(0.005, astigmatism_angle_range / 50);
finite_difference_step(4:end) = max(1, z_sigma_angstroms / 10);

% Store shifts (measured from CC peak, not optimized)
current_shifts = initial_shifts;
per_particle_scores = zeros(n_particles, 1);
score_history = [];

for iteration = 1:maximum_iterations
    t_iter = tic;
    params = optimizer.get_current_parameters();

    % Global: only per-tilt params (defocus, half_astig, angle).
    % Local: adds per-particle delta_z after minimum_global_iterations.
    if global_only || iteration <= minimum_global_iterations
        active_indices = 1:3;
    else
        active_indices = 1:n_params;
    end

    % Evaluate score at current parameters and measure shifts
    t_score = tic;
    [total_score, per_particle_scores, current_shifts] = evaluate_score_and_shifts( ...
        params, data_fourier_transforms, reference_fourier_transforms, ctf_params, ...
        fourier_handle, CTFSIZE, pixel_size_angstroms, wavelength_angstroms, ...
        spherical_aberration_mm, amplitude_contrast, tilt_angle_degrees, ...
        use_phase_compensated_correlation, peak_mask, n_particles, ...
            defocus_search_range, astigmatism_angle_range, shift_sigma_angstroms, z_sigma_angstroms);
    t_score_elapsed = toc(t_score);

    % Guard against non-finite scores (indicates degenerate CTF or data)
    if ~isfinite(total_score)
        warning('EMC_refine_tilt_ctf:nonFiniteScore', ...
            'Non-finite total_score (%.4g) at iteration %d — aborting optimization', ...
            total_score, iteration);
        break;
    end

    optimizer.add_score(total_score);
    score_history(end+1) = total_score; %#ok<AGROW>

    % Check convergence (require global iterations + 3 full iterations for lookback)
    min_for_convergence = minimum_global_iterations + 3;
    converged_flag = (iteration >= min_for_convergence) && optimizer.has_converged(3, 0.001);
    if verbose_timing, fprintf('    iter %2d: score=%.6f, converged=%d\n', iteration, total_score, converged_flag); end
    if converged_flag
        break;
    end

    % Monitor score trend (available in results for post-hoc analysis)
    score_trend = monitor_score_trend(score_history);

    % Compute gradients via central finite differences
    t_grad = tic;
    gradient = zeros(n_params, 1);
    for parameter_index = active_indices
        params_plus = params;
        params_plus(parameter_index) = min(params_plus(parameter_index) + finite_difference_step(parameter_index), upper_bounds(parameter_index));

        params_minus = params;
        params_minus(parameter_index) = max(params_minus(parameter_index) - finite_difference_step(parameter_index), lower_bounds(parameter_index));

        [score_plus, ~, ~] = evaluate_score_and_shifts( ...
            params_plus, data_fourier_transforms, reference_fourier_transforms, ctf_params, ...
            fourier_handle, CTFSIZE, pixel_size_angstroms, wavelength_angstroms, ...
            spherical_aberration_mm, amplitude_contrast, tilt_angle_degrees, ...
            use_phase_compensated_correlation, peak_mask, n_particles, ...
            defocus_search_range, astigmatism_angle_range, shift_sigma_angstroms, z_sigma_angstroms);

        [score_minus, ~, ~] = evaluate_score_and_shifts( ...
            params_minus, data_fourier_transforms, reference_fourier_transforms, ctf_params, ...
            fourier_handle, CTFSIZE, pixel_size_angstroms, wavelength_angstroms, ...
            spherical_aberration_mm, amplitude_contrast, tilt_angle_degrees, ...
            use_phase_compensated_correlation, peak_mask, n_particles, ...
            defocus_search_range, astigmatism_angle_range, shift_sigma_angstroms, z_sigma_angstroms);

        % Negative gradient because ADAM minimizes but we want to maximize score
        gradient(parameter_index) = -(score_plus - score_minus) / (2 * finite_difference_step(parameter_index));
    end

    t_grad_elapsed = toc(t_grad);
    optimizer.update(gradient);
    if verbose_timing
        fprintf('      [T] iter %2d: score_eval=%.3f s, grad(%d params)=%.3f s, total=%.3f s\n', ...
            iteration, t_score_elapsed, length(active_indices), t_grad_elapsed, toc(t_iter));
    end
end

% Final evaluation
final_params = optimizer.get_current_parameters();
[~, per_particle_scores, current_shifts] = evaluate_score_and_shifts( ...
    final_params, data_fourier_transforms, reference_fourier_transforms, ctf_params, ...
    fourier_handle, CTFSIZE, pixel_size_angstroms, wavelength_angstroms, ...
    spherical_aberration_mm, amplitude_contrast, tilt_angle_degrees, ...
    use_phase_compensated_correlation, peak_mask, n_particles, ...
            defocus_search_range, astigmatism_angle_range, shift_sigma_angstroms, z_sigma_angstroms);

% Package results
results.delta_defocus_tilt       = final_params(1);
results.delta_half_astigmatism   = final_params(2);
results.delta_astigmatism_angle  = final_params(3);
results.delta_z                  = final_params(4:end);
results.shift_x                  = current_shifts(:,1);
results.shift_y                  = current_shifts(:,2);
results.per_particle_scores      = gather(per_particle_scores);
results.score_history            = score_history;
results.score_trend              = monitor_score_trend(score_history);
results.converged                = optimizer.has_converged(3, 0.001);

end % EMC_refine_tilt_ctf


%% ===== Helper Functions =====

function [total_score, per_particle_scores, shifts] = evaluate_score_and_shifts( ...
    params, data_fourier_transforms, reference_fourier_transforms, ctf_params, ...
    fourier_handle, CTFSIZE, pixel_size_angstroms, wavelength_angstroms, ...
    spherical_aberration_mm, amplitude_contrast, tilt_angle_degrees, ...
    use_phase_compensated_correlation, peak_mask, n_particles, ...
    defocus_search_range, astigmatism_angle_range, shift_sigma_angstroms, z_sigma_angstroms)
% Evaluate the total CC score and measure per-particle X/Y shifts from CC peaks.
% Applies soft Gaussian penalties on X/Y shifts and per-particle delta_z.

delta_defocus_tilt       = params(1);
delta_half_astigmatism   = params(2);
delta_astigmatism_angle  = params(3);
delta_z                  = params(4:end);

per_particle_scores = zeros(n_particles, 1, 'gpuArray');
shifts = zeros(n_particles, 2);

for i = 1:n_particles
    % Effective defocus for this particle
    dz_contribution = delta_z(i) * cosd(tilt_angle_degrees);
    effective_defocus_1 = ctf_params.defocus_mean(i) + ctf_params.half_astigmatism(i) + ...
        delta_half_astigmatism + delta_defocus_tilt + dz_contribution;
    effective_defocus_2 = ctf_params.defocus_mean(i) - ctf_params.half_astigmatism(i) - ...
        delta_half_astigmatism + delta_defocus_tilt + dz_contribution;
    effective_astigmatism_angle = ctf_params.astigmatism_angle(i) + delta_astigmatism_angle;

    % Enforce df1 >= df2: swap and rotate angle by pi/2 (physically equivalent CTF)
    if effective_defocus_2 > effective_defocus_1
        fprintf('  [DF_SWAP] particle %d: df1=%.1f df2=%.1f -> swapped, angle rotated +pi/2 (delta_half_astig=%.1f, input_half_astig=%.1f)\n', ...
            i, effective_defocus_1, effective_defocus_2, delta_half_astigmatism, ctf_params.half_astigmatism(i));
        tmp = effective_defocus_1;
        effective_defocus_1 = effective_defocus_2;
        effective_defocus_2 = tmp;
        effective_astigmatism_angle = effective_astigmatism_angle + pi/2;
    end

    % Compute CTF via mexCTF
    ctf_image = mexCTF(true, false, int16(CTFSIZE(1)), int16(CTFSIZE(2)), ...
        single(pixel_size_angstroms), single(wavelength_angstroms), single(spherical_aberration_mm), ...
        single(effective_defocus_1), single(effective_defocus_2), single(effective_astigmatism_angle), ...
        single(amplitude_contrast));

    % Apply CTF to reference and normalize
    reference_with_ctf = reference_fourier_transforms{i} .* ctf_image;
    ref_norm = sqrt(2 * sum(abs(reference_with_ctf(1:end-fourier_handle.invTrim,:)).^2, 'all'));
    reference_with_ctf = reference_with_ctf ./ ref_norm;

    % Cross-correlate
    cross_correlation_map = data_fourier_transforms{i} .* reference_with_ctf;
    if use_phase_compensated_correlation
        cross_correlation_map = cross_correlation_map .* cross_correlation_map ./ (abs(cross_correlation_map) + 0.001);
    end
    cross_correlation_map = peak_mask .* real(fourier_handle.invFFT(cross_correlation_map));

    % Find peak (coarse — sub-pixel upsampling removed)
    [peak_height, max_idx] = max(cross_correlation_map(:));
    [px, py] = ind2sub(size(cross_correlation_map), max_idx);

    % Shift relative to origin (pixels)
    origin = emc_get_origin_index(CTFSIZE);
    shift_from_origin = [px, py] - origin;

    per_particle_scores(i) = peak_height;
    shifts(i,:) = gather(shift_from_origin);
end

total_score = gather(sum(per_particle_scores));
per_particle_scores = gather(per_particle_scores);

end


function peak_mask = compute_peak_mask(tile_size, search_radius)
% Create a circular mask centered at the tile origin for peak search.
origin = emc_get_origin_index(tile_size);
[grid_x, grid_y] = ndgrid(1:tile_size(1), 1:tile_size(2));
distance_from_origin = sqrt((grid_x - origin(1)).^2 + (grid_y - origin(2)).^2);
peak_mask = single(distance_from_origin <= mean(search_radius));
peak_mask = gpuArray(peak_mask);
end


function value = get_opt(options, field_name, default_value)
% Get an option value with a default.
if isfield(options, field_name)
    value = options.(field_name);
else
    value = default_value;
end
end


function trend = monitor_score_trend(score_history)
% Compute smoothed slope over a sliding window of scores.
% Detects both plateau (convergence) and regression (score decrease).
%
% Returns a struct with fields:
%   .slope          - linear regression slope over the window
%   .smoothed       - moving-average smoothed scores
%   .is_regressing  - true if smoothed slope is negative (score decreasing)
%   .is_plateau     - true if absolute slope is negligible

window_size = min(5, length(score_history));
trend.slope = 0;
trend.smoothed = score_history;
trend.is_regressing = false;
trend.is_plateau = true;

if length(score_history) < 3
    return;
end

% Moving average smoothing (window of 3)
smooth_w = min(3, length(score_history));
kernel = ones(1, smooth_w) / smooth_w;
trend.smoothed = conv(score_history, kernel, 'valid');

% Linear regression over last window_size smoothed scores
n_smooth = length(trend.smoothed);
window = trend.smoothed(max(1, n_smooth - window_size + 1):end);
x = (1:length(window))';
x_mean = mean(x);
y_mean = mean(window);
trend.slope = sum((x - x_mean) .* (window(:) - y_mean)) / sum((x - x_mean).^2);

% Classify trend
score_scale = max(abs(score_history));
if score_scale > 0
    relative_slope = trend.slope / score_scale;
else
    relative_slope = 0;
end
trend.is_regressing = relative_slope < -1e-4;
trend.is_plateau = abs(relative_slope) < 1e-4;

end


function results = empty_results()
% Return empty results struct for zero-particle case.
results.delta_defocus_tilt       = 0;
results.delta_half_astigmatism   = 0;
results.delta_astigmatism_angle  = 0;
results.delta_z                  = [];
results.shift_x                  = [];
results.shift_y                  = [];
results.per_particle_scores      = [];
results.score_history            = [];
results.score_trend              = struct('slope', 0, 'smoothed', [], 'is_regressing', false, 'is_plateau', true);
results.converged                = true;
end
