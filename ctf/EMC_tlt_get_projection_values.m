function [values] = EMC_tlt_get_projection_values(tlt_data, column_spec)
%EMC_tlt_get_projection_values Extract TLT values indexed by projection position
%
%   values = EMC_tlt_get_projection_values(tlt_data, column_spec)
%
%   Extracts values from a TLT matrix, sorted and indexed by projection
%   position (column 1). This ensures values align with stack slice order.
%
%   Input:
%       tlt_data    - Loaded TLT matrix (n_tilts x 23 columns)
%       column_spec - Either:
%                     'exposure' - Calculate per-projection exposure from cumulative dose
%                     numeric    - Column index(es) to extract directly
%
%   Output:
%       values - Values indexed by projection position (1 to n_tilts)
%                For 'exposure': n_tilts x 1 per-projection dose (e-/A^2)
%                For numeric: n_tilts x length(column_spec)
%
%   Examples:
%       % Get per-projection exposure
%       exposure = EMC_tlt_get_projection_values(TLT, 'exposure');
%
%       % Get defocus values (column 15)
%       defocus = EMC_tlt_get_projection_values(TLT, 15);
%
%       % Get multiple columns: defocus, astig_mag, astig_angle
%       ctf_params = EMC_tlt_get_projection_values(TLT, [15, 12, 13]);
%
%   TLT Column Reference:
%       1  - Projection index
%       4  - Tilt angle (degrees)
%       11 - Cumulative dose (e-/A^2)
%       12 - Astigmatism magnitude (meters)
%       13 - Astigmatism angle (radians)
%       15 - Defocus (meters)
%       16 - Pixel size (meters)
%       17 - Cs (meters)
%       18 - Wavelength (meters)
%       19 - Amplitude contrast (0-1)
%
%   See also: EMC_generate_projections, EMC_setup_synthetic_project

% Validate input
if isempty(tlt_data)
    error('EMC_tlt_get_projection_values:EmptyInput', 'TLT data is empty');
end

n_tilts = size(tlt_data, 1);

% Sort by projection index (column 1) to ensure correct ordering
tlt_sorted = sortrows(tlt_data, 1);

% Handle column_spec
if ischar(column_spec) || isstring(column_spec)
    switch lower(column_spec)
        case 'exposure'
            % Calculate per-projection exposure from cumulative dose (column 11)
            cumulative_dose = tlt_sorted(:, 11);
            values = zeros(n_tilts, 1);

            for j = 1:n_tilts
                this_cumulative = cumulative_dose(j);
                % Find doses smaller than this one (earlier in exposure order)
                earlier_doses = cumulative_dose(cumulative_dose < this_cumulative);
                if isempty(earlier_doses)
                    % This is the first exposure
                    values(j) = this_cumulative;
                else
                    % Previous exposure is the max of all earlier doses
                    values(j) = this_cumulative - max(earlier_doses);
                end
            end

        otherwise
            error('EMC_tlt_get_projection_values:UnknownSpec', ...
                  'Unknown column_spec: %s. Use ''exposure'' or numeric column indices.', ...
                  column_spec);
    end

elseif isnumeric(column_spec)
    % Direct column extraction
    max_col = size(tlt_sorted, 2);
    if any(column_spec < 1) || any(column_spec > max_col)
        error('EMC_tlt_get_projection_values:InvalidColumn', ...
              'Column index out of range. TLT has %d columns.', max_col);
    end

    values = tlt_sorted(:, column_spec);

else
    error('EMC_tlt_get_projection_values:InvalidSpec', ...
          'column_spec must be a string (''exposure'') or numeric column indices.');
end

end
