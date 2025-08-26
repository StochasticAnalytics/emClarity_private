function []  = BH_templateSearch3d_2( PARAMETER_FILE,...
  tomoName,tomoIdx,TEMPLATE, ...
  SYMMETRY, wedgeType, varargin)


%3d template matching

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


ctf3dNoSubTomoMeta = true;
if length(varargin) > 0
  % Allow for an override of the max number, useful when only a few tomos
  % have a strong feature like carbon that is hard to avoid.
  gpuIDX = EMC_str2double(varargin{1});
else
  gpuIDX = 1;
end
if length(varargin) == 2
  mapBackIter = EMC_str2double(varargin{2});
else
  mapBackIter = 0;
end
if length(varargin) > 2
  error('emClarity templateSearch paramN.m tiltN regionN referenceName symmetry(C1) <optional gpuIDX> <optional mapBackITer>');
end

tomoIdx = EMC_str2double(tomoIdx);

[ useGPU ] = BH_multi_checkGPU( gpuIDX );



gpuDevice(useGPU);

%  For now just override this as it doesn't do too much (randomizing symmetry mates. And doesn't work with new symmetry ops
% Need to get the symmetry mats from an interpolator object
% SYMMETRY = EMC_str2double(SYMMETRY);
SYMMETRY=1;

startTime = datetime("now") ;

emc = BH_parseParameterFile(PARAMETER_FILE);

% Currently hardcoded to always expect a tomogram constructed with ctf correction
% using emClarity ctf3d paramN.m templateSearch
use_ctf3d_templateSearch=true;

samplingRate  = emc.('Tmp_samplingRate');

test_half = emc.('Tmp_half_precision');



peakThreshold = emc.('Tmp_threshold');


latticeRadius = emc.('particleRadius');
try
  targetSize    = emc.('Tmp_targetSize')
catch
  targetSize = [512,512,512];
end
angleSearch   = emc.('Tmp_angleSearch');


convTMPNAME = sprintf('convmap_wedgeType_%d_bin%d',wedgeType,samplingRate)


try
  eraseMaskType = emc.('Peak_mType');
catch
  eraseMaskType = 'sphere';
end
try
  eraseMaskRadius = emc.('Peak_mRadius');
catch
  eraseMaskRadius = 1.0.*latticeRadius;
end


nPreviousSubTomos = 0;

reconScaling = 1;


ignore_threshold = false;
try
  max_tries = emc.('max_peaks');
catch
  max_tries = 10000;
end

try
  over_ride =  emc.('Override_threshold_and_return_N_peaks')
  ignore_threshold = true;
  fprintf('Override_threshold_and_return_N_peaks set to true, returning exactly %d peaks\n', over_ride);
  peakThreshold = over_ride;
end

pixelSizeFULL = emc.pixel_size_angstroms;

pixelSize =  emc.pixel_size_angstroms .* samplingRate;

% For testing
print_warning=false;



bp_vals = emc.('Tmp_bandpass');

try
  stats_diameter_fraction = emc.('diameter_fraction_for_local_stats')
catch
  stats_diameter_fraction = 1
end


mean_r2 = 0;
mean_r_mask = 0;
reference_mask = [];

try 
  measure_noise_variance = emc.('measure_noise_variance');
catch
  measure_noise_variance = false;
end


if pixelSize*2 >  bp_vals(3)
  fprintf('\nLimiting to Nyquist (%f) instead of user requested low pass cutoff %f Angstrom\n',pixelSize*2,bp_vals(3));
  bp_vals(3) = pixelSize*2;
end


mapPath = './cache';
mapName = sprintf('%s_%d_bin%d',tomoName,tomoIdx,samplingRate);
mapExt = '.rec';

% [ recGeom, ~, ~, ~] = BH_multi_recGeom( sprintf('recon/%s_recon.coords',tomoName), mapBackIter);


% bp_vals(2) = 2.*max(latticeRadius);
statsRadiusAng = stats_diameter_fraction.*[2,2,2].*max(latticeRadius);
statsRadius = ceil(statsRadiusAng./pixelSize); % Convert to binned pixels
maskRadius  = ceil(0.5.*[1,1,1].*max(latticeRadius)./pixelSize);
latticeRadius = (0.75 .* latticeRadius) ./ (pixelSize);
latticeRadius = floor(latticeRadius);
latticeRadius = latticeRadius + mod(latticeRadius, 2);

eraseMaskRadius = floor((eraseMaskRadius) ./ (pixelSize));
eraseMaskRadius = eraseMaskRadius + mod(eraseMaskRadius,2);

% fprintf('EXPERIMENTAL setting the highpass to match the max particle diameter. %3.3f Ang\n\n', bp_vals(2));

fprintf('\ntomograms normalized in %f Angstrom cubic window\n',statsRadiusAng(1));

