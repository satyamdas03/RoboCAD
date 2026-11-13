"""STEP assembly import through OpenCASCADE's XCAF document.

What this module guarantees, because the compiler depends on it:

* Units are metres. The STEP reader normalises to millimetres (``xstep.cascade.unit`` defaults to
  ``MM``) and this module converts once, at intake, so no other module multiplies by 0.001 again.
* Parts are deduplicated by measured geometry, not by name. SO-101 alone ships 393 instances under
  144 names, including PCB designators and anonymous numbers, so name-based grouping would either
  over-split or merge unrelated links.
* A placement whose rotation block has a negative determinant is a reflection. It is flagged on the
  instance, never folded into a rotation, because a reflection preserves volume but inverts
  handedness and the inertia of the reflected body is not the part inertia rotated. The flag is
  exact for the placement the reader delivers. It cannot recover a mirror that was lost earlier:
  OCC's own STEP writer turns a mirrored placement into a proper rotation (proven by
  ``test_step_round_trip_rewrites_a_mirrored_placement``), so "no reflected instances" means "none
  arrived", not "the source design has none".
* Nothing here trusts the input size. A STEP file is untrusted data: it is size-checked before
  being parsed and the parse runs with a wall-clock budget.

Geometry handles ride along on ``ImportedPart.shape`` for the property and meshing stages. Every
number the compiler acts on is in the models, so the compiler can be tested without a CAD kernel.
"""
from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Iterable

from ai_cad.importers.models import (
    ImportedAssembly,
    ImportedInstance,
    ImportedPart,
    PartSignature,
    determinant,
    is_proper_rotation,
    rotation_error,
)

MM_TO_M = 0.001

# A 250 MB STEP file is already an unusual input; beyond that the parse is a denial-of-service
# vector rather than a design task.
MAX_STEP_BYTES = 250 * 1024 * 1024
DEFAULT_PARSE_BUDGET_S = 300.0
MAX_LABELS = 200_000
MAX_DEPTH = 64


class StepImportError(RuntimeError):
    """Raised when a STEP file cannot be read as an assembly."""


def _ocp():
    try:
        from OCP.Bnd import Bnd_Box  # noqa: F401
        from OCP.BRepAdaptor import BRepAdaptor_Surface  # noqa: F401
        from OCP.BRepBndLib import BRepBndLib  # noqa: F401
        from OCP.BRepGProp import BRepGProp  # noqa: F401
        from OCP.GeomAbs import GeomAbs_SurfaceType  # noqa: F401
        from OCP.GProp import GProp_GProps  # noqa: F401
        from OCP.IFSelect import IFSelect_RetDone  # noqa: F401
        from OCP.STEPCAFControl import STEPCAFControl_Reader  # noqa: F401
        from OCP.TCollection import TCollection_ExtendedString  # noqa: F401
        from OCP.TDataStd import TDataStd_Name  # noqa: F401
        from OCP.TDF import TDF_Label, TDF_LabelSequence  # noqa: F401
        from OCP.TDocStd import TDocStd_Document  # noqa: F401
        from OCP.TopAbs import TopAbs_FACE  # noqa: F401
        from OCP.TopExp import TopExp_Explorer  # noqa: F401
        from OCP.TopLoc import TopLoc_Location  # noqa: F401
        from OCP.XCAFApp import XCAFApp_Application  # noqa: F401
        from OCP.XCAFDoc import XCAFDoc_DocumentTool  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the installed kernel
        raise StepImportError(
            "STEP import needs the OCP kernel that build123d installs. "
            "Install the runtime dependencies first: python -m pip install -r requirements.txt"
        ) from exc


