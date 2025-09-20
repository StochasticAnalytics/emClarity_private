function [ emc ] = BH_parseParameterFile( PARAMETER_FILE )
%Parse a parameter file & check for valid parameters.
%   experimental

fileID = fopen(PARAMETER_FILE,'r');

p = textscan(fileID, '%s', 'CommentStyle',{'%'},'Delimiter','\n', ...
  'TreatAsEmpty',{' '});

nParam = 1;
p2 = cell(1,1);
% Get rid of empty lines
for i = 1:size(p{1},1)
  if ~isempty(p{1}{i})
    p2{nParam,1} = p{1}{i};
    nParam = nParam + 1;
  end
end
clear p

emc = struct();
last_parsed_parameter = 'none';
% Check that all paramters are name: value pairs
stringValues = {'subTomoMeta'; ...
  'Ali_mType';'Cls_mType';'Cls_mType';'Raw_mType';'Fsc_mType'; ...
  'Pca_distMeasure';'Kms_mType';'flgPrecision';'Tmp_xcfScale';...
  'fastScratchDisk';'Tmp_eraseMaskType';'startingDirection';'Peak_mType';'symmetry'; ...
  'gmm_covariance_type';'distance_metric';'alt_cache';'metadata_format'};
for i = 1:size(p2,1)
  pNameVal = strsplit(p2{i,1},'=');
  if length(pNameVal) == 1
    fprintf("Last successfully parsed parameter: %s\n", string(last_parsed_parameter));
    error('Could not split Name=Value pair for\n\t %s',char(pNameVal))
  elseif length(pNameVal) > 2
    fprintf("Last successfully parsed parameter: %s\n", string(last_parsed_parameter));
    error('To many colons in\n\t %s',char(pNameVal))
  else   

    if any(strcmpi(stringValues, pNameVal{1}))
      emc.(pNameVal{1}) = pNameVal{2};
    else
      emc.(pNameVal{1}) = EMC_str2double(pNameVal{2});
    end
  
    last_parsed_parameter = pNameVal{1};
  end
end



%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Asserts on required parameters
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

if isfield(emc, 'fastScratchDisk')
  if strcmpi(emc.fastScratchDisk, 'ram')
    if isempty(getenv('EMC_CACHE_MEM'))
      fprintf('Did not find a variable for EMC_CACHE_MEM\nSkipping ram\n');
      emc.fastScratchDisk = '';
    else
      % I have no ideah how much is needed
      if EMC_str2double(getenv('EMC_CACHE_MEM')) < 32
        fprintf('There is only 64 Gb of cache on ramdisk, not using\n');
        emc.fastScratchDisk = '';
      else
        emc.fastScratchDisk=getenv('MCR_CACHE_ROOT');
      end
    end % if EMC_CACHE_MEM
  end % if ram
else
  emc.fastScratchDisk = '';
end

if isfield(emc, 'nGPUs')
  EMC_assert_numeric(emc.nGPUs, 1, [1, 1000]);
else
  error('nGPUs is a required parameter');
end

if isfield(emc, 'nCpuCores')
  EMC_assert_numeric(emc.nCpuCores, 1, [1, 1000]);
else
  error('nCpuCores is a required parameter');
end

symmetry_has_been_checked = false;
if ~isfield(emc, 'symmetry')
  %TODO asserts on allowed values for symmetry paraemeter
  error('You must now specify a symmetry=X parameter, where symmetry E (C1,C2..CX,O,I)');
end
symmetry_has_been_checked = true;

if isfield(emc, 'PIXEL_SIZE')
  EMC_assert_numeric(emc.PIXEL_SIZE, 1, [0, 100e-10]);
  emc.pixel_size_si = emc.PIXEL_SIZE;
  emc.pixel_size_angstroms = emc.PIXEL_SIZE.*10^10;
else
  error('PIXEL_SIZE is a required parameter');
end

if isfield(emc, 'Cs')
  EMC_assert_numeric(emc.Cs, 1, [0, 10e-3]);
else
  error('Cs is a required parameter');
end

if isfield(emc, 'VOLTAGE')
  EMC_assert_numeric(emc.VOLTAGE, 1, [20e3, 1000e3]);
else
  error('VOLTAGE is a required parameter');
end

if isfield(emc, 'AMPCONT')
  EMC_assert_numeric(emc.AMPCONT, 1, [0.0, 1.0]);
  if emc.Cs == 0
    emc.Cs = 1e-10;
  end
  
else
  error('AMPCONT is a required parameter');
end




%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Now check for optional parameters
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Early development parameter, used to store more than one orientation during template matching
% and use for further refinement.
if isfield(emc, 'nPeaks')
    EMC_assert_numeric(emc.nPeaks, 1);
else
  emc.('nPeaks') = 1;
end

% Used when cutting out subtomos for further processing. Adds extra padding to anticipate shifts etc.
% This has not been well tested

