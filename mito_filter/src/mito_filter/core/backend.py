"""Array-backend shim: numpy (default, always works) | cupy | torch.

The CPU/numpy path is **fully implemented and importable without torch or cupy**. GPU
imports are guarded and lazy so importing this module never requires the optional deps.

Downstream code obtains an array module via ``Backend.xp()`` and stays backend-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import ModuleType
from typing import Optional, cast

import numpy as np
from numpy.typing import NDArray


class Device(Enum):
    """Compute device / backend selector."""

    CPU = "cpu"
    """numpy on the CPU (always available)."""

    CUPY = "cupy"
    """cupy on a CUDA GPU (optional dependency)."""

    TORCH = "torch"
    """torch on a CUDA GPU (optional dependency)."""


def cupy_available() -> bool:
    """Return True if cupy is importable and a CUDA device is present."""
    try:
        import cupy  # noqa: F401

        return bool(cupy.cuda.runtime.getDeviceCount())
    except Exception:
        return False


def torch_available() -> bool:
    """Return True if torch is importable with CUDA available."""
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


@dataclass(frozen=True)
class Backend:
    """A resolved array backend.

    Args:
        device: The selected :class:`Device`.
        gpu_id: CUDA device ordinal for GPU backends (ignored on CPU).

    Attributes:
        device: The selected device.
        gpu_id: The CUDA device ordinal.
    """

    device: Device = Device.CPU
    gpu_id: int = 0

    @classmethod
    def cpu(cls) -> "Backend":
        """Return the always-available CPU (numpy) backend."""
        return cls(Device.CPU, 0)

    @classmethod
    def auto(cls, gpu_id: int = 0) -> "Backend":
        """Pick the best available backend: cupy, else torch, else CPU.

        Args:
            gpu_id: CUDA device ordinal to use if a GPU backend is chosen.

        Returns:
            A resolved backend (never raises; falls back to CPU).
        """
        if cupy_available():
            return cls(Device.CUPY, gpu_id)
        if torch_available():
            return cls(Device.TORCH, gpu_id)
        return cls(Device.CPU, 0)

    @property
    def is_gpu(self) -> bool:
        """True for GPU backends (cupy / torch)."""
        return self.device in (Device.CUPY, Device.TORCH)

    def xp(self) -> ModuleType:
        """Return the array module for this backend.

        Returns:
            ``numpy`` for CPU, ``cupy`` for CUPY, ``torch`` for TORCH.

        Raises:
            RuntimeError: If a GPU backend was requested but its library is unavailable.
        """
        if self.device is Device.CPU:
            return np
        if self.device is Device.CUPY:
            try:
                import cupy

                return cast(ModuleType, cupy)
            except Exception as exc:  # pragma: no cover - optional dep
                raise RuntimeError("cupy backend requested but cupy is unavailable") from exc
        if self.device is Device.TORCH:
            try:
                import torch

                return cast(ModuleType, torch)
            except Exception as exc:  # pragma: no cover - optional dep
                raise RuntimeError("torch backend requested but torch is unavailable") from exc
        raise RuntimeError(f"unknown device {self.device!r}")  # pragma: no cover

    def to_numpy(self, arr: "NDArray | object") -> "NDArray":
        """Copy an array from this backend to a host numpy array.

        Args:
            arr: An array produced by this backend's ``xp()`` module.

        Returns:
            A numpy ndarray on the host.
        """
        if self.device is Device.CPU:
            return np.asarray(arr)
        if self.device is Device.CUPY:  # pragma: no cover - optional dep
            import cupy

            return cast(NDArray, cupy.asnumpy(arr))
        # torch  # pragma: no cover - optional dep
        import torch

        if isinstance(arr, torch.Tensor):
            return cast(NDArray, arr.detach().cpu().numpy())
        return np.asarray(arr)

    def asarray(self, arr: "NDArray | object", dtype: Optional[np.dtype] = None) -> object:
        """Move/cast a host array onto this backend.

        Args:
            arr: Source array (numpy or array-like).
            dtype: Optional target dtype.

        Returns:
            An array on this backend (numpy / cupy ndarray or torch tensor).
        """
        if self.device is Device.TORCH:  # pragma: no cover - optional dep
            import torch

            t = torch.as_tensor(np.asarray(arr))
            if dtype is not None:
                t = t.to(getattr(torch, np.dtype(dtype).name))
            return t.cuda(self.gpu_id) if torch.cuda.is_available() else t
        xp = self.xp()
        return xp.asarray(arr, dtype=dtype)
