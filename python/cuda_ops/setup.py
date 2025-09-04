"""
setup.py for emClarity Python CUDA operations

Build system for CUDA-accelerated Python extensions.
Handles compilation of CUDA kernels and Python packaging.

Author: emClarity Python Conversion
Date: September 2025
"""

import os
import subprocess

from setuptools import find_packages, setup


# Check for CUDA availability
def check_cuda():
    """Check if CUDA is available and get version."""
    try:
        result = subprocess.run(
            ["nvcc", "--version"], capture_output=True, text=True, check=True
        )
        print("CUDA compiler found:")
        for line in result.stdout.split("\n"):
            if "release" in line:
                print(f"  {line.strip()}")
                return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("CUDA compiler (nvcc) not found")
        return False
    return False


# CUDA compilation flags matching mexCompile.m
def get_cuda_compile_args():
    """Get CUDA compilation arguments matching the MATLAB mexCompile.m setup."""
    cuda_args = [
        "-std=c++14",
        "--use_fast_math",
        "--default-stream",
        "per-thread",
        "-m64",
        "--extra-device-vectorization",
        "--expt-relaxed-constexpr",
        "-t8",
        "--gpu-architecture=compute_86",
        "--restrict",
        "-Xptxas",
        "--warn-on-spills",
        "-gencode=arch=compute_70,code=sm_70",
        "-gencode=arch=compute_80,code=sm_80",
        "-gencode=arch=compute_75,code=sm_75",
        "-gencode=arch=compute_86,code=sm_86",
        "-gencode=arch=compute_89,code=sm_89",
    ]
    return cuda_args


# Get CUDA paths
def get_cuda_paths():
    """Get CUDA library and include paths."""
    cuda_home = os.environ.get("CUDA_HOME", "/usr/local/cuda")

    cuda_include = os.path.join(cuda_home, "include")
    cuda_lib = os.path.join(cuda_home, "lib64")

    if not os.path.exists(cuda_include):
        cuda_include = "/usr/local/cuda/include"
    if not os.path.exists(cuda_lib):
        cuda_lib = "/usr/local/cuda/lib64"

    return cuda_include, cuda_lib


def create_cuda_extension():
    """Create CUDA extension if CUDA is available."""
    if not check_cuda():
        print("CUDA not available, skipping CUDA extensions")
        return []

    cuda_include, cuda_lib = get_cuda_paths()

    # For now, we're using CuPy RawKernel so no actual compilation needed
    # This setup is prepared for future Pybind11 CUDA extensions

    print("CUDA setup prepared:")
    print(f"  Include path: {cuda_include}")
    print(f"  Library path: {cuda_lib}")

    return []


# Package metadata
setup(
    name="emclarity-cuda-ops",
    version="0.1.0",
    author="emClarity Python Conversion",
    author_email="",
    description="CUDA-accelerated operations for emClarity Python conversion",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    package_data={
        "cuda_ops": ["*.cu", "*.cuh"],
    },
    include_package_data=True,
    ext_modules=create_cuda_extension(),
    install_requires=[
        "numpy>=1.20.0",
        "cupy-cuda12x>=10.0.0",  # Adjust based on CUDA version
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-benchmark",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: C++",
        "Programming Language :: CUDA",
        "Topic :: Scientific/Engineering :: Image Processing",
    ],
    keywords="cuda gpu scientific-computing image-processing cryo-em",
    project_urls={
        "Source": "https://github.com/StochasticAnalytics/emClarity",
        "Documentation": "https://github.com/StochasticAnalytics/emClarity/tree/main/python",
    },
)
