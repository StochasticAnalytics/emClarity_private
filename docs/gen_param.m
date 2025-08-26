% This is a comment
% Inline comments will break the parser.


% String to name the structure that contains all of the metadata, projectName
subTomoMeta=full_enchilada_2_1_branch_5

save_mapback_classes=1
tomoCPR_n_particles_minimum=1

measure_noise_variance=0

fastScratchDisk=ram

nGPUs=4
nCpuCores=16
n_tilt_workers=4

refine_defocus_cisTEM=0
rerun_refinement_cisTEM=0

phakePhasePlate=0
flgQualityWeight=0

flgMultiRefAlignment=0
updateClassByBestReferenceScore=0

max_ctf3dDepth=100e-9
% Do not whiten (1), but apply ctf weiner filter (3) with additive term
whitenPS=[0,0,0.5]
diameter_fraction_for_local_stats=0.9
test_local=1
scale_mip=0


nPeaks=1
symmetry=C12
doHelical=0

Pca_refineKmeans=1

% if > 1 use this many subtomos in the avg
% if < 1 use this fraction in the avg
%ccc_cutoff=0.6

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%    Mask parameters    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% The particle radius in x,y,z Angstrom, smallest value to contain particle. 
% For particles in a lattice, neighboring particles can be used in alignment
% by specifying a larger mask size, but this paramter must correspond to your
% target, a cetral hexamer of capsid proteins for example.

% For TM
particleRadius=[180,180,150]
particleMass=3.2

Ali_mType=cylinder
Cls_mType=cylinder


% For special cases where repeated motifs are present which might cause one
% subtomo to drift to a neighbor. This allows a larger alignment mask to be used
% for the rotational search (Ali_m...) but limits the translational peak search.
Peak_mType=cylinder
%Peak_mRadius=[210,210,320]
Peak_mRadius=[40,40,40]
% mask radius and center - and center in Angstrom. Mask size is determined 
% large enough to contain delocalized signal, proper apodization, and to 
% avoid wraparound error in cross-correlation.
% mask radius and center - and center in Angstrom. Mask size is determined 
% large enough to contain delocalized signal, proper apodization, and to 
% avoid wraparound error in cross-correlation.
Ali_mRadius=[220,220,164]
%Ali_mRadius=[220,220,200]
Ali_mCenter=[0,0,0]
Cls_mRadius=[220,220,164]
Cls_mCenter=[ 0,0,0 ]


% Sampling rate
Ali_samplingRate=3
Cls_samplingRate=3

move_reference_by_com=0


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%% Tomo-constrained projection refinement parameters    %%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


% I advise to avoid using this experimental feature for now.
tomoCprDefocusRefine=0
tomoCprDefocusRange=500e-9; 
tomoCprDefocusStep=20e-9;

% By default the patch size is calculated based on the number of available fiducials and the
% mass. To limit the number of local areas, set this to something other than zero.
tomoCPR_target_n_patches_x_y=[3,4]
tomoCPR_random_subset=0

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%    subTomogram alignment           %%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

Raw_className=0
% Second row specifies C1 symmetry
Raw_classes_odd=[0;12.*ones(1,1)]
Raw_classes_eve=[0;12.*ones(1,1)]

% replicate the in plane angles at each (CX) symmetry position
symmetry_constrained_search=0
Raw_angleSearch=[0,0,180,3]
print_alignment_stats=1
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%    Template matching parameters    %%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


Tmp_bandpass=[0.01,1200,25]
Tmp_samplingRate=5
Tmp_threshold=1500
Tmp_angleSearch=[180,12,180,12]

Tmp_targetSize=[512,512,768]

Tmp_half_precision=0

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%    Class reference   %%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%




Cls_className=49
Cls_classes_odd=[1:64;12.*ones(1,64)]
Cls_classes_eve=[1:64;12.*ones(1,64)]

 

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%    FSC Paramters    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% On/Off anisotropic SSNR calc
flgCones=0
fsc_shape_mask=0
% B-factor applied to weighted averages and refs. Should be < 20. Can be a vector
% where the 2:end positions generate independent maps at that sharpening 
% when avg paramN.m N FinalAlignment is run.

Fsc_bfactor=10

% For very tightly packed subTomos set to 1 to avoid mixing halfsets
% form overlaping peripheral density. fscGoldSplitOnTomos=0
fscGoldSplitOnTomos=0
% Default to doing an alignment between class halfs before calculating FSC
% This should be deprecated as the halves converge to each other.
fscWithChimera=0

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%    Classification Paramters    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Constrain to the asymmetric unit
% Only for Cx and cylinder masks right now.
Pca_constrain_symmetry=1
flgPcaShapeMask=0
% On/Off classification. This must be on when "avg paramN.m N RawAlignment"
% is run at the begining of a cycle where classification is to be run.
flgClassify=1

% List of different cluster sizes to try, eg [3;4]
Pca_clusters=[49,64]

% Maximum number of eigenvalues/vectors to save
Pca_maxEigs=64

% Different resolution bands to run PCA on. Not all need to be used for subsequent
% clustering. (Angstrom)

pcaScaleSpace=[21,42,84];


% Different ranges of coefficients to use in the clustering. At times, the 
% missing wedge can be a strong feature, such that ignoring the first few 
% eigen values can be usefule. [2:40 ; 6;40 ; 10:40]
% Each row must have the same number of entries, and there must be a row 
% for each scale space, even if it is all zeros.

% NOTE: if using multi_refalignment, this must match the number of references
Pca_coeffs=[3:48;3:48;3:48;3:48];
Pca_bandpass=[0.01,1200,20];




% The number of subtomos to process at once before pulling tempDataMatrix off 
% the gpu and into main memory.
PcaGpuPull=5000
Pca_randSubset=0





%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%% Parameters for CTF all si (meters, volts)%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%




%%%%%%%%%%   Microscope parameters     %%%%%%%%%%

% Of the data saved in fixed stacks - MUST match header
PIXEL_SIZE=2.50e-10
% Currently any super-resolution data is cropped in Fourier Space after alignment
% allowing for finer sampling when interpolating the stacks, while then 
% filtering out noise due to aliasing.
SuperResolution=0
% Spherical abberation
Cs=2.7e-3 
% Accelerating voltage
VOLTAGE=300e3
% Percent amplitude contrast
AMPCONT=0.04

% search range - generally safe to test a wide range
defEstimate=3.5e-6
defWindow=1.75e-6
% The PS is considered from the lower resolution inflection point
% past the first zero to this cutoff resolution
defCutOff=6e-10

% Total dose in electron/A^2, assumed constant rate
CUM_e_DOSE=180
% Gold fiducial diameter
beadDiameter=10e-9


oneOverCosineDose=0
startingAngle=0
startingDirection=pos
doseSymmetricIncrement=3
% The reported value is 4.86 but I'm scaling this down to 60% of that
doseAtMinTilt=2.9


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%% Advanced Parameters  %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% default is 1.5, may need to shrink for large objects, may need to increase for periodic objects.
scaleCalcSize=1.3

autoAli_min_sampling_rate=10
autoAli_max_sampling_rate=4
autoAli_patch_size_factor=4
autoAli_patch_overlap=0.6
autoAli_max_resolution=18
autoAli_refine_on_beads=0
autoAli_iterations_per_bin=2
autoAli_patch_tracking_border=64
autoAli_n_iters_no_rotation=2
autoAli_max_shift_in_angstroms=300
autoAli_max_shift_factor=1

ctf_tile_overlap=4



