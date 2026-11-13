"""Kinematic skeleton of a servo-mediated robot arm, derived from its own CAD.

Why this is not the M2 joint inference
--------------------------------------
M2 searched for a bore-and-shaft pair between two bodies and found one joint on SO-101. That was
correct and it was not enough. Measurement on the pinned file explains it: the six arm links share
**zero** coaxial cylinder pairs with each other at 0.5 mm axis offset and 1.2 mm radial gap, polarity
ignored, so no bore/shaft rule can recover the chain, and a rule loosened until it does is matching
screws to screws.

The mechanism that does work on this class of robot is the one the hardware uses: **each joint is a
servo, and the servo's output shaft is the joint axis.** Three facts are measured, never assumed:

1. **The servo axis.** Every ST3215 in the file carries one axis direction holding a family of
   concentric cylinders (r 8.53 / 8.7 / 8.8 / 9.65 / 9.8 mm on the observed servos). That family is the
   output bearing, and the axis it sits on is the joint axis. It is read from the servo's own B-rep.
2. **The driven point.** Each servo carries two metal horns, a drive horn and a driven horn, at
   opposite ends of its shaft. The drive horn's placed centre lies on the joint axis by construction,
   so it is the joint origin.
3. **The body on each side.** A servo belongs to exactly one body: the body it is bolted into. That
   is decided by which chain body's bounding box is nearest the servo, and every instance in the
   assembly is then assigned to exactly one of those bodies.

What is *not* derived, and is stated as such
--------------------------------------------
* **Topology order.** The chain ``Base -> Rotation_Pitch -> Upper_arm -> Under_arm ->
  Wrist_Roll_Pitch -> Wrist_Roll_Follower -> Moving_Jaw`` is the CAD's own assembly naming. Those are
  the designer's words, not a geometric result, and a robot whose CAD names its links differently
  gets nothing from this module.
* **Joint limits.** The CAD contains no travel limits. They are emitted as ``None``, meaning unknown,
  and a simulator must be given limits from a datasheet or a measurement. Writing a number here
  because it looks plausible is how a model starts lying about a robot.

Every joint this module emits carries ``review_required``, because none of it has been checked
against the real machine.
"""
from __future__ import annotations

import collections
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ai_cad.importers.features import CylinderFace
from ai_cad.importers.joints import LinkGroup, group_links
from ai_cad.importers.models import ImportedAssembly

SCHEMA = "robocad.twin.joints/1"

# A servo's output axis carries a family of concentric radii. Two faces belong to one cluster when
# their axes agree to 0.999 (2.6 degrees) and their axis lines pass within this distance.
SERVO_AXIS_DOT = 0.999
SERVO_AXIS_OFFSET_M = 0.5e-3
# Only substantial cylinders take part: below this radius a servo is covered in fastener holes.
SERVO_MIN_RADIUS_M = 6.0e-3
# A cluster needs more than one face to be a bearing rather than one boss that happens to exist.
SERVO_MIN_FACES = 2

HORN_PATTERN = ("舵盘", "horn")


class KinematicsError(RuntimeError):
    """Raised when the assembly cannot be assigned to a kinematic skeleton."""


class ServoAxis(BaseModel):
    """One servo's output axis, with the evidence that made it one."""

    servo_link_id: str
    direction: tuple[float, float, float]
    point: tuple[float, float, float]
    radii_m: list[float]
    face_count: int

    def normalized(self) -> "ServoAxis":
        d = self.direction
        for component in d:
            if abs(component) > 1e-12:
                if component < 0.0:
                    return self.model_copy(update={"direction": (-d[0], -d[1], -d[2])})
                break
        return self


class BodyAssignment(BaseModel):
    """Every instance in the assembly, resolved to exactly one rigid body."""

    body_id: str
    name: str
    role: str = "link"
    instance_ids: list[str] = Field(default_factory=list)
    part_ids: list[str] = Field(default_factory=list)
    attached_groups: dict[str, int] = Field(default_factory=dict)


