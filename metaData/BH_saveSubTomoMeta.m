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
    
    % Save the file
    try
        % Use v7.3 for large file support
        save(mat_file, 'subTomoMeta', '-v7.3');
        success = true;
        
    catch ME
        % Try v7 if v7.3 fails
        try
            save(mat_file, 'subTomoMeta', '-v7');
            success = true;
            warning('BH_saveSubTomoMeta:FallbackFormat', ...
                    'Saved using -v7 format instead of -v7.3');
        catch
            success = false;
            rethrow(ME);
        end
    end
end