% When used in average3d, this value is stored in the subTomoMeta.
if isfield(emc, 'CUTPADDING')
  EMC_assert_numeric(emc.CUTPADDING, 1);
else
  emc.('CUTPADDING') = 20;
end

if isfield(emc, 'whitenPS')
  EMC_assert_numeric(emc.whitenPS, 3)
  emc.('wiener_constant') = emc.whitenPS(3);
else
  emc.('whitenPS') = [0.0,0.0,0.0];
  emc.('wiener_constant') = 0.0;
end

% Default bfactor applied to the re-weighting when generating the fully corrected volumes.
% positive corresponds to a sharpening, negative to a low-pass.
if isfield(emc, 'Fsc_bfactor')
  EMC_assert_numeric(emc.Fsc_bfactor)
else
  emc.('Fsc_bfactor') = 40.0;
end

if isfield(emc, 'flgCones')
  EMC_assert_boolean(emc.flgCones)
else
  emc.('Fsc_bfactor') = false;
end


% Used to downweight higher frequencies based on relative CCC scores.
% Based on one of Niko's papers, but catching some edge cases for tomo.
% Overwritten if cycle == 0 as the scores from template matching do not work for this metric as they are SNR not CCC.
% TODO: get rid of the flg prefix
if isfield(emc, 'flgQualityWeight')
  EMC_assert_numeric(emc.flgQualityWeight, 1)
else
  emc.('flgQualityWeight') = 5.0;
end

% Experimental downweighting of higher frequency info farther from focus.
% Could also consider filtering pre reconstruction
% Filtering by defocus using exp[-(%d*(argmax(def-1,0,5).*q)^%d)]\n',flgFilterDefocus);
if isfield(emc,'filterDefocus')
  EMC_assert_numeric(emc.filterDefocus, 2)
else
  emc.filterDefocus = [0.0, 0.0];
end

if isfield(emc, 'refine_defocus_cisTEM')
  EMC_assert_boolean(emc.refine_defocus_cisTEM)
else
  emc.refine_defocus_cisTEM = false;
end
if isfield(emc, 'rerun_refinement_cisTEM')
  EMC_assert_boolean(emc.rerun_refinement_cisTEM)
else
  emc.rerun_refinement_cisTEM = false;
end

if isfield(emc,'flgCutOutVolumes')
  EMC_assert_boolean(emc.flgCutOutVolumes)
else
  emc.flgCutOutVolumes = false;
end


if isfield(emc,'track_stats')
  EMC_assert_boolean(emc.track_stats)
else
  emc.track_stats = false;
end

% alt_cache: optional list of writable cache directories
if ~isfield(emc, 'alt_cache')
  emc.alt_cache = {};
else
  t = strsplit(emc.alt_cache, ',');
  % Clear and we'll repopulate as a cell
  emc.alt_cache = cell(length(t),1);
  for i = 1:length(t)
    if ~(isfolder(t{i}))
      error('alt_cache directory does not exist: %s', t{i});
    else
      emc.alt_cache{i} = t{i};
    end
  end
end

% metadata_format: storage format for subTomoMeta (legacy, partitioned, or development)
if ~isfield(emc, 'metadata_format')
  emc.metadata_format = 'legacy';  % Default to legacy format
else
  % Validate the format
  valid_formats = {'legacy', 'partitioned', 'development'};
  if ~ismember(lower(emc.metadata_format), valid_formats)
    error('Invalid metadata_format: %s. Must be legacy, partitioned, or development', emc.metadata_format);
  end
  emc.metadata_format = lower(emc.metadata_format);
end


% Helix or filament with axis on Z, this will restrain the search angles to be +/- this many degrees from the X/y plane.
% A full search should still be specified
% Only affects templateSearch
if isfield(emc,'helical_search_theta_constraint')
  EMC_assert_numeric(emc.helical_search_theta_constraint, 1)
else
 emc.helical_search_theta_constraint = 0;
end

if isfield(emc,'eucentric_fit')
  EMC_assert_boolean(emc.eucentric_fit)
else
  emc.eucentric_fit = false;
end

if isfield(emc,'eucentric_minTilt')
  EMC_assert_numeric(emc.eucentric_maxTilt)
else
  emc.eucentric_maxTilt = 50.0;
end


% TODO: these should maybe be two different orthogonal parameters
  % if > 1 keep this many subtomos
  % if < 1 keep this fraction
emc = EMC_assert_deprecated_substitution(emc, 'ccc_cutoff', 'flgCCCcutoff');
if isfield(emc, 'ccc_cutoff')
  EMC_assert_numeric(emc.ccc_cutoff, 1)
else
  emc.('ccc_cutoff') = 0.0;
end

% TOOD: DOC
emc = EMC_assert_deprecated_substitution(emc, 'projectVolumes', 'flgProjectVolumes');
if isfield(emc, 'projectVolumes')
  EMC_assert_boolean(emc.projectVolumes);
