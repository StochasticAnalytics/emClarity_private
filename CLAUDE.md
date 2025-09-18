# CLAUDE.md - AI Agent Guidelines for emClarity

## Project Overview

**emClarity** is a comprehensive software package for high-resolution cryo-electron microscopy (cryo-EM) sub-tomogram averaging. This codebase has been developed over 10+ years, starting as a graduate project and evolving through post-doctoral work.

### Key Characteristics
- **Primary Language**: MATLAB with CUDA MEX extensions for GPU acceleration
- **Purpose**: Process cryo-EM tilt-series data to achieve sub-3Å resolution 3D reconstructions
- **Architecture**: Command-line driven with modular processing steps
- **Performance**: Heavy GPU utilization through custom CUDA kernels
- **Evolution**: Mixed coding standards due to organic growth over a decade

### Development Philosophy
**Important**: The codebase reflects a decade-long learning journey where coding skills and standards evolved significantly. Early code was written while learning to program, resulting in varying quality and conventions throughout.

When modifying any code:
- Always prefer refactoring and improving code quality
- Modernize variable names and structure when touching old code
- Apply current best practices rather than matching legacy patterns
- Clean up and simplify complex or unclear logic
- Add proper error handling and validation where missing
- Document unclear functionality as you discover it

## Scientific Context

### Problem Domain
emClarity processes cryo-electron tomography data to reconstruct high-resolution 3D structures of biological macromolecules. The workflow involves:
- Aligning and correcting tilt-series from electron microscopes
- Extracting and aligning thousands of sub-tomograms (3D particle images)
- Averaging aligned particles to improve signal-to-noise ratio
- Achieving sub-3Å resolution reconstructions of protein complexes

### Core Design Imperative: Scientific Robustness
**Critical**: emClarity is designed to protect users from common pitfalls in cryo-EM processing and ensure scientifically valid results. This means:

- **Preventing overfitting to noise**: Algorithms include safeguards against fitting noise patterns
- **Gold-standard FSC**: Fourier Shell Correlation calculations maintain true independence between half-sets
- **Artifact prevention**: Filtering operations are carefully designed to avoid introducing processing artifacts
- **Fail-fast philosophy**: Operations fail early and obviously if results might be compromised
- **Validation at every step**: Built-in checks ensure data integrity throughout the pipeline

When modifying code, maintain these protective measures. Never optimize for speed or convenience at the expense of scientific validity.

## Repository Structure

### Core MATLAB Directories

