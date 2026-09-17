"""Sagittal-plane workspace proxy and manipulability for morphology scoring.

Milestone C replaces the brittle 3-D workspace volume metric with a robust
reachable-workspace proxy that works for sagittal-plane robots (humanoids,
quadrupeds, manipulators) and adds a Yoshikawa-style manipulability index.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from ai_cad.feature_tree import FeatureTree, KinematicJoint
from ai_cad.kinematic_tree import forward_kinematics, get_joint_chain, sample_reachable_workspace


def _convex_hull_area_2d(points_xz: np.ndarray) -> float:
    """Return convex-hull area of 2-D points using scipy if available."""
    if len(points_xz) < 3:
        return 0.0
    try:
        from scipy.spatial import ConvexHull

        hull = ConvexHull(points_xz)
        return float(hull.volume)  # volume in 2-D is area
    except Exception:
        # Fallback: bounding-box area.
        mins = points_xz.min(axis=0)
        maxs = points_xz.max(axis=0)
        return float(np.prod(maxs - mins))


def _joint_axis(joint: KinematicJoint) -> np.ndarray:
    """Return normalized joint axis, defaulting to Z."""
    ax = np.array(joint.axis or (0.0, 0.0, 1.0), dtype=float)
    norm = float(np.linalg.norm(ax))
    return ax if norm < 1e-9 else ax / norm


def _joint_value_to_radians(joint: KinematicJoint, value: float) -> float:
    """Convert native joint value to radians for revolute joints."""
    if joint.type == "revolute":
        return math.radians(value)
    return 0.0


def _joint_delta_matrix(joint: KinematicJoint, value: float) -> np.ndarray:
    """Local transform of a joint value (same convention as kinematic_tree)."""
    ax = _joint_axis(joint)
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


def _transform_chain(chain: list[KinematicJoint], joint_values: dict[str, float]) -> np.ndarray:
    """Return end-effector transform from a chain of joint values."""
    M = np.eye(4)
    for joint in chain:
        value = joint_values.get(joint.id, 0.0)
        M = M @ _joint_delta_matrix(joint, value)
    return M


def compute_jacobian(
    chain: list[KinematicJoint],
    joint_values: dict[str, float],
    end_effector_position: tuple[float, float, float] | None = None,
) -> np.ndarray:
    """Build a 6×n geometric Jacobian for the joint chain.

    Columns are [Jv; Jw] where Jv is linear velocity contribution and Jw is
    angular velocity contribution. Revolute columns use axis × (ee - origin),
    prismatic columns use the axis directly.
    """
    n = len(chain)
    jacobian = np.zeros((6, n), dtype=float)

    # Compute world origin positions of each joint frame and the end-effector frame.
    # We must respect parent_link/child_link topology rather than assuming a simple
    # serial chain from the first joint.
    from ai_cad.kinematic_tree import _children_map

    children_map = _children_map(chain)
    link_transforms: dict[str, np.ndarray] = {"world": np.eye(4)}
    # Seed root links by walking chain; any link whose parent is not a child of
    # another chain joint starts at identity (world).
    all_children = {j.child_link for j in chain}
    all_parents = {j.parent_link for j in chain}
    roots = all_parents - all_children

    def _compute_link(link_id: str) -> np.ndarray:
        if link_id in link_transforms:
            return link_transforms[link_id]
        # Find the joint whose child is link_id.
        for j in chain:
            if j.child_link == link_id:
                parent_M = _compute_link(j.parent_link)
                value = joint_values.get(j.id, 0.0)
                link_transforms[link_id] = parent_M @ _joint_delta_matrix(j, value)
                return link_transforms[link_id]
        link_transforms[link_id] = np.eye(4)
        return link_transforms[link_id]

    for root in roots:
        link_transforms[root] = np.eye(4)

    for link_id in all_children | all_parents:
        _compute_link(link_id)

    # End-effector is the child link of the last joint in the chain.
    ee_link = chain[-1].child_link if chain else None
    if end_effector_position is None and ee_link is not None:
        ee = np.array(link_transforms.get(ee_link, np.eye(4))[:3, 3], dtype=float)
    elif end_effector_position is not None:
        ee = np.array(end_effector_position, dtype=float)
    else:
        ee = np.zeros(3)

    for i, joint in enumerate(chain):
        if joint.type not in ("revolute", "prismatic"):
            continue
        axis_local = _joint_axis(joint)
        joint_M = link_transforms.get(joint.parent_link, np.eye(4)) @ _joint_delta_matrix(joint, 0.0)
        axis_world = joint_M[:3, :3] @ axis_local
        origin = np.array(joint_M[:3, 3], dtype=float)
        if joint.type == "revolute":
            jacobian[:3, i] = np.cross(axis_world, ee - origin)
            jacobian[3:, i] = axis_world
        elif joint.type == "prismatic":
            jacobian[:3, i] = axis_world
    return jacobian


def manipulability_index(jacobian: np.ndarray) -> float:
    """Yoshikawa-style manipulability measure.

    Uses the product of non-zero singular values, which is more stable than
    sqrt(det(J @ J.T)) when the Jacobian is rank-deficient (e.g., all revolute
    axes intersecting at a point in a sagittal-chain robot).
    """
    if jacobian.shape[1] == 0:
        return 0.0
    # Compute singular values and use product of those above a tolerance.
    singular = np.linalg.svd(jacobian, compute_uv=False)
    non_zero = singular[singular > 1e-9]
    if non_zero.size == 0:
        return 0.0
    return float(np.prod(non_zero))


def _normalize(value: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 1.0 if value >= hi else 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def manipulability_score(
    tree: FeatureTree,
    end_effector_id: str,
    samples: int = 8,
    seed: int = 0,
) -> float:
    """Average manipulability index across sampled poses, normalized to [0, 1]."""
    chain = get_joint_chain(tree, end_effector_id)
    if not chain:
        return 0.0

    rng = np.random.default_rng(seed)
    indices: list[float] = []

    # Always include a neutral sample.
    neutral: dict[str, float] = {joint.id: 0.0 for joint in chain}
    j_neutral = compute_jacobian(chain, neutral)
    indices.append(manipulability_index(j_neutral))

    # Sample within joint limits.
    for _ in range(samples - 1):
        values: dict[str, float] = {}
        for joint in chain:
            lo, hi = joint.limits if joint.limits else (-180.0, 180.0)
            if joint.type == "prismatic":
                values[joint.id] = float(rng.uniform(lo, hi))
            else:
                # Use a bias toward mid-range for realistic poses.
                mid = (lo + hi) / 2.0
                half = (hi - lo) / 2.0
                values[joint.id] = float(rng.normal(mid, half / 3.0))
                values[joint.id] = max(lo, min(hi, values[joint.id]))
        jacobian = compute_jacobian(chain, values)
        indices.append(manipulability_index(jacobian))

    if not indices:
        return 0.0
    avg_index = float(np.mean(indices))
    # Normalization target: 5000 mm^3-ish scale. Use log-ish compression for robustness.
    # A value of 5000 maps to ~0.7, 20000 maps to ~0.95.
    score = 2.0 / math.pi * math.atan(avg_index / 3000.0)
    return float(_normalize(score, 0.0, 1.0))


def workspace_proxy(
    tree: FeatureTree,
    end_effector_id: str,
    samples_per_joint: int = 4,
) -> dict[str, Any]:
    """Return a robust reachable-workspace proxy for morphology scoring.

    Metrics:
      - reach_mm: maximum forward (|X|) reach.
      - sagittal_area_mm2: convex-hull area in the X-Z plane.
      - lateral_span_mm: total Y range.
      - workspace_score: normalized composite of reach, sagittal area, lateral span.
      - manipulability_index: Yoshikawa measure at the neutral pose.
      - manipulability_score: sampled average, normalized.
    """
    workspace = sample_reachable_workspace(tree, end_effector_id, samples_per_joint=samples_per_joint)
    points = workspace.get("points", [])
    if not points:
        return {
            "end_effector_id": end_effector_id,
            "reach_mm": 0.0,
            "sagittal_area_mm2": 0.0,
            "lateral_span_mm": 0.0,
            "workspace_score": 0.0,
            "manipulability_index": 0.0,
            "manipulability_score": 0.0,
        }

    arr = np.array(points, dtype=float)
    reach_mm = float(np.max(np.abs(arr[:, 0])))
    lateral_span_mm = float(arr[:, 1].max() - arr[:, 1].min())
    sagittal_area_mm2 = _convex_hull_area_2d(arr[:, [0, 2]])

    workspace_score = float(
        _normalize(reach_mm, 0.0, 1500.0) * 0.5
        + _normalize(sagittal_area_mm2, 0.0, 1_000_000.0) * 0.3
        + _normalize(lateral_span_mm, 0.0, 800.0) * 0.2
    )

    chain = get_joint_chain(tree, end_effector_id)
    m_index = 0.0
    if chain:
        neutral: dict[str, float] = {joint.id: 0.0 for joint in chain}
        jacobian = compute_jacobian(chain, neutral)
        m_index = manipulability_index(jacobian)
    m_score = manipulability_score(tree, end_effector_id, samples=8)

    return {
        "end_effector_id": end_effector_id,
        "reach_mm": round(reach_mm, 4),
        "sagittal_area_mm2": round(sagittal_area_mm2, 4),
        "lateral_span_mm": round(lateral_span_mm, 4),
        "workspace_score": round(workspace_score, 4),
        "manipulability_index": round(m_index, 4),
        "manipulability_score": round(m_score, 4),
    }
