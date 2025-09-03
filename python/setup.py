"""
Setup configuration for emClarity Python package.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_path = Path(__file__).parent / "docs" / "README.md"
if readme_path.exists():
    long_description = readme_path.read_text()
else:
    long_description = "Python conversion of emClarity cryo-EM processing tools"

# Read requirements
def read_requirements(filename):
    """Read requirements from file, filtering out comments and empty lines."""
    req_path = Path(__file__).parent / filename
    if not req_path.exists():
        return []
    
    with open(req_path) as f:
        requirements = []
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('-'):
                # Handle conditional requirements
                if ';' in line:
                    requirements.append(line)
                else:
                    requirements.append(line)
        return requirements

setup(
    name="emclarity-python",
    version="1.0.0",
    description="Python conversion of emClarity cryo-EM processing tools",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="emClarity Development Team",
    url="https://github.com/StochasticAnalytics/emClarity",
    packages=find_packages(),
    python_requires=">=3.8",
    
    # Core dependencies
    install_requires=read_requirements("requirements.txt"),
    
    # Optional dependencies
    extras_require={
        "gui": read_requirements("requirements-gui.txt"),
        "gpu": read_requirements("requirements-gpu.txt"),
        "dev": read_requirements("requirements-dev.txt"),
        "all": (read_requirements("requirements-gui.txt") + 
                read_requirements("requirements-gpu.txt")),
    },
    
    # Package data
    package_data={
        "cuda_ops": ["*.cu", "*.cuh", ".clang-format"],
        "gui": ["*.json", "*.ui", "*.qrc"],
        "docs": ["*.md"],
    },
    
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Image Processing",
        "Topic :: Scientific/Engineering :: Physics",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    ],
    
    # Console scripts
    entry_points={
        "console_scripts": [
            "emclarity-convert-params=parameters:main",
            "emclarity-gui=gui.main:main",
            "emclarity-test=test_runner:main",
        ],
    },
    
    # Include all package files
    include_package_data=True,
    zip_safe=False,
)