- **alignment/** - Sub-tomogram alignment algorithms
  - `BH_alignRaw3d_v2.m`: Main particle alignment routine
  - `BH_templateSearch3d_2.m`: Template matching for particle picking
  - Shell scripts for tilt-series alignment integration with IMOD

- **coordinates/** - Coordinate transformation and grid management
  - `EMC_coordTransform.m`: Core coordinate system transformations
  - `BH_multi_*`: Multi-particle coordinate operations
  - Handles Euler angles and spatial transformations

- **ctf/** - Contrast Transfer Function correction
  - `BH_ctf_Correct3d.m`: 3D CTF correction implementation
  - `BH_ctf_Estimate.m`: Defocus and astigmatism estimation
  - Critical for high-resolution reconstruction

- **masking/** - Image masking and filtering operations
  - `BH_mask3d.m`: 3D masking functions
  - `BH_bandpass3d.m`: Frequency filtering
  - `BH_padZeros3d.m`: Volume padding operations

- **metaData/** - Project metadata and parameter management
  - `BH_parseParameterFile.m`: Parameter file parsing
  - `BH_geometryInitialize.m`: Project geometry setup
  - Manages project state and configuration

- **mexFiles/** - CUDA MEX extensions for GPU acceleration
  - `mexFFT.cu`: GPU-accelerated FFT operations
  - `mexCTF.cu`: CTF calculations on GPU
  - Performance-critical operations

- **logicals/** - Boolean operations and validation utilities
  - Input validation functions
  - GPU availability checks
  - Parallel job management

### Supporting Directories

- **python/** - Ongoing Python conversion effort
- **@MRCImage/** - MRC file I/O class for cryo-EM data format
- **testScripts/** - Testing utilities and compilation scripts
- **gui/** - GUI development (PySide6-based interface)
- **bin/** - Compiled binaries and dependencies
- **docs/** - Documentation and tutorials

## MATLAB Coding Conventions

### Naming Conventions

**Function Prefixes**:
- **BH_*** - Legacy prefix from earlier development (still widely used)
- **EMC_*** - Newer, preferred prefix for all new functions
- Both prefixes were originally chosen to avoid naming conflicts with MATLAB built-ins
- When creating new functions, use `EMC_` prefix for consistency

**Function Naming Patterns**:
- `EMC_function_name` - Preferred snake_case for new functions after prefix
- `BH_multi_*` - Functions handling multiple particles/operations
- `BH_ctf_*` - CTF-related operations
- `BH_mask3d_*` - 3D masking operations

**Variable Naming**:
- ALL_CAPS for constants and parameter file variables (e.g., `PARAMETER_FILE`, `CYCLE`)
- snake_case for new local variables (e.g., `particle_radius`, `sampling_rate`)
- Older code uses camelCase - convert to snake_case when refactoring

**GPU/CPU Variants**:
- Functions may have `_cpu` suffix for CPU-only versions
- GPU operations typically use the standard name
- Example: `BH_mask3d.m` (GPU) vs `BH_mask3d_cpu.m` (CPU)

## Critical Development Rules


### File and Data Safety
- **Never modify production databases directly** - Always work on copies
- **Use /tmp/claude_cache/ for all temporary test files** - Create this directory if needed and use it exclusively for temporary scripts, test outputs, and working files. This makes cleanup easier and prevents cluttering the project directories
- **Never commit test data or temporary files** to the repository
- **Always preserve original data** - Work on copies when testing
- **Clean up temporary files** after completing tasks - Remove any test scripts or outputs created during development

### Error Handling Philosophy
- **Fail fast and loudly** when results might be compromised
- **Provide clear, actionable error messages**
- **Log errors to logFile/** directory for debugging
- **Never silently ignore errors** that could affect results

## Python Conversion Guidelines

### Conversion Strategy
- **Mirror MATLAB directory structure**: `alignment/BH_alignRaw3d.m` → `python/alignment/emc_align_raw3d.py`
- **Use `emc_` prefix** for Python modules (lowercase, snake_case)
- **Modernize, don't just translate**: Improve code structure and clarity
- **Maintain scientific accuracy**: Verify numerical results match MATLAB

### Python Standards
- **Follow PEP 8** with modifications per PYTHON_STYLE_GUIDE.md
- **Use type hints** extensively for clarity
- **Prefer NumPy/CuPy** for numerical operations
- **Document with Google-style docstrings**

### Key Conversion Patterns
- **Parameter files**: Convert MATLAB format to JSON with clear units
- **GPU operations**: Use CuPy with automatic CPU fallback
- **File I/O**: Use mrcfile library for MRC format compatibility
- **Testing**: Create comprehensive unit tests for each converted module

### Completed Conversions (Reference Examples)
- `metaData/emc_parameter_converter.py` - Parameter file handling
- `masking/emc_pad_zeros_3d.py` - 3D padding with GPU support
- `cuda_ops/emc_cuda_basic_ops.py` - CUDA kernel integration pattern

## Testing and Compilation

### MATLAB Compilation

**MEX Compilation**:
- Run `mexCompile.m` in `mexFiles/` to build CUDA MEX functions
- Requires CUDA toolkit and compatible MATLAB version
- Check `testScripts/mCompile.sh` for full compilation process
- Compilation warnings logged to `testScripts/compilation_warnings.log`

### Testing Requirements

**Before committing**:
- Run compilation without warnings
- Test GPU and CPU code paths
- Verify numerical accuracy against known results
- Check memory usage and cleanup

**Python Code Quality** (per pyproject.toml):
- **Linting/Formatting**: `ruff` (replaces black, isort, flake8)
  - Run: `ruff check python/` and `ruff format python/`
- **Type checking**: `pyright` for static type analysis
- **Security**: `bandit` for security issue scanning
- **Testing**: `pytest` with coverage reporting
- **Pre-commit hooks**: Available for automated checks

## Common Workflow Commands

### Main emClarity Entry Point

The main wrapper is `emClarity` (called from compiled version or `testScripts/emClarity.m`):

```bash
# General syntax
emClarity [command] [parameters]

# Examples
emClarity autoAlign param.m tilt1.st tilt1.rawtlt 0
emClarity ctf estimate param.m tilt1
emClarity init param0.m
emClarity ctf 3d param0.m
emClarity avg param0.m 0 RawAlignment
emClarity alignRaw param0.m 0
emClarity tomoCPR param0.m 4
```

### Key Processing Steps

1. **Tilt-series alignment**: `autoAlign`
2. **CTF estimation**: `ctf estimate`
3. **Template matching**: `templateSearch`
4. **Project initialization**: `init`
5. **Tomogram reconstruction**: `ctf 3d`
6. **Subtomogram averaging**: `avg`
7. **Particle alignment**: `alignRaw`
8. **Tilt-series refinement**: `tomoCPR`
9. **Classification**: `classify`

### Project Directory Organization

emClarity expects specific directory structure:
- **rawData/** - Original tilt-series
- **fixedStacks/** - Aligned tilt-series and metadata
- **aliStacks/** - CTF-corrected aligned stacks
- **cache/** - Temporary files and reconstructions
- **convmap/** - Template search results
- **FSC/** - Resolution curves and statistics
- **logFile/** - Processing logs

---

*[Next section to be added after review]*