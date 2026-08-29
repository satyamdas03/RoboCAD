"""Assembly support for RoboCAD Phase 11.

This module computes transforms for part instances from explicit transform specs
and from LCS-based mates. For Phase 11 the scope is intentionally simple:
- instances can be placed by an explicit translation/rotation transform
- mates: coincident (origin alignment), concentric (share Z axis), distance (offset),
  angle, parallel, perpendicular, fixed
- assembly export builds a Compound of placed BuildPart objects

Mates are solved in a single pass: each mate contributes a target transform for one
or both instance origins, and the solver averages conflicting targets and applies
offsets for distance/angle mates.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from ai_cad.feature_tree import Assembly, CoordinateSystem, FeatureTree, Instance, Mate, MateEntity
from ai_cad.transpiler import _transpile_part


def _resolve_value(value: Any, parameters: dict[str, float]) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        if value in parameters:
            return float(parameters[value])
        try:
            return float(eval(value, {"__builtins__": {}}, parameters))  # noqa: S307
        except Exception:
            raise ValueError(f"Could not resolve value: {value!r}")
    raise TypeError(f"Unsupported value type: {type(value)}")


def _csys_by_id(tree: FeatureTree, csys_id: str) -> CoordinateSystem:
    for csys in tree.coordinate_systems:
        if csys.id == csys_id:
            return csys
    raise ValueError(f"Coordinate system '{csys_id}' not found")


def _default_part_csys(part_id: str) -> CoordinateSystem:
    """Return a default LCS at the global origin for a part."""
    return CoordinateSystem(
        id=f"{part_id}_origin",
        name=f"{part_id} origin",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )


def _find_csys_for_entity(tree: FeatureTree, entity: MateEntity) -> CoordinateSystem:
    """Locate the coordinate system referenced by a mate entity."""
    if entity.csys_id:
        try:
            return _csys_by_id(tree, entity.csys_id)
        except ValueError:
            return _default_part_csys(entity.instance_id)
    return _default_part_csys(entity.instance_id)


def _transform_to_matrix(translation=(0, 0, 0), rotation=(0, 0, 0)) -> np.ndarray:
    """Build a 4x4 homogeneous matrix from translation and Euler angles (degrees)."""
    tx, ty, tz = translation
    rx, ry, rz = (math.radians(a) for a in rotation)

    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    # Intrinsic Z-Y-X rotation (roll-pitch-yaw).
    R = np.array([
        [cy * cz, cz * sx * sy - cx * sz, sx * sz + cx * cz * sy],
        [cy * sz, cx * cz + sx * sy * sz, cx * sy * sz - cz * sx],
        [-sy, cy * sx, cx * cy],
    ])

    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = [tx, ty, tz]
    return M


def _matrix_to_pos_rot(M: np.ndarray) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Extract translation and Euler angles (degrees, ZYX) from a 4x4 matrix."""
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

    return (tx, ty, tz), tuple(math.degrees(a) for a in (rx, ry, rz))


def _explicit_transform(instance: Instance) -> np.ndarray:
    """Return the explicit transform for an instance, or identity."""
    if not instance.transform:
        return np.eye(4)
    t = instance.transform.get("translation", [0, 0, 0])
    r = instance.transform.get("rotation", [0, 0, 0])
    return _transform_to_matrix(t, r)


def _csys_matrix(csys: CoordinateSystem) -> np.ndarray:
    """Convert a CoordinateSystem into a 4x4 matrix."""
    ox, oy, oz = csys.origin
    M = np.eye(4)
    M[:3, 0] = csys.x_axis
    M[:3, 1] = csys.y_axis
    M[:3, 2] = csys.z_axis
    M[:3, 3] = [ox, oy, oz]
    return M


