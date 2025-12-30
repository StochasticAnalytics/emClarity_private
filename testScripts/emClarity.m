function [ varargout ] = emClarity( varargin )
%Wrapper to run BH_subtomo programs.
%   Detailed explanation goes here

% Disable warnings

warning off
cudaStart='';
% FIXME: This only applies to ctf estimate, and it looks like there is no version 2 !?
useV2 = false;
useV1 = false;

% first argument is the program to run or "help" to print a list of available
% options.
setenv('MATLAB_SHELL','/bin/bash');
% Capture original CUDA visibility so we can restore on exit/early returns
origCUDA = getenv('CUDA_VISIBLE_DEVICES');
[sysERR] = system('mkdir -p logFile');

% These paths are fine in the compiled version, but if you are compiling on
% your own, you will need to edit. If you have a better solution, please
% FIXME! The dependencies are linked on the wiki.
emClarity_ROOT=getenv('emClarity_ROOT');
if isempty(emClarity_ROOT)
  error('emClarity_ROOT is not set properly in your run script');
end

% For deployed functions, the emClarity folder is probably renamed
% emClarity_1_5_xx, we need to replace this for the ctf root stuff.
% using fileparts will give different answers if the user defines
% emClarity_ROOT with or without a trailing slash. Instead simply
slashCheck = strsplit(emClarity_ROOT,'/');
[pathWithDir,~,~] = fileparts(emClarity_ROOT);
if isempty(slashCheck{end})
  % There is a trailing slash
  shift_end = 1;
  add_slash = '';
else
  shift_end = 0;
  add_slash = '/';
end

% fprintf('ctfroot is %s\n',ctfroot);

emC_PATH = strsplit(pathWithDir, slashCheck{end-shift_end});
emC_PATH = sprintf('%s%semClarity',emC_PATH{1},add_slash);

if isdeployed
  % This will find the m-file, which is used to grab the shell script which is what we want to define here.
  [BH_checkInstallPath, fname, fext] = fileparts(which('BH_checkInstall'));
  BH_checkInstallPath = fullfile(BH_checkInstallPath,fname);
  % fprintf('BH_checkInstall is %s\n',BH_checkInstallPath);
  %BH_checkInstallPath = sprintf('%s%s/metaData/BH_checkInstall',ctfroot,compiled_PATH);
else
  BH_checkInstallPath=sprintf('%s/metaData/BH_checkInstall',emC_PATH);
end

% For whatever reason, matlab can find BH_checkInstall, but not emC_auto... just grab the path root from BH_checkInstall
% NOTE: if there is a trailing slash, fileparts will not work here
emC_autoAliPath = sprintf('%s/alignment/emC_autoAlign',fileparts(fileparts(BH_checkInstallPath)));
emC_findBeadsPath = sprintf('%s/alignment/emC_findBeads',fileparts(fileparts(BH_checkInstallPath)));

% fprintf('emC_autoAlign is %s\n',emC_autoAliPath);
% fprintf('emC_findBeads is %s\n',emC_findBeadsPath);


setenv('EMC_AUTOALIGN',emC_autoAliPath);
setenv('EMC_FINDBEADS',emC_findBeadsPath);
setenv('BH_CHECKINSTALL',BH_checkInstallPath);

emC_cisTEMDepPath=sprintf('%s/bin/deps',emClarity_ROOT);
emC_cisTEM_deps = importdata(sprintf('%s/cisTEMDeps.txt',emC_cisTEMDepPath));

for iDep = 1:length(emC_cisTEM_deps)
  setenv(sprintf('EMC_%s',upper(emC_cisTEM_deps{iDep})), sprintf('%s/emC_%s',emC_cisTEMDepPath,emC_cisTEM_deps{iDep}));
end

nArgs = length(varargin);
if nArgs > 1 && strcmp(varargin{2},'gui')
  emClarityApp;
  return
end
if ( sysERR )
  fprintf('system command for mkdir failed for some reason\n');
  unix('mkdir -p logFile');
end

cudaCleanup  = onCleanup(@() setenv('CUDA_VISIBLE_DEVICES', origCUDA));
timeStart = datetime();
fprintf('\n\t\t***************************************\n\n');
if isdeployed && nArgs > 0
  fprintf('emClarity version %s\n', varargin{1});
else
  fprintf('emClarity (interactive)\n');
end
fprintf('run starting on %s\n', timeStart);
fprintf('cmd ');
% Start from 2 if deployed (skip version), 1 otherwise
startIdx = 1;
if isdeployed && length(varargin) > 1 && ~strcmp(varargin{1},'help')
  startIdx = 2;
end
% Initialize cmdIN to avoid undefined variable error
cmdIN = 'emClarity ';
for iArg = startIdx:length(varargin)
  if iArg > 1 || ~isdeployed
    cmdIN = [cmdIN sprintf('%s ',varargin{iArg})];
  end
  fprintf('%s ', varargin{iArg});
end
fprintf('\n\n')
fprintf('\t\t***************************************\n\n');
% Get rid of the shorthead passed in by the emClarity script.
if isdeployed
  varargin = varargin(2:end);
  nArgs = nArgs - 1;
end

emcHelp = false;
emcProgramHelp=false;




% For some reason, this doesn't fall through, so error if < arg
if nArgs > 0
  if ~strcmp(varargin{1},'check')
    if strcmp(varargin{1},'v2')
      % FIXME: This only applies to ctf estimate, and it looks like there is no version 2 !?
      useV2 = true;
      varargin = varargin(2:end);
    elseif strcmp(varargin{1},'v1')
      useV1 = true;
      varargin = varargin(2:end);
    else
      if nArgs < 2
        emcHelp = strcmpi(varargin{1},'help') || strcmp(varargin{1},'h');
      else
        % Check if the last argument is 'help' for program-specific help
        emcProgramHelp = strcmpi(varargin{end},'help') || strcmp(varargin{end},'h');
      end
    end
  end
else
  % When no arguments provided, show help
  emcHelp = true;
  varargin = {'help'}; % Set to help so the switch statement works
  nArgs = 1;
end

% Now that varargin is guaranteed to have at least one element, update command string if needed
if nArgs > 0
  cmdIN = sprintf('emClarity %s ',varargin{1});
end

multiGPUs = 1;
emc = struct();
% Get program specific help with emClarity progName help. Otherwise, we parse the third argument
if nArgs > 1 && ~(emcHelp || emcProgramHelp)
  switch varargin{1}
    case 'ctf'
      emc = emC_testParse(varargin{3});
    case 'rescale'
      % nothing to parse
      multiGPUs = 0;
    case 'alignFrames'
      error('alignFrames is not yet in production. Soon though!')
      % nothing to parse
      multiGPUs = 0;
    case 'removeNeighbors'
      % nothing to parse
      multiGPUs = 0;
    case 'cleanTemplateSearch'
      multiGPUs = 0;
    case 'segment'
      multiGPUs = 0;
    case 'getActiveTilts'
      multiGPUs = 0;
    case 'plotFSC'
      % nothing to parse
      multiGPUs = 0;
    case 'mask'
      % mask command doesn't need parameter file
      multiGPUs = 0;
    case 'simulate'
      % simulate commands are standalone (no parameter file)
      multiGPUs = 0;
    otherwise
      emc = emC_testParse(varargin{2});
  end
  if ( multiGPUs )
    % wanted num gpus
    nGPUs_wanted = emc.('nGPUs');
    cudaStart = getenv('CUDA_VISIBLE_DEVICES')
    nGPUs_visible = gpuDeviceCount;
    if nGPUs_visible < nGPUs_wanted
      error('\n\n\t\t%d gpus requested but only %d are visible to the system\n\n',nGPUs_wanted, nGPUs_visible);
    elseif nGPUs_visible > nGPUs_wanted
      % Select largest mem visible
      fprintf('\nThere are more gpus visible than requested, selecting the largest memory devices\n');
      select_gpus(nGPUs_wanted,nGPUs_visible,cmdIN);
    else
      fprintf('\nThe number of gpus requested matches those visible to the system\n');
    end
  end
