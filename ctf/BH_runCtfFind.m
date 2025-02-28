function [ ] = BH_runCtfFind(stackNameBaseName, tltNameBaseName, ctfParams, tiltAngles)
%Fit the ctf to a background subtracted PS using ctffind4
%   CTF params
%     PixelSize (Ang)
%     KeV
%     CS (mm)
%     Amplitude Contrast

system('mkdir -p fixedStacks/ctf/forCtfFind');

rng('shuffle');
randPrfx = sprintf('%s_%d',tltNameBaseName,randi(1e6,[1,1]));
randPrfx_inv = sprintf('%s_inv',randPrfx);

ctfFindPath = getenv('EMC_CTFFIND');

fprintf('%s\n',ctfFindPath);% split the stack up
fullStack = OPEN_IMG('single', sprintf('%s.mrc',stackNameBaseName));
fullStack_inv = OPEN_IMG('single', sprintf('%s_inv.mrc',stackNameBaseName));
[d1,d2,d3] = size(fullStack); % FIXME d1 assumed to equal d2 Add check in saving

for iPrj = 1:d3
  SAVE_IMG(MRCImage(fullStack(:,:,iPrj)),sprintf('fixedStacks/ctf/forCtfFind/%s_%d.mrc',randPrfx,iPrj));
  SAVE_IMG(MRCImage(fullStack_inv(:,:,iPrj)),sprintf('fixedStacks/ctf/forCtfFind/%s_%d.mrc',randPrfx_inv,iPrj));
end

% % Check to make sure this hasn't alread been done
% if ~exist(sprintf('fixedStacks/ctf/%s_orig',tltNameBaseName), 'file')
system(sprintf('mv fixedStacks/ctf/%s.tlt fixedStacks/ctf/%s.tlt_orig',tltNameBaseName,tltNameBaseName));
% end

tmpTLT = load(sprintf('fixedStacks/ctf/%s.tlt_orig',tltNameBaseName));
meanDefocus = mean(abs(tmpTLT(:,15)))*10^10;
fprintf('Searching around an estimated mean defocus of %3.6f Angstrom\n');

% write the run script, this should link to a distributed version with
% special name, but for testing use the beta.
score = 0;
score_inv = 0;
for i_run = [1:2]
  if (i_run == 1)
    % regular
    using_prfx = randPrfx;
  else
    using_prfx = randPrfx_inv;
    % inverse
  end

  scriptName = sprintf('.%s.sh',using_prfx);


  fID = fopen(scriptName,'w');

  fprintf(fID,'#!/bin/bash\n\n');
  for iPrj = 1:d3 
    % I want to fit to lower resolution at higher tilts
    tltIDX = find(tiltAngles(:,1) == iPrj);
    
    % put in a line to limit number of cores, or use the threaded version
    fprintf(fID,'\n%s --amplitude-spectrum-input << eof &',ctfFindPath);
    fprintf(fID,'\nfixedStacks/ctf/forCtfFind/%s_%d.mrc\n',using_prfx,iPrj);
    fprintf(fID,'fixedStacks/ctf/forCtfFind/%s_diagnostic_%d.mrc\n',using_prfx,iPrj);
    fprintf(fID,'%f\n%f\n%f\n%f\n%d\n%f\n%f\n%d\n%d\n%d\n', ...
            ctfParams(1:4), ...
            d1, ...
            30,3*ctfParams(1)./cosd(tiltAngles(tltIDX,4)).^0.4,...
            0.75*meanDefocus,...
            1.25*meanDefocus,...
            25.0);
    fprintf(fID,'no\nno\nyes\n500.0\nno\nno\nno\neof\n\n');
  end
  fprintf(fID,'wait\n');
  fclose(fID);

  system(sprintf('chmod a=wrx %s',scriptName));

  [runFail] = system(sprintf('./%s',scriptName));

  if (runFail)
    system(sprintf('cp ./%s tmpFail',scriptName));
    system(sprintf('mv tmpFail ./%s',scriptName));
    [runFail] = system(sprintf('./%s',scriptName));
    if (runFail)
      error('Tried to run %s twice and failed\n',scriptName);
    end
  end



  % will this wait for return?

  baseName = sprintf('fixedStacks/ctf/forCtfFind/%s_diagnostic_',using_prfx);
  tmpName  = sprintf('fixedStacks/ctf/forCtfFind/%s_tmp',using_prfx);
  if (i_run == 1)
    using_tltName = sprintf('%s.tlt',tltNameBaseName);
  else
    using_tltName = sprintf('%s_inv.tlt',tltNameBaseName);
  end

  system(sprintf('newstack %s?.mrc %s??.mrc %sfull.st',baseName,baseName,baseName));
  system(sprintf('rm %s?.mrc %s??.mrc',baseName,baseName));
  % system(sprintf('rm -f %s?.mrc %s??.mrc',using_prfx,using_prfx));
  system(sprintf('rm -f %s',tmpName));

  for iPrj = 1:d3
    % 2024 Jan, finally make switch to record positive for underfocus as is used internally.
    system(sprintf('tail -n -1 %s%d.txt | awk  ''{print (($2-$3)/2)*10^-10, 3.1415926535/180.0*$4, 1*(($2+$3)/2)*10^-10, $6 }'' >> %s', baseName,iPrj,tmpName));
    
  end

  % TODO ground truth to confirm orientation of astigmatism

  system(sprintf('awk ''FNR==NR{a[FNR]=$1;b[FNR]=$2;c[FNR]=$3 ;next}{ print $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,a[$1],b[$1],$14,c[$1],$16,$17,$18,$19,$20,$21,$22,$23}'' %s fixedStacks/ctf/%s.tlt_orig > fixedStacks/ctf/%s',tmpName,tltNameBaseName,using_tltName));

  a = importdata(tmpName);
  if (i_run == 1)
    % regular
    score = mean(a(:,4));
  else
    % inverse
    score_inv = mean(a(:,4));
  end
end % loop on reg/inv

% Save the scores in
fprintf('Found an average score: %3.6f and an average inverted hand score: %3.6f for tilt %s\n',score,score_inv, tltNameBaseName);
if (score_inv > score)
  fprintf('It looks like your handedness is inverted based on tiles.\n');
end

% Clean up the input slices (the stacks are still at fixedStacks/ctf/...PS-2.mrc)
for iPrj = 1:d3
  system(sprintf('rm -f fixedStacks/ctf/forCtfFind/%s_%d.mrc',randPrfx,iPrj));
  system(sprintf('rm -f fixedStacks/ctf/forCtfFind/%s_%d.mrc',randPrfx_inv,iPrj));
end

end % function