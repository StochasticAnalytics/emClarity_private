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
            
            part_dir = sprintf('%s_star', obj.base_path);
            
            if ~exist(part_dir, 'dir')
                % Try alternate naming
                part_dir = sprintf('%s', obj.base_path);
                if ~exist(fullfile(part_dir, 'index.json'), 'file')
                    error('BH_subTomoMeta_io:DirectoryNotFound', ...
                          'Partitioned metadata directory not found: %s', part_dir);
                end
            end
            
            fprintf('  Loading partitioned format from %s/...\n', part_dir);
            
            % Load index
            index_file = fullfile(part_dir, 'index.json');
            obj.index = obj.load_json(index_file);
            
            % Initialize data structure
            data = struct();
            
            % Load configuration
            if isfield(obj.index, 'config_file')
                config = obj.load_json(fullfile(part_dir, obj.index.config_file));
                fields = fieldnames(config);
                for i = 1:length(fields)
                    data.(fields{i}) = config.(fields{i});
                end
            end
            
            % Load cycles
            if isfield(obj.index, 'cycles')
                cycle_names = fieldnames(obj.index.cycles);
                for i = 1:length(cycle_names)
                    cycle = cycle_names{i};
                    data.(cycle) = obj.load_cycle_partitioned(part_dir, cycle);
                end
            end
            
            % Load geometry data
            if isfield(obj.index, 'geometry')
                data = obj.load_geometry_partitioned(data, part_dir);
            end
        end
        
        function save_legacy(obj, data)
            %save_legacy Save to legacy .mat file
            
            mat_file = sprintf('%s.mat', obj.base_path);
            
            % Create backup if file exists
            if exist(mat_file, 'file')
                backup_file = sprintf('%s_backup_%s.mat', obj.base_path, ...
                                      datestr(now, 'yyyymmdd_HHMMSS'));
                copyfile(mat_file, backup_file);
            end
            
            % Save with v7.3 for large files
            subTomoMeta = data;
            save(mat_file, 'subTomoMeta', '-v7.3');
            
            fprintf('  Saved legacy format to %s\n', mat_file);
        end
        
        function save_partitioned(obj, data)
            %save_partitioned Save to partitioned STAR/JSON files
            
            part_dir = sprintf('%s_star', obj.base_path);
            
            % Create directory if needed
            if ~exist(part_dir, 'dir')
                mkdir(part_dir);
            end
            
            fprintf('  Saving partitioned format to %s/...\n', part_dir);
            
            % Initialize or update index
            if isempty(obj.index)
                obj.index = obj.create_index();
            end
            obj.index.last_modified = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
            
            % Save configuration fields
            config = struct();
            config_fields = {'currentCycle', 'currentTomoCPR', 'maxGoldStandard', ...
                            'nSubTomoInitial', 'currentResForDefocusError'};
            for i = 1:length(config_fields)
                if isfield(data, config_fields{i})
                    config.(config_fields{i}) = data.(config_fields{i});
                end
            end
            obj.save_json(fullfile(part_dir, 'config.json'), config);
            
            % Save cycles
            fields = fieldnames(data);
            cycle_fields = fields(startsWith(fields, 'cycle'));
            
            for i = 1:length(cycle_fields)
                cycle = cycle_fields{i};
                obj.save_cycle_partitioned(part_dir, cycle, data.(cycle));
                
                % Update index
                if ~isfield(obj.index.cycles, cycle)
                    obj.index.cycles.(cycle) = struct();
                end
                obj.index.cycles.(cycle).last_modified = datestr(now);
            end
            
            % Save geometry data if present
            if isfield(data, 'mapBackGeometry') || isfield(data, 'tiltGeometry')
                obj.save_geometry_partitioned(data, part_dir);
            end
            
            % Save index
            obj.save_json(fullfile(part_dir, 'index.json'), obj.index);
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
    end
end