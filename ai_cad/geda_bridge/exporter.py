"""Export RoboCAD parts and assemblies to simulation-ready MJCF / URDF bundles.

The GEDA Bridge (Phase 14A) turns a build123d shape or a RoboCAD FeatureTree into a
zip bundle containing watertight STL meshes, inertial data, an MJCF file for MuJoCo,
and a URDF file. All output uses SI units (meters, kilograms).
"""
from __future__ import annotations

import datetime as dt
import math
import re
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

import numpy as np
import trimesh

from ai_cad.executor import execute_code
from ai_cad.feature_tree import FeatureTree, KinematicJoint
from ai_cad.geda_bridge.models import (
    BundleManifest,
    BundlePart,
    BundlePaths,
    InertialData,
)

# Material density lookup in kg/m³.
_MATERIAL_DENSITIES: dict[str, float] = {
    "pla": 1250.0,
    "petg": 1270.0,
    "abs": 1050.0,
    "nylon": 1150.0,
    "tpu": 1200.0,
    "aluminum": 2700.0,
    "aluminium": 2700.0,
    "steel": 7850.0,
    "stainless_steel": 8000.0,
    "titanium": 4500.0,
    "brass": 8500.0,
    "copper": 8960.0,
    "wood": 700.0,
    "default": 1000.0,
}


MM_TO_M = 0.001


def material_density(material: str | None) -> float:
    """Return density in kg/m³ for a material name, falling back to default."""
    key = (material or "default").lower().replace(" ", "_").replace("-", "_")
    return _MATERIAL_DENSITIES.get(key, _MATERIAL_DENSITIES["default"])


def _sanitize_name(name: str) -> str:
    """Make a string safe for URDF/MJCF link and mesh names."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if safe[0].isdigit():
        safe = "_" + safe
    return safe


def _render_parameter_value(value: Any) -> str:
    """Emit a numeric parameter value for generated Python code."""
    if isinstance(value, str):
        try:
            float(value)
            return value
        except ValueError:
            return repr(value)
    if isinstance(value, int):
        return str(value)
    return str(float(value))


def shape_to_trimesh(shape, tolerance: float = 0.1) -> trimesh.Trimesh:
    """Tessellate a build123d shape into a trimesh object (still in mm)."""
    raw_vertices, raw_faces = shape.tessellate(tolerance)
    verts = np.array([[float(v.X), float(v.Y), float(v.Z)] for v in raw_vertices], dtype=float)
    faces = np.asarray(raw_faces, dtype=int)
    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)


def compute_inertial(mesh_mm: trimesh.Trimesh, material: str | None = None) -> InertialData:
    """Compute mass properties of a millimeter-scale mesh and return SI values."""
    density = material_density(material)
    # Scale mesh to meters and set density.
    mesh_m = mesh_mm.copy()
    mesh_m.vertices = mesh_m.vertices * MM_TO_M
    mesh_m.density = density

    # Suppress trimesh's divide-by-zero RuntimeWarning on degenerate / tiny meshes
    # (e.g. flat collision test cubes) while still reading whatever value it returns.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mass = float(mesh_m.mass)
        com = tuple(float(x) for x in mesh_m.center_mass)
        inertia = mesh_m.moment_inertia
        # trimesh returns inertia tensor about center of mass in kg·m².
        inertia_tuple = (
            float(inertia[0, 0]),
            float(inertia[1, 1]),
            float(inertia[2, 2]),
            float(inertia[0, 1]),
            float(inertia[0, 2]),
            float(inertia[1, 2]),
        )

        try:
            principal_moments, principal_axes = mesh_m.principal_inertia_components, mesh_m.principal_inertia_vectors
            pm = tuple(float(x) for x in principal_moments)
            pa = [tuple(float(v) for v in axis) for axis in principal_axes]
        except Exception:
            pm = None
            pa = None

    return InertialData(
        mass_kg=mass,
        center_of_mass_m=com,
        inertia_tensor_kg_m2=inertia_tuple,
        principal_moments_kg_m2=pm,
        principal_axes=pa,
        density_kg_m3=density,
        material=material or "default",
    )


def _matrix_to_pos_quat(M: np.ndarray) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """Extract translation and unit quaternion from a 4x4 homogeneous matrix."""
    tx, ty, tz = M[:3, 3]
    R = M[:3, :3]
    w, x, y, z = _rotation_matrix_to_quaternion(R)
    return (tx * MM_TO_M, ty * MM_TO_M, tz * MM_TO_M), (w, x, y, z)


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


def _matrix_to_pos_rpy(M: np.ndarray) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Extract translation (m) and Euler rpy (rad, URDF order) from a 4x4 matrix."""
    tx, ty, tz = M[:3, 3]
    R = M[:3, :3]
    sy = -R[2, 0]
    if abs(sy) < 0.99999:
        rx = math.atan2(R[2, 1], R[2, 2])
        ry = math.asin(sy)
        rz = math.atan2(R[1, 0], R[0, 0])
    else:
        rx = math.atan2(-R[1, 2], R[1, 1])
        ry = math.asin(sy)
        rz = 0.0
    return (tx * MM_TO_M, ty * MM_TO_M, tz * MM_TO_M), (rx, ry, rz)