def compute_instance_transforms(
    tree: FeatureTree,
    assembly: Assembly,
    parameters: dict[str, float] | None = None,
) -> dict[str, np.ndarray]:
    """Compute a 4x4 transform matrix for every instance in the assembly.

    Start with explicit transforms, then iteratively relax mate constraints.
    """
    parameters = parameters or tree.parameter_dict()
    transforms = {inst.id: _explicit_transform(inst) for inst in assembly.instances}

    for _ in range(20):
        deltas: dict[str, list[np.ndarray]] = {inst.id: [] for inst in assembly.instances}
        for mate in assembly.mates:
            if len(mate.entities) < 2:
                continue
            e1, e2 = mate.entities[0], mate.entities[1]
            if e1.instance_id not in transforms or e2.instance_id not in transforms:
                continue
            c1 = _find_csys_for_entity(tree, e1)
            c2 = _find_csys_for_entity(tree, e2)
            M1 = transforms[e1.instance_id] @ _csys_matrix(c1)
            M2 = transforms[e2.instance_id] @ _csys_matrix(c2)
            mt = mate.type

            if mt == "fixed":
                continue
            if mt == "coincident":
                target = (M1[:3, 3] + M2[:3, 3]) / 2
                deltas[e1.instance_id].append(_move_origin(transforms[e1.instance_id], target - M1[:3, 3]))
                deltas[e2.instance_id].append(_move_origin(transforms[e2.instance_id], target - M2[:3, 3]))
            elif mt in ("concentric", "revolute"):
                target = (M1[:3, 3] + M2[:3, 3]) / 2
                deltas[e1.instance_id].append(_move_origin(transforms[e1.instance_id], target - M1[:3, 3]))
                deltas[e2.instance_id].append(_move_origin(transforms[e2.instance_id], target - M2[:3, 3]))
                z1 = M1[:3, 2]
                z2 = M2[:3, 2]
                new_z = (z1 + z2) / 2
                deltas[e1.instance_id].append(_set_z_axis(transforms[e1.instance_id], new_z))
                deltas[e2.instance_id].append(_set_z_axis(transforms[e2.instance_id], new_z))
            elif mt == "prismatic":
                # Align Z axes; keep X/Y origin coincident while leaving the Z slide
                # as a degree of freedom. We set a nominal zero offset.
                z1 = M1[:3, 2]
                z2 = M2[:3, 2]
                new_z = (z1 + z2) / 2
                deltas[e1.instance_id].append(_set_z_axis(transforms[e1.instance_id], new_z))
                deltas[e2.instance_id].append(_set_z_axis(transforms[e2.instance_id], new_z))
                # Coincide X/Y to define the prismatic rail origin.
                delta_xy = M1[:3, 3] - M2[:3, 3]
                delta_xy[2] = 0.0
                deltas[e2.instance_id].append(_move_origin(transforms[e2.instance_id], delta_xy / 2))
            elif mt == "distance":
                offset = _resolve_value(mate.parameters.get("distance", 0), parameters)
                z = (M1[:3, 2] + M2[:3, 2]) / 2
                z = z / (np.linalg.norm(z) + 1e-12)
                target = M1[:3, 3] + z * offset
                deltas[e2.instance_id].append(_move_origin(transforms[e2.instance_id], target - M2[:3, 3]))
            elif mt == "angle":
                continue
            elif mt == "parallel":
                z = (M1[:3, 2] + M2[:3, 2]) / 2
                deltas[e1.instance_id].append(_set_z_axis(transforms[e1.instance_id], z))
                deltas[e2.instance_id].append(_set_z_axis(transforms[e2.instance_id], z))
            elif mt == "perpendicular":
                z1 = M1[:3, 2]
                z2 = M2[:3, 2]
                new_z2 = np.cross(z1, np.cross(z2, z1))
                norm = np.linalg.norm(new_z2)
                if norm > 1e-9:
                    new_z2 = new_z2 / norm
                    deltas[e2.instance_id].append(_set_z_axis(transforms[e2.instance_id], new_z2))

        if not any(deltas[inst.id] for inst in assembly.instances):
            break
        for inst in assembly.instances:
            inst_deltas = deltas[inst.id]
            if inst_deltas:
                avg = np.mean(np.stack(inst_deltas), axis=0)
                transforms[inst.id] = avg

    return transforms


