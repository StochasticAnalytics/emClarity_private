function [ pool ] = EMC_parpool(nWorkers)
%Make a local copy of the default cluster, and modify the job storage
%location


local_cache_root = getenv('MCR_CACHE_ROOT');
if isempty(local_cache_root)
  fprintf('\nWARNING: the variable MCR_CACHE_ROOT is not set!\n');
  EMC_ROOT = getenv('EMC_CACHE_DIR');
  if isempty(EMC_ROOT)
    error('\nWARNING: the variable EMC_CACHE_ROOT is not set!\n');
  else
    error('\The variable EMC_CACHE_ROOT %s\n',EMC_ROOT);
  end
end


% Build a local cluster with a per-process JobStorageLocation and start the pool
% directly from the cluster OBJECT.  We intentionally do NOT saveAsProfile(): that
% persists the profile into the shared per-user settings store
% (prefdir -> ~/.matlab/<release>/matlab.mlsettings).  Under the driver many
% emClarity processes start pools concurrently on one host, and concurrent writes to
% that single shared file race -> intermittent exit 249 (write error) or a futex
% deadlock (hang).  Passing the object straight to parpool starts an identical pool
% with no write to the shared store, eliminating the race at the source.
% (verified interactively on salina 2026-07-15: parpool(object) starts + runs + tears
%  down a pool with saveAsProfile removed, live shared DB mtime untouched.)
emc_parcluster = parcluster(parallel.defaultClusterProfile);
emc_parcluster.JobStorageLocation = local_cache_root;

% Clean up any existing parpool before creating new one
% This consolidates cleanup logic that was scattered throughout the codebase
current_pool = gcp('nocreate');
if ~isempty(current_pool)
    fprintf('Cleaning up existing parpool (%d workers)\n', current_pool.NumWorkers);
    delete(current_pool);
end

[ pool ] = parpool(emc_parcluster, nWorkers);

end

