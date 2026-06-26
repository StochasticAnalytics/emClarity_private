function [ selected, other ] = BH_classModificationsFromModFile( ...
                                 MOD_FILE, locations, classVector, className, ...
                                 outputFile, selHeader, otherHeader, weightOnSelected )
%BH_classModificationsFromModFile  Map a montage-drawn .mod to class indices.
%
%   Reads an IMOD .mod file drawn on a class-average montage, determines which
%   class TILE each model point falls in, and writes a two-section text file:
%   the MARKED ("selected") classes and the UNMARKED ("other") classes. This is
%   the shared "read mod -> locate x,y -> classify -> write text file" core used
%   to translate a hand-drawn montage selection into the class-index vectors
%   emClarity consumes (e.g. Raw_classes).
%
%   It performs NO geometry edits and NO subTomoMeta writes -- it ONLY produces
%   the text file and returns the two class-index lists. The caller owns any
%   downstream -9999 marking (see BH_geometryAnalysis 'RemoveClasses', which keeps
%   its own inline cull and uses this helper only to emit the keep-side file).
%
% Inputs
%   MOD_FILE         - path to the IMOD .mod (the montage selection)
%   locations        - cell array of per-class tile bboxes {[x0 x1 y0 y1]} from
%                      subTomoMeta.<cycle>.<class_K_Locations_<prefix>_<half>_NoWgt>{2}
%   classVector      - classVector{1} = class indices actually present in the
%                      average, i.e. {3}(1,:) of the same montage field
%   className        - total number of classes (emc.<prefix>_className)
%   outputFile       - text file to write (e.g. cycleNNN_ClassKeep_STD.txt)
%   selHeader        - header line for the MARKED list   (e.g. 'Classes kept:')
%   otherHeader      - header line for the UNMARKED list (e.g. 'Classes dropped:')
%   weightOnSelected - true  -> the "; 1.*ones(1,N)" weights go on the MARKED list
%                      false -> the weights go on the UNMARKED list.
%                      The weighted list is the Raw_classes-bound one; classes not
%                      present in the average have no data and are forced onto the
%                      NON-weighted list regardless.
%
% Outputs
%   selected - sorted class indices whose montage tile was MARKED in MOD_FILE
%   other    - sorted class indices whose montage tile was UNMARKED

% Parse the mod into obj/cont/x/y/z rows (identical to BH_geometryAnalysis's reader).
[~, modName, ~] = fileparts(MOD_FILE);
system(sprintf('model2point -ObjectAndContour %s %s.txt > /dev/null', MOD_FILE, modName));
points = importdata(sprintf('%s.txt', modName));
points = round(points);

% Mark each drawn x,y in a blank montage-sized canvas (montage is square; the
% last tile's box gives the extent). Columns are obj cont x y z.
size_montage = max(locations{end}(2), locations{end}(4));
blankClassMont = zeros(size_montage, size_montage, 'single');
for ii = 1:size(points, 1)
  blankClassMont(points(ii,3), points(ii,4)) = 1;
end

% Classes not present in the average have no data -> they can never be the active
% (weighted) selection, so force them onto the non-weighted list.
classes_not_in_average = find(~ismember(1:className, classVector{1}));
selected = [];
other = [];
if (weightOnSelected)
  other = classes_not_in_average;
else
  selected = classes_not_in_average;
end

% Classify each remaining class tile as marked (selected) or unmarked (other).
for iClass = 1:length(locations)
  if ismember(iClass, classes_not_in_average)
    continue
  end
  iCut = blankClassMont(locations{iClass}(1):locations{iClass}(2), ...
                        locations{iClass}(3):locations{iClass}(4));
  if any(iCut(:))
    selected = [selected, iClass];
  else
    other = [other, iClass];
  end
end
selected = sort(selected, 'ascend');
other    = sort(other,    'ascend');

% Write the two-section file: marked list then unmarked list, weights on whichever
% list is the Raw_classes-bound selection.
fileOUT = fopen(outputFile, 'w');
local_write_section(fileOUT, selHeader,   selected, weightOnSelected);
local_write_section(fileOUT, otherHeader, other,    ~weightOnSelected);
fclose(fileOUT);

end

function local_write_section(fileOUT, header, list, withWeights)
  fprintf(fileOUT, '%s\n', header);
  if isempty(list)
    fprintf(fileOUT, '[]\n\n');
    return
  end
  fprintf(fileOUT, '[%g', list(1));
  if (numel(list) > 1)
    fprintf(fileOUT, ',%g', list(2:end));
  end
  if (withWeights)
    fprintf(fileOUT, '; 1.*ones(1,%d)]\n\n', numel(list));
  else
    fprintf(fileOUT, ']\n\n');
  end
end