else
  emc.('projectVolumes') = false;
end

% Whether the cycle is expected to be used for classification or alignment.
% Eventually, the distinction should not matter.
emc = EMC_assert_deprecated_substitution(emc, 'classification', 'flgClassify');
if isfield(emc, 'classification')
  EMC_assert_boolean(emc.classification);
else
  emc.('classification') = false;
end


emc = EMC_assert_deprecated_substitution(emc, 'multi_reference_alignment', 'flgMultiRefAlignment');
if isfield(emc, 'multi_reference_alignment')
  EMC_assert_numeric(emc.multi_reference_alignment, 1, [0, 2]);
else
  emc.('multi_reference_alignment') = 0;
end

% Zero padding of the volumes before alignment/other FFT ops
emc = EMC_assert_deprecated_substitution(emc, 'scale_calc_size', 'scaleCalcSize');
if isfield(emc, 'scale_calc_size')
  EMC_assert_numeric(emc.scale_calc_size, 1, [1.0, 2.0]);
else
  emc.('scale_calc_size') = 1.5;
end

emc = EMC_assert_deprecated_substitution(emc, 'limit_to_one_core', 'flgLimitToOneProcess');
if isfield(emc, 'limit_to_one_core')
  EMC_assert_boolean(emc.limit_to_one_core);
else
  emc.('limit_to_one_core') = false;
end

if (emc.limit_to_one_core)
  emc.nCpuCores = 1;
end

if isfield(emc, 'force_no_symmetry')
  EMC_assert_boolean(emc.force_no_symmetry)
  if (~symmetry_has_been_checked)
    error('force_no_symmetry must be after symmetry check');
  end
  % Warning must be after symmetry check
  if (emc.force_no_symmetry)
    emc.symmetry='C1';
  end
else
  emc.force_no_symmetry = true;
end

if isfield(emc, 'Pca_constrain_symmetry')
  EMC_assert_boolean(emc.Pca_constrain_symmetry)
else
  emc.Pca_constrain_symmetry = false;
end

emc = EMC_assert_deprecated_substitution(emc, 'fsc_with_chimera', 'fscWithChimera');
if isfield(emc, 'fsc_with_chimera')
  EMC_assert_boolean(emc.fsc_with_chimera);
else
  emc.fsc_with_chimera = false;
end

emc = EMC_assert_deprecated_substitution(emc, 'minimum_particle_for_fsc_weighting', 'minimumparticleVolume');
if isfield(emc, 'minimum_particle_for_fsc_weighting')
  EMC_assert_numeric(emc.minimum_particle_for_fsc_weighting, 1, [0.01, 1.0]);
else
  emc.('minimum_particle_for_fsc_weighting') = 0.1;
end

emc = EMC_assert_deprecated_substitution(emc, 'fsc_shape_mask', 'flgFscShapeMask');
if isfield(emc, 'fsc_shape_mask')
  EMC_assert_numeric(emc.fsc_shape_mask, 1, [0.0, 2.0]);
else
  emc.fsc_shape_mask = 1.0;
end

if isfield(emc, 'shape_mask_lowpass')
  EMC_assert_numeric(emc.shape_mask_lowpass, 1, [10, 100]);
else
  emc.shape_mask_lowpass = 14;
end

if isfield(emc, 'shape_mask_threshold')
  EMC_assert_numeric(emc.shape_mask_threshold, 1, [0.1, 10.0]);
else
  emc.shape_mask_threshold = 2.4;
end

if isfield(emc, 'shape_mask_test')
  EMC_assert_boolean(emc.shape_mask_test);
else
  emc.shape_mask_test = false;
end

emc = EMC_assert_deprecated_substitution(emc, 'pca_scale_spaces', 'pcaScaleSpace');
if isfield(emc, 'pca_scale_spaces')
  EMC_assert_numeric(emc.pca_scale_spaces);
else
  emc.pca_scale_spaces = 22.0;
end
emc.('n_scale_spaces') = numel(emc.pca_scale_spaces);

if isfield(emc, 'Pca_maxEigs')
  EMC_assert_numeric(emc.Pca_maxEigs, 1, [1, 1000]);
else
  emc.Pca_maxEigs = 36;
end

if isfield(emc, 'Pca_randSubset')
  EMC_assert_numeric(emc.Pca_randSubset, 1);
else
  emc.Pca_randSubset = 0;
end

if ~isfield(emc, 'Pca_clusters');
  error('Pca_clusters is a required parameter');
end

% Allowed values are validated inside BH_clusterPub.m
emc = EMC_assert_deprecated_substitution(emc, 'distance_metric', 'Pca_distMeasure');
if isfield(emc, 'distance_metric')
  EMC_assert_string_value(emc.distance_metric, {'sqeuclidean', 'cosine', 'gaussian','ward','neural'}, false);
else
  emc.distance_metric = 'sqeuclidean';
