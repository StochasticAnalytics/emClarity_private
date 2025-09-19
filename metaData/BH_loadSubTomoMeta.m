function subTomoMeta = BH_loadSubTomoMeta(identifier, metadata_format)
%BH_loadSubTomoMeta Load metadata using the wrapper class (or legacy direct load)
%
%   subTomoMeta = BH_loadSubTomoMeta(identifier, metadata_format)
%
%   This function provides a unified interface for loading metadata,
%   using the new wrapper class system when available.
%
%   Inputs:
%       identifier - Project name or path to metadata file (e.g., emc.('subTomoMeta'))
%       metadata_format - Format type: 'legacy', 'partitioned', or 'development'
%                        (typically from emc.('metadata_format'))
%
%   Output:
%       subTomoMeta - Either raw struct or wrapper object (depending on availability)

    % Handle missing arguments
    if nargin < 2
        metadata_format = 'legacy';  % Default to legacy if not specified
    end

    % Ensure format is lowercase
    metadata_format = lower(metadata_format);

    % Create minimal emc structure for the wrapper
    emc = struct('metadata_format', metadata_format);
    
    % Load metadata
    if use_wrapper
        % Check if wrapper class exists
        if exist('BH_subTomoMeta', 'class') == 8
            try
                % Use wrapper class
                subTomoMeta = BH_subTomoMeta(identifier, emc);
            catch ME
                % Fall back to legacy if wrapper fails
                warning('BH_loadSubTomoMeta:WrapperFailed', ...
                        'Wrapper failed (%s), using legacy mode', ME.message);
                subTomoMeta = load_legacy(identifier);
            end
        else
            % Wrapper not available, use legacy
            warning('BH_loadSubTomoMeta:NoWrapper', ...
                    'Wrapper class not found, using legacy mode');
            subTomoMeta = load_legacy(identifier);
        end
    else
        % Explicitly requested legacy mode
        subTomoMeta = load_legacy(identifier);
    end
end

function subTomoMeta = load_legacy(identifier)
    %load_legacy Load metadata using traditional method
    
    % Determine file path
    if contains(identifier, '.mat')
        mat_file = identifier;
    else
        mat_file = sprintf('%s.mat', identifier);
    end
    
    % Check file exists
    if ~exist(mat_file, 'file')
        % Try alternate path
        mat_file = sprintf('subTomoMeta_%s.mat', identifier);
        if ~exist(mat_file, 'file')
            error('BH_loadSubTomoMeta:FileNotFound', ...
                  'Cannot find metadata file for %s', identifier);
        end
    end
    
    % Load the file
    tmp = load(mat_file, 'subTomoMeta');
    
    if isfield(tmp, 'subTomoMeta')
        subTomoMeta = tmp.subTomoMeta;
    else
        error('BH_loadSubTomoMeta:InvalidFile', ...
              'File %s does not contain subTomoMeta', mat_file);
    end
end