class StepImporter:
    """Read a STEP file into an :class:`ImportedAssembly`."""

    def __init__(
        self,
        max_bytes: int = MAX_STEP_BYTES,
        parse_budget_s: float = DEFAULT_PARSE_BUDGET_S,
    ) -> None:
        self.max_bytes = max_bytes
        self.parse_budget_s = parse_budget_s

    # -- public -----------------------------------------------------------------------------
    def read(self, path: str | Path) -> ImportedAssembly:
        _ocp()
        p = Path(path)
        if not p.is_file():
            raise StepImportError(f"no such STEP file: {p}")
        size = p.stat().st_size
        if size > self.max_bytes:
            raise StepImportError(
                f"{p.name} is {size} bytes, above the {self.max_bytes} byte import limit"
            )

        started = time.monotonic()
        doc, reader, roots = self._read_document(p)
        self._check_budget(started, "read")

        warnings: list[str] = []
        assembly = ImportedAssembly(
            source_path=str(p),
            source_bytes=size,
            units="mm",
            root_name=self._root_name(roots),
            warnings=warnings,
        )

        from OCP.XCAFDoc import XCAFDoc_DocumentTool

        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

        part_by_signature: dict[tuple, ImportedPart] = {}
        part_by_label: dict[str, str] = {}
        counter = 0

        def walk(label, parent_matrix: tuple[float, ...], path: tuple[str, ...], depth: int) -> None:
            nonlocal counter
            counter += 1
            if counter > MAX_LABELS:
                raise StepImportError(f"{p.name} has more than {MAX_LABELS} labels")
            if depth > MAX_DEPTH:
                raise StepImportError(f"{p.name} nests assemblies deeper than {MAX_DEPTH} levels")
            if counter % 500 == 0:
                self._check_budget(started, f"walk ({counter} labels)")

            local = self._location_matrix(shape_tool, label)
            world = _compose(parent_matrix, local)
            name = self._name_of(label)
            here = path + (name,) if name else path

            # A component may point at another assembly. Recursing into the referred label is what
            # turns a gripper sub-assembly from one opaque blob into its real links; without it the
            # part count collapses and the link grouping in M2 has nothing to group.
            target = label
            if not shape_tool.IsAssembly_s(label):
                ref = _empty_label()
                if shape_tool.GetReferredShape_s(label, ref):
                    target = ref

            if shape_tool.IsAssembly_s(target):
                key = _label_key(target)
                if key in seen_assemblies:
                    warnings.append(
                        f"assembly {self._name_of(target)!r} appears inside itself; stopped there"
                    )
                    return
                seen_assemblies.add(key)
                comps = _label_sequence()
                shape_tool.GetComponents_s(target, comps)
                for i in range(1, comps.Length() + 1):
                    walk(comps.Value(i), world, here, depth + 1)
                seen_assemblies.discard(key)
                return

            key = _label_key(target)
            part_id = part_by_label.get(key)
            if part_id is None:
                shape = shape_tool.GetShape_s(target)
                if shape is None or shape.IsNull():
                    warnings.append(f"skipped empty label {self._name_of(target)!r}")
                    return
                sig = _measure(shape, warnings)
                if sig is None:
                    return
                existing = part_by_signature.get(sig.key())
                if existing is not None:
                    part_id = existing.part_id
                else:
                    part_id = f"part_{len(part_by_signature) + 1:03d}"
                    part = ImportedPart(
                        part_id=part_id,
                        name=self._name_of(target) or part_id,
                        signature=sig,
                        shape=shape,
                    )
                    part_by_signature[sig.key()] = part
                    assembly.parts[part_id] = part
                part_by_label[key] = part_id

            det = determinant(world)
            inst = ImportedInstance(
                instance_id=f"inst_{len(assembly.instances) + 1:03d}",
                name=name or f"instance_{len(assembly.instances) + 1}",
                part_id=part_id,
                transform=world,
                is_reflected=det < 0.0,
                assembly_path=here,
            )
            if inst.is_reflected:
                assembly.warnings.append(
                    f"instance {inst.name!r} is mirrored (determinant {det:.6f}); "
                    "handedness is carried on the instance, not the part"
                )
            elif not is_proper_rotation(world):
                # A scaled or sheared placement makes the placed geometry a different size from the
                # shape that was measured, so any mass or inertia derived from the definition would
                # be wrong. Flag it here rather than let it propagate as a plausible number.
                assembly.warnings.append(
                    f"instance {inst.name!r} has a non-rigid placement "
                    f"(orthonormality error {rotation_error(world):.3e}); "
                    "volumes and inertias of the definition do not apply as-is"
                )
            assembly.instances.append(inst)

        seen_assemblies: set[str] = set()
        for i in range(1, roots.Length() + 1):
            walk(roots.Value(i), _IDENTITY, (), 0)
        self._check_budget(started, "walk")

        assembly.label_count = counter
        if not assembly.instances:
            raise StepImportError(f"{p.name} contains no placed shapes")
        return assembly

    # -- internals --------------------------------------------------------------------------
    def _read_document(self, path: Path):
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDF import TDF_LabelSequence
        from OCP.TDocStd import TDocStd_Document
        from OCP.XCAFApp import XCAFApp_Application

        app = XCAFApp_Application.GetApplication_s()
        doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
        app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)

        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        reader.SetColorMode(True)
        reader.SetLayerMode(True)
        status = reader.ReadFile(str(path))
        if status != IFSelect_RetDone:
            raise StepImportError(f"{path.name}: STEP reader returned {status}")
        if reader.Transfer(doc) is False:
            raise StepImportError(f"{path.name}: STEP transfer into the XCAF document failed")

        from OCP.XCAFDoc import XCAFDoc_DocumentTool

        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        roots = TDF_LabelSequence()
        shape_tool.GetFreeShapes(roots)
        if roots.Length() == 0:
            raise StepImportError(f"{path.name}: no top-level shape")
        return doc, reader, roots

    def _check_budget(self, started: float, stage: str) -> None:
        elapsed = time.monotonic() - started
        if elapsed > self.parse_budget_s:
            raise StepImportError(
                f"STEP parse exceeded its {self.parse_budget_s:.0f} s budget during {stage}"
            )

    def _root_name(self, roots) -> str:
        for i in range(1, roots.Length() + 1):
            name = self._name_of(roots.Value(i))
            if name:
                return name
        return ""

    def _name_of(self, label) -> str:
        from OCP.TDataStd import TDataStd_Name

        attr = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
            name = str(attr.Get().ToExtString())
            # OCC stores an internal label reference as a name (``=>[0:1:1:1]``) when a STEP
            # component carries no product name. It is a pointer, not a name, so it does not reach
            # the model: downstream code must be able to tell "unnamed" from "named".
            if name.startswith("=>["):
                return ""
            return name
        return ""

    def _location_matrix(self, shape_tool, label) -> tuple[float, ...]:
        try:
            loc = shape_tool.GetLocation_s(label)
        except Exception:  # pragma: no cover - older bindings
            return _IDENTITY
        return _toploc_to_matrix(loc)


