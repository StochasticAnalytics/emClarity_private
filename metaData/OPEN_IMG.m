function [ vol ] = OPEN_IMG(precision, filename, varargin)

    if isa(filename, 'MRCImage')
        vol = getVolume(filename, varargin{:});
    else 
        if isfile(filename)
            vol = getVolume(MRCImage(filename), varargin{:});
        else
            error('\n\nFile does not exist: %s\n\n', filename);
        end
    end

    if strcmp(precision, 'single')
        vol = single(vol);
    elseif strcmp(precision, 'double')
        vol = double(vol);
    else
        error('Unknown precision');
    end
    

end