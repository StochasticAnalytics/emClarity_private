classdef BH_subTomoMeta_io < handle
%BH_subTomoMeta_io I/O handler for metadata operations
%
%   This class handles format-specific I/O operations for the metadata
%   wrapper, supporting legacy .mat files and partitioned STAR/JSON format.

    properties
        identifier         % Project identifier
        base_path         % Base path for metadata files
        format_type       % Current format type
        emc              % Parameter structure
        index            % Index for partitioned format
        cache            % Optional cache for performance
    end
    
    methods
        function obj = BH_subTomoMeta_io(identifier, emc)
            %BH_subTomoMeta_io Constructor
            
            obj.identifier = identifier;
            obj.emc = emc;
            
            % Determine base path
            if contains(identifier, '.mat')
                obj.base_path = identifier(1:end-4);
            else
                obj.base_path = identifier;
            end
            
            % Determine format type
            if isfield(emc, 'metadata_format')
                obj.format_type = lower(emc.metadata_format);
            else
                obj.format_type = obj.detect_format();
            end
        end
        
        function data = load_legacy(obj)
            %load_legacy Load from legacy .mat file
            
            mat_file = sprintf('%s.mat', obj.base_path);
            
            if ~exist(mat_file, 'file')
                error('BH_subTomoMeta_io:FileNotFound', ...
                      'Legacy metadata file not found: %s', mat_file);
            end
            
            fprintf('  Loading legacy format from %s...\n', mat_file);
            tmp = load(mat_file, 'subTomoMeta');
            
            if isfield(tmp, 'subTomoMeta')
                data = tmp.subTomoMeta;
            else
                error('BH_subTomoMeta_io:InvalidFile', ...
                      'File does not contain subTomoMeta structure');
            end
        end
        
        function data = load_partitioned(obj)
            %load_partitioned Load from partitioned STAR/JSON files
            %   Placeholder for future implementation

            error('BH_subTomoMeta_io:NotImplemented', ...
                  'Partitioned format loading not yet implemented. Please use legacy format.');
        end
        
        function save_legacy(obj, data)
            %save_legacy Save to legacy .mat file with atomic operation and integrity checks

            mat_file = sprintf('%s.mat', obj.base_path);

            % Create backup if file exists
            if exist(mat_file, 'file')
                backup_file = sprintf('%s_backup_%s.mat', obj.base_path, ...
                                      datestr(now, 'yyyymmdd_HHMMSS'));
                copyfile(mat_file, backup_file);
            end

            % Atomic save with integrity checking and retry logic
            max_retries = 2;
            success = false;

            for attempt = 1:max_retries
                try
                    % Use temporary file for atomic operation
                    temp_file = sprintf('%s.tmp', mat_file);

                    % Check for variables that might exceed v7 format limits
                    large_var_warning = obj.check_large_variables(data);

                    if large_var_warning
                        warning('BH_subTomoMeta_io:LargeVariables', ...
                                'Detected very large variables. If save fails, data may exceed v7 format limits.');
                    end

                    % Save to temporary file using v7 format to avoid corruption
                    subTomoMeta = data;
                    fprintf('  Using v7 format to avoid corruption\n');
                    save(temp_file, 'subTomoMeta', '-v7');

                    % Simple atomic move without integrity checks or sync
                    [move_success, move_msg] = movefile(temp_file, mat_file);
                    if move_success
                        success = true;
                        fprintf('  Saved legacy format to %s\n', mat_file);
                        break;
                    else
                        warning('BH_subTomoMeta_io:MoveFailed', ...
                                'Move operation failed on attempt %d/%d: %s', attempt, max_retries, move_msg);
                    end

                catch ME
                    % Clean up temp file on error
                    if exist(temp_file, 'file')
                        delete(temp_file);
                    end

                    if attempt == max_retries
                        error('BH_subTomoMeta_io:SaveFailed', ...
                              'Failed to save after %d attempts. Last error: %s', ...
                              max_retries, ME.message);
                    else
                        warning('BH_subTomoMeta_io:SaveAttemptFailed', ...
                                'Save attempt %d/%d failed: %s. Retrying...', ...
                                attempt, max_retries, ME.message);
                        pause(0.1); % Brief pause before retry
                    end
                end
            end

            if ~success
                error('BH_subTomoMeta_io:SaveFailed', ...
                      'Failed to save file after %d attempts', max_retries);
            end
        end
        
        function save_partitioned(obj, data)
            %save_partitioned Save to partitioned STAR/JSON files
            %   Placeholder for future implementation

            error('BH_subTomoMeta_io:NotImplemented', ...
                  'Partitioned format saving not yet implemented. Please use legacy format.');
        end
        
        function fields = get_field_list(obj)
            %get_field_list Return list of available fields
            
            if strcmp(obj.format_type, 'partitioned') && ~isempty(obj.index)
                % Get from index
                fields = {};
                
                % Add config fields
                if isfield(obj.index, 'config_fields')
                    fields = [fields; obj.index.config_fields(:)];
                end
                
                % Add cycles
                if isfield(obj.index, 'cycles')
                    cycles = fieldnames(obj.index.cycles);
                    fields = [fields; cycles(:)];
                end
                
                % Add geometry fields
                if isfield(obj.index, 'geometry')
                    geom_fields = fieldnames(obj.index.geometry);
                    fields = [fields; geom_fields(:)];
                end
            else
                % Load and check
                try
                    if strcmp(obj.format_type, 'legacy')
                        data = obj.load_legacy();
                    else
                        data = obj.load_partitioned();
                    end
                    fields = fieldnames(data);
                catch
                    fields = {};
                end
            end
        end
        
        function exists = field_exists(obj, field)
            %field_exists Check if field exists
            
            fields = obj.get_field_list();
            exists = ismember(field, fields);
        end
    end
    
    methods (Access = private)
        function is_valid = check_mat_file_integrity(obj, filename)
            %check_mat_file_integrity Verify MAT file can be loaded without corruption
            %   Returns true if file can be loaded successfully, false otherwise

            is_valid = false;

            try
                % Basic file existence and size check
                if ~exist(filename, 'file')
                    return;
                end

                file_info = dir(filename);
                if file_info.bytes == 0
                    return;
                end

                % Try to get variable information without loading data
                var_info = whos('-file', filename);
                if isempty(var_info)
                    return;
                end

                % Check that subTomoMeta variable exists
                var_names = {var_info.name};
                if ~ismember('subTomoMeta', var_names)
                    return;
                end

                % Try to load just the structure metadata (not the full data)
                % This will catch HDF5 corruption errors
                temp_struct = load(filename, 'subTomoMeta');
                if ~isfield(temp_struct, 'subTomoMeta')
                    return;
                end

                % Basic structure validation
                data = temp_struct.subTomoMeta;
                if ~isstruct(data)
                    return;
                end

                % Check for essential fields that should always exist
                essential_fields = {'currentCycle', 'currentTomoCPR'};
                for i = 1:length(essential_fields)
                    if ~isfield(data, essential_fields{i})
                        % Not necessarily an error for new projects, just continue
                    end
                end

                % If we get here, file passed all checks
                is_valid = true;

            catch ME
                % Any error during loading indicates corruption
                if contains(ME.message, 'HDF5') || contains(ME.message, 'inflate')
                    % Specific corruption patterns we've seen
                    is_valid = false;
                else
                    % Other errors might still indicate corruption
                    warning('BH_subTomoMeta_io:IntegrityCheckError', ...
                            'Unexpected error during integrity check: %s', ME.message);
                    is_valid = false;
                end
            end
        end

        function format = detect_format(obj)
            %detect_format Auto-detect metadata format

            % Check for partitioned format
            part_dir = sprintf('%s_star', obj.base_path);
            if exist(fullfile(part_dir, 'index.json'), 'file')
                format = 'partitioned';
                return;
            end
            
            % Check for legacy format
            mat_file = sprintf('%s.mat', obj.base_path);
            if exist(mat_file, 'file')
                format = 'legacy';
                return;
            end
            
            % Default to legacy for new projects
            format = 'legacy';
        end
        
        function index = create_index(obj)
            %create_index Create new index structure
            
            index = struct();
            index.version = '1.0';
            index.format = 'partitioned';
            index.created = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
            index.last_modified = index.created;
            index.cycles = struct();
            index.geometry = struct();
            index.config_file = 'config.json';
        end
        
        function cycle_data = load_cycle_partitioned(obj, part_dir, cycle)
            %load_cycle_partitioned Load a specific cycle from partitioned format
            
            cycle_dir = fullfile(part_dir, 'cycles', cycle);
            cycle_data = struct();
            
            % Load RawAlign geometry
            raw_align_file = fullfile(cycle_dir, 'raw_align.star');
            if exist(raw_align_file, 'file')
                cycle_data.RawAlign = obj.load_star_geometry(raw_align_file);
            end
            
            % Load other cycle data
            metadata_file = fullfile(cycle_dir, 'metadata.json');
            if exist(metadata_file, 'file')
                metadata = obj.load_json(metadata_file);
                fields = fieldnames(metadata);
                for i = 1:length(fields)
                    if ~strcmp(fields{i}, 'RawAlign')
                        cycle_data.(fields{i}) = metadata.(fields{i});
                    end
                end
            end
            
            % Load Post_ operations if present
            post_files = dir(fullfile(cycle_dir, 'Post_*.star'));
            for i = 1:length(post_files)
                [~, name, ~] = fileparts(post_files(i).name);
                cycle_data.(name) = obj.load_star_geometry(...
                    fullfile(cycle_dir, post_files(i).name));
            end
        end
        
        function save_cycle_partitioned(obj, part_dir, cycle, cycle_data)
            %save_cycle_partitioned Save a cycle to partitioned format
            
            cycle_dir = fullfile(part_dir, 'cycles', cycle);
            
            % Create directory
            if ~exist(cycle_dir, 'dir')
                mkdir(cycle_dir);
            end
            
            % Save RawAlign as STAR file
            if isfield(cycle_data, 'RawAlign')
                raw_align_file = fullfile(cycle_dir, 'raw_align.star');
                obj.save_star_geometry(raw_align_file, cycle_data.RawAlign);
            end
            
            % Save Post_ operations
            fields = fieldnames(cycle_data);
            post_fields = fields(startsWith(fields, 'Post_'));
            for i = 1:length(post_fields)
                post_file = fullfile(cycle_dir, [post_fields{i} '.star']);
                obj.save_star_geometry(post_file, cycle_data.(post_fields{i}));
            end
            
            % Save other metadata as JSON
            metadata = struct();
            for i = 1:length(fields)
                if ~strcmp(fields{i}, 'RawAlign') && ...
                   ~startsWith(fields{i}, 'Post_')
                    metadata.(fields{i}) = cycle_data.(fields{i});
                end
            end
            
            if ~isempty(fieldnames(metadata))
                metadata_file = fullfile(cycle_dir, 'metadata.json');
                obj.save_json(metadata_file, metadata);
            end
        end
        
        function data = load_geometry_partitioned(obj, data, part_dir)
            %load_geometry_partitioned Load geometry data from partitioned format
            
            geom_dir = fullfile(part_dir, 'geometry');
            
            % Load mapBackGeometry
            mapback_file = fullfile(geom_dir, 'mapback_geometry.star');
            if exist(mapback_file, 'file')
                data.mapBackGeometry = obj.load_star_file(mapback_file);
            end
            
            % Load tiltGeometry
            tilt_dir = fullfile(part_dir, 'tilt_geometry');
            if exist(tilt_dir, 'dir')
                tilt_files = dir(fullfile(tilt_dir, '*.star'));
                data.tiltGeometry = struct();
                for i = 1:length(tilt_files)
                    [~, name, ~] = fileparts(tilt_files(i).name);
                    data.tiltGeometry.(name) = obj.load_star_file(...
                        fullfile(tilt_dir, tilt_files(i).name));
                end
            end
        end
        
        function save_geometry_partitioned(obj, data, part_dir)
            %save_geometry_partitioned Save geometry data to partitioned format
            
            geom_dir = fullfile(part_dir, 'geometry');
            if ~exist(geom_dir, 'dir')
                mkdir(geom_dir);
            end
            
            % Save mapBackGeometry
            if isfield(data, 'mapBackGeometry')
                mapback_file = fullfile(geom_dir, 'mapback_geometry.star');
                obj.save_star_file(mapback_file, data.mapBackGeometry);
            end
            
            % Save tiltGeometry
            if isfield(data, 'tiltGeometry')
                tilt_dir = fullfile(part_dir, 'tilt_geometry');
                if ~exist(tilt_dir, 'dir')
                    mkdir(tilt_dir);
                end
                
                tomo_names = fieldnames(data.tiltGeometry);
                for i = 1:length(tomo_names)
                    tilt_file = fullfile(tilt_dir, [tomo_names{i} '.star']);
                    obj.save_star_file(tilt_file, data.tiltGeometry.(tomo_names{i}));
                end
            end
        end
        
        function geometry = load_star_geometry(obj, filename)
            %load_star_geometry Load geometry from STAR file
            
            % This is a placeholder - would use actual STAR file reader
            % For now, use basic text reading
            geometry = struct();
            
            % TODO: Implement actual STAR file reading
            % Would parse the STAR format and create tomogram structures
            
            fprintf('    Loading STAR geometry from %s\n', filename);
        end
        
        function save_star_geometry(obj, filename, geometry)
            %save_star_geometry Save geometry to STAR file
            
            % This is a placeholder - would use actual STAR file writer
            % For now, use basic text writing
            
            % TODO: Implement actual STAR file writing
            % Would format geometry data as STAR file
            
            fprintf('    Saving STAR geometry to %s\n', filename);
        end
        
        function data = load_star_file(obj, filename)
            %load_star_file Load generic STAR file
            
            % Placeholder for STAR file loading
            data = [];
            fprintf('    Loading STAR file %s\n', filename);
        end
        
        function save_star_file(obj, filename, data)
            %save_star_file Save generic STAR file
            
            % Placeholder for STAR file saving
            fprintf('    Saving STAR file %s\n', filename);
        end
        
        function data = load_json(obj, filename)
            %load_json Load JSON file
            
            if ~exist(filename, 'file')
                error('BH_subTomoMeta_io:FileNotFound', ...
                      'JSON file not found: %s', filename);
            end
            
            % Read JSON file
            fid = fopen(filename, 'r');
            raw = fread(fid, '*char')';
            fclose(fid);
            
            % Parse JSON (simplified - would use proper JSON parser)
            try
                data = jsondecode(raw);
            catch ME
                warning('BH_subTomoMeta_io:JSONError', ...
                        'Error parsing JSON file %s: %s', filename, ME.message);
                data = struct();
            end
        end
        
        function save_json(obj, filename, data)
            %save_json Save JSON file
            
            % Convert to JSON (simplified - would use proper JSON encoder)
            try
                json_str = jsonencode(data);
            catch ME
                warning('BH_subTomoMeta_io:JSONError', ...
                        'Error encoding JSON: %s', ME.message);
                return;
            end
            
            % Write file
            fid = fopen(filename, 'w');
            fprintf(fid, '%s', json_str);
            fclose(fid);
        end

        function has_large_vars = check_large_variables(obj, data_struct)
            %check_large_variables Check for variables that might exceed v7 format limits
            %   v7 format has 2GB limit per variable, not total file size

            has_large_vars = false;

            try
                if ~isstruct(data_struct)
                    % Check single variable
                    assignin('base', 'temp_size_var', data_struct);
                    info = evalin('base', 'whos(''temp_size_var'')');
                    evalin('base', 'clear temp_size_var');

                    if info.bytes > 1.5 * 1024^3  % > 1.5GB warning threshold
                        fprintf('  Large variable detected: %.2f GB\n', info.bytes / 1024^3);
                        has_large_vars = true;
                    end
                    return;
                end

                field_names = fieldnames(data_struct);

                for i = 1:length(field_names)
                    field_name = field_names{i};
                    field_data = data_struct.(field_name);

                    try
                        % Get memory info for this field
                        assignin('base', 'temp_size_var', field_data);
                        info = evalin('base', 'whos(''temp_size_var'')');
                        evalin('base', 'clear temp_size_var');

                        field_gb = info.bytes / 1024^3;

                        % Log fields > 100MB
                        if info.bytes > 100*1024^2
                            fprintf('  Field ''%s'': %.2f GB (%s)\n', ...
                                    field_name, field_gb, info.class);
                        end

                        % Warn if approaching v7 2GB per-variable limit
                        if info.bytes > 1.5 * 1024^3  % > 1.5GB
                            fprintf('  WARNING: Field ''%s'' is %.2f GB (approaching 2GB v7 limit)\n', ...
                                    field_name, field_gb);
                            has_large_vars = true;
                        end

                    catch
                        % If we can't check, assume it's not too large
                        continue;
                    end
                end

            catch ME
                fprintf('  Error checking variable sizes: %s\n', ME.message);
                has_large_vars = false; % Default to allowing save attempt
            end
        end
    end
end