def _measure(shape, warnings: list[str]) -> PartSignature | None:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    try:
        vol = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, vol)
        area = GProp_GProps()
        BRepGProp.SurfaceProperties_s(shape, area)
    except Exception as exc:  # pragma: no cover - kernel failure on a broken face
        warnings.append(f"could not measure a shape ({exc}); skipped")
        return None

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    if box.IsVoid():
        warnings.append("a shape has an empty bounding box; skipped")
        return None
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()

    return PartSignature(
        volume_m3=abs(vol.Mass()) * MM_TO_M**3,
        surface_area_m2=abs(area.Mass()) * MM_TO_M**2,
        bbox_min_m=(xmin * MM_TO_M, ymin * MM_TO_M, zmin * MM_TO_M),
        bbox_max_m=(xmax * MM_TO_M, ymax * MM_TO_M, zmax * MM_TO_M),
        face_count=_face_count(shape),
        face_type_counts=_face_types(shape),
    )


def _face_count(shape) -> int:
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    count = 0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        count += 1
        exp.Next()
    return count


def _face_types(shape) -> dict[str, int]:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    counts: Counter[str] = Counter()
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        try:
            surf = BRepAdaptor_Surface(TopoDS.Face_s(exp.Current()), True)
            # The enum prints as GeomAbs_SurfaceType.GeomAbs_Plane; keep the readable tail.
            counts[str(surf.GetType()).split(".")[-1].removeprefix("GeomAbs_")] += 1
        except Exception:  # pragma: no cover - kernel failure on a broken face
            counts["unknown"] += 1
        exp.Next()
    return dict(counts)


_IDENTITY: tuple[float, ...] = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


def _toploc_to_matrix(loc) -> tuple[float, ...]:
    if loc is None or loc.IsIdentity():
        return _IDENTITY
    trsf = loc.Transformation()
    # gp_Trsf exposes Value(row, col) with row in 1..3 and col in 1..4, and applies transforms as
    # x' = a11 x + a12 y + a13 z + a14, i.e. the translation sits in the fourth column. That is the
    # row-major layout stored here, with translation at indices 3, 7 and 11.
    #
    # Every coordinate that leaves this module is in metres, so the translation is converted here
    # and only here. The rotation block is dimensionless and is left alone.
    rotation = [float(trsf.Value(i, j)) for i in range(1, 4) for j in range(1, 4)]
    translation = [float(trsf.Value(i, 4)) * MM_TO_M for i in range(1, 4)]
    return (
        rotation[0], rotation[1], rotation[2], translation[0],
        rotation[3], rotation[4], rotation[5], translation[1],
        rotation[6], rotation[7], rotation[8], translation[2],
        0.0, 0.0, 0.0, 1.0,
    )


def _compose(parent: tuple[float, ...], local: tuple[float, ...]) -> tuple[float, ...]:
    """Row-major 4x4 multiply, parent @ local."""
    out = [0.0] * 16
    for r in range(4):
        for c in range(4):
            out[r * 4 + c] = sum(parent[r * 4 + k] * local[k * 4 + c] for k in range(4))
    return tuple(out)


def _label_key(label) -> str:
    """Stable string key for a TDF label, used to map a component's referred shape to its part."""
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDF import TDF_Tool

    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def _label_sequence():
    from OCP.TDF import TDF_LabelSequence

    return TDF_LabelSequence()


def _empty_label():
    from OCP.TDF import TDF_Label

    return TDF_Label()


def import_step(path: str | Path, **kwargs) -> ImportedAssembly:
    """Convenience wrapper: read one STEP file with default guards."""
    return StepImporter(**kwargs).read(path)


def iter_shapes(assembly: ImportedAssembly) -> Iterable[tuple[ImportedInstance, object]]:
    """Yield each placed instance with the shape of its part, for downstream geometry work."""
    for inst in assembly.instances:
        part = assembly.parts.get(inst.part_id)
        if part is not None and part.shape is not None:
            yield inst, part.shape


__all__ = [
    "DEFAULT_PARSE_BUDGET_S",
    "MAX_STEP_BYTES",
    "StepImporter",
    "StepImportError",
    "import_step",
    "iter_shapes",
]
