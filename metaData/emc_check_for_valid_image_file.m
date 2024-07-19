function [ is_valid ] = emc_check_for_valid_image_file(wanted_filename)

    % Check if the file exists
    fprintf('Checking if file exists: %s\n', wanted_filename);
    if isfile(wanted_filename)
        try 
            fprintf('Attempting to read file: %s\n', wanted_filename);
            test_header = MRCImage(wanted_filename, 0);
            fprintf('Reading file: %s\n', wanted_filename);
            % From the @MRCImage class
            is_valid = checkFullFile(test_header);
        catch
            fprintf('Error reading file: %s\n', wanted_filename);
            system(['rm ' wanted_filename]);
            is_valid = false;
        end
    else
        is_valid = false;
    end

end