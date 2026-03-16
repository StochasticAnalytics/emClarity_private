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
%       .upsample_factor         - Fourier upsampling factor (default: 8)
%       .upsample_window         - half-width of upsampling window (default: 8)
%       .lowpass_cutoff          - lowpass cutoff in Angstroms (default: 10)
%       .CTFSIZE                 - [nx, ny] size for CTF calculation
%       .use_phase_compensated_correlation - use phase-compensated XCF (default: false)
%       .warmup_iterations       - iterations with only per-tilt params (default: 3)
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
defocus_search_range   = get_opt(options, 'defocus_search_range', 5000);
maximum_iterations     = get_opt(options, 'maximum_iterations', 15);
upsample_factor        = get_opt(options, 'upsample_factor', 8);
upsample_window        = get_opt(options, 'upsample_window', 8);
lowpass_cutoff         = get_opt(options, 'lowpass_cutoff', 10);
CTFSIZE                = options.CTFSIZE;
use_phase_compensated_correlation  = get_opt(options, 'use_phase_compensated_correlation', false);
warmup_iterations      = get_opt(options, 'warmup_iterations', 3);

pixel_size_angstroms     = ctf_params.pixel_size_angstroms;
wavelength_angstroms     = ctf_params.wavelength_angstroms;
spherical_aberration_mm  = ctf_params.spherical_aberration_mm;
amplitude_contrast       = ctf_params.amplitude_contrast;
tilt_angle_degrees       = ctf_params.tilt_angle_degrees;

vt = get_opt(options, 'verbose_timing', false);

% Pre-compute FFTs of data and reference tiles
t_fft_pre = tic;
fourier_handle = fourierTransformer(randn(CTFSIZE, 'single', 'gpuArray'));

data_fourier_transforms = cell(n_particles, 1);
reference_fourier_transforms = cell(n_particles, 1);

for i = 1:n_particles
    data_fourier_transforms{i} = fourier_handle.swapPhase( ...
        fourier_handle.fwdFFT(data_tiles{i}, 1, 1, [1e-5, 400, lowpass_cutoff, pixel_size_angstroms]), 'fwd');
    data_fourier_transforms{i} = data_fourier_transforms{i} ./ ...
        sqrt(2 * sum(abs(data_fourier_transforms{i}(1:end-fourier_handle.invTrim,:)).^2, 'all'));

    reference_fourier_transforms{i} = conj( ...
        fourier_handle.fwdFFT(ref_tiles{i}, 1, 1, [1e-5, 400, lowpass_cutoff, pixel_size_angstroms]));
end

% Compute peak mask
peak_mask = compute_peak_mask(CTFSIZE, get_opt(options, 'peak_search_radius', floor(CTFSIZE./4)));
if vt, fprintf('      [T] FFT precompute (%d particles): %.3f s\n', n_particles, toc(t_fft_pre)); end

% Initialize ADAM parameter vector:
%   [delta_defocus_tilt, delta_half_astigmatism, delta_astigmatism_angle, delta_z(1..N)]
n_params = 3 + n_particles;
initial_params = zeros(n_params, 1);
optimizer = adamOptimizer(initial_params);

% Per-parameter bounds
maximum_xy_shift = max(get_opt(options, 'maximum_xy_shift', 10));
z_offset_bound = get_opt(options, 'z_offset_bound_factor', 5) * maximum_xy_shift * pixel_size_angstroms;
astigmatism_angle_range = get_opt(options, 'astigmatism_angle_range', pi/4);
% ADAM bounds: astigmatism angle uses pi/2 (widest); per-particle adaptive
% clamping inside evaluate_score_and_shifts applies the actual constraint
lower_bounds = [-defocus_search_range; -defocus_search_range/2; -pi/2; -z_offset_bound * ones(n_particles, 1)];
upper_bounds = [ defocus_search_range;  defocus_search_range/2;  pi/2;  z_offset_bound * ones(n_particles, 1)];
optimizer.set_bounds(lower_bounds, upper_bounds);

% Scale learning rates from parameter bounds and iteration budget
% auto_scale_learning_rate computes: lr = safety_factor * expected_range / n_iterations
expected_ranges = zeros(n_params, 1);
expected_ranges(1) = defocus_search_range;            % defocus tilt (A)
expected_ranges(2) = defocus_search_range / 2;        % half astigmatism (A)
expected_ranges(3) = pi/2;                              % astigmatism angle (rad) — widened, adaptive per-particle clamping applies
expected_ranges(4:end) = z_offset_bound;              % delta_z per particle (A)
optimizer.auto_scale_learning_rate(expected_ranges, maximum_iterations, 3);

