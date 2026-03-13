% test_ctf_refine_roundtrip.m - Roundtrip and regression tests for CTF refinement.
%
% Tests cover:
% 1. Star file parse -> write -> re-parse roundtrip (columns survive intact)
% 2. cos^alpha regression: synthetic (angle, score) pairs with known alpha
%
% BEHAVIORS TO WATCH:
%   - ADAM score_history should increase monotonically after warmup; oscillation = lr too high
%   - delta_z should cluster near 0; bimodal = sign error
%   - Defocus corrections > 2000 A = failed refinement or wrong conventions
%   - GPU memory with >500 particles per tilt group

function test_ctf_refine_roundtrip()
    fprintf('\n=== CTF Refine Roundtrip Tests ===\n\n');

    test_star_file_roundtrip();
    test_cos_alpha_regression();

    fprintf('\n=== All CTF refine roundtrip tests passed ===\n');
end


function test_star_file_roundtrip()
    fprintf('Test: star file parse -> write -> re-parse roundtrip... ');

    % Create a temporary star file with known content
    tmp_dir = '/tmp/claude_cache';
    if ~exist(tmp_dir, 'dir')
        mkdir(tmp_dir);
    end

    input_path = fullfile(tmp_dir, 'test_roundtrip_input.star');
    output_path = fullfile(tmp_dir, 'test_roundtrip_output.star');

    % Write a minimal star file with header and 3 particle lines
    fh = fopen(input_path, 'w');
    assert(fh ~= -1, 'Cannot create temp star file');

    % Header
    fprintf(fh, '\n');
    fprintf(fh, 'data_\n');
    fprintf(fh, 'loop_\n');
    fprintf(fh, '_cisTEMPositionInStack #1\n');
    fprintf(fh, '_cisTEMAnglePsi #2\n');
    fprintf(fh, '_cisTEMAngleTheta #3\n');
    fprintf(fh, '_cisTEMAnglePhi #4\n');
    fprintf(fh, '_cisTEMXShift #5\n');
    fprintf(fh, '_cisTEMYShift #6\n');
    fprintf(fh, '_cisTEMDefocus1 #7\n');
    fprintf(fh, '_cisTEMDefocus2 #8\n');
    fprintf(fh, '_cisTEMDefocusAngle #9\n');
    fprintf(fh, '_cisTEMPhaseShift #10\n');
    fprintf(fh, '_cisTEMOccupancy #11\n');
    fprintf(fh, '_cisTEMLogP #12\n');
    fprintf(fh, '_cisTEMSigma #13\n');
    fprintf(fh, '_cisTEMScore #14\n');
    fprintf(fh, '_cisTEMScoreChange #15\n');
    fprintf(fh, '_cisTEMPixelSize #16\n');
    fprintf(fh, '_cisTEMVoltage #17\n');
    fprintf(fh, '_cisTEMCs #18\n');
    fprintf(fh, '_cisTEMAmplitudeContrast #19\n');
    fprintf(fh, '_cisTEMBeamTiltX #20\n');
    fprintf(fh, '_cisTEMBeamTiltY #21\n');
    fprintf(fh, '_cisTEMImageShiftX #22\n');
    fprintf(fh, '_cisTEMImageShiftY #23\n');
    fprintf(fh, '_cisTEMBest2DClass #24\n');
    fprintf(fh, '_cisTEMBeamTiltGroup #25\n');
    fprintf(fh, '_cisTEMParticleGroup #26\n');
    fprintf(fh, '_cisTEMPreExposure #27\n');
    fprintf(fh, '_cisTEMTotalExposure #28\n');
    fprintf(fh, '_cisTEMOriginalImageFilename #29\n');
    fprintf(fh, '_cisTEMOriginalXPosition #30\n');

    % 3 particles with distinct values
    particles_data = {
        1, 10.5, 20.3, 30.1, 1.5, -2.3, 15000.0, 14500.0, 45.0, 0.0, 100, -500.0, 1.0, 0.85, 0.01, 1.34, 300.0, 2.7, 0.07, 0.0, 0.0, 0.0, 0.0, 1, 1, 1, 0.0, 3.0, 'tilt001.mrc', 0.0;
        2, 15.2, 25.4, 35.6, 0.8, -1.1, 16000.0, 15500.0, 50.0, 0.0, 100, -450.0, 1.0, 0.90, 0.02, 1.34, 300.0, 2.7, 0.07, 0.0, 0.0, 0.0, 0.0, 1, 1, 1, 0.0, 3.0, 'tilt001.mrc', 0.0;
        3, 20.0, 30.5, 40.2, -0.5, 0.7, 17000.0, 16500.0, 55.0, 0.0, 100, -400.0, 1.0, 0.88, 0.03, 1.34, 300.0, 2.7, 0.07, 0.0, 0.0, 0.0, 0.0, 1, 1, 1, 0.0, 3.0, 'tilt001.mrc', 15.0;
    };

    for i = 1:3
        d = particles_data(i, :);
        fprintf(fh, '%d %f %f %f %f %f %f %f %f %f %d %f %f %f %f %f %f %f %f %f %f %f %f %d %d %d %f %f %s %f\n', ...
            d{1}, d{2}, d{3}, d{4}, d{5}, d{6}, d{7}, d{8}, d{9}, d{10}, ...
            d{11}, d{12}, d{13}, d{14}, d{15}, d{16}, d{17}, d{18}, d{19}, ...
            d{20}, d{21}, d{22}, d{23}, d{24}, d{25}, d{26}, d{27}, d{28}, d{29}, d{30});
    end
    fclose(fh);

    % Parse the star file using the same parser
    [particles, header_lines] = parse_star_file_test(input_path);
    assert(length(particles) == 3, 'Expected 3 particles, got %d', length(particles));

    % Verify key fields survived parsing
    assert(abs(particles(1).psi - 10.5) < 0.01, 'Particle 1 psi mismatch');
    assert(abs(particles(2).defocus_1 - 16000.0) < 0.1, 'Particle 2 defocus_1 mismatch');
    assert(abs(particles(3).tilt_angle - 15.0) < 0.01, 'Particle 3 tilt_angle mismatch');
    assert(strcmp(particles(1).original_image_filename, 'tilt001.mrc'), ...
        'Particle 1 filename mismatch');

    % Write refined star file (use identity refinement = same values)
    n = length(particles);
    refined_df1 = arrayfun(@(p) p.defocus_1, particles(:));
    refined_df2 = arrayfun(@(p) p.defocus_2, particles(:));
    refined_ast = arrayfun(@(p) p.defocus_angle, particles(:));
    refined_sx = arrayfun(@(p) p.x_shift, particles(:));
    refined_sy = arrayfun(@(p) p.y_shift, particles(:));
    refined_scores = arrayfun(@(p) p.score, particles(:));
    refined_occ = 100 * ones(n, 1);

    write_refined_star_file_test(input_path, output_path, particles, ...
        refined_df1, refined_df2, refined_ast, refined_sx, refined_sy, ...
        refined_scores, refined_occ);

    % Re-parse the output
    [particles_out, ~] = parse_star_file_test(output_path);
    assert(length(particles_out) == 3, 'Output should have 3 particles, got %d', length(particles_out));

    % Verify columns survived roundtrip
    for i = 1:3
        assert(particles_out(i).position_in_stack == particles(i).position_in_stack, ...
            'Particle %d: position_in_stack mismatch', i);
        assert(abs(particles_out(i).psi - particles(i).psi) < 0.01, ...
            'Particle %d: psi mismatch', i);
        assert(abs(particles_out(i).theta - particles(i).theta) < 0.01, ...
            'Particle %d: theta mismatch', i);
        assert(abs(particles_out(i).defocus_1 - particles(i).defocus_1) < 1.0, ...
            'Particle %d: defocus_1 mismatch (%.1f vs %.1f)', i, ...
            particles_out(i).defocus_1, particles(i).defocus_1);
        assert(strcmp(particles_out(i).original_image_filename, particles(i).original_image_filename), ...
            'Particle %d: filename mismatch', i);
        assert(abs(particles_out(i).tilt_angle - particles(i).tilt_angle) < 0.01, ...
            'Particle %d: tilt_angle mismatch', i);
    end

    % Cleanup temp files
    delete(input_path);
    delete(output_path);

    fprintf('PASSED\n');
