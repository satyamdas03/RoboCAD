"""Tests for the Phase 19 deterministic mate-inference engine."""
from __future__ import annotations

import pytest

from ai_cad.feature_tree import Assembly, FeatureTree, Instance, Part
from ai_cad.mate_inference import infer_mates
from ai_cad.part_families import instantiate_family


def _make_tree(
    design_id: str,
    prompt: str,
    parts: list[Part],
    instances: list[Instance],
) -> FeatureTree:
    return FeatureTree(
        design_id=design_id,
        prompt=prompt,
        parts=parts,
        assemblies=[Assembly(id="asm_1", instances=instances)],
    )


def test_two_link_chain_revolute():
    """Two-link chain yields one revolute mate and one joint."""
    tree = _make_tree(
        design_id="chain",
        prompt="two link chain",
        parts=[
            instantiate_family("link", "link_a"),
            instantiate_family("link", "link_b"),
        ],
        instances=[
            Instance(id="i_link_a", part_id="link_a"),
            Instance(id="i_link_b", part_id="link_b"),
        ],
    )
    mates, joints = infer_mates(tree, tree.assemblies[0])

    assert len(mates) == 1
    mate = mates[0]
    assert mate.type == "revolute"
    assert {e.instance_id for e in mate.entities} == {"i_link_a", "i_link_b"}
    assert all(e.csys_id == "link_pin_a" for e in mate.entities)

    assert len(joints) == 1
    joint = joints[0]
    assert joint.type == "revolute"
    assert joint.parent_link in ("i_link_a", "i_link_b")
    assert joint.child_link in ("i_link_a", "i_link_b")
    assert joint.parent_link != joint.child_link
    assert joint.limits == pytest.approx((-180.0, 180.0))


def test_gripper_jaws_prismatic():
    """Gripper two jaws yield a prismatic mate between them."""
    tree = _make_tree(
        design_id="gripper",
        prompt="parallel jaw gripper",
        parts=[instantiate_family("end_effector", "gripper_jaw")],
        instances=[
            Instance(id="i_jaw_left", part_id="gripper_jaw"),
            Instance(id="i_jaw_right", part_id="gripper_jaw"),
        ],
    )
    mates, joints = infer_mates(tree, tree.assemblies[0])

    assert len(mates) == 1
    assert mates[0].type == "prismatic"
    assert {e.instance_id for e in mates[0].entities} == {"i_jaw_left", "i_jaw_right"}

    assert len(joints) == 1
    joint = joints[0]
    assert joint.type == "prismatic"
    assert joint.limits == pytest.approx((-50.0, 50.0))


def test_hub_four_arms_yields_revolute_mates():
    """Hub + 4 arms yields 4 revolute hub-arm mates; arm-arm siblings do not mate."""
    tree = _make_tree(
        design_id="hub_arm",
        prompt="hub with four arms",
        parts=[
            instantiate_family("hub", "center_hub"),
            instantiate_family("link", "motor_arm"),
        ],
        instances=[
            Instance(id="i_hub", part_id="center_hub"),
            *[Instance(id=f"i_arm_{i}", part_id="motor_arm") for i in range(4)],
        ],
    )
    mates, joints = infer_mates(tree, tree.assemblies[0])

    assert len(mates) == 4
    assert all(m.type == "revolute" for m in mates)
    # Every arm should be mated to the hub.
    for i in range(4):
        assert any(
            f"i_arm_{i}" in {e.instance_id for e in m.entities}
            and "i_hub" in {e.instance_id for e in m.entities}
            for m in mates
        )

    assert len(joints) == 4
    assert all(j.type == "revolute" for j in joints)
    hub_joints = [j for j in joints if j.parent_link == "i_hub"]
    assert len(hub_joints) == 4
    for i in range(4):
        assert any(
            j.parent_link == "i_hub" and j.child_link == f"i_arm_{i}" for j in joints
        )


def test_no_duplicate_mates():
    """No duplicate mates for re-checked pairs."""
    tree = _make_tree(
        design_id="no_dup",
        prompt="three links",
        parts=[instantiate_family("link", "link")],
        instances=[
            Instance(id="i_a", part_id="link"),
            Instance(id="i_b", part_id="link"),
            Instance(id="i_c", part_id="link"),
        ],
    )
    mates, joints = infer_mates(tree, tree.assemblies[0])

    # C(3, 2) = 3 unique pairs.
    assert len(mates) == 3
    assert len(joints) == 3

    pair_keys = [
        frozenset(e.instance_id for e in m.entities) for m in mates
    ]
    assert len(pair_keys) == len(set(pair_keys))


def test_unknown_parts_fixed_mate():
    """Unknown parts fall back to a fixed mate."""
    tree = _make_tree(
        design_id="unknown",
        prompt="unknown parts",
        parts=[
            Part(id="custom_a", name="Custom A"),
            Part(id="custom_b", name="Custom B"),
        ],
        instances=[
            Instance(id="i_a", part_id="custom_a"),
            Instance(id="i_b", part_id="custom_b"),
        ],
    )
    mates, joints = infer_mates(tree, tree.assemblies[0])

    assert len(mates) == 1
    assert mates[0].type == "fixed"
    assert len(joints) == 0


def test_single_instance_returns_empty():
    """Rule layer returns empty list for single instance."""
    tree = _make_tree(
        design_id="single",
        prompt="single link",
        parts=[instantiate_family("link", "link")],
        instances=[Instance(id="i_link", part_id="link")],
    )
    mates, joints = infer_mates(tree, tree.assemblies[0])

    assert mates == []
    assert joints == []


def test_parent_child_ordering():
    """Parent candidates are ordered before children in mates and joints."""
    tree = _make_tree(
        design_id="ordering",
        prompt="hub and arm",
        parts=[
            instantiate_family("hub", "center_hub"),
            instantiate_family("link", "motor_arm"),
        ],
        instances=[
            Instance(id="i_arm_0", part_id="motor_arm"),
            Instance(id="i_hub", part_id="center_hub"),
        ],
    )
    mates, joints = infer_mates(tree, tree.assemblies[0])

    assert len(mates) == 1
    assert mates[0].entities[0].instance_id == "i_hub"
    assert mates[0].entities[1].instance_id == "i_arm_0"

    assert len(joints) == 1
    assert joints[0].parent_link == "i_hub"
    assert joints[0].child_link == "i_arm_0"


def test_llm_fallback_logs_warning(caplog):
    """LLM fallback logs a warning and returns empty when no mates are inferred."""
    tree = _make_tree(
        design_id="llm_fallback",
        prompt="single unknown part",
        parts=[Part(id="custom", name="Custom")],
        instances=[Instance(id="i_custom", part_id="custom")],
    )
    with caplog.at_level("WARNING", logger="ai_cad.mate_inference"):
        mates, joints = infer_mates(
            tree, tree.assemblies[0], use_llm=True, prompt="make it work"
        )
    assert mates == []
    assert joints == []
    assert "LLM mate proposal is not wired" in caplog.text
