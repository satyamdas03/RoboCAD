import pytest

from ai_cad.decomposition import (
    DecomposedPart,
    decompose,
    should_decompose,
)


def test_single_part_prompt_is_not_system():
    assert should_decompose("A 120 mm bracket with four M3 holes") is False


def test_quadcopter_is_system_prompt():
    assert should_decompose("450 mm quadcopter with four motor arms") is True


def test_robot_arm_is_system_prompt():
    assert should_decompose("robot arm with gripper") is True


def test_decompose_quadcopter_rule_based():
    result = decompose("450 mm quadcopter with four motor arms", use_llm=False)
    assert result.primary_domain == "mechanical"
    assert result.multi_domain is True
    ids = {p.id for p in result.parts}
    assert "frame_hub" in ids
    assert "motor_arm" in ids
    assert "motor_mount" in ids

    motor_arm = next(p for p in result.parts if p.id == "motor_arm")
    assert motor_arm.count == 4
    assert motor_arm.family == "link"
    assert motor_arm.domain == "mechanical"


def test_decompose_quadcopter_without_explicit_count():
    result = decompose("quadcopter frame", use_llm=False)
    motor_arm = next((p for p in result.parts if p.id == "motor_arm"), None)
    assert motor_arm is not None
    assert motor_arm.count == 4


def test_decompose_robot_arm():
    result = decompose("robot arm with gripper", use_llm=False)
    ids = {p.id for p in result.parts}
    assert "arm_base" in ids
    assert "upper_link" in ids
    assert "forearm_link" in ids
    assert "gripper" in ids

    gripper = next(p for p in result.parts if p.id == "gripper")
    assert gripper.count == 2
    assert gripper.domain == "humanoid"


def test_decompose_humanoid():
    result = decompose("humanoid robot torso and legs", use_llm=False)
    ids = {p.id for p in result.parts}
    assert "torso_plate" in ids
    assert "thigh" in ids
    assert "shin" in ids


def test_decompose_fixed_wing():
    result = decompose("fixed wing aircraft", use_llm=False)
    ids = {p.id for p in result.parts}
    assert "fuselage" in ids
    assert "main_wing" in ids


def test_decompose_unknown_single_part_fallback():
    result = decompose("a small blue cylinder", use_llm=False)
    assert len(result.parts) == 1
    assert result.parts[0].domain == "mechanical"


def test_decomposed_part_defaults():
    part = DecomposedPart(id="p1", name="Test", domain="mechanical", family="bracket", sub_prompt="test")
    assert part.count == 1
    assert part.parameters == []
