"""Geometric features extracted from imported parts, in assembly coordinates.

Joint inference needs exactly one kind of evidence from the CAD: cylindrical faces, because that is
what a bearing, a servo spline, a pin and every revolute joint in a robot arm look like. This module
pulls them out of the B-rep once, in metres, in the assembly frame, and nothing downstream touches
the kernel again.

A bore and a shaft are the same cylinder to the kernel, so the distinction comes from face
orientation: on a solid, the cylindrical face of a hole faces into the void and is reversed, while
the face of a boss faces out. That orientation is what lets joint inference tell an interface from a
hole next to another hole.
"""
from __future__ import annotations

import math
from collections import Counter

from pydantic import BaseModel, Field

from ai_cad.importers.models import ImportedAssembly, ImportedInstance


class CylinderFace(BaseModel):
    """One cylindrical face, placed in assembly coordinates."""

    instance_id: str
    radius_m: float = Field(gt=0.0)
    axis_point: tuple[float, float, float]
    axis_dir: tuple[float, float, float]
    is_bore: bool
    area_m2: float = 0.0

    def normalized(self) -> "CylinderFace":
        """Same face with the axis direction flipped to a canonical half-space.

        Two coaxial cylinders can carry opposite direction vectors depending on how each was
        modelled. Parallelism is what matters, so the sign is thrown away here and compared with
        absolute dot products downstream.
        """
        d = self.axis_dir
        for component in d:
            if abs(component) > 1e-12:
                if component < 0.0:
                    return self.model_copy(update={"axis_dir": (-d[0], -d[1], -d[2])})
                break
        return self


def extract_cylinders(assembly: ImportedAssembly, max_faces_per_shape: int = 200_000) -> list[CylinderFace]:
    """Every cylindrical face of every placed instance, transformed into assembly coordinates."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    out: list[CylinderFace] = []
    for inst in assembly.instances:
        part = assembly.parts.get(inst.part_id)
        shape = getattr(part, "shape", None) if part is not None else None
        if shape is None:
            continue
        rot, trans = _rotation_translation(inst)
        seen = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            seen += 1
            if seen > max_faces_per_shape:
                break
            face = TopoDS.Face_s(exp.Current())
            exp.Next()
            try:
                surf = BRepAdaptor_Surface(face, True)
                if surf.GetType() != GeomAbs_Cylinder:
                    continue
                cyl = surf.Cylinder()
            except Exception:  # pragma: no cover - kernel failure on a broken face
                continue
            axis = cyl.Axis()
            loc, direction = axis.Location(), axis.Direction()
            point = _apply(rot, trans, (loc.X(), loc.Y(), loc.Z()))
            dirv = _rotate(rot, (direction.X(), direction.Y(), direction.Z()))
            if _norm(dirv) < 1e-9:  # pragma: no cover - degenerate axis
                continue
            out.append(
                CylinderFace(
                    instance_id=inst.instance_id,
                    radius_m=cyl.Radius() * 1e-3,
                    axis_point=point,
                    axis_dir=_unit(dirv),
                    is_bore=face.Orientation() == TopAbs_REVERSED,
                    area_m2=_face_area(face) * 1e-6,
                ).normalized()
            )
    return out


def summarize(cylinders: list[CylinderFace]) -> dict[str, int]:
    bores = sum(1 for c in cylinders if c.is_bore)
    return {
        "cylinders": len(cylinders),
        "bores": bores,
        "shafts": len(cylinders) - bores,
        "distinct_radii_mm": len({round(c.radius_m * 1e3, 3) for c in cylinders}),
    }


def radius_histogram(cylinders: list[CylinderFace], places: int = 1) -> Counter:
    return Counter(round(c.radius_m * 1e3, places) for c in cylinders)


# -- vector helpers -------------------------------------------------------------------------------
def _rotation_translation(inst: ImportedInstance):
    m = inst.transform
    rot = ((m[0], m[1], m[2]), (m[4], m[5], m[6]), (m[8], m[9], m[10]))
    trans = (m[3], m[7], m[11])
    return rot, trans


def _apply(rot, trans, p: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        rot[0][0] * p[0] + rot[0][1] * p[1] + rot[0][2] * p[2] + trans[0],
        rot[1][0] * p[0] + rot[1][1] * p[1] + rot[1][2] * p[2] + trans[1],
        rot[2][0] * p[0] + rot[2][1] * p[1] + rot[2][2] * p[2] + trans[2],
    )


def _rotate(rot, v: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        rot[0][0] * v[0] + rot[0][1] * v[1] + rot[0][2] * v[2],
        rot[1][0] * v[0] + rot[1][1] * v[1] + rot[1][2] * v[2],
        rot[2][0] * v[0] + rot[2][1] * v[1] + rot[2][2] * v[2],
    )


def _face_area(face) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    try:
        BRepGProp.SurfaceProperties_s(face, props)
    except Exception:  # pragma: no cover - kernel failure
        return 0.0
    return abs(props.Mass())


def _norm(v: tuple[float, float, float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    n = _norm(v)
    return (v[0] / n, v[1] / n, v[2] / n) if n > 0 else (0.0, 0.0, 1.0)


__all__ = [
    "CylinderFace",
    "extract_cylinders",
    "radius_histogram",
    "summarize",
]
