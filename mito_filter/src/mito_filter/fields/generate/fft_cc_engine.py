"""Stub: in-package FFT-CC angle-field fallback (SPEC §7c) when the re-run is blocked.

A cupy/torch FFT cross-correlation engine over the 864 sampled angles x 3 templates + missing
wedge, all inputs already on disk (searched recs, templates, ``_angles.list``, ctf/tilt geom).
It must replicate emClarity's per-orientation sigma-normalisation (divide each orientation's CC
by its own std, no mean subtraction, BH:640), apply the wedge from tilt geometry, match the rec
bandpass, and pass the §9.3 dense-vs-csv-normal acceptance test before its field is trusted.

Not implemented — ~10-50x the effort of the re-run and preferred only if recompile is impossible.
GPU-only in practice; the import stays CPU-safe (torch/cupy imported lazily inside the real
implementation, never at module load).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ...core.backend import Device
from ...core.field import DenseField
from ..provider import GPU_GENERATE, Availability, Cost, FieldProvider, FieldRegistry, FieldSpec

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ...datasets.base import TomogramRef


class TorchCCAngleProvider(FieldProvider):
    """Generate the dense ``angle`` field by an in-package FFT-CC search (SPEC §7c). STUB.

    :meth:`available` is ``MISSING`` and :meth:`materialize` raises :class:`NotImplementedError`
    until the FFT-CC engine (and its dense-vs-csv-normal acceptance test) is implemented.
    """

    produces = FieldSpec(
        name="angle",
        channels=1,
        dtype=np.dtype(np.float32),
        semantics="packed argmax orientation+template index per voxel via in-package FFT-CC (§7c)",
    )

    def available(self, tomo: "TomogramRef") -> Availability:
        return Availability.MISSING

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        raise NotImplementedError(
            "TorchCCAngleProvider is a stub (SPEC §7c fallback): implement the FFT-CC engine "
            "with per-orientation sigma-norm + wedge + bandpass, and pass the dense-vs-csv "
            "normal acceptance test before trusting its field."
        )

    def cost_hint(self) -> Cost:
        return GPU_GENERATE
