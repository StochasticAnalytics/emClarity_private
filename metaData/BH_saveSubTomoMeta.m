function success = BH_saveSubTomoMeta(identifier, subTomoMeta)
%BH_saveSubTomoMeta Save metadata using wrapper class or legacy method
%
%   success = BH_saveSubTomoMeta(identifier, subTomoMeta)
%
%   This function provides a unified interface for saving metadata,
%   handling both wrapper objects and raw structs.
%
%   Inputs:
%       identifier - Project name or path to save metadata (e.g., emc.('subTomoMeta'))
%       subTomoMeta - Metadata to save (wrapper object or struct)
%
%   Output:
%       success - True if save succeeded

    success = false;
    
    try
        % Check what type of data we have
        if isa(subTomoMeta, 'BH_subTomoMeta')
            % It's a wrapper object, use its save method
            subTomoMeta.save();
            success = true;
            
        elseif isstruct(subTomoMeta)
            % It's a raw struct, save using legacy method
            success = save_legacy(identifier, subTomoMeta);
            
        else
            error('BH_saveSubTomoMeta:InvalidType', ...
                  'subTomoMeta must be a struct or BH_subTomoMeta object');
        end
        
    catch ME
        warning('BH_saveSubTomoMeta:SaveFailed', ...
                'Failed to save metadata: %s', ME.message);
        
        % Try to save a backup if possible
        if isstruct(subTomoMeta)
            try
                backup_file = sprintf('%s_emergency_backup_%s.mat', ...
                                      identifier, datestr(now, 'yyyymmdd_HHMMSS'));
                save(backup_file, 'subTomoMeta', '-v7.3');
                warning('BH_saveSubTomoMeta:BackupSaved', ...
                        'Emergency backup saved to %s', backup_file);
            catch
                % Even backup failed
            end
        end
        
        rethrow(ME);
    end
end