fprintf('\nlatticeRadius = %dx%dx%d pixels\n\n', latticeRadius);
fprintf('\neraseMaskType %s, eraseMaskRadius %dx%dx%d pixels\n',eraseMaskType,eraseMaskRadius);
% For wedgeMask
particleThickness =  latticeRadius(3);


do_load = true;
[ tomogram ] = BH_multi_loadOrBuild(emc.alt_cache, ...
                                    sprintf('%s_%d',tomoName,tomoIdx),  ...
                                    mapBackIter, ...
                                    samplingRate,...
                                    gpuIDX, ...
                                    do_load, ...
                                    '');


% We'll handle image statistics locally, but first place the global environment
% into a predictible range



[template, tempPath, tempName, tempExt] = BH_multi_loadOrBin( TEMPLATE, 1, 3, true );

% Bandpass the template so it is properly normalized
bp_vals
temp_bp = BH_bandpass3d(size(template),bp_vals(1),0.3.*bp_vals(2),bp_vals(3),'GPU',pixelSizeFULL);
template = real(ifftn(fftn(gpuArray(template)).*temp_bp.^2));
clear temp_bp


% The template will be padded later, trim for now to minimum so excess
% iterations can be avoided.
fprintf('size of provided template %d %d %d\n',size(template));
trimTemp = BH_multi_padVal(size(template),ceil(2.0.*max(emc.('Ali_mRadius')./pixelSizeFULL)));
% template = BH_padZeros3d(template, trimTemp(1,:),trimTemp(2,:),'cpu','singleTaper');
% SAVE_IMG(MRCImage(template),'template_trimmed.mrc');
clear trimTemp
fprintf('size after trim to sqrt(2)*max(lattice radius) %d %d %d\n',size(template));

if isempty(mapPath) ; mapPath = '.' ; end
if isempty(tempPath) ; tempPath = '.' ; end
% Check to see if only tilt angles are supplied, implying a y-axis tilt scheme,
% or otherwise, assume a general geometry as in protomo.
% % % tiltGeometry = load(RAWTLT);
RAWTLT = sprintf('fixedStacks/ctf/%s_ali1_ctf.tlt',tomoName);
tiltGeometry = load(RAWTLT);
% subTomoMeta.('tiltGeometry').(mapName) = tiltGeometry;

% Make sure the template and is an even sized image
template = padarray(template, mod(size(template),2),0, 'post');
template = template - mean(template(:));


templateBIN = BH_reScale3d(gather(template),'',sprintf('%f',1/samplingRate),'cpu');

templateBIN = templateBIN - mean(templateBIN(:));
templateBIN = templateBIN  ./rms(templateBIN(:));

[templateMask] = (EMC_maskReference(gpuArray(templateBIN),pixelSize,{'fsc', true}));
templateMask = gather(templateMask);

% templateMask = gather(EMC_maskShape('sphere', size(templateBIN), [3,3,3].*2, 'gpu', {'shift', [0,0,0];'kernel',false}));



sizeTemp = size(template);
sizeTempBIN = size(templateBIN);




gpuDevice(useGPU);


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Initialize a whole mess of control variables and storage volumes. %
%Out of plane range inc (starts from 1.* inc)
rotConvention = 'Bah';



if (emc.use_new_grid_search)
  gridSearch = eulerSearch(emc.symmetry, angleSearch(1),...
    angleSearch(2),angleSearch(3),angleSearch(4), 0, 0, false);
  gridSearch.HelicalRestriction(emc.helical_search_theta_constraint);
  nAngles = sum(gridSearch.number_of_angles_at_each_theta);
  inPlaneSearch = gridSearch.parameter_map.psi;
else
  if (emc.helical_search_theta_constraint ~= 0)
    error('Helical search theta constraint not implemented for old grid search');
  end
  [  nInPlane, inPlaneSearch, angleStep, nAngles] ...
    = BH_multi_gridSearchAngles(angleSearch)
end


highThr=sqrt(2).*erfcinv(ceil(peakThreshold.*0.10).*2./(prod(size(tomogram)).*nAngles(1)))


[ OUTPUT ] = BH_multi_iterator( [targetSize; ...
                                size(tomogram);...
                                sizeTempBIN; ...
                                2.*latticeRadius], 'convolution' );



tomoPre   = OUTPUT(1,:);
tomoPost  = OUTPUT(2,:);
sizeChunk = OUTPUT(3,:);
validArea = OUTPUT(4,:);
validCalc = OUTPUT(5,:);
nIters    = OUTPUT(6,:);


%[ padVal ] = BH_multi_padVal( sizeTemp, sizeChunk );
%tempPre = padVal(1,:);
%tempPost = padVal(2,:);
[ padBIN ] = BH_multi_padVal( sizeTempBIN, sizeChunk );
[ trimValid ] = BH_multi_padVal(sizeChunk, validArea);


RMSFACTOR = sqrt(prod(sizeTempBIN) / prod(sizeChunk));




