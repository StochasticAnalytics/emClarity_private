#!/bin/bash

# emClarity compilation script
# This script compiles emClarity and creates the distribution package

# Required: Set the path to emClarity dependencies
# Download from the emC_dependencies folder on Google Drive
export emC_DEPS="/sa_shared/software/emClarity_1.6.1.0/bin/deps"

# Source directory - automatically passed to mexCompile.m via environment variable
export EMC_SOURCE_ROOT=/sa_shared/git/emClarity_private

export MATLABPATH=$EMC_SOURCE_ROOT:$MATLABPATH

# Where to install the compiled version
EMC_COMPILED_ROOT=/sa_shared/software/

# This is the version of matlab you will end up compiling with.
MATLAB_FOR_COMPILING=matlab

# This grabs the first bit of the commit hash, which then is printed in the logfile
shortHead=$(git rev-parse --short HEAD)

# The program you want to compile. Most BH_* can be compiled as standalones, but
# you probably just want the wrapper to the emClarity.m
mFile=${1}

post="_${shortHead}"

# First make sure the file exists
if [[ ! -f ${mFile} ]]; then
  echo "Could not find ${mFile}"
  exit 1
fi
# check the extension
if [[ $mFile != *.m ]]; then
  echo "Please provide a matlab file to compile"
  exit 1
fi

outName="$(basename ${mFile} .m)${post}"

# For naming. If you are compiling your own version, use something descriptive in the
# bugs line. e.g. bugs=5testingFeature
major=1
minor=8
bugs=5
nightly=0
binaryOutName="${major}_${minor}_${bugs}_${nightly}"
scriptOutName="${major}_${minor}_${bugs}_${nightly}_v23a"

EMC_VERSION=emClarity_${major}.${minor}.${bugs}.${nightly}

EMC_COMPILED_DIRNAME=${EMC_COMPILED_ROOT}/${EMC_VERSION}

# The final binary, run script and docs folder will be zipped and put in this location
# unless it is NONE then it will be left in the bin dir.
zip_location="${HOME}/tmp"
#zip_location="NONE"



# Skip MEX compilation flag - used to speed up debugging of non-CUDA compilation steps
# Generally only enabled when debugging compilation steps unrelated to the cudaMex files
skipMex=0
if [[ $skipMex -eq 0 ]]; then
  mexCompile="mexCompile ;"
else
  mexCompile=""
fi

# NOTE: warnings are disabled to ensure that failed builds are caught. Ideally they would be addressed and removed.
echo "🔨 Starting emClarity compilation..."
echo "   This will take several minutes. Filtering verbose output..."
echo ""

# Run compilation and save full output - use EMC_SOURCE_ROOT for correct paths
# Use try-catch in MATLAB to ensure we exit with error code on failure
${MATLAB_FOR_COMPILING} -nosplash -nodisplay -nojvm -r "try; cd('${EMC_SOURCE_ROOT}/testScripts'); addpath(genpath('${EMC_SOURCE_ROOT}')); ${mexCompile} mcc -w disable -m  ${mFile} -a fitInMap.py -a ../alignment/emC_autoAlign -a ../alignment/emC_findBeads -a ../metaData/BH_checkInstall -R -nodisplay -o $(basename ${mFile} .m)_${binaryOutName}; exit(0); catch ME; fprintf('ERROR: %s\n', ME.message); exit(1); end" 2>&1 | tee compilation_full.log | ./analyze_compilation.py

MATLAB_EXIT_CODE=${PIPESTATUS[0]}

if [ $MATLAB_EXIT_CODE -ne 0 ]; then
  echo "❌ Compilation failed with exit code $MATLAB_EXIT_CODE"
  echo "   Check compilation_full.log for complete output"
  exit $MATLAB_EXIT_CODE
fi

rm -f mccExcludedFiles.log
rm -f readme.txt
rm -f run_*.sh
rm -f requiredMCRProducts.txt
rm -f unresolvedSymbols.txt
rm -f includedSupportPackages.txt

if [ -f emClarity ] ; then
  mv emClarity emClarity~
fi

#Matlab (mcc) complains if ther is an underscore in the name.
#mv emClarity${binaryOutName} emClarity_${binaryOutName}