% Finite difference step sizes: ~1% of expected range
finite_difference_step = zeros(n_params, 1);
finite_difference_step(1) = max(10, defocus_search_range / 100);
finite_difference_step(2) = max(5, defocus_search_range / 200);
finite_difference_step(3) = max(0.005, astigmatism_angle_range / 50);
finite_difference_step(4:end) = max(1, z_offset_bound / 100);

% Store shifts (measured from CC peak, not optimized)
current_shifts = initial_shifts;
per_particle_scores = zeros(n_particles, 1);
score_history = [];

for iteration = 1:maximum_iterations
    t_iter = tic;
    params = optimizer.get_current_parameters();

    % Determine which parameters to optimize this iteration
    if iteration <= warmup_iterations
        active_indices = 1:3; % Only per-tilt params during warmup
    else
        active_indices = 1:n_params;
    end

    % Evaluate score at current parameters and measure shifts
    t_score = tic;
    [total_score, per_particle_scores, current_shifts] = evaluate_score_and_shifts( ...
        params, data_fourier_transforms, reference_fourier_transforms, ctf_params, ...
        fourier_handle, CTFSIZE, pixel_size_angstroms, wavelength_angstroms, ...
        spherical_aberration_mm, amplitude_contrast, tilt_angle_degrees, ...
        use_phase_compensated_correlation, peak_mask, upsample_factor, upsample_window, n_particles, ...
            defocus_search_range, astigmatism_angle_range);
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

    % Check convergence (require at least warmup + 3 full iterations)
    min_iterations = warmup_iterations + 3;
    converged_flag = (iteration >= min_iterations) && optimizer.has_converged(3, 0.001);
    fprintf('    iter %2d: score=%.6f, converged=%d\n', iteration, total_score, converged_flag);
    if converged_flag
        break;
    end

    % Monitor for score regression (after warmup)
    score_trend = monitor_score_trend(score_history);
    if score_trend.is_regressing && iteration > warmup_iterations
        warning('EMC_refine_tilt_ctf:scoreRegression', ...
            'Score regression detected at iteration %d (slope=%.4g)', ...
            iteration, score_trend.slope);
    end

    % Compute gradients via central finite differences
    t_grad = tic;
    gradient = zeros(n_params, 1);
    for parameter_index = active_indices
        params_plus = params;
        params_plus(parameter_index) = params_plus(parameter_index) + finite_difference_step(parameter_index);

        params_minus = params;
        params_minus(parameter_index) = params_minus(parameter_index) - finite_difference_step(parameter_index);

        [score_plus, ~, ~] = evaluate_score_and_shifts( ...
            params_plus, data_fourier_transforms, reference_fourier_transforms, ctf_params, ...
            fourier_handle, CTFSIZE, pixel_size_angstroms, wavelength_angstroms, ...
            spherical_aberration_mm, amplitude_contrast, tilt_angle_degrees, ...
            use_phase_compensated_correlation, peak_mask, upsample_factor, upsample_window, n_particles, ...
            defocus_search_range, astigmatism_angle_range);

        [score_minus, ~, ~] = evaluate_score_and_shifts( ...
            params_minus, data_fourier_transforms, reference_fourier_transforms, ctf_params, ...
            fourier_handle, CTFSIZE, pixel_size_angstroms, wavelength_angstroms, ...
            spherical_aberration_mm, amplitude_contrast, tilt_angle_degrees, ...
            use_phase_compensated_correlation, peak_mask, upsample_factor, upsample_window, n_particles, ...
            defocus_search_range, astigmatism_angle_range);

        % Negative gradient because ADAM minimizes but we want to maximize score
        gradient(parameter_index) = -(score_plus - score_minus) / (2 * finite_difference_step(parameter_index));
    end

    t_grad_elapsed = toc(t_grad);
    optimizer.update(gradient);
    if vt
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
    use_phase_compensated_correlation, peak_mask, upsample_factor, upsample_window, n_particles, ...
            defocus_search_range, astigmatism_angle_range);

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
    use_phase_compensated_correlation, peak_mask, upsample_factor, upsample_window, n_particles, ...
    defocus_search_range, astigmatism_angle_range)
% Evaluate the total CC score and measure per-particle X/Y shifts from CC peaks.

delta_defocus_tilt       = params(1);
delta_half_astigmatism   = params(2);
delta_astigmatism_angle  = params(3);
delta_z                  = params(4:end);

per_particle_scores = zeros(n_particles, 1, 'gpuArray');
shifts = zeros(n_particles, 2);