fprintf('\n-----\nProcessing in chunks\n\n');
fprintf('tomo prepadding  %d %d %d\n', tomoPre);
fprintf('tomo postpadding %d %d %d\n', tomoPost);
fprintf('size to process  %d %d %d\n', sizeChunk);
fprintf('valid Area       %d %d %d\n', validArea);
fprintf('valid Calc       %d %d %d\n', validCalc);
fprintf('# of iterations  %d %d %d\n', nIters);
fprintf('-----\n');

valid_ratio = prod(sizeChunk) ./ prod(validCalc);
size(tomogram)

% [ tomogram ] = BH_padZeros3d(tomogram, tomoPre, tomoPost, ...
%                                              'cpu', 'singleTaper',mean(tomogram(:)));
tomogram = padarray(tomogram,tomoPre,'symmetric','pre');
tomogram = padarray(tomogram,tomoPost,'symmetric','post');
sizeTomo = size(tomogram);


[ validCalcMask ] = BH_mask3d('rectangle',sizeChunk,validCalc./2,[0,0,0]);


[ vA ] = BH_multi_padVal( validArea, sizeChunk );
% This would need to be changed to take a mask size and not just a radius.
% Currently, this would not produce the correct results for odd size area
% % % fftMask = BH_fftShift(validArea,sizeChunk,0);

% Array for storing chunk results these could probably be half-precision
RESULTS_peak = zeros(sizeTomo, 'single');
RESULTS_angle= zeros(sizeTomo, 'single');

RESULTS_sum = [];
RESULTS_sum_sq = [];
if (measure_noise_variance)
  RESULTS_sum = zeros(sizeTomo, 'single');
  RESULTS_sum_sq = zeros(sizeTomo, 'single');
end



% % % % optimize fft incase a power of two is not used, this will make things run ok.
% % % opt = zeros(sizeChunk, precision,'gpuArray');
% % % fftw('planner','patient');
% % % fftn(opt);
% % % clear opt ans
[ bhF ] = fourierTransformer(randn(sizeChunk, 'single','gpuArray'));


sum_template = mean(templateBIN(:));
sum_templateMask = mean(templateMask(:));
sum_imgMask = prod(sizeChunk);% bhF.halfDimSize * sizeChunk(2) * sizeChunk(3);


% Temp while testing new dose weighting
TLT = tiltGeometry;
nPrjs = size(TLT,1);


kVal = 0;

% % [ OUTPUT ] = BH_multi_iterator( [sizeTempBIN;kVal.*[1,1,1]], 'extrapolate' );
[ OUTPUT ] = BH_multi_iterator( [sizeChunk;kVal.*[1,1,1]], 'extrapolate' );



tomoIDX = 1;
nTomograms = prod(nIters);


wanted_storage_precision = 'single';
if (test_half)
  wanted_storage_precision = 'uint16';
end

tomoStack = zeros([sizeChunk,nTomograms], wanted_storage_precision);
% tomoNonZero = zeros(nTomograms,6,'uint64');

% backgroundVol = zeros(sizeChunk,'single');
tomoCoords= zeros(nTomograms, 3, 'uint16');


try
  doMedFilt = emc.('Tmp_medianFilter');
  if ~ismember(doMedFilt,[3,5,7])
    error('Tmp_medianFilter can only be 3,5, or 7');
  else
    fprintf('Using median filter, size %d',doMedFilt);
  end
catch
  doMedFilt = 0;
end

calcStats = 0;
if calcStats
  maskStack = false([sizeChunk,nTomograms]);
  calcMask = 0;
else
  calcMask = 1;
end
firstStats = 1;
flgOOM = 0;

