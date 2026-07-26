% test_montage_rotate.m - Validate BH_montage_rotate's header-derived geometry.
%
% The claim under test: tile geometry read from the mrc header reproduces the
% locations cell BH_montage4d returns. If that is false the montage command's
% collapse to a single header-driven path is wrong.

% Synthetic checks only:
%   test_montage_rotate()
%
% Adding the comparison against an output the previous implementation wrote:
%   test_montage_rotate(dataDir, referenceName, oddName, [0,-90,12.5])

function test_montage_rotate(varargin)

fprintf('\n=== montage_rotate tests ===\n\n');

tmpDir = tempname;
mkdir(tmpDir);
cleanup = onCleanup(@() rmdir(tmpDir, 's'));

apparatus_control(tmpDir);
geometry_matches_stored(8, 6, 'cubic tiles');
geometry_matches_stored([8,12,8], 6, 'non-cubic tiles (iDim/jDim regression)');
negative_control_geometry(tmpDir);

if gpuDeviceCount < 1
  fprintf('\nNo GPU visible - skipping rotation tests.\n');
  fprintf('=== structural tests passed ===\n');
  return
end

identity_roundtrip(tmpDir);
halfset_pairing(tmpDir);

if nargin == 4
  reference_comparison(varargin{1}, varargin{2}, varargin{3}, varargin{4});
else
  fprintf('\nNo reference paths given - skipping comparison against the\n');
  fprintf('previous implementation. See the header of this file.\n');
end

fprintf('\n=== all tests passed ===\n');
end


function reference_comparison(dataDir, refName, oddName, angles)
% The positive control. Rotate the same input the previous implementation was
% given and require the same voxels back. This is the only check that can
% falsify the claim that header-derived geometry reproduces the locations that
% used to come from subTomoMeta.
fprintf('\nReference comparison against the previous implementation\n');

refPath = fullfile(dataDir, refName);
oddPath = fullfile(dataDir, oddName);
assert(isfile(refPath), 'reference not found: %s', refPath);
assert(isfile(oddPath), 'input not found: %s', oddPath);
assert(endsWith(oddPath, '_ODD.mrc'), 'input must be the _ODD.mrc half: %s', oddPath);

baseName = oddPath(1:end - length('_ODD.mrc'));
evePath = [baseName, '_EVE.mrc'];
assert(isfile(evePath), 'partner half not found: %s', evePath);

% Non-finite voxels are replaced with randn, so wherever the source carries any
% the two runs cannot agree there by construction. Count them first so a
% mismatch can be attributed instead of guessed at.
oddVol = OPEN_IMG('single', oddPath);
eveVol = OPEN_IMG('single', evePath);
nNonFinite = sum(~isfinite(oddVol(:))) + sum(~isfinite(eveVol(:)));
clear oddVol eveVol
fprintf('  non-finite voxels in source halves : %d\n', nNonFinite);

BH_montage_rotate(oddPath, angles);
newPath = sprintf('%s_rot_%2.2f_%2.2f_%2.2f_STD.mrc', ...
  baseName, angles(1), angles(2), angles(3));
assert(isfile(newPath), 'nothing written at %s', newPath);

refVol = OPEN_IMG('single', refPath);
newVol = OPEN_IMG('single', newPath);
assert(isequal(size(refVol), size(newVol)), ...
  'dimensions differ - reference %s, new %s', ...
  mat2str(size(refVol)), mat2str(size(newVol)));

d = abs(refVol(:) - newVol(:));
tol = 1e-4 .* max(abs(refVol(:)));
nDiff = sum(d > tol);
fprintf('  max abs difference                 : %g\n', max(d));
fprintf('  voxels over tolerance              : %d of %d\n', nDiff, numel(d));
fprintf('  wrote                              : %s\n', newPath);

if nNonFinite == 0
  % Nothing random happened in either run, so any disagreement is real.
  assert(nDiff == 0, ...
    ['%d voxels differ and the source had no non-finite values, so no randn ', ...
     'fill could explain it - header geometry does not reproduce the stored ', ...
     'locations'], nDiff);
  fprintf('  PASS - identical, with no randn fill available to mask a difference\n');
else
  fprintf(['  Source carries non-finite voxels, so a randn-filled population\n', ...
    '  cannot match between runs. Judge by scale: a count near %d is the fill,\n', ...
    '  a count approaching %d is a geometry failure.\n'], nNonFinite, numel(d));
end
end


function tiles = make_tiles(tileSize, nTiles)
% Each tile carries a unique id plus an asymmetric ramp, so a swapped or
% permuted grid is detectable - constant-valued tiles would hide both.
if isscalar(tileSize)
  tileSize = tileSize .* [1,1,1];
end
tiles = cell(nTiles,1);
for i = 1:nTiles
  t = single(zeros(tileSize));
  t(:) = i;
  t(1,:,:) = t(1,:,:) + 100;
  t(:,1,:) = t(:,1,:) + 1000;
  tiles{i} = t;
end
end


