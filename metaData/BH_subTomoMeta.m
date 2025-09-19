classdef BH_subTomoMeta < handle
%BH_subTomoMeta Universal metadata wrapper class for emClarity
%
%   This class provides a unified interface for metadata operations across
%   different storage formats (legacy .mat, partitioned STAR/JSON, or
%   development mode with dual read/write).
%
%   Usage:
%       meta = BH_subTomoMeta('project_name', emc);
%       meta.currentCycle = 5;              % Transparent field access
%       particles = meta.cycle005.RawAlign; % Nested access
%       meta.save();                         % Save in appropriate format
%       meta.exportToRELION('output_dir');  % Export functionality
%
%   Supported formats:
%       'legacy'      - Traditional monolithic .mat file
%       'partitioned' - Distributed STAR/JSON files
%       'development' - Dual format with validation

    properties (Access = private)
        data               % The actual metadata structure
        format_type        % 'legacy', 'partitioned', or 'development'
        legacy_data        % For development mode only
        partitioned_data   % For development mode only
        io_handler         % Handles format-specific I/O
        export_handler     % Handles export operations
        identifier         % Project identifier/path
        emc               % Parameter structure
        modified          % Track if data has been modified
        cache             % Optional caching for performance
    end
    
    properties (Constant, Access = private)
        TOLERANCE = 1e-10; % Numerical comparison tolerance
    end
    
    methods
        function obj = BH_subTomoMeta(identifier, emc)
            %BH_subTomoMeta Constructor
            %   identifier - Project name or path to metadata
            %   emc - Parameter structure from BH_parseParameterFile
            
            if nargin < 2
                error('BH_subTomoMeta:MissingArgs', ...
                      'Usage: BH_subTomoMeta(identifier, emc)');
            end
            
            obj.identifier = identifier;
            obj.emc = emc;
            obj.modified = false;
            
            % Determine format type from parameters
            if isfield(emc, 'metadata_format')
                obj.format_type = lower(emc.metadata_format);
            else
                obj.format_type = 'legacy'; % Default
            end
            
            % Validate format type
            valid_formats = {'legacy', 'partitioned', 'development'};
            if ~ismember(obj.format_type, valid_formats)
                error('BH_subTomoMeta:InvalidFormat', ...
                      'Invalid format: %s. Must be legacy, partitioned, or development', ...
                      obj.format_type);
            end
            
            % Initialize I/O handler
            obj.io_handler = BH_subTomoMeta_io(identifier, emc);
            
            % Initialize export handler
            obj.export_handler = BH_exportHandler();
            
            % Load metadata based on format
            obj.load();
        end
        
        function value = subsref(obj, s)
            %subsref Overloaded subscript reference
            %   Provides transparent field access to metadata
            
            % Handle method calls
            if length(s) == 1 && strcmp(s.type, '.')
                % Check if it's a method
                if ismember(s.subs, methods(obj))
                    % Call the method
                    if nargout > 0
                        value = builtin('subsref', obj, s);
                    else
                        builtin('subsref', obj, s);
                    end
                    return;
                end
            end
            
            % Handle data field access
            try
                switch obj.format_type
                    case 'legacy'
                        value = subsref(obj.data, s);
                        
                    case 'partitioned'
                        % Lazy loading for partitioned format
                        value = obj.get_partitioned_field(s);
                        
                    case 'development'
                        % Get from both and compare
                        value = obj.get_development_field(s);
                end
            catch ME
                % If field doesn't exist, follow MATLAB convention
                if contains(ME.message, 'Reference to non-existent field')
                    error('BH_subTomoMeta:InvalidField', ...
                          'Reference to non-existent field ''%s''', ...
                          s(1).subs);
                else
                    rethrow(ME);
                end
            end
        end
        
        function obj = subsasgn(obj, s, value)
            %subsasgn Overloaded subscript assignment
            %   Provides transparent field assignment to metadata
            
            % Mark as modified
            obj.modified = true;
            
            switch obj.format_type
                case 'legacy'
                    obj.data = subsasgn(obj.data, s, value);
                    
                case 'partitioned'
                    obj.set_partitioned_field(s, value);
                    
                case 'development'
                    % Update both formats
                    obj.set_development_field(s, value);
            end
        end
        
        function fields = fieldnames(obj)
            %fieldnames Return field names of metadata
            
            switch obj.format_type
                case 'legacy'
                    fields = fieldnames(obj.data);
                    
                case 'partitioned'
                    fields = obj.io_handler.get_field_list();
                    
                case 'development'
                    % Return union of fields from both formats
                    fields_legacy = fieldnames(obj.legacy_data);
                    fields_part = obj.io_handler.get_field_list();
                    fields = unique([fields_legacy; fields_part]);
            end
        end
        
        function result = isfield(obj, field)
            %isfield Check if field exists in metadata
            
            switch obj.format_type
                case 'legacy'
                    result = isfield(obj.data, field);
                    
                case 'partitioned'
                    result = obj.io_handler.field_exists(field);
                    
                case 'development'
                    % Check both formats
                    result = isfield(obj.legacy_data, field) || ...
                             obj.io_handler.field_exists(field);
            end
        end
        
        function save(obj)
            %save Save metadata to appropriate format(s)
            
            fprintf('Saving metadata (format: %s)...\n', obj.format_type);
            
            switch obj.format_type
                case 'legacy'
                    obj.save_legacy();
                    
                case 'partitioned'
                    obj.save_partitioned();
                    
                case 'development'
                    % Save to both formats
                    fprintf('  Saving legacy format...\n');
                    obj.save_legacy();
                    fprintf('  Saving partitioned format...\n');
                    obj.save_partitioned();
                    fprintf('  Verifying consistency...\n');
                    obj.verify_consistency();
            end
            
            obj.modified = false;
            fprintf('Save complete.\n');
        end
        
        function exportToRELION(obj, output_dir, varargin)
            %exportToRELION Export metadata to RELION format
            %   output_dir - Directory for RELION STAR files
            %   varargin - Optional parameters (cycle, validate, etc.)
            
            fprintf('\nExporting to RELION format...\n');
            options = obj.parse_export_options(varargin{:});
            
            % Use export handler
            obj.export_handler.exportToRELION(obj.get_data(), ...
                                               output_dir, options);
            
            fprintf('Export complete. Output in: %s\n', output_dir);
        end
        
        function exportToPEET(obj, output_dir, varargin)
            %exportToPEET Export metadata to PEET format
            %   output_dir - Directory for PEET files
            %   varargin - Optional parameters
            
            fprintf('\nExporting to PEET format...\n');
            options = obj.parse_export_options(varargin{:});
            
            % Use export handler
            obj.export_handler.exportToPEET(obj.get_data(), ...
                                            output_dir, options);
            
            fprintf('Export complete. Output in: %s\n', output_dir);
        end
        
        function exportToCryoSPARC(obj, output_dir, varargin)
            %exportToCryoSPARC Export metadata to CryoSPARC format
            %   output_dir - Directory for CryoSPARC files
            %   varargin - Optional parameters
            
            fprintf('\nExporting to CryoSPARC format...\n');
            options = obj.parse_export_options(varargin{:});
            
            % Use export handler
            obj.export_handler.exportToCryoSPARC(obj.get_data(), ...
                                                 output_dir, options);
            
            fprintf('Export complete. Output in: %s\n', output_dir);
        end
        
        function data = get_data(obj)
            %get_data Return the underlying data structure
            %   Used for compatibility with legacy code
            
            switch obj.format_type
                case 'legacy'
                    data = obj.data;
                case 'partitioned'
                    data = obj.partitioned_data;
                case 'development'
                    data = obj.legacy_data; % Default to legacy
            end
        end
    end
    
    methods (Access = private)
        function load(obj)
            %load Load metadata from storage
            
            switch obj.format_type
                case 'legacy'
                    obj.data = obj.io_handler.load_legacy();
                    
                case 'partitioned'
                    obj.partitioned_data = obj.io_handler.load_partitioned();
                    obj.data = obj.partitioned_data; % For compatibility
                    
                case 'development'
                    % Load both formats
                    fprintf('Loading development mode (dual format)...\n');
                    obj.legacy_data = obj.io_handler.load_legacy();
                    obj.partitioned_data = obj.io_handler.load_partitioned();
                    obj.data = obj.legacy_data; % Default to legacy
                    
                    % Initial validation
                    obj.verify_consistency();
            end
        end
        
        function value = get_partitioned_field(obj, s)
            %get_partitioned_field Get field from partitioned storage
            %   Implements lazy loading for efficiency
            
            % TODO: Implement lazy loading logic
            value = subsref(obj.partitioned_data, s);
        end
        
        function value = get_development_field(obj, s)
            %get_development_field Get field in development mode
            %   Compares values from both formats
            
            field_path = obj.build_field_path(s);
            
            % Get from both sources
            try
                legacy_val = subsref(obj.legacy_data, s);
            catch
                legacy_val = [];
            end
            
            try
                part_val = subsref(obj.partitioned_data, s);
            catch
                part_val = [];
            end
            
            % Compare if both exist
            if ~isempty(legacy_val) && ~isempty(part_val)
                if ~obj.compare_values(legacy_val, part_val)
                    obj.log_discrepancy(field_path, legacy_val, part_val);
                end
            end
            
            % Return legacy value (safe default)
            value = legacy_val;
        end
        
        function set_partitioned_field(obj, s, value)
            %set_partitioned_field Set field in partitioned storage
            
            obj.partitioned_data = subsasgn(obj.partitioned_data, s, value);
        end
        
        function set_development_field(obj, s, value)
            %set_development_field Set field in development mode
            %   Updates both formats
            
            obj.legacy_data = subsasgn(obj.legacy_data, s, value);
            obj.partitioned_data = subsasgn(obj.partitioned_data, s, value);
        end
        
        function save_legacy(obj)
            %save_legacy Save in legacy format
            
            if strcmp(obj.format_type, 'development')
                obj.io_handler.save_legacy(obj.legacy_data);
            else
                obj.io_handler.save_legacy(obj.data);
            end
        end
        
        function save_partitioned(obj)
            %save_partitioned Save in partitioned format
            
            if strcmp(obj.format_type, 'development')
                obj.io_handler.save_partitioned(obj.partitioned_data);
            else
                obj.io_handler.save_partitioned(obj.data);
            end
        end
        
        function match = compare_values(obj, val1, val2)
            %compare_values Compare two values with appropriate tolerance
            
            if isnumeric(val1) && isnumeric(val2)
                % Numerical comparison with tolerance
                if size(val1) == size(val2)
                    match = all(abs(val1(:) - val2(:)) < obj.TOLERANCE);
                else
                    match = false;
                end
            elseif ischar(val1) && ischar(val2)
                % String comparison
                match = strcmp(val1, val2);
            elseif isstruct(val1) && isstruct(val2)
                % Structural comparison (recursive)
                match = obj.compare_structs(val1, val2);
            else
                % Type mismatch or other
                match = isequal(val1, val2);
            end
        end
        
        function match = compare_structs(obj, s1, s2)
            %compare_structs Recursively compare structures
            
            fields1 = fieldnames(s1);
            fields2 = fieldnames(s2);
            
            if ~isequal(sort(fields1), sort(fields2))
                match = false;
                return;
            end
            
            match = true;
            for i = 1:length(fields1)
                field = fields1{i};
                if ~obj.compare_values(s1.(field), s2.(field))
                    match = false;
                    return;
                end
            end
        end
        
        function log_discrepancy(obj, field_path, legacy_val, part_val)
            %log_discrepancy Log value discrepancy to file
            
            if ~isfield(obj.emc, 'dev_mode_log_all_access') || ...
               obj.emc.dev_mode_log_all_access
                
                log_file = sprintf('logFile/metadata_discrepancy_%s.log', ...
                                   datestr(now, 'yyyymmdd'));
                
                if ~exist('logFile', 'dir')
                    mkdir('logFile');
                end
                
                fid = fopen(log_file, 'a');
                fprintf(fid, '\n[%s] Field: %s\n', datestr(now), field_path);
                fprintf(fid, '  Legacy value: %s\n', obj.value_to_string(legacy_val));
                fprintf(fid, '  Partitioned value: %s\n', obj.value_to_string(part_val));
                fclose(fid);
                
                % Also warn in console if configured
                if isfield(obj.emc, 'dev_mode_fail_on_mismatch') && ...
                   obj.emc.dev_mode_fail_on_mismatch
                    error('BH_subTomoMeta:ValueMismatch', ...
                          'Value mismatch for field %s', field_path);
                else
                    warning('BH_subTomoMeta:ValueMismatch', ...
                            'Value mismatch for field %s (see log)', field_path);
                end
            end
        end
        
        function str = value_to_string(~, val)
            %value_to_string Convert value to string for logging
            
            if isnumeric(val)
                if numel(val) == 1
                    str = num2str(val);
                else
                    str = sprintf('[%dx%d %s]', size(val,1), size(val,2), class(val));
                end
            elseif ischar(val)
                str = val;
            elseif isstruct(val)
                str = sprintf('[struct with %d fields]', length(fieldnames(val)));
            else
                str = sprintf('[%s]', class(val));
            end
        end
        
        function path = build_field_path(~, s)
            %build_field_path Build field path string from substruct
            
            path = '';
            for i = 1:length(s)
                switch s(i).type
                    case '.'
                        if isempty(path)
                            path = s(i).subs;
                        else
                            path = [path '.' s(i).subs];
                        end
                    case '()'
                        indices = s(i).subs;
                        if iscell(indices)
                            idx_str = sprintf('%d,', indices{:});
                            idx_str = idx_str(1:end-1);
                        else
                            idx_str = num2str(indices);
                        end
                        path = [path '(' idx_str ')'];
                    case '{}'
                        path = [path '{}'];
                end
            end
        end
        
        function verify_consistency(obj)
            %verify_consistency Verify consistency between formats
            %   Only used in development mode
            
            if ~strcmp(obj.format_type, 'development')
                return;
            end
            
            fprintf('Verifying consistency between legacy and partitioned formats...\n');
            
            % Compare major fields
            fields_to_check = {'currentCycle', 'currentTomoCPR', 'maxGoldStandard'};
            
            for i = 1:length(fields_to_check)
                field = fields_to_check{i};
                if isfield(obj.legacy_data, field) && ...
                   isfield(obj.partitioned_data, field)
                    if ~obj.compare_values(obj.legacy_data.(field), ...
                                           obj.partitioned_data.(field))
                        warning('BH_subTomoMeta:Inconsistency', ...
                                'Field %s differs between formats', field);
                    end
                end
            end
            
            fprintf('Consistency check complete.\n');
        end
        
        function options = parse_export_options(~, varargin)
            %parse_export_options Parse export option arguments
            
            p = inputParser;
            p.addParameter('cycle', [], @isnumeric);
            p.addParameter('validate', true, @islogical);
            p.addParameter('verbose', true, @islogical);
            p.addParameter('force', false, @islogical);
            
            p.parse(varargin{:});
            options = p.Results;
        end
    end
end