fullX = 0;
fullX2 = 0;
fullnX = 0;
oT  = ceil((validArea./2)+1)
for  iX = 1:nIters(1)
  cutX = 1 + (iX-1).*validArea(1);
  for iY = 1:nIters(2)
    cutY = 1 + (iY-1).*validArea(2);
    for iZ = 1:nIters(3)
      cutZ = 1 + (iZ-1).*validArea(3);
      
      fprintf('preprocessing tomo_chunk %d/%d col %d/%d row %d/%d plane idx%d\n' , ...
        iY,nIters(2),iX,nIters(1),iZ,nIters(3),tomoIDX)
      
      
      
      tomoChunk = gpuArray(tomogram(cutX:cutX+sizeChunk(1)-1,...
        cutY:cutY+sizeChunk(2)-1,...
        cutZ:cutZ+sizeChunk(3)-1));
      
      % Make a list of the padded regions of the tomogram to exclude from
      % statistical calculations
      
      tomoChunk = tomoChunk - mean(tomoChunk(:));
      tomoChunk = tomoChunk ./ rms(tomoChunk(:));
      
      %       tomoChunk = real(ifftn(fftn(tomoChunk).*tomoBandpass));
      
      tomoChunk = bhF.invFFT(bhF.fwdFFT(tomoChunk,0,0,[bp_vals, pixelSize]),2);
      
      
      if doMedFilt
        if ( flgOOM )
          tomoChunk = (medfilt3(tomoChunk,doMedFilt.*[1,1,1]));
        else
          tomoChunk = gpuArray(medfilt3(tomoChunk,doMedFilt.*[1,1,1]));
        end
      else
        if ( flgOOM )
          % Leave on CPU
        else
          tomoChunk = gpuArray(tomoChunk);
          statsRadius = gather(statsRadius);
        end
      end
      
      [ averageMask, flgOOM ] = BH_movingAverage_2(tomoChunk, statsRadius(1));
      rmsMask =  BH_movingAverage_2(tomoChunk.^2, statsRadius(1));
      rmsMask = sqrt(rmsMask - averageMask.^2);
      

      tomoChunk = (tomoChunk - averageMask) ./ rmsMask;
      clear rmsMask averageMask
      
      tomoChunk = gather(tomoChunk .*validCalcMask);
      
      tmp_sum = sum(tomoChunk(:));
      
      fullX = fullX + gather(tmp_sum);
      fullX2 = fullX2 + gather(tmp_sum.^2);
      fullnX = fullnX + gather(prod(sizeChunk));
      
      if (test_half)
        % The default is to return uint16 on the same device (host in this case)
        tomoStack(:,:,:,tomoIDX) = emc_halfcast(tomoChunk);
      else
        tomoStack(:,:,:,tomoIDX) = tomoChunk;
      end
      
      tomoCoords(tomoIDX,:) = [cutX,cutY,cutZ];
      tomoIDX = tomoIDX + 1;
      
    end % end of loop over Z chunks
  end % end of loop over Y chunks
end % end of loop over X chunks


% Normalize the global variance
globalVariance = (fullX2/fullnX) - (fullX/fullnX)^2;



clear tomoWedgeMask validCalcMask  bandpassFilter statBinary  tomoChunk

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

kVal = 0;




ANGLE_LIST = zeros(nAngles(1),3, 'single');
totalTime = 0;
firstLoopOverTomo = true;


if (emc.use_new_grid_search)
  theta_search = gridSearch.active_theta_positions;
else
  theta_search = 1:size(angleStep,1);
end


tomoIDX = 1;
firstLoopOverAngles = true;


  
% Avoid repeated allocations
tempPAD = zeros(size(templateBIN) + padBIN(1,:) + padBIN(2,:),'single','gpuArray');

use_only_once = false;
template_interpolator = '';
[template_interpolator, ~] = interpolator(gpuArray(templateBIN),[0,0,0],[0,0,0], 'Bah', 'forward', 'C1', use_only_once);

% templateMask_interpolator = '';
% [templateMask_interpolator, ~] = interpolator(gpuArray(templateMask),[0,0,0],[0,0,0], 'Bah', 'forward', 'C1', use_only_once);

