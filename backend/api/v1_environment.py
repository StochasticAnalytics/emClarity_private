"""V1 Environment API endpoints.

Provides endpoints for validating executable paths, testing SSH connectivity,
and checking for required system dependencies.

POST /api/v1/environment/validate-path
    body: { path: str }
    Returns { valid: bool, version: str | null, error: str | null }
    Checks existence, executability, and attempts to retrieve version string.

POST /api/v1/environment/test-ssh
    body: { host: str, user: str | null, port: int }
    Returns { connected: bool, error: str | null, latency_ms: float | null }
    Shells out to the system ssh command; does NOT use paramiko.

GET /api/v1/environment/check-dependencies
    Returns { dependencies: [{ name: str, path: str | null, found: bool, version: str | null }] }
    Checks for emClarity, IMOD (imodinfo), and CUDA Toolkit (nvcc).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/environment", tags=["environment-v1"])

# ---------------------------------------------------------------------------
# Whitelist of environment variables that may be resolved via the API
# ---------------------------------------------------------------------------

ALLOWED_ENV_VARS = {"EMCLARITY_PATH", "IMOD_DIR", "CUDA_HOME", "IMOD_BIN"}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_version(path: str) -> str | None:
    """Try --version then -v to retrieve a version string from an executable.

    Returns the first non-empty line from stdout (preferred) or stderr, or
    None if both attempts fail or produce no output.
    """
    for flag in ("--version", "-v"):
        try:
            result = subprocess.run(
                [path, flag],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout.strip() or result.stderr.strip()
            if output:
                return output.splitlines()[0].strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError, OSError):
            continue
    return None


# ---------------------------------------------------------------------------
# POST /validate-path
# ---------------------------------------------------------------------------

class ValidatePathRequest(BaseModel):
    path: str


class ValidatePathResponse(BaseModel):
    valid: bool
    version: str | None
    error: str | None


@router.post("/validate-path", response_model=ValidatePathResponse)
def validate_path(request: ValidatePathRequest) -> ValidatePathResponse:
    """Validate that a path exists, is executable, and optionally return its version."""
    path = request.path

    if not path:
        return ValidatePathResponse(valid=False, version=None, error="Path must not be empty")

    if not os.path.exists(path):
        return ValidatePathResponse(valid=False, version=None, error=f"Path does not exist: {path}")

    if not os.path.isfile(path):
        return ValidatePathResponse(valid=False, version=None, error=f"Path is not a file: {path}")

    if not os.access(path, os.X_OK):
        return ValidatePathResponse(valid=False, version=None, error=f"Path is not executable: {path}")

    version = _get_version(path)

    return ValidatePathResponse(valid=True, version=version, error=None)


# ---------------------------------------------------------------------------
# POST /test-ssh
# ---------------------------------------------------------------------------

class TestSshRequest(BaseModel):
    host: str
    user: str | None = None
    port: int = Field(default=22, ge=1, le=65535)


class TestSshResponse(BaseModel):
    connected: bool
    error: str | None
    latency_ms: float | None


@router.post("/test-ssh", response_model=TestSshResponse)
def test_ssh(request: TestSshRequest) -> TestSshResponse:
    """Test SSH connectivity to a remote host by shelling out to the ssh command."""
    user_at_host = f"{request.user}@{request.host}" if request.user else request.host

    cmd = [
        "ssh",
        "-o", "ConnectTimeout=5",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-p", str(request.port),
        "--",
        user_at_host,
        "true",
    ]

    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        if result.returncode == 0:
            return TestSshResponse(connected=True, error=None, latency_ms=latency_ms)
        else:
            error_text = result.stderr.strip() or f"SSH exited with code {result.returncode}"
            return TestSshResponse(connected=False, error=error_text, latency_ms=None)

    except subprocess.TimeoutExpired:
        return TestSshResponse(connected=False, error="SSH connection timed out", latency_ms=None)
    except FileNotFoundError:
        return TestSshResponse(connected=False, error="ssh executable not found", latency_ms=None)
    except PermissionError as exc:
        return TestSshResponse(connected=False, error=f"Permission denied running ssh: {exc}", latency_ms=None)
    except OSError as exc:
        return TestSshResponse(connected=False, error=f"OS error running ssh: {exc}", latency_ms=None)


# ---------------------------------------------------------------------------
# GET /check-dependencies
# ---------------------------------------------------------------------------

class DependencyInfo(BaseModel):
    name: str
    path: str | None
    found: bool
    version: str | None


class CheckDependenciesResponse(BaseModel):
    dependencies: list[DependencyInfo]


_DEPENDENCY_SPECS: list[tuple[str, str, list[str]]] = [
    # (display_name, binary_name, extra_paths_to_check)
    ("emClarity", "emClarity", ["/usr/local/bin/emClarity"]),
    ("IMOD", "imodinfo", ["/usr/local/IMOD/bin/imodinfo"]),
    ("CUDA Toolkit", "nvcc", ["/usr/local/cuda/bin/nvcc"]),
]


def _find_binary(binary_name: str, extra_paths: list[str]) -> str | None:
    """Return the first accessible path for a binary, or None."""
    found = shutil.which(binary_name)
    if found:
        return found
    for candidate in extra_paths:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


@router.get("/check-dependencies", response_model=CheckDependenciesResponse)
def check_dependencies() -> CheckDependenciesResponse:
    """Check for required system dependencies and return their status."""
    results: list[DependencyInfo] = []

    for display_name, binary_name, extra_paths in _DEPENDENCY_SPECS:
        binary_path = _find_binary(binary_name, extra_paths)
        if binary_path is None:
            results.append(DependencyInfo(name=display_name, path=None, found=False, version=None))
        else:
            version = _get_version(binary_path)
            results.append(DependencyInfo(name=display_name, path=binary_path, found=True, version=version))

    return CheckDependenciesResponse(dependencies=results)


# ---------------------------------------------------------------------------
# GET /resolve-env
# ---------------------------------------------------------------------------

class ResolveEnvResponse(BaseModel):
    value: str | None
    found: bool


@router.get("/resolve-env", response_model=ResolveEnvResponse)
def resolve_env(var: str) -> ResolveEnvResponse:
    """Resolve a whitelisted environment variable."""
    if var not in ALLOWED_ENV_VARS:
        raise HTTPException(
            status_code=403,
            detail=f"Environment variable '{var}' is not in the allowed list",
        )
    value = os.environ.get(var)
    return ResolveEnvResponse(value=value, found=value is not None)


# ---------------------------------------------------------------------------
# GET /registry-path
# ---------------------------------------------------------------------------


class RegistryPathResponse(BaseModel):
    path: str


@router.get("/registry-path", response_model=RegistryPathResponse)
def get_registry_path() -> RegistryPathResponse:
    """Return the current registry directory path."""
    from backend.utils.machine_config import get_registry_dir

    return RegistryPathResponse(path=str(get_registry_dir()))
