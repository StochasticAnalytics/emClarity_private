function outPath = EMC_setCacheForFile(alt_cache, inPath)
% EMC_setCacheForFile
% Choose the best cache location (cache/ or one of emc.alt_cache) based on
% available free disk space, and return the full path for writing.
%
% Usage:
%   outPath = EMC_setCacheForFile(alt_cache, inPath)
%
% Inputs
%   alt_cache - cell array of alternate cache base directories (may be empty {})
%   inPath    - string/char path that MUST start with 'cache/'
%
% Behavior
%   - If alt_cache is empty or missing, returns fullfile('cache', normalizedInPath).
%   - Otherwise, considers both 'cache' and each alt cache directory and
%     selects the base with the most free bytes (usable space).
%   - Returns fullfile(bestBase, normalizedInPath).
%
% Notes
%   - This does not create directories; callers can mkdir(fileparts(outPath))
%     if needed prior to writing.
%   - alt_cache directories are validated in parameter parsing; we still
%     check existence defensively and skip missing ones.

DEBUG = true; % verbose debug prints

% Validate inputs
if nargin < 2
  error('EMC_setCacheForFile: two input arguments required: (alt_cache, inPath)');
end

% Normalize inPath to char and strip leading file separators
if isstring(inPath)
  inPath = char(inPath);
end
if ~ischar(inPath)
  error('EMC_setCacheForFile: inPath must be a string or char');
end
% Strip any leading slashes, then enforce 'cache/' prefix
while ~isempty(inPath) && (inPath(1) == filesep || inPath(1) == '/')
  inPath = inPath(2:end);
end
prefix = 'cache/';
if ~strncmp(inPath, prefix, numel(prefix))
  error('EMC_setCacheForFile: inPath must start with "%s" (got "%s")', prefix, inPath);
end

% Base candidate always includes 'cache'. The input already includes 'cache/'.
cacheBase = 'cache';
suffix = inPath(numel(prefix)+1:end);

% If alt cache list is empty -> just return the input path (already cache/...)
alt_list = alt_cache;
if isempty(alt_list)
  if DEBUG
    fprintf('EMC_setCacheForFile: alt_cache empty or missing, using primary cache/.\n');
    fprintf('EMC_setCacheForFile: returning %s\n', inPath);
  end
  outPath = inPath;
  return;
end

if ~iscell(alt_list)
  alt_list = {alt_list};
end

% Build candidate bases: cache + existing alt caches
candidates = {cacheBase};
candidatePaths = {inPath}; % for 'cache', the path is already inPath

if DEBUG
  fprintf('EMC_setCacheForFile: %d alt cache(s) configured. Verifying existence...\n', numel(alt_list));
end

for i = 1:numel(alt_list)
  base = alt_list{i};
  if isstring(base), base = char(base); end
  if ~ischar(base) || isempty(base)
    if DEBUG
      fprintf('EMC_setCacheForFile: skipping invalid alt cache entry at index %d\n', i);
    end
    continue;
  end
  if exist(base, 'dir') ~= 7
    if DEBUG
      fprintf('EMC_setCacheForFile: alt cache does not exist (skipping): %s\n', base);
    end
    continue;
  end
  candidates{end+1} = base; %#ok<AGROW>
  candidatePaths{end+1} = fullfile(base, suffix); %#ok<AGROW>
end

% Compute free bytes for each candidate base using Java (partition usable space)
freeBytes = zeros(1, numel(candidates));
for i = 1:numel(candidates)
  base = candidates{i};
  try
    jfile = java.io.File(base);
    freeBytes(i) = double(jfile.getUsableSpace());
  catch ME
    if DEBUG
      fprintf('EMC_setCacheForFile: failed to query free space for %s (%s). Assuming 0.\n', base, ME.message);
    end
    freeBytes(i) = 0;
  end
  if DEBUG
    fprintf('EMC_setCacheForFile: candidate %-4d free bytes: %s -> %.0f\n', i, base, freeBytes(i));
  end
end

% Select best base (max free bytes)
[~, idx] = max(freeBytes);
bestBase = candidates{idx};

if DEBUG
  fprintf('EMC_setCacheForFile: selected base: %s (free: %.0f bytes)\n', bestBase, freeBytes(idx));
end

% Return the precomputed candidate path
outPath = candidatePaths{idx};
if DEBUG
  fprintf('EMC_setCacheForFile: returning %s\n', outPath);
end

end