for iTomo = 1:nTomograms
  currentGlobalAngle = 1;
  currentSearchPosition = 0;

  fprintf('Working on tomo chunk %d/%d from %s\n', iTomo, nTomograms, mapName);
  
  
  % Iterate over the tomogram pulling each chunk one at a time.
  % for iTomo = 1:nTomograms sqp loop
  tic;
  iCut =  tomoCoords(iTomo,:);
  % reset the angle count and value at the begining of loop
  % inside, while each new outer loop changes the start values.
  
  
  % Truth value to initialize temp results matrix each new tomo
  % chunk.
  firstLoopOverChunk = true;
    

    
  if (test_half)
    % Convert and return on GPU
    tomoFou = emc_halfcast(tomoStack(:,:,:,iTomo), true);
  else
    tomoFou = gpuArray(tomoStack(:,:,:,iTomo));
  end

  tomoFou = bhF.swapPhase(bhF.fwdFFT(bhF.normalization_factor^3.*(tomoFou)), 'fwd');

  for iAngle = theta_search


  
    if (emc.use_new_grid_search)
      theta = gridSearch.parameter_map.theta(iAngle);
    else
      theta = angleStep(iAngle,1);
      phiStep = angleStep(iAngle,3);
    end   
      
    if (emc.use_new_grid_search)
      phi_search = gridSearch.parameter_map.phi{iAngle};
    else
      phi_search = 0:angleStep(iAngle,2);
    end
    
    for iAzimuth = phi_search
      % currentSearchPosition = currentSearchPosition + 1;
      % fprintf('Working search position %d/%d for tomo chunk %d/%d from %s\n',currentSearchPosition, nAngles/length(inPlaneSearch), iTomo, nTomograms, mapName);

      if (emc.use_new_grid_search)
        phi = iAzimuth;
      else
        phi = phiStep * iAzimuth;
      end
      
      for iInPlane = inPlaneSearch
        
        psi = iInPlane;
        
        %calc references only on first chunk
        if (firstLoopOverAngles)
          ANGLE_LIST(currentGlobalAngle,:) = [phi, theta, psi - phi];
        end
        
        
        % rather than using padzeros
        tempPAD = tempPAD .* 0;
        tempPAD(padBIN(1,1)+1: end - padBIN(2,1), ...
          padBIN(1,2)+1: end - padBIN(2,2), ...
          padBIN(1,3)+1: end - padBIN(2,3)) = template_interpolator.interp3d(...
                                                                            [phi, theta, psi - phi],...
                                                                            [0,0,0],rotConvention,...
                                                                            'forward','C1');
        
                                              

        tempPAD = tempPAD - mean(tempPAD(:));
        
        
        ccfmap = BH_padZeros3d(real(single(...
          bhF.invFFT(tomoFou.* conj(bhF.fwdFFT(tempPAD))))),...%./(tomoNorm.*tempNorm))))),...
          trimValid(1,:),trimValid(2,:),'GPU','single');
        %
        
        ccfmap = ccfmap ./ std(ccfmap(:));
        
        
        % If first loop over tomo, initialize the storage volumes, if
        % first loop over the chunk but not over the tomo, pull storage
        % chunks from storage volume.
        if (firstLoopOverChunk)
          %store ccfmap as complex with phase = angle of reference
          magTmp = ccfmap;
          angTmp = ones(size(magTmp), 'single','gpuArray');

          if (measure_noise_variance)
            ccfmap(abs(ccfmap) > 3) = 0;
            sumTmp = ccfmap;
            sumSqTmp = ccfmap.^2;
          end
          
          firstLoopOverChunk = false;
        else
          % update higher values of ccfmap with new reference if applicable.
          replaceTmp = ( magTmp < ccfmap );
          
          magTmp(replaceTmp) = ccfmap(replaceTmp);
          angTmp(replaceTmp) = currentGlobalAngle;

          if (measure_noise_variance)
            ccfmap(abs(ccfmap) > 3) = 0;
            sumTmp = sumTmp + ccfmap;
            sumSqTmp = sumSqTmp + ccfmap.^2;
          end
          
          
          clear replaceTmp
        end % end if firstLoopOverChunk
        currentGlobalAngle = currentGlobalAngle + 1;

      end % end psi loop over in plane angles
    end % end phi loop over azimuth angles
  end % end theta loop over out of plane angles

  % FIXME this double cutting and temporary allocation is ridiculous.
  magStoreTmp =  RESULTS_peak(iCut(1):iCut(1)+sizeChunk(1)-1,...
    iCut(2):iCut(2)+sizeChunk(2)-1,...
    iCut(3):iCut(3)+sizeChunk(3)-1);
  angStoreTmp = RESULTS_angle(iCut(1):iCut(1)+sizeChunk(1)-1,...
    iCut(2):iCut(2)+sizeChunk(2)-1,...
    iCut(3):iCut(3)+sizeChunk(3)-1);
  
  
  magStoreTmp(vA(1,1) + 1:end - vA(2,1), ...
    vA(1,2) + 1:end - vA(2,2), ...
    vA(1,3) + 1:end - vA(2,3)) = gather(magTmp);
  angStoreTmp(vA(1,1) + 1:end - vA(2,1), ...
    vA(1,2) + 1:end - vA(2,2), ...
    vA(1,3) + 1:end - vA(2,3)) = gather(angTmp);
  
  
  RESULTS_peak(iCut(1):iCut(1)+sizeChunk(1)-1,...
    iCut(2):iCut(2)+sizeChunk(2)-1,...
    iCut(3):iCut(3)+sizeChunk(3)-1) = magStoreTmp;
  
  clear magStoreTmp
  
  RESULTS_angle(iCut(1):iCut(1)+sizeChunk(1)-1,...
    iCut(2):iCut(2)+sizeChunk(2)-1,...
    iCut(3):iCut(3)+sizeChunk(3)-1) = angStoreTmp;
  clear angStoreTmp

  if (measure_noise_variance)
    sumStoreTmp =  RESULTS_sum(iCut(1):iCut(1)+sizeChunk(1)-1,...
      iCut(2):iCut(2)+sizeChunk(2)-1,...
      iCut(3):iCut(3)+sizeChunk(3)-1);
    sumSqStoreTmp = RESULTS_sum_sq(iCut(1):iCut(1)+sizeChunk(1)-1,...
      iCut(2):iCut(2)+sizeChunk(2)-1,...
      iCut(3):iCut(3)+sizeChunk(3)-1);
    
    
    sumStoreTmp(vA(1,1) + 1:end - vA(2,1), ...
      vA(1,2) + 1:end - vA(2,2), ...
      vA(1,3) + 1:end - vA(2,3)) = gather(sumTmp);
    sumSqStoreTmp(vA(1,1) + 1:end - vA(2,1), ...
      vA(1,2) + 1:end - vA(2,2), ...
      vA(1,3) + 1:end - vA(2,3)) = gather(sumSqTmp);
    
    
    RESULTS_sum(iCut(1):iCut(1)+sizeChunk(1)-1,...
      iCut(2):iCut(2)+sizeChunk(2)-1,...
      iCut(3):iCut(3)+sizeChunk(3)-1) = sumStoreTmp;
    
    clear sumStoreTmp
    
    RESULTS_sum_sq(iCut(1):iCut(1)+sizeChunk(1)-1,...
      iCut(2):iCut(2)+sizeChunk(2)-1,...
      iCut(3):iCut(3)+sizeChunk(3)-1) = sumSqStoreTmp;
    clear sumSqStoreTmp
    
    firstLoopOverAngles = false;
  end  