end

% if the emc struct is not empty, grab the subTomoMeta name for logging
if isempty(fieldnames(emc))
  log_file_name = 'logFile/emClarity.logfile';
else 
  log_file_name = sprintf('logFile/emClarity_%s.logfile', emc.subTomoMeta);
end

diary(log_file_name)
% Ensure diary/env are restored even on early returns or errors
diaryCleanup = onCleanup(@() diary('off'));

switch varargin{1}
  case 'help'
    fprintf(['\n=== emClarity Commands ===\n\n',...
      'For detailed help on any command, use: emClarity <command> help\n\n',...
      '--- Project Setup & System ---\n',...
      '  help                - Show this help message\n',...
      '  check               - Check system dependencies and installation\n',...
      '  init                - Initialize new project from template matching results\n',...
      '  segment             - Define subregions to reconstruct\n\n',...
      '--- Tilt-Series Processing ---\n',...
      '  autoAlign           - Align tilt-series using IMOD\n',...
      '  ctf                 - Estimate, correct, or refine CTF parameters\n',...
      '  tomoCPR             - Tomogram constrained projection refinement\n',...
      '  getActiveTilts      - Report number of active tilt-series\n\n',...
      '--- Particle Picking ---\n',...
      '  templateSearch      - Template matching/global particle search\n',...
      '  cleanTemplateSearch - [experimental, likely broken] Remove based on neighbor constraints\n',...
      '  removeNeighbors     - [experimental, likely broken] Clean based on lattice constraints\n\n',...
      '--- Sub-tomogram Averaging ---\n',...
      '  avg                 - Average aligned subtomograms\n',...
      '  alignRaw            - Align subtomograms to reference(s)\n',...
      '  skip                - Skip alignment after averaging/removing classes\n\n',...
      '--- Resolution & Analysis ---\n',...
      '  fsc                 - Calculate Fourier Shell Correlation\n',...
      '  plotFSC             - Plot FSC curves from multiple cycles\n\n',...
      '--- Classification & PCA ---\n',...
      '  pca                 - Principal component analysis for clustering\n',...
      '  cluster             - Sort populations using various approaches\n\n',...
      '--- Utilities ---\n',...
      '  geometry            - Edit or analyze experimental metadata\n',...
      '  mask                - Create masks for volumes\n',...
      '  rescale             - Change magnification of volume\n',...
      '  reconstruct         - Reconstruct volume from subtomograms\n',...
      '  montage             - Unstack/rotate montage elements\n',...
      '  experimental        - Access experimental features\n\n',...
      '--- Simulation ---\n',...
      '  simulate            - Generate synthetic data (tomograms, tilt files, projections)\n\n']);
    
    % Currently disabled options. Multi-reference alignment
    % % %                       '\nalignRef - align one or more references against a primary ref\n',...
    % % %              '             optionally add multiple instances aligned to each\n',...
    % % %              '             to its respective reference.\n',...
    % % %              '\nalignCls - align refs from alignRef to a usually much larger number of class averages.\n',...
  case 'experimental'
    print_experimental_options();
    
  case 'check'
    if nArgs > 1
      fprintf('check takes no arguments');
    else
      BH_checkInstall(getenv('BH_CHECKINSTALL'))
    end
  case 'segment'
    if emcProgramHelp || ...
        length(varargin) ~= 2
  fprintf(['\nUsage:  emClarity segment build (make bin10 tomos)\n\tor\n\temClarity segment recon (convert model files)\n']);
    else
      recScript(varargin{2});
    end
  case 'getActiveTilts'
    if emcProgramHelp || ...
        length(varargin) ~= 2
      fprintf(['\nUsage: emClarity getActiveTilts param.m\n']);
    else
      emc = emC_testParse(varargin{2});
      % Load using wrapper
      subTomoMeta = BH_loadSubTomoMeta(emc.('subTomoMeta'), emc.('metadata_format'));
      [tiltNameList, nTiltSeries] = BH_returnIncludedTilts( subTomoMeta.mapBackGeometry );
      fprintf('%d\n',nTiltSeries);
      return 
    end
  case 'init'
  if emcProgramHelp || ...
    (length(varargin) < 2 || length(varargin) > 5)
      fprintf(['\nUsage: emClarity init param.m [tomoCPR_cycle] [iteration] [start_tilt]\n\n',...
        'Initialize new emClarity project from template search results.\n\n',...
        'Arguments:\n',...
        '  param.m      - Parameter file for the project\n',...
        '  tomoCPR_cycle - [Optional] TomoCPR cycle for continuing processing\n',...
        '  iteration    - [Optional] Iteration number for restart\n',...
        '  start_tilt   - [Optional] Starting tilt number for partial processing\n\n',...
        'Function: Sets up project geometry, initializes metadata structures,\n',...
        'and prepares for subtomogram averaging workflow.\n\n',...
        'Requirements:\n',...
        '  - Parameter file must be configured\n',...
        '  - Template search results must exist\n',...
        '  - CTF estimation should be completed\n\n',...
        'Examples:\n',...
        '  emClarity init param.m\n',...
        '  emClarity init param.m 2 1 5\n']);
    elseif length(varargin) == 5
      emC_testParse(varargin{2});
      BH_geometryInitialize(varargin{2},varargin{3},varargin{4},varargin{5});
    elseif length(varargin) == 4
      emC_testParse(varargin{2});
      BH_geometryInitialize(varargin{2},varargin{3},varargin{4});
    elseif length(varargin) == 3
      emC_testParse(varargin{2});
      BH_geometryInitialize(varargin{2},varargin{3});
    else
      emC_testParse(varargin{2});
      BH_geometryInitialize(varargin{2});
    end
  case 'removeNeighbors'
    if emcProgramHelp || ...
        length(varargin) ~= 6
      fprintf(['\nUsage: emCLarity removeNeighbors pixelSize CYCLE distanceCutoff (Ang) angleCutoff (Deg) N-neighbors\n']);
    else
      %emC_testParse(varargin{2});
      if length(varargin) == 6
        BH_geometry_Constraints(varargin{2},varargin{3},varargin{4},varargin{5},varargin{6});
      else
        BH_geometry_Constraints(varargin{2},varargin{3},varargin{4},varargin{5},varargin{6},varargin{7});
      end
    end
    
  case 'autoAlign'
    if emcProgramHelp || ...
        (length(varargin) ~= 5 && length(varargin) ~= 6)
      fprintf(['\nUsage: emClarity autoAlign param.m stack_name tilt_file tilt_axis_rotation [pixel_size]\n\n',...
        'Align tilt-series using IMOD integration for fiducial-based alignment.\n\n',...
        'Arguments:\n',...
        '  param.m           - Parameter file for the project\n',...
        '  stack_name        - Input tilt-series stack (.st file)\n',...
        '  tilt_file         - Raw tilt angles file (.rawtlt file)\n',...
        '  tilt_axis_rotation - Tilt axis rotation angle (degrees)\n',...
        '  pixel_size        - [Optional] Pixel size override (Angstroms)\n\n',...
        'Requirements:\n',...
        '  - Both .st and .rawtlt files must exist\n',...
        '  - IMOD must be installed and accessible\n\n',...
        'Examples:\n',...
        '  emClarity autoAlign param.m tilt01.st tilt01.rawtlt 85.3\n',...
        '  emClarity autoAlign param.m tilt01.st tilt01.rawtlt 85.3 1.35\n']);
    else
      emC_testParse(varargin{2});
      if ~exist(varargin{4}, 'file')
        fprintf('Did not find your .rawtlt file %s\n',varargin{3});
        error('Expecting tiltName.st tiltName.rawtlt pixelSize (Ang) imageRotation (degrees)');
      end
      if ~exist(varargin{3}, 'file')
        fprintf('Did not find your .st file %s\n',varargin{2});
        error('Expecting tiltName.st tiltName.rawtlt pixelSize (Ang) imageRotation (degrees)');
      end
      
      if length(varargin) == 5
        BH_runAutoAlign(varargin{2},getenv('EMC_AUTOALIGN'),getenv('EMC_FINDBEADS'),varargin{3},varargin{4},varargin{5});
      else
        BH_runAutoAlign(varargin{2},getenv('EMC_AUTOALIGN'),getenv('EMC_FINDBEADS'),varargin{3},varargin{4},varargin{5},varargin{6});
      end
      
      return
    end
  case 'skip'
    if emcProgramHelp || ...
        (length(varargin) ~= 3 && length(varargin) ~= 4)
      fprintf(['\nUsage: emClarity skip param.m iter [optional: AssignAndMergeToBranch|RemoveClasses]\n']);
    else
      emC_testParse(varargin{2});
      if length(varargin) == 4
        BH_skipClassAlignment(varargin{2},varargin{3},'RawAlignment','1',varargin{4});
      else
        BH_skipClassAlignment(varargin{2},varargin{3},'RawAlignment','1');
      end
    end
  case 'rescale'
    if emcProgramHelp || ...
        length(varargin) ~= 6
      fprintf(['\nUsage: emClarity rescale fileNameIN fileNameOut angPixIN angPixOut cpu/GPU\n']);
    else
      mag = EMC_str2double(varargin{4})/EMC_str2double(varargin{5});
      BH_reScale3d(varargin{2},varargin{3},mag,varargin{6});
    end
  case 'mask'
  if emcProgramHelp || ...
    (~ismember(length(varargin),[4,8,9]))
      fprintf(['\nFor geometric mask:\n', ...
        'fileNameOUT.mrc, pixelSize (Ang), Shape (sphere,cylinder,rectangle), Size/radius/center in pixels: [nX,nY,nZ], [rX,rY,rZ], [cX,cY,cZ], optional: "2d"',...
        '\n\nFor a shape based mask\n', ...
        'fileNameIN.mrc,fileNameOUT.mrc, pixelSize (Ang)\n']);


    else
      switch length(varargin)
        case 4
          maskVol = OPEN_IMG('single', varargin{2});
          pixelSize = EMC_str2double(varargin{4});
          maskVol = BH_mask3d(maskVol,EMC_str2double(varargin{4}),'','');
          SAVE_IMG(MRCImage(gather(maskVol)),varargin{3},pixelSize);
        case 8
          pixelSize = EMC_str2double(varargin{4});
          maskVol = BH_mask3d(varargin{5},EMC_str2double(varargin{6}), ...
            EMC_str2double(varargin{7}), ...
            EMC_str2double(varargin{8}));
          SAVE_IMG(MRCImage(gather(maskVol)),varargin{3},pixelSize);
        case 9
          pixelSize = EMC_str2double(varargin{4});
          maskVol = BH_mask3d(varargin{5},EMC_str2double(varargin{6}), ...
            EMC_str2double(varargin{7}), ...
            EMC_str2double(varargin{8}), ...
            EMC_str2double(varargin{9}));
          SAVE_IMG(MRCImage(gather(maskVol)),varargin{3},pixelSize);
      end
      
    end
  case 'avg'
    if emcProgramHelp || ...
        length(varargin) ~= 4
      fprintf(['\nUsage: emClarity avg param.m cycle_number stage_of_alignment\n\n',...
        'Average aligned subtomograms using gold-standard FSC approach.\n\n',...
        'Arguments:\n',...
        '  param.m           - Parameter file for the project\n',...
        '  cycle_number      - Processing cycle (0 for initial, 1+ for iterative)\n',...
        '  stage_of_alignment - Stage to average:\n',...
        '    RawAlignment    - Post subtomogram alignment\n',...
        '    Cluster_cls     - Post classification\n\n',...
        'Examples:\n',...
        '  emClarity avg param.m 0 RawAlignment\n',...
        '  emClarity avg param.m 3 Cluster_cls\n']);
    else
      emC_testParse(varargin{2});
      BH_average3d(varargin{2}, varargin{3}, varargin{4});
    end
  case 'fsc'
    if emcProgramHelp || ...
        (length(varargin) ~= 4 &&  length(varargin) ~= 6)
      fprintf(['\nUsage: emClarity fsc param.m cycle_number stage_of_alignment\n\n',...
        'Calculate Fourier Shell Correlation and resolution curves.\n\n',...
        'Arguments:\n',...
        '  param.m           - Parameter file for the project\n',...
        '  cycle_number      - Processing cycle to analyze\n',...
        '  stage_of_alignment - Stage to calculate FSC for:\n',...
        '    RawAlignment    - Post subtomogram alignment\n',...
        '    Cluster_cls     - Post classification\n\n',...
        'Output: Creates FSC curves in ./FSC/ directory\n\n',...
        'Examples:\n',...
        '  emClarity fsc param.m 0 RawAlignment\n',...
        '  emClarity fsc param.m 3 Cluster_cls\n']);
    elseif length(varargin) == 4
      emC_testParse(varargin{2});
      BH_fscGold_class(varargin{2}, varargin{3}, varargin{4});
    else
      BH_fscGold_class(varargin{2}, varargin{3}, varargin{4},varargin{5},varargin{6});
    end
  case 'plotFSC'
    if emcProgramHelp || ...
        length(varargin) < 3 || length(varargin) > 4
      fprintf(['\nUsage: emClarity plotFSC\n',...
        'subTomoMeta_name (without .mat)\n',...
        'cycle_list (e.g., ''16'' or ''[10,12,14,16]'')\n',...
        '[optional] reference_list (e.g., ''1'' or ''[1,2]'', default: ''1'')\n\n',...
        'Examples:\n',...
        '  emClarity plotFSC project1 ''[10,12,14,16]'' ''1''\n',...
        '  emClarity plotFSC project1 16 ''[1,2]''\n']);
    else
      if length(varargin) == 3
        BH_plotMultiCycleFSC(varargin{2}, varargin{3});
      else
        BH_plotMultiCycleFSC(varargin{2}, varargin{3}, varargin{4});
      end
    end
  case 'alignRaw'
    if emcProgramHelp || ...
        (length(varargin) ~= 3 && length(varargin) ~= 4)
      fprintf(['\nUsage: emClarity alignRaw param.m cycle_number [scoring_method]\n\n',...
        'Align subtomograms to reference volume(s) for iterative refinement.\n\n',...
        'Arguments:\n',...
        '  param.m        - Parameter file for the project\n',...
        '  cycle_number   - Processing cycle (typically > 0)\n',...
        '  scoring_method - [Optional] Experimental scoring options:\n',...
        '    1 - abs(cross-correlation)\n',...
        '    2 - weighted scoring\n',...
        '    3 - abs(weighted scoring)\n\n',...
        'Function: Performs translational and rotational alignment of\n',...
        'subtomograms against current reference(s) using GPU acceleration.\n\n',...
        'Examples:\n',...
        '  emClarity alignRaw param.m 1\n',...
        '  emClarity alignRaw param.m 2 3\n']);
    else
      emC_testParse(varargin{2});
      if length(varargin) == 3
        BH_alignRaw3d_v2(varargin{2}, varargin{3});
      else
        % Switching to v2 always, 1.5.0.9 20200520
        BH_alignRaw3d_v2(varargin{2},varargin{3}, varargin{4});
      end
    end
    

  case 'pca'
    if emcProgramHelp || ...
        length(varargin) ~= 4  && length(varargin) ~= 5
      fprintf(['\nUsage: emClarity pca param.m cycle_number randomSubset mask_option [mask_value]\n\n',...
        'WARNING: Options 1 and 2 are broken and will return an error.\n',...
        'Use option 3 (user supplied mask) instead.\n\n',...
        'Principal Component Analysis for clustering and variance analysis.\n\n',...
        'Arguments:\n',...
        '  param.m       - Parameter file for the project\n',...
        '  cycle_number  - Processing cycle to analyze\n',...
        '  randomSubset  - 1 to project onto full set, 0 for subset analysis\n',...
        '  mask_option   - Focused masking approach:\n',...
        '    1           - [broken] Standard deviation mask\n',...
        '    2           - [broken] Variance mask\n',...
        '    3           - User supplied mask (requires external mask file)\n',...
        '  mask_value    - [Optional] Threshold value for options 1 or 2\n\n',...
        'For option 3 (user supplied mask):\n',...
        '  Create soft link: <reference_name>-pcaMask.mrc -> your_mask.mrc\n',...
        '  where <reference_name> is the class average file name\n\n',...
        'Examples:\n',...
        '  emClarity pca param.m 2 0 3\n',...
        '  ln -s my_pca_mask.mrc class_1_Ref_STD_1.mrc-pcaMask.mrc\n']);
    else
      emC_testParse(varargin{2});

      if (EMC_str2double(varargin{4}))
        % project onto full set
        BH_pcaPub(varargin{2}, varargin{3}, '1');
      else

        if length(varargin) == 5
          maskVal = EMC_str2double(varargin{5});
        else
          maskVal = 0;
        end

        if (maskVal)
          % Check for broken mask options
          if maskVal == 1 || maskVal == 2
            error(['PCA mask options 1 and 2 are broken. Please use option 3 (user supplied mask).\n',...
                   'See "emClarity pca help" for instructions on creating the required mask file.']);
          elseif maskVal == 3
            % User supplied mask - proceed with option 3
            BH_pcaPub(varargin{2}, varargin{3}, sprintf('%d',-1.*maskVal))
          else
            error('Invalid mask option. Valid options are 3 (user supplied mask). Options 1 and 2 are broken.');
          end
        else
          BH_pcaPub(varargin{2}, varargin{3}, '0')
        end



      end
      
    end
  case 'cluster'
    if emcProgramHelp || ...
        length(varargin) ~= 3
      fprintf(['\nparam.m\n',...
        'cycle number\n']);
    else
      emC_testParse(varargin{2});
      BH_clusterPub(varargin{2}, varargin{3});
    end
  case 'ctf'
    if emcProgramHelp
      fprintf(['\nUsage: emClarity ctf <subcommand> [arguments]\n\n',...
        'Contrast Transfer Function estimation, refinement, and correction.\n\n',...
        'Subcommands:\n\n',...
        'estimate - Initial CTF parameter estimation\n',...
        '  Usage: emClarity ctf estimate param.m tilt_base_name [gpu_idx]\n',...
        '    param.m        - Parameter file\n',...
        '    tilt_base_name - Base name of tilt-series (without extension)\n',...
        '    gpu_idx        - [Optional] GPU index to use\n\n',...
        'refine - Refine CTF parameters\n',...
        '  Usage: emClarity ctf refine param.m tilt_base_name\n',...
        '    param.m        - Parameter file\n',...
        '    tilt_base_name - Base name of tilt-series\n\n',...
        'update - Update CTF correction files\n',...
        '  Usage: emClarity ctf update param.m\n',...
        '    param.m        - Parameter file\n\n',...
        '3d - Apply 3D CTF correction to tomograms\n',...
        '  Usage: emClarity ctf 3d param.m [scratch_dir]\n',...
        '    param.m    - Parameter file\n',...
        '    scratch_dir - [Optional] Temporary directory for processing\n\n',...
        'Examples:\n',...
        '  emClarity ctf estimate param.m tilt01\n',...
        '  emClarity ctf 3d param.m\n']);
    else
      
      emC_testParse(varargin{3});
      
      switch varargin{2}
        case 'estimate'
          if (useV2)
            % FIXME: This only applies to ctf estimate, and it looks like there is no version 2 !?
            if nArgs == 4
              BH_ctf_Estimate_2(varargin{3},varargin{4});
            else
              BH_ctf_Estimate_2(varargin{3},varargin{4},varargin{5});
            end
          else
            if nArgs == 4
              BH_ctf_Estimate(varargin{3},varargin{4});
            else
              BH_ctf_Estimate(varargin{3},varargin{4},varargin{5});
            end
          end
        case 'refine'
          if length(varargin) ~= 4
            error('You need to specify a parameter file and tilt name')
          end
          BH_ctf_Refine2(varargin{3},varargin{4});
        case 'update'
          if length(varargin) > 3
            error('\n\nYou now only need to specify %s parameter file.\n\n','the')
          end
          BH_ctf_Updatefft(varargin{3},'-1','full');
        case '3d'
          if nArgs == 6
            % last is a dummy, used for tomoCPR background
            BH_ctf_Correct3d(varargin{3},varargin{4},varargin{5},varargin{6});
          elseif nArgs == 5
            % Not a public option, start from tilt # (of nTilts)
            BH_ctf_Correct3d(varargin{3},varargin{4},varargin{5});
          elseif nArgs == 4
            BH_ctf_Correct3d(varargin{3},varargin{4});
          else
            BH_ctf_Correct3d(varargin{3});
          end
          
        otherwise
          error('ctf operations are estimate,refine,update, or 3d.');
      end
    end
  case 'simulate'
    if emcProgramHelp
      fprintf(['\nUsage: emClarity simulate <subcommand> [arguments]\n\n',...
        'Generate synthetic cryo-EM data for testing and validation.\n\n',...
        'Subcommands:\n\n',...
        'tomogram    - Generate synthetic 3D tomogram with placed particles\n',...
        '  Usage: emClarity simulate tomogram <template_input> <tomo_size_xyz> <exclusion_factor> <output_path> <output_prefix> [options]\n',...
        '    template_input  - Either:\n',...
        '                      - Path to single MRC file\n',...
        '                      - Path to text file listing MRC/PDB pairs (alternating lines):\n',...
        '                        Line 1: template1.mrc\n',...
        '                        Line 2: model1.pdb\n',...
        '                        Line 3: template2.mrc\n',...
        '                        Line 4: model2.cif\n',...
        '    tomo_size_xyz   - Tomogram dimensions as "nX,nY,nZ"\n',...
        '    exclusion_factor - Particle exclusion radius multiplier (>=1.0)\n',...
        '    output_path     - Output directory (must exist)\n',...
        '    output_prefix   - Output file prefix\n',...
        '    Options: max_particles, gpu_id, collision_mode, add_water_background, output_starfile\n\n',...
        'tlt_file    - Generate synthetic tilt geometry file\n',...
        '  Usage: emClarity simulate tlt_file <tomogram_path> <defocus_angstrom> [options]\n',...
        '    tomogram_path    - Path to tomogram MRC file\n',...
        '    defocus_angstrom - Mean defocus in Angstroms (positive = underfocus)\n',...
        '    Options: tilt_range, tilt_step, dose_per_image, defocus_std_angstrom, Cs_mm, voltage_kev\n\n',...
        'projections - Generate tilt series from tomogram\n',...
        '  Usage: emClarity simulate projections <tomogram_path> <tiltfile_path> <slab_thickness_angstrom> [options]\n',...
        '    tomogram_path          - Path to synthetic tomogram\n',...
        '    tiltfile_path          - Path to _ctf.tlt file\n',...
        '    slab_thickness_angstrom - Slab thickness for wave propagation\n',...
        '    Options: gpu_id, dose_scale, st_suffix, cleanup_tomos\n\n',...
        'project     - Set up complete emClarity project from synthetic data\n',...
        '  Usage: emClarity simulate project <project_path> <synthetic_data_path> <particle_radius> <particle_mass> [options]\n',...
        '    project_path        - Full path to new project directory\n',...
        '    synthetic_data_path - Path containing synthetic data files\n',...
        '    particle_radius     - Particle radius in Angstroms\n',...
        '    particle_mass       - Particle mass in Megadaltons\n',...
        '    Options: dose_scale, gpu, st_suffix, nGPUs, nCpuCores, symmetry\n\n',...
        'Examples:\n',...
        '  emClarity simulate tomogram /data/template.mrc 512,512,256 1.5 /output synthetic_001\n',...
        '  emClarity simulate tomogram /data/templates.txt 512,512,256 1.5 /output synthetic_001\n',...
        '  emClarity simulate tlt_file /output/synthetic_001.mrc 15000\n',...
        '  emClarity simulate projections /output/synthetic_001.mrc /output/synthetic_001_ctf.tlt 5\n',...
        '  emClarity simulate project /projects/synthetic /output 80 50 symmetry C12\n']);
    else
      if length(varargin) < 2
        error('simulate requires a subcommand: tomogram, tlt_file, projections, or project');
      end

      switch varargin{2}
        case 'tomogram'
          % Required: simulate tomogram template_input tomo_size exclusion output_path output_prefix
          if length(varargin) < 7
            error('simulate tomogram requires: <template_input> <tomo_size_xyz> <exclusion_factor> <output_path> <output_prefix>');
          end
          % Parse template input - can be single MRC or text file with MRC/PDB pairs
          template_input_path = varargin{3};
          if ~exist(template_input_path, 'file')
            error('Template input file not found: %s', template_input_path);
          end
          template_inputs = parse_simulate_template_input(template_input_path);
          % Validate output directory exists
          if ~isfolder(varargin{6})
            error('Output directory does not exist: %s', varargin{6});
          end
          % Parse tomo_size from "nX,nY,nZ" string
          tomo_size = str2double(strsplit(varargin{4}, ','));
          if length(tomo_size) ~= 3 || any(isnan(tomo_size))
            error('tomo_size_xyz must be three comma-separated integers (e.g., "512,512,256")');
          end
          % Collect optional name-value pairs
          opts = parse_simulate_options(varargin(8:end));
          EMC_syntheticTomogram(template_inputs, tomo_size, ...
                                str2double(varargin{5}), varargin{6}, varargin{7}, opts{:});

        case 'tlt_file'
          % Required: simulate tlt_file tomogram_path defocus_angstrom
          if length(varargin) < 4
            error('simulate tlt_file requires: <tomogram_path> <defocus_angstrom>');
          end
          % Validate tomogram exists
          if ~exist(varargin{3}, 'file')
            error('Tomogram file not found: %s', varargin{3});
          end
          opts = parse_simulate_options(varargin(5:end));
          EMC_generate_synthetic_tltFile(varargin{3}, str2double(varargin{4}), opts{:});

        case 'projections'
          % Required: simulate projections tomogram_path tiltfile_path slab_thickness
          if length(varargin) < 5
            error('simulate projections requires: <tomogram_path> <tiltfile_path> <slab_thickness_angstrom>');
          end
          % Validate files exist
          if ~exist(varargin{3}, 'file')
            error('Tomogram file not found: %s', varargin{3});
          end
          if ~exist(varargin{4}, 'file')
            error('Tilt file not found: %s', varargin{4});
          end
          opts = parse_simulate_options(varargin(6:end));
          EMC_generate_projections(varargin{3}, varargin{4}, ...
                                    str2double(varargin{5}), opts{:});

        case 'project'
          % Required: simulate project project_path data_path particle_radius particle_mass
          if length(varargin) < 6
            error('simulate project requires: <project_path> <synthetic_data_path> <particle_radius> <particle_mass>');
          end
          % Validate project path does not exist
          if isfolder(varargin{3})
            error('Project directory already exists: %s', varargin{3});
          end
          % Validate data path exists
          if ~isfolder(varargin{4})
            error('Synthetic data directory not found: %s', varargin{4});
          end
          opts = parse_simulate_options(varargin(7:end));
          EMC_setup_synthetic_project(varargin{3}, varargin{4}, ...
                                       str2double(varargin{5}), str2double(varargin{6}), opts{:});

        otherwise
          error('simulate operations are: tomogram, tlt_file, projections, project');
      end
    end
  case 'tomoCPR'
    fprintf('In tomoCPR the MCR is %s\n',getenv('MCR_CACHE_ROOT'));

    if emcProgramHelp || ...
        ( length(varargin) < 4 || length(varargin) > 5 )
      fprintf(['\nUsage: emClarity tomoCPR param.m cycle_number stage_of_alignment [start_tilt]\n\n',...
        'Tomogram Constrained Projection Refinement for improving tilt-series alignment.\n\n',...
        'Arguments:\n',...
        '  param.m            - Parameter file for the project\n',...
        '  cycle_number       - Processing cycle number\n',...
        '  stage_of_alignment - Geometry metadata stage to use:\n',...
        '    Avg            - Post averaging\n',...
        '    RawAlignment   - Post subtomogram alignment\n',...
        '    Cluster_cls    - Post classification\n',...
        '  start_tilt         - [Optional] Starting tilt number for debugging\n\n',...
        'Function: Refines tilt-series alignment using high-resolution particle\n',...
        'positions as constraints to improve tomogram reconstruction quality.\n\n',...
        'Examples:\n',...
        '  emClarity tomoCPR param.m 2 RawAlignment\n',...
        '  emClarity tomoCPR param.m 3 Avg 5\n']);
    else
      emC_testParse(varargin{2});
      if length(varargin) == 5
        tiltStart = EMC_str2double(varargin{4});
      else
        tiltStart = 1;
      end
      % Check that the stage of alignment is valid
      if ~ismember(varargin{4},{'Avg','RawAlignment','Cluster_cls'})
        error('Stage of alignment must be one of Avg, RawAlignment, or Cluster_cls');
      end
      BH_synthetic_mapBack(varargin{2}, varargin{3}, varargin{4},tiltStart);
    end
  case 'geometry'
    if emcProgramHelp || ...
        length(varargin) ~= 7
      fprintf(['\nUsage: emClarity geometry param.m cycle stage operation vectOP halfset\n\n',...
        'Edit or analyze experimental geometry metadata.\n\n',...
        'Arguments:\n',...
        '  param.m   - Parameter file\n',...
        '  cycle     - Cycle number\n',...
        '  stage     - Stage of alignment (TiltAlignment, RawAlignment, Cluster_cls)\n',...
        '  operation - Operation to perform (see below)\n',...
        '  vectOP    - Operation-specific input (file/vector/string)\n',...
        '  halfset   - Half-set selection (STD, EVE, ODD)\n\n',...
        'Operations:\n',...
        '  Metadata Operations:\n',...
        '    SwitchCurrentCycle, UpdateTilts, WriteCsv\n',...
        '  Particle Operations:\n',...
        '    RemoveClasses, RemoveFraction, RemoveIgnoredParticles\n',...
        '  Geometry Operations:\n',...
        '    ShiftAll, ShiftBin, RandomizeEulers\n',...
        '  Tomogram Operations:\n',...
        '    ListTomos, RemoveTomos, ListPercentiles\n',...
        '  Branch Operations:\n',...
        '    AssignClassToBranch   - Split classes into branch files\n',...
        '    AssignClassFromBranch - Create mapping files from branches\n',...
        '    AssignAndMergeToBranch - Merge specific branch back\n',...
        '    AssignAndMergeAll     - Merge multiple branches (vectOP: ''1,2:6,9'')\n\n',...
        'Examples:\n',...
        '  emClarity geometry param.m 0 RawAlignment RemoveFraction 0.15 STD\n',...
        '  emClarity geometry param.m 5 Cluster_cls AssignAndMergeAll ''1,2:6,9'' STD\n']);
    else
      emC_testParse(varargin{2});
      BH_geometryAnalysis(varargin{2}, varargin{3},varargin{4}, ...
        varargin{5}, varargin{6},varargin{7});
    end
    
    
  case 'templateSearch'
    if emcProgramHelp || ...
        ~ismember(length(varargin),[7,8])
      fprintf(['\nUsage: emClarity templateSearch param.m tomo_name tomo_idx template_name symmetry gpu_idx [threshold]\n\n',...
        'Perform template matching for particle picking in tomograms.\n\n',...
        'Arguments:\n',...
        '  param.m       - Parameter file for the project\n',...
        '  tomo_name     - Base name of tomogram to search\n',...
        '  tomo_idx      - Index/number of tomogram in dataset\n',...
        '  template_name - Reference volume file for template matching\n',...
        '  symmetry      - Symmetry group (e.g., C1, C4, D2, etc.)\n',...
        '  gpu_idx       - GPU device index to use for computation\n',...
        '  threshold     - [Optional] Cross-correlation threshold override\n\n',...
        'Output: Creates convolution maps in ./convmap/ directory\n\n',...
        'Examples:\n',...
        '  emClarity templateSearch param.m tomo01 1 ref.mrc C1 0\n',...
        '  emClarity templateSearch param.m tomo01 1 ref.mrc C4 0 0.15\n']);
    else
      wedgeType = 2;
      
      switch length(varargin)
        case 7
          
          if (useV1)
            BH_templateSearch3d( varargin{2}, varargin{3},varargin{4}, ...
              varargin{5}, varargin{6},wedgeType,varargin{7});
          else
            BH_templateSearch3d_2( varargin{2}, varargin{3},varargin{4}, ...
              varargin{5}, varargin{6},wedgeType,varargin{7});
          end
          
        case 8
          if (useV1)
            
            BH_templateSearch3d( varargin{2}, varargin{3},varargin{4}, ...
              varargin{5}, varargin{6},wedgeType, ...
              varargin{7},varargin{8});
          else
            BH_templateSearch3d_2( varargin{2}, varargin{3},varargin{4}, ...
              varargin{5}, varargin{6},wedgeType, ...
              varargin{7},varargin{8});
          end
          
      end
      
    end
    
  case 'cleanTemplateSearch'
    if emcProgramHelp || ...
        length(varargin) ~= 5
      fprintf(['\npixelSize (Ang)\n',...
  'distance to neighbor (Ang)\n',...
        'angular deviation to neighbor (degrees)\n', ...
        'min number neighbors (one less than expected is usually good)\n']);
    else
      
      BH_geometry_Constraints(EMC_str2double(varargin{2}), '0', varargin{3}, varargin{4}, varargin{5});
      
    end
    
  case 'montage'
      if emcProgramHelp || ...
         length(varargin) ~= 7
        fprintf(['parameterfile\n',...
          'cycle #\n',...
          'stage of alignment [RawAlignment or Cluster_cls]\n', ...
          'class number\n',...
          'operation [unstack or angles to rotate volume by [ZXZ]]\n', ...
          'halfset [odd, eve, or std (combine)]\n ']);  
      else
        % FIMXE: move all this to a different file
        % FIXME: eve/odd 
        % FIXME: unstack (add counts too)
        % FIXME: set pixel size
        % Check the input arguments
        EMC_assert_string_value(varargin{7}, {'odd', 'eve', 'std'}, false);
        halfset = 0; % default is combine
        if strcmpi(varargin{7},'eve')
          halfset = 2;
        elseif strcmpi(varargin{7},'odd')
          halfset = 1;
        end
        if halfset ~= 0
          error('partial implementation only good for std right now')
        end
        operation_val = varargin{6};
        if strcmpi(operation_val,'unstack')
          operation = 'unstack';
        else
          operation = 'rotx';
          operation_val = EMC_str2double(operation_val);
          EMC_assert_numeric(operation_val, 3);
        end
          
        n_classes = EMC_str2double(varargin{5});
        EMC_assert_numeric(n_classes, 1, [0, 1000]);
        
        EMC_assert_string_value(varargin{4}, {'RawAlignment', 'Cluster_cls'}, false)
        if strcmpi(varargin{4},'RawAlignment')
          prfx = 'Ref';
        else
          prfx = 'Cls';
        end
        cycle = EMC_str2double(varargin{3});
        EMC_assert_numeric(cycle, 1, [0, 1000]);
        
        % Read in the parameter file and subTomoMeta
        cycleNumber = sprintf('cycle%0.3u', cycle);
        % Load using wrapper
        subTomoMeta = BH_loadSubTomoMeta(emc.('subTomoMeta'), emc.('metadata_format'));
        emc = BH_parseParameterFile(varargin{2});
        % Make sure the cycle has been run
        if ~isfield(subTomoMeta, cycleNumber)
          error('Cycle %s has not been run yet', cycleNumber);
        end
        % Make sure the class locations information is present
        if (halfset == 0 || halfset == 1)
          fname = sprintf('class_%d_Locations_%s_%s', n_classes, prfx, 'ODD');
          if ~isfield(subTomoMeta.(cycleNumber),fname)
            error('Class locations (%s) for odd half-set are not present', fname);
          end
        end
        if (halfset == 0 || halfset == 2)
          fname = sprintf('class_%d_Locations_%s_%s', n_classes, prfx, 'EVE');
          if ~isfield(subTomoMeta.(cycleNumber),fname)
            error('Class locations (%s) for even half-set are not present', fname);
          end
        end
        % Eve/Odd should always have the same size windows, grab the first
        % Field is a cell, 1 file names of the references, 2 locations in the image (6 indices), 3 number added to the averages.
        window_size = subTomoMeta.(cycleNumber).(fname){2}{1}(2:2:end);
        odd_stack = [];
        eve_stack = [];
        if (halfset == 0 || halfset == 1)
          fname = sprintf('class_%d_Locations_%s_%s', n_classes, prfx, 'ODD');
          odd_stack = BH_unStackMontage4d(1:length(subTomoMeta.(cycleNumber).(fname){2}), ...
                                          subTomoMeta.(cycleNumber).(fname){1}, ...
                                          subTomoMeta.(cycleNumber).(fname){2}, ...
                                          window_size);
        end
        if (halfset == 0 || halfset == 2)
          fname = sprintf('class_%d_Locations_%s_%s', n_classes, prfx, 'EVE');
          eve_stack = BH_unStackMontage4d(1:length(subTomoMeta.(cycleNumber).(fname){2}), ...
                                          subTomoMeta.(cycleNumber).(fname){1}, ...
                                          subTomoMeta.(cycleNumber).(fname){2}, ...
                                          window_size);
        end
        if strcmpi(operation,'unstack')
          error('not setup yet')
        elseif strcmpi(operation,'rotx')
          if (halfset == 0 || halfset == 1)
            for i = 1:length(odd_stack)
              [~,img] = interpolator(gpuArray(odd_stack{i}),operation_val,[0,0,0], 'Bah' , 'forward', 'C1', false);
              odd_stack{i} = gather(img);
            end
          end
          if (halfset == 0 || halfset == 2)
            for i = 1:length(eve_stack)
              [~,img] = interpolator(gpuArray(eve_stack{i}),operation_val,[0,0,0], 'Bah' , 'forward', 'C1', false);
              eve_stack{i} = gather(img);
            end
          end
          % Combine them if we want to
          switch halfset
            case 0
              % Combine the two half-sets
              for i = 1:length(odd_stack)
                odd_stack{i} = odd_stack{i} + eve_stack{i};
                check_vals = ~isfinite(odd_stack{i}(:));
                odd_stack{i}(check_vals) = randn(size(odd_stack{i}(check_vals)));
              end
              montOUT = BH_montage4d(odd_stack,'');
              fname = strjoin(strsplit(subTomoMeta.(cycleNumber).(sprintf('class_%d_Locations_%s_%s',n_classes, prfx,'ODD')){1},'_ODD.mrc'),sprintf('_rot_%2.2f_%2.2f_%2.2f_STD_rotx.mrc',operation_val(1),operation_val(2),operation_val(3)));
              % TODO pixels size 
              SAVE_IMG(montOUT, fname); %,pixelSize);
              
            case 1
              % Save the odd half-set
              for i = 1:length(odd_stack)
                odd_stack{i} = odd_stack{i};
              end
            case 2
              % Save the even half-set
              for i = 1:length(odd_stack)
                eve_stack{i} = eve_stack{i};
              end
            otherwise
              error('halfset must be 0, 1, or 2')
          end
          % Save the stack
        end
      end
    
  case 'reconstruct'
    if emcProgramHelp || ...
        length(varargin) ~= 6 && length(varargin) ~= 7
      fprintf(['parameterfile\n',...
        'cycle #\n',...
        'output prefix\n', ...
        'symmetry (C1)\n',...
        'max exposure (e/A^2)\n', ...
        'classIDX']);
    else
      if (length(varargin) == 7)
        BH_to_cisTEM_mapBack(varargin{2},varargin{3},varargin{4},varargin{5},varargin{6}, varargin{7});
      else
        BH_to_cisTEM_mapBack(varargin{2},varargin{3},varargin{4},varargin{5},varargin{6}, "-1");
      end
    end
  otherwise
    error('command --%s-- not recognized. Try "help" for a list.', varargin{1})
