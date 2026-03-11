function compare_star_files(initial_star_path, refined_star_path)
% compare_star_files - Plot diagnostics comparing initial vs refined star files.
%
% Creates per-tilt histograms of defocus change, astigmatism change, and net shift,
% plus 3D scatter plots of particle coordinates color-coded by refinement changes.
%
% INPUTS:
%   initial_star_path - path to the initial star file (e.g. 'prefix_initial.star')
%   refined_star_path - path to the refined star file (e.g. 'prefix.star')

fprintf('Loading initial star file: %s\n', initial_star_path);
initial_data = read_star_data(initial_star_path);

fprintf('Loading refined star file: %s\n', refined_star_path);
refined_data = read_star_data(refined_star_path);

n_particles = size(initial_data, 1);
if size(refined_data, 1) ~= n_particles
    error('Star files have different numbers of records (%d vs %d)', ...
        n_particles, size(refined_data, 1));
end

% Extract relevant columns (cisTEM star file format)
% Columns: 1=pos, 2=psi, 3=theta, 4=phi, 5=shiftX, 6=shiftY, 7=df1, 8=df2, 9=dfAngle, 14=score
delta_defocus_1 = refined_data(:,7) - initial_data(:,7);
delta_defocus_2 = refined_data(:,8) - initial_data(:,8);
delta_defocus_mean = (delta_defocus_1 + delta_defocus_2) / 2;
delta_astigmatism = (delta_defocus_1 - delta_defocus_2) / 2 - (initial_data(:,7) - initial_data(:,8)) / 2;
delta_astigmatism_angle = refined_data(:,9) - initial_data(:,9);
delta_shift_x = refined_data(:,5) - initial_data(:,5);
delta_shift_y = refined_data(:,6) - initial_data(:,6);
net_shift = sqrt(delta_shift_x.^2 + delta_shift_y.^2);

% Get tilt group from original image filename (last column)
% We use the original image filename to group by tilt
original_image_filenames = initial_data(:, end);

fprintf('Analyzed %d particles\n', n_particles);
fprintf('  Mean defocus change: %.1f Angstroms\n', mean(delta_defocus_mean));
fprintf('  Mean astigmatism change: %.1f Angstroms\n', mean(delta_astigmatism));
fprintf('  Mean net shift: %.2f Angstroms\n', mean(net_shift));

% Figure 1: Histograms of changes
figure('Name', 'Refinement Changes - Histograms', 'Position', [100 100 1200 800]);

subplot(2,3,1);
histogram(delta_defocus_mean, 50);
xlabel('Delta defocus mean (Angstroms)');
ylabel('Count');
title('Defocus Change Distribution');
grid on;

subplot(2,3,2);
histogram(delta_astigmatism, 50);
xlabel('Delta astigmatism (Angstroms)');
ylabel('Count');
title('Astigmatism Change Distribution');
grid on;

subplot(2,3,3);
histogram(delta_astigmatism_angle, 50);
xlabel('Delta astigmatism angle (degrees)');
ylabel('Count');
title('Astigmatism Angle Change');
grid on;

subplot(2,3,4);
histogram(delta_shift_x, 50);
xlabel('Delta X shift (Angstroms)');
ylabel('Count');
title('X Shift Change');
grid on;

subplot(2,3,5);
histogram(delta_shift_y, 50);
xlabel('Delta Y shift (Angstroms)');
ylabel('Count');
title('Y Shift Change');
grid on;

subplot(2,3,6);
histogram(net_shift, 50);
xlabel('Net shift magnitude (Angstroms)');
ylabel('Count');
title('Net Shift Magnitude');
grid on;

% Figure 2: Score comparison
figure('Name', 'Score Comparison', 'Position', [100 100 800 400]);

subplot(1,2,1);
scatter(initial_data(:,14), refined_data(:,14), 3, '.');
hold on;
plot(xlim, xlim, 'r--', 'LineWidth', 1);
xlabel('Initial Score');
ylabel('Refined Score');
title('Score: Initial vs Refined');
grid on;

subplot(1,2,2);
histogram(refined_data(:,14) - initial_data(:,14), 50);
xlabel('Score Change');
ylabel('Count');
title('Score Change Distribution');
grid on;

fprintf('\nPlots generated successfully.\n');

end


function data = read_star_data(star_path)
% Read numeric data lines from a cisTEM star file.
% Skips header lines (comments, loop_, column definitions).

file_handle = fopen(star_path, 'r');
if file_handle == -1
    error('Could not open star file: %s', star_path);
end

data = [];
while ~feof(file_handle)
    line = fgetl(file_handle);
    if isempty(line) || line(1) == '#' || line(1) == '_' || startsWith(strtrim(line), 'data_') || startsWith(strtrim(line), 'loop_')
        continue;
    end
    tokens = strsplit(strtrim(line));
    if isempty(tokens) || isnan(str2double(tokens{1}))
        continue;
    end
    % Parse all numeric columns
    values = cellfun(@str2double, tokens(1:min(28, length(tokens))));
    if ~any(isnan(values))
        data(end+1, :) = values; %#ok<AGROW>
    end
end

fclose(file_handle);
end
