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
import time
from collections import Counter

from pydantic import BaseModel, Field

from ai_cad.importers.models import ImportedAssembly, ImportedInstance

# The same guards the STEP reader uses, for the same reason: a CAD file is untrusted input, and a
# file that measures cheap can still be made expensive to interrogate. Faces are counted once per
# unique part rather than once per placement, but the totals are still capped.
MAX_FACES_PER_SHAPE = 200_000
MAX_CYLINDERS = 500_000
FACE_CHECK_EVERY = 2048
DEFAULT_FEATURE_BUDGET_S = 120.0

# A cylinder radius is untrusted input the moment it can arrive from a file rather than from the
# kernel. An infinite or absurd radius would crash the pairing loop's bucket arithmetic, so the
# model rejects it on construction instead. 1 km is larger than any robot.
MAX_PHYSICAL_RADIUS_M = 1.0e3


class FeatureExtractionError(RuntimeError):
    """Raised when a part exceeds a resource guard instead of returning a partial answer."""


class _Deadline:
    __slots__ = ("at", "seconds")

    def __init__(self, seconds: float | None) -> None:
        self.seconds = seconds
        self.at = None if seconds is None else time.monotonic() + seconds

    def check(self, stage: str) -> None:
        if self.at is not None and time.monotonic() > self.at:
            raise FeatureExtractionError(
                f"feature extraction exceeded its {self.seconds:.0f} s budget during {stage}"
            )


class CylinderFace(BaseModel):
    """One cylindrical face, placed in assembly coordinates."""

    instance_id: str
    radius_m: float = Field(gt=0.0, lt=MAX_PHYSICAL_RADIUS_M, allow_inf_nan=False)
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


def extract_cylinders(
    assembly: ImportedAssembly,
    max_faces_per_shape: int = MAX_FACES_PER_SHAPE,
    budget_s: float | None = DEFAULT_FEATURE_BUDGET_S,
    max_cylinders: int = MAX_CYLINDERS,
) -> list[CylinderFace]:
    """Every cylindrical face of every placed instance, transformed into assembly coordinates.

    Faces are read once per **part** and transformed once per **instance**. In a real assembly the
    same part is often placed many times (SO-101 places one adapter 45 times), so reading per
    instance multiplies the kernel cost by the instance count for no new information. The guards are
    the reader's: a deadline, a per-shape face cap and a total cap on what this call may emit. A cap
    is reached by raising, never by returning a shorter list, because a silently truncated feature
    set produces a proposal that looks complete and is not.
    """
    deadline = _Deadline(budget_s)
    cache: dict[str, list[dict]] = {}
    out: list[CylinderFace] = []
    for inst in assembly.instances:
        deadline.check("instance placement")
        part = assembly.parts.get(inst.part_id)
        shape = getattr(part, "shape", None) if part is not None else None
        if shape is None:
            continue
        local = cache.get(inst.part_id)
        if local is None:
            local = _part_cylinders(shape, max_faces_per_shape, deadline)
            cache[inst.part_id] = local
        if len(out) + len(local) > max_cylinders:
            raise FeatureExtractionError(
                f"assembly would yield more than {max_cylinders} cylinder faces; refusing rather "
                "than returning a partial feature set"
            )
        rot, trans = _rotation_translation(inst)
        for cyl in local:
            out.append(
                CylinderFace(
                    instance_id=inst.instance_id,
                    radius_m=cyl["radius_m"],
                    axis_point=_apply(rot, trans, cyl["point"]),
                    axis_dir=_unit(_rotate(rot, cyl["dir"])),
                    is_bore=cyl["is_bore"],
                    area_m2=cyl["area_m2"],
                ).normalized()
            )
    return out


def _part_cylinders(shape, max_faces: int, deadline: _Deadline) -> list[dict]:
    """Cylindrical faces of one part, in part coordinates."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    out: list[dict] = []
    seen = 0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    deadline.check("face iteration")
    while exp.More():
        seen += 1
        if seen > max_faces:
            raise FeatureExtractionError(
                f"a part has more than {max_faces} faces; refusing to interrogate it"
            )
        if seen % FACE_CHECK_EVERY == 0:
            deadline.check("face iteration")
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
        dirv = (direction.X(), direction.Y(), direction.Z())
        if _norm(dirv) < 1e-9:  # pragma: no cover - degenerate axis
            continue
        out.append(
            {
                "radius_m": cyl.Radius() * 1e-3,
                "point": (loc.X(), loc.Y(), loc.Z()),
                "dir": dirv,
                "is_bore": face.Orientation() == TopAbs_REVERSED,
                "area_m2": _face_area(face) * 1e-6,
            }
        )
    deadline.check("face iteration")
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
    "DEFAULT_FEATURE_BUDGET_S",
    "FeatureExtractionError",
    "MAX_CYLINDERS",
    "MAX_FACES_PER_SHAPE",
    "extract_cylinders",
    "radius_histogram",
    "summarize",
]
