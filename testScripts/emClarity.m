function [ varargout ] = emClarity( varargin )
%Wrapper to run BH_subtomo programs.
%   Detailed explanation goes here

% Disable warnings

warning off
cudaStart='';
% FIXME: This only applies to ctf estimate, and it looks like there is no version 2 !?
useV2 = false;
useV1 = false;

cmdIN = sprintf('emClarity %s ',varargin{1});

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
fprintf('emClarity version %s\n', varargin{1});
fprintf('run starting on %s\n', timeStart);
fprintf('cmd ');
for iArg = 2:length(varargin)
  cmdIN = [cmdIN sprintf('%s ',varargin{iArg})];
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
      elseif nArgs < 3
        emcProgramHelp = strcmpi(varargin{2},'help') || strcmp(varargin{2},'h');
      elseif nArgs < 4
        emcProgramHelp = strcmpi(varargin{3},'help') || strcmp(varargin{3},'h');
      end
    end
  end
else
  myErr = sprintf('\n\n\tRun with help for a list of functions\n\n');
  error(myErr);
  %   checkHelp = 0;
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
    case 'benchmark'
      % nothing to parse
      multiGPUs= 0;
    case 'removeNeighbors'
      % nothing to parse
      multiGPUs = 0;
    case 'combineProjects'
      % nothing to parse
      multiGPUs = 0;
    case 'cleanTemplateSearch'
      multiGPUs = 0;
    case 'segment'
      multiGPUs = 0;
    case 'getActiveTilts'
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
    fprintf(['\nAvailable commands (case sensitive):\n\n',...
      '\nhelp - this message\n',...
      '\n\t\t for more details, emClarity <program> help\n',...
      '\ncheck - system check for dependencies\n',...
      '\nsegment - define subregions to reconstruct\n',...
      '\ngetActiveTilts - get the number of active tilt-series\n',...
      '\ninit - create a new project from template matching results.\n',...
  '\nautoAlign - align tilt-series\n',...
      '\navg - average subtomograms\n',...
      '\nfsc - calculate the fsc\n',...
      '\nmask - create a mask\n',...
      '\nbenchmark - run a benchmark\n',...
      '\ncalcWeights - calculate the weights for a given cycle\n',...
      '\nalignRaw - align one or more references against individual subtomograms.\n',...
      '\npca - reduce dimensionality prior to clustering, possibly on smaller subset of data.\n',...
      '\ncluster - use one of a number of approaches to sort populations.\n',...
  '\nskip - after averaging classes & possible removing some, skip to next cycle.\n',...
      '\ngeometry - edit or analyze the experimental metadata.\n',...
      '\ncombineProjects - combine two or more projects together', ...
      '\nctf - estimate, correct, or refine the CTF.\n',...
      '\ntomoCPR - tomogram constrained projection refinement\n',...
      '\ntemplateSearch - template matching/ global search\n',...
      '\ncleanTemplateSearch - clean search results based on neighbor constraints\n',...
      '\nrescale - change the mag on a volume\n',...
      '\nreconstruct - reconstruct a volume from a set of subtomograms\n',...
      '\nremoveDuplicates - remove subtomos that have migrated to the same position\n',...
      '\nexperimental - experimental options\n',...
      '\nmontage - unstack and/or rotate the elements of a montage about x\n',...
      '\nremoveNeighbors - clean templateSearch results based on lattice constraints\n']);
    
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
      load(sprintf('%s.mat', emc.('subTomoMeta')), 'subTomoMeta');
      [tiltNameList, nTiltSeries] = BH_returnIncludedTilts( subTomoMeta.mapBackGeometry );
      fprintf('%d\n',nTiltSeries);
      return 
    end
  case 'init'
  if emcProgramHelp || ...
    (length(varargin) < 2 || length(varargin) > 5)
      fprintf(['\nUsage: emClarity init param.m [tomoCpr iter, for continuing after second globalsearch]\n']);
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
      fprintf(['\nUsage: emClarity autoAlign param.m stackName tiltFile tilt-axis Rotation\n']);
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
    (~ismember(length(varargin),[5,8,9]))
      fprintf(['\nFor geometric mask:\n', ...
        'fileNameOUT.mrc, pixelSize (Ang), Shape (sphere,cylinder,rectangle), Size/radius/center in pixels: [nX,nY,nZ], [rX,rY,rZ], [cX,cY,cZ], optional: "2d"',...
        '\n\nFor a shape based mask\n', ...
        'fileNameIN.mrc,fileNameOUT.mrc, pixelSize (Ang)\n']);
      
        
    else
      switch length(varargin)
        case 5
          maskVol = OPEN_IMG('single', varargin{3});
          pixelSize = EMC_str2double(varargin{5});
          maskVol = BH_mask3d(maskVol,EMC_str2double(varargin{5}),'','');
          SAVE_IMG(MRCImage(gather(maskVol)),varargin{4},pixelSize);
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
  case 'benchmark'
    if emcProgramHelp || ...
        length(varargin) ~= 4
      fprintf(['\nUsage: emClarity benchmark fileNameOut fastScratchDisk nWorkers\n']);
    else
      BH_benchmark(varargin{2},varargin{3},varargin{4});
    end
  case 'calcWeights'
    if emcProgramHelp || ...
        length(varargin) ~= 6
      fprintf(['\nUsage: emClarity calcWeights param.m cycle prefixOUT symmetry [gpuIDX, tiltStart, tiltStop]\n']);
    else
      
      BH_weightMask_dpRUN(varargin{2},varargin{3},varargin{4},varargin{5},varargin{6});
    end
  case 'avg'
    if emcProgramHelp || ...
        length(varargin) ~= 4
      fprintf(['\nUsage: emClarity avg\n',...
        'param.m\n',...
        'cycle number\n',...
        'stage of alignment\n',...
        '  raw (post raw alignment)\n',...
        '  cluster_cls (post classification)\n']);
    else
      emC_testParse(varargin{2});
      BH_average3d(varargin{2}, varargin{3}, varargin{4});
    end
  case 'fsc'
    if emcProgramHelp || ...
        (length(varargin) ~= 4 &&  length(varargin) ~= 6)
      fprintf(['\nUsage: emClarity fsc\n',...
        'param.m\n',...
        'cycle number\n',...
        'stage of alignment\n',...
        '  raw (post raw alignment)\n',...
        '  cluster_cls (post classification)\n']);
    elseif length(varargin) == 4
      emC_testParse(varargin{2});
      BH_fscGold_class(varargin{2}, varargin{3}, varargin{4});
    else
      BH_fscGold_class(varargin{2}, varargin{3}, varargin{4},varargin{5},varargin{6});
    end
  case 'alignRaw'
    if emcProgramHelp || ...
        (length(varargin) ~= 3 && length(varargin) ~= 4)
      fprintf(['\nUsage: emClarity alignRaw\n',...
        'param.m\n',...
        'cycle number\n',...
        '[experimental option 1/2/3, 1 - abs(ccc),2 - weighted,3 -abs(weighted)]']);
    else
      emC_testParse(varargin{2});
      if length(varargin) == 3
        BH_alignRaw3d_v2(varargin{2}, varargin{3});
      else
        % Switching to v2 always, 1.5.0.9 20200520
        BH_alignRaw3d_v2(varargin{2},varargin{3}, varargin{4});
      end
    end
    
  case 'alignRef'
    if emcProgramHelp || ...
        length(varargin) ~= 3
      fprintf(['\nparam.m\n',...
        'cycle number\n',...
        'stage of alignment\n']);
    else
      emC_testParse(varargin{2});
      BH_alignReferences3d(varargin{2}, varargin{3});
    end
  case 'alignCls'
    if emcProgramHelp || ...
        length(varargin) ~= 3
      fprintf(['\nparam.m\n',...
        'cycle number\n',...
        'stage of alignment\n']);
    else
      emC_testParse(varargin{2});
      BH_alignClassRotAvg3d(varargin{2}, varargin{3});
    end

  case 'pca'
    if emcProgramHelp || ...
        length(varargin) ~= 4  && length(varargin) ~= 5
      fprintf(['\nparam.m\n',...
        'cycle number\n',...
        'randomSubset\n',...
       'use focused mask\n',...
       '  1 from standard devation\n',...
       '  2 from variance\n',...
       '  3 user supplied (not recommended)\n']);
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
          % re-run on full or randomsubset now using variance or stddev mask
          BH_pcaPub(varargin{2}, varargin{3}, sprintf('%d',-1.*maskVal))
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
      fprintf(['\nestimate\n',...
        '  param.m tiltBaseName\n',...
        '\nrefine\n',...
        '  param.m tiltBaseName gpuIDX\n',...
        '\nupdate\n',...
        '  param.m tiltBaseName (full,refine,update)\n',...
        '\ncorrect\n',...
  '  param.m precision      usable-area nWorkers\n',...
        '         (single,double) [nx,ny,nz] \n',...
        '\n3d\n',...
        '  param.m [/local/Scratch]\n']);
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
  case 'tomoCPR'
    fprintf('In tomoCPR the MCR is %s\n',getenv('MCR_CACHE_ROOT'));
    
    if emcProgramHelp || ...
        ( length(varargin) < 4 || length(varargin) > 5 )
      fprintf(['\nparam.m\n',...
        'cycle number\n',...
  'stage of alignment [most recent stage finished for geometry metadata, eg  - Avg, RawAlignment, Cluster_cls]\n',...
        '<optional debuging - nTiltStart>\n']);
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
  case 'removeDuplicates'
    if emcProgramHelp || ...
        length(varargin) ~= 3
      fprintf(['\nparam.m\n',...
        'cycle number\n',...
        ]);
    else
      emC_testParse(varargin{2});
      BH_removeDuplicates(varargin{2}, varargin{3} );
    end
  case 'geometry'
    if emcProgramHelp || ...
        length(varargin) ~= 7
      fprintf(['\nparam.m\n',...
        'cycle number\n',...
        'stage of alignment\n',...
        'operation []\n',...
        '  SwitchCurrentCycle, UpdateTilts, WriteCsv, RemoveClasses,\n'...
        '  ShiftAll, ShiftBin, ListTomos, RemoveTomos,\n',...
        '  ListPercentiles, RemoveFraction, RemoveIgnoredParticles, RandomizeEulers\n',...
        'vectOP [0,0,0]\n',...
        'STD, EVE, ODD\n']);
    else
      emC_testParse(varargin{2});
      BH_geometryAnalysis(varargin{2}, varargin{3},varargin{4}, ...
        varargin{5}, varargin{6},varargin{7});
    end
  case 'combineProjects'
    BH_combineProjects(varargin{1},varargin(2:end));
    
    
  case 'templateSearch'
    if emcProgramHelp || ...
        ~ismember(length(varargin),[7,8])
      fprintf(['\nparam.m\n',...
        'tomoName\n',...
        'tomoIdx\n', ...
        'template name\n',...
        'symmetry\n',...
        '[threshold override]\n',...
        'gpuIDX.\n']);
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
        load(sprintf('%s.mat', emc.('subTomoMeta')), 'subTomoMeta');
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
  
  % Note that these must also be declared in the relevant functions
  
  global emc_debug_print;
  try
    emc_debug_print = emc.('debugPrint');
  catch
    emc_debug_print = false;
  end

  %%%%%%% BH_mask3d.m %%%%%%%
  global bh_global_binary_mask_low_pass;
  global bh_global_binary_mask_threshold;
  %%%%%%%%%%%%%%%%%%%%%%%%%%%%
  
  %%%%%%% BH_pcaPub.m %%%%%%%
  global bh_global_binary_pcaMask_threshold;
  %%%%%%%%%%%%%%%%%%%%%%%%%%%
  
  %%%%%%% Anything that reads geometry. This way if size changes, its okay.
  %%%%%%% Needed only for tracking multiple copies of a single particle.
  %%%%%%% (Currently not used)
  global bh_global_nCol
  bh_global_nCol = 26;
  %%%%%%%
  
  %%%%%% BH_mask3d - affects then the FSC calc
  global bh_global_vol_est_scaling;
  global bh_global_MTF;
  
  %%%%%
  global bh_global_fast_scratch_disk;
  global bh_global_ram_disk;
  
  %%%%%%% BH_ctfCorrect_3d
  %%%%%%% Wiener filter and cut off past this point
  global bh_global_turn_on_phase_plate;
  
  try
    bh_global_turn_on_phase_plate = emc.('phakePhasePlate');
  catch
    bh_global_turn_on_phase_plate = 0;
  end
  
  %%%%%%% BH_ctf_estimate, updateFFT
  %%%% Can't pad K3 images enough to avoid ghosting until mexInterp is
  %%%% ready
  global bh_global_do_2d_fourier_interp;
  try
    bh_global_do_2d_fourier_interp = emc.('useFourierInterp');
  catch
    bh_global_do_2d_fourier_interp = 1;
  end
  
  global bh_global_save_tomoCPR_diagnostics;
  try
    bh_global_save_tomoCPR_diagnostics = emc.('tomoCprDiagnostics');
  catch
    bh_global_save_tomoCPR_diagnostics = 0;
  end
  
  global bh_global_imodProjectionShifts;
  bh_global_imodProjectionShifts = [ -0.5, -0.5, 0.5 ; -0.5, -0.5, 0; 0.5,0.5,1.0 ];
  
  %%%%%%%%%%%%%%
  
  %%%%% For profiling
  global bh_global_do_profile;
  try
    bh_global_do_profile = emc.('doProfile');
  catch
    bh_global_do_profile = false;
  end
  
  
  try
    bh_global_fast_scratch_disk  = emc.('fastScratchDisk');
  catch
    bh_global_fast_scratch_disk='';
  end
  
  global emc_debug_print
  emc_debug_print = emc.('debug_print');

  try
    bh_global_ram_disk = emc.('ramDisk');
  catch
    bh_global_ram_disk = '/dev/shm';
  end
  
  [status , fileAttributes] = fileattrib(bh_global_ram_disk);
  if (status && fileAttributes.UserWrite)
    fprintf('Found and using your ramDisk\n');
  else
    fprintf('\nRan into an error trying to write to the fastScatchDisk %s\n',bh_global_ram_disk);
    fprintf('Please check that it exists and is writable status (%d) UserWrite (%d)\n', status, fileAttributes.UserWrite);
    bh_global_ram_disk = '';
  end
  
  
  try
    bh_global_binary_mask_low_pass = emc.('setMaskLowPass');
  catch
    % These seem to be okay for higher-resolution data (EMPIAR ribo sets)
    bh_global_binary_mask_low_pass = 14;
  end
  
  try
    bh_global_binary_mask_threshold = emc.('setMaskThreshold');
  catch
    bh_global_binary_mask_threshold = 2.5;
  end
  
  try
    bh_global_binary_pcaMask_threshold = emc.('setPcaMaskThreshold');
  catch
    bh_global_binary_pcaMask_threshold = 0.5;
  end
  
  global bh_global_kFactorScaling;
  try
    bh_global_kFactorScaling = emc.('kFactorScaling');
  catch
    bh_global_kFactorScaling = 1.0;
  end
  
  try
    bh_global_vol_est_scaling = emc.('setParticleVolumeScaling');
  catch
    % The low pass version of the map used for the estimate overestimates
    % the molecular volume at the hydration radius of the underlying atoms.
    % This flag will override the value I've calculated which depends on
    % the masking resolution. TODO when the map resolution is lower than
    % the masking resolution, this will again underestimate the scaling,
    % artificialy *de*pressing the FSC. Left to zero this is calculated in
    % mask_3d
    bh_global_vol_est_scaling = 0.0;
  end

  
  fprintf('nExpGlobals %2.2f maskLP, %2.2f maskThr, %2.2f pcaMaskThr\n', ...
    bh_global_binary_mask_low_pass, ...
    bh_global_binary_mask_threshold, ...
    bh_global_binary_pcaMask_threshold);
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

