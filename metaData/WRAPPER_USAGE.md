# Metadata Wrapper Usage Guide

## Overview

The metadata wrapper provides a unified interface for loading and saving emClarity metadata, preparing for future storage format transitions while maintaining backward compatibility.

## Basic Usage

### Loading Metadata

```matlab
% Standard usage with parameter structure
emc = BH_parseParameterFile('my_project.param');
subTomoMeta = BH_loadSubTomoMeta(emc.('subTomoMeta'), emc.('metadata_format'));

% Access fields normally
currentCycle = subTomoMeta.currentCycle;
particles = subTomoMeta.cycle001.RawAlign.tomo_001;
```

### Saving Metadata

```matlab
% Modify metadata
subTomoMeta.currentCycle = subTomoMeta.currentCycle + 1;

% Save using wrapper
BH_saveSubTomoMeta(emc.('subTomoMeta'), subTomoMeta);
```

## Converting Existing Code

### Old Pattern
```matlab
% Loading
load(sprintf('%s.mat', emc.('subTomoMeta')), 'subTomoMeta');

% Saving
save(emc.('subTomoMeta'), 'subTomoMeta', '-v7.3');
```

### New Pattern
```matlab
% Loading
subTomoMeta = BH_loadSubTomoMeta(emc.('subTomoMeta'), emc.('metadata_format'));

% Saving
BH_saveSubTomoMeta(emc.('subTomoMeta'), subTomoMeta);
```

## Supported Formats

Currently only `'legacy'` format is fully implemented:
- **legacy**: Traditional .mat file storage (default)
- **partitioned**: STAR/JSON format (future)
- **development**: Dual format with validation (future)

## Parameter File Configuration

Add to your parameter file:
```
metadata_format=legacy
```

If not specified, defaults to `'legacy'`.

## Benefits

1. **Future-proof**: Easy transition to new storage formats
2. **Backward compatible**: Works with existing code
3. **Unified interface**: Same functions regardless of storage format
4. **Automatic backups**: Creates backups before overwriting
5. **Error handling**: Better error messages and recovery

## Example: BH_removeDuplicates

The function has been updated to use the wrapper:

```matlab
function [] = BH_removeDuplicates(PARAMETER_FILE, CYCLE)
    % ... setup code ...
    
    % Load metadata using wrapper
    subTomoMeta = BH_loadSubTomoMeta(emc.('subTomoMeta'), emc.('metadata_format'));
    geometry = subTomoMeta.(cycleNumber).RawAlign;
    
    % ... processing code ...
    
    % Save using wrapper
    subTomoMeta.(cycleNumber).RawAlign = geometry;
    BH_saveSubTomoMeta(emc.('subTomoMeta'), subTomoMeta);
end
```

## Migration Strategy

1. Update functions gradually as you work on them
2. Both old and new patterns work during transition
3. Wrapper falls back to legacy mode if needed
4. No changes required to data structures

## Troubleshooting

### "metadata_format not found"
Add `metadata_format=legacy` to your parameter file, or the parameter parser will add it automatically with default value.

### "Wrapper class not found"
The wrapper functions automatically fall back to legacy mode if the wrapper class is not available.

### Backup files
Backups are created automatically when saving: `filename.backup_YYYYMMDD_HHMMSS`

## Future Features

- STAR file format for interoperability
- Partitioned storage for large datasets
- Export to RELION/PEET/CryoSPARC
- Development mode for format validation
- Lazy loading for performance