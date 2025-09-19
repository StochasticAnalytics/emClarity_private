function  BH_geometryAnalysis( PARAMETER_FILE, CYCLE, ...
                               STAGEofALIGNMENT, OPERATION, ...
                               VECTOR_OP, HALF_SET)
% BH_geometryAnalysis
% Purpose
%   Perform geometry edits, exports, and bookkeeping across several alignment
%   stages (TiltAlignment, RawAlignment, Cluster_cls/Cluster). This includes
%   class-based filtering, montage-tiling operations, and utility exports.
%
% Inputs
%   PARAMETER_FILE    - emClarity parameters (.mat) parsed via BH_parseParameterFile
%   CYCLE             - cycle index (numeric or string convertible)
%   STAGEofALIGNMENT  - 'TiltAlignment' | 'RawAlignment' | 'Cluster_cls'
%   OPERATION         - One of the supported operations (see below)
%   VECTOR_OP         - Operation-specific vector or path (see below)
%   HALF_SET          - 'ODD' | 'EVE' | 'STD' (both)
%
% Selected operations (new/extended)
%   AssignToBranch
%     - VECTOR_OP: rows [class_idx, <ignored>, x, y] with 1-based montage coords.
%       class_idx==1 means ignore; class_idx>1 maps to branch (class_idx-1).
%     - Validates each montage tile: must have exactly one positive label; unlabeled
%       or conflicting tiles raise errors. Builds per-branch geometry copies in-memory
%       and defers saving (writes subTomoMeta_branch_<b>.mat at end of function).
%     - No modification to the in-memory subTomoMeta during the case execution.
%
%   AssignToTrunk
%     - VECTOR_OP: same format as AssignToBranch.
%     - Writes TSV files in working directory: cycleNNN_trunk_<b>_from_<origin>.txt
%       each with columns: tName (tomogram), subtomoIDX (col 4), mappedClass=b.
%       <origin> is parsed from subTomoMeta suffix "_branch_<num>" (0 if absent),
%       allowing per-branch disambiguation to prevent overwrites.
%     - Validates labels and tiles in the same way; no metadata mutation.
%
%   AssignAndMerge
%     - Consumes mapping files cycleNNN_trunk_*_from_<origin>.txt and uses only
%       those with <origin> equal to the current branch parsed from subTomoMeta.
%       Sets class to the current branch for matching subtomoIDX and -9999
%       otherwise. Only affects the current in-memory geometry and subsequent
%       save of subTomoMeta.
%
% Notes
%   - Column conventions used here: class column=26, subtomo index column=4.
%   - Many operations are stage-specific; errors are thrown if misused.



if (nargin ~= 6)
  error('args = (PARAMETER_FILE, CYCLE, STAGEofALIGNMENT, OPERATION, REMOVE_CLASS, HALF_SET)')
end

remove_cycles = false;
assignBranchTriggered = false; % set true when OPERATION == 'AssignClassToBranch'
assignBranch_nBranches = 0;    % number of branches = max(classIDX)-1
assignBranch_geometry = {};    % cell array of geometries per branch index
CYCLE = EMC_str2double(CYCLE);
undoOP = 0;
listTomos = 0;
if strcmpi(VECTOR_OP, 'undo')
  undoOP = 1;
  fprintf('Undoing %s action', OPERATION);
elseif (strcmpi(VECTOR_OP, 'listTomos'))
    listTomos = 1;
    fprintf('Listing tomos, delete those that should be removed, and run again replacing "listTomos" with "tomoList.txt"\n');
elseif strcmpi(OPERATION, 'TrimOldCycles')
  % For TrimOldCycles, VECTOR_OP should be a scalar (target cycle)
  VECTOR_OP = EMC_str2double(VECTOR_OP);

else
  try
    % should be a text file of only x,y,z (model2points imodModel classes.txt)
    % or
    % a list of names of tomograms to remove 
    % FIXME if any path this will not work.
    if ~(strcmp(VECTOR_OP,'tomoList.txt'))
      [~,modNAME,~] = fileparts(VECTOR_OP);
      system(sprintf('model2point -ObjectAndContour %s %s.txt > /dev/null',VECTOR_OP,modNAME));

      VECTOR_OP = importdata(sprintf('%s.txt',modNAME));
    end

  catch
    % or a 3-vector containing shifts to apply to all volumes, or range for
    % randomization of 3 euler angles
    VECTOR_OP = EMC_str2double(VECTOR_OP);
    if isequal(size(VECTOR_OP), [1,3])
      shiftXYZ = VECTOR_OP';
    elseif isequal(size(VECTOR_OP), [3,1])
      shiftXYZ = VECTOR_OP;
    elseif ~any(size(VECTOR_OP))
      % size of EMC_str2double('undo') = [0 0]
    else
      error('shift values must be a three vector or string "undo"\n');
    end
  end
end
  
% start time intentionally omitted (unused)

cycleNumber = sprintf('cycle%0.3u', CYCLE);

emc = BH_parseParameterFile(PARAMETER_FILE);
try
  conserveDiskSpace = emc.('conserveDiskSpace');
catch
  conserveDiskSpace = 0;
end
try
  percentCut   = emc.('removeBottomPercent');
catch
  percentCut = 0.0;
end


if percentCut < 0 
  error('removeBottomPercent must be a fraction between 0 1, or the top N volumes to keep');
end


halfSet = HALF_SET
if strcmpi(halfSet, 'ODD')
  halfNUM = 1;
elseif strcmpi(halfSet, 'EVE')
  halfNUM = 2;
elseif strcmpi(halfSet, 'STD')
  halfNUM = [1,2];
else
  error('HALF_SET should be EVE or ODD or STD')
end


% Column indices (replace magic numbers)
COL_SUBTOMO_IDX  = 4;
COL_CLASS        = 26;


switch STAGEofALIGNMENT
  case 'TiltAlignment'
    fieldPrefix = 'Raw'
  case 'RawAlignment'
    fieldPrefix = 'Raw';
  case 'Cluster_cls'
    fieldPrefix = 'Cls';
    STAGEofALIGNMENT = 'Cluster';
  otherwise
    error('STAGEofALIGNMENT incorrect, should be Cluster_cls or [Tilt,Raw]Alignment, not %s', ...
                                                        STAGEofALIGNMENT);
end


% sampling rate not used in this function scope
% samplingRate = emc.(sprintf('%s_samplingRate','Ali'));

className    = emc.(sprintf('%s_className',fieldPrefix));


outputPrefix = sprintf('%s_%s', cycleNumber, emc.('subTomoMeta'));


