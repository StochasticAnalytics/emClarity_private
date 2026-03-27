"""Service for detecting system hardware: GPUs, CPUs, and memory.

Uses nvidia-smi for GPU detection and /proc or psutil-style queries
for CPU and memory information.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field


class GpuInfo(BaseModel):
    """Information about a single GPU device."""

    index: int = Field(..., description="Device index")
    name: str = Field(..., description="GPU model name")
    memory_total_mb: int = Field(..., description="Total GPU memory in MB")
    memory_used_mb: int = Field(default=0, description="Currently used memory in MB")
    memory_free_mb: int = Field(default=0, description="Available memory in MB")
    driver_version: str = Field(default="", description="NVIDIA driver version")
    cuda_version: str = Field(default="", description="CUDA version")


class SystemInfo(BaseModel):
    """Aggregated system information."""

    cpu_count: int = Field(..., description="Number of logical CPU cores")
    cpu_count_physical: int = Field(..., description="Number of physical CPU cores")
    memory_total_gb: float = Field(..., description="Total system RAM in GB")
    memory_available_gb: float = Field(..., description="Available RAM in GB")
    hostname: str = Field(default="", description="Machine hostname")
    gpus: list[GpuInfo] = Field(default_factory=list, description="Detected GPUs")


class SystemService:
    """Detect and report system hardware capabilities."""

    def detect_gpus(self) -> list[GpuInfo]:
        """Detect NVIDIA GPUs using nvidia-smi.

        Returns an empty list if nvidia-smi is not available or no
        GPUs are found.
        """
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,memory.total,memory.used,memory.free,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        if result.returncode != 0:
            return []

        gpus: list[GpuInfo] = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                continue
            try:
                gpus.append(
                    GpuInfo(
                        index=int(parts[0]),
                        name=parts[1],
                        memory_total_mb=int(parts[2]),
                        memory_used_mb=int(parts[3]),
                        memory_free_mb=int(parts[4]),
                        driver_version=parts[5],
                    )
                )
            except (ValueError, IndexError):
                continue

        # Try to get CUDA version
        cuda_version = self._detect_cuda_version()
        for gpu in gpus:
            gpu.cuda_version = cuda_version

        return gpus

    def get_system_info(self) -> SystemInfo:
        """Gather CPU, memory, and GPU information."""
        cpu_count = os.cpu_count() or 1
        cpu_physical = self._get_physical_cpu_count()
        mem_total, mem_available = self._get_memory_info()

        hostname = ""
        try:
            import socket
            hostname = socket.gethostname()
        except OSError:
            pass

        return SystemInfo(
            cpu_count=cpu_count,
            cpu_count_physical=cpu_physical,
            memory_total_gb=round(mem_total / (1024 ** 3), 2),
            memory_available_gb=round(mem_available / (1024 ** 3), 2),
            hostname=hostname,
            gpus=self.detect_gpus(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_physical_cpu_count() -> int:
        """Get physical CPU core count from /proc/cpuinfo."""
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text()
            physical_ids = set()
            core_ids = set()
            current_physical = None

            for line in cpuinfo.splitlines():
                if line.startswith("physical id"):
                    current_physical = line.split(":")[1].strip()
                elif line.startswith("core id") and current_physical is not None:
                    core_id = line.split(":")[1].strip()
                    physical_ids.add(current_physical)
                    core_ids.add((current_physical, core_id))

            if core_ids:
                return len(core_ids)
        except (FileNotFoundError, PermissionError):
            pass

        return os.cpu_count() or 1

    @staticmethod
    def _get_memory_info() -> tuple[int, int]:
        """Read total and available memory from /proc/meminfo.

        Returns (total_bytes, available_bytes).
        """
        total = 0
        available = 0

        try:
            meminfo = Path("/proc/meminfo").read_text()
            for line in meminfo.splitlines():
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) * 1024  # kB to bytes
                elif line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) * 1024
        except (FileNotFoundError, PermissionError, ValueError):
            pass

        return total, available

    @staticmethod
    def _detect_cuda_version() -> str:
        """Try to detect the installed CUDA version."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # nvidia-smi also shows CUDA version in the header output
            header_result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if header_result.returncode == 0:
                for line in header_result.stdout.splitlines():
                    if "CUDA Version:" in line:
                        parts = line.split("CUDA Version:")
                        if len(parts) > 1:
                            return parts[1].strip().rstrip("|").strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: check nvcc
        try:
            result = subprocess.run(
                ["nvcc", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "release" in line.lower():
                        # Typical format: "Cuda compilation tools, release 12.2, V12.2.140"
                        parts = line.split("release")
                        if len(parts) > 1:
                            return parts[1].strip().split(",")[0].strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return ""