function success = save_legacy(identifier, subTomoMeta)
    %save_legacy Save metadata using traditional method

    % Verbose DEBUG output gated behind EMC_SAVE_VERBOSE (default off) to keep the
    % diary clean. Defined before any file operation, so every write this function
    % performs is loggable: a copy that runs before the handle exists is a write
    % you cannot see when diagnosing a file that arrived corrupt.
    verbose = ~isempty(getenv('EMC_SAVE_VERBOSE'));
    dbg = @(varargin) verbose && fprintf(varargin{:});

    % Determine file path
    if contains(identifier, '.mat')
        mat_file = identifier;
    else
        mat_file = sprintf('%s.mat', identifier);
    end

    % No pre-write copy of the existing file. The original stays at mat_file until
    % a verified temp is renamed over it, so a bad write cannot destroy the good
    % copy -- a backup would insure against a failure the rename already prevents.
    
    % Atomic save with integrity checking and retry logic
    max_retries = 2;
    success = false;

    dbg('DEBUG: Starting atomic save for %s\n', mat_file);
    dbg('DEBUG: subTomoMeta is %s with %d fields\n', class(subTomoMeta), length(fieldnames(subTomoMeta)));
    if isstruct(subTomoMeta) && isfield(subTomoMeta, 'currentCycle')
        dbg('DEBUG: currentCycle = %s\n', num2str(subTomoMeta.currentCycle));
    end

    % Check available disk space. fileparts returns empty for a bare filename, so
    % this probed df with an empty path and reported nothing for every identifier
    % carrying no directory component -- removing the one signal that explains a
    % short write. The status is checked because a probe that fails silently is
    % worse than no probe: it looks like it ran.
    if isunix()
        target_dir = fileparts(mat_file);
        if isempty(target_dir)
            target_dir = pwd;
        end
        [df_status, df_output] = system(['df -h "' target_dir '"']);
        if df_status == 0
            dbg('DEBUG: Disk space for %s:\n%s\n', target_dir, df_output);
        else
            dbg('DEBUG: df probe FAILED on %s (status %d): %s\n', ...
                target_dir, df_status, strtrim(df_output));
        end
    end

    for attempt = 1:max_retries
        dbg('DEBUG: Attempt %d/%d\n', attempt, max_retries);

        try
            % Use temporary file for atomic operation with .mat extension
            temp_file = sprintf('%s.tmp.mat', mat_file);
            dbg('DEBUG: Using temp file: %s\n', temp_file);

            % Remove any existing temp file
            if exist(temp_file, 'file')
                dbg('DEBUG: Removing existing temp file\n');
                delete(temp_file);
                pause(0.1); % Brief pause to ensure deletion completes
            end

            % Try -v7 format first for better compatibility
            % (v7.3 can have issues with immediate loading)
            dbg('DEBUG: Attempting save with -v7 format\n');
            save_start_time = tic;
            try
                save(temp_file, 'subTomoMeta', '-v7');
                save_version = 'v7';
                save_time = toc(save_start_time);
                dbg('DEBUG: Save completed in %.2f seconds using %s\n', save_time, save_version);
            catch save_error
                dbg('DEBUG: v7 save failed: %s\n', save_error.message);
                % Fall back to v7.3 if v7 fails (e.g., file too large)
                dbg('DEBUG: Attempting fallback to -v7.3 format\n');
                save(temp_file, 'subTomoMeta', '-v7.3');
                save_version = 'v7.3';
                save_time = toc(save_start_time);
                dbg('DEBUG: Fallback save completed in %.2f seconds using %s\n', save_time, save_version);
                warning('BH_saveSubTomoMeta:UsingV73Format', ...
                        'Using -v7.3 format due to file size or complexity');
            end

            % Check temp file was created and has reasonable size
            if exist(temp_file, 'file')
                temp_info = dir(temp_file);
                dbg('DEBUG: Temp file created, size = %d bytes\n', temp_info.bytes);
                if temp_info.bytes == 0
                    error('Temp file is empty (0 bytes)');
                end
            else
                error('Temp file was not created');
            end

            % For v7.3 files, add extra wait time and multiple sync attempts
            if strcmp(save_version, 'v7.3')
                dbg('DEBUG: v7.3 format detected, adding extra sync time\n');
                pause(0.5);  % Give HDF5 library time to fully flush

                % Multiple sync attempts for HDF5 files
                if isunix()
                    for sync_attempt = 1:3
                        dbg('DEBUG: Forcing filesystem sync (attempt %d/3)\n', sync_attempt);
                        sync_start = tic;
                        system('sync');
                        sync_time = toc(sync_start);
                        dbg('DEBUG: Sync %d completed in %.2f seconds\n', sync_attempt, sync_time);
                        pause(0.1);
                    end
                end
            else
                % Single sync for v7 format
                if isunix()
                    dbg('DEBUG: Forcing filesystem sync\n');
                    sync_start = tic;
                    system('sync');
                    sync_time = toc(sync_start);
                    dbg('DEBUG: Sync completed in %.2f seconds\n', sync_time);
                end
            end

            % Add a brief pause to ensure file operations complete
            pause(0.2);

            % Verify file integrity before moving
            dbg('DEBUG: Starting integrity check on temp file\n');
            integrity_start = tic;
            [is_valid, error_msg] = check_mat_file_integrity_robust(temp_file, save_version);
            integrity_time = toc(integrity_start);
            dbg('DEBUG: Integrity check completed in %.2f seconds, result: %s\n', integrity_time, error_msg);

            if is_valid
                dbg('DEBUG: Integrity check passed, attempting atomic move\n');

                % Check if destination exists
                if exist(mat_file, 'file')
                    dest_info = dir(mat_file);
                    dbg('DEBUG: Destination file exists, size = %d bytes\n', dest_info.bytes);
                end

                % Atomic move (rename)
                move_start = tic;
                [move_success, move_msg] = movefile(temp_file, mat_file);
                move_time = toc(move_start);

                if move_success
                    dbg('DEBUG: Move completed successfully in %.2f seconds\n', move_time);

                    % Verify destination file
                    if exist(mat_file, 'file')
                        final_info = dir(mat_file);
                        dbg('DEBUG: Final file size = %d bytes\n', final_info.bytes);
                        success = true;
                        dbg('DEBUG: Save operation succeeded on attempt %d\n', attempt);
                        fprintf('Saved %s using %s format\n', mat_file, save_version);
                        break;
                    else
                        error('Destination file does not exist after move');
                    end
                else
                    error('Move operation failed: %s', move_msg);
                end
            else
                % Integrity check failed
                dbg('DEBUG: Integrity check failed: %s\n', error_msg);
                if exist(temp_file, 'file')
                    dbg('DEBUG: Cleaning up failed temp file\n');
                    delete(temp_file);
                end
                warning('BH_saveSubTomoMeta:IntegrityCheckFailed', ...
                        'Integrity check failed for attempt %d/%d: %s', attempt, max_retries, error_msg);
            end

        catch ME
            dbg('DEBUG: Exception caught in attempt %d: %s\n', attempt, ME.message);
            dbg('DEBUG: Exception identifier: %s\n', ME.identifier);
            if ~isempty(ME.stack)
                dbg('DEBUG: Exception occurred in: %s at line %d\n', ME.stack(1).name, ME.stack(1).line);
            end

            % Clean up temp file on error
            if exist('temp_file', 'var') && exist(temp_file, 'file')
                dbg('DEBUG: Cleaning up temp file after exception\n');
                delete(temp_file);
            end

            if attempt == max_retries
                dbg('DEBUG: Final attempt failed, will rethrow error\n');
                success = false;
                rethrow(ME);
            else
                warning('BH_saveSubTomoMeta:SaveAttemptFailed', ...
                        'Save attempt %d/%d failed: %s. Retrying...', ...
                        attempt, max_retries, ME.message);
                dbg('DEBUG: Pausing 0.5 seconds before retry\n');
                pause(0.5); % Longer pause before retry
            end
        end
    end

    % Final check - if we exit the loop without success, something went wrong
    if ~success
        dbg('DEBUG: All attempts failed, throwing final error\n');
        error('BH_saveSubTomoMeta:SaveFailed', ...
              'Failed to save %s after %d attempts', mat_file, max_retries);
    end

    dbg('DEBUG: Save operation completed successfully\n');
