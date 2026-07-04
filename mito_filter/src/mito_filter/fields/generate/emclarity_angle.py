"""Stub: drive the SPEC §7b emClarity patch + recompile + re-run, then load the angle field.

The recommended path to a dense per-voxel orientation field (SPEC §7): patch the commented
``BH_templateSearch3d_2.m:806`` to a mode-2 fp32 ``SAVE_IMG(single(RESULTS_angle), anglesOUT)``
(never ``'half'`` — 2592 > fp16 integer-exact 2048), recompile **salina-only**
(``testScripts/mCompile.sh``, ``skipMex=1``; mind the NFS symlink attr-cache on
``current_emClarity``), and re-run the 112-tomo bin5 search. This provider would orchestrate
that pipeline and then hand off to :class:`~mito_filter.fields.loaders.AngleIndexLoader`.

Not implemented here — this is a later workflow (the search re-run is a cluster job, not an
in-process compute). The registry can still *name* it so a config can select the generation
strategy for ``angle``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ...core.backend import Device
from ...core.field import DenseField
from ..provider import GPU_GENERATE, Availability, Cost, FieldProvider, FieldRegistry, FieldSpec

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ...datasets.base import TomogramRef


class EmClarityAngleProvider(FieldProvider):
    """Generate the dense ``angle`` index field via the emClarity re-run (SPEC §7b). STUB.

    Its real implementation drives the salina patch/recompile/re-run and then loads
    ``<base>_angles.mrc``; until then :meth:`available` is ``MISSING`` and :meth:`materialize`
    raises :class:`NotImplementedError`.
    """

    produces = FieldSpec(
        name="angle",
        channels=1,
        dtype=np.dtype(np.float32),
        semantics="packed argmax orientation+template index per voxel via emClarity re-run (§7b)",
    )

    def available(self, tomo: "TomogramRef") -> Availability:
        return Availability.MISSING

    def materialize(self, tomo: "TomogramRef", reg: FieldRegistry, *, device: Device) -> DenseField:
        raise NotImplementedError(
            "EmClarityAngleProvider is a stub: patch/recompile/re-run is a later workflow "
            "(SPEC §7b). Use AngleIndexLoader once <base>_angles.mrc exists."
        )

    def cost_hint(self) -> Cost:
        return GPU_GENERATE
