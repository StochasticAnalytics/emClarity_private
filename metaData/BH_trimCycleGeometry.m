function [subTomoMeta, droppedFields] = BH_trimCycleGeometry(subTomoMeta, keepFromCycle)
%BH_trimCycleGeometry Rebuild superseded cycles from their small bookkeeping only.
%
%   [subTomoMeta, droppedFields] = BH_trimCycleGeometry(subTomoMeta, keepFromCycle)
%   replaces each cycleXXX struct with XXX < keepFromCycle by one holding only the
%   fields in PRESERVE_FIELDS. Cycles at or above keepFromCycle are untouched, as
%   is everything outside the cycleXXX fields. droppedFields lists the field names
%   discarded, so the log records what a cycle actually contained.
%
%   WHY rebuild rather than remove: several cycle members are written through
%   dynamically built field names, so any enumeration of what to delete stops
%   matching as the schema grows and silently leaves bulk behind. Constructing the
%   replacement from a known keep-list inverts that -- whatever was in the cycle is
%   gone because it was never carried across, and nothing has to know it existed.
%
%   WHY these five survive: they are scalars and small fits rather than
%   per-particle tables. fitFSC is the one that earns its keep beyond size --
%   BH_plotMultiCycleFSC walks every cycle for it, so dropping whole cycleXXX
%   structs would destroy that plot's input to reclaim space that is almost
%   entirely geometry.
%
%   WHY a keep-list is the safe direction: if a field belongs here and is missing,
%   the next read of it raises immediately. The failure is loud and local. A
%   delete-list gets the same uncertainty wrong in the silent direction.
%
%   WHY this is safe to run automatically: BH_average3d writes a complete snapshot
%   of subTomoMeta at the start of each cycle, so what is discarded here stays
%   recoverable from cycleXXX_<name>_backup.mat, and the live copy is a duplicate
%   rather than the only record. The caller MUST confirm that snapshot succeeded
%   first -- trimming against an unverified write deletes the last copy.

PRESERVE_FIELDS = {'fitFSC', 'nParticles', 'bad_tiles', 'class_weights', 'KmsSampling'};

if ~isstruct(subTomoMeta)
  error('BH_trimCycleGeometry:InvalidInput', ...
        'subTomoMeta must be a struct, got %s', class(subTomoMeta));
end

if ~isnumeric(keepFromCycle) || ~isscalar(keepFromCycle) || keepFromCycle < 0
  error('BH_trimCycleGeometry:InvalidCycle', ...
        'keepFromCycle must be a non-negative scalar, got %s', mat2str(keepFromCycle));
end

droppedFields = {};

% Names are constructed, not parsed: sprintf built them in the first place, so
% there is nothing to recover by matching against fieldnames.
for iCycle = 0:keepFromCycle - 1
  cycleName = sprintf('cycle%0.3u', iCycle);
  if ~isfield(subTomoMeta, cycleName)
    continue;
  end

  kept = struct();
  for iField = 1:numel(PRESERVE_FIELDS)
    fieldName = PRESERVE_FIELDS{iField};
    if isfield(subTomoMeta.(cycleName), fieldName)
      kept.(fieldName) = subTomoMeta.(cycleName).(fieldName);
    end
  end

  droppedFields = [droppedFields; ...
                   setdiff(fieldnames(subTomoMeta.(cycleName)), fieldnames(kept))]; %#ok<AGROW>

  % Whole-value replacement. Assigning the field discards the previous struct
  % outright -- MATLAB does not merge -- which is the rmfield-then-readd result
  % without moving cycleName to the end of the parent's field order.
  subTomoMeta.(cycleName) = kept;
end

droppedFields = unique(droppedFields);

end