%try
  % Load using wrapper
  subTomoMeta = BH_loadSubTomoMeta(emc.('subTomoMeta'), emc.('metadata_format'));
  switch STAGEofALIGNMENT
    case 'TiltAlignment'
     geometry = subTomoMeta.tiltGeometry;
     subTomoMeta.(cycleNumber).(sprintf('Pre_%s_tiltGeometry', OPERATION)) = geometry;
    case 'RawAlignment'
      if (undoOP)
        subTomoMeta.(cycleNumber).RawAlign = ...
        subTomoMeta.(cycleNumber).(sprintf('Pre_%s_RawAlign', OPERATION));
  % Save using wrapper
  BH_saveSubTomoMeta(emc.('subTomoMeta'), subTomoMeta);
        error('No Error, just exiting.\n')
      else      
        geometry = subTomoMeta.(cycleNumber).RawAlign;
        subTomoMeta.(cycleNumber).(sprintf('Pre_%s_RawAlign', OPERATION)) = geometry;
      end
    case 'Cluster'
      
      try
        class_coeffs{1} =  emc.('Pca_coeffs_odd');
        class_coeffs{2} =  emc.('Pca_coeffs_eve');
      catch
        class_coeffs{1} = emc.('Pca_coeffs');
      end

      cluster_key = sprintf('%s_%d_%d_nClass_%d_%s',outputPrefix,class_coeffs{halfNUM(1)}(1,1), ...
                                    class_coeffs{halfNUM(1)}(1,end), className, halfSet)
      img_name = sprintf('class_%d_Locations_%s_%s_NoWgt', className, fieldPrefix, halfSet);
      img_name_std = sprintf('class_%d_Locations_%s_%s_NoWgt', className, fieldPrefix, 'ODD');
     
      
      if (undoOP)
        subTomoMeta.(cycleNumber).ClusterResults.(cluster_key) = ...
        subTomoMeta.(cycleNumber).(sprintf('Pre_%s_ClusterResults', OPERATION)).(cluster_key);
  % Save using wrapper
  BH_saveSubTomoMeta(emc.('subTomoMeta'), subTomoMeta);
        error('No Error, just exiting.\n')
      else     

        if strcmpi(fieldPrefix, 'Cls')
         geometry = subTomoMeta.(cycleNumber).('ClusterClsGeom');
         clusterGeom = 'ClusterClsGeom';
        elseif strcmpi(fieldPrefix, 'Ref')
         geometry = subTomoMeta.(cycleNumber).('ClusterRefGeom');
         clusterGeom = 'ClusterRefGeom';
        end
        
        % Skip Pre_ backup for assign methods and RemoveClasses
        skip_backup = strcmpi(OPERATION, 'AssignClassToBranch') || ...
                      strcmpi(OPERATION, 'AssignClassFromBranch') || ...
                      strcmpi(OPERATION, 'AssignAndMergeToBranch') || ...
                      strcmpi(OPERATION, 'RemoveClasses');

        %geometry = subTomoMeta.(cycleNumber).ClusterResults.(cluster_key);
        if ~skip_backup
          subTomoMeta.(cycleNumber).(sprintf('Pre_%s_ClusterResults', OPERATION)).(cluster_key) = geometry;
        end
        try
          locations= subTomoMeta.(cycleNumber).(img_name){2};
          classVector{1} = subTomoMeta.(cycleNumber).(img_name){3}(1,:);
        catch
          locations= subTomoMeta.(cycleNumber).(img_name_std){2};
          classVector{1} = subTomoMeta.(cycleNumber).(img_name_std){3}(1,:);
        end
      end
    otherwise
      error('STAGE_ALIGNMENTS: [Tilt,Class,No,Raw]Alignment, not %s', ...
                                                            STAGEofALIGNMENT);
  end
% % %     pathList= subTomoMeta.mapPath;
% % %     extList = subTomoMeta.mapExt;
mapBackIter = subTomoMeta.currentTomoCPR; 

    % No longer need to copy to masterTM - work directly with subTomoMeta
%   
% catch 
%   error('failed to load geometry')
% end

tomoList = fieldnames(geometry);
nTomograms = length(tomoList);


switch OPERATION
  case 'SwitchCurrentCycle'
    subTomoMeta.currentCycle = VECTOR_OP(1);
  case 'SwitchCurrentTomoCpr'
    subTomoMeta.currentTomoCPR = VECTOR_OP(1);    
  case 'SwitchExposureDose'
    % While transitioning , edit the dose column in the tilt geometry.
    
    for iTomo = 1:nTomograms
      tilt_table = geometry.(tomoList{iTomo});
      n_projs = size(tilt_table,1);
      % Assuming a bi-directional tilt scheme with smallest abs value as first tilt,
      % which could be wrong
  dose_per_tilt = [tilt_table(:,1), tilt_table(:,4), zeros(n_projs,1)];
      % Make sure arranged from negative to positive
      dose_per_tilt = sortrows(dose_per_tilt,2);
      [~,first_tilt] = min(abs(dose_per_tilt(:,2)));
      dose_per_tilt(1:first_tilt,:) = sortrows(dose_per_tilt(1:first_tilt,:),-2);
      exposure = VECTOR_OP(1)./n_projs
      for iExposure = 1:n_projs
        dose_per_tilt(iExposure,3) = iExposure .* exposure;
      end
      dose_per_tilt
      for iPrj = 1:n_projs
        cum_dose = dose_per_tilt(find(dose_per_tilt(:,1) == tilt_table(iPrj,1)),3);
        geometry.(tomoList{iTomo})(iPrj,11) = cum_dose
      end
    end
  case 'UpdateTilts'
 
    
    % Usually the tilt angle change is pretty small, so re-calculating the 
    % weights may not be strictly necessary -- consider an option to not 
    % clear them.
