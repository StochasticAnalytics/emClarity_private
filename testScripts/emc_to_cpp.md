# MATLAB to C++ Conversion Plan: emClarity Project

## 1. Project Overview & Goals

*   **Project**: emClarity MATLAB project.
*   **Focus of this Plan**: Conversion of the main entry point script (assumed to be `emClarity.m` or a similar top-level script) and subsequently its sub-programs.
*   **Overall Goal**: Convert the emClarity project from MATLAB to C++ to potentially improve performance, reduce licensing dependencies, and facilitate integration with other C++ tools.
*   **Strategy**: Phased conversion, starting with the main program and progressively converting its core sub-modules.

## 2. Analysis of the Main Program (`emClarity.m`)

*(This section will require details about `emClarity.m`)*

*   **Purpose**:
    *   Acts as the primary user interface or entry point.
    *   Parses user commands/arguments.
    *   Dispatches tasks to various sub-programs or functions within the emClarity suite.
*   **Key Functionalities**:
    *   Argument parsing (e.g., identifying which sub-program to run and its parameters).
    *   Calling/dispatching to other MATLAB scripts/functions (e.g., `BH_synthetic_mapBack.m`, alignment routines, classification, etc.).
    *   Global setup or environment configuration.
    *   Help system / usage information.
*   **Inputs**:
    *   Command-line arguments or function parameters.
    *   Parameter files.
*   **Outputs**:
    *   Messages to the console.
    *   Calls to sub-programs which produce their own outputs.

## 3. Dependency Analysis (from `emClarity.m` perspective)

*   **Primary Dependencies**:
    *   List of core MATLAB scripts/functions directly called by `emClarity.m` (e.g., `BH_align_subTomos`, `BH_tomoCPR_cluster`, `BH_synthetic_mapBack`, etc.).
    *   Parameter parsing functions (e.g., `BH_parseParameterFile`).
*   **MATLAB Toolboxes**:
    *   Identify any toolboxes used directly by `emClarity.m` or its immediate utility functions.
*   **Shared Utility Functions**:
    *   Common helper functions used for path management, string operations, etc.

## 4. C++ Conversion Strategy for `emClarity.m`

*   **C++ Main Executable**:
    *   The C++ equivalent of `emClarity.m` will be a `main()` function in a C++ executable.
*   **Argument Parsing**:
    *   Implement robust command-line argument parsing.
    *   Libraries: `cxxopts`, `CLI11`, `Boost.Program_options`, or a custom solution.
    *   The goal is to replicate the way `emClarity.m` receives and interprets user commands.
*   **Dispatching Logic**:
    *   Based on parsed arguments, the C++ `main` function will call the C++ equivalents of the MATLAB sub-programs.
    *   This might involve a series of `if/else if` statements or a map of command strings to function pointers/functors.
*   **Parameter Handling**:
    *   The C++ version will need to read and parse parameter files, similar to `BH_parseParameterFile.m`. This module should be one of the first to be converted.
*   **Build System**:
    *   CMake is recommended for managing the C++ project, its modules, and dependencies.

## 5. Modular Conversion Approach & Prioritization

1.  **Core Utilities & Parameter Parsing**:
    *   Convert `BH_parseParameterFile.m` to a C++ equivalent.
    *   Convert essential utility functions (string manipulation, file system interaction).
2.  **Main Dispatcher (`emClarity.cpp`)**:
    *   Develop the C++ `main` function with argument parsing and basic dispatching stubs.
3.  **Sub-Program Conversion (Phased)**:
    *   Identify a key sub-program (e.g., `BH_synthetic_mapBack.m` as previously discussed, or another core module).
    *   Create a detailed conversion plan for that sub-program (similar to the one we started for `BH_synthetic_mapBack.m`).
    *   Convert and test the sub-program in C++.
    *   Integrate the converted C++ sub-program with the C++ main dispatcher.
    *   Repeat for other sub-programs.
    *   **Priority List (Example - to be refined based on `emClarity.m` structure)**:
        *   Parameter parsing (`BH_parseParameterFile`)
        *   `BH_synthetic_mapBack` (synthetic data generation and basic alignment)
        *   Core alignment routines
        *   Classification routines
        *   Other reconstruction/processing modules

## 6. C++ Libraries and Tools

*   **Standard Libraries**: C++17 or newer for `<filesystem>`, `<string>`, `<vector>`, etc.
*   **Image Processing**: OpenCV, ITK, or existing custom C++ image libraries.
*   **MRC I/O**: `libmrc` or custom implementation.
*   **FFT**: FFTW (CPU), cuFFT (GPU).
*   **Linear Algebra**: Eigen.
*   **Parallelism**: OpenMP, C++ `<thread>`, TBB.
*   **Logging**: spdlog, glog.

## 7. Testing and Validation Strategy

*   **Unit Tests**: For individual C++ functions and classes.
*   **Integration Tests**: For modules and the interaction between the main dispatcher and sub-programs.
*   **Comparison with MATLAB**: Output data (images, metadata files, logs) from C++ versions should be compared against outputs from the original MATLAB code using the same input datasets. Numerical precision differences should be anticipated and managed.

---

To proceed with detailing this plan, especially sections 2 and 3, please provide the content of `emClarity.m` or describe its main functionalities and how it calls other scripts.