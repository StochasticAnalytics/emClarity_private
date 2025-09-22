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

    for attempt = 1:max_retries
        try
            % Use temporary file for atomic operation
            temp_file = sprintf('%s.tmp', mat_file);

            % Save to temporary file with v7.3 first
            try
                save(temp_file, 'subTomoMeta', '-v7.3');
                save_version = 'v7.3';
            catch
                % Fall back to v7 if v7.3 fails
                save(temp_file, 'subTomoMeta', '-v7');
                save_version = 'v7';
                warning('BH_saveSubTomoMeta:FallbackFormat', ...
                        'Using -v7 format instead of -v7.3');
            end

            % Force filesystem sync to ensure data is written
            if isunix()
                system('sync');
            end

            % Verify file integrity before moving
            [is_valid, error_msg] = check_mat_file_integrity_simple(temp_file);
            if is_valid
                % Atomic move (rename)
                movefile(temp_file, mat_file);
                success = true;
                fprintf('Saved %s using %s format\n', mat_file, save_version);
                break;
            else
                % Integrity check failed
                if exist(temp_file, 'file')
                    delete(temp_file);
                end
                warning('BH_saveSubTomoMeta:IntegrityCheckFailed', ...
                        'Integrity check failed for attempt %d/%d: %s', attempt, max_retries, error_msg);
            end

        catch ME
            % Clean up temp file on error
            if exist('temp_file', 'var') && exist(temp_file, 'file')
                delete(temp_file);
            end

            if attempt == max_retries
                success = false;
                rethrow(ME);
            else
                warning('BH_saveSubTomoMeta:SaveAttemptFailed', ...
                        'Save attempt %d/%d failed: %s. Retrying...', ...
                        attempt, max_retries, ME.message);
                pause(0.1); % Brief pause before retry
            end
        end
    end

    % Final check - if we exit the loop without success, something went wrong
    if ~success
        error('BH_saveSubTomoMeta:SaveFailed', ...
              'Failed to save %s after %d attempts', mat_file, max_retries);
    end
end

function [is_valid, error_msg] = check_mat_file_integrity_simple(filename)
    %check_mat_file_integrity_simple Simple integrity check for MAT files
    %   Returns [is_valid, error_msg] where is_valid is true if file can be loaded successfully

    is_valid = false;
    error_msg = '';

    try
        % Basic file existence and size check
        if ~exist(filename, 'file')
            error_msg = 'File does not exist';
            return;
        end

        file_info = dir(filename);
        if file_info.bytes == 0
            error_msg = 'File is empty (0 bytes)';
            return;
        end

        % Try to get variable information without loading full data
        var_info = whos('-file', filename);
        if isempty(var_info)
            error_msg = 'No variables found in file';
            return;
        end

        % Check that subTomoMeta variable exists
        var_names = {var_info.name};
        if ~ismember('subTomoMeta', var_names)
            error_msg = sprintf('subTomoMeta variable not found (found: %s)', strjoin(var_names, ', '));
            return;
        end

        % Try to load the structure - this will catch HDF5 corruption
        temp_struct = load(filename, 'subTomoMeta');
        if ~isfield(temp_struct, 'subTomoMeta') || ~isstruct(temp_struct.subTomoMeta)
            error_msg = 'subTomoMeta is not a valid structure';
            return;
        end

        % If we get here, file passed all checks
        is_valid = true;
        error_msg = 'OK';

    catch ME
        % Any error during loading indicates corruption
        if contains(ME.message, 'HDF5') || contains(ME.message, 'inflate')
            % Specific corruption patterns
            error_msg = sprintf('HDF5/compression error: %s', ME.message);
            is_valid = false;
        else
            % Other errors might still indicate corruption
            error_msg = sprintf('Load error: %s', ME.message);
            is_valid = false;
        end
    end
end