def export_shape_to_stl(shape, output_path: Path, tolerance: float = 0.1) -> Path:
    """Tessellate a build123d shape and save a watertight binary STL."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mesh = shape_to_trimesh(shape, tolerance)
    mesh.fix_normals()
    mesh.merge_vertices()
    mesh.export(output_path)
    return output_path


def _transpile_single_part_code(part, parameters: dict[str, Any]) -> str:
    """Generate build123d code that exports a single part to result = part.part."""
    from ai_cad.transpiler import _transpile_part

    lines = ["from build123d import *"]
    for name, value in parameters.items():
        lines.append(f"{name} = {_render_parameter_value(value)}")
    lines.extend(_transpile_part(part, parameters, var_name="part"))
    lines.append("")
    lines.append("result = part.part")
    return "\n".join(lines)


def _build_part_mesh(
    part,
    parameters: dict[str, Any],
    output_dir: Path,
    tolerance: float = 0.1,
) -> trimesh.Trimesh:
    """Generate and tessellate a single FeatureTree part."""
    code = _transpile_single_part_code(part, parameters)
    exec_result = execute_code(code, timeout=60, output_dir=output_dir)
    if not exec_result.get("success"):
        raise RuntimeError(f"Failed to execute part '{part.id}': {exec_result.get('traceback', exec_result.get('error'))}")
    stl_path = exec_result.get("stl_path")
    if not stl_path or not Path(stl_path).exists():
        raise RuntimeError(f"Part '{part.id}' produced no STL output.")
    mesh = trimesh.load_mesh(stl_path)
    if isinstance(mesh, trimesh.Scene):
        if len(mesh.geometry) == 1:
            mesh = next(iter(mesh.geometry.values()))
        else:
            raise RuntimeError(f"Part '{part.id}' STL contains multiple bodies; cannot compute inertial data.")
    return mesh


def _build_bundle_part(
    part,
    instance_id: str | None,
    transform_m: np.ndarray | None,
    output_dir: Path,
    parameters: dict[str, Any],
    tolerance: float = 0.1,
) -> BundlePart:
    """Build a BundlePart for one part instance."""
    mesh_mm = _build_part_mesh(part, parameters, output_dir, tolerance)
    inertial = compute_inertial(mesh_mm, part.material)

    safe_part = _sanitize_name(part.id)
    safe_instance = _sanitize_name(instance_id or part.id)
    mesh_name = f"{safe_instance}_{safe_part}" if instance_id else safe_part
    mesh_file = f"meshes/{mesh_name}.stl"
    mesh_path = output_dir / mesh_file
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    # Store the mesh in meters (manifest declares length_unit="m").
    mesh_m = mesh_mm.copy()
    mesh_m.vertices = mesh_m.vertices * MM_TO_M
    mesh_m.export(mesh_path)

    transform_m_list = None
    if transform_m is not None:
        transform_m_list = [[float(v) for v in row] for row in transform_m]

    return BundlePart(
        part_id=part.id,
        instance_id=instance_id,
        name=mesh_name,
        material=inertial.material,
        density_kg_m3=inertial.density_kg_m3,
        mesh_file=mesh_file,
        inertial=inertial,
        transform_m=transform_m_list,
    )


def _resolve_link_name(ref: str, parts: list[BundlePart]) -> str:
    """Map a joint parent_link/child_link reference to a BundlePart link name."""
    name_map = {p.name: p for p in parts}
    if ref in name_map:
        return ref
    for p in parts:
        if p.instance_id == ref:
            return p.name
    for p in parts:
        if p.part_id == ref:
            return p.name
    return _sanitize_name(ref)


def _joint_origin_m(joint: KinematicJoint) -> tuple[float, float, float]:
    """Return the joint origin in meters (FeatureTree stores mm by default)."""
    return tuple(float(v) * MM_TO_M for v in joint.origin)


def _joint_limits_native(joint: KinematicJoint) -> tuple[float, float]:
    """Return joint limits in native URDF/MuJoCo units (radians / meters)."""
    if joint.limits is not None:
        lower, upper = joint.limits
        if joint.type == "revolute":
            return math.radians(lower), math.radians(upper)
        if joint.type == "prismatic":
            return float(lower) * MM_TO_M, float(upper) * MM_TO_M
    if joint.type == "revolute":
        return -math.pi, math.pi
    if joint.type == "prismatic":
        return -0.05, 0.05
    return 0.0, 0.0


def _joint_axis(joint: KinematicJoint) -> tuple[float, float, float]:
    """Return a normalized joint axis with sensible defaults."""
    if joint.axis is not None:
        a = np.array(joint.axis, dtype=float)
        norm = np.linalg.norm(a)
        if norm > 1e-9:
            return tuple(float(v) for v in a / norm)
    if joint.type == "prismatic":
        return (1.0, 0.0, 0.0)
    return (0.0, 0.0, 1.0)


def _build_body_hierarchy(
    parts: list[BundlePart], joints: list[KinematicJoint]
) -> tuple[dict[str, BundlePart], dict[str, str], dict[str, list[str]], list[BundlePart], list[tuple[KinematicJoint, str, str]]]:
    """Group bodies by parent-child links from real (non-fixed) joints.

    Returns:
        name_to_part mapping, parent map, children map, root bodies, and a list
        of (joint, parent_name, child_name) tuples for real joints.
    """
    name_to_part = {p.name: p for p in parts}
    parent_map: dict[str, str] = {}
    children_map: dict[str, list[str]] = {}
    processed: list[tuple[KinematicJoint, str, str]] = []
    seen_children: set[str] = set()

    for joint in joints:
        if joint.type == "fixed":
            continue
        parent = _resolve_link_name(joint.parent_link, parts)
        child = _resolve_link_name(joint.child_link, parts)
        if parent == child or child in seen_children:
            continue
        seen_children.add(child)
        parent_map[child] = parent
        children_map.setdefault(parent, []).append(child)
        processed.append((joint, parent, child))

    roots = [p for p in parts if p.name not in parent_map]
    return name_to_part, parent_map, children_map, roots, processed


def _part_world_pos_quat(part: BundlePart) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """Return the world position and quaternion of a part instance in meters."""
    if part.transform_m is not None:
        M = np.array(part.transform_m)
        return _matrix_to_pos_quat(M)
    return (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)


def _build_urdf(
    parts: list[BundlePart],
    output_path: Path,
    robot_name: str,
    joints: Optional[list[KinematicJoint]] = None,
) -> Path:
    """Write a URDF file with one link per part instance.

    Parts that are children of a real (non-fixed) joint are connected by that
    joint; all other parts remain fixed to the world link.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joints = joints or []

    robot = ET.Element("robot", {"name": _sanitize_name(robot_name)})

    world_link = ET.SubElement(robot, "link", {"name": "world"})
    _urdf_inertial(world_link, 0.0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

    _, _, _, _, real_joints = _build_body_hierarchy(parts, joints)
    real_joint_children = {child for _, _, child in real_joints}

    for part in parts:
        link_name = _sanitize_name(part.name)
        link = ET.SubElement(robot, "link", {"name": link_name})

        i = part.inertial
        _urdf_inertial(
            link,
            i.mass_kg,
            i.center_of_mass_m,
            i.inertia_tensor_kg_m2,
        )

        visual = ET.SubElement(link, "visual")
        ET.SubElement(visual, "origin", {"xyz": "0 0 0", "rpy": "0 0 0"})
        geom = ET.SubElement(visual, "geometry")
        ET.SubElement(geom, "mesh", {"filename": part.mesh_file, "scale": "1 1 1"})

        collision = ET.SubElement(link, "collision")
        ET.SubElement(collision, "origin", {"xyz": "0 0 0", "rpy": "0 0 0"})
        cgeom = ET.SubElement(collision, "geometry")
        ET.SubElement(cgeom, "mesh", {"filename": part.mesh_file, "scale": "1 1 1"})

    for part in parts:
        link_name = _sanitize_name(part.name)
        if link_name in real_joint_children:
            continue

        if part.transform_m is not None:
            M = np.array(part.transform_m)
            pos, rpy = _matrix_to_pos_rpy(M)
        else:
            pos, rpy = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

        joint_name = f"{link_name}_fixed"
        joint = ET.SubElement(
            robot,
            "joint",
            {"name": joint_name, "type": "fixed"},
        )
        ET.SubElement(joint, "parent", {"link": "world"})
        ET.SubElement(joint, "child", {"link": link_name})
        ET.SubElement(
            joint,
            "origin",
            {
                "xyz": f"{pos[0]:.6f} {pos[1]:.6f} {pos[2]:.6f}",
                "rpy": f"{rpy[0]:.6f} {rpy[1]:.6f} {rpy[2]:.6f}",
            },
        )

    for joint, parent_name, child_name in real_joints:
        joint_name = _sanitize_name(joint.id)
        joint_elem = ET.SubElement(
            robot,
            "joint",
            {"name": joint_name, "type": joint.type},
        )
        ET.SubElement(joint_elem, "parent", {"link": _sanitize_name(parent_name)})
        ET.SubElement(joint_elem, "child", {"link": _sanitize_name(child_name)})
        origin_m = _joint_origin_m(joint)
        ET.SubElement(
            joint_elem,
            "origin",
            {
                "xyz": f"{origin_m[0]:.6f} {origin_m[1]:.6f} {origin_m[2]:.6f}",
                "rpy": "0 0 0",
            },
        )
        if joint.type in ("revolute", "prismatic"):
            axis = _joint_axis(joint)
            ET.SubElement(
                joint_elem,
                "axis",
                {"xyz": f"{axis[0]:.6f} {axis[1]:.6f} {axis[2]:.6f}"},
            )
            if joint.limits is not None:
                lower, upper = _joint_limits_native(joint)
                ET.SubElement(
                    joint_elem,
                    "limit",
                    {
                        "lower": f"{lower:.6f}",
                        "upper": f"{upper:.6f}",
                        "effort": "10",
                        "velocity": "10",
                    },
                )

    tree = ET.ElementTree(robot)
    _write_pretty_xml(tree, output_path)
    return output_path


def _urdf_inertial(parent, mass: float, com: tuple[float, float, float], inertia: tuple[float, ...]) -> None:
    """Append a URDF inertial block."""
    inertial = ET.SubElement(parent, "inertial")
    ET.SubElement(
        inertial,
        "origin",
        {"xyz": f"{com[0]:.6f} {com[1]:.6f} {com[2]:.6f}", "rpy": "0 0 0"},
    )
    ET.SubElement(inertial, "mass", {"value": f"{mass:.6f}"})
    ixx, iyy, izz, ixy, ixz, iyz = inertia
    ET.SubElement(
        inertial,
        "inertia",
        {
            "ixx": f"{ixx:.6e}",
            "iyy": f"{iyy:.6e}",
            "izz": f"{izz:.6e}",
            "ixy": f"{ixy:.6e}",
            "ixz": f"{ixz:.6e}",
            "iyz": f"{iyz:.6e}",
        },
    )


def _build_mjcf(
    parts: list[BundlePart],
    output_path: Path,
    model_name: str,
    joints: Optional[list[KinematicJoint]] = None,
) -> Path:
    """Write a MuJoCo MJCF file with nested bodies and real joints.

    Child bodies are placed inside their parent body according to the joint
    hierarchy. Each real joint becomes a ``<joint>`` inside its child body, and
    actuators/sensors are emitted for every revolute/prismatic joint.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joints = joints or []

    name_to_part, _, children_map, roots, real_joints = _build_body_hierarchy(parts, joints)
    actuated_joints = [joint for joint, _, _ in real_joints if joint.type in ("revolute", "prismatic")]

    mujoco = ET.Element("mujoco", {"model": _sanitize_name(model_name)})
    ET.SubElement(mujoco, "compiler", {"meshdir": "meshes", "autolimits": "true"})
    asset = ET.SubElement(mujoco, "asset")
    worldbody = ET.SubElement(mujoco, "worldbody")

    for part in parts:
        mesh_name = _sanitize_name(part.name)
        ET.SubElement(asset, "mesh", {"name": mesh_name, "file": Path(part.mesh_file).name})

    built: set[str] = set()

    def _emit_body(parent_elem: ET.Element, part: BundlePart, parent_world_pos: tuple[float, float, float]) -> None:
        body_name = _sanitize_name(part.name)
        if body_name in built:
            return
        built.add(body_name)

        pos_world, quat = _part_world_pos_quat(part)
        rel_pos = (
            pos_world[0] - parent_world_pos[0],
            pos_world[1] - parent_world_pos[1],
            pos_world[2] - parent_world_pos[2],
        )

        body = ET.SubElement(
            parent_elem,
            "body",
            {
                "name": body_name,
                "pos": f"{rel_pos[0]:.6f} {rel_pos[1]:.6f} {rel_pos[2]:.6f}",
            },
        )
        if not np.allclose(quat, (1.0, 0.0, 0.0, 0.0), atol=1e-6):
            body.set("quat", f"{quat[0]:.6f} {quat[1]:.6f} {quat[2]:.6f} {quat[3]:.6f}")

        i = part.inertial
        com = i.center_of_mass_m
        ixx, iyy, izz, ixy, ixz, iyz = i.inertia_tensor_kg_m2
        ET.SubElement(
            body,
            "inertial",
            {
                "pos": f"{com[0]:.6f} {com[1]:.6f} {com[2]:.6f}",
                "mass": f"{i.mass_kg:.6f}",
                "diaginertia": f"{ixx:.6e} {iyy:.6e} {izz:.6e}",
            },
        )
        ET.SubElement(
            body,
            "geom",
            {"type": "mesh", "mesh": body_name, "rgba": "0.8 0.8 0.8 1"},
        )

        for joint, _, child_name in real_joints:
            if child_name != part.name:
                continue
            joint_origin_m = _joint_origin_m(joint)
            joint_rel = (
                joint_origin_m[0] - pos_world[0],
                joint_origin_m[1] - pos_world[1],
                joint_origin_m[2] - pos_world[2],
            )
            axis = _joint_axis(joint)
            lower, upper = _joint_limits_native(joint)

            if joint.type == "revolute":
                ET.SubElement(
                    body,
                    "joint",
                    {
                        "name": _sanitize_name(joint.id),
                        "type": "hinge",
                        "pos": f"{joint_rel[0]:.6f} {joint_rel[1]:.6f} {joint_rel[2]:.6f}",
                        "axis": f"{axis[0]:.6f} {axis[1]:.6f} {axis[2]:.6f}",
                        "range": f"{lower:.6f} {upper:.6f}",
                    },
                )
            elif joint.type == "prismatic":
                ET.SubElement(
                    body,
                    "joint",
                    {
                        "name": _sanitize_name(joint.id),
                        "type": "slide",
                        "pos": f"{joint_rel[0]:.6f} {joint_rel[1]:.6f} {joint_rel[2]:.6f}",
                        "axis": f"{axis[0]:.6f} {axis[1]:.6f} {axis[2]:.6f}",
                        "range": f"{lower:.6f} {upper:.6f}",
                    },
                )
            elif joint.type == "spherical":
                ET.SubElement(
                    body,
                    "joint",
                    {
                        "name": _sanitize_name(joint.id),
                        "type": "ball",
                        "pos": f"{joint_rel[0]:.6f} {joint_rel[1]:.6f} {joint_rel[2]:.6f}",
                    },
                )

        for child_name in children_map.get(body_name, []):
            child_part = name_to_part.get(child_name)
            if child_part is not None:
                _emit_body(body, child_part, pos_world)

    for root in roots:
        _emit_body(worldbody, root, (0.0, 0.0, 0.0))

    if actuated_joints:
        actuator = ET.SubElement(mujoco, "actuator")
        for joint in actuated_joints:
            jname = _sanitize_name(joint.id)
            lower, upper = _joint_limits_native(joint)
            ET.SubElement(
                actuator,
                "motor",
                {
                    "name": f"{jname}_motor",
                    "joint": jname,
                    "ctrlrange": f"{lower:.6f} {upper:.6f}",
                    "gear": "1",
                },
            )

        sensor = ET.SubElement(mujoco, "sensor")
        for joint in actuated_joints:
            jname = _sanitize_name(joint.id)
            ET.SubElement(sensor, "jointpos", {"name": f"{jname}_pos", "joint": jname})
            ET.SubElement(sensor, "jointvel", {"name": f"{jname}_vel", "joint": jname})
            ET.SubElement(sensor, "jointactuatorfrc", {"name": f"{jname}_force", "joint": jname})

    tree = ET.ElementTree(mujoco)
    _write_pretty_xml(tree, output_path)
    return output_path


def _write_pretty_xml(tree: ET.ElementTree, path: Path) -> None:
    """Write an XML tree with pretty indentation and an XML declaration."""
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def export_bundle_from_tree(
    tree: FeatureTree,
    output_dir: Path,
    name: str = "model",
    tolerance: float = 0.1,
) -> BundlePaths:
    """Export a RoboCAD FeatureTree to a simulation-ready bundle directory."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    parameters = tree.parameter_dict()
    parts: list[BundlePart] = []
    joints: list[KinematicJoint] = []

    if tree.assemblies:
        from ai_cad.assembly import compute_instance_transforms

        assembly = tree.assemblies[0]
        joints = assembly.joints
        transforms = compute_instance_transforms(tree, assembly, parameters)
        for inst in assembly.instances:
            part = tree.find_part(inst.part_id)
            if part is None:
                continue
            M = transforms.get(inst.id, np.eye(4))
            parts.append(
                _build_bundle_part(
                    part,
                    inst.id,
                    M,
                    output_dir,
                    parameters,
                    tolerance,
                )
            )
    else:
        if not tree.parts:
            raise ValueError("FeatureTree has no parts.")
        part = tree.parts[0]
        parts.append(_build_bundle_part(part, None, None, output_dir, parameters, tolerance))

    if not parts:
        raise ValueError("No parts could be exported.")

    manifest = BundleManifest(
        design_id=tree.design_id,
        name=name,
        created_at=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        parts=parts,
    )

    urdf_path = output_dir / f"{name}.urdf"
    mjcf_path = output_dir / f"{name}.mjcf"
    manifest.urdf_file = urdf_path.name
    manifest.mjcf_file = mjcf_path.name

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    inertial_path = output_dir / "inertial.json"
    inertial_data = {p.name: p.inertial.model_dump() for p in parts}
    import json

    inertial_path.write_text(json.dumps(inertial_data, indent=2), encoding="utf-8")
    _build_urdf(parts, urdf_path, name, joints=joints)
    _build_mjcf(parts, mjcf_path, name, joints=joints)

    return BundlePaths(
        directory=output_dir,
        manifest_json=manifest_path,
        meshes_dir=output_dir / "meshes",
        urdf=urdf_path,
        mjcf=mjcf_path,
        inertial_json=inertial_path,
    )


def export_bundle_from_mesh(
    mesh_mm: trimesh.Trimesh,
    output_dir: Path,
    name: str = "model",
    material: str | None = None,
) -> BundlePaths:
    """Export a single trimesh object (in mm) to a simulation-ready bundle directory."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    inertial = compute_inertial(mesh_mm, material)

    safe_name = _sanitize_name(name)
    mesh_file = f"meshes/{safe_name}.stl"
    mesh_path = output_dir / mesh_file
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    # Store the mesh in meters (manifest declares length_unit="m").
    mesh_m = mesh_mm.copy()
    mesh_m.vertices = mesh_m.vertices * MM_TO_M
    mesh_m.export(mesh_path)

    part = BundlePart(
        part_id=safe_name,
        instance_id=None,
        name=safe_name,
        material=inertial.material,
        density_kg_m3=inertial.density_kg_m3,
        mesh_file=mesh_file,
        inertial=inertial,
        transform_m=None,
    )

    manifest = BundleManifest(
        name=name,
        created_at=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        parts=[part],
    )

    urdf_path = output_dir / f"{name}.urdf"
    mjcf_path = output_dir / f"{name}.mjcf"
    manifest.urdf_file = urdf_path.name
    manifest.mjcf_file = mjcf_path.name

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    inertial_path = output_dir / "inertial.json"
    import json

    inertial_path.write_text(json.dumps({part.name: part.inertial.model_dump()}, indent=2), encoding="utf-8")
    _build_urdf([part], urdf_path, name)
    _build_mjcf([part], mjcf_path, name)

    return BundlePaths(
        directory=output_dir,
        manifest_json=manifest_path,
        meshes_dir=output_dir / "meshes",
        urdf=urdf_path,
        mjcf=mjcf_path,
        inertial_json=inertial_path,
    )


def export_bundle_from_shape(
    shape,
    output_dir: Path,
    name: str = "model",
    material: str | None = None,
    tolerance: float = 0.1,
) -> BundlePaths:
    """Export a single build123d shape to a simulation-ready bundle directory."""
    mesh_mm = shape_to_trimesh(shape, tolerance)
    return export_bundle_from_mesh(mesh_mm, output_dir, name=name, material=material)
