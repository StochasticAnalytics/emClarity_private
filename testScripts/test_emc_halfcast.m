function test_emc_halfcast(nIter, N)
% Standalone validation for the rewritten emc_halfcast / mexFP16.
%   - correctness of the host<->host round trip (the @MRCImage / SAVE_IMG path)
%   - correctness + GPU-memory-leak check of host-uint16 -> gpu-single readback
%     (the template-search path that previously returned all zeros -> NaNs)
%
% Run from MATLAB after recompiling the mex:
%   cd /sa_shared/git/emClarity_private
%   addpath(genpath(pwd));
%   mexCompile('mexFP16');   clear mexFP16;     % rebuild + reload
%   test_emc_halfcast(30, 512)
%
% A loop "similar to TM regarding no clears": gpu_single is NOT explicitly
% cleared inside the loop, just overwritten next iteration. If MATLAB's
% reference counting frees the returned gpuArray, free memory stays flat; a
% leak shows as a monotonic decline in GPU free memory.

    if nargin < 1 || isempty(nIter), nIter = 30; end
    if nargin < 2 || isempty(N),     N = 512;    end

    g = gpuDevice();
    fprintf('GPU: %s | %.1f GB total | %.2f GB free at start\n', ...
            g.Name, g.TotalMemory/1e9, g.AvailableMemory/1e9);

    % --- reference: a host single volume in a realistic (normalized-tomo) range ---
    rng(7);
    host_single = single(randn(N, N, N));
    n = numel(host_single);
    fprintf('volume %d^3 = %d elements  (%.2f GB single / %.2f GB uint16)\n\n', ...
            N, n, 4*n/1e9, 2*n/1e9);

    % =================== 1) host <-> host round trip ===================
    h_u16  = emc_halfcast(host_single);          % single  -> uint16 (host)
    assert(strcmp(underlyingType(h_u16),'uint16') && ~isa(h_u16,'gpuArray'), 'pack: wrong type/device');
    h_back = emc_halfcast(h_u16);                % uint16 -> single (host)
    assert(strcmp(underlyingType(h_back),'single') && ~isa(h_back,'gpuArray'), 'unpack: wrong type/device');
    err_host = max(abs(h_back(:) - host_single(:)));
    nan_host = nnz(isnan(h_back(:)));
    fprintf('[host<->host]  nan=%d  max FP16 round-trip err=%.5g\n', nan_host, err_host);

    % =================== 2) host-uint16 -> gpu-single, leak loop ===================
    base_free = g.AvailableMemory;
    fprintf('\n[host-u16 -> gpu-single] %d iters, FRESH randn each iter, no in-loop clears. base free=%.3f GB\n', ...
            nIter, base_free/1e9);
    worst_err = 0; worst_nan = 0;
    for it = 1:nIter
        host_single = single(randn(N, N, N));                   % fresh data + fresh host allocs each iter
        h_u16       = emc_halfcast(host_single);                % pack:   single -> uint16 (host)
        gpu_single  = emc_halfcast(h_u16, true);                % unpack: uint16 -> single (gpu)  <-- was all-zeros/NaN
        assert(isa(gpu_single,'gpuArray') && strcmp(underlyingType(gpu_single),'single'), ...
               'readback: wrong type/device');
        gs   = gather(gpu_single);                              % force eval + bring back to compare
        sumv = sum(double(gs(:)));
        e    = max(abs(gs(:) - host_single(:)));
        nanc = nnz(isnan(gs(:)));
        worst_err = max(worst_err, e); worst_nan = max(worst_nan, nanc);
        wait(g);
        % free here reflects ONE resident gpu_single (~size of the volume); the
        % number should be ~constant across iters if there is no leak.
        fprintf('  it %2d  free %.3f GB  d_base %+8.1f MB | sum=%.4e  err=%.4g  nan=%d\n', ...
                it, g.AvailableMemory/1e9, (g.AvailableMemory-base_free)/1e6, sumv, e, nanc);
    end

    % Release the last resident arrays and re-measure: net change vs base is the leak.
    clear gpu_single gs host_single h_u16; wait(g);
    net = (g.AvailableMemory - base_free)/1e6;

    fprintf('\nSUMMARY: worst FP16 err=%.4g  worst nan=%d  net GPU free change=%+.1f MB (after clear)\n', ...
            worst_err, worst_nan, net);
    if (worst_nan == 0) && (nan_host == 0) && (worst_err < 1e-2) && (err_host < 1e-2) && (abs(net) < 50)
        fprintf('PASS: correct round trips, no NaNs, no GPU memory leak.\n');
    else
        fprintf('CHECK: inspect nan / err / net above (PASS wants nan=0, err<1e-2, |net|<50 MB).\n');
    end
end