end

timeFinish = datetime();
fprintf('\n\t\t***************************************\n\n');
fprintf('run ending on %s\n', timeFinish);
fprintf('\n\n')
fprintf('\t\t***************************************\n\n');


diary off
if (cudaStart)
  setenv('CUDA_VISIBLE_DEVICES',cudaStart);
end
end



function [ emc  ] = emC_testParse( paramTest )
% Try to parse the parameter file make sure it's okay.
%
% Add some actual error handling here to help trouble shoot.
% try
  emc = BH_parseParameterFile( paramTest );
  
  
  
  
  
  
  % These are for making shape based masks. I think the problem is likely
  % dependent on the current resolution of the sub-tomogram, and that a
  % single set of values will not work for everything.
  
  % Note that most global variables have been moved to the parameter file
  % Only variables used by functions without parameter access remain as globals

  %%%%%%% Variables still needed for BH_mask3d.m and EMC_maskReference.m %%%%%%%
  global emc_debug_print;
  try
    emc_debug_print = emc.('debug_print');
  catch
    emc_debug_print = false;
  end

  global bh_global_binary_mask_low_pass;
  try
    bh_global_binary_mask_low_pass = emc.('setMaskLowPass');
  catch
    % These seem to be okay for higher-resolution data (EMPIAR ribo sets)
    bh_global_binary_mask_low_pass = 14;
  end

  global bh_global_binary_mask_threshold;
  try
    bh_global_binary_mask_threshold = emc.('setMaskThreshold');
  catch
    bh_global_binary_mask_threshold = 2.5;
  end

  global bh_global_vol_est_scaling;
  try
    bh_global_vol_est_scaling = emc.('setParticleVolumeScaling');
  catch
    % The low pass version of the map used for the estimate overestimates
    % the molecular volume at the hydration radius of the underlying atoms.
    bh_global_vol_est_scaling = 1.0;
  end
  %%%%%%%%%%%%%%%%%%%%%%%%%%%%

  %%%%%%% MOVED TO PARAMETERS - NOW HANDLED IN BH_parseParameterFile %%%%%%%
  % The following variables have been moved to the parameter file:
  % - bh_global_binary_pcaMask_threshold -> emc.pca_mask_threshold
  % - bh_global_turn_on_phase_plate -> emc.phase_plate_mode
  % - bh_global_do_2d_fourier_interp -> emc.use_fourier_interp
  % - bh_global_do_profile -> emc.enable_profiling
  % - bh_global_save_tomoCPR_diagnostics -> emc.save_tomocpr_diagnostics
  % - bh_global_nCol, bh_global_MTF, bh_global_fast_scratch_disk,
  %   bh_global_ram_disk, bh_global_imodProjectionShifts,
  %   bh_global_kFactorScaling (all removed - never used)
  %%%%%%%%%%%%%%%%%%%%%%%%%%%
