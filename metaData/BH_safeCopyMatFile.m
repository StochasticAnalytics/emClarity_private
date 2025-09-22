function success = BH_safeCopyMatFile(source_file, dest_file)
%BH_safeCopyMatFile Safely copy MAT files to avoid HDF5 corruption
%
%   success = BH_safeCopyMatFile(source_file, dest_file)
%
%   This function safely copies MATLAB MAT files, particularly v7.3 files
%   that use HDF5 format, which are susceptible to corruption during
%   standard copy operations.
%
%   Inputs:
%       source_file - Path to source MAT file
%       dest_file   - Path to destination MAT file
%
%   Output:
%       success - True if copy succeeded and integrity verified
%
%   The function uses multiple strategies to ensure safe copying:
%   1. Loads and re-saves the file (most reliable for MAT files)
%   2. Falls back to filesystem-level copying with integrity checks
%   3. Verifies file integrity after copying

    success = false;

    if ~exist(source_file, 'file')
        error('BH_safeCopyMatFile:SourceNotFound', 'Source file not found: %s', source_file);
    end

    fprintf('Safely copying %s to %s...\n', source_file, dest_file);

    % Strategy 1: Load and re-save (most reliable for MAT files)
    try
        fprintf('  Attempting load-and-save method...\n');
        temp_data = load(source_file);

        % Create backup if destination exists
        if exist(dest_file, 'file')
            backup_file = sprintf('%s_backup_%s', dest_file, ...
                                  datestr(now, 'yyyymmdd_HHMMSS'));
            copyfile(dest_file, backup_file);
            fprintf('  Created backup: %s\n', backup_file);
        end

        % Save using atomic method
        temp_save_file = sprintf('%s.tmp', dest_file);
        save(temp_save_file, '-struct', 'temp_data', '-v7.3');

        % Force sync and verify
        if isunix()
            system('sync');
            pause(0.05);
        end

        % Check integrity and move
        [is_valid, error_msg] = check_mat_integrity(temp_save_file);
        if is_valid
            movefile(temp_save_file, dest_file);

            % Final verification
            [is_valid_final, ~] = check_mat_integrity(dest_file);
            if is_valid_final
                success = true;
                fprintf('  Successfully copied using load-and-save method\n');
                return;
            else
                fprintf('  Load-and-save method failed final verification\n');
                if exist(dest_file, 'file')
                    delete(dest_file);
                end
            end
        else
            fprintf('  Load-and-save method failed: %s\n', error_msg);
            if exist(temp_save_file, 'file')
                delete(temp_save_file);
            end
        end

    catch ME
        fprintf('  Load-and-save method failed: %s\n', ME.message);
        if exist('temp_save_file', 'var') && exist(temp_save_file, 'file')
            delete(temp_save_file);
        end
    end

    % Strategy 2: Filesystem-level copy with verification
    try
        fprintf('  Attempting filesystem copy with verification...\n');

        % Use MATLAB's copyfile for better compatibility
        [copy_success, copy_msg] = copyfile(source_file, dest_file);
        if ~copy_success
            error('Copy operation failed: %s', copy_msg);
        end

        % Force sync
        if isunix()
            system('sync');
            pause(0.05);
        end

        % Verify integrity
        [is_valid, error_msg] = check_mat_integrity(dest_file);
        if is_valid
            success = true;
            fprintf('  Successfully copied using filesystem method\n');
            return;
        else
            fprintf('  Filesystem copy failed verification: %s\n', error_msg);
            if exist(dest_file, 'file')
                delete(dest_file);
            end
        end

    catch ME
        fprintf('  Filesystem copy failed: %s\n', ME.message);
        if exist(dest_file, 'file')
            delete(dest_file);
        end
    end

    % Strategy 3: Use system rsync with checksum (Unix only)
    if isunix() && ~success
        try
            fprintf('  Attempting rsync with checksum verification...\n');

            % Check if rsync is available
            [rsync_status, ~] = system('which rsync');
            if rsync_status == 0
                rsync_cmd = sprintf('rsync --checksum "%s" "%s"', source_file, dest_file);
                [rsync_result, rsync_output] = system(rsync_cmd);

                if rsync_result == 0
                    % Verify integrity
                    [is_valid, error_msg] = check_mat_integrity(dest_file);
                    if is_valid
                        success = true;
                        fprintf('  Successfully copied using rsync method\n');
                        return;
                    else
                        fprintf('  Rsync copy failed verification: %s\n', error_msg);
                        if exist(dest_file, 'file')
                            delete(dest_file);
                        end
                    end
                else
                    fprintf('  Rsync failed: %s\n', rsync_output);
                end
            else
                fprintf('  Rsync not available on this system\n');
            end

        catch ME
            fprintf('  Rsync method failed: %s\n', ME.message);
        end
    end

    if ~success
        error('BH_safeCopyMatFile:AllMethodsFailed', ...
              'All copy methods failed. File may be corrupted or inaccessible.');
    end
end

function [is_valid, error_msg] = check_mat_integrity(filename)
    %check_mat_integrity Simple integrity check for MAT files

    is_valid = false;
    error_msg = '';

    try
        if ~exist(filename, 'file')
            error_msg = 'File does not exist';
            return;
        end

        file_info = dir(filename);
        if file_info.bytes == 0
            error_msg = 'File is empty';
            return;
        end

        % Try to get variable list
        var_info = whos('-file', filename);
        if isempty(var_info)
            error_msg = 'No variables found';
            return;
        end

        % Try to load a small amount of data
        temp_struct = load(filename, var_info(1).name);
        if isempty(temp_struct)
            error_msg = 'Failed to load variables';
            return;
        end

        is_valid = true;
        error_msg = 'OK';

    catch ME
        if contains(ME.message, 'HDF5') || contains(ME.message, 'inflate')
            error_msg = sprintf('HDF5/compression error: %s', ME.message);
        else
            error_msg = sprintf('Load error: %s', ME.message);
        end
    end
end