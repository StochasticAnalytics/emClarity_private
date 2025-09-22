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
    
    % Determine file path
    if contains(identifier, '.mat')
        mat_file = identifier;
    else
        mat_file = sprintf('%s.mat', identifier);
    end
    
    % Create backup if file exists and is large enough
    if exist(mat_file, 'file')
        file_info = dir(mat_file);
        if file_info.bytes > 1000  % Only backup non-trivial files
            backup_file = sprintf('%s.backup_%s', mat_file, ...
                                  datestr(now, 'yyyymmdd_HHMMSS'));
            try
                copyfile(mat_file, backup_file);
            catch
                warning('BH_saveSubTomoMeta:BackupFailed', ...
                        'Could not create backup of %s', mat_file);
            end
        end
    end
    
    % Atomic save with integrity checking and retry logic
    max_retries = 2;
    success = false;

    fprintf('DEBUG: Starting atomic save for %s\n', mat_file);
    fprintf('DEBUG: subTomoMeta is %s with %d fields\n', class(subTomoMeta), length(fieldnames(subTomoMeta)));
    if isstruct(subTomoMeta) && isfield(subTomoMeta, 'currentCycle')
        fprintf('DEBUG: currentCycle = %s\n', num2str(subTomoMeta.currentCycle));
    end

    % Check available disk space
    if isunix()
        [~, df_output] = system(['df -h "' fileparts(mat_file) '"']);
        fprintf('DEBUG: Disk space info:\n%s\n', df_output);
    end

    for attempt = 1:max_retries
        fprintf('DEBUG: Attempt %d/%d\n', attempt, max_retries);

        try
            % Use temporary file for atomic operation
            temp_file = sprintf('%s.tmp', mat_file);
            fprintf('DEBUG: Using temp file: %s\n', temp_file);

            % Remove any existing temp file
            if exist(temp_file, 'file')
                fprintf('DEBUG: Removing existing temp file\n');
                delete(temp_file);
            end

            % Save to temporary file with v7.3 first
            fprintf('DEBUG: Attempting save with -v7.3 format\n');
            save_start_time = tic;
            try
                save(temp_file, 'subTomoMeta', '-v7.3');
                save_version = 'v7.3';
                save_time = toc(save_start_time);
                fprintf('DEBUG: Save completed in %.2f seconds using %s\n', save_time, save_version);
            catch save_error
                fprintf('DEBUG: v7.3 save failed: %s\n', save_error.message);
                % Fall back to v7 if v7.3 fails
                fprintf('DEBUG: Attempting fallback to -v7 format\n');
                save(temp_file, 'subTomoMeta', '-v7');
                save_version = 'v7';
                save_time = toc(save_start_time);
                fprintf('DEBUG: Fallback save completed in %.2f seconds using %s\n', save_time, save_version);
                warning('BH_saveSubTomoMeta:FallbackFormat', ...
                        'Using -v7 format instead of -v7.3');
            end

            % Check temp file was created and has reasonable size
            if exist(temp_file, 'file')
                temp_info = dir(temp_file);
                fprintf('DEBUG: Temp file created, size = %d bytes\n', temp_info.bytes);
                if temp_info.bytes == 0
                    error('Temp file is empty (0 bytes)');
                end
            else
                error('Temp file was not created');
            end

            % Force filesystem sync to ensure data is written
            if isunix()
                fprintf('DEBUG: Forcing filesystem sync\n');
                sync_start = tic;
                system('sync');
                sync_time = toc(sync_start);
                fprintf('DEBUG: Sync completed in %.2f seconds\n', sync_time);
            end

            % Verify file integrity before moving
            fprintf('DEBUG: Starting integrity check on temp file\n');
            integrity_start = tic;
            [is_valid, error_msg] = check_mat_file_integrity_simple(temp_file);
            integrity_time = toc(integrity_start);
            fprintf('DEBUG: Integrity check completed in %.2f seconds, result: %s\n', integrity_time, error_msg);

            if is_valid
                fprintf('DEBUG: Integrity check passed, attempting atomic move\n');

                % Check if destination exists
                if exist(mat_file, 'file')
                    dest_info = dir(mat_file);
                    fprintf('DEBUG: Destination file exists, size = %d bytes\n', dest_info.bytes);
                end

                % Atomic move (rename)
                move_start = tic;
                [move_success, move_msg] = movefile(temp_file, mat_file);
                move_time = toc(move_start);

                if move_success
                    fprintf('DEBUG: Move completed successfully in %.2f seconds\n', move_time);

                    % Verify destination file
                    if exist(mat_file, 'file')
                        final_info = dir(mat_file);
                        fprintf('DEBUG: Final file size = %d bytes\n', final_info.bytes);
                        success = true;
                        fprintf('DEBUG: Save operation succeeded on attempt %d\n', attempt);
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
                fprintf('DEBUG: Integrity check failed: %s\n', error_msg);
                if exist(temp_file, 'file')
                    fprintf('DEBUG: Cleaning up failed temp file\n');
                    delete(temp_file);
                end
                warning('BH_saveSubTomoMeta:IntegrityCheckFailed', ...
                        'Integrity check failed for attempt %d/%d: %s', attempt, max_retries, error_msg);
            end

        catch ME
            fprintf('DEBUG: Exception caught in attempt %d: %s\n', attempt, ME.message);
            fprintf('DEBUG: Exception identifier: %s\n', ME.identifier);
            if ~isempty(ME.stack)
                fprintf('DEBUG: Exception occurred in: %s at line %d\n', ME.stack(1).name, ME.stack(1).line);
            end

            % Clean up temp file on error
            if exist('temp_file', 'var') && exist(temp_file, 'file')
                fprintf('DEBUG: Cleaning up temp file after exception\n');
                delete(temp_file);
            end

            if attempt == max_retries
                fprintf('DEBUG: Final attempt failed, will rethrow error\n');
                success = false;
                rethrow(ME);
            else
                warning('BH_saveSubTomoMeta:SaveAttemptFailed', ...
                        'Save attempt %d/%d failed: %s. Retrying...', ...
                        attempt, max_retries, ME.message);
                fprintf('DEBUG: Pausing 0.1 seconds before retry\n');
                pause(0.1); % Brief pause before retry
            end
        end
    end

    % Final check - if we exit the loop without success, something went wrong
    if ~success
        fprintf('DEBUG: All attempts failed, throwing final error\n');
        error('BH_saveSubTomoMeta:SaveFailed', ...
              'Failed to save %s after %d attempts', mat_file, max_retries);
    end

    fprintf('DEBUG: Save operation completed successfully\n');