for i = 1:n_particles
    % Effective defocus for this particle
    dz_contribution = delta_z(i) * cosd(tilt_angle_degrees);
    effective_defocus_mean = ctf_params.defocus_mean(i) + delta_defocus_tilt + dz_contribution;
    effective_half_astig = ctf_params.half_astigmatism(i) + delta_half_astigmatism;

    effective_defocus_1 = effective_defocus_mean + effective_half_astig;
    effective_defocus_2 = effective_defocus_mean - effective_half_astig;

    % Adaptive astigmatism angle constraint (per-particle)
    % When |half_astig/defocus_mean| is small, angle is poorly defined → allow full pi/2
    % When ratio >= 5% of defocus, angle is well-constrained → use tighter range
    astig_fraction = abs(effective_half_astig) / max(abs(effective_defocus_mean), 1);
    effective_angle_range = pi/2 - (pi/2 - astigmatism_angle_range) * min(astig_fraction / 0.05, 1);
    clamped_delta_angle = max(-effective_angle_range, min(delta_astigmatism_angle, effective_angle_range));
    effective_astigmatism_angle = ctf_params.astigmatism_angle(i) + clamped_delta_angle;

    % Enforce df1 >= df2. If violated, swap and rotate angle by pi/2
    % (physically equivalent CTF). Penalty pushes optimizer away from boundary.
    df_ordering_penalty = 0;
    if effective_defocus_2 > effective_defocus_1
        tmp = effective_defocus_1;
        effective_defocus_1 = effective_defocus_2;
        effective_defocus_2 = tmp;
        effective_astigmatism_angle = effective_astigmatism_angle + pi/2;
        df_ordering_penalty = (effective_defocus_1 - effective_defocus_2) / max(defocus_search_range, 1);
    end

    % Compute CTF via mexCTF
    ctf_image = mexCTF(true, false, int16(CTFSIZE(1)), int16(CTFSIZE(2)), ...
        single(pixel_size_angstroms), single(wavelength_angstroms), single(spherical_aberration_mm), ...
        single(effective_defocus_1), single(effective_defocus_2), single(effective_astigmatism_angle), ...
        single(amplitude_contrast));

    % Apply CTF to reference and normalize
    reference_with_ctf = reference_fourier_transforms{i} .* ctf_image;
    ref_norm = sqrt(2 * sum(abs(reference_with_ctf(1:end-fourier_handle.invTrim,:)).^2, 'all'));
    % REVERT_NAN_DEBUG: check for zero/NaN norm before dividing
    if ~isfinite(ref_norm) || ref_norm == 0
        fprintf('  [NAN_DEBUG] particle %d: ref_norm=%.6g (df1=%.1f df2=%.1f ast=%.4f)\n', ...
            i, ref_norm, effective_defocus_1, effective_defocus_2, effective_astigmatism_angle);
        fprintf('  [NAN_DEBUG] ctf_image: min=%.6g max=%.6g nNaN=%d nInf=%d\n', ...
            gather(min(ctf_image(:))), gather(max(ctf_image(:))), ...
            gather(sum(isnan(ctf_image(:)))), gather(sum(isinf(ctf_image(:)))));
        fprintf('  [NAN_DEBUG] ref_ft: min=%.6g max=%.6g nNaN=%d\n', ...
            gather(min(abs(reference_fourier_transforms{i}(:)))), ...
            gather(max(abs(reference_fourier_transforms{i}(:)))), ...
            gather(sum(isnan(reference_fourier_transforms{i}(:)))));
    end
    reference_with_ctf = reference_with_ctf ./ ref_norm;

    % Cross-correlate
    cross_correlation_map = data_fourier_transforms{i} .* reference_with_ctf;
    if use_phase_compensated_correlation
        % Phase-compensated XCF: modifies CC modulus to sharpen translational
        % peak (Saxton, 1994, Eq. 14). Multiplies CC by itself / |CC| to
        % enhance signal while regularizing near-zero amplitudes.
        cross_correlation_map = cross_correlation_map .* cross_correlation_map ./ (abs(cross_correlation_map) + 0.001);
    end
    cross_correlation_map = peak_mask .* real(fourier_handle.invFFT(cross_correlation_map));

    % Find peak (with optional Fourier upsampling)
    if upsample_factor > 1
      [peak_height, peak_position] = fourier_upsample_peak(cross_correlation_map, upsample_factor, upsample_window);
    else
      [peak_height, max_idx] = max(cross_correlation_map(:));
      [px, py] = ind2sub(size(cross_correlation_map), max_idx);
      peak_position = [px, py];
    end

    % Convert from image coordinates to shift relative to origin
    origin = emc_get_origin_index(CTFSIZE);
    shift_from_origin = peak_position - origin;

    per_particle_scores(i) = peak_height - df_ordering_penalty;
    shifts(i,:) = gather(shift_from_origin);
