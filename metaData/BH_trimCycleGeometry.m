function [subTomoMeta, droppedFields] = BH_trimCycleGeometry(subTomoMeta, keepFromCycle)
%BH_trimCycleGeometry Remove large per-particle geometry arrays from superseded cycles.
%
%   [subTomoMeta, droppedFields] = BH_trimCycleGeometry(subTomoMeta, keepFromCycle)
%   walks each cycleXXX struct with XXX < keepFromCycle and rmfields the members
%   named in DROP_FIELDS_EXACT plus any Pre_<OPERATION>_<suffix> backup whose
%   suffix is in DROP_PRE_SUFFIXES. Everything else in the cycle is untouched,
%   as is cycleXXX for XXX >= keepFromCycle. droppedFields lists what was
%   removed, in field-name order, so the caller can log it.
%
%   WHY drop-list rather than keep-list: an earlier keep-list rebuild also
%   discarded bookkeeping that BH_average3d and BH_plotMultiCycleFSC read across
%   cycles (SymmetryApplied, ClassVector, class_N_Locations_*, nSubTomoAveraged,
%   score_sigma, and the Ref/EVE/ODD location pointers). The drop-list direction
%   keeps everything by default and removes only the per-particle geometry
%   arrays that dominate the file's size. The failure modes are inverted: a new
%   large-geometry field added later stays as silent bulk until added to this
%   list, but nothing that a downstream reader depends on vanishes silently.
%
%   WHY the Pre_* pattern: BH_geometryAnalysis parks a copy of RawAlign,
%   tiltGeometry, or ClusterResults under a Pre_<OPERATION>_<suffix> name before
%   destructive operations. Those are dynamic (OPERATION varies) and per-particle
%   sized, so a suffix match reaches them without hardcoding every OPERATION.
%
%   WHY safe to run automatically: BH_average3d writes a complete snapshot of
%   subTomoMeta at the start of each cycle. The caller MUST confirm that
%   snapshot succeeded first -- trimming against an unverified write deletes the
%   last copy of what is removed here.

DROP_FIELDS_EXACT = {'RawAlign', ...
                     'geometry', ...
                     'Avg_geometry', ...
                     'ClusterClsGeom', ...
                     'ClusterRefGeom', ...
                     'ClusterResults', ...
                     'Post_AssignAndMergeToBranch'};

DROP_PRE_SUFFIXES = {'_RawAlign', '_ClusterResults', '_tiltGeometry'};

if ~isstruct(subTomoMeta)
  error('BH_trimCycleGeometry:InvalidInput', ...
        'subTomoMeta must be a struct, got %s', class(subTomoMeta));
end

if ~isnumeric(keepFromCycle) || ~isscalar(keepFromCycle) || keepFromCycle < 0
  error('BH_trimCycleGeometry:InvalidCycle', ...
        'keepFromCycle must be a non-negative scalar, got %s', mat2str(keepFromCycle));
end

droppedFields = {};

for iCycle = 0:keepFromCycle - 1
  cycleName = sprintf('cycle%0.3u', iCycle);
  if ~isfield(subTomoMeta, cycleName)
    continue;
  end

  cycleFields = fieldnames(subTomoMeta.(cycleName));
  for iField = 1:numel(cycleFields)
    fieldName = cycleFields{iField};
    if ismember(fieldName, DROP_FIELDS_EXACT) || is_pre_backup(fieldName, DROP_PRE_SUFFIXES)
      subTomoMeta.(cycleName) = rmfield(subTomoMeta.(cycleName), fieldName);
      droppedFields{end+1} = fieldName; %#ok<AGROW>
    end
  end
end

droppedFields = unique(droppedFields);

end

function tf = is_pre_backup(fieldName, suffixes)
%is_pre_backup True if fieldName is a Pre_<OPERATION>_<suffix> backup name.
%   The Pre_ prefix is required to distinguish these from live fields that
%   happen to end in one of the suffixes (RawAlign itself, for example, ends
%   in _RawAlign but must not match this test).

if ~startsWith(fieldName, 'Pre_')
  tf = false;
  return;
end

for iSuffix = 1:numel(suffixes)
  if endsWith(fieldName, suffixes{iSuffix})
    tf = true;
    return;
  end
end

tf = false;

end
