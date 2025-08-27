# emClarity GUI

A modern PySide6-based graphical user interface for emClarity, the cryo-electron microscopy processing software.

## Features

- **Modern Interface**: Clean, responsive design optimized for high-DPI displays
- **Version Display**: Shows the current emClarity version and installation path
- **Command Categories**: Organized commands by functional groups
- **Parameter Input**: Smart parameter forms with file browsers and validation
- **Real-time Output**: Live command execution with formatted output
- **Environment Monitoring**: Detailed environment and configuration information
- **GPU Awareness**: Clear indication of GPU-required commands

## Quick Start

### Option 1: Using the launcher script (Recommended)
```bash
# From the emClarity root directory
./gui/run_gui.sh
```

### Option 2: Manual setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install required packages
pip install PySide6 typing_extensions

# Launch GUI
python gui/launcher.py
```

## System Requirements

- Python 3.8 or later
- Qt5/Qt6 support (automatically installed with PySide6)
- Display server (X11 or Wayland) for GUI operation
- Existing emClarity installation

## Available Commands

The GUI provides access to all emClarity commands organized by category:

### System Commands
- **help**: Show available commands
- **check**: System dependency verification
- **benchmark**: Performance testing
- **experimental**: Access experimental features

### Project Setup
- **init**: Initialize new project from template matching results
- **segment**: Define reconstruction subregions

### Alignment
- **autoAlign**: Automatic tilt-series alignment
- **alignRaw**: Align references against individual subtomograms

### Analysis
- **avg**: Average subtomograms
- **fsc**: Calculate Fourier Shell Correlation
- **mask**: Create and apply masks

### CTF Processing
- **ctf**: CTF estimation, refinement, and correction

### Classification
- **pca**: Principal Component Analysis
- **cluster**: Cluster subtomogram populations

### Template Matching
- **templateSearch**: Global template matching
- **cleanTemplateSearch**: Clean search results

### Reconstruction
- **reconstruct**: Volume reconstruction
- **tomoCPR**: Tomogram constrained projection refinement

### Utility Commands
- **calcWeights**, **skip**, **rescale**, **geometry**
- **removeNeighbors**, **removeDuplicates**, **combineProjects**
- **getActiveTilts**, **montage**
