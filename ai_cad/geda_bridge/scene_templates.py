"""Standard manipulation scene templates for the RoboCAD GEDA Bridge.

Phase 14B provides drop-in MuJoCo/URDF-compatible scenes so `LearningRobotics` can
place a RoboCAD-designed asset into a known task. Each template returns a
`SceneDescription` that can be exported to a standalone MJCF world file.
"""
from __future__ import annotations

import datetime as dt
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ai_cad.geda_bridge.models import BundlePart


MM_TO_M = 0.001


@dataclass
class ScenePose:
    """Position (m) and orientation (quaternion w,x,y,z) in world frame."""

    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    quat: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)


@dataclass
class SceneObject:
    """A prop or manipulated object in the scene."""

    name: str
    geom_type: str  # box, sphere, cylinder, capsule, mesh
    size: tuple[float, ...] | None = None
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    quat: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    rgba: tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0)
    density: float = 1000.0
    mass: float | None = None
    mesh_file: str | None = None
    friction: tuple[float, float, float] | None = None
    contype: int | None = None
    conaffinity: int | None = None


@dataclass
class SceneGoalRegion:
    """A target region used by downstream RL/behavior-cloning code."""

    name: str
    goal_type: str  # reach, lift, push, insert, hang
    pos: tuple[float, float, float]
    size: tuple[float, float, float] | None = None
    rgba: tuple[float, float, float, float] = (0.0, 1.0, 0.0, 0.3)


@dataclass
class SceneDescription:
    """Full description of a manipulation scene."""

    name: str
    template: str
    asset_parts: list[BundlePart] = field(default_factory=list)
    asset_pose: ScenePose = field(default_factory=ScenePose)
    objects: list[SceneObject] = field(default_factory=list)
    goals: list[SceneGoalRegion] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())


class ManipulationScene:
    """Mutable builder for a manipulation scene around a RoboCAD asset."""

    def __init__(self, name: str, template: str = "custom") -> None:
        self.description = SceneDescription(name=name, template=template)

    def set_asset(self, parts: list[BundlePart], pose: ScenePose | None = None) -> "ManipulationScene":
        """Attach the RoboCAD asset (one or more BundleParts) to the scene."""
        self.description.asset_parts = list(parts)
        if pose is not None:
            self.description.asset_pose = pose
        return self

    def add_object(self, obj: SceneObject) -> "ManipulationScene":
        """Add a prop, table, target object, etc."""
        self.description.objects.append(obj)
        return self

    def define_goal_region(self, goal: SceneGoalRegion) -> "ManipulationScene":
        """Define a goal region for the task."""
        self.description.goals.append(goal)
        return self

    def to_mjcf(self, output_path: Path) -> Path:
        """Export this scene to a standalone MuJoCo MJCF file."""
        return export_scene_to_mjcf(self.description, output_path)


def _sanitize_name(name: str) -> str:
    """Make a string safe for MJCF body/geom/site names."""
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    if safe and safe[0].isdigit():
        safe = "_" + safe
    return safe or "obj"


def _euler_to_quaternion(rpy: tuple[float, float, float]) -> tuple[float, float, float, float]:
    """Convert intrinsic XYZ Euler angles (rad) to quaternion (w,x,y,z)."""
    rx, ry, rz = rpy
    cx, sx = math.cos(rx / 2), math.sin(rx / 2)
    cy, sy = math.cos(ry / 2), math.sin(ry / 2)
    cz, sz = math.cos(rz / 2), math.sin(rz / 2)
    w = cx * cy * cz + sx * sy * sz
    x = sx * cy * cz - cx * sy * sz
    y = cx * sy * cz + sx * cy * sz
    z = cx * cy * sz - sx * sy * cz
    return (w, x, y, z)


def _format_quat(q: tuple[float, float, float, float]) -> str:
    return f"{q[0]:.6f} {q[1]:.6f} {q[2]:.6f} {q[3]:.6f}"


def _format_pos(p: tuple[float, float, float]) -> str:
    return f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}"


def _multiply_quat(
    q1: tuple[float, float, float, float], q2: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    """Hamilton product q1 * q2."""
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )


def _apply_pose(
    local_pos: tuple[float, float, float], local_quat: tuple[float, float, float, float], pose: ScenePose
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """Apply a scene-level pose to a local body pos/quat."""
    # Rotate local position by asset orientation, then translate.
    q = pose.quat
    # Pure vector rotation: q * (0, x, y, z) * q_conj
    x, y, z = local_pos
    qv = (0.0, x, y, z)
    qc = (q[0], -q[1], -q[2], -q[3])
    t = _multiply_quat(q, qv)
    t = _multiply_quat(t, qc)
    world_pos = (t[1] + pose.pos[0], t[2] + pose.pos[1], t[3] + pose.pos[2])
    world_quat = _multiply_quat(pose.quat, local_quat)
    return world_pos, world_quat


def _rotation_matrix_to_quaternion(R: np.ndarray) -> tuple[float, float, float, float]:
    """Convert a 3x3 rotation matrix to a unit quaternion (w, x, y, z)."""
    trace = R[0, 0] + R[1, 1] + R[2, 2]
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return (w, x, y, z)


def _bundle_part_local_pose(part: BundlePart) -> ScenePose:
    """Extract the body-frame pose from a BundlePart transform matrix (mm -> m)."""
    if part.transform_m is None:
        return ScenePose()
    M = np.array(part.transform_m, dtype=float)
    tx, ty, tz = M[:3, 3] * MM_TO_M
    R = M[:3, :3]
    quat = _rotation_matrix_to_quaternion(R)
    return ScenePose(pos=(tx, ty, tz), quat=quat)


def export_scene_to_mjcf(scene: SceneDescription, output_path: Path) -> Path:
    """Write a standalone MuJoCo MJCF world from a SceneDescription.

    The RoboCAD asset is placed at `scene.asset_pose`. Additional scene objects
    and goal sites are added to the worldbody. The output file references mesh
    files relative to the bundle `meshes/` directory.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mujoco = ET.Element("mujoco", {"model": _sanitize_name(scene.name)})
    ET.SubElement(mujoco, "compiler", {"meshdir": "meshes", "autolimits": "true"})
    ET.SubElement(
        mujoco,
        "option",
        {
            "timestep": "0.002",
            "integrator": "implicitfast",
            "solver": "Newton",
            "iterations": "50",
            "ls_iterations": "10",
        },
    )

    asset = ET.SubElement(mujoco, "asset")
    worldbody = ET.SubElement(mujoco, "worldbody")

    # Global light + camera so the scene is viewable without a custom XML.
    ET.SubElement(worldbody, "light", {"directional": "true", "diffuse": "0.5 0.5 0.5", "pos": "0 0 3", "dir": "0 0 -1"})
    ET.SubElement(worldbody, "camera", {"name": "topdown", "pos": "0 -1.5 1.5", "quat": "0.707 0.707 0 0", "fovy": "60"})

    # Default material for props.
    ET.SubElement(asset, "texture", {"name": "grid", "type": "2d", "builtin": "checker", "width": "512", "height": "512", "rgb1": "0.1 0.1 0.1", "rgb2": "0.2 0.2 0.2"})
    ET.SubElement(asset, "material", {"name": "table_mat", "texture": "grid", "texrepeat": "5 5", "reflectance": "0.1"})

    # Register asset meshes and place asset bodies.
    for part in scene.asset_parts:
        mesh_name = _sanitize_name(part.name)
        ET.SubElement(asset, "mesh", {"name": mesh_name, "file": Path(part.mesh_file).name})

    for part in scene.asset_parts:
        body_name = _sanitize_name(part.name)
        i = part.inertial

        # Each part's body frame is defined by its assembly transform (mm) if any.
        local_pose = _bundle_part_local_pose(part)
        world_pos, world_quat = _apply_pose(local_pose.pos, local_pose.quat, scene.asset_pose)

        body = ET.SubElement(
            worldbody,
            "body",
            {
                "name": body_name,
                "pos": _format_pos(world_pos),
                "quat": _format_quat(world_quat),
            },
        )
        ixx, iyy, izz, ixy, ixz, iyz = i.inertia_tensor_kg_m2
        ET.SubElement(
            body,
            "inertial",
            {
                "pos": _format_pos(i.center_of_mass_m),
                "mass": f"{i.mass_kg:.6f}",
                "diaginertia": f"{ixx:.6e} {iyy:.6e} {izz:.6e}",
            },
        )
        ET.SubElement(
            body,
            "geom",
            {"type": "mesh", "mesh": body_name, "rgba": "0.7 0.7 0.75 1"},
        )

    # Add scene props / objects.
    for obj in scene.objects:
        _add_scene_object(worldbody, obj)

    # Add goal sites.
    for goal in scene.goals:
        ET.SubElement(
            worldbody,
            "site",
            {
                "name": _sanitize_name(goal.name),
                "pos": _format_pos(goal.pos),
                "type": "sphere",
                "size": f"{goal.size[0]:.4f}" if goal.size else "0.025",
                "rgba": f"{goal.rgba[0]} {goal.rgba[1]} {goal.rgba[2]} {goal.rgba[3]}",
            },
        )

    tree = ET.ElementTree(mujoco)
    _write_pretty_xml(tree, output_path)
    return output_path


def _add_scene_object(worldbody: ET.Element, obj: SceneObject) -> None:
    """Add a single scene object as a free or static MuJoCo body."""
    body = ET.SubElement(
        worldbody,
        "body",
        {
            "name": _sanitize_name(obj.name),
            "pos": _format_pos(obj.pos),
            "quat": _format_quat(obj.quat),
        },
    )
    if obj.mass is not None:
        ET.SubElement(
            body,
            "freejoint",
        )
        ET.SubElement(body, "inertial", {"pos": "0 0 0", "mass": f"{obj.mass:.6f}", "diaginertia": "0.001 0.001 0.001"})

    geom_attrs: dict[str, str] = {"name": _sanitize_name(obj.name) + "_geom", "type": obj.geom_type}
    if obj.geom_type == "box" and obj.size is not None:
        geom_attrs["size"] = f"{obj.size[0] / 2:.6f} {obj.size[1] / 2:.6f} {obj.size[2] / 2:.6f}"
    elif obj.geom_type in {"sphere", "capsule"} and obj.size is not None:
        geom_attrs["size"] = " ".join(f"{s:.6f}" for s in obj.size)
    elif obj.geom_type == "cylinder" and obj.size is not None:
        geom_attrs["size"] = f"{obj.size[0]:.6f} {obj.size[1]:.6f}"
    elif obj.geom_type == "mesh" and obj.mesh_file:
        geom_attrs["mesh"] = _sanitize_name(obj.name)
    else:
        geom_attrs["size"] = "0.05"

    geom_attrs["rgba"] = f"{obj.rgba[0]} {obj.rgba[1]} {obj.rgba[2]} {obj.rgba[3]}"
    geom_attrs["density"] = f"{obj.density:.1f}"
    if obj.friction is not None:
        geom_attrs["friction"] = f"{obj.friction[0]} {obj.friction[1]} {obj.friction[2]}"
    if obj.contype is not None:
        geom_attrs["contype"] = str(obj.contype)
    if obj.conaffinity is not None:
        geom_attrs["conaffinity"] = str(obj.conaffinity)

    ET.SubElement(body, "geom", geom_attrs)


def _write_pretty_xml(tree: ET.ElementTree, path: Path) -> None:
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------


def gripper_cube_grasp_template(
    asset_parts: list[BundlePart],
    table_height: float = 0.45,
    cube_size_m: float = 0.05,
    cube_pos: tuple[float, float, float] = (0.0, 0.0, 0.55),
    goal_height: float = 0.15,
) -> SceneDescription:
    """Place a parallel-jaw gripper asset above a cube on a table; goal is lifted cube."""
    scene = ManipulationScene("gripper_cube_grasp", template="gripper_cube_grasp")
    scene.set_asset(asset_parts, pose=ScenePose(pos=(0.0, 0.0, table_height + 0.15)))

    # Table.
    scene.add_object(
        SceneObject(
            name="table",
            geom_type="box",
            size=(1.0, 0.6, 0.05),
            pos=(0.0, 0.0, table_height - 0.025),
            rgba=(0.3, 0.3, 0.35, 1.0),
            density=500.0,
        )
    )
    # Target cube (manipuland).
    scene.add_object(
        SceneObject(
            name="target_cube",
            geom_type="box",
            size=(cube_size_m, cube_size_m, cube_size_m),
            pos=cube_pos,
            rgba=(1.0, 0.4, 0.2, 1.0),
            density=800.0,
            mass=0.1,
        )
    )
    # Goal: cube lifted above the table.
    scene.define_goal_region(
        SceneGoalRegion(
            name="lift_goal",
            goal_type="lift",
            pos=(cube_pos[0], cube_pos[1], cube_pos[2] + goal_height),
            size=(0.03, 0.03, 0.03),
            rgba=(0.0, 1.0, 0.0, 0.3),
        )
    )
    return scene.description


def bracket_hook_hang_template(
    asset_parts: list[BundlePart],
    wall_pos: tuple[float, float, float] = (-0.2, 0.0, 0.5),
    peg_pos: tuple[float, float, float] = (0.0, 0.0, 0.65),
) -> SceneDescription:
    """Place a wall with a peg so a bracket/hook asset can hang on it."""
    scene = ManipulationScene("bracket_hook_hang", template="bracket_hook_hang")
    scene.set_asset(asset_parts, pose=ScenePose(pos=(0.0, 0.0, 0.6), quat=_euler_to_quaternion((0.0, 0.0, math.pi / 2))))

    scene.add_object(
        SceneObject(
            name="wall",
            geom_type="box",
            size=(0.05, 0.6, 0.6),
            pos=wall_pos,
            rgba=(0.5, 0.5, 0.55, 1.0),
            density=2000.0,
        )
    )
    scene.add_object(
        SceneObject(
            name="peg",
            geom_type="cylinder",
            size=(0.012, 0.08),
            pos=peg_pos,
            quat=_euler_to_quaternion((math.pi / 2, 0.0, 0.0)),
            rgba=(0.7, 0.7, 0.75, 1.0),
            density=2000.0,
        )
    )
    scene.define_goal_region(
        SceneGoalRegion(
            name="hang_goal",
            goal_type="hang",
            pos=peg_pos,
            size=(0.04, 0.04, 0.04),
            rgba=(0.0, 1.0, 0.0, 0.3),
        )
    )
    return scene.description


def wedge_push_block_template(
    asset_parts: list[BundlePart],
    table_height: float = 0.45,
    block_size_m: float = 0.08,
    block_pos: tuple[float, float, float] = (0.25, 0.0, 0.49),
    target_pos: tuple[float, float, float] = (0.55, 0.0, 0.49),
) -> SceneDescription:
    """Place a wedge-shaped pusher asset near a block on a table; goal is pushed target zone."""
    scene = ManipulationScene("wedge_push_block", template="wedge_push_block")
    scene.set_asset(asset_parts, pose=ScenePose(pos=(0.0, 0.0, table_height + 0.03), quat=_euler_to_quaternion((0.0, 0.0, math.pi))))

    scene.add_object(
        SceneObject(
            name="table",
            geom_type="box",
            size=(1.0, 0.6, 0.05),
            pos=(0.0, 0.0, table_height - 0.025),
            rgba=(0.3, 0.3, 0.35, 1.0),
            density=500.0,
        )
    )
    scene.add_object(
        SceneObject(
            name="block",
            geom_type="box",
            size=(block_size_m, block_size_m, block_size_m),
            pos=block_pos,
            rgba=(0.2, 0.5, 0.9, 1.0),
            density=600.0,
            mass=0.2,
            friction=(0.8, 0.05, 0.05),
        )
    )
    scene.define_goal_region(
        SceneGoalRegion(
            name="push_goal",
            goal_type="push",
            pos=target_pos,
            size=(0.06, 0.06, 0.01),
            rgba=(0.0, 1.0, 0.0, 0.3),
        )
    )
    return scene.description


def peg_insertion_template(
    asset_parts: list[BundlePart],
    board_pos: tuple[float, float, float] = (0.3, 0.0, 0.45),
    hole_radius: float = 0.012,
    hole_depth: float = 0.05,
    peg_asset_offset: tuple[float, float, float] = (0.0, 0.0, 0.55),
) -> SceneDescription:
    """Place a peg asset above a board with a cylindrical hole; goal is inserted peg."""
    scene = ManipulationScene("peg_insertion", template="peg_insertion")
    scene.set_asset(asset_parts, pose=ScenePose(pos=peg_asset_offset))

    # Board with hole: modeled as four boxes around a gap.
    board_thickness = 0.02
    board_size = 0.2
    gap = hole_radius * 2.5
    half = board_size / 2
    z = board_pos[2]
    color = (0.4, 0.4, 0.45, 1.0)
    density = 1500.0

    # Four walls around the hole.
    wall_specs = [
        ("board_north", (half, (board_size - gap) / 4, board_thickness / 2), (0, gap / 2 + (board_size - gap) / 4, 0)),
        ("board_south", (half, (board_size - gap) / 4, board_thickness / 2), (0, -gap / 2 - (board_size - gap) / 4, 0)),
        ("board_east", ((board_size - gap) / 4, gap / 2, board_thickness / 2), (gap / 2 + (board_size - gap) / 4, 0, 0)),
        ("board_west", ((board_size - gap) / 4, gap / 2, board_thickness / 2), (-gap / 2 - (board_size - gap) / 4, 0, 0)),
    ]
    for name, size, offset in wall_specs:
        scene.add_object(
            SceneObject(
                name=name,
                geom_type="box",
                size=size,
                pos=(board_pos[0] + offset[0], board_pos[1] + offset[1], z),
                rgba=color,
                density=density,
            )
        )

    scene.define_goal_region(
        SceneGoalRegion(
            name="insertion_goal",
            goal_type="insert",
            pos=(board_pos[0], board_pos[1], z - hole_depth / 2),
            size=(hole_radius, hole_radius, hole_depth / 2),
            rgba=(0.0, 1.0, 0.0, 0.3),
        )
    )
    return scene.description


TEMPLATE_REGISTRY: dict[str, Any] = {
    "gripper_cube_grasp": gripper_cube_grasp_template,
    "bracket_hook_hang": bracket_hook_hang_template,
    "wedge_push_block": wedge_push_block_template,
    "peg_insertion": peg_insertion_template,
}


def build_scene(template_name: str, asset_parts: list[BundlePart], **kwargs: Any) -> SceneDescription:
    """Create a SceneDescription from a named template and a list of BundleParts."""
    if template_name not in TEMPLATE_REGISTRY:
        raise ValueError(f"Unknown scene template '{template_name}'. Available: {list(TEMPLATE_REGISTRY)}")
    return TEMPLATE_REGISTRY[template_name](asset_parts, **kwargs)
