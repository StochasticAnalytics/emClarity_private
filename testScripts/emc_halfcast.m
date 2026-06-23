function [output_vol] =  emc_halfcast(input_vol, swap_host_device)
% Convert between single and FP16-packed uint16, returning a NEW, MATLAB-owned
% array. The direction is inferred from the input precision:
%     single  ->  uint16 (FP16 bit pattern)
%     uint16  ->  single
%
% By default the output is on the SAME device as the input. Pass
% swap_host_device = true to put the output on the OTHER device (e.g. a
% host-uint16 tomogram -> single gpuArray for processing).
%
% Under the hood mexFP16 allocates the output (mxGPUCreateGPUArray for a
% gpuArray, mxCreateNumericArray for a host array) and returns it; MATLAB then
% owns and reference-counts it exactly like the result of gpuArray(x). When the
% output is a gpuArray the conversion runs on the GPU, so a host-uint16 ->
% gpu-single cast moves only the uint16 bytes across PCIe and never builds a
% single-precision copy on the host.

    if nargin < 2
        swap_host_device = false;
    end

    % I'm not sure why, but this breaks when numel == 1
    if ~(numel(input_vol) > 1)
       error('Input volume to emc_halfcast must have more than one element\n');
    end

    % Determine direction from the input precision.
    switch underlyingType(input_vol)
        case 'uint16'
            to_half = false;   % uint16 (FP16) -> single
        case 'single'
            to_half = true;    % single -> uint16 (FP16)
        otherwise
            error('Unknown precision');
    end

    % Where the output should live: same device by default, the other on swap.
    input_on_gpu = isa(input_vol, 'gpuArray');
    if (swap_host_device)
        output_on_gpu = ~input_on_gpu;
    else
        output_on_gpu =  input_on_gpu;
    end

    output_vol = mexFP16(input_vol, logical(to_half), logical(output_on_gpu), int64(numel(input_vol)));

end
