function outPath = EMC_checkCacheForFile(alt_cache, relPath)
% EMC_checkCacheForFile
% Resolve a cached file path, falling back to alternate cache directories.
%
% Usage:
%   outPath = EMC_checkCacheForFile(alt_cache, relPath)
%
% Inputs
%   alt_cache - cell array of alternate cache base directories (may be empty {})
%   relPath   - string/char path expected to start with 'cache/'
%
% Behavior
%   1) Hard error if relPath does not start with 'cache/'.
%   2) If relPath exists on disk, return it unchanged.
%   3) Otherwise, use alt_cache; error if empty.
%   4) For each alt cache base, replace the leading 'cache/' with base and
%      return the first path that exists. If none exist, return the original relPath.
%
% Notes
%   - This helper is intended only for cached image files under cache/.
%   - alt_cache entries should be writable directories (validated at parse time).

DEBUG = true; % set true for verbose debug prints

% Validate inputs
if nargin < 2
  error('EMC_checkCacheForFile: two input arguments required: (alt_cache, relPath)');
end

% Normalize relPath to char
if isstring(relPath)
  relPath = char(relPath);
end
if ~ischar(relPath)
  error('EMC_checkCacheForFile: relPath must be a string or char');
end

prefix = 'cache/';
if ~strncmp(relPath, prefix, numel(prefix))
  error('EMC_checkCacheForFile: path must start with "%s" (got "%s")', prefix, relPath);
end

if DEBUG
  fprintf('EMC_checkCacheForFile: checking primary cache path: %s\n', relPath);
end

if exist(relPath, 'file') == 2
  if DEBUG
    fprintf('EMC_checkCacheForFile: found at primary cache: %s\n', relPath);
  end
  outPath = relPath;
  return;
end

% Use provided alt_cache list
alt_list = alt_cache;
if isempty(alt_list)
  error('EMC_checkCacheForFile: not found in cache/ and alt_cache is empty: %s', relPath);
end
if ~iscell(alt_list)
  alt_list = {alt_list};
end

if DEBUG
  fprintf('EMC_checkCacheForFile: checking %d alt cache(s)\n', numel(alt_list));
end

suffix = relPath(numel(prefix)+1:end);
for i = 1:numel(alt_list)
  base = alt_list{i};
  if isstring(base), base = char(base); end
  if ~ischar(base) || isempty(base)
    if DEBUG
      fprintf('EMC_checkCacheForFile: skipping invalid alt cache entry at index %d\n', i);
    end
    continue; % skip invalid entries defensively
  end
  if DEBUG
    fprintf('EMC_checkCacheForFile: checking %d/%d alt cache: %s\n', i, numel(alt_list), base);
  end
  try
    cand = fullfile(base, suffix);
  catch
    cand = [base, filesep, suffix]; %#ok<AGROW>
  end
  if exist(cand, 'file') == 2
    if DEBUG
      fprintf('EMC_checkCacheForFile: found at alt cache: %s\n', cand);
    end
    outPath = cand;
    return;
  end
end

% If we get here, nothing was found in any alt cache, return original
if DEBUG
  fprintf('EMC_checkCacheForFile: not found in any alt cache, returning original: %s\n', relPath);
end
outPath = relPath;

end
