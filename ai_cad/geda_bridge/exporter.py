"""Export RoboCAD parts and assemblies to simulation-ready MJCF / URDF bundles.

The GEDA Bridge (Phase 14A) turns a build123d shape or a RoboCAD FeatureTree into a
zip bundle containing watertight STL meshes, inertial data, an MJCF file for MuJoCo,
and a URDF file. All output uses SI units (meters, kilograms).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import uuid
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

import numpy as np
import trimesh

from ai_cad.actuator_sizing import size_actuators_for_tree
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


def _fallback_cube_mesh(size_mm: float = 10.0) -> trimesh.Trimesh:
    """Return a watertight axis-aligned cube centered at the origin."""
    extents = (size_mm, size_mm, size_mm)
    return trimesh.creation.box(extents=extents)


def _is_skeleton_part(part) -> bool:
    """True for template links that carry no CAD geometry of their own."""
    return not part.sketches and not part.features


def _capsule_between(p0: np.ndarray, p1: np.ndarray, radius: float) -> trimesh.Trimesh:
    """Return a capsule whose axis runs from p0 to p1 (millimetres)."""
    axis = p1 - p0
    length = float(np.linalg.norm(axis))
    capsule = trimesh.creation.capsule(height=length, radius=radius, count=[16, 16])
    # trimesh capsules are centred on the origin along +Z.
    transform = trimesh.geometry.align_vectors([0.0, 0.0, 1.0], axis / length)
    transform[:3, 3] = (p0 + p1) / 2
    capsule.apply_transform(transform)
    return capsule


def _skeleton_visual_mesh(
    instance,
    joints: list[KinematicJoint],
    parameters: dict[str, Any],
) -> trimesh.Trimesh:
    """Build a proportioned visual mesh for a geometry-less template link.

    Skeleton templates define a robot only by link frames and joint origins.
    The visual is derived from that skeleton: a capsule from the joint that
    drives the link to each joint it carries, a slab for feet, and a box hull
    for the trunk. It is used for display only; inertial data still comes from
    the placeholder cube so simulation behaviour is unchanged.
    """
    origin = np.array((instance.transform or {}).get("translation", (0.0, 0.0, 0.0)), dtype=float)
    name = instance.id.lower()

    def _num(key: str, default: float) -> float:
        try:
            return float(parameters.get(key, default))
        except (TypeError, ValueError):
            return default

    joint_in = next((j for j in joints if j.child_link == instance.id), None)
    start = np.array(joint_in.origin, dtype=float) - origin if joint_in is not None else np.zeros(3)
    ends = [np.array(j.origin, dtype=float) - origin for j in joints if j.parent_link == instance.id]

    reach = max([float(np.linalg.norm(e - start)) for e in ends] + [_num("thigh_length", 150.0)])
    radius = float(np.clip(reach * 0.09, 10.0, 28.0))
    meshes: list[trimesh.Trimesh] = []

    if "foot" in name:
        length = _num("foot_length", reach * 0.7)
        width = _num("foot_width", length * 0.5)
        height = max(length * 0.14, 12.0)
        slab = trimesh.creation.box(extents=(length, width, height))
        slab.apply_translation((length * 0.18, 0.0, height / 2))
        meshes.append(slab)
    elif joint_in is None and ends:
        # Trunk: box enclosing every joint it carries, padded to a solid body.
        pts = np.array(ends)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        pad = np.array([radius * 1.6, radius * 1.6, radius * 1.4])
        depth = _num("torso_depth", 0.0)
        if depth > 0.0 and (hi[1] - lo[1]) < depth:
            mid = (hi[1] + lo[1]) / 2
            lo[1], hi[1] = mid - depth / 2, mid + depth / 2
            pad[1] = 0.0
        body = trimesh.creation.box(extents=(hi - lo) + 2 * pad)
        body.apply_translation((lo + hi) / 2)
        meshes.append(body)
    else:
        for end in ends:
            if float(np.linalg.norm(end - start)) > 5.0:
                meshes.append(_capsule_between(start, end, radius))
        if not meshes:
            if "hand" in name or "effector" in name or "gripper" in name:
                palm = trimesh.creation.box(extents=(radius * 1.6, radius * 2.2, radius * 2.6))
                palm.apply_translation(start + np.array([0.0, 0.0, -radius * 1.3]))
                meshes.append(palm)
            else:
                # Joint housing (e.g. a hip or shoulder link with coincident joints).
                ball = trimesh.creation.icosphere(subdivisions=2, radius=radius * 1.25)
                ball.apply_translation(start)
                meshes.append(ball)

    return trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]


def skeleton_preview_mesh(tree: FeatureTree) -> trimesh.Trimesh | None:
    """Return one merged display mesh (mm, world frame) for a skeleton template.

    Returns ``None`` when the tree is not a pure kinematic skeleton, i.e. when
    any instance has real CAD geometry that should be built instead.
    """
    if not tree.assemblies:
        return None
    assembly = tree.assemblies[0]
    parameters = tree.parameter_dict()
    meshes: list[trimesh.Trimesh] = []
    for inst in assembly.instances:
        part = tree.find_part(inst.part_id)
        if part is None or not _is_skeleton_part(part):
            return None
        mesh = _skeleton_visual_mesh(inst, assembly.joints, parameters)
        mesh.apply_translation((inst.transform or {}).get("translation", (0.0, 0.0, 0.0)))
        meshes.append(mesh)
    if not meshes:
        return None
    return trimesh.util.concatenate(meshes)


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


def _inertial_from_mesh_m(mesh_m: trimesh.Trimesh, material: str | None = None) -> InertialData:
    """Compute SI inertial properties from a mesh already scaled to meters."""
    density = material_density(material)
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


def compute_inertial(mesh_mm: trimesh.Trimesh, material: str | None = None) -> InertialData:
    """Compute mass properties of a millimeter-scale mesh and return SI values."""
    mesh_m = mesh_mm.copy()
    mesh_m.vertices = mesh_m.vertices * MM_TO_M
    return _inertial_from_mesh_m(mesh_m, material)


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
    # Skeleton templates may contain placeholder links with no geometry. Emit a
    # minimal cube so the bundle still has valid collision/visual meshes.
    if not part.sketches and not part.features:
        return _fallback_cube_mesh(10.0)

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
    mesh_mm: trimesh.Trimesh | None = None,
    visual_mesh_mm: trimesh.Trimesh | None = None,
) -> BundlePart:
    """Build a BundlePart for one part instance.

    ``mesh_mm`` may be passed in to avoid rebuilding the same part mesh for
    multiple assembly instances. ``visual_mesh_mm`` replaces the exported mesh
    file while inertial data is still computed from ``mesh_mm``.
    """
    if mesh_mm is None:
        mesh_mm = _build_part_mesh(part, parameters, output_dir, tolerance)

    safe_part = _sanitize_name(part.id)
    safe_instance = _sanitize_name(instance_id or part.id)
    mesh_name = f"{safe_instance}_{safe_part}" if instance_id else safe_part
    mesh_file = f"meshes/{mesh_name}.stl"
    mesh_path = output_dir / mesh_file
    mesh_path.parent.mkdir(parents=True, exist_ok=True)

    # One copy: scale to meters, compute inertial, then export.
    mesh_m = mesh_mm.copy()
    mesh_m.vertices = mesh_m.vertices * MM_TO_M
    inertial = _inertial_from_mesh_m(mesh_m, part.material)
    if visual_mesh_mm is not None:
        visual_m = visual_mesh_mm.copy()
        visual_m.vertices = visual_m.vertices * MM_TO_M
        visual_m.export(mesh_path)
    else:
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


def _actuator_torque_specs(tree: FeatureTree) -> dict[str, float]:
    """Return joint_id -> peak torque (N m) from actuator sizing."""
    params = tree.parameter_dict()
    payload = float(params.get("payload_kg", 5.0))
    specs = size_actuators_for_tree(
        tree,
        payload_kg=payload,
        safety_factor=2.0,
        walking_speed_m_s=0.5,
    )
    return {
        jid: spec.torque_nm
        for jid, spec in specs.items()
        if spec.torque_nm is not None and spec.torque_nm > 0.0
    }


def _fallback_torque_nm(joint: KinematicJoint, payload_kg: float = 5.0) -> float:
    """Heuristic peak torque for joints without an actuator sizing spec."""
    G = 9.80665
    safety = 2.0
    jid = joint.id.lower()
    lever = 0.15  # generic 15 cm lever arm
    if any(k in jid for k in ("hip", "shoulder")):
        lever = 0.22
    elif any(k in jid for k in ("knee", "elbow")):
        lever = 0.24
    elif any(k in jid for k in ("ankle", "wrist", "foot", "hand")):
        lever = 0.08
    return payload_kg * G * lever * safety


def _build_body_hierarchy(
    parts: list[BundlePart], joints: list[KinematicJoint]
) -> tuple[dict[str, BundlePart], dict[str, str], dict[str, list[str]], list[BundlePart], list[tuple[KinematicJoint, str, str]]]:
    """Group bodies by parent-child links from the joint list.

    Real (non-fixed) joints and fixed attachments both define the hierarchy;
    only real joints are returned in the processed joint list.

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

    # Fixed joints carry no degree of freedom, but the child must still move
    # with its parent: nest it under the parent body instead of leaving it
    # welded to the world. Joints to "world" (or unknown links) keep the child
    # as a root body.
    for joint in joints:
        if joint.type != "fixed":
            continue
        parent = _resolve_link_name(joint.parent_link, parts)
        child = _resolve_link_name(joint.child_link, parts)
        if parent == child or child in seen_children:
            continue
        if parent not in name_to_part or child not in name_to_part:
            continue
        # Never create a cycle.
        ancestor, is_cycle = parent, False
        while ancestor in parent_map:
            ancestor = parent_map[ancestor]
            if ancestor == child:
                is_cycle = True
                break
        if is_cycle:
            continue
        seen_children.add(child)
        parent_map[child] = parent
        children_map.setdefault(parent, []).append(child)

    roots = [p for p in parts if p.name not in parent_map]
    return name_to_part, parent_map, children_map, roots, processed