% catch
%   error('error parsing parameter file %s\n', paramTest)
% end



end

function [] = select_gpus(nGPUs_wanted,nGPUs_visible,cmdIN)

% I don't like this string parsing with system tools
[~,uuidList] = system('nvidia-smi --list-gpus | awk -F "UUID: " ''{print $2}'' | awk -F ")" ''{print $1}''');
uuidlist = strsplit(uuidList);
nGPUs_total = length(uuidlist)-1;
memList = zeros(nGPUs_total,2);
memList(:,1) = 1:nGPUs_total;
for iGPU = 1:nGPUs_total
  memCMD = sprintf('nvidia-smi --id=%s --query-gpu=memory.total --format=csv,noheader,nounits',uuidlist{iGPU});
  [~,memString] = system(memCMD);
  memList(iGPU,2) = EMC_str2double(memString);
  fprintf('found gpu with %f Mib memory\n',memList(iGPU,2));
end

memList = sortrows(memList,-2);
devList = '';
for iGPU = 1:nGPUs_total
  if iGPU <= nGPUs_wanted
    devList = strcat(devList,uuidlist{memList(iGPU,1)});
    if iGPU < nGPUs_wanted
      devList = strcat(devList,',');
    elseif iGPU == nGPUs_wanted && nGPUs_total > nGPUs_wanted
      % start list of uuids to explicitly block
      devList = strcat(devList,',-1,');
    end
  elseif iGPU > nGPUs_wanted && nGPUs_total >=nGPUs_wanted
    devList =  strcat(devList,uuidlist{memList(iGPU,1)});
    if iGPU < nGPUs_total
      devList = strcat(devList,',');
    end
  end