end
%save('angle_list.txt','angle_list','-ascii');
clear tomoStack
% Cut out the post padding used to iterate over the tomogram
RESULTS_peak = RESULTS_peak(1+tomoPre(1):end-tomoPost(1),...
  1+tomoPre(2):end-tomoPost(2),...
  1+tomoPre(3):end-tomoPost(3));
%RESULTS_peak(RESULTS_peak < 0) = 0;
RESULTS_angle = RESULTS_angle(1+tomoPre(1):end-tomoPost(1),...
  1+tomoPre(2):end-tomoPost(2),...
  1+tomoPre(3):end-tomoPost(3));

if (measure_noise_variance)
  RESULTS_sum = RESULTS_sum(1+tomoPre(1):end-tomoPost(1),...
    1+tomoPre(2):end-tomoPost(2),...
    1+tomoPre(3):end-tomoPost(3));
  RESULTS_sum_sq = RESULTS_sum_sq(1+tomoPre(1):end-tomoPost(1),...
    1+tomoPre(2):end-tomoPost(2),...
    1+tomoPre(3):end-tomoPost(3));
end




gpuDevice(useGPU);
clear bhF


% scale the magnitude of the results to be 0 : 1
szK = latticeRadius;%floor(0.8.*szM);
rmDim = max(max(eraseMaskRadius),max(szK)).*[1,1,1]+7;
mag = RESULTS_peak; clear RESULTS_peak
% Normalize so the difference if using a decoy makes sense. The input decoy
% should have the same power, so I'm not sure why this is needed, but it is
% an easy fix and a problem for future Ben to figure out.
% mag = mag ./ std(mag(:));

system(sprintf('mkdir -p %s',convTMPNAME));
system(sprintf('mv temp_%s.mrc %s',convTMPNAME,convTMPNAME));

resultsOUT = sprintf('./%s/%s_convmap.mrc',convTMPNAME,mapName);
anglesOUT  = sprintf('./%s/%s_angles.mrc',convTMPNAME,mapName);
angleListOUT = sprintf('./%s/%s_angles.list',convTMPNAME,mapName);
SAVE_IMG(mag,{resultsOUT,'half'});
noiseVarOUT = sprintf('./%s/%s_noise_variance.mrc',convTMPNAME,mapName);

if (measure_noise_variance)
  n_angles_searched = sum(any(ANGLE_LIST,2));
  noiseVar = (RESULTS_sum_sq./n_angles_searched - (RESULTS_sum./n_angles_searched).^2);
  noiseVar(noiseVar == 0) = 1;

  SAVE_IMG(noiseVar,{noiseVarOUT,'half'});
end
% SAVE_IMG(MRCImage(RESULTS_angle),anglesOUT);

