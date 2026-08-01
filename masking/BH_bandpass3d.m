function [ BANDPASS ] = BH_bandpass3d( SIZE, HIGH_THRESH, HIGH_CUT, LOW_CUT, ...
  METHOD, PIXEL_SIZE, varargin )
%Create a bandpass filter, to apply to fft of real space 3d images.
%
%   Input variables:

%   SIZE = size of the image filter is to be applied to : vector, float
%
%   HIGH_THRESH = Percent attenuation of low frequency : float
%
%   HIGH_CUT  = Spatial frequency high-pass back to 100% (A^-1) : float
%
%   LOW_CUT= Spatial frequency low-pass starts to roll off :  float
%
%   METHOD = 'GPU' case specific, create mask on GPU, otherwise on CPU
%
%   PIXEL_SIZE = Sampling frequency : Angstrom/Pixel
%
%
%   Output variables:
%
%   BANDPASS  = 3d MRC image file, single precision float.
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%
%   Goals & Limitations:
%
%   Creates a bandpass filter, that falls off smoothly enough to avoid
%   artifacts, while also restricting information to the expected ranges.
%   This is accomplished by oversampling the image to be filtered, so that
%   the fall off can be over a sufficient number of pixels, while still
%   happening over a small range of frequency.
%
%   Because this is frequency space, the fall off depends on the resolution
%   where it begins. For sampling of 3A/pixel with a cutoff starting at
%   20A^-1 the spatial frequency drops to ~ 17.3 over six pixels if the
%   frequency rectangle is 256 pixel sq. For a cutoff starting at 10A the
%   drop over 6 pixels is only to ~9.3
%
%   For the monolayer work, the largest dimension is ~140 pixels, s.t. 256
%   provides a substantial padding for cross-correlation, and also a
%   reasonably tight window for filtering. The memory requirements are ~
%   67/134 mb for single/double precision, compared to another order of
%   magnitude for 512.
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%
%   TODO:
%     -test with gpu flag
%
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


if numel(SIZE) == 2
  SIZE = [SIZE,1];
end

% The following will adjust the apodization window, and is not intended for
% regular users to adjust. The value of 2.0 makes for a nice (soft) fall
% off over ~ 7 pixels. Larger value results in a steeper cutoff.
% Corresponds to the standard deviation in the gaussian roll.
if isnumeric(PIXEL_SIZE)
  [bSize, highRoll, lowRoll, highCut, lowCut] = calc_frequencies( ...
    SIZE, HIGH_THRESH, HIGH_CUT, LOW_CUT, PIXEL_SIZE );
else
  % This branch took ANY non-numeric PIXEL_SIZE, not only 'nyquistHigh'. Under that
  % sentinel it set the high-pass from the box, at 7/N voxels, so the same call removed a
  % different band at every box size. Any OTHER string reached its else path, meaning no
  % high-pass and a low-pass at 0.485 cycles/pixel; write that as HIGH_CUT of 0 with a
  % unit PIXEL_SIZE and LOW_CUT of 1/0.485, since only their ratio sets the corner.
  error(['A non-numeric PIXEL_SIZE is no longer accepted: pass HIGH_THRESH, HIGH_CUT ', ...
         'and LOW_CUT with a numeric PIXEL_SIZE. Got PIXEL_SIZE = %s'], PIXEL_SIZE);
end

gaussian = @(x,m,s) exp( -1.*(x-m).^2 ./ (2.*s.^2) );

half_grid = false;
if nargin > 6
  if strcmpi(varargin{1},'halfGrid')
    half_grid = true;
  end
end

if (half_grid)
  nX = emc_get_origin_index(bSize(1));
else
  nX = bSize(1);
end
% initialize window of appropriate size
if strcmp(METHOD, 'GPU')
  mWindow(nX,bSize(2),bSize(3)) = gpuArray(single(0));
else
  mWindow(nX,bSize(2),bSize(3)) = single(0);
end
mWindow = mWindow + 1;

%%%% This is ~ 120x faster than = gpuArray(ones(bSize, 'single'));
% initialize nd grids of appropriate size

