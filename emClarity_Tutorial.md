# emClarity v1.5.3.10 Tutorial

## Table of Contents

1. [How to use this guide](#how-to-use-this-guide)
2. [The project directory](#the-project-directory)
3. [Get your data ready](#get-your-data-ready)
4. [Workflow](#workflow)
5. [Initial tilt-series alignment](#initial-tilt-series-alignment)
6. [Defocus estimate](#defocus-estimate)
7. [Select the sub-regions](#select-the-sub-regions)
8. [Picking](#picking)
9. [Initialize the project](#initialize-the-project)
10. [CTF 3D](#ctf-3d)
11. [Averaging](#averaging)
12. [Alignment](#alignment)
13. [TomoCPR](#tomocpr)
14. [Classification](#classification)
15. [Final map](#final-map)
16. [Algorithms](#algorithms)

---

## How to use this guide

### Run the jobs

Our main objective in writing this tutorial is to help you get started using **emClarity** for processing sub-tomogram data as quickly as possible. To begin, we will not introduce all of the methods that **emClarity** puts at your disposal, instead focusing on core features and concepts. If at any point you are confused, or something seems to not work as you expect, you might find more information on the [wiki](https://github.com/bHimes/emClarity/wiki); feel free to also search the mailing list archive, or post new questions to the community forum, hosted on [google groups](https://groups.google.com/forum/#!forum/emclarity), should you have any questions you cannot resolve on your own.

> **Tip**: To display every procedure available, run `emClarity help` from the command line.

### Algorithms

The **emClarity** source code is available on [github](https://github.com/bHimes/emClarity/tree/LTS_version_1_5_0), and we encourage you to go through the code to look at the algorithms directly. Because **emClarity** is frequently being updated, this can be a great way to see what's going on behind the scenes.

Section [Algorithms](#algorithms) contains descriptions of the algorithms for each section presented in this tutorial. Please keep in mind that these are simplified descriptions of what **emClarity** is actually doing, as we often don't mention the details that were implemented to make the code more efficient.

### Installation and Requirements

Information about the [installation](https://github.com/bHimes/emClarity/wiki/Installation) and the software and hardware [requirements](https://github.com/bHimes/emClarity/wiki/Requirements) is available [online](https://github.com/bHimes/emClarity/wiki).

### Parameter files

**emClarity** is currently using a parameter file to manage inputs. You can find an example [here](https://github.com/bHimes/emClarity/blob/master/docs/exampleParametersAndRunScript/param0.m).

### System parameters

Your parameter files should have the following parameters:

| Parameter | Description |
|-----------|-------------|
| `nGPUs` * | The number of visible GPUs. **emClarity** will try to use them in parallel as much as possible. If this number doesn't correspond to the actual number of GPUs available, **emClarity** will ask you to either adjust this number to match the number of GPUs, or modify the environment variable `CUDA_VISIBLE_DEVICE` to make some GPUs invisible to **MATLAB**. |
| `nCpuCores` * | The maximum number of processes to run simultaneously. In most **emClarity** programs, the number of processes launched in parallel on a single GPU is equal to `nCpuCores`/`nGPUs`. If your devices run out of memory, it is likely that you will have to decrease the number of processes per device, thus decreasing this parameter. |
| `fastScratchDisk` * | Path of the optional temporary cache directory, used by `ctf 3d` and `tomoCPR`. This directory is only temporary and is moved back inside the project directory at the end of the execution. We recommend setting this to the fastest storage you have available. If left empty, `ctf 3d` and `tomoCPR` will use directly the project cache directory. |

*Required parameters are marked with *

---

## The project directory

**emClarity** should be run from the "project directory", referred to as `<projectDir>`. Every output will be saved in this directory, ignoring the temporary cache set by the `fastScratchDisk` parameter. As we go along, we will present in more detail each sub-directory and their content.

### Directory Structure

- **`<projectDir>`**: Contains every input file and input directories **emClarity** needs and every outputs. As most of the **emClarity** programs are project based, you should run **emClarity** from this directory.

- **`<projectDir>/rawData`**: **(User created)** Contains the original raw tilt-series data (`*.mrc`, `*.st`) and associated files (`*.rawtlt`) that will be used as input for `autoAlign`. This is where you should place your downloaded or collected tilt-series before starting the workflow.

- **`<projectDir>/fixedStacks`**: **(Created by `autoAlign` or user)** Contains the raw (not aligned) tilt-series (`*.fixed`) and the initial tilt-series alignment files (`*.xf`, `*.tlt` and optionally `*.local` and `*.erase`). This directory is automatically created and populated by `emClarity autoAlign`, or manually created if you're starting with pre-aligned data from **ETomo**.

- **`<projectDir>/fixedStacks/ctf`**: Created by `ctf estimate` and updated after tilt-series refinements by `ctf update`. Contains the radial averages (`*_psRadial1.pdf`) and stretched power spectrum (`*_PS2.mrc`) computed by `ctf estimate`, as well as the tilt-series metadata (`*_ctf.tlt`), used throughout the entire workflow and containing in particular the dose-scheme and defocus estimate of each view.

- **`<projectDir>/aliStacks`**: Created by `ctf estimate` and updated after tilt-series refinement by `ctf update`. Contains the aligned, bead-erased tilt-series. These stacks are mostly used by `ctf 3d` to compute the tomograms at different binning.

- **`<projectDir>/cache`**: Created and updated by **emClarity** when needed, usually during `ctf 3d`. Store any stack or reconstruction for the current binning. If a reconstruction (`*.rec`) is present at the current binning, `ctf 3d` will skip its reconstruction.

- **`<projectDir>/convmap`**: When creating a project with `init`, **emClarity** will look in this directory to grab outputs from `templateSearch`. If you pick your particles with **emClarity**, the content of this directory is generated by `templateSearch`.

- **`<projectDir>/recon`**: Holds the information for each reconstructed sub-region in a given tilt-series. The `*_recon.coords` files are read into the metadata created by `init` and is used whenever a tomogram is made or whenever the coordinates of a sub-region is needed.

- **`<projectDir>/<binX>`**: **emClarity** does not directly use this directory, but it is used by `recScript2.sh` to define the sub-regions boundaries and create `<projectDir>/recon`.

- **`<projectDir>/FSC`**: Created and updated during subtomogram averaging. Contains the spherical and conical FSCs for each cycle (`*fsc_GLD.txt` and `*fsc_GLD.pdf`), as well as the Figure-Of-Merit used for filtering (`*cRef_GLD.pdf`) and the CTF-corrected volume used for FSC calculations.

- **`<projectDir>/alignResume`**: Contains the results of the subtomogram alignments, for each cycle. **emClarity** will look at this directory before aligning the particles from a given sub-region. If the results for this sub-region, at the current cycle, are already saved, it will skip the alignment.

---

## Get your data ready

In this tutorial, we will use the apoferritin tomography dataset deposited on [EMPIAR-11273](https://www.ebi.ac.uk/pdbe/emdb/empiar/entry/11273/). You should be able to get a sub-3Å map from this tutorial. Apoferritin is an excellent choice for learning subtomogram averaging due to its high octahedral symmetry, which makes processing faster and typically yields higher resolution results.

### Tutorial Dataset

| Aspect | Description |
|--------|-------------|
| **Sample** | Apoferritin (octahedral symmetry, ~12nm diameter) |
| **Tilt-series count** | 100 tilt-series (TS_12 to TS_123) |
| **Tilt-scheme** | Hagen dose-symmetric, ±48°, 3° increment, 115.5e/Å² total exposure |
| **Instruments** | Krios at 300kV, Gatan K3 camera, 0.729Å/pix calibrated pixel size |
| **Defocus range** | -1 to -3 μm |
| **Expected result** | Sub-3Å reconstruction |

> **Note**: This dataset uses EER format movies that need to be converted to tilt-series. The high symmetry of apoferritin (octahedral) makes it ideal for tutorial purposes as it processes much faster than asymmetric particles like ribosomes. With 100 tilt-series, this provides excellent statistics for high-resolution reconstruction.

### Setting up the project directory

Before starting, create your project directory and the initial `rawData` subdirectory:

```bash
# Create your project directory
mkdir -p /path/to/your/project
cd /path/to/your/project

# Create rawData directory for your input tilt-series
mkdir rawData

# For EMPIAR-11273, the data is available in EER format and needs to be converted
# The dataset contains 100 tilt-series (TS_12 to TS_123)
# Copy or link the converted tilt-series to rawData/
# Each tilt-series should be named like TS_012.st, TS_013.st, etc.
```

The `fixedStacks` directory will be automatically created by `emClarity autoAlign` in the next step. If you're starting with pre-aligned data from **ETomo**, you would manually create and populate the `fixedStacks` directory instead.

> **Data preparation note**: The EMPIAR-11273 dataset contains EER movies that need motion correction and tilt-series generation. Use tools like RELION's `relion_convert_to_tiff` or IMOD's `alignframes` to convert the EER data to tilt-series stacks before starting the emClarity workflow.

---

## Workflow

You will often find that it is much easier to organize every **emClarity** calls into one script. This script has two main purposes. First, it keeps track of the jobs that have been run (you can also find this information into the `logFile` directory). This is often useful to visualize the global picture and it might help you to remember how you got your final reconstruction. Second, it is a script, so you can use it directly to run **emClarity**, making the workflow much simpler.

### Example Workflow Script

```bash
#!/bin/bash

# Simple function to stop on *most* errors
check_error() {
    sleep 2
    if tail -n 30 ./logFile/emClarity.logfile |\
       grep -q "Error in emClarity" ; then
        echo "Critical error found. Stopping the script."
        exit
    else
        echo "No error detected. Continue."
    fi
}

# Change binning with tomoCPR
run_transition_tomoCPR() {
    emClarity removeDuplicates param${i}.m ${i}; check_error
    emClarity tomoCPR param${i}.m ${i}; check_error
    emClarity ctf update param$((${i}+1)).m; check_error
    emClarity ctf 3d param$((${i}+1)).m; check_error
}

# Basic alignment cycle
run_avg_and_align() {
    emClarity avg param${i}.m ${i} RawAlignment; check_error
    emClarity alignRaw param${i}.m ${i}; check_error
}

# autoAlign
# ctf estimate
# templateSearch

# Create metadata and reconstruct the tomograms
emClarity init param0.m; check_error
emClarity ctf 3d param0.m; check_error

# First reconstruction - check if that looks OK.
emClarity avg param0.m 0 RawAlignment; check_error
emClarity alignRaw param0.m 0; check_error

# Bin 3
for i in 1 2 3 4; do run_avg_and_align; done

# Run tomoCPR at bin3 using cycle 4 and then switch to bin2
run_transition_tomoCPR

# Bin 2
for i in 5 6 7 8 9; do run_avg_and_align; done

# Run tomoCPR at bin2 using cycle 9 and then switch to bin1
run_transition_tomoCPR

# Bin 1
for i in 10 11 12 13 14; do run_avg_and_align; done

# Last cycle: merge the datasets
emClarity avg param15.m 15 RawAlignment; check_error
emClarity avg param15.m 15 FinalAlignment; check_error
emClarity reconstruct param15.m 15;
```

This example doesn't have a classification, but as explained in the classification section, classifications are encapsulated in their own cycles, so you can run them anytime you want between two cycles.

In our experience, it is usually good practice to keep a close eye on how the half-maps and FSC evolves throughout the workflow, specially before deciding to change the sampling. Moreover, the tilt-series refinement is completely optional and you can simply change the binning by running `ctf 3d`, as opposed to `run_transition_tomoCPR`.

> **Tip**: It is best practice to work the whole way through the workflow with the smallest data-set as possible and once you checked that everything holds, then process your full data. The same approach may be taken with this tutorial; it should be possible to obtain a low-resolution but recognizable 70S ribosome with only two or three of the tilt-series.

---

## Initial tilt-series alignment

### Objectives

The first step of the workflow consists into finding an initial alignment for the raw tilt-series, that is the tilt, rotation and shift for each image within the series. After the alignment, the tilt-axis must be parallel to the y-axis. This alignment can be refined later on using the particles positions (tomoCPR section).

### With emClarity

**emClarity** can align the tilt-series for you using its `autoAlign` procedure. This procedure is based on the **IMOD** programs **tilt** and **tiltalign** and offers an automatic way of aligning tilt-series, with or without gold beads.

#### Run

As with every **emClarity** programs, you should run the next commands in the project directory. The `autoAlign` routine has the following signature:

```
emClarity autoAlign <param> <stack> <rawtlt> <rot>
```

Where:
- `<param>` is the name of the parameter file
- `<stack>` is the tilt-series to align (e.g. `tilt1.st`)
- `<rawtlt>` is a text file containing the raw tilt-angles (e.g. `tilt1.rawtlt`), in degrees
- `<rot>` is the image rotation (tilt-axis angle from the vertical), in degrees, as specified in **ETomo**

For example, to run `autoAlign` on the first tilt-series of the tutorial:

```
emClarity autoAlign param.m TS_012.st TS_012.rawtlt 0
```

For this apoferritin dataset, you may need to determine the appropriate rotation angle. You can check the first few tilt-series manually or use a small rotation angle since the data acquisition was well-controlled.

#### Outputs

**emClarity** creates and organizes the necessary files it needs to run the next step of the workflow. The goal here is to check whether or not the alignment is good enough to start with and the easiest way is to look at `fixedStacks/<prefix>_3dfind.ali` or `fixedStacks/<prefix>_binX.ali`.

If you are familiar with **ETomo**, then you can of course also look at the log files saved in `emC_autoAlign_<prefix>`. For instance, to visually check the fiducial beads:

```
3dmod \
emC_autoAlign_<prefix>/<prefix>_X_3dfind.ali \
emC_autoAlign_<prefix>/<prefix>_X_fitbyResid_X.fid
```

### With ETomo

If you don't want to use `autoAlign`, we do recommend using the (fiducial) alignment procedure from the **ETomo** pipeline. One powerful option of this pipeline is to be able to solve for a series of local alignments using subsets of fiducial points, which can then be used by **emClarity**, via the IMOD **tilt** program, to reconstruct the tomograms.

For each tilt-series, **emClarity** needs:

- **`<prefix>.fixed`**: the raw (not aligned) tilt-series. These should not be exposure-filtered nor phase flipped.

- **`<prefix>.xf`**: the file with alignment transforms to apply to the `<prefix>.fixed` stacks. This file should contain one line per view, each with a linear transformation specified by six numbers.

- **`<prefix>.tlt`**: the file with the solved tilt angles. One line per view, angles in degrees.

- **(optional) `<prefix>.local`**: the file of local alignments. This file is similar to the `<prefix>.xf` file, but contains one transformation per view and per patch.

- **(optional) `<prefix>.erase`**: the file with the coordinates (in pixel) of the fiducial beads to erase before ctf estimation.

These files should be copied to `<projectDir>/fixedStacks`.

> **Tip**: You don't necessarily need to copy the tilt-series to the `fixedStacks` directory; use soft links: `ln -s <...>/<prefix>.mrc <...>/fixedStacks/<prefix>.fixed`

---

## Defocus estimate

### Objectives

There are two main objectives. First, create the aligned, optionally bead-erased, weighted stacks. Weighted refers to the per-view weighting applied by **emClarity** to take into account the frequency dependent drop in SNR due to radiation damage, an isotropic drop in SNR due to increased thickness with the tilt-angle causing inelastic scattering losses and optionally also for the cosine dose-scheme, also referred as Saxton scheme. These stacks will be then used to compute the tomograms at later stages. The second objective is to estimate the defocus of each view of the stack (two defoci and the astigmatism angle, per view).

### Run

The `ctf estimate` routine has the following signature:

```
emClarity ctf estimate <param> <prefix>
```

`<param>` is the name of the parameter file (e.g. `param_ctf.m`), and `<prefix>` is the base-name of the tilt-series in `<projectDir>/fixedStacks` you wish to process.

For example, to run `ctf estimate` on the first tilt-series of the tutorial:

```
emClarity ctf estimate param_ctf.m TS_012
```

If you have many tilt-series and you don't want to run all of them individually, you can do the following:

```bash
#!/bin/bash
for stack in fixedStacks/*.fixed; do
    prefix=${stack#fixedStacks/}
    emClarity ctf estimate param_ctf.m ${prefix%.fixed}
done
```

For the apoferritin dataset, you generally won't need to remove specific images, but if needed, `ctf estimate` can remove images from the stack. For instance, to remove the first view:

```
emClarity ctf estimate param_ctf.m TS_012 1
```

### Outputs

You should make sure the tilt-series "looks aligned" and the average defocus (at the tilt axis) was correctly estimated. The best way to check:

1. Open `aliStacks/<prefix>_ali1.fixed` and go through the views. The views should be aligned to the tilt-axis, which must be parallel to the Y axis (so vertical if you use **3dmod**). If an `*.erase` file was available for this tilt-series, the beads should be removed.

2. Open `fixedStacks/ctf/<prefix>_ali1_psRadial_1.pdf` and check that the theoretical CTF estimate (green) matches the radial average of the power spectrum of the tilt-series (black). Note that the amplitude doesn't matter here, the phase on the other hand, does.

3. If they don't match, it is likely that you will need to adjust the `defEstimate` and `defWindow` parameters. Open `fixedStacks/ctf/*_ccFIT.pdf`, which plots the cross-correlation score as a function of defocus. There is often an obvious correct peak, smoothly rising and falling. If you don't see this peak, try to change the sampled defoci with `defEstimate` ± `defWindow` and re-run `ctf estimate`.

---

## Algorithms

### Naming conventions

There is a lot of things to cover and it is often easier to use abbreviations (CTF, FSC, CCC, etc.) and symbols to refer to something.

Indexes are subscripts, e.g. the p-th subtomogram is referred as **s**_p. This works with multiple indexes, e.g. the p-th subtomogram rotated by the r-th rotation is referred as **s**_p,r. Labels are subscripts as well, e.g. if we want to specify that the subtomograms are in the reference frame, we would write **s**_ref.

### Euler angles conventions

The φ, θ, ψ Euler angles used by **emClarity** describe a z-x-z active intrinsic rotations of the particles coordinate system. That is to say, to switch the particles from the microscope frame to the reference frame, the basis vectors of the subtomograms are rotated (positive anti-clockwise) around z, the new x, and the new z axis.

The microscope frame defines the coordinate system of the microscope, where the electron beam is the z axis. When the subtomograms are extracted from their tomogram, they are in the microscope frame. The reference frame is the coordinate system attached to the reconstruction, i.e. the subtomogram average and is usually set during the particle picking.

### Linear transformations in Fourier space

Linear transformations are often applied in Fourier space directly. It might be useful to write down a few useful properties of the Fourier transforms.

- **Shift**: Shifting an image in real space is equivalent to applying a complex phase shift to its frequency spectrum
- **Magnification**: Magnifying an image by a factor a is equivalent to magnifying its frequency spectrum by 1/a
- **Rotation**: Rotating an image by an angle Θ in real space is the same as rotating its frequency spectrum by the same angle Θ

---

## Select the sub-regions

The purpose of this step is to define sub-regions within each tilt-series that will be reconstructed as tomograms. This is typically done using IMOD's reconstruction scripts to create appropriate coordinate files that define the boundaries of each sub-region.

---

## Picking

### Objectives

It's time to pick the particles, i.e. the subtomograms. There are many ways to pick particles, but they usually all rely on the tomograms. Each particle can be described by its x, y, z coordinates and φ, θ, ψ Euler angles. **emClarity** has a template matching routine that can pick the subtomograms for you, but it requires a template.

### Run

#### Preparing the template

Before running `templateSearch`, you need to prepare a template. This template should have the same pixel size as the `PIXEL_SIZE` parameter. It doesn't need to be low-pass filter, as **emClarity** will do it internally. If you want to re-scale a map, you can run:

```bash
emClarity rescale <in> <out> <inPixel> <OutPixel> <method>
```

`<in>` and `<out>` are the name of your template and the output name of the re-scaled template, respectively. `<inPixel>` is the pixel size of your template and `<OutPixel>` is the desired pixel size. `<method>` can be "GPU" or "cpu".

> **Note**: For this tutorial, you'll need an apoferritin template. Apoferritin templates are readily available from the PDB (e.g. PDB ID: 2FHA) or EMDB, and can be filtered to the appropriate resolution for initial template matching.

#### Generating the tomograms

The tomograms use for the template matching are CTF multiplied. To generate them, simply run:

```bash
emClarity ctf 3d <param> templateSearch
```

This will generate a tomogram for every subregion defined in the `recon/*.coords` files.

#### Template matching

The `templateSearch` routine has the following signature:

```bash
emClarity templateSearch <param> <prefix> <region> <template> <symmetry> <GPU>
```

Where:

- `<param>` is the name of the parameter file
- `<prefix>` is the base-name of the tilt-series in `<projectDir>/aliStacks` to process
- `<region>` is the number of the sub-region to process
- `<symmetry>` is not used but kept for backward compatibility
- `<GPU>` is the GPU ID to use (starting from 1)

For example, to run `templateSearch` on the first tilt-series of the tutorial, where we defined 2 sub-regions:

```bash
# First region
emClarity templateSearch param.m TS_012 1 apoferritin_template.mrc O 1
# Second region
emClarity templateSearch param.m TS_012 2 apoferritin_template.mrc O 1
```

Note the use of "O" for octahedral symmetry instead of "C1" - this is one of the key advantages of using apoferritin.

### Outputs

The primary goal now is to remove false positives due to strong homogeneous features like carbon edges, membranes, or residual gold beads. The template matching produces a "cumulative correlation" map, which can be opened alongside a 3d model of the selected peaks.

---

## Initialize the project

### Objectives

This step is creating the project metadata that will be used throughout the processing. There are three main things that **emClarity** will do. First, it will grab the sub-region coordinates in `/recon/<prefix>.coords`. Second, it will grab the tilt-series CTF estimate stored in `fixedStacks/ctf/<prefix>_ali1_ctf.tlt`. Lastly, it will grab the particle coordinates from `convmap/<prefix>_<nb>_<bin>.csv`. As explained in the last section, peaks can be removed from the `.csv` files using the corresponding `.mod` file.

> **Note**: Once ran, these files are ignored and will not be used again. If one needs to modify some of the above-mentioned information, this step must be re-run for the modification to be effective.

### Run

The `init` routine has the following signature:

```bash
emClarity init <param>
```

where `<param>` is the parameter file name.

### Outputs

The main output is of course the output file `<subTomoMeta>.mat`. This step should only take a few seconds to run and it will output to the terminal, the total number of particles and the number of particles before and after cleaning, for each sub-region.

---

## CTF 3D

This step reconstructs the tomograms using CTF correction. **emClarity** will create 3D CTF-corrected tomograms from the aligned tilt-series.

### Run

```bash
emClarity ctf 3d <param>
```

This will reconstruct tomograms for all defined sub-regions at the current binning level.

---

## Averaging

This step performs subtomogram averaging to create a reference structure from the picked particles.

### Run

```bash
emClarity avg <param> <cycle> <type>
```

Where:

- `<param>` is the parameter file
- `<cycle>` is the cycle number
- `<type>` can be "RawAlignment" or "FinalAlignment"

---

## Alignment

This step aligns individual subtomograms to the current reference.

### Run

```bash
emClarity alignRaw <param> <cycle>
```

Where:

- `<param>` is the parameter file
- `<cycle>` is the cycle number

---

## TomoCPR

TomoCPR (Tomogram-based Contrast Transfer Function Correction and Pose Refinement) refines the tilt-series alignment using the particle positions.

### Run

```bash
emClarity tomoCPR <param> <cycle>
```

This is typically run before changing binning levels to improve the alignment.

---

## Classification

Classification allows you to separate different conformational states or remove bad particles.

### Run

```bash
emClarity classify <param> <cycle>
```

Classifications are encapsulated in their own cycles and can be run between regular averaging cycles.

---

## Final map

The final step creates the highest resolution map by merging data from the final alignment cycles.

### Run

```bash
emClarity avg <param> <cycle> FinalAlignment
emClarity reconstruct <param> <cycle>
```

## Quick Reference Commands

### Initial Setup

```bash
# Align tilt-series
emClarity autoAlign param.m TS_012.st TS_012.rawtlt 0

# Estimate CTF
emClarity ctf estimate param_ctf.m TS_012

# Template search
emClarity templateSearch param.m TS_012 1 apoferritin_template.mrc O 1

# Initialize project
emClarity init param0.m
```

### Main Processing Loop
```bash
# Reconstruct tomograms
emClarity ctf 3d param0.m

# Average and align (repeat for multiple cycles)
emClarity avg param0.m 0 RawAlignment
emClarity alignRaw param0.m 0

# Tilt-series refinement (optional)
emClarity tomoCPR param0.m 0
emClarity ctf update param1.m
```

### Final Steps
```bash
# Final averaging
emClarity avg param15.m 15 FinalAlignment
emClarity reconstruct param15.m 15
```

This tutorial provides a comprehensive guide to using **emClarity** for subtomogram processing. For more detailed information about specific algorithms and advanced features, please refer to the [emClarity wiki](https://github.com/bHimes/emClarity/wiki) and the [source code repository](https://github.com/bHimes/emClarity).

## Additional Resources

- [emClarity GitHub Repository](https://github.com/bHimes/emClarity)
- [emClarity Wiki](https://github.com/bHimes/emClarity/wiki)
- [Google Groups Forum](https://groups.google.com/forum/#!forum/emclarity)
- [Installation Guide](https://github.com/bHimes/emClarity/wiki/Installation)
- [Requirements](https://github.com/bHimes/emClarity/wiki/Requirements)

---

*This tutorial was generated from the original LaTeX tutorial repository and converted to Markdown format for easier reference and integration.*