end

setenv('CUDA_VISIBLE_DEVICES',char(devList));

fprintf('\n\n\t\tPlease add the following line to your emClarity run script\n\nexport CUDA_VISIBLE_DEVICES=%s\n\n',devList);

exit

end % end select gpus

function print_experimental_options

  % FIXME: make these match the corrections to deprecated options in parseParemeterFile and extend to include 
  % the (many) that are currently ommitted.
fprintf('\n\n\tExperimental Options: use at your own RISK\n');
fprintf('(\t\tOr better yet, check with ben!\t\t)\n');
fprintf('\nIf you do use/change any of these, please mention in your methods and EMDB entry!\n');
fprintf('\n\n----------------------------------\n\n');
fprintf('\nscale_calc_size\toversampling of vol for xcorr. Def:\t1.5\n');
fprintf('\npaddedSize\tpadded size of tiles in ctf estimateion\n');

fprintf('\nflgFscShapeMask\t default 1\n');
fprintf('\nflgPcaShapeMask\t default 1\n');

fprintf('\nflgQualityWeight\t Downweight high-freq of low scoring sub-tomos. Def:\t4\n');
fprintf('\nlimit_to_one_core\t For OOM issues in averaging. Boolean Def:\t0\n');
fprintf('\move_reference_by_com\tShift reference to center of mass. Boolean Def:\t1\n');
fprintf('\nconserveDiskSpace\n');
fprintf('\nPca_distMeasure\tMeasure for difference. euclidean, cityblock, correlation, cosine Def:\t sqeuclidean\n');
fprintf('\nPca_nReplicates\tThe number of times Kmeans is intialized. Def:\t 128\n');
fprintf('\nflgSymmetrizeSubTomos\tApply symmetry to subtomos in alignment.\nCurrently not worse, not better, but much slower.\n');

