function [ ] = BH_montage_rotate( MONTAGE_NAME, EULER_ZXZ )
%Rotate each sub-volume of a montage and re-tile the result.
%
%   Input variables:
%
%   MONTAGE_NAME = string, path to a montage written by BH_montage4d.
%
%   EULER_ZXZ = 3 vector, ZXZ Euler angles in degrees applied to every tile.
%
%   Output variables:
%
%   none - writes an mrc beside the input, named for the rotation applied.
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%
%   Goals & limitations
%
%   Tile geometry is recovered from the mrc header rather than from a locations
%   cell stored in subTomoMeta. That is what lets the eigenImage montages from
%   BH_pcaPub be rotated at all - BH_pcaPub discards the locations BH_montage4d
%   returns and records nothing about those montages, so there is no metadata to
%   look up. Reading the header instead means any BH_montage4d product can be
%   rotated, and no parameter file is needed.
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%
%   TODO:
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

if ~isfile(MONTAGE_NAME)
  error('\n\nFile does not exist: %s\n\n', MONTAGE_NAME);
end

mrcIMG = MRCImage(MONTAGE_NAME);
volSize = getDimensions(mrcIMG);
tileEdge = volSize(3);

% BH_montage4d tiles onto an nDim x nDim grid with padSize = 0 and keeps the full
% Z depth of each sub-volume, and every box handed to it is cubic
% (BH_multi_validArea forces .*[1,1,1]). Those two facts make the tile edge equal
% to nZ and fix the grid order at nX/nZ, so the stored locations are redundant.
if volSize(1) ~= volSize(2) || rem(volSize(1), tileEdge)
  error(['\n\n%s is %d x %d x %d, which is not a square montage of cubic tiles.\n', ...
    'Expected nX == nY, and nX divisible by nZ.\n\n'], ...
    MONTAGE_NAME, volSize(1), volSize(2), volSize(3));
end

nDim = volSize(1) ./ tileEdge;

% The montages emClarity writes all carry a pixel size (BH_pcaPub and
% BH_average3d both pass one to SAVE_IMG) so recover it rather than dropping the
% scale on the output.
pixelSize = getCellX(mrcIMG) ./ getMX(mrcIMG);
if ~isfinite(pixelSize) || pixelSize <= 0
  error(['\n\nCannot recover a pixel size from the header of %s\n', ...
    '(cellDimensionX %f, mX %d). Montages written by emClarity carry one.\n\n'], ...
    MONTAGE_NAME, getCellX(mrcIMG), getMX(mrcIMG));
end

% The gold-standard halves are sibling files differing only in this suffix
% (BH_average3d) and only their sum is interpretable. Detecting either half means
% naming the EVE file cannot silently yield a half-set montage that looks
% combined. Matching on the suffix rather than anywhere in the string keeps a
% directory called _ODD.mrc_something from being rewritten.
if endsWith(MONTAGE_NAME, '_ODD.mrc')
  halfToken = '_ODD.mrc';
  partnerToken = '_EVE.mrc';
elseif endsWith(MONTAGE_NAME, '_EVE.mrc')
  halfToken = '_EVE.mrc';
  partnerToken = '_ODD.mrc';
else
  halfToken = '';
end

% The numeric [nRows, nCols] branch of BH_unStackMontage4d synthesizes the
% extraction indices, walking dim 1 fastest to match BH_montage4d's fill order.
% It trims nothing, so the unused sizeWINDOW argument is empty.
tileStack = BH_unStackMontage4d(1:nDim^2, MONTAGE_NAME, [nDim, nDim], []);

if isempty(halfToken)
  % Only strip an extension that is actually there - blind truncation would eat
  % four characters of the stem for anything not named .mrc.
  if endsWith(MONTAGE_NAME, '.mrc')
    baseName = MONTAGE_NAME(1:end - length('.mrc'));
  else
    baseName = MONTAGE_NAME;
  end
  outSuffix = '';
else
  baseName = MONTAGE_NAME(1:end - length(halfToken));
  outSuffix = '_STD';
  partnerName = [baseName, partnerToken];

  if ~isfile(partnerName)
    error(['\n\n%s names one half-set but its partner is missing:\n  %s\n', ...
      'Both halves are needed - only the combined average is interpretable.\n\n'], ...
      MONTAGE_NAME, partnerName);
  end

  partnerSize = getDimensions(MRCImage(partnerName));
  if any(partnerSize ~= volSize)
    error(['\n\nHalf-set geometry disagrees.\n  %s is %d x %d x %d\n', ...
      '  %s is %d x %d x %d\n\n'], ...
      MONTAGE_NAME, volSize(1), volSize(2), volSize(3), ...
      partnerName, partnerSize(1), partnerSize(2), partnerSize(3));
  end

  fprintf('\nPairing half-sets\n  %s\n  %s\n', MONTAGE_NAME, partnerName);
  partnerStack = BH_unStackMontage4d(1:nDim^2, partnerName, [nDim, nDim], []);
end

fprintf('\nRotating %d tiles of %d^3 by [%2.2f, %2.2f, %2.2f] (ZXZ)\n', ...
  nDim^2, tileEdge, EULER_ZXZ(1), EULER_ZXZ(2), EULER_ZXZ(3));

tileStack = rotate_tiles(tileStack, EULER_ZXZ, nDim^2);

% Each half is rotated on its own and combined afterwards. Summing first would
% be equivalent for the density - interpolation is linear - but not for the
% noise fill below: it would put the substituted values through the
% interpolator and spread them into neighbouring voxels.
if ~isempty(halfToken)
  partnerStack = rotate_tiles(partnerStack, EULER_ZXZ, nDim^2);
  for iTile = 1:nDim^2
    tileStack{iTile} = tileStack{iTile} + partnerStack{iTile};
    % Masked-out voxels arrive here as NaN or Inf from the average and would
    % otherwise poison every statistic taken over the montage.
    nonFinite = ~isfinite(tileStack{iTile}(:));
    tileStack{iTile}(nonFinite) = randn(size(tileStack{iTile}(nonFinite)));
  end
  clear partnerStack
end

montOUT = BH_montage4d(tileStack, '');

outName = sprintf('%s_rot_%2.2f_%2.2f_%2.2f%s.mrc', ...
  baseName, EULER_ZXZ(1), EULER_ZXZ(2), EULER_ZXZ(3), outSuffix);

SAVE_IMG(montOUT, outName, pixelSize);

fprintf('\nWrote %s\n', outName);

end % end of montage_rotate function


function [ STACK ] = rotate_tiles( STACK, EULER_ZXZ, nTiles )
% Resample every tile in place on the gpu.
%
% useOnlyOnce is true so each texture object is released as its tile finishes;
% left false the interpolator strands one handle object per tile.

for iTile = 1:nTiles
  [~, rotIMG] = interpolator(gpuArray(STACK{iTile}), EULER_ZXZ, [0,0,0], ...
    'Bah', 'forward', 'C1', true);
  STACK{iTile} = gather(rotIMG);
end

end % end of rotate_tiles function
