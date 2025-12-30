
function [star_path, tomo_path, csv_path] = EMC_syntheticTomogram_starfile(template_pdb_pairs, tomo_size, ...
                                                        exclusion_factor, output_path, output_prefix, varargin)
%EMC_syntheticTomogram_starfile DEPRECATED - Use EMC_syntheticTomogram with 'output_starfile', true
%
%   This function is deprecated and maintained only for backward compatibility.
%   Please use EMC_syntheticTomogram with the 'output_starfile' option instead:
%
%   outputs = EMC_syntheticTomogram(template_pdb_pairs, tomo_size, exclusion_factor, ...
%                                    output_path, output_prefix, 'output_starfile', true);
%
%   See EMC_syntheticTomogram for full documentation.
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% Issue deprecation warning
warning('EMC:deprecated', ...
    ['EMC_syntheticTomogram_starfile is deprecated.\n' ...
     'Use EMC_syntheticTomogram with ''output_starfile'', true instead.\n' ...
     'Example: outputs = EMC_syntheticTomogram(pairs, size, excl, path, prefix, ''output_starfile'', true);']);

%% Parse inputs to extract build_tomogram and save_projection
p = inputParser;
addRequired(p, 'template_pdb_pairs', @iscell);
addRequired(p, 'tomo_size', @(x) isnumeric(x) && numel(x) == 3);
addRequired(p, 'exclusion_factor', @(x) isnumeric(x) && x >= 1.0);
addRequired(p, 'output_path', @ischar);
addRequired(p, 'output_prefix', @ischar);
addParameter(p, 'max_particles', inf, @isnumeric);
addParameter(p, 'max_attempts', 100000, @isnumeric);
addParameter(p, 'gpu_id', 1, @isnumeric);
addParameter(p, 'build_tomogram', false, @islogical);
addParameter(p, 'save_projection', false, @islogical);

parse(p, template_pdb_pairs, tomo_size, exclusion_factor, output_path, output_prefix, varargin{:});

%% Call unified function with starfile output enabled
outputs = EMC_syntheticTomogram(template_pdb_pairs, tomo_size, exclusion_factor, ...
    output_path, output_prefix, ...
    'max_particles', p.Results.max_particles, ...
    'max_attempts', p.Results.max_attempts, ...
    'gpu_id', p.Results.gpu_id, ...
    'build_tomogram', p.Results.build_tomogram, ...
    'save_projection', p.Results.save_projection, ...
    'output_starfile', true, ...
    'collision_mode', 'sphere');  % Original starfile version used sphere mode

%% Return legacy output format
star_path = outputs.star_path;
tomo_path = outputs.tomo_path;
csv_path = outputs.csv_path;

end
