"""Compile a kinematic skeleton plus mass properties plus collision hulls into a sim bundle.

The bundle carries an MJCF and a URDF that describe the *same* kinematics, so the two can be
compared to each other rather than trusted separately. Every body frame is placed at its joint
origin with no rotation. That choice is what makes the two files provably equivalent: MJCF body poses
and URDF joint origins then express the same numbers, and the inertia tensor needs no rotation
between the assembly frame and the body frame.

Units are metres and kilograms throughout. Mass properties are measured from the B-rep; a bundle
built on an assumed density says so in every body's warnings, and the report repeats it once.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ai_cad.compiler.collision import CollisionError, CollisionMesh, collision_mesh, write_obj
from ai_cad.compiler.kinematics import Skeleton
from ai_cad.compiler.properties import LinkMassProperties, PropertyError, link_properties
from ai_cad.importers.models import ImportedAssembly

BUNDLE_SCHEMA = "robocad.twin.bundle/1"
REPORT_SCHEMA = "robocad.twin.report/1"

# Kinematic agreement between the two files. The plan sets 1e-5 m because the writers round at 1e-6;
# the writers here print nine decimals, so the floor is 0.5e-9 per coordinate and a 1e-6 m tolerance
# measures the kinematics rather than the formatting.
FK_TOLERANCE_M = 1e-6
FK_SAMPLES = 100
FK_SEED = 0
SETTLE_SECONDS = 2.0


class BundleError(RuntimeError):
    """Raised when the three inputs cannot be assembled into a loadable model."""


class CheckResult(BaseModel):
    id: str
    status: str  # pass | warn | fail | skipped
    measured: dict = Field(default_factory=dict)
    threshold: dict = Field(default_factory=dict)
    explanation: str = ""


class BodyModel(BaseModel):
    body_id: str
    name: str
    parent: str | None = None
    joint_id: str | None = None
    axis_dir: tuple[float, float, float] = (0.0, 0.0, 1.0)
    origin_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # None means unknown, which is the CAD's own answer. A range written here without a source string
    # in ``limits_source`` is a fabricated specification.
    limits: dict[str, float] | None = None
    limits_source: str | None = None
    mass_kg: float
    com_m: tuple[float, float, float]
    inertia_6: tuple[float, float, float, float, float, float]  # ixx iyy izz ixy ixz iyz
    hull_files: list[str] = Field(default_factory=list)
    hull_count: int = 0
    part_count: int = 0
    instance_count: int = 0
    instance_ids: list[str] = Field(default_factory=list, exclude=True)
    rests_on_an_assumed_density: bool = False


class BundleModel(BaseModel):
    schema_version: str = BUNDLE_SCHEMA
    name: str
    bodies: list[BodyModel]
    total_mass_kg: float
    warnings: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------------------------------------
# build
# ------------------------------------------------------------------------------------------------
def _fmt(values) -> str:
    return " ".join(f"{float(v) + 0.0:.9f}" for v in values)


def _inertia6(props: LinkMassProperties) -> tuple[float, float, float, float, float, float]:
    m = props.inertia_kg_m2
    return (m[0][0], m[1][1], m[2][2], m[0][1], m[0][2], m[1][2])


def _mesh_plan(part_of, body: BodyModel, meshes: dict[str, CollisionMesh]) -> list[tuple[str, str, int]]:
    """(file name, instance id, hull index) for one body, in a stable order.

    Hulls are named per *instance*, not per part. Two instances of the same part sit in different
    places, so one shared file would put one of them in the wrong spot. The name uses a counter rather
    than the raw ids because instance ids are not guaranteed to be safe in a file name or an XML
    attribute.
    """
    plan: list[tuple[str, str, int]] = []
    counter = 0
    for instance_id in body.instance_ids:
        mesh = meshes.get(part_of[instance_id])
        if mesh is None:
            continue
        for index in range(mesh.hull_count):
            plan.append((f"{body.body_id}_{counter:03d}_h{index}.obj", instance_id, index))
        counter += 1
    return plan


def build_bundle(
    skeleton: Skeleton,
    assembly: ImportedAssembly,
    name: str = "so101",
    density_by_part=None,
    hull_cache: dict[str, CollisionMesh] | None = None,
) -> tuple[BundleModel, dict[str, LinkMassProperties], dict[str, CollisionMesh]]:
    """Bodies with their measured mass properties and their collision hulls."""
    joints = {j.child_body: j for j in skeleton.joints}
    properties: dict[str, LinkMassProperties] = {}
    meshes: dict[str, CollisionMesh] = {}
    hull_cache = hull_cache if hull_cache is not None else {}
    bodies: list[BodyModel] = []
    warnings: list[str] = []

    part_of = {instance.instance_id: instance.part_id for instance in assembly.instances}
    assembled: set[str] = set()
    for assignment in skeleton.bodies:
        try:
            props = link_properties(
                assembly,
                assignment.body_id,
                assignment.instance_ids,
                density_by_part,
            )
        except PropertyError as exc:
            raise BundleError(f"body {assignment.body_id}: {exc}") from exc
        properties[assignment.body_id] = props
        warnings.extend(props.warnings)

        for instance_id in assignment.instance_ids:
            part_id = part_of[instance_id]
            if part_id in assembled:
                continue
            assembled.add(part_id)
            if part_id not in hull_cache:
                part = assembly.parts[part_id]
                try:
                    hull_cache[part_id] = collision_mesh(part)
                except CollisionError as exc:
                    raise BundleError(f"part {part_id}: {exc}") from exc
            mesh = hull_cache[part_id]
            meshes[part_id] = mesh
            warnings.extend(mesh.warnings)

        joint = joints.get(assignment.body_id)
        body = BodyModel(
            body_id=assignment.body_id,
            name=assignment.name,
            parent=joint.parent_body if joint else None,
            joint_id=joint.joint_id if joint else None,
            axis_dir=joint.axis_dir if joint else (0.0, 0.0, 1.0),
            origin_m=joint.axis_point if joint else (0.0, 0.0, 0.0),
            limits=joint.limits if joint else None,
            limits_source=joint.limits_source if joint else None,
            mass_kg=props.mass_kg,
            com_m=props.com_m,
            inertia_6=_inertia6(props),
            part_count=len(assignment.part_ids),
            instance_count=len(assignment.instance_ids),
            instance_ids=list(assignment.instance_ids),
            rests_on_an_assumed_density=props.rests_on_an_assumed_density,
        )
        plan = _mesh_plan(part_of, body, meshes)
        body.hull_files = [name for name, _, _ in plan]
        body.hull_count = len(plan)
        bodies.append(body)

    total = sum(b.mass_kg for b in bodies)
    return (
        BundleModel(name=name, bodies=bodies, total_mass_kg=total, warnings=sorted(set(warnings))),
        properties,
        meshes,
    )


# ------------------------------------------------------------------------------------------------
# writers
# ------------------------------------------------------------------------------------------------
def write_meshes(
    model: BundleModel,
    assembly: ImportedAssembly,
    meshes: dict[str, CollisionMesh],
    directory: Path,
) -> Path:
    """One OBJ per hull, in the body frame, so a geom needs no placement of its own.

    A hull lives in its part frame; the instance transform puts it in the assembly frame; the body
    frame origin subtracts. Doing that here rather than in the XML means the file a reviewer opens is
    already in the coordinates the simulator will use.
    """
    directory.mkdir(parents=True, exist_ok=True)
    instance_of = {i.instance_id: i for i in assembly.instances}
    part_of = {i.instance_id: i.part_id for i in assembly.instances}
    for body in model.bodies:
        origin = body.origin_m
        for filename, instance_id, index in _mesh_plan(part_of, body, meshes):
            instance = instance_of[instance_id]
            hull = meshes[instance.part_id].hulls[index]
            m = instance.transform
            moved = []
            for x, y, z in hull.vertices:
                wx = m[0] * x + m[1] * y + m[2] * z + m[3]
                wy = m[4] * x + m[5] * y + m[6] * z + m[7]
                wz = m[8] * x + m[9] * y + m[10] * z + m[11]
                moved.append((wx - origin[0], wy - origin[1], wz - origin[2]))
            write_obj(hull.model_copy(update={"vertices": moved}), directory / filename)
    return directory


def write_mjcf(model: BundleModel, path: Path, meshdir: str = "meshes") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_id = {b.body_id: b for b in model.bodies}
    children: dict[str, list[BodyModel]] = {}
    roots: list[BodyModel] = []
    for body in model.bodies:
        if body.parent is None:
            roots.append(body)
        else:
            children.setdefault(body.parent, []).append(body)
    if len(roots) != 1:
        raise BundleError(f"{len(roots)} root bodies; a robot model must have exactly one")

    seen: dict[str, str] = {}
    for body in model.bodies:
        for name in body.hull_files:
            stem = Path(name).stem
            if stem in seen and seen[stem] != body.body_id:
                raise BundleError(
                    f"hull {name} is claimed by both {seen[stem]} and {body.body_id}; a mesh name "
                    "must be unique across the model, so two bodies cannot share one hull file"
                )
            seen[stem] = body.body_id

    lines = [
        f'<mujoco model="{model.name}">',
        f'  <compiler angle="radian" meshdir="{meshdir}"/>',
        "  <asset>",
    ]
    for body in model.bodies:
        for name in body.hull_files:
            lines.append(f'    <mesh name="{Path(name).stem}" file="{name}"/>')
    lines.append("  </asset>")
    lines.append("  <worldbody>")

    def emit(body: BodyModel, depth: int) -> None:
        pad = "  " * depth
        pos = (0.0, 0.0, 0.0)
        if body.parent is not None:
            parent = by_id[body.parent]
            pos = tuple(body.origin_m[i] - parent.origin_m[i] for i in range(3))
        attrs = f'name="{body.body_id}" pos="{_fmt(pos)}"'
        lines.append(f"{pad}<body {attrs}>")
        if body.joint_id:
            span = ""
            if body.limits and "lower" in body.limits and "upper" in body.limits:
                span = f' range="{body.limits["lower"]:.9f} {body.limits["upper"]:.9f}"'
            lines.append(
                f'{pad}  <joint name="{body.joint_id}" type="hinge" axis="{_fmt(body.axis_dir)}" '
                f'pos="0 0 0" damping="0" armature="0"{span}/>'
            )
        ix, iy, iz, ixy, ixz, iyz = body.inertia_6
        body_com = tuple(body.com_m[i] - body.origin_m[i] for i in range(3))
        lines.append(
            f'{pad}  <inertial pos="{_fmt(body_com)}" mass="{body.mass_kg:.9f}" '
            f'fullinertia="{ix:.12g} {iy:.12g} {iz:.12g} {ixy:.12g} {ixz:.12g} {iyz:.12g}"/>'
        )
        for name in body.hull_files:
            lines.append(f'{pad}  <geom name="{Path(name).stem}" type="mesh" mesh="{Path(name).stem}"/>')
        for child in children.get(body.body_id, []):
            emit(child, depth + 1)
        lines.append(f"{pad}</body>")

    emit(roots[0], 2)
    lines.append("  </worldbody>")
    lines.append("</mujoco>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_urdf(model: BundleModel, path: Path, meshdir: str = "meshes") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_id = {b.body_id: b for b in model.bodies}
    lines = [f'<robot name="{model.name}">']
    for body in model.bodies:
        lines.append(f'  <link name="{body.body_id}">')
        ix, iy, iz, ixy, ixz, iyz = body.inertia_6
        body_com = tuple(body.com_m[i] - body.origin_m[i] for i in range(3))
        lines.append(
            f'    <inertial><origin xyz="{_fmt(body_com)}" rpy="0 0 0"/>'
            f'<mass value="{body.mass_kg:.9f}"/>'
            f'<inertia ixx="{ix:.12g}" iyy="{iy:.12g}" izz="{iz:.12g}" '
            f'ixy="{ixy:.12g}" ixz="{ixz:.12g}" iyz="{iyz:.12g}"/></inertial>'
        )
        for name in body.hull_files:
            lines.append(
                f'    <collision><origin xyz="0 0 0" rpy="0 0 0"/>'
                f'<geometry><mesh filename="{meshdir}/{name}"/></geometry></collision>'
            )
            lines.append(
                f'    <visual><origin xyz="0 0 0" rpy="0 0 0"/>'
                f'<geometry><mesh filename="{meshdir}/{name}"/></geometry></visual>'
            )
        lines.append("  </link>")
    for body in model.bodies:
        if body.parent is None:
            continue
        parent = by_id[body.parent]
        pos = tuple(body.origin_m[i] - parent.origin_m[i] for i in range(3))
        span = ""
        if body.limits and "lower" in body.limits and "upper" in body.limits:
            effort = float(body.limits.get("effort", 0.0))
            velocity = float(body.limits.get("velocity", 0.0))
            span = (
                f'<limit lower="{body.limits["lower"]:.9f}" upper="{body.limits["upper"]:.9f}" '
                f'effort="{effort:.6f}" velocity="{velocity:.6f}"/>'
            )
        lines.append(
            f'  <joint name="{body.joint_id}" type="revolute">'
            f'<parent link="{body.parent}"/><child link="{body.body_id}"/>'
            f'<origin xyz="{_fmt(pos)}" rpy="0 0 0"/>'
            f'<axis xyz="{_fmt(body.axis_dir)}"/>'
            f"{span}"
            "</joint>"
        )
    # MuJoCo fuses fixed-joint children into their parent by default, which renumbers bodies and
    # makes a name-matched comparison meaningless. The URDF asks the reader not to.
    lines.append('  <mujoco><compiler fusestatic="false"/></mujoco>')
    lines.append("</robot>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


__all__ = [
    "BUNDLE_SCHEMA",
    "BundleError",
    "BundleModel",
    "BodyModel",
    "CheckResult",
    "REPORT_SCHEMA",
    "build_bundle",
    "write_mjcf",
    "write_urdf",
]