class DerivedJoint(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    joint_id: str
    parent_body: str
    child_body: str
    joint_type: str = "revolute"
    axis_point: tuple[float, float, float]
    axis_dir: tuple[float, float, float]
    # Unknown is the honest value: the CAD has no travel limits. A number here without a source is a
    # fabricated specification. A caller that *has* a source supplies it through ``apply_limits``, and
    # the source string travels with the number into the YAML and the report.
    limits: dict[str, float] | None = None
    limits_source: str | None = None
    servo: str
    horn_instance: str
    evidence: dict = Field(default_factory=dict)
    review_required: bool = True


class Skeleton(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = Field(default=SCHEMA, alias="schema", serialization_alias="schema")
    source: dict = Field(default_factory=dict)
    bodies: list[BodyAssignment] = Field(default_factory=list)
    joints: list[DerivedJoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
    status: str = "derived"


# ------------------------------------------------------------------------------------------------
# servo axes
# ------------------------------------------------------------------------------------------------
def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _line_distance(p1, d, p2) -> float:
    v = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
    along = _dot(v, d)
    perp = (v[0] - along * d[0], v[1] - along * d[1], v[2] - along * d[2])
    return math.sqrt(_dot(perp, perp))


def servo_axis(faces: list[CylinderFace], servo_link_id: str) -> ServoAxis:
    """The output axis of one servo: the axis carrying the widest family of concentric radii.

    A tie is broken by the largest radius, because a bearing seat is a bigger circle than the screw
    holes beside it.
    """
    usable = [f for f in faces if f.radius_m >= SERVO_MIN_RADIUS_M]
    if not usable:
        raise KinematicsError(
            f"{servo_link_id} has no cylindrical face at or above {SERVO_MIN_RADIUS_M * 1e3:.1f} mm, "
            "so its output axis cannot be read from geometry"
        )
    clusters: list[dict] = []
    for face in sorted(usable, key=lambda f: -f.radius_m):
        for cluster in clusters:
            ref = cluster["ref"]
            if (
                abs(_dot(face.axis_dir, ref.axis_dir)) > SERVO_AXIS_DOT
                and _line_distance(ref.axis_point, ref.axis_dir, face.axis_point) < SERVO_AXIS_OFFSET_M
            ):
                cluster["faces"].append(face)
                break
        else:
            clusters.append({"ref": face, "faces": [face]})
    clusters = [c for c in clusters if len(c["faces"]) >= SERVO_MIN_FACES]
    if not clusters:
        raise KinematicsError(
            f"{servo_link_id} has no axis carrying {SERVO_MIN_FACES} or more concentric cylinders"
        )
    clusters.sort(
        key=lambda c: (len({round(f.radius_m, 6) for f in c["faces"]}), max(f.radius_m for f in c["faces"])),
        reverse=True,
    )
    best = clusters[0]
    radii = sorted({round(f.radius_m, 9) for f in best["faces"]})
    return ServoAxis(
        servo_link_id=servo_link_id,
        direction=tuple(float(c) for c in best["ref"].axis_dir),
        point=tuple(float(c) for c in best["ref"].axis_point),
        radii_m=list(radii),
        face_count=len(best["faces"]),
    ).normalized()


# ------------------------------------------------------------------------------------------------
# body assignment
# ------------------------------------------------------------------------------------------------
def _center(box_min, box_max) -> tuple[float, float, float]:
    return tuple((box_min[i] + box_max[i]) / 2.0 for i in range(3))


def _distance(a, b) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def assign_bodies(
    links: list[LinkGroup], chain: list[str]
) -> tuple[list[BodyAssignment], dict[str, list[str]]]:
    """Give every instance to exactly one body in ``chain``.

    The chain bodies are the skeleton. Every other group the CAD keeps separate -- servos, motor
    holders, PCB adapter, anonymous components -- is bolted to one of them, and the nearest chain
    body's centroid is the evidence used to decide which. That is a proximity rule, not a
    measurement, so the result says so and the caller is expected to look at the count it produces.
    """
    by_id = {g.link_id: g for g in links}
    missing = [name for name in chain if name not in by_id]
    if missing:
        raise KinematicsError(
            "chain names bodies the assembly does not contain: " + ", ".join(missing)
        )
    centroid = {name: _center(by_id[name].bbox_min_m, by_id[name].bbox_max_m) for name in chain}
    assignments = {
        name: BodyAssignment(body_id=name, name=by_id[name].name, role=by_id[name].role)
        for name in chain
    }
    for name in chain:
        assignments[name].instance_ids.extend(by_id[name].instance_ids)
        for part_id in by_id[name].part_ids:
            if part_id not in assignments[name].part_ids:
                assignments[name].part_ids.append(part_id)

    for group in links:
        if group.link_id in chain:
            continue
        own = _center(group.bbox_min_m, group.bbox_max_m)
        best = min(chain, key=lambda name: _distance(own, centroid[name]))
        target = assignments[best]
        target.instance_ids.extend(group.instance_ids)
        target.attached_groups[group.link_id] = len(group.instance_ids)
        for part_id in group.part_ids:
            if part_id not in target.part_ids:
                target.part_ids.append(part_id)

    seen: dict[str, str] = {}
    for assignment in assignments.values():
        for instance_id in assignment.instance_ids:
            if instance_id in seen:
                raise KinematicsError(
                    f"instance {instance_id} assigned to both {seen[instance_id]} and "
                    f"{assignment.body_id}"
                )
            seen[instance_id] = assignment.body_id
    return list(assignments.values()), seen


# ------------------------------------------------------------------------------------------------
# horns and joints
# ------------------------------------------------------------------------------------------------
def _instance_center(assembly: ImportedAssembly, instance_id: str) -> tuple[float, float, float]:
    instance = next((i for i in assembly.instances if i.instance_id == instance_id), None)
    if instance is None:
        raise KinematicsError(f"no instance {instance_id}")
    part = assembly.parts.get(instance.part_id)
    if part is None:
        raise KinematicsError(f"instance {instance_id} names unknown part {instance.part_id}")
    signature = part.signature
    local = _center(signature.bbox_min_m, signature.bbox_max_m)
    m = instance.transform
    return (
        m[0] * local[0] + m[1] * local[1] + m[2] * local[2] + m[3],
        m[4] * local[0] + m[5] * local[1] + m[6] * local[2] + m[7],
        m[8] * local[0] + m[9] * local[1] + m[10] * local[2] + m[11],
    )


def _horn_instances(assembly: ImportedAssembly, instance_ids: list[str]) -> list[str]:
    found = []
    for instance_id in instance_ids:
        instance = next((i for i in assembly.instances if i.instance_id == instance_id), None)
        if instance is None:
            continue
        part = assembly.parts.get(instance.part_id)
        if part is None:
            continue
        name = part.name or ""
        if any(token in name.lower() or token in name for token in HORN_PATTERN):
            found.append(instance_id)
    return found


def derive_skeleton(
    assembly: ImportedAssembly,
    chain: list[str],
    cylinders: list[CylinderFace] | None = None,
) -> Skeleton:
    """Bodies, servo axes and one joint per servo, all traced back to geometry."""
    if cylinders is None:
        from ai_cad.importers.features import extract_cylinders

        cylinders = extract_cylinders(assembly)
    links = group_links(assembly)
    bodies, instance_to_body = assign_bodies(links, chain)
    by_id = {g.link_id: g for g in links}

    faces_by_instance: dict[str, list[CylinderFace]] = collections.defaultdict(list)
    for face in cylinders:
        faces_by_instance[face.instance_id].append(face)

    servos = [g for g in links if g.name.upper().startswith("ST3215")]
    if len(servos) != len(chain) - 1:
        raise KinematicsError(
            f"{len(servos)} servo group(s) for {len(chain) - 1} joint(s) in the chain; the "
            "servo-per-joint assumption does not hold for this assembly"
        )

    warnings: list[str] = []
    axes: list[ServoAxis | None] = []
    for servo in servos:
        servo_faces = [
            face for instance_id in servo.instance_ids for face in faces_by_instance[instance_id]
        ]
        try:
            axes.append(servo_axis(servo_faces, servo.link_id))
        except KinematicsError as exc:
            warnings.append(str(exc))
            axes.append(None)

    # A servo drives the joint whose two bodies it sits between, so the servo is paired to the
    # boundary its drive horn is nearest. Pairing by chain position alone would be an assumption;
    # the horn's placement is geometry.
    pairs: list[tuple[float, int, int, str]] = []
    for servo_index, servo in enumerate(servos):
        horns = _horn_instances(assembly, servo.instance_ids)
        if not horns:
            continue
        centres = [_instance_center(assembly, h) for h in horns]
        # The drive horn is the one furthest from the servo body's own centre: it is on the output
        # side of the shaft, the driven horn is the bearing on the other end.
        base = _center(servo.bbox_min_m, servo.bbox_max_m)
        order = sorted(range(len(horns)), key=lambda i: -_distance(centres[i], base))
        drive = horns[order[0]] if order else horns[0]
        drive_centre = _instance_center(assembly, drive)
        for joint_index in range(len(chain) - 1):
            parent, child = chain[joint_index], chain[joint_index + 1]
            middle = tuple(
                (
                    _center(by_id[parent].bbox_min_m, by_id[parent].bbox_max_m)[axis]
                    + _center(by_id[child].bbox_min_m, by_id[child].bbox_max_m)[axis]
                )
                / 2.0
                for axis in range(3)
            )
            pairs.append((_distance(drive_centre, middle), servo_index, joint_index, drive))

    chosen: dict[int, tuple[float, int, str]] = {}
    for distance, servo_index, joint_index, drive in sorted(pairs):
        if joint_index in chosen or any(v[1] == servo_index for v in chosen.values()):
            continue
        chosen[joint_index] = (distance, servo_index, drive)

    joints: list[DerivedJoint] = []
    for joint_index in range(len(chain) - 1):
        parent, child = chain[joint_index], chain[joint_index + 1]
        if joint_index not in chosen:
            warnings.append(
                f"no servo could be paired to the {parent} -> {child} joint; it is emitted without "
                "an axis and must be supplied by hand"
            )
            continue
        distance, servo_index, drive = chosen[joint_index]
        servo = servos[servo_index]
        axis = axes[servo_index]
        if axis is None:
            warnings.append(f"{servo.link_id} has no readable output axis; joint left axisless")
            continue
        point = _instance_center(assembly, drive)
        joints.append(
            DerivedJoint(
                joint_id=f"joint_{joint_index + 1}",
                parent_body=parent,
                child_body=child,
                axis_point=point,
                axis_dir=axis.direction,
                servo=servo.link_id,
                horn_instance=drive,
                evidence={
                    "servo_radii_m": axis.radii_m,
                    "servo_cylinder_faces": axis.face_count,
                    "servo_axis_point_m": list(axis.point),
                    "servo_to_joint_distance_m": round(distance, 6),
                    "source": "servo output-shaft axis and drive-horn placement, both from the "
                    "CAD B-rep; topology order from the CAD assembly names",
                },
            )
        )

    return Skeleton(
        source={
            "file": Path(assembly.source_path).name,
            "parts": assembly.part_count,
            "instances": assembly.instance_count,
            "units": assembly.units,
        },
        bodies=bodies,
        joints=joints,
        warnings=warnings,
        summary={
            "bodies": len(bodies),
            "joints": len(joints),
            "instances_assigned": sum(len(b.instance_ids) for b in bodies),
            "parts_assigned": len({p for b in bodies for p in b.part_ids}),
            "servos": [s.link_id for s in servos],
            "limits": "unknown; the CAD carries no travel limits",
            "topology_source": "CAD assembly names, not geometry",
        },
    )


def apply_limits(
    skeleton: Skeleton, limits: dict[str, dict], source: str
) -> Skeleton:
    """Attach travel limits a caller has a source for, recording that source.

    The CAD carries no limits, so this is the one place a number can enter the skeleton that did not
    come out of the geometry. It is an explicit act with a named source, never an inference. A joint
    the limits file does not mention keeps ``None``, which is what keeps "unknown" from decaying into
    a plausible default.
    """
    wanted = {k: v for k, v in limits.items()}
    joints = []
    attached = 0
    for joint in skeleton.joints:
        entry = wanted.get(joint.joint_id)
        if entry is None:
            joints.append(joint)
            continue
        lower = float(entry["lower"])
        upper = float(entry["upper"])
        if not (math.isfinite(lower) and math.isfinite(upper)) or lower >= upper:
            raise KinematicsError(
                f"{joint.joint_id}: limits {lower} to {upper} are not a usable range"
            )
        values = {"lower": lower, "upper": upper}
        for key in ("effort", "velocity"):
            if entry.get(key) is not None:
                values[key] = float(entry[key])
        joints.append(joint.model_copy(update={"limits": values, "limits_source": source}))
        attached += 1
    summary = dict(skeleton.summary)
    summary["limits"] = f"{attached} of {len(joints)} joints, sourced from {source}" if attached else (
        "unknown; the CAD carries no travel limits"
    )
    return skeleton.model_copy(update={"joints": joints, "summary": summary})


def write_skeleton(skeleton: Skeleton, path: str | Path, notice: str | None = None) -> Path:
    import textwrap

    import yaml

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # The header states what this file's own joints say. A hardcoded "UNKNOWN" line would contradict
    # the sourced limits in the body below it, and a reader would have to decide which half to trust.
    stated = skeleton.summary.get("limits")
    if stated:
        limits_block = textwrap.fill(
            f"Joint limits: {str(stated).rstrip('.')}.", width=94, initial_indent="# ",
            subsequent_indent="# "
        ) + "\n"
    else:
        limits_block = (
            "# Joint limits are UNKNOWN: the CAD carries no travel limits. Supply them from a "
            "datasheet\n# or a measurement before simulating motion this file describes.\n"
        )
    header = (
        "# RoboCAD twin joint skeleton, derived from CAD geometry.\n"
        "# Axes and origins come from the servo output shafts and drive-horn placements in the CAD.\n"
        + limits_block
        + "# Topology order is taken from the CAD's own assembly names, not from geometry.\n"
    )
    attribution = ""
    if notice:
        attribution = "".join(
            f"# {line}\n" if line else "#\n" for line in notice.strip().splitlines()
        )
        attribution += "#\n"
    out.write_text(
        header + attribution + yaml.safe_dump(
            skeleton.model_dump(mode="json", by_alias=True), sort_keys=False, allow_unicode=True
        ),
        encoding="utf-8",
    )
    return out


__all__ = [
    "BodyAssignment",
    "DerivedJoint",
    "KinematicsError",
    "SCHEMA",
    "ServoAxis",
    "Skeleton",
    "apply_limits",
    "assign_bodies",
    "derive_skeleton",
    "servo_axis",
    "write_skeleton",
]