end


function test_cos_alpha_regression()
    fprintf('Test: cos^alpha regression recovery... ');

    % Generate synthetic (angle, score) pairs with known alpha
    true_alpha = 1.5;
    baseline_score = 100.0;
    angles_deg = [10, 20, 30, 40, 50, 60];

    scores = baseline_score * cosd(angles_deg) .^ true_alpha;

    % Run the same regression as in EMC_ctf_refine_from_star
    angles_rad = angles_deg * pi / 180;
    log_ratio = log(scores / baseline_score);
    log_cos = log(cos(angles_rad));
    valid = isfinite(log_ratio) & isfinite(log_cos) & log_cos ~= 0;

    % Correct regression: log_ratio = alpha * log_cos, solve for alpha
    % Using MATLAB \ operator: log_cos \ log_ratio
    alpha_fit = log_cos(valid)' \ log_ratio(valid)';

    err = abs(alpha_fit - true_alpha) / true_alpha;
    assert(err < 0.10, ...
        'Alpha recovery error %.2f%% > 10%% (fitted=%.4f, true=%.4f)', ...
        err*100, alpha_fit, true_alpha);

    % Also test with noisy scores
    rng(42);
    noisy_scores = scores .* (1 + 0.05 * randn(size(scores)));
    log_ratio_noisy = log(noisy_scores / baseline_score);
    valid_noisy = isfinite(log_ratio_noisy) & isfinite(log_cos) & log_cos ~= 0;
    alpha_fit_noisy = log_cos(valid_noisy)' \ log_ratio_noisy(valid_noisy)';

    err_noisy = abs(alpha_fit_noisy - true_alpha) / true_alpha;
    assert(err_noisy < 0.10, ...
        'Noisy alpha recovery error %.2f%% > 10%% (fitted=%.4f, true=%.4f)', ...
        err_noisy*100, alpha_fit_noisy, true_alpha);

    fprintf('PASSED (exact=%.4f, noisy=%.4f, true=%.4f)\n', alpha_fit, alpha_fit_noisy, true_alpha);