end

function [is_valid, error_msg] = check_mat_file_integrity_robust(filename, format_version)
    %check_mat_file_integrity_robust Verify a written MAT file loads
    %   Returns [is_valid, error_msg]. format_version ('v7' or 'v7.3') selects
    %   format-specific retry quirks.
    %
    %   WHY the load alone is the integrity check: v7 data elements are zlib
    %   streams carrying an Adler-32 of the uncompressed bytes, which inflate
    %   verifies. A truncated file fails on a short stream and a bit-rotted one
    %   fails the checksum, so neither can reach the end of a successful load.
    %   Comparing the result against the in-memory source would add coverage only
    %   for a self-consistently wrong serialization, at the price of walking the
    %   whole structure.

    is_valid = false;
    error_msg = '';

    verbose = ~isempty(getenv('EMC_SAVE_VERBOSE'));
    dbg = @(varargin) verbose && fprintf(varargin{:});
    dbg('DEBUG: Integrity check starting for %s (format: %s)\n', filename, format_version);

    try
        % Basic file existence and size check
        if ~exist(filename, 'file')
            error_msg = 'File does not exist';
            dbg('DEBUG: Integrity check failed - file does not exist\n');
            return;
        end

        file_info = dir(filename);
        dbg('DEBUG: File exists, size = %d bytes\n', file_info.bytes);
        if file_info.bytes == 0
            error_msg = 'File is empty (0 bytes)';
            dbg('DEBUG: Integrity check failed - file is empty\n');
            return;
        end

        % Try to get variable information without loading full data
        dbg('DEBUG: Getting variable information\n');
        var_info_start = tic;

        % For v7.3 files, whos might not work immediately after save
        max_whos_attempts = 3;
        var_info = [];
        for whos_attempt = 1:max_whos_attempts
            try
                var_info = whos('-file', filename);
                if ~isempty(var_info)
                    break;
                end
            catch whos_error
                if whos_attempt < max_whos_attempts
                    dbg('DEBUG: whos attempt %d failed, retrying...\n', whos_attempt);
                    pause(0.2);
                else
                    rethrow(whos_error);
                end
            end
        end

        var_info_time = toc(var_info_start);
        dbg('DEBUG: Variable info completed in %.2f seconds\n', var_info_time);

        if isempty(var_info)
            error_msg = 'No variables found in file';
            dbg('DEBUG: Integrity check failed - no variables found\n');
            return;
        end

        % Check that subTomoMeta variable exists
        var_names = {var_info.name};
        dbg('DEBUG: Found %d variables: %s\n', length(var_names), strjoin(var_names, ', '));
        if ~ismember('subTomoMeta', var_names)
            error_msg = sprintf('subTomoMeta variable not found (found: %s)', strjoin(var_names, ', '));
            dbg('DEBUG: Integrity check failed - subTomoMeta variable not found\n');
            return;
        end

        % Get subTomoMeta variable info
        submeta_info = var_info(strcmp(var_names, 'subTomoMeta'));
        dbg('DEBUG: subTomoMeta variable: size = [%s], class = %s, bytes = %d\n', ...
                num2str(submeta_info.size), submeta_info.class, submeta_info.bytes);

        % For v7.3 format, try multiple load attempts with delays
        if strcmp(format_version, 'v7.3')
            dbg('DEBUG: Using robust loading for v7.3 format\n');
            max_load_attempts = 3;
            load_successful = false;

            for load_attempt = 1:max_load_attempts
                dbg('DEBUG: Load attempt %d/%d\n', load_attempt, max_load_attempts);
                try
                    load_start = tic;
                    temp_struct = load(filename, '-mat', 'subTomoMeta');
                    load_time = toc(load_start);
                    dbg('DEBUG: Load completed in %.2f seconds\n', load_time);
                    load_successful = true;
                    break;
                catch load_error
                    dbg('DEBUG: Load attempt %d failed: %s\n', load_attempt, load_error.message);
                    if load_attempt < max_load_attempts
                        dbg('DEBUG: Waiting before retry...\n');
                        pause(0.5 * load_attempt); % Increasing delay
                    else
                        rethrow(load_error);
                    end
                end
            end

            if ~load_successful
                error('Failed to load after multiple attempts');
            end
        else
            % Standard load for v7 format - explicitly specify -mat flag
            dbg('DEBUG: Attempting to load subTomoMeta structure (with -mat flag)\n');
            load_start = tic;
            temp_struct = load(filename, '-mat', 'subTomoMeta');
            load_time = toc(load_start);
            dbg('DEBUG: Load completed in %.2f seconds\n', load_time);
        end

        if ~isfield(temp_struct, 'subTomoMeta')
            error_msg = 'subTomoMeta field not found in loaded structure';
            dbg('DEBUG: Integrity check failed - subTomoMeta field not found after load\n');
            return;
        end

        loaded_meta = temp_struct.subTomoMeta;

        % Type check before fieldnames, so a non-struct reports what it actually is
        % rather than surfacing as a generic fieldnames error from the catch below.
        if ~isstruct(loaded_meta)
            error_msg = sprintf('subTomoMeta is not a struct (class: %s)', class(loaded_meta));
            dbg('DEBUG: Integrity check failed - subTomoMeta is not a struct\n');
            return;
        end

        loaded_fields = fieldnames(loaded_meta);
        dbg('DEBUG: Loaded structure has %d fields: %s\n', length(loaded_fields), strjoin(loaded_fields, ', '));

        is_valid = true;
        error_msg = 'OK';
        dbg('DEBUG: Integrity check passed successfully\n');

    catch ME
        dbg('DEBUG: Exception during integrity check: %s\n', ME.message);
        dbg('DEBUG: Exception identifier: %s\n', ME.identifier);
        if ~isempty(ME.stack)
            dbg('DEBUG: Exception in: %s at line %d\n', ME.stack(1).name, ME.stack(1).line);
        end

        % Any error during loading indicates corruption
        if contains(ME.message, 'HDF5') || contains(ME.message, 'inflate')
            % Specific corruption patterns
            error_msg = sprintf('HDF5/compression error: %s', ME.message);
            is_valid = false;
            dbg('DEBUG: Detected HDF5/compression corruption\n');
        else
            % Other errors might still indicate corruption
            error_msg = sprintf('Load error: %s', ME.message);
            is_valid = false;
            dbg('DEBUG: Detected general load error\n');
        end
    end
end