end

emc = EMC_assert_deprecated_substitution(emc, 'n_replicates', 'Pca_nReplicates');
if isfield(emc, 'n_replicates')
  EMC_assert_numeric(emc.n_replicates, 1, [1, 1000]);
else
  emc.n_replicates = 64;
end

if isfield(emc, 'Pca_refineKmeans')
  EMC_assert_boolean(emc.Pca_refineKmeans);
else
  emc.Pca_refineKmeans = false;
end

if isfield(emc, 'Pca_flattenEigs')
  EMC_assert_boolean(emc.Pca_flattenEigs);
else
  emc.Pca_flattenEigs = true;
end

if isfield(emc, 'Pca_use_real_space_conv')
  EMC_assert_boolean(emc.Pca_use_real_space_conv);
else
  emc.Pca_use_real_space_conv = false;
end

if isfield(emc, 'Pca_som_coverSteps')
  EMC_assert_numeric(emc.Pca_som_coverSteps, 1, [1, 1000]);
else
  emc.Pca_som_coverSteps = 100;
end

if isfield(emc, 'Pca_som_initNeighbor')
  EMC_assert_numeric(emc.Pca_som_initNeighbor, 1, [1, 32]);
else
  emc.Pca_som_initNeighbor = 3;
end

if ~isfield(emc, 'Pca_som_topologyFcn')
  % TODO: assert on allowed values
  emc.Pca_som_topologyFcn = 'hextop';
end


% specifying shared diagonal will approximate K-means
if isfield(emc, 'gmm_covariance_type')
  EMC_assert_string_value(emc.gmm_covariance_type, {'full', 'diagonal'},false);
else
  emc.gmm_covariance_type = 'full';
end

if isfield(emc, 'gmm_covariance_shared_between_clusters')
  EMC_assert_boolean(emc.gmm_covariance_shared_between_clusters);
else
  emc.gmm_covariance_shared_between_clusters = false;
end

if isfield(emc, 'gmm_regularize_value')
  EMC_assert_numeric(emc.gmm_regularize_value, 1, [0.0, 1.0]);
else
  emc.gmm_regularize_value = 0.01;
end

if isfield(emc, 'spike_prior')
  EMC_assert_boolean(emc.spike_prior);
else
  emc.spike_prior = false;
end


emc = EMC_assert_deprecated_substitution(emc, 'update_class_by_ccc', 'updateClassByBestReferenceScore');
if isfield(emc, 'update_class_by_ccc')
  EMC_assert_boolean(emc.update_class_by_ccc);
else
  emc.('update_class_by_ccc') = true;
end

if (~emc.multi_reference_alignment)
  % update by ccc only makes sense for multi reference alignment
  emc.update_class_by_ccc = false;
end

emc = EMC_assert_deprecated_substitution(emc, 'move_reference_by_com', 'flgCenterRefCOM');
if isfield(emc, 'move_reference_by_com')
  EMC_assert_boolean(emc.move_reference_by_com);
else
  emc.('move_reference_by_com') = true;
end

if isfield(emc, 'use_new_grid_search')
  EMC_assert_boolean(emc.use_new_grid_search);
else
  emc.use_new_grid_search = true;
end


%%%%%%%%%%%%%%%%%%%%%%%%%% tomoCPR params, mostly experimental

emc = EMC_assert_deprecated_substitution(emc, 'save_mapback_classes', 'flgColorMap');
if isfield(emc, 'save_mapback_classes')
  EMC_assert_boolean(emc.save_mapback_classes);
else
  emc.('save_mapback_classes') = false;
end

if isfield(emc, 'only_use_reference_classes')
  EMC_assert_boolean(emc.only_use_reference_classes);
else
  emc.only_use_reference_classes = false;
end

% These seemed to be necessary at some point to translate between IMOD and emClarity 
% coordinate systems, but the should probably be looked at again. TODO:
if isfield(emc, 'flgPreShift')
  EMC_assert_numeric(emc.flgPreShift, 3);
else
  emc.flgPreShift = [-0.5,-0.5,0.5];
end


% These seemed to be necessary at some point to translate between IMOD and emClarity 
% coordinate systems, but the should probably be looked at again. TODO:
if isfield(emc, 'flgPostShift')
  EMC_assert_numeric(emc.flgPostShift, 2);
else
  emc.flgPostShift = 1.*[1.0,-1.0];
end

if isfield(emc, 'prjVectorShift')
  EMC_assert_numeric(emc.prjVectorShift, 3);
else
  emc.prjVectorShift = [0.5,0.5,1.5];
end

if isfield(emc,'pixelShift')
  EMC_assert_numeric(emc.pixelShift, 1);
else
  emc.pixelShift = 0;
end

if isfield(emc, 'pixelMultiplier')
  EMC_assert_numeric(emc.pixelMultiplier, 1);
else
  emc.pixelMultiplier = -1;
end

