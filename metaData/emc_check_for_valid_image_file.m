function [ is_valid ] = emc_check_for_valid_image_file(wanted_filename)

    is_valid = true;
    is_file = false;
    % Check if the file exists
    %fprintf('Checking if file exists: %s\n', wanted_filename);
    if isfile(wanted_filename)
        is_file = true;
        try 
            fprintf('Attempting to read file: %s\n', wanted_filename);
            test_header = MRCImage(wanted_filename, 0);
        catch
            is_valid = false;
        end
        if is_valid
            % So all we know is that the header was readable, now check that there are at least the right number of bytes in the file
            is_valid = checkFullFile(test_header);
        end
    else
        is_valid = false;
    end

    if ( is_file && ~is_valid )
        % fprintf('Error reading file: %s\n', wanted_filename);
        system([sprintf('rm -f %s',wanted_filename)]);
    end

end