def solve_assembly(
    tree: FeatureTree,
    assembly: Assembly,
    parameters: dict[str, float] | None = None,
    max_iterations: int = 40,
    tolerance: float = 1e-2,
) -> dict[str, Any]:
    """Solve instance transforms and report convergence / constraint residual.

    Returns a dict with:
        transforms: dict[str, np.ndarray]
        overconstrained: bool
        residual_mm: float
        iterations: int
    """
    parameters = parameters or tree.parameter_dict()
    transforms = {inst.id: _explicit_transform(inst) for inst in assembly.instances}
    residual = float("inf")
    iterations = 0
    overconstrained = False

    for iteration in range(max_iterations):
        deltas: dict[str, list[np.ndarray]] = {inst.id: [] for inst in assembly.instances}
        for mate in assembly.mates:
            if len(mate.entities) < 2:
                continue
            e1, e2 = mate.entities[0], mate.entities[1]
            if e1.instance_id not in transforms or e2.instance_id not in transforms:
                continue
            c1 = _find_csys_for_entity(tree, e1)
            c2 = _find_csys_for_entity(tree, e2)
            M1 = transforms[e1.instance_id] @ _csys_matrix(c1)
            M2 = transforms[e2.instance_id] @ _csys_matrix(c2)
            mt = mate.type

            if mt == "fixed":
                continue
            if mt == "coincident":
                target = (M1[:3, 3] + M2[:3, 3]) / 2
                deltas[e1.instance_id].append(_move_origin(transforms[e1.instance_id], target - M1[:3, 3]))
                deltas[e2.instance_id].append(_move_origin(transforms[e2.instance_id], target - M2[:3, 3]))
            elif mt in ("concentric", "revolute"):
                target = (M1[:3, 3] + M2[:3, 3]) / 2
                deltas[e1.instance_id].append(_move_origin(transforms[e1.instance_id], target - M1[:3, 3]))
                deltas[e2.instance_id].append(_move_origin(transforms[e2.instance_id], target - M2[:3, 3]))
                z1 = M1[:3, 2]
                z2 = M2[:3, 2]
                new_z = (z1 + z2) / 2
                deltas[e1.instance_id].append(_set_z_axis(transforms[e1.instance_id], new_z))
                deltas[e2.instance_id].append(_set_z_axis(transforms[e2.instance_id], new_z))
            elif mt == "distance":
                offset = _resolve_value(mate.parameters.get("distance", 0), parameters)
                z = (M1[:3, 2] + M2[:3, 2]) / 2
                z = z / (np.linalg.norm(z) + 1e-12)
                target = M1[:3, 3] + z * offset
                deltas[e2.instance_id].append(_move_origin(transforms[e2.instance_id], target - M2[:3, 3]))
            elif mt == "angle":
                continue
            elif mt == "parallel":
                z = (M1[:3, 2] + M2[:3, 2]) / 2
                deltas[e1.instance_id].append(_set_z_axis(transforms[e1.instance_id], z))
                deltas[e2.instance_id].append(_set_z_axis(transforms[e2.instance_id], z))
            elif mt == "perpendicular":
                z1 = M1[:3, 2]
                z2 = M2[:3, 2]
                new_z2 = np.cross(z1, np.cross(z2, z1))
                norm = np.linalg.norm(new_z2)
                if norm > 1e-9:
                    new_z2 = new_z2 / norm
                    deltas[e2.instance_id].append(_set_z_axis(transforms[e2.instance_id], new_z2))
            elif mt == "prismatic":
                z1 = M1[:3, 2]
                z2 = M2[:3, 2]
                new_z = (z1 + z2) / 2
                deltas[e1.instance_id].append(_set_z_axis(transforms[e1.instance_id], new_z))
                deltas[e2.instance_id].append(_set_z_axis(transforms[e2.instance_id], new_z))
                delta_xy = M1[:3, 3] - M2[:3, 3]
                delta_xy[2] = 0.0
                deltas[e2.instance_id].append(_move_origin(transforms[e2.instance_id], delta_xy / 2))

        if not any(deltas[inst.id] for inst in assembly.instances):
            residual = 0.0
            iterations = iteration
            break

        # Compute residual from average delta magnitudes.
        delta_norms: list[float] = []
        for inst in assembly.instances:
            inst_deltas = deltas[inst.id]
            if inst_deltas:
                avg = np.mean(np.stack(inst_deltas), axis=0)
                delta_norms.append(float(np.linalg.norm(avg[:3, 3])))
                transforms[inst.id] = avg
        residual = max(delta_norms) if delta_norms else 0.0
        iterations = iteration + 1
        if residual < tolerance:
            break

    if residual >= tolerance:
        overconstrained = True

    return {
        "transforms": transforms,
        "overconstrained": overconstrained,
        "residual_mm": residual,
        "iterations": iterations,
    }


