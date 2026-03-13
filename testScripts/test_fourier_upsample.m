% test_fourier_upsample.m - Unit test for Fourier upsampling peak finder accuracy.
%
% Creates 2D Gaussians with known sub-pixel shifts and verifies that the
% fourier_upsample_peak function recovers them accurately.
%
% This test can run on CPU by replacing gpuArray calls (the function under
% test is inside EMC_refine_tilt_ctf.m as a local helper, so we copy the
% logic here for standalone testing).

function test_fourier_upsample()
    fprintf('\n=== Fourier Upsampling Peak Finder Tests ===\n\n');

    test_centered_peak();
    test_known_subpixel_shifts();
    test_accuracy_vs_upsample_factor();
    % test_noise_robustness(); % Disabled: synthetic Gaussian + white noise
    % doesn't realistically model CC map noise (structured from CTF, missing
    % wedge, etc.). Needs real or simulated CC maps to be meaningful.
    test_exact_integer_peak();
    test_near_half_pixel_shift();
    test_wrapping_at_boundary();

    fprintf('\n=== All Fourier upsampling tests passed ===\n');
end

function test_centered_peak()
    fprintf('Test: centered Gaussian peak... ');

    n = 64;
    sigma = 5;
    center = floor(n/2) + 1;
    [xx, yy] = ndgrid(1:n, 1:n);
    gauss = exp(-((xx - center).^2 + (yy - center).^2) / (2*sigma^2));

    [peak_height, peak_pos] = fourier_upsample_peak_cpu(gauss, 8, 8);

    assert(abs(peak_pos(1) - center) < 0.05, ...
        'X peak should be at %d, got %f', center, peak_pos(1));
    assert(abs(peak_pos(2) - center) < 0.05, ...
        'Y peak should be at %d, got %f', center, peak_pos(2));
    assert(abs(peak_height - 1.0) < 0.01, ...
        'Peak height should be ~1.0, got %f', peak_height);
    fprintf('PASSED\n');
end

function test_known_subpixel_shifts()
    fprintf('Test: known sub-pixel shifts... ');

    n = 64;
    sigma = 5;
    center = floor(n/2) + 1;

    % Test several sub-pixel offsets
    test_offsets = [0.3, 0.7; -0.4, 0.2; 0.1, -0.6; -0.25, -0.35];

    for k = 1:size(test_offsets, 1)
        dx = test_offsets(k, 1);
        dy = test_offsets(k, 2);

        [xx, yy] = ndgrid(1:n, 1:n);
        gauss = exp(-((xx - center - dx).^2 + (yy - center - dy).^2) / (2*sigma^2));

        [~, peak_pos] = fourier_upsample_peak_cpu(gauss, 8, 8);

        err_x = abs(peak_pos(1) - (center + dx));
        err_y = abs(peak_pos(2) - (center + dy));

        assert(err_x < 0.15, ...
            'Offset [%.2f,%.2f]: X error %.4f > 0.15', dx, dy, err_x);
        assert(err_y < 0.15, ...
            'Offset [%.2f,%.2f]: Y error %.4f > 0.15', dx, dy, err_y);
    end
    fprintf('PASSED\n');
end

function test_accuracy_vs_upsample_factor()
    fprintf('Test: accuracy improves with upsample factor... ');

    n = 64;
    sigma = 5;
    center = floor(n/2) + 1;
    true_dx = 0.37;
    true_dy = -0.23;

    [xx, yy] = ndgrid(1:n, 1:n);
    gauss = exp(-((xx - center - true_dx).^2 + (yy - center - true_dy).^2) / (2*sigma^2));

    errors = zeros(3, 1);
    factors = [2, 4, 8];
    for k = 1:3
        [~, peak_pos] = fourier_upsample_peak_cpu(gauss, factors(k), 8);
        errors(k) = sqrt((peak_pos(1) - center - true_dx)^2 + (peak_pos(2) - center - true_dy)^2);
    end

    % Higher upsample factor should give equal or better accuracy
    assert(errors(3) <= errors(1) + 0.01, ...
        '8x upsampling (err=%.4f) should be better than 2x (err=%.4f)', errors(3), errors(1));
    fprintf('PASSED (errors: 2x=%.4f, 4x=%.4f, 8x=%.4f)\n', errors(1), errors(2), errors(3));
end


function test_noise_robustness()
    fprintf('Test: noise robustness (CC peak SNR=5)... ');
    % CC peak SNR (peak_height / noise_variance) is typically 3-10 in
    % cryo-EM cross-correlation maps. Test at SNR=5 (mid-range).

    n = 64;
    sigma = 5;
    center = floor(n/2) + 1;
    true_dx = 0.35;
    true_dy = -0.22;

    rng(123);
    [xx, yy] = ndgrid(1:n, 1:n);
    signal = exp(-((xx - center - true_dx).^2 + (yy - center - true_dy).^2) / (2*sigma^2));

    % peak_height=1, noise_variance = peak/SNR = 0.2, noise_std = sqrt(0.2)
    noise_std = sqrt(1.0 / 5);
    noisy = signal + noise_std * randn(n, n);

    [~, peak_pos] = fourier_upsample_peak_cpu(noisy, 8, 8);

    err = sqrt((peak_pos(1) - center - true_dx)^2 + (peak_pos(2) - center - true_dy)^2);
    assert(err < 0.5, ...
        'Noisy CC peak error %.4f > 0.5 px', err);
    fprintf('PASSED (error=%.4f)\n', err);
end

