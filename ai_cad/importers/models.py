"""Value types for imported CAD assemblies.

These are the only objects the compiler accepts from a CAD source. Nothing here knows about
build123d, OCP or mesh libraries: geometry handles travel in ``ImportedPart.shape`` for callers
that need them, but every decision the compiler makes is driven by the numbers below, so a test can
build an ``ImportedAssembly`` by hand and exercise the whole compiler without a CAD kernel.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PartSignature(BaseModel):
    """A shape's identity for deduplication.

    Two instances reference the same part when these numbers agree. Handedness is deliberately not
    part of it: a mirrored left and right link share one B-rep and differ only by the placement,
    so reflection is a property of the instance, never of the part.
    """

    volume_m3: float
    surface_area_m2: float
    bbox_min_m: tuple[float, float, float]
    bbox_max_m: tuple[float, float, float]
    face_count: int
    face_type_counts: dict[str, int] = Field(default_factory=dict)

    def key(self) -> tuple:
        """Hashable identity, quantized at the resolution the compiler can actually distinguish.

        Volume is compared at 1 mm³, area at 1 mm², and bounding-box extents at 1 µm. Quantizing in
        SI units with a single decimal place count would have been wrong: 1e-6 m³ is a litre, so
        rounding volumes to six decimals in cubic metres would merge every small link in a robot arm
        into one part. Scaling first makes the tolerance the unit a designer would state.
        """
        return (
            round(self.volume_m3 * 1e9),
            round(self.surface_area_m2 * 1e6),
            tuple(round(v * 1e6) for v in self.bbox_min_m),
            tuple(round(v * 1e6) for v in self.bbox_max_m),
            self.face_count,
            tuple(sorted(self.face_type_counts.items())),
        )


class ImportedPart(BaseModel):
    """One unique referenced shape in the source CAD."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    part_id: str
    name: str
    signature: PartSignature
    is_solid: bool = True
    shape: Any = Field(default=None, exclude=True, repr=False)

    def model_post_init(self, __context: Any) -> None:  # noqa: D105 - pydantic hook
        # Geometric identity is the signature; a part whose numbers are not finite is unusable.
        for value in (
            self.signature.volume_m3,
            self.signature.surface_area_m2,
            *self.signature.bbox_min_m,
            *self.signature.bbox_max_m,
        ):
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError(f"part {self.part_id} has a non-finite measurement")


class ImportedInstance(BaseModel):
    """One placed copy of a part, with its transform relative to the assembly root."""

    instance_id: str
    name: str
    part_id: str
    transform: tuple[float, ...] = Field(
        ...,
        min_length=16,
        max_length=16,
        description="Row-major 4x4 transform in metres, taking part coordinates to assembly coordinates.",
    )
    is_reflected: bool = False
    assembly_path: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Named labels from the root assembly down to this instance, for link grouping.",
    )

    def model_post_init(self, __context: Any) -> None:  # noqa: D105 - pydantic hook
        if self.is_reflected != (determinant(self.transform) < 0.0):
            raise ValueError(
                f"instance {self.instance_id}: is_reflected={self.is_reflected} disagrees with the "
                f"transform determinant {determinant(self.transform):.6f}"
            )


class ImportedAssembly(BaseModel):
    """Everything the compiler needs from one CAD file."""

    source_path: str = ""
    source_bytes: int = 0
    units: str = "mm"
    root_name: str = ""
    parts: dict[str, ImportedPart] = Field(default_factory=dict)
    instances: list[ImportedInstance] = Field(default_factory=list)
    label_count: int = 0
    warnings: list[str] = Field(default_factory=list)

    @property
    def part_count(self) -> int:
        return len(self.parts)

    @property
    def instance_count(self) -> int:
        return len(self.instances)

    def instances_by_part(self) -> dict[str, list[ImportedInstance]]:
        out: dict[str, list[ImportedInstance]] = {}
        for inst in self.instances:
            out.setdefault(inst.part_id, []).append(inst)
        return out


def determinant(m: tuple[float, ...]) -> float:
    """Determinant of the rotation block of a row-major 4x4 transform.

    A negative value means the placement reflects the part. That matters physically: the inertia of
    a reflected instance is not the inertia of the part rotated by that matrix, so the compiler
    flags it rather than folding it into a rotation.
    """
    if len(m) != 16:
        raise ValueError(f"expected 16 values, got {len(m)}")
    a, b, c = m[0], m[1], m[2]
    d, e, f = m[4], m[5], m[6]
    g, h, i = m[8], m[9], m[10]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def rotation_error(m: tuple[float, ...]) -> float:
    """Largest deviation of ``R @ R.T`` from the identity, i.e. how far the block is from a pure rotation.

    Near zero for a proper rotation, near zero for a reflection too (a reflection is orthogonal with
    determinant -1), and clearly non-zero when the placement carries a scale or shear. Compose with
    :func:`determinant` to separate those three cases.
    """
    if len(m) != 16:
        raise ValueError(f"expected 16 values, got {len(m)}")
    r = [[m[row * 4 + col] for col in range(3)] for row in range(3)]
    worst = 0.0
    for i in range(3):
        for j in range(3):
            dot = sum(r[i][k] * r[j][k] for k in range(3))
            target = 1.0 if i == j else 0.0
            worst = max(worst, abs(dot - target))
    return worst


def is_proper_rotation(m: tuple[float, ...], tol: float = 1e-6) -> bool:
    """True when the placement is a pure rotation with no reflection, scale or shear.

    This is the gate the physics stages use before applying a part's inertia to an instance: only
    then is ``I_world = R I_part Rᵀ`` a faithful transform of the part inertia.
    """
    return rotation_error(m) <= tol and determinant(m) > 0.0


__all__ = [
    "ImportedAssembly",
    "ImportedInstance",
    "ImportedPart",
    "PartSignature",
    "determinant",
    "is_proper_rotation",
    "rotation_error",
]
