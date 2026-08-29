"""Tests for the Phase 19 assembly solver: revolute/prismatic mates and poses."""
from __future__ import annotations

import math

import pytest

from ai_cad.assembly import sample_assembly_poses, solve_assembly
from ai_cad.feature_tree import (
    Assembly,
    FeatureTree,
    Instance,
    KinematicJoint,
    Mate,
    MateEntity,
)


def _make_tree_with_joint(joint_type: str) -> FeatureTree:
    tree = FeatureTree(
        design_id="joint_test",
        prompt=f"{joint_type} joint test",
        parts=[],
        assemblies=[
            Assembly(
                id="asm",
                instances=[
                    Instance(id="base", part_id="base_part"),
                    Instance(id="arm", part_id="arm_part", transform={"translation": (100, 0, 0)}),
                ],
                mates=[
                    Mate(
                        id="m_base_arm",
                        type=joint_type,
                        entities=[
                            MateEntity(instance_id="base"),
                            MateEntity(instance_id="arm"),
                        ],
                    )
                ],
                joints=[
                    KinematicJoint(
                        id="j_base_arm",
                        type=joint_type,
                        parent_link="base",
                        child_link="arm",
                        origin=(0, 0, 0),
                        axis=(0, 0, 1) if joint_type == "revolute" else (1, 0, 0),
                        limits=(-90, 90) if joint_type == "revolute" else (-20, 20),
                    )
                ],
            )
        ],
    )
    return tree


def test_solve_revolute_mate_converges():
    tree = _make_tree_with_joint("revolute")
    result = solve_assembly(tree, tree.assemblies[0])
    assert "transforms" in result
    assert "base" in result["transforms"]
    assert "arm" in result["transforms"]


def test_solve_prismatic_mate_converges():
    tree = _make_tree_with_joint("prismatic")
    result = solve_assembly(tree, tree.assemblies[0])
    assert "transforms" in result
    assert not result["overconstrained"]


def test_sample_poses_has_frames():
    tree = _make_tree_with_joint("revolute")
    data = sample_assembly_poses(tree, samples_per_joint=5)
    assert data["joint_count"] == 1
    assert len(data["frames"]) == 5
    first = data["frames"][0]
    assert "joint_states" in first
    assert "transforms" in first
    assert "arm" in first["transforms"]


def test_revolute_pose_rotates_child():
    tree = _make_tree_with_joint("revolute")
    data = sample_assembly_poses(tree, samples_per_joint=3)
    # frames: -90, 0, 90 deg for the one revolute joint.
    arm_positions = [f["transforms"]["arm"]["position"] for f in data["frames"]]
    # At ±90 the arm end should move in X/Y.
    assert len(set(arm_positions)) == 3


def test_prismatic_pose_translates_child():
    tree = _make_tree_with_joint("prismatic")
    data = sample_assembly_poses(tree, samples_per_joint=3)
    arm_positions = [f["transforms"]["arm"]["position"] for f in data["frames"]]
    x_values = [p[0] for p in arm_positions]
    assert max(x_values) > min(x_values)