if (half_grid)
  [ radius,~,~,~,~,~] = BH_multi_gridCoordinates( bSize, 'Cartesian', METHOD, ...
  {'single',...
  [1,0,0;0,1,0;0,0,1],...
  [0,0,0]','forward',1,1}, ...
  1, 0, 1, {'halfGrid'} );
else
  [ radius,~,~,~,~,~] = BH_multi_gridCoordinates( bSize, 'Cartesian', METHOD, ...
  {'single',...
  [1,0,0;0,1,0;0,0,1],...
  [0,0,0]','forward',1,1}, ...
  1, 0, 1 );

end


% Calc lowpass filter
mWindow = ...
  ( (radius < lowCut) .* mWindow + ...
  (radius >= lowCut) .* gaussian(radius, lowCut, lowRoll) );

% Breaks Hermitian symmetry
% % % Don't randomize the high-pass since the signal it modulates is very
% % % strong.
% % mWindow = BH_multi_randomizeTaper(mWindow);
% Add in high pass if required

if highCut ~= 0
  mWindow = (radius <= highCut) .* gaussian(radius, highCut, highRoll) + ...
    (radius > highCut) .* mWindow;
end

%mWindow((mWindow<= 10^-8)) = 0;
BANDPASS = mWindow;
clearvars -except BANDPASS

end % end of BH_mask3d function.


function [bSize, highRoll, lowRoll, highCut, lowCut] = calc_frequencies(...
  SIZE, HIGH_THRESH, HIGH_CUT, LOW_CUT, PIXEL_SIZE )

bSize = SIZE;

% Check that the value makes sense.
if ( 0 > HIGH_THRESH || HIGH_THRESH >= 1)
  error('HIGH_THRESH must be between 0 and 1, not %f', HIGH_THRESH)
end



% Translate boundries from A^-1 to cycles/pixel. A value of zero means no
% high pass filter.
if HIGH_CUT ~= 0
  highCut = PIXEL_SIZE ./ HIGH_CUT;

  % The high-pass ramps from HIGH_THRESH at DC up to 1 at HIGH_CUT. Its slope must stay
  % under 1/7 per voxel or the transition acts as a hard cut -- 1/7 is the gentle bound
  % for normally distributed data, and would be wrong for data ranging to 10^6. Where the
  % ramp ends is the caller's resolution, so the value to move is HIGH_THRESH. min() takes
  % the axis with the fewest voxels across the ramp, since each is normalised by its own
  % length in BH_multi_gridCoordinates.
  %
  % A ramp shorter than one voxel is exempt: it ends before the first sample off DC, so
  % nothing is left to be steep between and the filter reduces to scaling DC, the same
  % operation as subtracting the mean.
  nSmallest = min(bSize(bSize > 1));
  rampVoxels = nSmallest .* highCut;
  if ( rampVoxels >= 1 && (1 - HIGH_THRESH) ./ rampVoxels > 1/7 )
    error(['A high-pass reaching 1 at %g A on a %d pixel axis at %g A/pixel ramps up ', ...
           'from HIGH_THRESH = %g over %.2f voxels, a slope of %.4f per voxel against ', ...
           'a limit of %.4f. Raise HIGH_THRESH to at least %.4f.'], ...
          HIGH_CUT, nSmallest, PIXEL_SIZE, HIGH_THRESH, rampVoxels, ...
          (1 - HIGH_THRESH) ./ rampVoxels, 1/7, 1 - rampVoxels./7);
  end
else
  highCut = 0;
end
lowCut  = PIXEL_SIZE ./ LOW_CUT;

% fixed lowpass roll off, cycles/pix depends on dimension of image
% if lowCut is negative, indicates a "SIRT like" lowpass and filter rolls
% from 1 at abs(lowCut) to 10^-8 at 20A

if (lowCut > 0)
  if (bSize(3) == 1)
    lowRoll = 2.0 .* (1.0./min(bSize(1:2)));
  else
    lowRoll = 2.0 .* (1.0./min(bSize));
  end
else
  lowCut = abs(lowCut);
  lowEND = 0.5;%PIXEL_SIZE ./ 20;
  lowRoll = sqrt((-1.*(lowEND-lowCut).^2)./(2.*log(10^-3)));
end

% calc the highpass roll off
if HIGH_CUT ~= 0
  highRoll = sqrt((-1.*highCut.^2)./(2.*log(HIGH_THRESH)));
else
  highRoll = 0;
end



end % end of calc_frequencies function.