def _part_world_pos_quat(part: BundlePart) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """Return the world position and quaternion of a part instance in meters."""
    if part.transform_m is not None:
        M = np.array(part.transform_m)
        return _matrix_to_pos_quat(M)
    return (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)


def _part_world_rotation(part: BundlePart) -> np.ndarray:
    """Return the 3x3 world rotation of a part instance."""
    if part.transform_m is not None:
        return np.array(part.transform_m, dtype=float)[:3, :3]
    return np.eye(3)


def _rotation_to_rpy(R: np.ndarray) -> tuple[float, float, float]:
    """Return URDF roll-pitch-yaw (rad) for a 3x3 rotation matrix."""
    M = np.eye(4)
    M[:3, :3] = R
    return _matrix_to_pos_rpy(M)[1]


def _fmt3(values) -> str:
    return " ".join(f"{float(v) + 0.0:.6f}" for v in values)


def _build_urdf(
    parts: list[BundlePart],
    output_path: Path,
    robot_name: str,
    joints: Optional[list[KinematicJoint]] = None,
) -> Path:
    """Write a URDF file with one link per part instance.

    URDF places every child link frame at its joint, relative to the parent
    link frame. Each jointed link therefore gets its frame at the joint anchor
    (with the orientation of the part instance), and its mesh and inertial
    data are offset back to where the part actually sits. Parts without a
    parent joint are fixed to the world link at their instance pose.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joints = joints or []

    robot = ET.Element("robot", {"name": _sanitize_name(robot_name)})

    world_link = ET.SubElement(robot, "link", {"name": "world"})
    _urdf_inertial(world_link, 0.0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

    name_to_part, parent_map, _, _, real_joints = _build_body_hierarchy(parts, joints)

    # Joint that attaches each child link to its parent (real or fixed).
    attach: dict[str, KinematicJoint] = {child: joint for joint, _, child in real_joints}
    for joint in joints:
        if joint.type != "fixed":
            continue
        child = _resolve_link_name(joint.child_link, parts)
        parent = _resolve_link_name(joint.parent_link, parts)
        if child not in attach and parent_map.get(child) == parent:
            attach[child] = joint

    # World pose of every link frame: joint anchor for attached links, instance
    # origin otherwise. Orientation always follows the part instance.
    frame_pos: dict[str, np.ndarray] = {}
    frame_rot: dict[str, np.ndarray] = {}
    inst_pos: dict[str, np.ndarray] = {}
    for part in parts:
        pos_world, _ = _part_world_pos_quat(part)
        inst_pos[part.name] = np.array(pos_world, dtype=float)
        frame_rot[part.name] = _part_world_rotation(part)
        joint = attach.get(part.name)
        frame_pos[part.name] = (
            np.array(_joint_origin_m(joint), dtype=float) if joint is not None else inst_pos[part.name]
        )

    for part in parts:
        link_name = _sanitize_name(part.name)
        link = ET.SubElement(robot, "link", {"name": link_name})
        # Offset from the link frame back to the origin of the part itself.
        offset = frame_rot[part.name].T @ (inst_pos[part.name] - frame_pos[part.name])

        i = part.inertial
        com = offset + np.array(i.center_of_mass_m, dtype=float)
        _urdf_inertial(link, i.mass_kg, tuple(float(v) + 0.0 for v in com), i.inertia_tensor_kg_m2)

        for tag in ("visual", "collision"):
            elem = ET.SubElement(link, tag)
            ET.SubElement(elem, "origin", {"xyz": _fmt3(offset), "rpy": "0 0 0"})
            geom = ET.SubElement(elem, "geometry")
            ET.SubElement(geom, "mesh", {"filename": part.mesh_file, "scale": "1 1 1"})

    for part in parts:
        link_name = _sanitize_name(part.name)
        joint = attach.get(part.name)
        parent_name = parent_map.get(part.name) if joint is not None else None

        if joint is None or parent_name not in name_to_part:
            joint_elem = ET.SubElement(robot, "joint", {"name": f"{link_name}_fixed", "type": "fixed"})
            ET.SubElement(joint_elem, "parent", {"link": "world"})
            ET.SubElement(joint_elem, "child", {"link": link_name})
            ET.SubElement(
                joint_elem,
                "origin",
                {"xyz": _fmt3(frame_pos[part.name]), "rpy": _fmt3(_rotation_to_rpy(frame_rot[part.name]))},
            )
            continue

        parent_rot = frame_rot[parent_name]
        rel_pos = parent_rot.T @ (frame_pos[part.name] - frame_pos[parent_name])
        rel_rot = parent_rot.T @ frame_rot[part.name]
        joint_elem = ET.SubElement(robot, "joint", {"name": _sanitize_name(joint.id), "type": joint.type})
        ET.SubElement(joint_elem, "parent", {"link": _sanitize_name(parent_name)})
        ET.SubElement(joint_elem, "child", {"link": link_name})
        ET.SubElement(joint_elem, "origin", {"xyz": _fmt3(rel_pos), "rpy": _fmt3(_rotation_to_rpy(rel_rot))})
        if joint.type in ("revolute", "prismatic"):
            # The axis is given in the world frame; URDF wants it in the joint frame.
            axis = frame_rot[part.name].T @ np.array(_joint_axis(joint), dtype=float)
            ET.SubElement(joint_elem, "axis", {"xyz": _fmt3(axis)})
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
    torque_specs: Optional[dict[str, float]] = None,
    default_payload_kg: float = 5.0,
) -> Path:
    """Write a MuJoCo MJCF file with nested bodies and real joints.

    Child bodies are placed inside their parent body according to the joint
    hierarchy. Each real joint becomes a ``<joint>`` inside its child body, and
    actuators/sensors are emitted for every revolute/prismatic joint.

    ``torque_specs`` maps joint id to peak motor torque in N m.  When absent, a
    conservative payload-based heuristic is used so that walking is physically
    plausible.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joints = joints or []
    torque_specs = torque_specs or {}

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

    def _emit_body(
        parent_elem: ET.Element,
        part: BundlePart,
        parent_world_pos: tuple[float, float, float],
        parent_world_rot: np.ndarray | None = None,
    ) -> None:
        body_name = _sanitize_name(part.name)
        if body_name in built:
            return
        built.add(body_name)

        # MJCF body poses are relative to the parent body frame, so express the
        # world pose of this instance in the (possibly rotated) parent frame.
        pos_world, _ = _part_world_pos_quat(part)
        rot_world = _part_world_rotation(part)
        parent_rot = np.eye(3) if parent_world_rot is None else parent_world_rot
        rel_pos = parent_rot.T @ (np.array(pos_world) - np.array(parent_world_pos))
        quat = _rotation_matrix_to_quaternion(parent_rot.T @ rot_world)

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
            # Joint anchor and axis are given in the world frame; MJCF wants
            # them in the child body frame.
            joint_rel = rot_world.T @ (np.array(_joint_origin_m(joint)) - np.array(pos_world))
            axis = rot_world.T @ np.array(_joint_axis(joint))
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
                _emit_body(body, child_part, pos_world, rot_world)

    for root in roots:
        _emit_body(worldbody, root, (0.0, 0.0, 0.0))

    if actuated_joints:
        actuator = ET.SubElement(mujoco, "actuator")
        for joint in actuated_joints:
            jname = _sanitize_name(joint.id)
            peak = torque_specs.get(joint.id)
            if peak is None or peak <= 0.0:
                peak = _fallback_torque_nm(joint, default_payload_kg)
            ET.SubElement(
                actuator,
                "motor",
                {
                    "name": f"{jname}_motor",
                    "joint": jname,
                    "ctrlrange": f"{-peak:.6f} {peak:.6f}",
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


def _param_hash(parameters: dict[str, Any]) -> str:
    """Stable hash for part-parameter deduplication."""
    try:
        return str(hash(json.dumps(parameters, sort_keys=True, default=str)))
    except Exception:
        return str(uuid.uuid4())


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

    # Cache per-unique-part meshes so multiple instances do not rebuild.
    part_mesh_cache: dict[tuple[str, str, float], trimesh.Trimesh] = {}

    if tree.assemblies:
        from ai_cad.assembly import compute_instance_transforms

        assembly = tree.assemblies[0]
        joints = assembly.joints
        transforms = compute_instance_transforms(tree, assembly, parameters)
        for inst in assembly.instances:
            part = tree.find_part(inst.part_id)
            if part is None:
                continue
            cache_key = (part.id, _param_hash(parameters), tolerance)
            if cache_key not in part_mesh_cache:
                part_mesh_cache[cache_key] = _build_part_mesh(
                    part, parameters, output_dir, tolerance
                )
            mesh_mm = part_mesh_cache[cache_key]
            M = transforms.get(inst.id, np.eye(4))
            visual_mesh_mm = None
            if _is_skeleton_part(part) and joints:
                try:
                    visual_mesh_mm = _skeleton_visual_mesh(inst, joints, parameters)
                except Exception:
                    visual_mesh_mm = None
            parts.append(
                _build_bundle_part(
                    part,
                    inst.id,
                    M,
                    output_dir,
                    parameters,
                    tolerance,
                    mesh_mm=mesh_mm,
                    visual_mesh_mm=visual_mesh_mm,
                )
            )
    else:
        if not tree.parts:
            raise ValueError("FeatureTree has no parts.")
        part = tree.parts[0]
        parts.append(_build_bundle_part(part, None, None, output_dir, parameters, tolerance))

    if not parts:
        raise ValueError("No parts could be exported.")

    # Skeleton templates were tuned with their fixed end links (e.g. hands)
    # exported as separate static bodies. Keep that behaviour for geometry-less
    # links; links with real geometry are nested under their parent body.
    if joints and tree.assemblies:
        skeleton_instances = {
            inst.id
            for inst in tree.assemblies[0].instances
            if (part := tree.find_part(inst.part_id)) is not None and _is_skeleton_part(part)
        }
        joints = [
            j for j in joints
            if not (j.type == "fixed" and j.child_link in skeleton_instances)
        ]

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
    inertial_path.write_text(json.dumps(inertial_data, indent=2), encoding="utf-8")
    _build_urdf(parts, urdf_path, name, joints=joints)
    torque_specs = _actuator_torque_specs(tree) if tree.assemblies else {}
    payload_kg = float(parameters.get("payload_kg", 5.0))
    _build_mjcf(
        parts,
        mjcf_path,
        name,
        joints=joints,
        torque_specs=torque_specs,
        default_payload_kg=payload_kg,
    )

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

    safe_name = _sanitize_name(name)
    mesh_file = f"meshes/{safe_name}.stl"
    mesh_path = output_dir / mesh_file
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    # One copy: scale to meters, compute inertial, then export.
    mesh_m = mesh_mm.copy()
    mesh_m.vertices = mesh_m.vertices * MM_TO_M
    inertial = _inertial_from_mesh_m(mesh_m, material)
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
    inertial_path.write_text(json.dumps({part.name: part.inertial.model_dump()}, indent=2), encoding="utf-8")
    _build_urdf([part], urdf_path, name)
    _build_mjcf([part], mjcf_path, name, default_payload_kg=5.0)

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