angleFILE = fopen(angleListOUT,'w');
fprintf(angleFILE,'%2.2f\t%2.2f\t%2.2f\n', ANGLE_LIST');
fclose(angleFILE);


% mag =  mag - min(mag(:)); mag = mag ./ max(mag(:));

% Zero out one lattice width from the edges to reduce edge effect (but cutting
% out and padding back in.) Also pad by size of removal mask (subtract this from
% coordinates)
mag = mag(szK(1)+1:end - szK(1), ...
  szK(2)+1:end - szK(2), ...
  szK(3)+1:end - szK(3));
mag = BH_padZeros3d(mag,szK+rmDim,szK+rmDim, 'cpu', 'single');
%dev.FreeMemory;
%%%Ang = angle(RESULTS_peak); %clear Results
% negative phase angles mapped back to 0-->pi
%Ang(sign(Ang) < 0) = Ang(sign(Ang)<0) + pi; serotonin_ali1_75_1.mod
%Ang = BH_padZeros3d(round(Ang./angleIncrement),szK,szK,'cpu','single');
Ang = BH_padZeros3d(RESULTS_angle,rmDim,rmDim,'cpu','single');


%mag =  mag - min(mag(:)); mag = mag ./ max(mag(:));

Tmean = mean(mag(( mag ~= 0 )));
Tstd  = std(mag(( mag~=0 )));
threshold = Tmean + peakThreshold*Tstd;
mag((Ang < 0)) = 0;

mag = gpuArray(mag);
sizeTomo = size(mag);


[MAX, coord] = max(mag(:));

peakMat = zeros(peakThreshold,10*emc.nPeaks);

n = 1;

fprintf('rmDim %f szK %f\n',  rmDim,szK);
removalMask = BH_mask3d(eraseMaskType,[2,2,2].*rmDim+1,eraseMaskRadius,[0,0,0]);
rmInt = interpolator(gpuArray(removalMask),[0,0,0],[0,0,0],rotConvention ,'forward','C1');
symOps = interpolator(gpuArray(removalMask),[0,0,0],[0,0,0],rotConvention ,'forward',emc.symmetry);

maskCutOff = 0.98;
nIncluded = gather(sum(sum(sum(removalMask > maskCutOff))));
nTries = 0;
if strcmpi(eraseMaskType,'rectangle')
  areaPreFactor = 0;
else
  areaPreFactor = (4/3*pi);
end

while nIncluded < areaPreFactor*prod(eraseMaskRadius)
  maskCutOff = 0.99*maskCutOff;
  nIncluded = gather(sum(sum(sum(removalMask > maskCutOff))));
  nTries = nTries + 1;
  if (nTries > 1000)
    error('Did not find an appropriate erase mask');
  end
  
end

if ignore_threshold
  highThr = 0;
end

this_try = 0;
if (ignore_threshold)
  search_limit = peakThreshold
else
  search_limit = 2 .* peakThreshold
end

while n <= search_limit && (this_try < max_tries) && MAX > highThr
  this_try = this_try + 1;
  
  %
  % Some indicies come back as an error, even when they seem like the
  % should be fine. I'm not sure why, and I should think about this
  % more, but for now, just set that one index to zero (instead of a
  % whole box) and move on with life. It looks like the index that is
  % kicking out the error is equal to -1*numberofreferences, which
  % might be an issue because that corresonds to the positive upper
  % limit of the reference index. Ignoring it still seems to be okay
  % but it bothers me not to know.
  
  
  [i,j,k] = ind2sub(sizeTomo,coord);
  try
    c = gather([i,j,k]);
  catch
    fprint('Ran into some trouble gathering the i,j,k. Breaking out\n');
    break
  end
  
  if Ang(gather(coord)) > 0
    
    % box for removal and center of mass calc, use a larger box if multiple
    % peaks are being saved.
    bDist = 1+round(log(emc.nPeaks));
    clI  = c(1) - bDist;
    chI  = c(1) + bDist;
    clJ  = c(2) - bDist;
    chJ  = c(2) + bDist;
    clK  = c(3) - bDist;
    chK  = c(3) + bDist;
    
    magBox = mag(clI:chI,clJ:chJ,clK:chK);
    
    angBox = Ang(clI:chI,clJ:chJ,clK:chK);
    
    [cmX, cmY, cmZ] = ndgrid(-1*bDist:1*bDist, ...
      -1*bDist:1*bDist, ...
      -1*bDist:1*bDist );
    
    cMass = [ sum(sum(sum(magBox.*cmX))) ; ...
      sum(sum(sum(magBox.*cmY))) ; ...
      sum(sum(sum(magBox.*cmZ))) ] ./ sum(magBox(:));
    
    
    % Switching from centered to lower left coordinates and subtracting the
    % padding
    
    cenP = c + cMass' - rmDim;
    
    
    
    % % %     % If the most frequent peak is unique use it;
    % % %     [peakM, ~, peakC] = mode(angBox(:));
    % % %     if length(peakC) == 1 && peakM
    % % %       % Need to ensure the mode is none zero which is possible.
    % % %       peakMat(n,4:6) = ANGLE_LIST(peakM,:);
    % % %       topPeak = peakM;
    % % %     else
    % Otherwise use the value at the max for the peak val;
    peakMat(n,4:6) = ANGLE_LIST(Ang(coord),:);
    topPeak = Ang(coord);
    % % %     end
    peakMat(n,1:3) = gather(samplingRate.*cenP);
    peakMat(n,10) = gather(MAX);
    
    iSNR = 0;
    if emc.nPeaks > 1
      possible_angles = gather(magBox);
      possible_angles(angBox == topPeak) = 0;
      nRandom = 2;
      for iPeak = 2:emc.nPeaks
        
        useRandom = false;
        
        if any(possible_angles ~= 0)
          [~, cAng] = max(possible_angles(:));
          topPeak = angBox(cAng);
          iSNR = gather(mean( possible_angles(angBox == topPeak)));
          possible_angles(angBox == topPeak) = 0;
          Ang(cAng)
          if topPeak <= 0 || Ang(cAng) <= 0
            useRandom = true;
            % If random set the SNR as a fraction of the mean of the
            % previous peaks
            iSNR = mean( peakMat(n,10:10:10*(iPeak-1)) ) .* 0.75;
          else
            iAngles =  ANGLE_LIST(Ang(cAng),:);
          end
        else
          useRandom = true;
        end
        
        if useRandom
          % If we've used up all the possible peaks, just insert a random
          % Incrementally far from the original
          iAngles = [ randn(1) .* (nRandom.^2) + peakMat(n,1), ...
            randn(1) .* (nRandom.^2) + peakMat(n,2), ...
            randn(1) .* (nRandom.^2) + peakMat(n,3)];
          if nRandom < 10
            nRandom = nRandom + 1;
          end
        end
        peakMat(n,[1:3]+10*(iPeak-1)) = gather(samplingRate.*cenP);
        peakMat(n,[4:6]+10*(iPeak-1)) = iAngles;
        peakMat(n,10+10*(iPeak-1)) = iSNR;
        % % %          oldPeaks = ( angBox == peakM | oldPeaks );
        
      end
      
    end
    
    
    
    %     rmMask = BH_resample3d(removalMask,peakMat(n,4:6),[0,0,0],rotConvention ,'GPU','forward');
    rmMask = rmInt.interp3d(gather(peakMat(n,4:6)),[0,0,0],rotConvention,'forward','C1');
    
    % Invert after resampling so that zeros introduced by not extrapolating
    % the corners are swapped to ones, i.e. not removed.
    %     rmMask = (1-rmMask);
    
    mag(c(1)-rmDim:c(1)+rmDim,...
      c(2)-rmDim:c(2)+rmDim,...
      c(3)-rmDim:c(3)+rmDim) = ...
      mag(c(1)-rmDim:c(1)+rmDim,...
      c(2)-rmDim:c(2)+rmDim,...
      c(3)-rmDim:c(3)+rmDim) .* (rmMask< maskCutOff);
    
    % % %     peakMat(n,10) = (gather(MAX) - Tmean)./Tstd; % record stds above mean
    n = n + 1;
    
    if ~mod(n,100)
      n
    end
    
  else
    Ang(gather(coord));
    mag(coord) = 0;
  end
  
  
  [MAX, coord] = max(mag(:));
  
end

peakMat = peakMat( ( peakMat(:,1)>0 ),:);

%save('peakMat_post.mat', 'peakMat');

% A temp test, not the correct output just score x y z dx dy dz e1 e2 e3

csv_out = sprintf('./%s/%s.csv',convTMPNAME,mapName);
pos_out = sprintf('./%s/%s.pos',convTMPNAME,mapName);
%fieldOUT = zeros(length(peakMat(:,1)),26);
fileID = fopen(csv_out,'w');
fileID2 = fopen(pos_out,'w');
errID  = fopen(sprintf('./%s/%s.errID',convTMPNAME,mapName));


n=1;
nSym=1;
for i = 1:length(peakMat(:,1))
  if all(peakMat(i,1:3))
    
    iSym = mod(nSym,symOps.nSymMats)+1;
    % Generate a uniform distribution over the in-plane
    % randomizations
    
    r = reshape(BH_defineMatrix(peakMat(i,4:6), rotConvention , 'inv') * symOps.symmetry_matrices{iSym},1,9);
    nSym = nSym + 1;
    fprintf(fileID,['%1.2f %d %d %d %d %d %d %d %d %d %f %f %f %d %d %d ',...
      '%f %f %f %f %f %f %f %f %f %d '],peakMat(i,10),samplingRate,0, ...
      i+nPreviousSubTomos,1,1,1,1,1,0,peakMat(i,1:3), ...
      peakMat(i,4:6),r,1);
    
    if emc.nPeaks > 1
      for iPeak = 2:emc.nPeaks
        
        iSym = mod(nSym,symOps.nSymMats)+1;
        r = reshape(BH_defineMatrix(peakMat(i,[4:6]+10*(iPeak-1)), rotConvention , 'inv') * symOps.symmetry_matrices{iSym},1,9);
        nSym = nSym + 1;
        fprintf(fileID,['%1.2f %d %d %d %d %d %d %d %d %d %f %f %f %d %d %d ',...
          '%f %f %f %f %f %f %f %f %f %d '],peakMat(i,10),samplingRate,0, ...
          i+nPreviousSubTomos,1,1,1,1,1,0,peakMat(i,[1:3]+10*(iPeak-1)), ...
          peakMat(i,[4:6]+10*(iPeak-1)),r,1);
        
        
      end
    end
    
    fprintf(fileID,'\n');
    fprintf(fileID2,'%f %f %f\n',peakMat(i,1:3)./samplingRate);
    
    
    n = n + 1;
  end
end

%lastIndex = find(fieldOUT(:,4),1,'last');

fclose(fileID);
fclose(fileID2);



system(sprintf('point2model -number 1 -sphere 3 -scat ./%s/%s.pos ./%s/%s.mod', convTMPNAME,mapName,convTMPNAME, mapName));

fileID = fopen(sprintf('./%s/%s.path',convTMPNAME,mapName),'w');
fprintf(fileID,'%s,%s,%s,%s',mapName,mapPath,mapExt,RAWTLT);
fclose(fileID);


fprintf('Total execution time : %f seconds\n', seconds(datetime("now")-startTime));



end % end of templateSearch3d function