end


%% ===== Local copies of parse/write functions for standalone testing =====

function [particles, header_lines] = parse_star_file_test(path)
% Parse a 30-column star file into a struct array.
% (Copy of the parser from EMC_ctf_refine_from_star.m for standalone testing)
  fh = fopen(path, 'r');
  if fh == -1
    error('Cannot open star file: %s', path);
  end

  header_lines = {};
  data_lines = {};

  while ~feof(fh)
    line = fgetl(fh);
    if isempty(strtrim(line))
      header_lines{end+1} = line; %#ok<AGROW>
      continue;
    end
    first_char = strtrim(line);
    first_char = first_char(1);
    if first_char == '#' || first_char == '_' || ...
        startsWith(strtrim(line), 'data_') || startsWith(strtrim(line), 'loop_')
      header_lines{end+1} = line; %#ok<AGROW>
    else
      data_lines{end+1} = line; %#ok<AGROW>
    end
  end
  fclose(fh);

  n = length(data_lines);
  particles = struct('position_in_stack', cell(1,n), ...
      'psi', cell(1,n), 'theta', cell(1,n), 'phi', cell(1,n), ...
      'x_shift', cell(1,n), 'y_shift', cell(1,n), ...
      'defocus_1', cell(1,n), 'defocus_2', cell(1,n), 'defocus_angle', cell(1,n), ...
      'phase_shift', cell(1,n), 'occupancy', cell(1,n), ...
      'logp', cell(1,n), 'sigma', cell(1,n), 'score', cell(1,n), ...
      'score_change', cell(1,n), 'pixel_size', cell(1,n), ...
      'voltage_kv', cell(1,n), 'cs_mm', cell(1,n), 'amplitude_contrast', cell(1,n), ...
      'beam_tilt_x', cell(1,n), 'beam_tilt_y', cell(1,n), ...
      'image_shift_x', cell(1,n), 'image_shift_y', cell(1,n), ...
      'best_2d_class', cell(1,n), 'beam_tilt_group', cell(1,n), ...
      'particle_group', cell(1,n), 'pre_exposure', cell(1,n), ...
      'total_exposure', cell(1,n), ...
      'original_image_filename', cell(1,n), 'tilt_angle', cell(1,n));

  for i = 1:n
    tokens = strsplit(strtrim(data_lines{i}));
    if length(tokens) < 29
      error('Star file line %d has only %d tokens (expected >= 29)', i, length(tokens));
    end

    particles(i).position_in_stack = str2double(tokens{1});
    particles(i).psi = str2double(tokens{2});
    particles(i).theta = str2double(tokens{3});
    particles(i).phi = str2double(tokens{4});
    particles(i).x_shift = str2double(tokens{5});
    particles(i).y_shift = str2double(tokens{6});
    particles(i).defocus_1 = str2double(tokens{7});
    particles(i).defocus_2 = str2double(tokens{8});
    particles(i).defocus_angle = str2double(tokens{9});
    particles(i).phase_shift = str2double(tokens{10});
    particles(i).occupancy = str2double(tokens{11});
    particles(i).logp = str2double(tokens{12});
    particles(i).sigma = str2double(tokens{13});
    particles(i).score = str2double(tokens{14});
    particles(i).score_change = str2double(tokens{15});
    particles(i).pixel_size = str2double(tokens{16});
    particles(i).voltage_kv = str2double(tokens{17});
    particles(i).cs_mm = str2double(tokens{18});
    particles(i).amplitude_contrast = str2double(tokens{19});
    particles(i).beam_tilt_x = str2double(tokens{20});
    particles(i).beam_tilt_y = str2double(tokens{21});
    particles(i).image_shift_x = str2double(tokens{22});
    particles(i).image_shift_y = str2double(tokens{23});
    particles(i).best_2d_class = str2double(tokens{24});
    particles(i).beam_tilt_group = str2double(tokens{25});
    particles(i).particle_group = str2double(tokens{26});
    particles(i).pre_exposure = str2double(tokens{27});
    particles(i).total_exposure = str2double(tokens{28});
    particles(i).original_image_filename = tokens{29};

    if length(tokens) >= 30
      particles(i).tilt_angle = str2double(tokens{30});
    else
      particles(i).tilt_angle = 0;
    end
  end