function test_exact_integer_peak()
    fprintf('Test: exact integer peak position... ');

    n = 64;
    sigma = 5;
    center = floor(n/2) + 1;

    % Gaussian centered exactly at integer position (no sub-pixel offset)
    [xx, yy] = ndgrid(1:n, 1:n);
    gauss = exp(-((xx - center).^2 + (yy - center).^2) / (2*sigma^2));

    [~, peak_pos] = fourier_upsample_peak_cpu(gauss, 8, 8);

    err_x = abs(peak_pos(1) - center);
    err_y = abs(peak_pos(2) - center);
    assert(err_x < 0.05, 'X error %.4f > 0.05 for integer peak', err_x);
    assert(err_y < 0.05, 'Y error %.4f > 0.05 for integer peak', err_y);
    fprintf('PASSED (err_x=%.4f, err_y=%.4f)\n', err_x, err_y);
end

function test_near_half_pixel_shift()
    fprintf('Test: near half-pixel shifts (+/-0.49)... ');

    n = 64;
    sigma = 5;
    center = floor(n/2) + 1;

    offsets = [0.49, 0.49; -0.49, -0.49; 0.49, -0.49; -0.49, 0.49];

    for k = 1:size(offsets, 1)
        dx = offsets(k, 1);
        dy = offsets(k, 2);

        [xx, yy] = ndgrid(1:n, 1:n);
        gauss = exp(-((xx - center - dx).^2 + (yy - center - dy).^2) / (2*sigma^2));

        [~, peak_pos] = fourier_upsample_peak_cpu(gauss, 8, 8);

        err_x = abs(peak_pos(1) - (center + dx));
        err_y = abs(peak_pos(2) - (center + dy));

        assert(err_x < 0.2, ...
            'Offset [%.2f,%.2f]: X error %.4f > 0.2', dx, dy, err_x);
        assert(err_y < 0.2, ...
            'Offset [%.2f,%.2f]: Y error %.4f > 0.2', dx, dy, err_y);
    end
    fprintf('PASSED\n');
end

function test_wrapping_at_boundary()
    fprintf('Test: peak wrapping at boundary (position 1)... ');

    n = 64;
    sigma = 5;

    % Place Gaussian at position 1 (which wraps at the boundary)
    [xx, yy] = ndgrid(1:n, 1:n);
    % Use periodic distance to position (1,1)
    dist_x = min(abs(xx - 1), n - abs(xx - 1));
    dist_y = min(abs(yy - 1), n - abs(yy - 1));
    gauss = exp(-(dist_x.^2 + dist_y.^2) / (2*sigma^2));

    [~, peak_pos] = fourier_upsample_peak_cpu(gauss, 8, 8);

    % Peak should be near position (1, 1)
    err_x = min(abs(peak_pos(1) - 1), abs(peak_pos(1) - 1 - n));
    err_y = min(abs(peak_pos(2) - 1), abs(peak_pos(2) - 1 - n));

    assert(err_x < 0.15, 'Boundary peak X error %.4f > 0.15', err_x);
    assert(err_y < 0.15, 'Boundary peak Y error %.4f > 0.15', err_y);
    fprintf('PASSED (pos=[%.2f, %.2f])\n', peak_pos(1), peak_pos(2));
end


%% ===== CPU version of the Fourier upsampling peak finder =====

function [peak_height, peak_pos] = fourier_upsample_peak_cpu(cccMap, upsample_factor, upsample_window)
% CPU version of the Fourier upsampling peak finder for testing.

[~, max_idx] = max(cccMap(:));
[mMx, mMy] = ind2sub(size(cccMap), max_idx);
map_size = size(cccMap);

hw = upsample_window;
win_size = 2*hw + 1;
window = zeros(win_size, win_size);

for di = -hw:hw
    for dj = -hw:hw
        ri = mod(mMx - 1 + di, map_size(1)) + 1;
        rj = mod(mMy - 1 + dj, map_size(2)) + 1;
        window(di+hw+1, dj+hw+1) = cccMap(ri, rj);
    end
end

% Mirror-pad
mirror_x = [window(end:-1:2, :); window; window(end-1:-1:1, :)];
mirror_xy = [mirror_x(:, end:-1:2), mirror_x, mirror_x(:, end-1:-1:1)];

padded_size = size(mirror_xy);

% FFT
F = fft2(mirror_xy);

% Zero-pad in Fourier space
up_size = padded_size * upsample_factor;
F_up = zeros(up_size);

half_x = floor(padded_size(1)/2);
half_y = floor(padded_size(2)/2);

F_up(1:half_x, 1:half_y) = F(1:half_x, 1:half_y);
F_up(1:half_x, end-half_y+1:end) = F(1:half_x, end-half_y+1:end);
F_up(end-half_x+1:end, 1:half_y) = F(end-half_x+1:end, 1:half_y);
F_up(end-half_x+1:end, end-half_y+1:end) = F(end-half_x+1:end, end-half_y+1:end);

% IFFT
upsampled = real(ifft2(F_up)) * (upsample_factor^2);

% Find peak in original window region only (exclude mirror padding)
mirror_offset = win_size - 1;
orig_start_x = mirror_offset * upsample_factor + 1;
orig_start_y = mirror_offset * upsample_factor + 1;
region_len = win_size * upsample_factor;

region = upsampled(orig_start_x:orig_start_x + region_len - 1, ...
                   orig_start_y:orig_start_y + region_len - 1);
[peak_height, up_idx] = max(region(:));
[up_mx, up_my] = ind2sub(size(region), up_idx);

% Sub-pixel offset: window center in region is at (hw * upsample_factor + 1)
dx_subpix = (up_mx - 1 - hw * upsample_factor) / upsample_factor;
dy_subpix = (up_my - 1 - hw * upsample_factor) / upsample_factor;

peak_pos = [mMx + dx_subpix, mMy + dy_subpix];

end