function apparatus_control(tmpDir)
% Positive control: montage -> save -> reopen must round-trip independent of
% anything under test. If this fails every result below is meaningless.
fprintf('Apparatus control (montage4d -> SAVE_IMG -> OPEN_IMG)... ');
tiles = make_tiles(8, 4);
mont = BH_montage4d(tiles, '');
f = fullfile(tmpDir, 'apparatus.mrc');
SAVE_IMG(mont, f, 1.5);
back = OPEN_IMG('single', f);
assert(isequal(size(back), size(mont)), 'apparatus: size changed on round-trip');
assert(max(abs(back(:) - mont(:))) == 0, 'apparatus: values changed on round-trip');
fprintf('ok\n');
end


function geometry_matches_stored(tileSize, nTiles, label)
% The load-bearing claim. Unstack the same montage twice - once with the
% locations cell BH_montage4d returned, once with the [nDim,nDim] pair the
% header yields - and require identical tiles.
fprintf('Geometry, %s... ', label);
tiles = make_tiles(tileSize, nTiles);
[mont, imgLoc] = BH_montage4d(tiles, '');

nDim = ceil(sqrt(nTiles));
f = [tempname, '.mrc'];
SAVE_IMG(mont, f, 1.0);
c = onCleanup(@() delete(f));

fromStored  = BH_unStackMontage4d(1:nTiles,   f, imgLoc,        size(tiles{1}));
fromHeader  = BH_unStackMontage4d(1:nDim^2,   f, [nDim, nDim],  []);

for i = 1:nTiles
  assert(isequal(size(fromStored{i}), size(fromHeader{i})), ...
    'tile %d size differs: stored %s vs header %s', i, ...
    mat2str(size(fromStored{i})), mat2str(size(fromHeader{i})));
  assert(max(abs(fromStored{i}(:) - fromHeader{i}(:))) == 0, ...
    'tile %d content differs between stored locations and header geometry', i);
end
fprintf('ok (%d tiles)\n', nTiles);
end


function negative_control_geometry(tmpDir)
% Negative control: the geometry check must reject. If a malformed montage is
% accepted the check is not measuring anything.
fprintf('Negative control, malformed input rejected... ');

bad = single(rand(20, 24, 7));   % nX ~= nY, and neither divisible by nZ
f = fullfile(tmpDir, 'malformed.mrc');
SAVE_IMG(bad, f, 1.0);

threw = false;
try
  BH_montage_rotate(f, [0,0,0]);
catch
  threw = true;
end
assert(threw, 'malformed montage was accepted - geometry check is inert');
fprintf('ok\n');
end


function identity_roundtrip(tmpDir)
% A zero rotation must return the montage it was given. Tile-order inversion
% shows up here and nowhere else.
fprintf('Identity rotation round-trip... ');
tiles = make_tiles(16, 9);
mont = BH_montage4d(tiles, '');
f = fullfile(tmpDir, 'identity.mrc');
pixelSize = 2.5;
SAVE_IMG(mont, f, pixelSize);

BH_montage_rotate(f, [0,0,0]);
outName = fullfile(tmpDir, 'identity_rot_0.00_0.00_0.00.mrc');
assert(isfile(outName), 'expected output %s was not written', outName);

out = OPEN_IMG('single', outName);
assert(isequal(size(out), size(mont)), 'identity changed montage dimensions');
tol = 1e-3 * max(abs(mont(:)));
assert(max(abs(out(:) - mont(:))) < tol, ...
  'identity rotation altered the montage by more than interpolation round-off');

outPix = getCellX(MRCImage(outName)) ./ getMX(MRCImage(outName));
assert(abs(outPix - pixelSize) < 1e-4, ...
  'pixel size not carried through: in %f, out %f', pixelSize, outPix);
fprintf('ok\n');
end


function halfset_pairing(tmpDir)
% Naming either half must sum both. Naming EVE and silently getting a half-set
% back would be a wrong answer that looks correct.
fprintf('Half-set pairing... ');
tiles = make_tiles(16, 4);
montOdd = BH_montage4d(tiles, '');
montEve = 2 .* montOdd;

oddName = fullfile(tmpDir, 'pair_ODD.mrc');
eveName = fullfile(tmpDir, 'pair_EVE.mrc');
SAVE_IMG(montOdd, oddName, 1.0);
SAVE_IMG(montEve, eveName, 1.0);

BH_montage_rotate(oddName, [0,0,0]);
outName = fullfile(tmpDir, 'pair_rot_0.00_0.00_0.00_STD.mrc');
assert(isfile(outName), 'expected paired output %s was not written', outName);

out = OPEN_IMG('single', outName);
expected = montOdd + montEve;
tol = 1e-3 * max(abs(expected(:)));
assert(max(abs(out(:) - expected(:))) < tol, ...
  'paired output is not the sum of the two half-sets');

% Same result from the EVE side.
delete(outName);
BH_montage_rotate(eveName, [0,0,0]);
assert(isfile(outName), 'naming the EVE half did not pair back to ODD');
fprintf('ok\n');
end