end


function write_refined_star_file_test(input_path, output_path, particles, ...
    refined_df1, refined_df2, refined_ast_angle, ...
    refined_sx, refined_sy, refined_scores, refined_occ)
% Write refined star file by reading original and replacing refined columns.
% (Copy from EMC_ctf_refine_from_star.m with bug #4 fix for standalone testing)

  fh_in = fopen(input_path, 'r');
  if fh_in == -1
    error('Cannot open input star file for reading: %s', input_path);
  end
  fh_out = fopen(output_path, 'w');
  if fh_out == -1
    fclose(fh_in);
    error('Cannot open output star file for writing: %s', output_path);
  end

  particle_idx = 0;

  while ~feof(fh_in)
    line = fgetl(fh_in);
    if line == -1
      break;
    end

    trimmed = strtrim(line);
    if isempty(trimmed)
      fprintf(fh_out, '%s\n', line);
      continue;
    end

    % Check if this is a data line (starts with a number)
    first_char = trimmed(1);
    if first_char >= '0' && first_char <= '9'
      tokens = strsplit(trimmed);
      stack_pos = str2double(tokens{1});
      if ~isnan(stack_pos) && stack_pos >= 1 && particle_idx < length(refined_df1)
        particle_idx = particle_idx + 1;

        % Replace columns 5-6 (shifts), 7-9 (defocus), 11 (occupancy), 14 (score)
        tokens{5} = sprintf('%9.2f', refined_sx(particle_idx));
        tokens{6} = sprintf('%9.2f', refined_sy(particle_idx));
        tokens{7} = sprintf('%8.1f', refined_df1(particle_idx));
        tokens{8} = sprintf('%8.1f', refined_df2(particle_idx));
        tokens{9} = sprintf('%7.2f', refined_ast_angle(particle_idx));
        tokens{11} = sprintf('%5i', refined_occ(particle_idx));
        tokens{14} = sprintf('%10.4f', refined_scores(particle_idx));
        fprintf(fh_out, '%s\n', strjoin(tokens, ' '));
        continue;
      end
    end

    % Header or comment line - pass through unchanged
    fprintf(fh_out, '%s\n', line);
  end

  fclose(fh_in);
  fclose(fh_out);
end
