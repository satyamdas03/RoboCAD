"""Kinematic tree utilities for articulated robot assemblies.

Provides forward kinematics, joint-chain transform propagation, and reachable
workspace sampling for humanoid / legged robots built by RoboCAD.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ai_cad.feature_tree import Assembly, FeatureTree, KinematicJoint


@dataclass
class JointState:
    """Named joint value in native units (deg for revolute, mm for prismatic)."""

    id: str
    type: str
    value: float


@dataclass
class LinkPose:
    """6-DOF pose of a link relative to the world frame."""

    name: str
    position: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]
    transform: np.ndarray


def _rotation_matrix_to_euler(R: np.ndarray) -> tuple[float, float, float]:
    """Convert 3x3 rotation matrix to ZYX Euler angles in degrees."""
    sy = max(-1.0, min(1.0, float(-R[2, 0])))
    if abs(sy) < 0.99999:
        rx = math.atan2(R[2, 1], R[2, 2])
        ry = math.asin(sy)
        rz = math.atan2(R[1, 0], R[0, 0])
    else:
        rx = math.atan2(-R[1, 2], R[1, 1])
        ry = math.asin(sy)
        rz = 0.0
    return tuple(math.degrees(a) for a in (rx, ry, rz))


def _joint_delta_matrix(joint: KinematicJoint, value: float) -> np.ndarray:
    """Return 4x4 transform of joint value relative to its origin."""
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


def _children_map(joints: list[KinematicJoint]) -> dict[str, list[tuple[str, KinematicJoint]]]:
    """Build parent -> (child, joint) adjacency from joints."""
    children: dict[str, list[tuple[str, KinematicJoint]]] = {}
    for j in joints:
        children.setdefault(j.parent_link, []).append((j.child_link, j))
    return children


def _subtree_links(joints: list[KinematicJoint], root_child: str) -> set[str]:
    """Return all link names reachable from root_child via joints."""
    children = _children_map(joints)
    visited: set[str] = set()
    stack = [root_child]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        stack.extend(child for child, _ in children.get(node, []))
    return visited


def forward_kinematics(
    tree: FeatureTree,
    assembly: Assembly | None = None,
    joint_states: dict[str, float] | None = None,
    base_transform: np.ndarray | None = None,
) -> dict[str, LinkPose]:
    """Compute world poses for every link in an articulated assembly.

    Args:
        tree: FeatureTree containing the assembly and parts.
        assembly: Assembly to solve. Defaults to tree.assemblies[0].
        joint_states: optional map of joint_id -> value. Defaults to zero.
        base_transform: optional 4x4 base transform for the root link(s).

    Returns:
        dict mapping link/instance id to LinkPose.
    """
    if assembly is None:
        assembly = tree.assemblies[0] if tree.assemblies else None
    if assembly is None:
        return {}

    # Start with nominal instance transforms from the assembly solver.
    from ai_cad.assembly import compute_instance_transforms

    parameters = tree.parameter_dict()
    nominal_transforms = compute_instance_transforms(tree, assembly, parameters)

    joints = assembly.joints or []
    joint_states = joint_states or {}

    # Build parent map and determine roots.
    parent_map: dict[str, str] = {}
    for j in joints:
        parent_map.setdefault(j.child_link, j.parent_link)

    out: dict[str, LinkPose] = {}
    children = _children_map(joints)

    base_transform = base_transform if base_transform is not None else np.eye(4)
    recursion_seen: set[str] = set()

    def _pose_of(link_id: str) -> np.ndarray:
        if link_id in out:
            return out[link_id].transform
        if link_id in recursion_seen:
            # Cyclic joint graph detected; break recursion with identity to avoid
            # an infinite loop / stack overflow.
            return np.eye(4)
        recursion_seen.add(link_id)
        # Root: use nominal transform composed with base.
        if link_id not in parent_map:
            M = nominal_transforms.get(link_id, np.eye(4))
            result = base_transform @ M
            recursion_seen.discard(link_id)
            return result
        parent_id = parent_map[link_id]
        joint = next(j for j in joints if j.child_link == link_id)
        parent_M = _pose_of(parent_id)

        # The template stores joint origins as the absolute (zero-pose) position
        # of the joint in the assembly frame. Compute the origin relative to the
        # parent's nominal frame and the child offset from that origin so that
        # at zero pose the child lands exactly on its nominal transform.
        origin = np.array(joint.origin, dtype=float)
        T_joint_origin = np.eye(4)
        T_joint_origin[:3, 3] = origin

        parent_nominal = nominal_transforms.get(parent_id, np.eye(4))
        child_nominal = nominal_transforms.get(link_id, np.eye(4))

        T_joint_origin_in_parent = np.linalg.inv(parent_nominal) @ T_joint_origin
        T_child_offset = np.linalg.inv(T_joint_origin) @ child_nominal

        value = joint_states.get(joint.id, 0.0)
        delta = _joint_delta_matrix(joint, value)

        recursion_seen.discard(link_id)
        return parent_M @ T_joint_origin_in_parent @ delta @ T_child_offset

    all_links = set(nominal_transforms.keys()) | {j.parent_link for j in joints} | {j.child_link for j in joints}
    for link_id in all_links:
        M = _pose_of(link_id)
        pos = tuple(float(v) for v in M[:3, 3])
        rot = _rotation_matrix_to_euler(M[:3, :3])
        out[link_id] = LinkPose(name=link_id, position=pos, rotation_deg=rot, transform=M)

    return out


def sample_reachable_workspace(
    tree: FeatureTree,
    end_effector_id: str,
    assembly: Assembly | None = None,
    samples_per_joint: int = 5,
) -> dict[str, Any]:
    """Sample reachable positions of an end-effector by sweeping joint limits.

    Returns a dict with:
        end_effector_id: str
        point_count: int
        points: list[(x, y, z)]
        envelope_mm: (dx, dy, dz)
        volume_estimate_mm3: float
    """
    if assembly is None:
        assembly = tree.assemblies[0] if tree.assemblies else None
    if assembly is None:
        return {"end_effector_id": end_effector_id, "point_count": 0, "points": []}

    joints = [j for j in (assembly.joints or []) if j.type in ("revolute", "prismatic")]
    if not joints:
        return {"end_effector_id": end_effector_id, "point_count": 0, "points": []}

    # Build minimal joint state combinations.
    joint_limits: list[tuple[str, list[float]]] = []
    for j in joints:
        lo, hi = j.limits if j.limits else (-180.0, 180.0)
        if j.type == "prismatic":
            lo, hi = lo, hi  # already in mm
        values = [lo + (hi - lo) * i / (samples_per_joint - 1) for i in range(samples_per_joint)]
        joint_limits.append((j.id, values))

    points: list[tuple[float, float, float]] = []
    # Cartesian product can be huge (e.g. 3^14 ≈ 4.8M tuples). Cap at 4096
    # samples without materializing the full product.
    import itertools

    value_lists = [v for _, v in joint_limits]
    counts = [len(v) for v in value_lists]
    total = math.prod(counts) if counts else 0
    rng = np.random.default_rng(0)

    if total <= 4096:
        combinations = list(itertools.product(*value_lists))
    else:
        combinations = []
        for _ in range(4096):
            combo = tuple(rng.choice(vals) for vals in value_lists)
            combinations.append(combo)

    for combo in combinations:
        states = {jid: combo[i] for i, (jid, _) in enumerate(joint_limits)}
        poses = forward_kinematics(tree, assembly, joint_states=states)
        if end_effector_id in poses:
            points.append(poses[end_effector_id].position)

    if not points:
        return {"end_effector_id": end_effector_id, "point_count": 0, "points": []}

    arr = np.array(points)
    min_bounds = arr.min(axis=0)
    max_bounds = arr.max(axis=0)
    envelope = tuple(float(max_bounds[i] - min_bounds[i]) for i in range(3))
    volume = float(np.prod(envelope))
    return {
        "end_effector_id": end_effector_id,
        "point_count": len(points),
        "points": [tuple(float(v) for v in p) for p in points],
        "envelope_mm": envelope,
        "volume_estimate_mm3": volume,
    }


def get_joint_chain(
    tree: FeatureTree,
    end_effector_id: str,
    assembly: Assembly | None = None,
) -> list[KinematicJoint]:
    """Return the joint chain from a root to the end-effector instance id."""
    if assembly is None:
        assembly = tree.assemblies[0] if tree.assemblies else None
    if assembly is None:
        return []

    joints = assembly.joints or []
    parent_map: dict[str, KinematicJoint | None] = {j.child_link: j for j in joints}
    chain: list[KinematicJoint] = []
    current = end_effector_id
    seen: set[str] = set()
    while current in parent_map and current not in seen:
        seen.add(current)
        joint = parent_map[current]
        if joint is None:
            break
        chain.append(joint)
        current = joint.parent_link
    chain.reverse()
    return chain