fprintf('\ndeltaZTolerance\tallowed defocus variance in ctf estimation:Def:\t100e-9\n');
fprintf('\nzShift\tselect tiles with a defocus offset. Determine tilt gradient.\n\n');


end % end of print experimental options

function opts = parse_simulate_options(args)
% Parse name-value pairs from command line for simulate commands
%
% Converts string arguments to appropriate types (numbers, vectors, strings).
% Handles comma-separated values as numeric vectors.
%
% Input:
%   args - Cell array of command-line arguments (name-value pairs)
%
% Output:
%   opts - Cell array suitable for passing to functions as varargin
%
% Example:
%   parse_simulate_options({'max_particles', '500', 'tilt_range', '-60,60'})
%   Returns: {'max_particles', 500, 'tilt_range', [-60, 60]}

opts = {};
i = 1;
while i <= length(args)
  param_name = args{i};
  if i+1 <= length(args)
    param_value = args{i+1};
    % Try to convert to number if it looks like one
    num_val = str2double(param_value);
    if ~isnan(num_val)
      opts{end+1} = param_name;
      opts{end+1} = num_val;
    else
      % Check for comma-separated numeric vector
      if contains(param_value, ',')
        vec_vals = str2double(strsplit(param_value, ','));
        if ~any(isnan(vec_vals))
          opts{end+1} = param_name;
          opts{end+1} = vec_vals;
        else
          % Keep as string if not all numeric
          opts{end+1} = param_name;
          opts{end+1} = param_value;
        end
      else
        % Keep as string
        opts{end+1} = param_name;
        opts{end+1} = param_value;
      end
    end
    i = i + 2;
  else
    error('Missing value for parameter: %s', param_name);
  end
