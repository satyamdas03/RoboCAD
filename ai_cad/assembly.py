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
        return _csys_by_id(tree, entity.csys_id)
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
            elif mt == "concentric":
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

        if not any(deltas[inst.id] for inst in assembly.instances):
            break
        for inst in assembly.instances:
            inst_deltas = deltas[inst.id]
            if inst_deltas:
                avg = np.mean(np.stack(inst_deltas), axis=0)
                transforms[inst.id] = avg

    return transforms


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
            f"{var_name}.part.move(Location(({tx}, {ty}, {tz})) * Rotation({rx}, {ry}, {rz}))"
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
