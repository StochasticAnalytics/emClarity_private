# Some basic rules for GH agent for converting emClarity to python

## Structure

- mirror the directory structure of the main project, eg, if we are adapting metaData/BH_parseParameter.m, we should create a corresponding Python file at python/metaData/emc_parseParameter.py

- update a README.md file in the corresponding directory to explain the purpose and usage of the new Python module.

- add unit tests for the new Python module, at python/folderName/tests/

- update an overall README at python/docs/agent_notes.md that includes useful information about the conversion process, any challenges encountered, and other details that will help future agent work on the project.

## Temporary File Management

- **All temporary files must go in /tmp/copilot-test/**: Never create temporary test files, demo data, star files, CSV files, or experimental files directly in the project directories. Always use `/tmp/copilot-test/` for any temporary files during development and testing. This keeps the project clean and prevents accidental commits of temporary data.

- **Clean up after testing**: Remove temporary files from `/tmp/copilot-test/` when testing is complete, or document their purpose if they need to be preserved.

## Naming Conventions

- Use `emc_` prefix for Python modules (e.g., `BH_parseParameterFile.m` → `emc_parameter_converter.py`)
- Use descriptive names that reflect functionality
- Follow Python naming conventions (snake_case for functions and variables)

## Formatting

- when working on cuda, please use the guidlines from the file #python/cuda_ops/.clang-format
- CuPy requires names to not be mangled, so clean entry points for kernels must include extern "C"


## Image and Array conventions

- For multi-dimensional arrays, emClarity refers to fastest dimension as X, the second as Y and the third as Z.
- Indexing in emClarity matlab files is started from 1 (vs 0 in python and cuda)

## CUDA Integration Architecture

- prefer int to uint where possible.

### Pattern for CUDA-Accelerated Operations

Following the established pattern in `python/cuda_ops/`, CUDA operations should use:

1. **File Naming Convention**: `emc_module_name.cu` and `emc_module_name.py`
2. **CuPy RawModule Integration**: Load custom CUDA kernels via `cp.RawModule(code=cuda_source)`
3. **External C Linkage**: Use `extern "C" { }` wrapper in CUDA files for Python visibility
4. **Memory Management**: Support both CuPy arrays and raw GPU pointers
5. **Error Handling**: Comprehensive validation and CUDA error checking

### CUDA Development Workflow

1. **CUDA Kernel** (`.cu` file):
   ```cuda
   extern "C" {
   __global__ void cuda_operation_name(const float* input, float* output, int n) {
       // Kernel implementation
   }
   }
   ```

2. **Python Wrapper** (`.py` file):
   ```python
   class CudaOperations:
       def __init__(self):
           self._load_cuda_kernels()

       def operation_name(self, input_array):
           # CuPy interface with grid/block calculation
           return result_array
   ```

3. **Testing**: Compare against NumPy/CuPy reference implementations

### Current CUDA Status

**✅ Working Operations** (September 3, 2025):
- Array addition, scalar multiplication, 2D transpose
- CuPy RawModule integration established
- Comprehensive test framework

**🔧 In Development**:
- 3D array transpose (index mapping issues)
- Performance optimization vs CuPy built-ins

This CUDA architecture will replace MATLAB MEX files (like `mexFFT.cu`) with Python-wrapped implementations providing better memory management and integration.

## Recent Completions

### ✅ Parameter Management (September 3, 2025)

**Converted**: `metaData/BH_parseParameterFile.m` → `python/metaData/emc_parameter_converter.py`

**Key improvements**:
- Modern JSON format replacing MATLAB syntax
- Clear unit names (angstroms, mm, kV) instead of scientific notation
- Structured parameter organization (system, microscope, ctf, etc.)
- Full bidirectional conversion with backward compatibility
- Comprehensive JSON schema validation
- 100% test coverage with round-trip validation

**Files created**:
- `python/metaData/emc_parameter_converter.py` - Main converter
- `python/metaData/tests/test_emc_parameter_converter.py` - Unit tests
- `python/metaData/README.md` - Module documentation
- `python/metaData/__init__.py` - Package initialization
- `python/docs/agent_notes.md` - Conversion tracking

This conversion serves as the template for future module conversions.

## Key Learnings from Development Sessions

### CUDA Development Challenges & Solutions (September 3, 2025)

**Challenge: CuPy Header File Inclusion**
- **Issue**: CuPy's RawModule cannot directly include external header files (`#include "emc_cuda_utils.cuh"`)
- **Solution**: Dynamically inline header content during Python wrapper compilation
- **Learning**: Always inline utility functions rather than relying on separate header includes for CuPy

**Challenge: Vector Return Types vs Reference Parameters**
- **Issue**: Initial utility functions used reference parameters (`void get_2d_idx(int& x, int& y)`)
- **Improvement**: Switched to CUDA vector return types (`int2 get_2d_idx()`)
- **Learning**: CUDA vector types (`int2`, `int3`) provide cleaner, more idiomatic code

**Challenge: emClarity Dimension Convention Mapping**
- **Issue**: Multiple iterations needed to correctly implement 3D transpose following emClarity conventions
- **Solution**: X=fastest, Y=second, Z=slowest dimension ordering with row-major memory layout
- **Learning**: Always validate indexing patterns against NumPy/CuPy references for correctness

**Challenge: CUDA Utility Function Architecture**
- **Issue**: Code duplication across multiple CUDA kernels for indexing operations
- **Solution**: Created comprehensive utility header with inline device functions
- **Learning**: Invest in reusable utilities early to maintain code quality and consistency

### Class-Based Architecture Patterns (September 3, 2025)

**Challenge: fourierTransformer.m Pattern Translation**
- **Issue**: Translating MATLAB object-oriented patterns to Python while maintaining efficiency
- **Solution**: Created PaddedArray class following established patterns:
  - Persistent memory management with `use_once` parameter
  - CPU/GPU switching methods (`to_cpu()`, `to_gpu()`)
  - Direct array access via `get_stored_array_reference()`
  - Memory monitoring with `get_memory_info()`
- **Learning**: Follow existing MATLAB patterns closely for consistency and user familiarity

**Challenge: Memory Safety in Array References**
- **Issue**: Python array references can become invalid after operations like `zero_stored_array()`
- **Solution**: Clear documentation and examples about reference lifetime management
- **Learning**: Provide explicit warnings and usage examples for memory-unsafe operations

**Challenge: Performance Optimization Strategy**
- **Issue**: Custom CUDA kernels sometimes performed worse than CuPy built-ins
- **Solution**: Use custom kernels only when necessary; leverage CuPy for standard operations
- **Learning**: Don't optimize prematurely - profile and compare against established libraries

### Development Workflow Improvements

**Communication Pattern: Incremental Testing**
- **Effective**: Breaking complex implementations into testable components
- **Example**: CUDA utilities → basic operations → complex class implementation
- **Learning**: Always validate each layer before building the next

**Communication Pattern: Real-world Usage Examples**
- **Effective**: Creating practical examples following established patterns (fourierTransformer.m)
- **Example**: PaddedArray examples showing single-use vs persistent patterns
- **Learning**: Concrete usage examples clarify requirements better than abstract descriptions

**Communication Pattern: Performance Validation**
- **Effective**: Benchmarking against existing implementations to validate improvements
- **Example**: 3.9x speedup for persistent PaddedArray vs original function
- **Learning**: Always include performance comparisons to justify architectural decisions

### File Organization Best Practices

**Pattern: Comprehensive Documentation Structure**
- **Effective**: Multiple documentation types for different audiences:
  - `README.md`: Quick start and overview
  - `README_utilities.md`: Detailed API reference
  - `IMPLEMENTATION_SUMMARY.md`: Technical implementation details
  - `*_examples.py`: Practical usage demonstrations
- **Learning**: Over-document rather than under-document for complex systems

**Pattern: Test-Driven Development**
- **Effective**: Creating comprehensive test suites before finalizing implementation
- **Example**: 15+ test scenarios covering correctness, performance, memory management
- **Learning**: Extensive testing catches edge cases and validates design decisions

These learnings should guide future conversion sessions to minimize iteration cycles and improve code quality.

## Session-Specific Learnings (September 3, 2025)

### Key Insights from BH_runAutoAlign → EMC_runAutoAlign Conversion

**Effective Pattern: Function Rename + Integration Architecture Shift**

**Challenge**: Converting MATLAB function that relied on external shell scripts (`emC_autoAlign`, `emC_findBeads`)
- **Initial Approach**: Direct translation maintaining external script dependencies
- **Evolution**: Integrated shell script functionality directly into Python implementation
- **Final Result**: Simplified interface with better error handling and no external dependencies

**Key Decision Points**:
1. **External vs Integrated**: Initially kept external script paths, then realized integration would provide better user experience
2. **Function Signature Evolution**: Removed `run_path` and `find_beads_path` parameters, simplifying the interface
3. **Shell Script Translation**: Implemented `_run_integrated_patch_tracking()` and `_run_integrated_bead_finding()` as native Python methods

**Learning**: When converting functions with external dependencies, consider whether those dependencies can be integrated for a cleaner Python API.

---

**Communication Pattern: Incremental Refactoring with User Input**

**Effective Cycle**:
1. **Initial Conversion**: Direct MATLAB-to-Python translation maintaining original architecture
2. **User Feedback**: "Rather than have this separate functionality, let's make them methods"
3. **Architecture Shift**: Integrated external shell scripts as Python methods
4. **Naming Convention**: Applied consistent `emc_` prefix throughout

**Impact**: This pattern caught a major architectural improvement opportunity that would have been missed with a pure translation approach.

**Learning**: Always present initial conversion for user review before finalizing - users often have insights about better integration patterns.

---

**Technical Challenge: Complex Shell Script Integration**

**Problem**: The `emC_autoAlign` shell script contained complex bash logic with:
- Multi-level binning loops with mathematical calculations
- Conditional iteration logic based on alignment quality
- External tool coordination (newstack, tiltxcorr, tiltalign, etc.)
- File management and cleanup

**Solution Strategy**:
1. **Analyze shell script structure**: Identified main loops and decision points
2. **Translate bash constructs**: Converted shell math and loops to Python equivalents
3. **Subprocess management**: Maintained calls to IMOD tools with proper error handling
4. **Helper function decomposition**: Split complex logic into `_run_first_iteration_alignment()`, `_run_subsequent_iteration_alignment()`, etc.

**Key Code Pattern**:
```python
# Bash: for iBin in $(seq $binHigh $binInc $binLow)
# Python:
bin_sequence = list(range(binning_params['bin_high'],
                         binning_params['bin_low'] + binning_params['bin_inc'],
                         binning_params['bin_inc']))
for i_bin in bin_sequence:
    # Process each binning level
```

**Learning**: Complex shell scripts can be successfully translated to Python with careful analysis of control flow and proper helper function decomposition.

---

**File Management Anti-Pattern: Temporary File Proliferation**

**Problem Observed**: Throughout the session, multiple temporary files were created in project directories:
- Test files in root directory (`test_*.py`, `test_*.m`)
- Demo data in `python/metaData/` (`demo_*.py`, `*.png`, `*.csv`)
- Star file test data (`test_star_data/` directories)

**Solution Implemented**:
- **Cleanup Rule**: All temporary files must go in `/tmp/copilot-test/`
- **Documentation**: Added rule to both instruction files
- **Retroactive Cleanup**: Removed all temporary files from project directories

**Learning**: Establish temporary file management rules early in development to prevent project bloat and ensure clean git history.

---

**Testing Strategy: Comprehensive Validation with Renamed Functions**

**Challenge**: After renaming functions and changing signatures, all references needed updating:
- Test files importing old function names
- Command line interface changes
- Documentation updates

**Effective Approach**:
1. **Update function definition first**
2. **Update imports systematically**
3. **Test immediately after each change**
4. **Update CLI and help text**
5. **Validate with comprehensive test suite**

**Key Success**: The test suite caught all reference errors immediately, preventing runtime failures.

**Learning**: When making breaking changes like function renames, update and test incrementally rather than changing everything at once.

---

**Documentation Pattern: Multiple Documentation Types for Complex Changes**

**Effective Pattern**: Created multiple documentation artifacts:
- `FUNCTION_RENAME_NOTES.md`: Specific to the naming convention change
- `EMC_INTEGRATION_COMPLETE.md`: Comprehensive implementation summary
- `CONVERSION_COMPLETE.md`: Original completion documentation
- Updated `README.md` files: User-facing documentation

**Benefit**: Different audiences (users, developers, future AI sessions) each get appropriate level of detail.

**Learning**: For significant architectural changes, create multiple documentation types rather than trying to fit everything in one document.