%     system('rm cache/*.wgt');
    % This is most important to update the changes to the tilt angles in
    % the TLT geometry which affect future tomoCPR.
    if ( conserveDiskSpace )
      system('rm cache/*.wgt*');
      system('rm cache/*.rec*');
    end

  [stack_list, ~] = BH_returnIncludedTilts( subTomoMeta.mapBackGeometry );

    for iStack = 1:length(stack_list)
      stack_prfx = stack_list{iStack};
      tomo_names = subTomoMeta.mapBackGeometry.(stack_prfx).tomoList;
      for iTomo = 1:length(tomo_names)

        new_tlt = sprintf('fixedStacks/ctf/%s_ali%d_ctf.tlt', stack_prfx,mapBackIter+1); 
        geometry.(tomo_names{iTomo}) = load(new_tlt);
        fprintf('Updating TLT %s\n', new_tlt);
      end
    end

    
    
  case 'WriteCsv'
    !mkdir -p csv
    for iTomo = 1:nTomograms
      position_list = geometry.(tomoList{iTomo});
      csv_out = sprintf('./csv/%s_%s_%s.csv',cycleNumber,tomoList{iTomo},fieldPrefix);
      csv_fid = fopen(csv_out, 'w');
      for i_subtomo = 1:size(position_list,1)
        if ( VECTOR_OP(1) == -1 && position_list(i_subtomo,26) ~= -9999 ) || ...
           ( ismember(position_list(i_subtomo,26), VECTOR_OP) )
            fprintf(csv_fid,'%-06.3f %-06.3f %-06.3f %-04d %-06.3f %-06.3f %-04d %-04d %-06.3f %-06.3f   %-07.3f %-07.3f %-07.3f   %-03.3f %-03.3f %-03.3f    %-03.3f %-03.3f %-03.3f %-03.3f %-03.3f %-03.3f %-03.3f %-03.3f %-03.3f    %-4d\n',...
              position_list(i_subtomo,:));
        end
      end
      fclose(csv_fid);
    end
  case 'RemoveClasses'

    % Create a copy of geometry to work with
    geometry_copy = geometry;

  classes_to_keep = [];
    % make a 2d array same size as montage
    clear blankClassMont
    % montage is always square, and the first row is always full, so use this to
    % determine the size.

  size_montage = max(locations{end}(2),locations{end}(4));
  blankClassMont(size_montage, size_montage) = single(0);
    
    % put a 1 at each x,y from the model file identifying classes to kill
    % columns are obj cont x y z
    VECTOR_OP = round(VECTOR_OP);
    for i_kill = 1:size(VECTOR_OP,1)
      blankClassMont(VECTOR_OP(i_kill,3),VECTOR_OP(i_kill,4)) = 1;
    end
    
    % FIXME: I did not run into this until 2025, so for now just working around. If not all of the classes are included in the class average, then
    % This could skip classes that are to be removed. For now, I'm just going to assume anything not averaged should be removed.
    % In this case, the class was not averaged b/c there was 2 in the odd set and 0 in the eve, which created a NAN in averaging (which is also a bug, it should be caught, I must just be checking one halfset?)
  classes_not_in_average = ~ismember(1:className,classVector{1});
    classesToKill = find(classes_not_in_average);
    for iClass = 1:length(locations)
    
  iCut = blankClassMont(locations{iClass}(1):locations{iClass}(2), ...
            locations{iClass}(3):locations{iClass}(4));
                            
    
        
        if any(iCut(:))
          classesToKill = [classesToKill, iClass];
        else
          classes_to_keep = [classes_to_keep, iClass];
        end

    end
    classesToKill = sort(classesToKill,'ascend');    

    fileOUT = fopen(sprintf('%s_ClassMods_%s.txt',cycleNumber, halfSet), 'w');
    fprintf(fileOUT, '%s\n','Classes removed:');
    fprintf(fileOUT, '[%g',classesToKill(1));
    fprintf(fileOUT, ',%g', classesToKill(2:end));
    fprintf(fileOUT, ']\n\n');

  fprintf(fileOUT, '%s\n','Classes retained:');
  fprintf(fileOUT, '[%g',classes_to_keep(1));
  fprintf(fileOUT, ',%g', classes_to_keep(2:end));
  fprintf(fileOUT, '; 1.*ones(1,%d)]\n\n',numel(classes_to_keep));

  


    nTotal = 0;
    nRemoved = 0;
    nRemain = 0;
    for iTomo = 1:nTomograms
      positionList = geometry_copy.(tomoList{iTomo});


      toRemove = ismember(positionList(:,7),  halfNUM) & ...
                 ismember(positionList(:,26), classesToKill);

      nOrig = ismember(positionList(:,7),  halfNUM) & ...
              (positionList(:,26) ~= -9999);
      positionList(toRemove,26) = -9999;
      nRemain = nRemain + sum(ismember(positionList(:,7),  halfNUM) & ...
              (positionList(:,26) ~= -9999))

      nTotal = nTotal + sum(nOrig);
      nRemoved = nRemoved + sum(toRemove)

      geometry_copy.(tomoList{iTomo}) = positionList;
    end


   fprintf(fileOUT, '\nremoved:\t%d\nremaining:%d\norig:%d\n',nRemoved,nRemain,nTotal);
    fclose(fileOUT);

    % Store the modified geometry in Post_ field instead of overwriting
    if strcmpi(STAGEofALIGNMENT, 'Cluster')
      subTomoMeta.(cycleNumber).Post_RemoveClasses.ClusterResults.(cluster_key) = geometry_copy;
    end
  
  case 'AssignClassToBranch'
  % Assign montage tiles to branches using VECTOR_OP labels.
  % Contract:
  % - Input VECTOR_OP: [class_idx, <ignored>, x, y] with class 1 == ignore.
  % - Each tile must have exactly one positive label inside its bbox; unlabeled or conflicting labels error.
  % - Output: no mutation to subTomoMeta here; per-branch geometries cached and saved at end.
  % Failure modes: out-of-bounds label, unlabeled tile, conflicting labels.

    if ~(strcmpi(STAGEofALIGNMENT, 'Cluster'))
      error('AssignClassToBranch is only valid at STAGEofALIGNMENT=Cluster');
    end

  % Build tile mapping (and branch count) using shared helper; validates VECTOR_OP
  fprintf('\n=== DEBUG AssignClassToBranch: Starting ===\n'); % revert
  fprintf('DEBUG: VECTOR_OP size = %s\n', mat2str(size(VECTOR_OP))); % revert
  fprintf('DEBUG: Number of locations (tiles) = %d\n', length(locations)); % revert
  fprintf('DEBUG: First 10 VECTOR_OP rows:\n'); % revert
  for debug_i = 1:min(10, size(VECTOR_OP,1)) % revert
    fprintf('  Row %d: [classIdx=%d, col2=%g, x=%d, y=%d]\n', debug_i, VECTOR_OP(debug_i,1), VECTOR_OP(debug_i,2), VECTOR_OP(debug_i,3), VECTOR_OP(debug_i,4)); % revert
  end % revert
  [tile_to_branch, n_branches] = emc_build_tile_to_branch(VECTOR_OP, locations, 'AssignClassToBranch');
  assignBranch_nBranches = n_branches;
  fprintf('DEBUG: After emc_build_tile_to_branch: n_branches=%d\n', n_branches); % revert
  fprintf('DEBUG: tile_to_branch mapping:\n'); % revert
  for debug_i = 1:length(tile_to_branch) % revert
    fprintf('  Tile %d -> Branch %d\n', debug_i, tile_to_branch(debug_i)); % revert
  end % revert

    % Build per-branch geometries without altering 'geometry'
  % Build per-branch geometries without altering 'geometry'
  % Build per-branch geometries without altering 'geometry'
  branch_geometries = emc_assign_branch_geometries(geometry, tomoList, tile_to_branch, n_branches, COL_CLASS);

    % Mark that we will handle saving at the end
    assignBranch_geometry = branch_geometries;
    assignBranchTriggered = true;

    % Summary logging: tiles per branch and per-tomo assignment counts
    tiles_ignored = sum(tile_to_branch == 0);
    fprintf('\nDEBUG: Counting tiles_ignored...\n'); % revert
    fprintf('DEBUG: tile_to_branch values: %s\n', mat2str(tile_to_branch')); % revert
    fprintf('DEBUG: Number of zeros in tile_to_branch: %d\n', sum(tile_to_branch == 0)); % revert
    fprintf('DEBUG: Tiles with branch 0 (ignored): '); % revert
    ignored_indices = find(tile_to_branch == 0); % revert
    fprintf('%s\n', mat2str(ignored_indices')); % revert
    fprintf('AssignClassToBranch: tiles ignored=%d\n', tiles_ignored);
    for b = 1:n_branches
      fprintf('AssignClassToBranch: tiles -> branch %d = %d\n', b, sum(tile_to_branch == b));
    end
    % Per-tomo particle distribution based on original classes
    total_per_branch = zeros(n_branches,1);
    total_ignored = 0;
    for iTomo = 1:nTomograms
      tName = tomoList{iTomo};
      position_list_orig = geometry.(tName);
      included_mask = (position_list_orig(:,COL_CLASS) ~= -9999);
      orig_classes = position_list_orig(included_mask, COL_CLASS);
      fprintf('  DEBUG: Tomo %s - orig_classes unique values: %s\n', tName, mat2str(unique(orig_classes)')); % revert
      tiles_with_zero = find(tile_to_branch == 0); % revert
      fprintf('  DEBUG: Tiles mapped to branch 0 (positions): %s\n', mat2str(tiles_with_zero')); % revert
      ignore_count = sum(ismember(orig_classes, find(tile_to_branch == 0)));
      counts_line = zeros(1,n_branches);
      for b = 1:n_branches
        tiles_for_branch = find(tile_to_branch == b); % revert
        fprintf('    DEBUG: Branch %d gets tiles: %s\n', b, mat2str(tiles_for_branch')); % revert
        cnt_b = sum(ismember(orig_classes, find(tile_to_branch == b)));
        counts_line(b) = cnt_b; total_per_branch(b) = total_per_branch(b) + cnt_b;
      end
      total_ignored = total_ignored + ignore_count;
      fprintf('AssignClassToBranch: %s -> branch_counts=%s, ignored=%d\n', tName, mat2str(counts_line), ignore_count);
    end
    fprintf('AssignClassToBranch: totals per branch=%s, total ignored=%d\n', mat2str(total_per_branch'), total_ignored);
  
  case 'AssignClassFromBranch'
  % Prepare mapping files for future AssignAndMergeToBranch without modifying metadata.
  % Contract:
  % - Input VECTOR_OP: [class_idx, <ignored>, x, y] with class 1 == ignore.
  % - Output files: cycleNNN_branch_<b>_from_<origin>.txt (TSV: tName, subtomoIDX, mappedClass=b).
  %   <origin> is parsed from subTomoMeta suffix _branch_<num>; 0 if not present.
  % Failure modes: out-of-bounds label, unlabeled/conflicting tiles.

    if ~(strcmpi(STAGEofALIGNMENT, 'Cluster'))
      error('AssignClassFromBranch is only valid at STAGEofALIGNMENT=Cluster');
    end

  % Build tile mapping (and branch count) using shared helper
  fprintf('\n=== DEBUG AssignClassFromBranch: Starting ===\n'); % revert
  fprintf('DEBUG: VECTOR_OP size = %s\n', mat2str(size(VECTOR_OP))); % revert
  fprintf('DEBUG: Number of locations (tiles) = %d\n', length(locations)); % revert
  [tile_to_branch, n_branches] = emc_build_tile_to_branch(VECTOR_OP, locations, 'AssignClassFromBranch');
  fprintf('DEBUG: After emc_build_tile_to_branch: n_branches=%d\n', n_branches); % revert
  fprintf('DEBUG: tile_to_branch mapping: %s\n', mat2str(tile_to_branch')); % revert

  % Determine originating branch for disambiguation
  origin_branch = 0;
  meta_name_tmp = emc.('subTomoMeta');
  origin_tokens = regexp(meta_name_tmp, '_branch_(\d+)$', 'tokens');
  if ~isempty(origin_tokens)
    origin_branch = str2double(origin_tokens{1}{1});
    if isnan(origin_branch) || origin_branch < 0, origin_branch = 0; end
  end

  % Open one output file per branch in the working directory, prefixed by cycle number
  file_ids = cell(n_branches,1);
  lines_per_branch = zeros(n_branches,1);
    for b = 1:n_branches
      out_path = sprintf('%s_branch_%d_from_%d.txt', cycleNumber, b, origin_branch);
      fid = fopen(out_path, 'w');
      if fid == -1, error('AssignClassFromBranch: failed to open %s for writing', out_path); end
      fprintf(fid, '# tName\tsubtomoIDX\tmappedClass\n');
      file_ids{b} = fid;
    end

    % Write assignments: for each tile mapped to branch b, list all rows with origClass==iClass
    fprintf('DEBUG: Writing assignments to files...\n'); % revert
    for iTomo = 1:nTomograms
      tomo_name = tomoList{iTomo};
      position_list = geometry.(tomo_name);
      original_class_labels = position_list(:,COL_CLASS);
      subtomo_idx = position_list(:,COL_SUBTOMO_IDX);
      unique_classes = unique(original_class_labels(original_class_labels ~= -9999)); % revert
      fprintf('  DEBUG: Tomo %s has classes: %s\n', tomo_name, mat2str(unique_classes')); % revert
      for tile_index = 1:length(tile_to_branch)
        b = tile_to_branch(tile_index);
        if b <= 0
          fprintf('    DEBUG: tile %d -> branch %d (ignored)\n', tile_index, b); % revert
          continue;
        end
        class_mask = (original_class_labels == tile_index);
        fprintf('    DEBUG: tile %d -> branch %d, looking for class %d, found %d particles\n', tile_index, b, tile_index, sum(class_mask)); % revert
        if any(class_mask)
          fid = file_ids{b};
          idx_list = find(class_mask)';
          for k = idx_list
            fprintf(fid, '%s\t%d\t%d\n', tomo_name, subtomo_idx(k), b);
          end
          lines_per_branch(b) = lines_per_branch(b) + numel(idx_list);
        end
      end
    end

    % Close files
    for b = 1:n_branches
      fclose(file_ids{b});
      fprintf('AssignClassFromBranch: wrote %s_branch_%d_from_%d.txt (rows=%d)\n', cycleNumber, b, origin_branch, lines_per_branch(b));
    end
    fprintf('AssignClassFromBranch: tiles ignored=%d\n', sum(tile_to_branch==0));
    for b = 1:n_branches
      fprintf('AssignClassFromBranch: tiles -> branch %d = %d\n', b, sum(tile_to_branch==b));
    end

  case 'AssignAndMergeToBranch'
  % Merge assignments: choose current branch based on subTomoMeta name, then
  % for all cycle-prefixed mapping files, set class=b for matches and -9999 otherwise.
  % Contract:
  % - Input files: cycleNNN_branch_<current_branch>_from_*.txt (TSV header + rows tName,subtomoIDX,mappedClass).
  % - Behavior: detect current branch from subTomoMeta suffix _branch_<num> and apply.
  % Failure modes: missing branch files, invalid branch suffix, file read errors.
    if ~(strcmpi(STAGEofALIGNMENT, 'Cluster'))
      error('AssignAndMergeToBranch is only valid at STAGEofALIGNMENT=Cluster');
    end
  meta_name = emc.('subTomoMeta');
    branch_tokens = regexp(meta_name, '_branch_(\d+)$', 'tokens');
    if isempty(branch_tokens)
      error('AssignAndMergeToBranch: could not determine branch from subTomoMeta "%s"; expected suffix _branch_<num>', meta_name);
    end
    current_branch = str2double(branch_tokens{1}{1});
    if isnan(current_branch) || current_branch < 1
      error('AssignAndMergeToBranch: invalid branch number parsed from subTomoMeta "%s"', meta_name);
    end

    % Discover mapping files for this cycle with branch matching current branch; origin wildcard
    file_list = dir(sprintf('%s_branch_%d_from_*.txt', cycleNumber, current_branch));
    if isempty(file_list)
      error('AssignAndMergeToBranch: no mapping files found for current branch. Expected files like %s_branch_%d_from_*.txt', cycleNumber, current_branch);
    end

  % Build a keep list (by tName) for current branch
  keep_by_tomo = struct();
  total_rows_current_branch = 0;
  for file_i = 1:numel(file_list)
    file_path = file_list(file_i).name;
    fid = fopen(file_path, 'r');
    if fid == -1
      error('AssignAndMergeToBranch: failed to open %s', file_path);
    end
    % header then rows: tName\tsubtomoIDX\tmappedClass
    header_line = fgetl(fid); %#ok<NASGU>
    parsed_cols = textscan(fid, '%s%d%d', 'Delimiter', '\t');
    fclose(fid);
    if isempty(parsed_cols{1})
      continue;
    end
    tomo_names = parsed_cols{1};
    subtomo_ids = parsed_cols{2};
    mapped_classes = parsed_cols{3};
    % Filter to current branch
    is_current_branch = (mapped_classes == current_branch);
    tomo_names = tomo_names(is_current_branch);
    subtomo_ids = subtomo_ids(is_current_branch);
    total_rows_current_branch = total_rows_current_branch + numel(subtomo_ids);
    for id_i = 1:numel(subtomo_ids)
      t_name = tomo_names{id_i};
      if ~isfield(keep_by_tomo, t_name)
        keep_by_tomo.(t_name) = subtomo_ids(id_i);
      else
        keep_by_tomo.(t_name) = unique([keep_by_tomo.(t_name); subtomo_ids(id_i)]);
      end
    end
  end

    % Apply to a COPY of geometry (not modifying the original):
    % - Set -9999 by default for rows that were previously included
    % - Assign class=current_branch for any mapped subtomoIDs (revive if previously -9999)

    % Create a deep copy of the geometry
    geometry_copy = geometry;

    total_kept = 0; total_ignored = 0;
    for iTomo = 1:nTomograms
      tName = tomoList{iTomo};
      position_list = geometry_copy.(tName);
      included_mask = (position_list(:,COL_CLASS) ~= -9999);
      % default ignore for all included
      position_list(included_mask,COL_CLASS) = -9999;
      if isfield(keep_by_tomo, tName)
        ids_to_keep = keep_by_tomo.(tName);
        % match by column 4 (subtomoIDX); revive even if previously -9999
        keep_mask = ismember(position_list(:,COL_SUBTOMO_IDX), ids_to_keep);
        position_list(keep_mask, COL_CLASS) = current_branch;
        kept_here = sum(keep_mask);
        ignored_here = numel(ids_to_keep) - kept_here;
      else
        kept_here = 0; ignored_here = 0;
      end
      total_kept = total_kept + kept_here; total_ignored = total_ignored + ignored_here;
      fprintf('AssignAndMergeToBranch: %s -> kept=%d, ignored=%d\n', tName, kept_here, ignored_here);
      geometry_copy.(tName) = position_list;
    end
    fprintf('AssignAndMergeToBranch: files_read=%d, rows_for_branch=%d, total_kept=%d, total_ignored=%d\n', numel(file_list), total_rows_current_branch, total_kept, total_ignored);

    % Store the modified geometry in Post_ field instead of overwriting
    % geometry_copy already contains the complete geometry structure with all tomogram fields
    subTomoMeta.(cycleNumber).Post_AssignAndMergeToBranch = geometry_copy;
  
  case 'ShiftAll'
    % No option to shift eve/odd separately.
    for iTomo = 1:nTomograms
      positionList = geometry.(tomoList{iTomo});
      for iSubTomo = 1:size(positionList,1)
        if ismember(positionList(iSubTomo,7), [1,2]) 
          rotMat = reshape(positionList(iSubTomo,17:25),3,3);
          shifts = (rotMat*shiftXYZ)';
          positionList(iSubTomo,11:13) = positionList(iSubTomo,11:13) + shifts;
        end
      end
      geometry.(tomoList{iTomo}) = positionList;
    end 
  
  case 'ShiftBin'
    for iTomo = 1:nTomograms
      positionList = geometry.(tomoList{iTomo});
      for iSubTomo = 1:size(positionList,1)
        if ismember(positionList(iSubTomo,7) , halfNUM) 
          positionList(iSubTomo,11:13) = positionList(iSubTomo,11:13) + shiftXYZ';
        end
      end
      geometry.(tomoList{iTomo}) = positionList;
    end    
    
  case 'ListTomos'
  system(sprintf('mkdir -p tomoList_%s',cycleNumber));
  tomo_list_fid = fopen(sprintf('tomoList_%s/tomoList.txt',cycleNumber),'w');
    for iTomo = 1:nTomograms
      positionList = geometry.(tomoList{iTomo});
        includeList = (positionList(:,26) ~= -9999);
  n_remaining = sum(includeList);
  n_total = length(includeList);
  figure('Visible','off'); hist(positionList(includeList,1),floor(n_remaining./5)+1);
        title({sprintf('%s',tomoList{iTomo})},'Interpreter','none'); 
        xlabel('CCC'); 
        file_out = sprintf('tomoList_%s/%s.pdf', cycleNumber, tomoList{iTomo});
        saveas(gcf, file_out,'pdf')   
  fprintf(tomo_list_fid,'%s\t%d/%d\n',tomoList{iTomo},n_remaining,n_total);
  fclose(tomo_list_fid);
    end 
    
  case 'RemoveTomos'
    
    if (listTomos)
  f=fieldnames(subTomoMeta.mapBackGeometry.tomoName);
      tomoFid = fopen('tomoList.txt','w');
      fprintf(tomoFid,'%s\n',f{:});
      fclose(tomoFid);   
    else
      tomoList = importdata(VECTOR_OP);
      f=fieldnames(subTomoMeta.mapBackGeometry.tomoName);
    
      for iOrig = 1:length(f)
  flg_remove = 1;
        for iToKeep = 1:length(tomoList)         
          if strcmp(f{iOrig},tomoList{iToKeep})
            flg_remove = 0;
            break;
          end
        end
        if (flg_remove)
          if isfield(subTomoMeta.reconGeometry, f{iOrig})
            subTomoMeta.reconGeometry = rmfield(subTomoMeta.reconGeometry,f{iOrig});
          end
          if isfield(subTomoMeta.tiltGeometry, f{iOrig})
            subTomoMeta.tiltGeometry = rmfield(subTomoMeta.tiltGeometry,f{iOrig});
          end

          if isfield(subTomoMeta.(cycleNumber).RawAlign, f{iOrig})
            subTomoMeta.(cycleNumber).RawAlign = rmfield(subTomoMeta.(cycleNumber).RawAlign, f{iOrig});
          end
          if isfield(subTomoMeta.mapBackGeometry.tomoName, f{iOrig})
            tN = subTomoMeta.mapBackGeometry.tomoName.(f{iOrig}).tomoIdx;
            tName = subTomoMeta.mapBackGeometry.tomoName.(f{iOrig}).tiltName;
            if isfield(subTomoMeta.mapBackGeometry, tName)
              subTomoMeta.mapBackGeometry.(tName).nTomos = subTomoMeta.mapBackGeometry.(tName).nTomos - 1;
                keep_rows = ismember(1:size(subTomoMeta.mapBackGeometry.(tName).coords,1),tN);
                subTomoMeta.mapBackGeometry.(tName).coords = subTomoMeta.mapBackGeometry.(tName).coords(~keep_rows,:);
                subTomoMeta.mapBackGeometry.tomoName = rmfield(subTomoMeta.mapBackGeometry.tomoName,f{iOrig});
              if subTomoMeta.mapBackGeometry.(tName).nTomos == 0 
                subTomoMeta.mapBackGeometry = rmfield(subTomoMeta.mapBackGeometry,tName);
              end
            end
          end
        
        end
      end
      geometry = subTomoMeta.tiltGeometry;  
    end   
    
      
       
    
  case 'RandomizeEulers'
    for iTomo = 1:nTomograms
      rng('shuffle')
      positionList = geometry.(tomoList{iTomo});
      for iSubTomo = 1:size(positionList,1)
        if ismember(positionList(iSubTomo,7) , halfNUM)
          
          rotMat = reshape(positionList(iSubTomo,17:25),3,3);
          
          r1 = randi([-1,1].*VECTOR_OP(1));
          r2 = randi([-1,1].*VECTOR_OP(2));
          r3 = randi([-1,1].*VECTOR_OP(3));
          
          randMat = BH_defineMatrix([r1,r2,r3-r1],'SPIDER','inv');
          
          positionList(iSubTomo,17:25) = reshape(rotMat*randMat,1,9);
        end
      end
      geometry.(tomoList{iTomo}) = positionList;
    end   
    
  case 'RemoveFraction'
    % Get distribution of CCC from given cycle rawAlignment
    % Save histogram, also remove given bottom percentage and report CCC cutoff
    if ~(strcmpi(STAGEofALIGNMENT, 'RawAlignment'))
      error('Can only remove fraction at RawAlignment Stage')
    end
    cccValues = [];
    for iTomo = 1:nTomograms
      positionList = geometry.(tomoList{iTomo});
      cccValues = [cccValues;positionList(( positionList(:,26) ~= -9999 ), 1)];
    end   
    
    nSubTomos = length(cccValues);
    
    sortCCC = sort(cccValues,'descend')
    
    if percentCut < 1
      cutIDX = floor(percentCut .* nSubTomos) + 1
    else
      % Keep the top N values
      cutIDX = percentCut
    end
    
    cccCutOff = sortCCC(cutIDX)
    sortCCC(1)
    sortCCC(end)
    
    nRemoved = 0;
    for iTomo = 1:nTomograms
      positionList = geometry.(tomoList{iTomo});
      removeList = positionList(:, 1) < cccCutOff & positionList(:,26)~=-9999;
      nRemoved = nRemoved + sum(removeList)
      positionList(removeList,26) = -9999;
      geometry.(tomoList{iTomo}) = positionList;
    end   
    
    figure('visible', 'off'), hist(cccValues);
    title(sprintf('CCC distribution\n%2.2f%% cut\n %f CCC\n%d/ %d removed ',100*percentCut,cccCutOff,nRemoved,nSubTomos));
    xlabel('CCC'); ylabel('nSubTomos');
    
    file_out = sprintf('%s-cccCutoff.pdf', outputPrefix);

    saveas(gcf, file_out,'pdf')
 
  case 'TrimOldCycles'
    % Trim subTomoMeta by removing all cycleXXX structs with XXX <= VECTOR_OP(1)
    trim_cycle = VECTOR_OP(1);
    if isnan(trim_cycle) || trim_cycle < 0
      error('TrimOldCycles: invalid cycle value %s', mat2str(VECTOR_OP));
    end
    flds = fieldnames(subTomoMeta);
    cycle_names = {};
    cycle_ids = [];
    for i = 1:numel(flds)
      tok = regexp(flds{i}, '^cycle(\d{3})$', 'tokens');
      if ~isempty(tok)
        cid = str2double(tok{1}{1});
        cycle_names{end+1} = flds{i}; %#ok<AGROW>
        cycle_ids(end+1) = cid; %#ok<AGROW>
      end
    end
    if isempty(cycle_ids)
      warning('TrimOldCycles: no cycleXXX fields found to trim');
    end
    to_remove_mask = cycle_ids <= trim_cycle;
    to_keep_mask   = cycle_ids >  trim_cycle;
    n_remove = sum(to_remove_mask);
    n_keep   = sum(to_keep_mask);
    if n_remove > 0
      rm_list = cycle_names(to_remove_mask);
      subTomoMeta = rmfield(subTomoMeta, rm_list);
      fprintf('TrimOldCycles: removed %d cycle(s) <= %03d\n', n_remove, trim_cycle);
    else
      fprintf('TrimOldCycles: nothing to remove at or below cycle %03d\n', trim_cycle);
    end
    if n_keep == 0
      warning('TrimOldCycles: no cycleXXX fields remain greater than %03d', trim_cycle);
    else
      fprintf('TrimOldCycles: %d cycle(s) remain > %03d\n', n_keep, trim_cycle);
    end
    % geometry remains unchanged; final save below will persist subTomoMeta
    
    
    case 'RemoveIgnoredParticles'
      % Get distribution of CCC from given cycle rawAlignment
      % Save histogram, also remove given bottom percentage and report CCC cutoff
      fprintf('\n\t\nRemoving ignored particles from the meta data to save space, this must be run after alignment or after a call to emClarity skip, post classification\n\n');
      if (length(shiftXYZ) == 3)
        remove_cycles = true;
        fprintf('Removing any alignment cycles before cycle %d\n',shiftXYZ(3));
      end
      if ~(strcmpi(STAGEofALIGNMENT, 'RawAlignment'))
        error('Can only remove fraction at RawAlignment Stage')
      end
      n_removed = 0;
      n_total = 0;
      for iTomo = 1:nTomograms
        % Get the non ignored values
        non_ignored = any(geometry.(tomoList{iTomo})(:,26:26*emc.nPeaks) ~= -9999, 2);
        n_total = n_total + size(geometry.(tomoList{iTomo}),1);
        n_removed = n_removed + sum(~non_ignored);
        geometry.(tomoList{iTomo}) = geometry.(tomoList{iTomo})(non_ignored,:);
      end   
      
      fprintf('Removed %d/%d particles\n',n_removed,n_total);
      

  case 'ListPercentiles'
    cccVector = [];
    % Gather included scores
    for iTomo = 1:nTomograms
      positionList = geometry.(tomoList{iTomo});
      cccVector = [cccVector;positionList(( positionList(:,26) ~= -9999 ), 1)];
    end   
    nVols = length(cccVector)
    cccVector = sort(cccVector,1,'descend');
    snrVector = 2.* cccVector ./ (1-cccVector);
    percentiles = [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9;0,0,0,0,0,0,0,0,0];
    percentiles(2,:) = cccVector(floor(nVols.*(percentiles(1,:))))
    weightedCurve = zeros(nVols,2);
    weightedCurve(:,1) = 1:nVols;
    for iVol = 1:nVols
      weightedCurve(iVol,2) = mean(snrVector(1:iVol,1).*sqrt(iVol));
    end
  length((1:nVols)')
    length(weightedCurve(:,2))
  r = fit((1:nVols)',weightedCurve(:,2),'linear');
    maxVal = find(r(2:nVols+1)-r(1:nVols) <= 0, 1,'first')
    maxCCC = cccVector(maxVal)
    
    figure('visible', 'off'), plot(weightedCurve(:,2));
    title({'mean SNR via CCC vs nVols',sprintf('%0.3f CCC',maxCCC),sprintf( '%d Vols', maxVal),sprintf('%0.2f',100.*maxVal/nVols)});
    file_out = sprintf('%s_percentiles_%s.pdf', cycleNumber, fieldPrefix);
    saveas(gcf, file_out,'pdf')
    
    fOUT = sprintf('./%s_percentiles_%s.txt',cycleNumber,fieldPrefix);
    fID = fopen(fOUT, 'w');    
    fprintf(fID,'%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t\n%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t%-4.3f\t\n',percentiles');
    fclose(fID);
  otherwise
  error('OPERATION must be WriteCsv, RemoveClasses, AssignToBranch, AssignToTrunk, AssignAndMerge, ShiftAll, RemoveFraction, RemoveIgnoredParticles, TrimOldCycles, not %s', OPERATION)
end 

% Redundant for WriteCsv, otherwise update the new geometry, which was backed up
% at the begining as Pre_OPERATION_...
switch STAGEofALIGNMENT
  
  case 'TiltAlignment'
    subTomoMeta.tiltGeometry = geometry;
  
  case 'RawAlignment'
    subTomoMeta.(cycleNumber).RawAlign = geometry;
  case 'Cluster'
    subTomoMeta.(cycleNumber).(clusterGeom) = geometry;

  otherwise
    error('STAGE_ALIGNMENTS: [Tilt,Class,No,Raw]Alignment, not %s', ...
                                                        STAGEofALIGNMENT);
end

% Currently set only if calling RemoveIgnoredParticles
if (remove_cycles)
  % Remove cycles BEFORE the specified cycle (keeping the specified cycle and later)
  for iCycle = 0:(shiftXYZ(3)-1)
    cycleName = sprintf('cycle%0.3u', iCycle);
    if isfield(subTomoMeta, cycleName)
      fprintf('Removing cycle %s from metadata\n', cycleName);
      subTomoMeta = rmfield(subTomoMeta, cycleName);
    end
  end
end

if assignBranchTriggered
  % Save per-branch variants without modifying subTomoMeta
  for b = 1:assignBranch_nBranches
    branchMasterTM = subTomoMeta;
    % Only Cluster stage supported for AssignClassToBranch
    if strcmpi(STAGEofALIGNMENT, 'Cluster')
      branchMasterTM.(cycleNumber).(clusterGeom) = assignBranch_geometry{b};
    else
      error('AssignClassToBranch saving encountered unexpected stage: %s', STAGEofALIGNMENT);
    end
    subTomoMeta = branchMasterTM; %#ok<NASGU>
    outBase = sprintf('%s_branch_%d', emc.('subTomoMeta'), b);
    save(outBase, 'subTomoMeta', '-v7.3');
  end
else
  % No longer need to copy back - just save subTomoMeta directly
  % Save using wrapper
  BH_saveSubTomoMeta(emc.('subTomoMeta'), subTomoMeta);
end
end






% ---- Local helpers (behavior-preserving) ---------------------------------
function [tile_to_branch, n_branches] = emc_build_tile_to_branch(VECTOR_OP, locations, whoami)
% emc_build_tile_to_branch
% Build per-tile branch mapping from montage label points.
%
% Inputs
%   VECTOR_OP  - N×4 array; columns [class_idx, <ignored>, x, y], 1-based.
%                class_idx==1 => ignore; class_idx>1 => branch (class_idx-1).
%   locations  - cell array of montage tile bounding boxes: [x1 x2 y1 y2].
%   whoami     - string used for clearer error messages (optional).
%
% Outputs
%   tile_to_branch - vector of length num_tiles; 0 for ignore, >0 for branch idx.
%   n_branches     - number of branches implied by maximum class_idx minus one.
%
% Errors
%   - Out-of-bounds or invalid class_idx rows.
%   - Any tile without a positive label.
%   - Any tile that contains multiple distinct labels.
  if nargin < 3, whoami = 'Assign'; end
  VECTOR_OP = round(VECTOR_OP);
  if size(VECTOR_OP,2) < 4
    error('%s: expects VECTOR_OP with 4 columns: [classIDX, <ignored>, x, y]', whoami);
  end

  fprintf('\n=== DEBUG emc_build_tile_to_branch START ===\n'); % revert
  fprintf('DEBUG: whoami = %s\n', whoami); % revert
  fprintf('DEBUG: VECTOR_OP has %d rows\n', size(VECTOR_OP,1)); % revert
  fprintf('DEBUG: locations has %d tiles\n', length(locations)); % revert

  montage_size = max(locations{end}(2),locations{end}(4));
  fprintf('DEBUG: montage_size = %d\n', montage_size); % revert
  label_montage = zeros(montage_size, montage_size, 'single');

  for label_idx = 1:size(VECTOR_OP,1)
    class_idx = VECTOR_OP(label_idx,1);
    x_idx = VECTOR_OP(label_idx,3); y_idx = VECTOR_OP(label_idx,4);
    if mod(label_idx, 100) == 1 || label_idx <= 10 % revert
      fprintf('DEBUG: Processing label %d: class_idx=%d at (%d,%d)\n', label_idx, class_idx, x_idx, y_idx); % revert
    end % revert
    if class_idx < 1
      error('%s: classIDX must be >= 1 at row %d (got %d)', whoami, label_idx, class_idx);
    end
    if x_idx < 1 || y_idx < 1 || x_idx > montage_size || y_idx > montage_size
      error('%s: coordinate out of bounds at row %d: (%d,%d) not in [1,%d]', whoami, label_idx, x_idx, y_idx, montage_size);
    end
    label_montage(x_idx,y_idx) = class_idx; %#ok<AGROW>
  end
  fprintf('DEBUG: Finished populating label_montage\n'); % revert

  max_class_idx = max(VECTOR_OP(:,1));
  fprintf('DEBUG: max_class_idx = %d\n', max_class_idx); % revert
  fprintf('DEBUG: unique class indices in VECTOR_OP: %s\n', mat2str(unique(VECTOR_OP(:,1))')); % revert
  % Allow n branches for n+1 class labels (including ignore class)
  % This handles cases where class labels can exceed initial tile count due to branch-from-branch scenarios
  if max_class_idx == 1
    % Only ignore class present
    error('%s: need at least one classIDX > 1 to form branches (max classIDX=%d)', whoami, max_class_idx);
  end
  n_branches = max_class_idx - 1;
  fprintf('DEBUG: n_branches = %d\n', n_branches); % revert

  n_tiles = length(locations);
  fprintf('DEBUG: n_tiles = %d\n', n_tiles); % revert
  row_starts = zeros(n_tiles,1); col_starts = zeros(n_tiles,1);
  for ii = 1:n_tiles
    row_starts(ii) = locations{ii}(1);
    col_starts(ii) = locations{ii}(3);
    if ii <= 5 % revert
      fprintf('DEBUG: Tile %d location: [%d %d %d %d]\n', ii, locations{ii}(1), locations{ii}(2), locations{ii}(3), locations{ii}(4)); % revert
    end % revert
  end
  row_vals_top = sort(unique(row_starts),'ascend');
  n_rows = numel(row_vals_top);
  fprintf('DEBUG: n_rows = %d\n', n_rows); % revert
  tile_to_branch = zeros(n_tiles,1,'int32');
  fprintf('DEBUG: Starting tile-to-branch mapping...\n'); % revert
  for tile_index = 1:n_tiles
    x1 = locations{tile_index}(1); x2 = locations{tile_index}(2);
    y1 = locations{tile_index}(3); y2 = locations{tile_index}(4);
    fprintf('\nDEBUG: Processing tile %d with bbox [%d:%d, %d:%d]\n', tile_index, x1, x2, y1, y2); % revert
    region = label_montage(x1:x2, y1:y2);
    fprintf('DEBUG: Region size: %s\n', mat2str(size(region))); % revert
    vals = unique(region(:)); vals = vals(vals > 0);
    fprintf('DEBUG: All unique values in region (including 0): %s\n', mat2str(unique(region(:))')); % revert
    fprintf('DEBUG: Non-zero unique values (vals): %s\n', mat2str(vals')); % revert
    row_from_top = find(row_vals_top == x1, 1, 'first'); if isempty(row_from_top), row_from_top = 1; end
    tiles_in_row = find(row_starts == x1); [~, col_order] = sort(col_starts(tiles_in_row), 'ascend');
    col_idx = find(tiles_in_row(col_order) == tile_index, 1, 'first'); if isempty(col_idx), col_idx = 1; end
    row_from_bottom = n_rows - row_from_top + 1; %#ok<NASU> % retained for error context
    fprintf('DEBUG: Tile position: row_from_bottom=%d, col_idx=%d\n', row_from_bottom, col_idx); % revert
    if isempty(vals)
      error('%s: tile (row=%d, col=%d) has no label; every tile must have at least one label [bbox %d:%d,%d:%d]', ...
            whoami, row_from_bottom, col_idx, x1, x2, y1, y2);
    end
    unique_labels = unique(vals);
    fprintf('DEBUG: unique_labels for tile %d: %s\n', tile_index, mat2str(unique_labels')); % revert
    if numel(unique_labels) > 1
      error('%s: tile (row=%d, col=%d) has conflicting labels %s [bbox %d:%d,%d:%d]', ...
            whoami, row_from_bottom, col_idx, mat2str(unique_labels'), x1, x2, y1, y2);
    end
    if unique_labels == 1
      fprintf('DEBUG: Tile %d has label 1 (ignore), setting tile_to_branch=%d\n', tile_index, 0); % revert
      tile_to_branch(tile_index) = 0;
    else
      fprintf('DEBUG: Tile %d has label %d, setting tile_to_branch=%d\n', tile_index, unique_labels, unique_labels-1); % revert
      tile_to_branch(tile_index) = int32(unique_labels - 1);
    end
  end
  fprintf('\nDEBUG: Final tile_to_branch mapping: %s\n', mat2str(tile_to_branch')); % revert
  fprintf('DEBUG: Tiles mapped to branch 0 (ignored): %s\n', mat2str(find(tile_to_branch == 0)')); % revert
  fprintf('=== DEBUG emc_build_tile_to_branch END ===\n\n'); % revert
end

function branch_geometries = emc_assign_branch_geometries(geometry, tomo_list, tile_to_branch, n_branches, COL_CLASS)
% emc_assign_branch_geometries
% Construct per-branch copies of geometry with reassigned class labels.
%
% Inputs
%   geometry        - struct: fields per tomogram name, each an array (rows=subtomos).
%   tomo_list       - cellstr of tomogram names (fieldnames of geometry).
%   tile_to_branch  - vector mapping class (tile index) -> branch index (0 ignore).
%   n_branches      - number of branches.
%   COL_CLASS       - column index of class label (usually 26).
%
% Output
%   branch_geometries - cell of structs, one per branch, same schema as geometry.
  fprintf('\n=== DEBUG emc_assign_branch_geometries START ===\n'); % revert
  n_tiles = length(tile_to_branch);
  fprintf('DEBUG: n_tiles=%d, n_branches=%d, COL_CLASS=%d\n', n_tiles, n_branches, COL_CLASS); % revert
  fprintf('DEBUG: tile_to_branch mapping: %s\n', mat2str(tile_to_branch')); % revert
  branch_geometries = cell(n_branches,1);
  for b = 1:n_branches
    branch_geometries{b} = geometry;
  end
  for iTomo = 1:length(tomo_list)
    tName = tomo_list{iTomo};
    position_list_orig = geometry.(tName);
    original_class_labels = position_list_orig(:,COL_CLASS);
    included_mask = (position_list_orig(:,COL_CLASS) ~= -9999);

    fprintf('\nDEBUG: Processing tomo %s\n', tName); % revert
    unique_classes = unique(original_class_labels(included_mask)); % revert
    fprintf('DEBUG: Unique class labels in this tomo (excluding -9999): %s\n', mat2str(unique_classes')); % revert
    fprintf('DEBUG: Number of included particles: %d\n', sum(included_mask)); % revert

    for b = 1:n_branches
      pl = position_list_orig;
      pl(included_mask,COL_CLASS) = -9999;
      branch_geometries{b}.(tName) = pl;
    end

    fprintf('DEBUG: Assigning particles to branches based on tile_index...\n'); % revert
    for tile_index = 1:n_tiles
      b = tile_to_branch(tile_index);
      fprintf('  DEBUG: tile_index=%d -> branch=%d\n', tile_index, b); % revert
      if b <= 0
        fprintf('    -> Skipping (branch 0 = ignore)\n'); % revert
        continue;
      end
      class_mask = (original_class_labels == tile_index);
      num_particles = sum(class_mask); % revert
      fprintf('    -> Looking for particles with class==%d: found %d particles\n', tile_index, num_particles); % revert
      if any(class_mask)
        branch_pl = branch_geometries{b}.(tName);
        branch_pl(class_mask,COL_CLASS) = b;
        branch_geometries{b}.(tName) = branch_pl;
        fprintf('    -> Assigned %d particles to branch %d\n', num_particles, b); % revert
      end
    end

    % Debug: Check final assignment % revert
    fprintf('DEBUG: Final particle counts per branch for %s:\n', tName); % revert
    for b = 1:n_branches % revert
      branch_pl = branch_geometries{b}.(tName); % revert
      assigned_count = sum(branch_pl(:,COL_CLASS) == b); % revert
      ignored_count = sum(branch_pl(:,COL_CLASS) == -9999); % revert
      fprintf('  Branch %d: assigned=%d, ignored=%d\n', b, assigned_count, ignored_count); % revert
    end % revert
  end
  fprintf('=== DEBUG emc_assign_branch_geometries END ===\n\n'); % revert
end