if isfield(emc, 'tomoCprLowPass')
  EMC_assert_numeric(emc.tomoCprLowPass, 1);
  if (emc.tomoCprLowPass < 20 || emc.tomoCprLowPass > 44)
    fprintf('\n\n\tWARNING: tomoCprLowPass is outside the range of 20 to 44, this may be okay, but ... maybe not.\n\n');
  end
else
  emc.tomoCprLowPass = 22;
end

if isfield(emc, 'tomoCPR_random_subset')
  EMC_assert_numeric(emc.tomoCPR_random_subset, 1);
else
  emc.tomoCPR_random_subset = -1;
end

if isfield(emc, 'tomoCPR_n_particles_minimum')
  EMC_assert_numeric(emc.tomoCPR_n_particles_minimum, 1, [1, 100000]);
else
  emc.tomoCPR_n_particles_minimum = 10;
end

if isfield(emc, 'tomoCPR_target_n_patches_x_y')
  EMC_assert_numeric(emc.tomoCPR_target_n_patches_x_y, 2, [0, 100]);
else
  emc.tomoCPR_target_n_patches_x_y = [2,2];
end
% I think this has been removed
if isfield(emc, 'probabilityPeakiness')
  EMC_assert_numeric(emc.probabilityPeakiness, 1);
else
  emc.probabilityPeakiness = 0;
end

if isfield(emc, 'whitenProjections')
  EMC_assert_numeric(emc.whitenProjections, 1);
else
  emc.whitenProjections = 0;
end

if isfield(emc, 'rot_option_global')
  EMC_assert_numeric(emc.rot_option_global, 1);
else
  emc.rot_option_global = 1;
end


if isfield(emc, 'rot_option_local')
  EMC_assert_numeric(emc.rot_option_local, 1);
else
  emc.rot_option_local = 1;
end

if isfield(emc, 'rot_default_grouping_global')
  EMC_assert_numeric(emc.rot_default_grouping_global, 1);
else
  emc.rot_default_grouping_global = 3;
end

if isfield(emc, 'rot_default_grouping_local')
  EMC_assert_numeric(emc.rot_default_grouping_local, 1);
else
  emc.rot_default_grouping_local = 3;
end

if isfield(emc, 'mag_option_global')
  EMC_assert_numeric(emc.mag_option_global, 1);
else
  emc.mag_option_global = 1;
end

if isfield(emc, 'mag_option_local')
  EMC_assert_numeric(emc.mag_option_local, 1);
else
  emc.mag_option_local = 1;
end

if isfield(emc, 'mag_default_grouping_global')
  EMC_assert_numeric(emc.mag_default_grouping_global, 1);
else
  emc.mag_default_grouping_global = 5;
end

if isfield(emc, 'mag_default_grouping_local')
  EMC_assert_numeric(emc.mag_default_grouping_local, 1);
else
  emc.mag_default_grouping_local = 5;
end

if isfield(emc, 'tilt_option_global')
  EMC_assert_numeric(emc.tilt_option_global, 1);
else
  emc.tilt_option_global = 5;
end

if isfield(emc, 'tilt_option_local')
  EMC_assert_numeric(emc.tilt_option_local, 1);
else
  emc.tilt_option_local = 5;
end

if isfield(emc, 'tilt_default_grouping_global')
  EMC_assert_numeric(emc.tilt_default_grouping_global, 1);
else
  emc.tilt_default_grouping_global = 5;
end

if isfield(emc, 'tilt_default_grouping_local')
  EMC_assert_numeric(emc.tilt_default_grouping_local, 1);
else
  emc.tilt_default_grouping_local = 5;
end


if isfield(emc, 'peak_mask_fraction')
  EMC_assert_numeric(emc.flgPeakMask,1);
else
  emc.peak_mask_fraction = 0.4;
end

if isfield(emc, 'min_overlap')
  EMC_assert_numeric(emc.min_overlap,1);
else
  emc.min_overlap = 0.5;
end


if isfield(emc, 'k_factor_scaling')
  EMC_assert_numeric(emc.k_factor_scaling,1);
else
  emc.k_factor_scaling = nan;
end

if isfield(emc, 'shift_z_to_to_centroid')
  EMC_assert_boolean(emc.shift_z_to_to_centroid);
else
  emc.shift_z_to_to_centroid = true;
end

emc = EMC_assert_deprecated_substitution(emc, 'tomo_cpr_defocus_range', 'tomoCprDefocusRange');
if isfield(emc, 'tomo_cpr_defocus_range')
  EMC_assert_numeric(emc.tomo_cpr_defocus_range, 1, [0.0, 100000e-9]);
else
  emc.tomo_cpr_defocus_range = 500e-9;
end

emc = EMC_assert_deprecated_substitution(emc, 'tomo_cpr_defocus_step', 'tomoCprDefocusStep');
if isfield(emc, 'tomo_cpr_defocus_step')
  EMC_assert_numeric(emc.tomo_cpr_defocus_step, 1, [1.0e-9, 10000e-9]);
