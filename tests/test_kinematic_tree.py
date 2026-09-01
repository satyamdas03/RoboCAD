"""Tests for ai_cad.kinematic_tree forward kinematics and workspace sampling."""
from __future__ import annotations

import numpy as np
import pytest

from ai_cad.feature_tree import Assembly, FeatureTree, Instance, KinematicJoint, Part
from ai_cad.kinematic_tree import forward_kinematics


def _make_dummy_part(part_id: str = "link") -> Part:
    return Part(
        id=part_id,
        sketches=[],
        features=[],
    )


def test_forward_kinematics_breaks_cycle():
    """A cyclic joint graph must not infinite-loop or stack-overflow."""
    tree = FeatureTree(
        design_id="cycle_tree",
        prompt="cyclic test",
        created_at="2026-08-29T00:00:00Z",
        parts=[_make_dummy_part("base"), _make_dummy_part("child")],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="base_inst", part_id="base"),
                    Instance(id="child_inst", part_id="child"),
                ],
                joints=[
                    # Cycle: child_inst -> base_inst -> child_inst
                    KinematicJoint(
                        id="j1",
                        type="fixed",
                        parent_link="base_inst",
                        child_link="child_inst",
                        origin=(0, 0, 0),
                    ),
                    KinematicJoint(
                        id="j2",
                        type="fixed",
                        parent_link="child_inst",
                        child_link="base_inst",
                        origin=(0, 0, 0),
                    ),
                ],
            )
        ],
    )
    # Should return without hanging; the cyclic part resolves to identity.
    poses = forward_kinematics(tree)
    assert "base_inst" in poses
    assert "child_inst" in poses
    # Both transforms should be valid 4x4 matrices.
    assert poses["base_inst"].transform.shape == (4, 4)
    assert poses["child_inst"].transform.shape == (4, 4)
    assert np.allclose(poses["base_inst"].transform, np.eye(4))