{

echo '#!/bin/bash'
echo ''
echo '# When this script is invoked, record the PID so that the EMC_tmpDir is deleted'
echo '# even in the event of a crash. (With program script added from EMC_tmpDir.sh)'
echo 'thisPID=$$'
echo ''
echo ''
echo '# Note you no longer need to modify this line inside the singularity container:'
echo 'MCR_BASH=/sa_shared/software/matlab2023/MATLAB/R2023a/runtime/glnxa64:/sa_shared/software/matlab2023/MATLAB/R2023a/bin/glnxa64:/sa_shared/software/matlab2023/MATLAB/R2023a/sys/os/glnxa64'
echo ''
echo ''
echo '#Please modify this line to point to the install for emClarity binary'
echo "export emClarity_ROOT=${EMC_COMPILED_DIRNAME}"
echo 'export LD_LIBRARY_PATH=${emClarity_ROOT}/lib:${MCR_BASH}:${LD_LIBRARY_PATH}'
echo ''

} > emClarity_${scriptOutName}

cat EMC_tmpDir.sh >> emClarity_${scriptOutName}

{
echo ''
echo '# Run an interactive MATLAB session with emClarity properly configured'
echo 'if [[ ${1} == "int" || ${1} == "interactive" ]] ; then'
echo '  echo "Running an interactive MATLAB session through emClarity"'
echo '  '
echo '  # Use provided matlab command or default'
echo '  if [[ -z "${2}" ]] ; then'
echo '    matlabCommand="matlab -nosplash -nodisplay"'
echo '  else'
echo '    matlabCommand="${2}"'
echo '  fi'
echo '  '
echo '  # Set MATLABPATH to prioritize emClarity source directory'
echo '  # This ensures we use the correct emClarity even if user has saved paths'
echo "  export EMCLARITY_SOURCE_DIR=${EMC_SOURCE_ROOT}"
echo '  build_up_path=""'
echo '  root_dirs=($(cd $EMCLARITY_SOURCE_DIR && ls -d */ | grep -v -e .git -e bin -e gui -e venv -e docs -e docs_overleaf -e logFile -e python))'
echo '    for dir in "${root_dirs[@]}"; do'
echo '        build_up_path="${EMCLARITY_SOURCE_DIR}/${dir%/}:$build_up_path"'
echo '    done'
echo '  export MATLABPATH=$build_up_path:$MATLABPATH'
echo '  echo "Setting MATLABPATH to use: ${MATLABPATH}"'
echo '  echo "Launching: ${matlabCommand}"'
echo '  echo "Type emClarity or emClarity('"'"'help'"'"') to get started"'
echo '  echo ""'
echo '  '
echo '  # Set other environment variables as needed'
echo '  export IMOD_FORCE_OMP_THREADS=8'
echo '  '
echo '  # Launch MATLAB with the configured environment'
echo '  ${matlabCommand}'
echo '  exit 0'
echo 'fi'

} >> emClarity_${scriptOutName}

{
echo ""
echo ''
echo "if [ ! -f \${emClarity_ROOT}/bin/emClarity_${binaryOutName} ]; then"
echo '  echo "Did not find the binary on the path, did you fill it in above?"'
echo '  exit 1'
echo 'fi'
echo ''
echo "argList="${shortHead} ""
echo 'while [ $# -gt 0 ]; do'
echo '  token=$1'
echo '  argList="${argList} ${token}"'
echo '  shift'
echo 'done'
echo ''
echo "\${emClarity_ROOT}/bin/emClarity_${binaryOutName} \${argList}"
 

} >> emClarity_${scriptOutName}

chmod a=wrx emClarity_${scriptOutName}


rm -rf ../bin/${EMC_VERSION}
mkdir ../bin/${EMC_VERSION} ../bin/${EMC_VERSION}/bin ../bin/${EMC_VERSION}/bin/deps

mv emClarity_${scriptOutName} ../bin/${EMC_VERSION}/bin
mv emClarity_${binaryOutName} ../bin/${EMC_VERSION}/bin

cp -ru ${emC_DEPS}/deps/cisTEMDeps.txt ../bin/${EMC_VERSION}/bin/deps

cat ../bin/${EMC_VERSION}/bin/deps/cisTEMDeps.txt | while read dep ; do
  echo "Copying ${dep} to ../bin/${EMC_VERSION}/bin/deps"
  cp -u ${emC_DEPS}/emC_${dep} ../bin/${EMC_VERSION}/bin/deps
done

cp -rp ../docs ../bin/${EMC_VERSION}

cp .bashrc ../bin/${EMC_VERSION}
cd ../bin/${EMC_VERSION}/bin

ln -s emClarity_${scriptOutName} emClarity
cd ../../

if [[ ${zip_location} != "NONE" ]]; then
  zip -qr --symlinks ${EMC_VERSION}.zip ./${EMC_VERSION}
  mv ${EMC_VERSION}.zip ${zip_location}
fi

rm -rf ${EMC_VERSION}




