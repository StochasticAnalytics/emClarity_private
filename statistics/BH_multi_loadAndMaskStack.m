function [ STACK ] = BH_multi_loadAndMaskStack(STACK,TLT,mapBackIter,THICKNESS,PIXEL_SIZE,HIGH_PASS,varargin)
%Relative weighting of a tilt-series
%   Weight projections after normalizing stats (mean and unit var)
%   1) For best expected signal, which is assumed to be the fraction of
%   inelestics. Assume 100nm thickness unless an estimate is known from
%   tomoCPR. Use meanfree path for in-elastics of 400nm
%   2) Normal schemes aim to have ~ the same dose at the detector. If this
%   is not true, the projections must be weighted appropriately. For the
%   initial implementation, this will require a "custom" order file which
%   has for each tilt:
%     1 - number in stack
%     2 - order in data collection (from 1) -9999 to skip
%     3 - total dose on *this* tilt (not cummulative)
%     4 - defocus 1
%     5 - defocus 2
%     6 - astigmatism angle
%
%     The final columns can be set to zero to calculate in ctf_estimate,
%     otherwise the program will now just set up the tlt info, resample the
%     stack, and exit.
%
%     % Store the dose per-tilt in col 14 (cummul. dose is in 11)
%
%
%     % STACK - 3d vol stack, or PATH to file
%     % TLT - loaded tilt geometry
%     % THICKNESS - estimate for thickness
%     % PIXEL_SIZE - angstrom
%     % HIGH_PASS - [HIGH_THRESH, resolution in angstrom] for the gradient prefilter
%     %
%     % STACK - Modified stack in mem, or on disk

EDGE_PAD = 64; % min dist to edge for stats calc

if (THICKNESS < 10 || THICKNESS > 1000)
  error('Your sample thickness is likely incorrect, it should be between 10 and 1000 nm, not %d \n',THICKNESS);
end

% A negative PIXEL_SIZE used to select a filter-only path that skipped the normalization
% and dose weighting below. No caller has taken it, and the prefilter it selected now runs
% on every projection regardless, so the flag has nothing left to switch.
if (PIXEL_SIZE < 0)
  error('PIXEL_SIZE must be positive, not %g. The filter-only path it selected is gone.', PIXEL_SIZE);
end

if nargin > 6
  useMask = 1;
else
  useMask = 0;
end

% Override the thickness for now, if the sample isn't flat, the method to
% calculate it based on subTomogram coordinates in 3d is not correct
THICKNESS = 75;
if ~isnumeric(STACK)
  error('This branch is deprecated and should not be reached.');
end

[d1,d2,d3] = size(STACK);

if isa(STACK,'gpuArray')
  flgOnDevice = 1;
else
  flgOnDevice = 0;
end

meanVariance = 0;

% Gradient prefilter. The mean subtraction below is commented "Remove gradients" but
% subtracts a scalar, so a real gradient across the projection survives it into the
% aligned stack, which is the only pixel source for everything built afterwards.
% low-pass = Nyquist
gradientPrefilter = BH_bandpass3d([d1,d2,1],HIGH_PASS(1),HIGH_PASS(2), ...
                                  2.*PIXEL_SIZE,'GPU',PIXEL_SIZE);

fractionOfDose = TLT(:,14)/mean(TLT(:,14));
fractionOfElastics = exp(-1.*THICKNESS./( cosd(TLT(:,4)).*400 ));
fractionOfElastics = fractionOfElastics ./ max(fractionOfElastics(:));

for iPrj = 1:d3
  
  if (flgOnDevice)
    iProjection = STACK(:,:,TLT(iPrj,1));
  else
    iProjection = gpuArray(STACK(:,:,TLT(iPrj,1)));
  end

  % Roll the outer 7 pixels toward the projection mean before transforming, so
  % the frame edges do not ring into the low frequencies the prefilter shapes.
  % The [0,0],[0,0] extents add no pixels -- this tapers in place.
  iProjection = BH_padZeros3d(iProjection,[0,0],[0,0],'gpuArray','singleTaper',mean(iProjection(:)));
  iProjection = real(ifftn(fftn(iProjection).*gradientPrefilter));

  if (useMask)
    iProjection = iProjection - mean2(iProjection(varargin{1}(:,:,TLT(iPrj,1))>0));
    iProjection = iProjection ./ rms(rms(iProjection(varargin{1}(:,:,TLT(iPrj,1))>0)));
  else
    maxEval = cosd(TLT(iPrj,4)).*(d1/2) + (THICKNESS*10./(PIXEL_SIZE))./2*abs(sind(TLT(iPrj,4)));
    oX = ceil((d1+1)./2);
    iEvalMask = max(EDGE_PAD,floor(oX-maxEval)):min(d1-EDGE_PAD,ceil(oX+maxEval));
    
    % Remove gradients
    % Center under mask
    iProjection = iProjection - mean2(iProjection(iEvalMask,EDGE_PAD:end-EDGE_PAD));
    % Unit variance
    iProjection = iProjection ./ rms(rms(iProjection(iEvalMask,EDGE_PAD:end-EDGE_PAD)));
  end
  
  
  
  iProjection = iProjection .* (fractionOfDose(iPrj)*fractionOfElastics(iPrj));
  
  %   if (useMask)
  %     meanVariance = meanVariance + rms(rms(iProjection(varargin{1}(:,:,TLT(iPrj,1))>0)));
  %   else
  %     meanVariance = meanVariance + rms(rms(iProjection(iEvalMask,EDGE_PAD:end-EDGE_PAD)));
  %   end
  
  
  
  if (flgOnDevice)
    STACK(:,:,TLT(iPrj,1)) = iProjection;
  else
    STACK(:,:,TLT(iPrj,1)) = gather(iProjection);
  end
  
end % end loop over projections



end % end of function