def _move_origin(M: np.ndarray, delta: np.ndarray) -> np.ndarray:
    """Return a copy of M with its origin shifted by delta."""
    new = M.copy()
    new[:3, 3] = M[:3, 3] + delta
    return new


def _set_z_axis(M: np.ndarray, new_z: np.ndarray) -> np.ndarray:
    """Return a copy of M with its Z axis aligned to new_z while keeping origin."""
    new_z = np.asarray(new_z, dtype=float)
    norm = np.linalg.norm(new_z)
    if norm < 1e-9:
        return M.copy()
    new_z = new_z / norm
    old_x = M[:3, 0]
    new_x = old_x - np.dot(old_x, new_z) * new_z
    nx = np.linalg.norm(new_x)
    if nx < 1e-9:
        tmp = np.array([1.0, 0.0, 0.0]) if abs(new_z[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        new_x = np.cross(new_z, tmp)
        nx = np.linalg.norm(new_x)
    new_x = new_x / nx
    new_y = np.cross(new_z, new_x)
    new = M.copy()
    new[:3, 0] = new_x
    new[:3, 1] = new_y
    new[:3, 2] = new_z
    return new


def transpile_assembly(tree: FeatureTree, assembly: Assembly | None = None) -> str:
    """Generate a build123d script for an assembly of multiple part instances.

    The generated script defines one `BuildPart` variable per unique part, then places
    copies of those parts in a `Compound` named `result`.
    """
    if assembly is None:
        if tree.assemblies:
            assembly = tree.assemblies[0]
        else:
            # No assembly defined: fall back to the first part.
            if not tree.parts:
                raise ValueError("Feature tree has no parts to transpile.")
            return "# Single-part fallback\n" + _single_part_fallback(tree)

    if not tree.parts:
        raise ValueError("Feature tree has no parts to transpile.")

    parameters = tree.parameter_dict()

    lines: list[str] = []
    lines.append("from build123d import *")
    lines.append("")

    for param in tree.parameters:
        lines.append(f"{param.name} = {param.value}")
    lines.append("")

    # Emit each unique part as a BuildPart variable.
    part_var_names: dict[str, str] = {}
    for idx, part in enumerate(tree.parts):
        var_name = f"part_{idx}"
        part_var_names[part.id] = var_name
        lines.extend(_transpile_part(part, parameters, var_name=var_name))
        lines.append("")

    transforms = compute_instance_transforms(tree, assembly, parameters)

    placed: list[str] = []
    for inst in assembly.instances:
        part = tree.find_part(inst.part_id)
        if part is None:
            continue
        var_name = part_var_names[inst.part_id]
        M = transforms.get(inst.id, np.eye(4))
        (tx, ty, tz), (rx, ry, rz) = _matrix_to_pos_rot(M)
        placed.append(
            f"{var_name}.part.moved(Location(({tx}, {ty}, {tz})) * Rotation({rx}, {ry}, {rz}))"
        )

    if not placed:
        # Fallback to first part if no instances are valid.
        lines.append(f"result = {part_var_names[tree.parts[0].id]}.part")
        return "\n".join(lines)

    lines.append("result = Compound(children=[")
    for p in placed:
        lines.append(f"    {p},")
    lines.append("])")

    return "\n".join(lines)


def _single_part_fallback(tree: FeatureTree) -> str:
    from ai_cad.transpiler import transpile
    return transpile(tree)


def _joint_subtree(joints: list, root_child: str) -> set[str]:
    """Return all instance ids reachable from root_child via joints."""
    parent_map: dict[str, str] = {}
    for j in joints:
        parent_map[j.child_link] = j.parent_link

    # Build children adjacency (parent -> children) from the joints.
    children: dict[str, set[str]] = {}
    for j in joints:
        children.setdefault(j.parent_link, set()).add(j.child_link)

    visited: set[str] = set()
    stack = [root_child]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        stack.extend(children.get(node, set()) - visited)
    return visited


def _joint_transform_matrix(joint, value: float) -> np.ndarray:
    """Return a 4x4 transform representing the joint value relative to zero."""
    ax = np.array(joint.axis or (0.0, 0.0, 1.0), dtype=float)
    norm = np.linalg.norm(ax)
    if norm < 1e-9:
        ax = np.array([0.0, 0.0, 1.0])
    else:
        ax = ax / norm

    delta = np.eye(4)
    if joint.type == "revolute":
        theta = math.radians(value)
        c, s = math.cos(theta), math.sin(theta)
        # Rodrigues' rotation matrix for axis ax.
        x, y, z = ax
        R = np.array(
            [
                [c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)],
            ]
        )
        delta[:3, :3] = R
    elif joint.type == "prismatic":
        delta[:3, 3] = ax * value
    return delta


def sample_assembly_poses(
    tree: FeatureTree,
    assembly: Assembly | None = None,
    *,
    samples_per_joint: int = 8,
) -> dict[str, Any]:
    """Sample range-of-motion poses for an articulated assembly.

    Returns:
        {
            "joint_count": int,
            "overconstrained": bool,
            "frames": [
                {
                    "joint_states": {joint_id: value},
                    "transforms": {instance_id: {position, rotation_deg}}
                }
            ]
        }
    """
    if assembly is None:
        assembly = tree.assemblies[0] if tree.assemblies else None
    if assembly is None:
        return {"joint_count": 0, "overconstrained": False, "frames": []}

    solved = solve_assembly(tree, assembly)
    nominal = solved["transforms"]
    joints = assembly.joints or []

    def _serialize(transforms: dict[str, np.ndarray]) -> dict[str, dict[str, tuple]]:
        out: dict[str, dict[str, tuple]] = {}
        for inst_id, M in transforms.items():
            pos, rot = _matrix_to_pos_rot(M)
            out[inst_id] = {
                "position": tuple(float(v) for v in pos),
                "rotation_deg": tuple(float(v) for v in rot),
            }
        return out

    if not joints or samples_per_joint < 2:
        return {
            "joint_count": len(joints),
            "overconstrained": solved["overconstrained"],
            "frames": [
                {"joint_states": {}, "transforms": _serialize(nominal)}
            ],
        }

    frames: list[dict[str, Any]] = []
    for joint in joints:
        limits = joint.limits
        if limits is None:
            lo, hi = -180.0, 180.0
        else:
            lo, hi = float(limits[0]), float(limits[1])
        for i in range(samples_per_joint):
            t = i / (samples_per_joint - 1)
            value = lo + (hi - lo) * t
            joint_states = {j.id: 0.0 for j in joints}
            joint_states[joint.id] = round(value, 3)

            transforms = {k: v.copy() for k, v in nominal.items()}
            joint_origin = np.array(joint.origin, dtype=float)
            T_origin = np.eye(4)
            T_origin[:3, 3] = joint_origin
            T_origin_inv = np.linalg.inv(T_origin)
            delta = _joint_transform_matrix(joint, value)
            world_delta = T_origin @ delta @ T_origin_inv

            for child_id in _joint_subtree(joints, joint.child_link):
                if child_id in transforms:
                    transforms[child_id] = world_delta @ transforms[child_id]

            frames.append(
                {
                    "joint_states": joint_states,
                    "transforms": _serialize(transforms),
                }
            )

    return {
        "joint_count": len(joints),
        "overconstrained": solved["overconstrained"],
        "frames": frames,
    }