end

function [is_valid, error_msg] = check_mat_file_integrity_simple(filename)
    %check_mat_file_integrity_simple Simple integrity check for MAT files
    %   Returns [is_valid, error_msg] where is_valid is true if file can be loaded successfully

    is_valid = false;
    error_msg = '';

    fprintf('DEBUG: Integrity check starting for %s\n', filename);

    try
        % Basic file existence and size check
        if ~exist(filename, 'file')
            error_msg = 'File does not exist';
            fprintf('DEBUG: Integrity check failed - file does not exist\n');
            return;
        end

        file_info = dir(filename);
        fprintf('DEBUG: File exists, size = %d bytes\n', file_info.bytes);
        if file_info.bytes == 0
            error_msg = 'File is empty (0 bytes)';
            fprintf('DEBUG: Integrity check failed - file is empty\n');
            return;
        end

        % Try to get variable information without loading full data
        fprintf('DEBUG: Getting variable information\n');
        var_info_start = tic;
        var_info = whos('-file', filename);
        var_info_time = toc(var_info_start);
        fprintf('DEBUG: Variable info completed in %.2f seconds\n', var_info_time);

        if isempty(var_info)
            error_msg = 'No variables found in file';
            fprintf('DEBUG: Integrity check failed - no variables found\n');
            return;
        end

        % Check that subTomoMeta variable exists
        var_names = {var_info.name};
        fprintf('DEBUG: Found %d variables: %s\n', length(var_names), strjoin(var_names, ', '));
        if ~ismember('subTomoMeta', var_names)
            error_msg = sprintf('subTomoMeta variable not found (found: %s)', strjoin(var_names, ', '));
            fprintf('DEBUG: Integrity check failed - subTomoMeta variable not found\n');
            return;
        end

        % Get subTomoMeta variable info
        submeta_info = var_info(strcmp(var_names, 'subTomoMeta'));
        fprintf('DEBUG: subTomoMeta variable: size = [%s], class = %s, bytes = %d\n', ...
                num2str(submeta_info.size), submeta_info.class, submeta_info.bytes);

        % Try to load the structure - this will catch HDF5 corruption
        fprintf('DEBUG: Attempting to load subTomoMeta structure\n');
        load_start = tic;
        temp_struct = load(filename, 'subTomoMeta');
        load_time = toc(load_start);
        fprintf('DEBUG: Load completed in %.2f seconds\n', load_time);

        if ~isfield(temp_struct, 'subTomoMeta')
            error_msg = 'subTomoMeta field not found in loaded structure';
            fprintf('DEBUG: Integrity check failed - subTomoMeta field not found after load\n');
            return;
        end

        if ~isstruct(temp_struct.subTomoMeta)
            error_msg = 'subTomoMeta is not a valid structure';
            fprintf('DEBUG: Integrity check failed - subTomoMeta is not a structure (class: %s)\n', class(temp_struct.subTomoMeta));
            return;
        end

        % Basic structure validation
        loaded_meta = temp_struct.subTomoMeta;
        loaded_fields = fieldnames(loaded_meta);
        fprintf('DEBUG: Loaded structure has %d fields: %s\n', length(loaded_fields), strjoin(loaded_fields, ', '));

        % Check for key fields
        if isfield(loaded_meta, 'currentCycle')
            fprintf('DEBUG: currentCycle = %s\n', num2str(loaded_meta.currentCycle));
        else
            fprintf('DEBUG: currentCycle field not found\n');
        end

        % If we get here, file passed all checks
        is_valid = true;
        error_msg = 'OK';
        fprintf('DEBUG: Integrity check passed successfully\n');

    catch ME
        fprintf('DEBUG: Exception during integrity check: %s\n', ME.message);
        fprintf('DEBUG: Exception identifier: %s\n', ME.identifier);
        if ~isempty(ME.stack)
            fprintf('DEBUG: Exception in: %s at line %d\n', ME.stack(1).name, ME.stack(1).line);
        end

        % Any error during loading indicates corruption
        if contains(ME.message, 'HDF5') || contains(ME.message, 'inflate')
            % Specific corruption patterns
            error_msg = sprintf('HDF5/compression error: %s', ME.message);
            is_valid = false;
            fprintf('DEBUG: Detected HDF5/compression corruption\n');
        else
            % Other errors might still indicate corruption
            error_msg = sprintf('Load error: %s', ME.message);
            is_valid = false;
            fprintf('DEBUG: Detected general load error\n');
        end
    end
end