else
  emc.tomo_cpr_defocus_step = 100e-9;
end

emc = EMC_assert_deprecated_substitution(emc, 'tomo_cpr_defocus_refine', 'tomoCprDefocusRefine');
if isfield(emc, 'tomo_cpr_defocus_refine')
  EMC_assert_boolean(emc.tomo_cpr_defocus_refine);
else
  emc.tomo_cpr_defocus_refine = false;
end

if isfield(emc, 'print_alignment_stats')
  EMC_assert_boolean(emc.print_alignment_stats);
else
  emc.print_alignment_stats = false;
end

if isfield(emc, 'printShiftsInParticleBasis')
  EMC_assert_boolean(emc.printShiftsInParticleBasis);
else
  emc.printShiftsInParticleBasis = true;
end

if isfield(emc, 'ML_compressByFactor')
  EMC_assert_numeric(emc.ML_compressByFactor, 1);
else
  emc.ML_compressByFactor = 2.0;
end

if isfield(emc, 'ML_angleTolerance')
  EMC_assert_numeric(emc.ML_angleTolerance, 1);
else
  emc.ML_angleTolerance = 2.0;
end

if isfield(emc, 'mtf_value')
  EMC_assert_numeric(emc.mtf_value, 1);
else
  emc.mtf_value = 1;
end

% Number of tilt processes to run in parallel in ctf 3d.
if isfield(emc, 'n_tilt_workers')
  EMC_assert_numeric(emc.n_tilt_workers, 1);
else
  emc.n_tilt_workers = 4;
end

if isfield(emc,'useSurfaceFit')
  EMC_assert_boolean(emc.useSurfaceFit)
else
  emc.useSurfaceFit = false;
end

if isfield(emc, 'test_flip_defocus_offset')
  EMC_assert_boolean(emc.test_flip_defocus_offset)
else
  emc.test_flip_defocus_offset = false;
end

if isfield(emc, 'test_flip_tilt_offset')
  EMC_assert_boolean(emc.test_flip_tilt_offset)
else
  emc.test_flip_tilt_offset = false;
end


% Number of tiltalign processes to run in parallel in tomoCPR 
% For now, default to zero and manually re-run while sorting out the
% optimization process
if isfield(emc, 'run_tomocpr_alignments')
  EMC_assert_numeric(emc.run_tomocpr_alignments, 1);
else
  emc.run_tomocpr_alignments = 0;
end

% Generally useful for single particle like projects. If there is substantial density not related to the specimen,
% this will not be so useful as the measure defocus will come largely from those. 
% Since most people are using other software for high-res in vitro work, default this to false now.
if isfield(emc, 'set_defocus_origin_using_subtomos')
  EMC_assert_boolean(emc.set_defocus_origin_using_subtomos)
else
  emc.set_defocus_origin_using_subtomos = false;
end

if isfield(emc, 'max_ctf3dDepth')
  EMC_assert_numeric(emc.max_ctf3dDepth, 1, [1 * 10^-9, 1000 * 10^-9]);
else
  emc.max_ctf3dDepth = 100*10^-9;
end

if isfield(emc, 'expand_lines')
  EMC_assert_boolean(emc.expand_lines);
else
  emc.expand_lines = true;
end

if isfield(emc, 'super_sample')
  emc.super_sample
  EMC_assert_numeric(emc.super_sample, 1, [2, 5]);
else
  emc.super_sample = 3;
end

if isfield(emc, 'debug_print')
  EMC_assert_boolean(emc.debug_print);
else
  emc.debug_print = false;
end

if isfield(emc, 'tmp_scan')
  EMC_assert_numeric(emc.tmp_scan, 3, [-1, 1]);
else
  emc.tmp_scan = [1,1,0];
end

if isfield(emc, 'Tmp_bandpass')
  EMC_assert_numeric(emc.Tmp_bandpass, 3);
else
  emc.Tmp_bandpass = [0.001, 1200, 28];
end

if isfield(emc, 'Tmp_half_precision')
  EMC_assert_boolean(emc.Tmp_half_precision);
else
  emc.Tmp_half_precision = false;
end

if isfield(emc, 'Pca_bandpass')
  EMC_assert_numeric(emc.Pca_bandpass, 3);
else
  emc.Pca_bandpass = [0.001, 1200, 28];
end

if isfield(emc, 'autoAli_switchAxes')
  EMC_assert_boolean(emc.autoAli_switchAxes);
else
  emc.autoAli_switchAxes = true;
end

if isfield(emc, 'ctf_tile_size')
  EMC_assert_numeric(emc.ctf_tile_size, 1);
else
  emc.ctf_tile_size = floor(680e-10 / emc.pixel_size_si);
end
emc.ctf_tile_size = emc.ctf_tile_size + mod(emc.ctf_tile_size,2);