end
end % end of parse_simulate_options

function template_inputs = parse_simulate_template_input(input_path)
% Parse template input file for simulate tomogram command
%
% Determines if input is:
%   - Single MRC file -> returns the path string
%   - Text file with MRC/PDB pairs -> returns cell array of {mrc, pdb} pairs
%
% Text file format (alternating lines):
%   Line 1: path/to/template1.mrc
%   Line 2: path/to/model1.pdb
%   Line 3: path/to/template2.mrc
%   Line 4: path/to/model2.cif
%   ...
%
% Input:
%   input_path - Path to single MRC file or text file with MRC/PDB pairs
%
% Output:
%   template_inputs - Either string (single MRC) or cell array of {mrc, pdb} pairs

[~, ~, ext] = fileparts(input_path);

% Check if it's a single MRC file
if strcmpi(ext, '.mrc')
  template_inputs = input_path;
  return;
end

% Otherwise, treat as text file with MRC/PDB pairs
fid = fopen(input_path, 'r');
if fid == -1
  error('Cannot open template input file: %s', input_path);
end
cleanup = onCleanup(@() fclose(fid));

lines = {};
while ~feof(fid)
  line = strtrim(fgetl(fid));
  if ~isempty(line) && ~startsWith(line, '#')  % Skip empty lines and comments
    lines{end+1} = line;
  end
end

n_lines = length(lines);
if n_lines == 0
  error('Template input file is empty: %s', input_path);
end

if mod(n_lines, 2) ~= 0
  error('Template input file must have even number of lines (MRC/PDB pairs): %s has %d lines', input_path, n_lines);
end

% Build cell array of {mrc, pdb} pairs
n_pairs = n_lines / 2;
template_inputs = cell(1, n_pairs);
for i = 1:n_pairs
  mrc_path = lines{2*i - 1};
  pdb_path = lines{2*i};

  % Validate files exist
  if ~exist(mrc_path, 'file')
    error('Template MRC file not found: %s', mrc_path);
  end
  if ~exist(pdb_path, 'file')
    error('Template PDB/CIF file not found: %s', pdb_path);
  end

  template_inputs{i} = {mrc_path, pdb_path};
end

fprintf('Parsed %d MRC/PDB template pair(s) from %s\n', n_pairs, input_path);
end % end of parse_simulate_template_input

