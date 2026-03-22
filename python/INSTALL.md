# emClarity Python Installation Guide

## Quick Setup

1. **Ensure you're in the virtual environment**:
   ```bash
   cd /sa_shared/git/emClarity
   source .venv/bin/activate
   ```

2. **Install core dependencies**:
   ```bash
   cd python
   pip install -r requirements.txt
   ```

3. **Install development tools** (optional but recommended):
   ```bash
   pip install -r requirements-dev.txt
   ```

4. **Verify installation**:
   ```bash
   python check_environment.py
   ```

## Dependency Categories

### Core Dependencies (Required)

These packages are **required** for emClarity Python functionality:

- **numpy, scipy**: Scientific computing foundation
- **mrcfile**: MRC file I/O (cryo-EM standard format)
- **jsonschema**: Parameter validation
- **cupy-cuda12x**: GPU acceleration (essential for performance)
- **matplotlib**: Plotting and visualization
- **pillow**: Image processing (imports as `PIL`)

### Development Tools (Recommended)

These tools are helpful for development but not required for runtime:

- **pytest**: Testing framework
- **coverage**: Test coverage reporting
- **black**: Code formatting
- **flake8**: Code linting

## CUDA Version Notes

The default requirements include `cupy-cuda12x` for CUDA 12.x support. If you have a different CUDA version:

- **CUDA 11.x**: Replace with `cupy-cuda11x>=11.0.0`
- **CUDA 10.x**: Replace with `cupy-cuda10x>=10.0.0`

Check your CUDA version:
```bash
nvcc --version
```

## Troubleshooting

### Common Issues

1. **CuPy installation fails**: 
   - Check CUDA version compatibility
   - Ensure CUDA toolkit is properly installed
   - Consider using conda: `conda install cupy`

2. **Import errors**:
   - Verify virtual environment is activated
   - Run `python check_environment.py -v` for detailed status

### Environment Verification

Quick check:
```bash
python check_environment.py --quiet
```

Detailed status:
```bash
python check_environment.py --verbose
```

## Performance Notes

- **GPU acceleration**: emClarity relies heavily on GPU processing. Ensure CuPy is working correctly.
- **Memory management**: Large tilt series require significant RAM. Monitor memory usage during processing.
- **Parallel processing**: emClarity can utilize multiple GPUs when available.