if isfield(emc, 'ctf_tile_overlap')
  EMC_assert_numeric(emc.ctf_tile_overlap, 1);
else
  emc.ctf_tile_overlap = 2;
end

if isfield(emc, 'deltaZTolerance')
  EMC_assert_numeric(emc.deltaZTolerance, 1, [10e-9, 300e-9]);
else
  emc.deltaZTolerance = 100e-9;
end

if isfield(emc, 'zShift')
  EMC_assert_numeric(emc.zShift, 1, [100e-9, 300e-9]);
else
  emc.zShift = 150e-9;
end

if isfield(emc, 'ctfMaxNumberOfTiles')
  EMC_assert_numeric(emc.ctfMaxNumberOfTiles, 1);
else
  emc.('ctfMaxNumberOfTiles') = 10000;
end

if isfield(emc, 'remove_duplicates')
  EMC_assert_boolean(emc.remove_duplicates);
else
  emc.remove_duplicates = true;
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% CTF-related parameters that were previously loaded elsewhere
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Phase plate shift for CTF correction (multiplied by pi when used)
if isfield(emc, 'PHASE_PLATE_SHIFT')
  EMC_assert_numeric(emc.PHASE_PLATE_SHIFT, 2);
  emc.PHASE_PLATE_SHIFT = emc.PHASE_PLATE_SHIFT .* pi;
else
  emc.PHASE_PLATE_SHIFT = [0, 0];
end

% Padded size for CTF operations
if isfield(emc, 'paddedSize')
  EMC_assert_numeric(emc.paddedSize, 1, [256, 2048]);
else
  emc.paddedSize = 768;  % Standardizing on 768 as default
end

% Whether to erase beads after CTF correction
if isfield(emc, 'erase_beads_after_ctf')
  EMC_assert_boolean(emc.erase_beads_after_ctf);
else
  emc.erase_beads_after_ctf = false;
end

% Sign flip test for defocus (legacy parameter)
if isfield(emc, 'testFlipSign')
  EMC_assert_numeric(emc.testFlipSign, 1, [-1, 1]);
  emc.defShiftSign = emc.testFlipSign;  % Alias for compatibility
else
  emc.defShiftSign = -1;
  emc.testFlipSign = -1;  % Keep both for backward compatibility
end

% Map back iteration counter
if isfield(emc, 'mapBackIter')
  EMC_assert_numeric(emc.mapBackIter, 1, [0, 1000]);
else
  emc.mapBackIter = 0;
end

% Force no defocus stretch in CTF refinement
if isfield(emc, 'force_no_defocus_stretch')
  EMC_assert_boolean(emc.force_no_defocus_stretch);
else
  emc.force_no_defocus_stretch = false;
end

% Fraction of extra tilt data to use in refinement
if isfield(emc, 'fraction_of_extra_tilt_data')
  EMC_assert_numeric(emc.fraction_of_extra_tilt_data, 1, [0.0, 1.0]);
else
  emc.fraction_of_extra_tilt_data = 0.25;
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Disk and memory management parameters
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Conserve disk space by removing intermediate files
if isfield(emc, 'conserveDiskSpace')
  EMC_assert_numeric(emc.conserveDiskSpace, 1, [0, 2]);
else
  emc.conserveDiskSpace = 0;
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Geometry and analysis parameters
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Remove bottom percentage of particles based on scores
if isfield(emc, 'removeBottomPercent')
  EMC_assert_numeric(emc.removeBottomPercent, 1, [0.0, 100.0]);
else
  emc.removeBottomPercent = 0.0;
end

% Low resolution cutoff in Angstroms
if isfield(emc, 'lowResCut')
  EMC_assert_numeric(emc.lowResCut, 1, [10, 200]);
else
  emc.lowResCut = 40;
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Alignment parameters
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Whether to constrain alignment search based on symmetry
if isfield(emc, 'symmetry_constrained_search')
  EMC_assert_boolean(emc.symmetry_constrained_search);
else
  emc.symmetry_constrained_search = false;
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Dose-related parameters for tilt series
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Use one over cosine dose weighting
if isfield(emc, 'oneOverCosineDose')
  EMC_assert_boolean(emc.oneOverCosineDose);
else
  emc.oneOverCosineDose = false;
end

% Starting angle for dose accumulation
if isfield(emc, 'startingAngle')
  EMC_assert_numeric(emc.startingAngle, 1, [-90, 90]);
else
  emc.startingAngle = 0;
end

% Starting direction for tilt series acquisition
if isfield(emc, 'startingDirection')
  EMC_assert_string_value(emc.startingDirection, {'pos', 'neg'}, false);
else
  emc.startingDirection = 'pos';
end

% Dose symmetric increment (0 or number of tilts per sweep)
if isfield(emc, 'doseSymmetricIncrement')
  EMC_assert_numeric(emc.doseSymmetricIncrement, 1, [0, 100]);
