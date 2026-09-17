"""Self-collision scoring for morphology candidates.

Samples representative task poses and runs pairwise assembly collision checks.
A candidate with frequent interferences receives a high collision penalty.
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any

from ai_cad.assembly_collision import check_assembly_collision
from ai_cad.feature_tree import FeatureTree


def _default_poses(tree: FeatureTree) -> list[dict[str, float]]:
    """Return representative joint-state poses for common robot templates."""
    prompt = tree.prompt.lower()
    if "quadruped" in prompt:
        return [
            {},  # neutral
            {"hip_pitch_fl": -20.0, "knee_fl": 40.0, "hip_pitch_fr": -20.0, "knee_fr": 40.0},
        ]
    if "manipulator" in prompt or "base" in prompt:
        return [
            {},  # neutral
            {"shoulder_lift": 45.0, "elbow": -45.0},  # reach forward
            {"shoulder_lift": -45.0, "elbow": -90.0},  # reach high
        ]
    # Default humanoid.
    return [
        {},  # neutral standing
        {
            "hip_pitch_l": -20.0,
            "knee_l": 40.0,
            "hip_pitch_r": -20.0,
            "knee_r": 40.0,
            "shoulder_l": 30.0,
            "elbow_l": -60.0,
            "shoulder_r": -30.0,
            "elbow_r": -60.0,
        },
        {
            "shoulder_l": 90.0,
            "elbow_l": -90.0,
            "shoulder_r": -90.0,
            "elbow_r": -90.0,
        },
    ]


def score_candidate_collision(
    tree: FeatureTree,
    output_dir: Path | str | None = None,
    poses: list[dict[str, float]] | None = None,
    samples: int = 200,
) -> dict[str, Any]:
    """Score a candidate by self-collision across representative poses.

    Args:
        tree: morphology candidate FeatureTree.
        output_dir: directory for temporary mesh generation. Defaults to a temp dir.
        poses: list of joint-state dicts to evaluate. If None, template defaults.
        samples: surface samples for each pairwise collision check.

    Returns:
        dict with collision_penalty (0 = clean, 1 = colliding in every pose),
        interference_count, worst_clearance_mm, and poses_checked.
    """
    if not tree.assemblies:
        return {
            "collision_penalty": 0.0,
            "interference_count": 0,
            "worst_clearance_mm": 0.0,
            "poses_checked": 0,
            "notes": "no assembly",
        }

    poses = poses if poses is not None else _default_poses(tree)
    if not poses:
        poses = [{}]

    use_tmp = output_dir is None
    if use_tmp:
        tmp = tempfile.TemporaryDirectory()
        output_dir = Path(tmp.name)
    else:
        output_dir = Path(output_dir)
        tmp = None

    try:
        total_interference = 0
        total_transition = 0
        worst_clearance_mm = float("inf")
        checked = 0

        for pose in poses:
            reports = check_assembly_collision(
                tree,
                output_dir,
                samples=samples,
                joint_states=pose,
            )
            checked += 1
            for report in reports:
                if report.classification == "interference":
                    total_interference += 1
                elif report.classification == "transition":
                    total_transition += 1
                if report.min_clearance_mm is not None and report.min_clearance_mm < worst_clearance_mm:
                    worst_clearance_mm = float(report.min_clearance_mm)

        # Each pose has N choose 2 pairs. Penalty rises with fraction of
        # pose-pairs that show interference or transition.
        n_pairs = max(1, len(reports))
        bad_fraction = (total_interference + 0.5 * total_transition) / max(1, checked * n_pairs)
        collision_penalty = min(1.0, bad_fraction)
        if math.isinf(worst_clearance_mm):
            worst_clearance_mm = 0.0

        return {
            "collision_penalty": round(collision_penalty, 4),
            "interference_count": total_interference,
            "transition_count": total_transition,
            "worst_clearance_mm": round(worst_clearance_mm, 4),
            "poses_checked": checked,
            "notes": f"{total_interference} interferences, {total_transition} transitions across {checked} poses",
        }
    finally:
        if tmp is not None:
            tmp.cleanup()