end

total_score = gather(sum(per_particle_scores));
per_particle_scores = gather(per_particle_scores);

end


function [peak_height, peak_position] = fourier_upsample_peak(cross_correlation_map, upsample_factor, upsample_window)
% Find sub-pixel peak position using Fourier upsampling with mirror padding.
%
% 1. Find coarse peak via max
% 2. Extract window around peak (with wrapping)
% 3. Mirror-pad for continuous periodic signal
% 4. FFT, zero-pad in Fourier space, inverse FFT
% 5. Find sub-pixel peak in upsampled map

[~, max_index] = max(cross_correlation_map(:));
[coarse_peak_x, coarse_peak_y] = ind2sub(size(cross_correlation_map), max_index);
map_size = size(cross_correlation_map);

% Extract window around peak, handling boundary wrap
half_width = upsample_window;
window_size = 2 * half_width + 1;
window = zeros(window_size, window_size, 'like', cross_correlation_map);

for delta_i = -half_width:half_width
    for delta_j = -half_width:half_width
        wrapped_i = mod(coarse_peak_x - 1 + delta_i, map_size(1)) + 1;
        wrapped_j = mod(coarse_peak_y - 1 + delta_j, map_size(2)) + 1;
        window(delta_i + half_width + 1, delta_j + half_width + 1) = cross_correlation_map(wrapped_i, wrapped_j);
    end
end

% Mirror-pad: [x(end:-1:2), x, x(end-1:-1:1)] in each dimension
mirror_rows = [window(end:-1:2, :); window; window(end-1:-1:1, :)];
mirror_both = [mirror_rows(:, end:-1:2), mirror_rows, mirror_rows(:, end-1:-1:1)];

% Get nice FFT size
padded_size = BH_multi_iterator(size(mirror_both), 'fourier2d');

% Pad mirror signal to nice FFT size if needed
if any(padded_size ~= size(mirror_both))
    padded_mirror = zeros(padded_size, 'like', cross_correlation_map);
    padded_mirror(1:size(mirror_both,1), 1:size(mirror_both,2)) = mirror_both;
    mirror_both = padded_mirror;
end

% FFT
fourier_coefficients = fft2(mirror_both);

% Zero-pad in Fourier space for upsampling
upsampled_size = padded_size * upsample_factor;
fourier_upsampled = zeros(upsampled_size, 'like', fourier_coefficients);

% Copy low frequencies to the upsampled Fourier array
half_freq_x = floor(padded_size(1) / 2);
half_freq_y = floor(padded_size(2) / 2);

fourier_upsampled(1:half_freq_x, 1:half_freq_y) = fourier_coefficients(1:half_freq_x, 1:half_freq_y);
fourier_upsampled(1:half_freq_x, end-half_freq_y+1:end) = fourier_coefficients(1:half_freq_x, end-half_freq_y+1:end);
fourier_upsampled(end-half_freq_x+1:end, 1:half_freq_y) = fourier_coefficients(end-half_freq_x+1:end, 1:half_freq_y);
fourier_upsampled(end-half_freq_x+1:end, end-half_freq_y+1:end) = fourier_coefficients(end-half_freq_x+1:end, end-half_freq_y+1:end);

% Inverse FFT and scale
upsampled_map = real(ifft2(fourier_upsampled)) * (upsample_factor^2);

% Find peak in original window region only (exclude mirror padding)
mirror_offset = window_size - 1;
orig_start_x = mirror_offset * upsample_factor + 1;
orig_start_y = mirror_offset * upsample_factor + 1;
region_len = window_size * upsample_factor;

upsampled_region = upsampled_map(orig_start_x:orig_start_x + region_len - 1, ...
                                 orig_start_y:orig_start_y + region_len - 1);
[peak_height, region_peak_index] = max(upsampled_region(:));
[region_peak_x, region_peak_y] = ind2sub(size(upsampled_region), region_peak_index);

% Sub-pixel offset: window center in region is at (half_width * upsample_factor + 1)
subpixel_offset_x = (region_peak_x - 1 - half_width * upsample_factor) / upsample_factor;
subpixel_offset_y = (region_peak_y - 1 - half_width * upsample_factor) / upsample_factor;

% Peak position in original map coordinates
peak_position = [coarse_peak_x + subpixel_offset_x, coarse_peak_y + subpixel_offset_y];

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
