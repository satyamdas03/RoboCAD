"""CAD import: STEP assemblies in, compiler-ready models out.

The contract the rest of the compiler relies on is in :mod:`ai_cad.importers.models`: metres,
deduplicated parts, placed instances, and a reflection flag that is true exactly when the placement
is left-handed. :mod:`ai_cad.importers.step_import` is the only place that touches the CAD kernel.
"""
from ai_cad.importers.models import (
    ImportedAssembly,
    ImportedInstance,
    ImportedPart,
    PartSignature,
    determinant,
    is_proper_rotation,
    rotation_error,
)

__all__ = [
    "ImportedAssembly",
    "ImportedInstance",
    "ImportedPart",
    "PartSignature",
    "determinant",
    "is_proper_rotation",
    "rotation_error",
]
