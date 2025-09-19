# emClarity Metadata Refactor Implementation Plan

**Version:** 1.0
**Date:** December 2024
**Status:** Planning Phase

## Executive Summary

This document outlines the plan to refactor emClarity's metadata storage system from a monolithic MATLAB .mat file to a partitioned, interoperable format using STAR files and JSON. The refactor includes a feature flag system to allow seamless switching between legacy and new formats during the transition period.

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Architecture Overview](#architecture-overview)
3. [Feature Flag System](#feature-flag-system)
4. [Implementation Phases](#implementation-phases)
5. [File Format Specifications](#file-format-specifications)
6. [API Design](#api-design)
7. [Migration Strategy](#migration-strategy)
8. [Testing Plan](#testing-plan)
9. [Rollback Procedures](#rollback-procedures)
10. [Future Roadmap](#future-roadmap)

## Problem Statement

### Current Issues
- **File corruption**: Large .mat files (>2GB) prone to corruption during saves
- **Memory inefficiency**: Entire metadata structure loaded even when only current cycle needed
- **Lack of interoperability**: .mat format not readable by other cryo-EM software
- **Version control**: Binary format difficult to track changes
- **Recovery difficulty**: Single corrupt file loses all metadata

### Solution Goals
- Partition metadata into smaller, manageable files
- Use standard cryo-EM formats (STAR files) for interoperability
- Implement robust save/load with verification
- Enable gradual migration without disrupting production
- Maintain backward compatibility

## Architecture Overview

### Directory Structure

```
project/
├── emClarity.param              # Parameter file with format flag
├── subTomoMeta.mat             # Legacy format (if metadata_format='legacy')
└── subTomoMeta/                # New format (if metadata_format='partitioned')
    ├── index.json              # Master index with version, checksums
    ├── config.json             # Core parameters and settings
    ├── geometry/
    │   ├── mapBackGeometry.star    # Tomogram to tilt series mapping
    │   ├── tiltGeometry.star       # Tilt series alignment parameters
    │   └── reconGeometry.star      # Reconstruction parameters
    ├── cycles/
    │   ├── cycle000/
    │   │   ├── metadata.json       # Cycle-specific parameters
    │   │   ├── particles.star      # Particle positions (RawAlign)
    │   │   ├── classification.star # Classification results
    │   │   ├── montages.json       # Montage locations and metadata
    │   │   └── fsc.json           # FSC curves and fits
    │   ├── cycle001/
    │   └── ...
    └── cache/                  # Optional memory-mapped cache
```

### Format Selection Logic

```
┌─────────────────┐
│ Load Parameter  │
│      File       │
└────────┬────────┘
         │
         ▼
    ┌────────────┐
    │ Check      │
    │ metadata_  │
    │ format     │
    └────┬───────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌──────────┐
│ Legacy │ │Partitioned│
│  .mat  │ │STAR/JSON │
└────────┘ └──────────┘
```

## Feature Flag System

### Parameter File Configuration

Add to `emClarity.param`:

```matlab
% Metadata Storage Format
% Options: 'legacy' (default), 'partitioned', or 'development'
metadata_format legacy

% Optional: Auto-migration settings
auto_migrate_metadata 0
verify_metadata_saves 1
metadata_backup_count 3

% Development mode settings (only used when metadata_format='development')
dev_mode_compare_tolerance 1e-10  % Numerical comparison tolerance
dev_mode_log_all_access 0         % Log every field access (verbose)
dev_mode_fail_on_mismatch 0       % Error instead of warning on mismatch
```

### Runtime Detection

The system will automatically detect the format based on:
1. First check `metadata_format` parameter
2. If not specified, check for existence of `subTomoMeta/index.json` (new format)
3. Fall back to `subTomoMeta.mat` (legacy format)
4. Error if neither exists and it's not an initialization

## Universal Wrapper Class Architecture

### Design Principles

The metadata system uses a universal wrapper class (`BH_subTomoMeta`) that:
1. **Hides implementation details** - Application code doesn't know the storage format
2. **Provides transparent access** - Uses MATLAB's subsref/subsasgn for native syntax
3. **Supports three modes**:
   - **Legacy**: Traditional .mat file storage
   - **Partitioned**: STAR/JSON distributed storage
   - **Development**: Dual read/write with automatic validation
4. **Enables export** - Built-in conversion to RELION, PEET, CryoSPARC formats

### Wrapper Class Structure

```matlab
classdef BH_subTomoMeta < handle
    properties (Access = private)
        data               % The actual metadata
        format_type        % 'legacy', 'partitioned', or 'development'
        legacy_data        % For development mode
        partitioned_data   % For development mode
        io_handler         % I/O operations handler
        export_handler     % Export operations handler
        emc               % Parameter structure
    end

    methods
        % Core functionality
        function obj = BH_subTomoMeta(identifier, emc)
        function value = subsref(obj, s)
        function obj = subsasgn(obj, s, value)
        function save(obj)

        % Export methods
        function exportToRELION(obj, output_dir, options)
        function exportToPEET(obj, output_dir, options)
        function exportToCryoSPARC(obj, output_dir, options)
    end
end
```

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1-2)

#### 1.1 Create Base I/O Classes

**File: `metaData/BH_subTomoMeta_io.m`**
```matlab
classdef BH_subTomoMeta_io < handle
    properties
        base_path
        format_type  % 'legacy', 'partitioned', or 'development'
        format_version = '1.0'
        index
        cache
        emc  % Parameter structure
    end

    methods
        function obj = BH_subTomoMeta_io(identifier, emc)
            % Detect format and initialize appropriately
            obj.emc = emc;
            obj.detect_format(identifier);
        end

        function subTomoMeta = load(obj, options)
            switch obj.format_type
                case 'legacy'
                    subTomoMeta = obj.load_legacy();
                case 'partitioned'
                    subTomoMeta = obj.load_partitioned(options);
            end
        end

        function save(obj, subTomoMeta, options)
            switch obj.format_type
                case 'legacy'
                    obj.save_legacy(subTomoMeta);
                case 'partitioned'
                    obj.save_partitioned(subTomoMeta, options);
            end
        end
    end
end
```

**File: `metaData/BH_star_io.m`**
```matlab
classdef BH_star_io
    % MATLAB-native STAR file I/O

    methods (Static)
        function data = read(filename)
            % Read STAR file into MATLAB table
            % Handles both loop_ and single value formats
        end

        function write(data, filename, column_names)
            % Write MATLAB table/array to STAR format
            % Maintains RELION compatibility
        end

        function column_names = get_standard_columns(type)
            % Return standard column names for different data types
            % type: 'particles', 'micrographs', 'optics', etc.
        end
    end
end
```

#### 1.2 Implement Wrapper Functions

**File: `metaData/BH_loadSubTomoMeta.m`**
```matlab
function subTomoMeta = BH_loadSubTomoMeta(identifier, cycle_num)
    % Smart loader with format detection
    % Maintains same interface for both formats

    % Get parameters to check format preference
    if exist([identifier '.param'], 'file')
        emc = BH_parseParameterFile([identifier '.param']);
    else
        emc.metadata_format = 'legacy';  % Default
    end

    % Initialize I/O handler
    io = BH_subTomoMeta_io(identifier, emc);

    % Load with appropriate method
    if nargin > 1
        options.cycles = cycle_num;
    else
        options.cycles = 'all';
    end

    subTomoMeta = io.load(options);
end
```

**File: `metaData/BH_saveSubTomoMeta.m`**
```matlab
function success = BH_saveSubTomoMeta(identifier, subTomoMeta, emc)
    % Smart saver with verification

    if nargin < 3
        emc = BH_parseParameterFile([identifier '.param']);
    end

    io = BH_subTomoMeta_io(identifier, emc);

    % Save with verification if requested
    if emc.verify_metadata_saves
        success = io.save_with_verification(subTomoMeta);
    else
        io.save(subTomoMeta);
        success = true;
    end

    % Log the save operation
    BH_log_metadata_operation('save', identifier, success);
end
```

### Phase 2: Format Converters (Week 2-3)

#### 2.1 Legacy to Partitioned Converter

**File: `metaData/BH_convert_metadata_format.m`**
```matlab
function success = BH_convert_metadata_format(source, target_format, options)
    % Convert between metadata formats
    % source: path to existing metadata
    % target_format: 'legacy' or 'partitioned'
    % options: struct with conversion options

    fprintf('Converting metadata to %s format...\n', target_format);

    % Load source
    source_io = BH_subTomoMeta_io(source, struct('metadata_format', 'auto'));
    subTomoMeta = source_io.load();

    % Create backup
    if options.create_backup
        backup_path = sprintf('%s.backup_%s', source, datestr(now, 'yyyymmdd_HHMMSS'));
        copyfile(source, backup_path);
        fprintf('Created backup at %s\n', backup_path);
    end

    % Save in new format
    target_io = BH_subTomoMeta_io(source, struct('metadata_format', target_format));
    success = target_io.save(subTomoMeta);

    if success && options.verify_conversion
        % Verify by loading and comparing
        verify_io = BH_subTomoMeta_io(source, struct('metadata_format', target_format));
        subTomoMeta_verify = verify_io.load();
        success = BH_compare_metadata(subTomoMeta, subTomoMeta_verify);
    end
end
```

#### 2.2 STAR File Handlers

**Particle Data Handler:**
```matlab
function write_particles_star(particles, filename, cycle_num)
    % Convert particle geometry to STAR format

    % Standard RELION-compatible columns
    columns = {
        'rlnCoordinateX', 'rlnCoordinateY', 'rlnCoordinateZ',
        'rlnAngleRot', 'rlnAngleTilt', 'rlnAnglePsi',
        'rlnClassNumber', 'rlnRandomSubset',
        'rlnImageName', 'rlnMicrographName',
        'rlnOpticsGroup', 'rlnCtfMaxResolution',
        'rlnCtfFigureOfMerit', 'rlnDefocusU', 'rlnDefocusV',
        'rlnDefocusAngle', 'rlnCtfBfactor', 'rlnCtfScalefactor',
        'rlnPhaseShift'
    };

    % Map emClarity columns to RELION columns
    star_data = map_emclarity_to_relion(particles, columns);

    % Write STAR file
    BH_star_io.write(star_data, filename, columns);
end
```

### Phase 3: Update Core Functions (Week 3-4)

#### 3.1 Update All Direct Save/Load Calls

Replace throughout codebase:
```matlab
% OLD:
load(sprintf('%s.mat', emc.('subTomoMeta')), 'subTomoMeta');
save(emc.('subTomoMeta'), 'subTomoMeta', '-v7.3');

% NEW:
subTomoMeta = BH_loadSubTomoMeta(emc.('subTomoMeta'));
BH_saveSubTomoMeta(emc.('subTomoMeta'), subTomoMeta, emc);
```

#### 3.2 Add Format-Aware Functions

Update functions that need cycle-specific data:
```matlab
function geometry = BH_loadCycleGeometry(emc, cycle_num)
    % Load only specific cycle data
    io = BH_subTomoMeta_io(emc.('subTomoMeta'), emc);

    if strcmp(io.format_type, 'partitioned')
        % Load just the cycle we need
        geometry = io.load_cycle_geometry(cycle_num);
    else
        % Legacy: load everything and extract
        subTomoMeta = io.load();
        cycleName = sprintf('cycle%03d', cycle_num);
        geometry = subTomoMeta.(cycleName).RawAlign;
    end
end
```

### Phase 4: Testing & Validation (Week 4-5)

See [Testing Plan](#testing-plan) section for details.

### Phase 5: Production Rollout (Week 5-6)

1. Deploy with `metadata_format = 'legacy'` (no change)
2. Test on development systems with `metadata_format = 'partitioned'`
3. Gradual rollout to production systems
4. Monitor performance and issues
5. Full migration once stable

## File Format Specifications

### STAR File Format (Particles)

```
data_particles

loop_
_rlnCoordinateX #1
_rlnCoordinateY #2
_rlnCoordinateZ #3
_rlnAngleRot #4
_rlnAngleTilt #5
_rlnAnglePsi #6
_rlnClassNumber #7
_rlnRandomSubset #8
_rlnImageName #9
_rlnMicrographName #10
123.45 234.56 345.67 12.3 45.6 78.9 2 1 000001@particles.mrcs tomogram_001.mrc
124.45 235.56 346.67 13.3 46.6 79.9 2 2 000002@particles.mrcs tomogram_001.mrc
...
```

### JSON Index Format

```json
{
    "version": "1.0",
    "created": "2024-12-01T10:00:00Z",
    "last_modified": "2024-12-01T14:30:00Z",
    "format": "partitioned",
    "cycles": {
        "cycle000": {
            "path": "cycles/cycle000",
            "checksum": "md5:abc123...",
            "particle_count": 50000,
            "created": "2024-11-15T10:00:00Z"
        },
        "cycle017": {
            "path": "cycles/cycle017",
            "checksum": "md5:def456...",
            "particle_count": 48500,
            "created": "2024-12-01T14:30:00Z"
        }
    },
    "geometry": {
        "mapBackGeometry": {
            "file": "geometry/mapBackGeometry.star",
            "checksum": "md5:789abc..."
        },
        "tiltGeometry": {
            "file": "geometry/tiltGeometry.star",
            "checksum": "md5:def123..."
        }
    }
}
```

## API Design

### Public Interface (User-Facing)

```matlab
% Loading
subTomoMeta = BH_loadSubTomoMeta(identifier);          % Load all
subTomoMeta = BH_loadSubTomoMeta(identifier, 17);      % Load specific cycle
subTomoMeta = BH_loadSubTomoMeta(identifier, [16,17]); % Load multiple cycles

% Saving
BH_saveSubTomoMeta(identifier, subTomoMeta);           % Save all
BH_saveSubTomoMeta(identifier, subTomoMeta, emc);      % Save with options

% Format conversion
BH_convert_metadata_format('project', 'partitioned', options);
BH_convert_metadata_format('project', 'legacy', options);

% Utilities
BH_verify_metadata(identifier);                        % Check integrity
BH_repair_metadata(identifier);                        % Attempt recovery
BH_compare_metadata(meta1, meta2);                     % Compare structures
```

### Internal Interface (Developer)

```matlab
% Direct I/O class usage
io = BH_subTomoMeta_io(identifier, emc);
io.load_cycle(17);                                    % Load specific cycle
io.save_cycle(17, cycle_data);                        % Save specific cycle
io.load_geometry();                                   % Load geometry only
io.get_cycle_list();                                  % List available cycles
io.verify_checksums();                                % Verify all checksums
io.create_backup();                                   % Create backup
io.restore_from_backup(backup_id);                    % Restore backup
```

## Migration Strategy

### Step 1: Pre-Migration Validation

```matlab
function ready = BH_check_migration_readiness(project)
    ready = true;

    % Check current metadata integrity
    if ~BH_verify_metadata(project)
        fprintf('ERROR: Current metadata has issues\n');
        ready = false;
    end

    % Check disk space (need ~2x current size)
    % Check write permissions
    % Check MATLAB version compatibility
    % List any custom modifications

    return ready;
end
```

### Step 2: Migration Process

```matlab
function success = BH_migrate_project(project)
    fprintf('\n=== emClarity Metadata Migration ===\n');

    % 1. Pre-checks
    if ~BH_check_migration_readiness(project)
        error('Project not ready for migration');
    end

    % 2. Create backup
    backup_path = BH_backup_metadata(project);
    fprintf('Backup created: %s\n', backup_path);

    % 3. Convert to partitioned format
    options.verify_conversion = true;
    options.create_backup = false;  % Already done
    success = BH_convert_metadata_format(project, 'partitioned', options);

    % 4. Verify conversion
    if success
        fprintf('Migration successful!\n');
        fprintf('Update parameter file: metadata_format partitioned\n');
    else
        fprintf('Migration failed - restoring from backup\n');
        BH_restore_metadata(project, backup_path);
    end
end
```

### Step 3: Rollback Plan

If issues arise, rollback is simple:
1. Change parameter: `metadata_format legacy`
2. Or restore from backup: `BH_restore_metadata(project, backup_path)`
3. System automatically uses legacy format

## Testing Plan

### Unit Tests

```matlab
% Test suite: test/test_metadata_io.m
function test_metadata_io()
    % Test both formats
    test_legacy_format();
    test_partitioned_format();
    test_format_conversion();
    test_corruption_recovery();
    test_performance();
end

function test_legacy_format()
    % Test traditional .mat operations
    io = BH_subTomoMeta_io('test_project', struct('metadata_format', 'legacy'));

    % Test save/load
    test_data = create_test_metadata();
    io.save(test_data);
    loaded_data = io.load();

    assert(isequal(test_data, loaded_data), 'Legacy save/load failed');
end

function test_partitioned_format()
    % Test new STAR/JSON operations
    io = BH_subTomoMeta_io('test_project', struct('metadata_format', 'partitioned'));

    % Test cycle operations
    cycle_data = create_test_cycle();
    io.save_cycle(17, cycle_data);
    loaded_cycle = io.load_cycle(17);

    assert(isequal(cycle_data, loaded_cycle), 'Partitioned cycle save/load failed');
end
```

### Integration Tests

1. **Round-trip test**: .mat → STAR/JSON → .mat
2. **Concurrent access**: Multiple processes reading/writing
3. **Large dataset test**: >10GB metadata
4. **Corruption recovery**: Intentionally corrupt files
5. **Performance benchmark**: Time save/load operations

### Validation Tests

1. **RELION compatibility**: Load particles.star in RELION
2. **Python interop**: Read/write with starfile package
3. **Checksum verification**: All files match checksums
4. **Memory usage**: Confirm reduced memory footprint
5. **Backward compatibility**: Old code works with new format

### Production Testing

1. **Pilot project**: One production project with new format
2. **A/B testing**: Run same processing with both formats
3. **Performance monitoring**: Track save/load times
4. **Error monitoring**: Log any format-related errors
5. **User feedback**: Collect usability feedback

## Rollback Procedures

### Immediate Rollback (Parameter Change)

```bash
# Edit parameter file
sed -i 's/metadata_format partitioned/metadata_format legacy/' project.param
```

### Full Rollback (Format Conversion)

```matlab
% MATLAB rollback script
project = 'my_project';
BH_convert_metadata_format(project, 'legacy', struct('create_backup', true));
```

### Emergency Recovery

```matlab
% If both formats corrupted
backup_dir = '/backups/project_20241201/';
BH_restore_metadata('my_project', backup_dir);
```

## Export Functionality

### Supported Export Formats

#### RELION Export
- Generates `particles.star` with proper metadata columns
- Converts emClarity ZXZ to RELION ZYZ Euler angles
- Creates optics table with CTF parameters
- Handles coordinate transformations (pixels to Angstroms)

#### PEET Export
- Generates `.prm` parameter files
- Creates IMOD `.mod` model files
- Converts to PEET motive list format
- Handles missing wedge parameters

#### CryoSPARC Export
- Creates `.cs` files with particle metadata
- Converts Euler angles to CryoSPARC convention
- Generates project structure compatible with CryoSPARC import

### Angle Convention Conversions

```matlab
% emClarity uses ZXZ intrinsic rotations
% RELION uses ZYZ intrinsic rotations
% PEET uses ZYX intrinsic rotations

function [out_angles] = BH_convertEulerAngles(in_angles, from_convention, to_convention)
    % Convert to rotation matrix first
    R = convention_to_matrix(in_angles, from_convention);
    % Decompose to target convention
    out_angles = matrix_to_convention(R, to_convention);
end
```

## Validation Strategy

### External Test Datasets

1. **RELION Validation**
   - EMPIAR-10025: T20S proteasome
   - EMPIAR-10568: Apoferritin benchmark
   - EMPIAR-10204: Beta-galactosidase tutorial

2. **PEET Validation**
   - Microtubule doublet datasets
   - Boulder Lab tutorial data

3. **CryoSPARC Validation**
   - T20S proteasome subset (8GB)
   - Extensive validation workflow

### Validation Tests

```matlab
function run_validation_suite()
    % 1. Round-trip conversion tests
    test_relion_roundtrip();    % emClarity → RELION → emClarity
    test_peet_roundtrip();       % emClarity → PEET → emClarity

    % 2. Numerical precision tests
    validate_euler_conversions();
    validate_coordinate_transforms();

    % 3. External tool compatibility
    validate_starfile_compliance();  % Python starfile package
    validate_imod_models();          % IMOD model files

    % 4. Visual validation
    visualize_particle_orientations();
    generate_conversion_report();
end
```

## Performance Considerations

### Memory Usage Comparison

| Operation | Legacy (.mat) | Partitioned (STAR/JSON) | Improvement |
|-----------|--------------|-------------------------|-------------|
| Load current cycle | ~8 GB | ~500 MB | 16x |
| Save after small change | ~8 GB write | ~50 MB write | 160x |
| Load geometry only | ~8 GB | ~200 MB | 40x |

### I/O Performance

| Operation | Legacy | Partitioned | Notes |
|-----------|--------|-------------|-------|
| Full save | 45 sec | 5 sec | Only changed components |
| Full load | 30 sec | 35 sec | Slightly slower initially |
| Cycle load | 30 sec | 2 sec | Much faster for single cycle |
| Parallel access | Blocked | Concurrent | Multiple readers OK |

## Future Roadmap

### Version 1.1 (Q1 2025)
- [ ] Compression support for older cycles
- [ ] Memory-mapped file support
- [ ] Web API for metadata queries
- [ ] Real-time metadata viewer

### Version 1.2 (Q2 2025)
- [ ] Direct CryoSPARC integration
- [ ] RELION project import/export
- [ ] Metadata versioning system
- [ ] Automated backup scheduling

### Version 2.0 (Q3 2025)
- [ ] Full Python implementation
- [ ] REST API server
- [ ] Cloud storage support
- [ ] Distributed metadata system

## Appendix A: Error Codes

| Code | Description | Resolution |
|------|-------------|------------|
| E001 | Format detection failed | Check index.json and .mat existence |
| E002 | Checksum mismatch | Run BH_verify_metadata() |
| E003 | Missing cycle data | Check cycles/ directory |
| E004 | Incompatible version | Update emClarity |
| E005 | Insufficient permissions | Check file permissions |
| E006 | Corrupted STAR file | Run BH_repair_metadata() |

## Appendix B: Configuration Options

```matlab
% Complete list of metadata parameters
metadata_format = 'partitioned';     % 'legacy' or 'partitioned'
auto_migrate_metadata = 0;           % Auto-convert on first load
verify_metadata_saves = 1;           % Verify after each save
metadata_backup_count = 3;           % Number of backups to keep
metadata_compression = 'none';       % 'none', 'gzip', 'bzip2'
metadata_cache_size = 1000;         % MB to cache in memory
parallel_metadata_io = 1;           % Use parallel I/O
metadata_checksum_type = 'md5';     % 'md5', 'sha256', 'none'
```

## Appendix C: Troubleshooting

### Common Issues and Solutions

**Issue: "Cannot find metadata" error**
- Check metadata_format parameter
- Verify file/directory exists
- Run format detection: `BH_detect_metadata_format(project)`

**Issue: Slow loading times**
- Check if loading unnecessary cycles
- Consider using cache: `io.enable_cache(true)`
- Verify network if using remote storage

**Issue: Save verification failures**
- Check disk space
- Verify write permissions
- Try disabling parallel I/O
- Check for antivirus interference

**Issue: STAR file compatibility**
- Ensure column names match RELION conventions
- Check for special characters in strings
- Verify numeric precision settings

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024-12-01 | emClarity Team | Initial plan |
| | | | |

## References

1. [RELION STAR format documentation](https://relion.readthedocs.io)
2. [TeamTomo starfile package](https://teamtomo.org/starfile)
3. [CryoEM data standards](https://www.ebi.ac.uk/emdb/documentation)
4. [MATLAB MAT-file format](https://www.mathworks.com/help/matlab/import_export/mat-file-versions.html)

---
*This document is a living specification and will be updated as the implementation progresses.*