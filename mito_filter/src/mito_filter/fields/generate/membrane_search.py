"""Stub: synthetic-bilayer membrane search producing dense ``membrane`` + ``membrane_normal``.

SPEC §8: build a physically-parameterised synthetic bilayer/edge template (two density lamellae
at the mito-membrane headgroup spacing, low-passed to 12.5 A / bin5, in a 288^3 box, rescaled to
~58^3 internally), add it to the multi-reference search, and reuse the SPEC §7 argmax patch — or
run it as a SEPARATE membrane-only search to avoid the combined-MIP masking caveat. Each voxel's
packed index then yields a membrane likelihood (``refIdx == membrane_ref``, with the co-located
CC as strength) and a membrane normal (SPEC §5).

Not implemented — no membrane/mito reference exists on disk today (SPEC §8), so building it is
genuine from-scratch work. The registry can still name the provider so a config can request it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ...core.backend import Device
from ...core.field import DenseField
from ..provider import GPU_GENERATE, Availability, Cost, FieldProvider, FieldRegistry, FieldSpec

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ...datasets.base import TomogramRef


class MembraneSearchProvider(FieldProvider):
    """Generate a dense ``membrane`` CC field from a synthetic-bilayer search (SPEC §8). STUB.

    Produces ``membrane`` (CC strength); the paired ``membrane_normal`` is decoded from the same
    packed-index volume by :class:`~mito_filter.fields.derived.NormalFieldProvider`-style logic.
    :meth:`available` is ``MISSING`` and :meth:`materialize` raises :class:`NotImplementedError`
    until the bilayer template + separate search are built.
    """

    produces = FieldSpec(
        name="membrane",
        channels=1,
        dtype=np.dtype(np.float32),
        semantics="dense membrane-template CC strength from a synthetic-bilayer search (§8)",
    )

    def available(self, tomo: "TomogramRef") -> Availability:
        return Availability.MISSING

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        raise NotImplementedError(
            "MembraneSearchProvider is a stub (SPEC §8): build the synthetic bilayer template "
            "(288^3 box) and run a separate membrane-only search; no membrane reference exists "
            "on disk yet."
        )

    def cost_hint(self) -> Cost:
        return GPU_GENERATE
