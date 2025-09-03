# Function Naming Convention Change

## Summary

As of September 3, 2025, we have standardized the naming convention for emClarity Python functions from `bh_` prefix to `emc_` prefix to better reflect the emClarity branding and avoid confusion with the original MATLAB BH (Benjamin Himes) functions.

## Changes Made

### File Rename
- **Old**: `bh_run_auto_align.py`
- **New**: `emc_run_auto_align.py`

### Function Rename
- **Old**: `bh_run_auto_align()`
- **New**: `emc_run_auto_align()`

### Integrated Shell Script Functionality
In addition to the rename, we have **integrated the shell script functionality** directly into the Python implementation:

#### Removed External Dependencies
- **emC_autoAlign** shell script functionality → integrated as `_run_integrated_patch_tracking()`
- **emC_findBeads** shell script functionality → integrated as `_run_integrated_bead_finding()`

#### New Function Signature
```python
# OLD (with external shell script paths)
def bh_run_auto_align(
    parameter_file: Union[str, Path],
    run_path: Union[str, Path],           # ← REMOVED
    find_beads_path: Union[str, Path],    # ← REMOVED
    stack_in: Union[str, Path],
    tilt_angles: Union[str, Path],
    img_rotation: Union[str, float],
    skip_tilts: Union[str, List[int], None] = None
) -> None:

# NEW (integrated functionality)
def emc_run_auto_align(
    parameter_file: Union[str, Path],
    stack_in: Union[str, Path],
    tilt_angles: Union[str, Path], 
    img_rotation: Union[str, float],
    skip_tilts: Union[str, List[int], None] = None
) -> None:
```

#### Benefits of Integration
1. **Simplified Usage**: No need to specify paths to external shell scripts
2. **Better Error Handling**: Python-native error handling instead of subprocess error codes
3. **Improved Logging**: Detailed logging of each step in the alignment process
4. **Self-Contained**: All functionality in a single Python module
5. **Cross-Platform**: Better compatibility across different operating systems

## Future Naming Convention

**Going forward, all new emClarity Python functions should use the `emc_` prefix:**

- ✅ `emc_run_auto_align()` 
- ✅ `emc_str2double()`
- 🔮 `emc_ctf_estimate()` (future)
- 🔮 `emc_template_match()` (future)
- 🔮 `emc_refine_alignment()` (future)

## Legacy Support

The old `bh_` prefix functions are deprecated but any references in documentation or other code should be updated to use the new `emc_` prefix.

## Implementation Details

### Integrated Patch Tracking (`_run_integrated_patch_tracking`)
Replaces the `emC_autoAlign` shell script with native Python implementation that:
- Iterates through binning levels
- Runs tiltxcorr for cross-correlation
- Performs patch tracking with configurable parameters
- Runs tiltalign for fiducial-based alignment
- Handles both global and local alignment options

### Integrated Bead Finding (`_run_integrated_bead_finding`)
Replaces the `emC_findBeads` shell script with native Python implementation that:
- Creates binned aligned stacks
- Generates 3D reconstructions for bead finding
- Runs findbeads3d to locate fiducial markers
- Creates erased reconstructions by projecting beads out
- Performs cleanup of temporary files

### External Tool Dependencies
The integrated functions still call IMOD tools as subprocesses:
- `newstack` - stack manipulation and binning
- `tiltxcorr` - cross-correlation alignment
- `tiltalign` - fiducial-based alignment
- `tilt` - tomographic reconstruction
- `findbeads3d` - 3D bead detection
- `imodchopconts` - contour processing
- `xfproduct` - transform combination
- `xftoxg` - transform conversion

This provides the same functionality as the original shell scripts while maintaining the robustness of the IMOD tool chain.

---

*This change improves the consistency and usability of the emClarity Python implementation while maintaining full compatibility with existing workflows.*