else
  emc.doseSymmetricIncrement = 0;
end

% Dose at minimum tilt angle
if isfield(emc, 'doseAtMinTilt')
  EMC_assert_numeric(emc.doseAtMinTilt, 1, [0, 1000]);
else
  emc.doseAtMinTilt = 0;
end

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Parameters replacing global variables
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Debug print mode (replaces emc_debug_print global)
if isfield(emc, 'debug_print')
  EMC_assert_boolean(emc.debug_print);
else
  emc.debug_print = false;
end

% Binary mask low pass for shape masking (replaces bh_global_binary_mask_low_pass)
if isfield(emc, 'shape_mask_lowpass_override')
  EMC_assert_numeric(emc.shape_mask_lowpass_override, 1, [10, 100]);
elseif isfield(emc, 'setMaskLowPass')
  % Support legacy parameter name
  EMC_assert_numeric(emc.setMaskLowPass, 1, [10, 100]);
  emc.shape_mask_lowpass_override = emc.setMaskLowPass;
else
  % Use existing shape_mask_lowpass if no override
  emc.shape_mask_lowpass_override = 0; % 0 means use shape_mask_lowpass
end

% Binary mask threshold (replaces bh_global_binary_mask_threshold)
if isfield(emc, 'shape_mask_threshold_override')
  EMC_assert_numeric(emc.shape_mask_threshold_override, 1, [0.1, 10.0]);
elseif isfield(emc, 'setMaskThreshold')
  % Support legacy parameter name
  EMC_assert_numeric(emc.setMaskThreshold, 1, [0.1, 10.0]);
  emc.shape_mask_threshold_override = emc.setMaskThreshold;
else
  % Use existing shape_mask_threshold if no override
  emc.shape_mask_threshold_override = 0; % 0 means use shape_mask_threshold
end

% PCA mask threshold (replaces bh_global_binary_pcaMask_threshold)
if isfield(emc, 'pca_mask_threshold')
  EMC_assert_numeric(emc.pca_mask_threshold, 1, [0.0, 5.0]);
elseif isfield(emc, 'setPcaMaskThreshold')
  % Support legacy parameter name
  EMC_assert_numeric(emc.setPcaMaskThreshold, 1, [0.0, 5.0]);
  emc.pca_mask_threshold = emc.setPcaMaskThreshold;
else
  emc.pca_mask_threshold = 0.5;
end

% Volume scaling factor (replaces bh_global_vol_est_scaling)
if isfield(emc, 'particle_volume_scaling')
  EMC_assert_numeric(emc.particle_volume_scaling, 1, [0.1, 10.0]);
elseif isfield(emc, 'setParticleVolumeScaling')
  % Support legacy parameter name
  EMC_assert_numeric(emc.setParticleVolumeScaling, 1, [0.1, 10.0]);
  emc.particle_volume_scaling = emc.setParticleVolumeScaling;
else
  emc.particle_volume_scaling = 1.0;
end

% Phase plate mode (replaces bh_global_turn_on_phase_plate)
if isfield(emc, 'phase_plate_mode')
  EMC_assert_boolean(emc.phase_plate_mode);
elseif isfield(emc, 'phakePhasePlate')
  % Support legacy parameter name
  EMC_assert_numeric(emc.phakePhasePlate, 1);
  emc.phase_plate_mode = (emc.phakePhasePlate ~= 0);
else
  emc.phase_plate_mode = false;
end

% Use Fourier interpolation (replaces bh_global_do_2d_fourier_interp)
if isfield(emc, 'use_fourier_interp')
  EMC_assert_boolean(emc.use_fourier_interp);
elseif isfield(emc, 'useFourierInterp')
  % Support legacy parameter name
  EMC_assert_numeric(emc.useFourierInterp, 1);
  emc.use_fourier_interp = (emc.useFourierInterp ~= 0);
else
  emc.use_fourier_interp = true;
end

% Enable profiling (replaces bh_global_do_profile)
if isfield(emc, 'enable_profiling')
  EMC_assert_boolean(emc.enable_profiling);
elseif isfield(emc, 'doProfile')
  % Support legacy parameter name
  EMC_assert_boolean(emc.doProfile);
  emc.enable_profiling = emc.doProfile;
else
  emc.enable_profiling = false;
end

% TomoCPR diagnostics saving (replaces bh_global_save_tomoCPR_diagnostics - unused but keep for future)
if isfield(emc, 'save_tomocpr_diagnostics')
  EMC_assert_boolean(emc.save_tomocpr_diagnostics);
elseif isfield(emc, 'tomoCprDiagnostics')
  % Support legacy parameter name
  EMC_assert_numeric(emc.tomoCprDiagnostics, 1);
  emc.save_tomocpr_diagnostics = (emc.tomoCprDiagnostics ~= 0);
else
  emc.save_tomocpr_diagnostics = false;
end
