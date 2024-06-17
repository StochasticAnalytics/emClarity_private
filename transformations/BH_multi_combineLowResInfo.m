function [ outputRefs ] = BH_multi_combineLowResInfo( inputRefs, inputCounts, pixelSize, resCutOff )
%UNTITLED Summary of this function goes here
%   Detailed explanation goes here

use_original = false;
input_was_resized = false;
padded_size = 512;

if (use_original)
  method = 'cpu';
  wanted_size = [1,1,1] .* padded_size;
  if ~all(size(inputRefs) == wanted_size)
    input_was_resized = true;
  end
else
  method = 'GPU';
  wanted_size = size(inputRefs{1}{1});
end
refIDX = BH_multi_isCell( inputRefs{1} );
nRefs = length(refIDX);

[radialGrid,~,~,~,~,~] = BH_multi_gridCoordinates(wanted_size, 'Cartesian', method, {'none'}, 1, 0, 1);
radialGrid = radialGrid ./ pixelSize;
shared_lowres_info_idx = (radialGrid < 1./resCutOff);
radialGrid = [];

outputRefs = cell(2,1);
outputRefs{1} = cell(nRefs,1);
outputRefs{2} = cell(nRefs,1);

for iRef = refIDX'
  % For today assume equal contributions, I think I already save this in the
  % meta data, so add this in soon.
  %   oddWeight = sum(nExtracted(iClassPos,1)) ./ sum(nExtracted(iClassPos,1:2))
  %   eveWeight = sum(nExtracted(iClassPos,2)) ./ sum(nExtracted(iClassPos,1:2))
  oddWeight = inputCounts{1}(2,iRef) ./ (inputCounts{1}(2,iRef) + inputCounts{2}(2,iRef));
  eveWeight = inputCounts{2}(2,iRef) ./ (inputCounts{1}(2,iRef) + inputCounts{2}(2,iRef));

  if (abs(eveWeight - oddWeight) > 0.25)
    fprintf('Warning: The weights for the two half-maps (%f and %f) are not equal, this may cause issues with the final map.\n', oddWeight, eveWeight);
  end
  
  
  
  [ combPAD ] = BH_multi_padVal( size(inputRefs{1}{iRef}), wanted_size );
  % Oversample so the cutoff is more accurate, and use double precision for the
  % same reason.
  outputRefs{1}{iRef} = fftn(BH_padZeros3d(inputRefs{1}{iRef}, combPAD(1,:), combPAD(2,:), method, 'singleTaper'));
  outputRefs{2}{iRef} = fftn(BH_padZeros3d(inputRefs{2}{iRef}, combPAD(1,:), combPAD(2,:), method, 'singleTaper'));
  
  sharedInfo = oddWeight.*outputRefs{1}{iRef}(shared_lowres_info_idx) + eveWeight.*outputRefs{2}{iRef}(shared_lowres_info_idx);
  
  if (use_original)
    outputRefs{1}{iRef} = real(ifftn(sharedInfo + (radialGrid >= 1/resCutOff).*outputRefs{1}{iRef}));
    outputRefs{2}{iRef} = real(ifftn(sharedInfo + (radialGrid >= 1/resCutOff).*outputRefs{2}{iRef}));
  else
    outputRefs{1}{iRef}(shared_lowres_info_idx) = sharedInfo;
    outputRefs{2}{iRef}(shared_lowres_info_idx) = sharedInfo;
    outputRefs{1}{iRef} = real(ifftn( outputRefs{1}{iRef}));
    outputRefs{2}{iRef} = real(ifftn( outputRefs{2}{iRef}));
  end    

  clear sharedInfo oddWeight eveWeight
    
  if (use_original)
    outputRefs{1}{iRef} = single( outputRefs{1}{iRef}(1+combPAD(1,1):end-combPAD(2,1), ...
                                                      1+combPAD(1,2):end-combPAD(2,2), ...
                                                      1+combPAD(1,3):end-combPAD(2,3)));
    
    outputRefs{2}{iRef} = single( outputRefs{2}{iRef}(1+combPAD(1,1):end-combPAD(2,1), ...
                                                      1+combPAD(1,2):end-combPAD(2,2), ...
                                                      1+combPAD(1,3):end-combPAD(2,3)));
  end    
end
clear inputRefs
end

