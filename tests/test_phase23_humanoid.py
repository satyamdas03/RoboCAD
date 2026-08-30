"""Phase 23: humanoid and full-robot system synthesis tests."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from ai_cad.actuator_sizing import actuator_summary, size_actuators_for_tree
from ai_cad.kinematic_tree import forward_kinematics, get_joint_chain, sample_reachable_workspace
from ai_cad.robot_templates import humanoid_template, manipulator_on_base_template, quadruped_template
from ai_cad.stability import check_stability, stability_summary
from ai_cad.verification import run_verification
from ai_cad.verification_models import LoadCase, VerificationRequest


@pytest.fixture
def humanoid():
    return humanoid_template(height_mm=1000.0)


def test_humanoid_template_has_biped_legs(humanoid):
    assert humanoid.domain == "mechanical"
    assert "humanoid" in humanoid.prompt.lower()
    assembly = humanoid.assemblies[0]
    ids = {j.id for j in assembly.joints}
    assert "hip_pitch_l" in ids
    assert "knee_l" in ids
    assert "ankle_l" in ids
    assert "hip_pitch_r" in ids


def test_humanoid_template_has_arms(humanoid):
    assembly = humanoid.assemblies[0]
    ids = {j.id for j in assembly.joints}
    assert "shoulder_l" in ids
    assert "elbow_l" in ids
    assert "wrist_l" in ids


def test_quadruped_template_has_four_legs():
    tree = quadruped_template(height_mm=600.0)
    assembly = tree.assemblies[0]
    foot_ids = [j.child_link for j in assembly.joints if "ankle" in j.id]
    assert len(foot_ids) == 4


def test_manipulator_on_base_template_has_arm_joints():
    tree = manipulator_on_base_template(reach_mm=800.0)
    assembly = tree.assemblies[0]
    types = [j.type for j in assembly.joints]
    assert types.count("revolute") >= 4


def test_forward_kinematics_zero_pose(humanoid):
    poses = forward_kinematics(humanoid)
    assert "torso" in poses
    # Feet should be near ground (z small) and separated in x/y.
    foot_l = poses["foot_l"]
    foot_r = poses["foot_r"]
    assert foot_l.position[2] < 50.0
    assert foot_r.position[2] < 50.0
    assert abs(foot_l.position[0] - foot_r.position[0]) > 50.0


def test_get_joint_chain(humanoid):
    chain = get_joint_chain(humanoid, "hand_r")
    ids = [j.id for j in chain]
    assert "shoulder_r" in ids
    assert "elbow_r" in ids
    assert "wrist_r" in ids


def test_sample_reachable_workspace(humanoid):
    result = sample_reachable_workspace(humanoid, "hand_r", samples_per_joint=3)
    assert result["point_count"] > 0
    assert len(result["envelope_mm"]) == 3
    assert all(e >= 0 for e in result["envelope_mm"])


def test_actuator_sizing_returns_specs(humanoid):
    specs = size_actuators_for_tree(humanoid, payload_kg=5.0, safety_factor=2.0)
    assert len(specs) > 0
    hip = specs.get("hip_pitch_l")
    assert hip is not None
    assert hip.torque_nm is not None
    assert hip.torque_nm > 0
    summary = actuator_summary(specs)
    assert summary["joint_count"] == len(specs)
    assert summary["max_torque_nm"] > 0


def test_stability_check_on_template(humanoid):
    report = check_stability(humanoid, robot_mass_kg=20.0)
    assert report.support_polygon_m2 > 0
    summary = stability_summary(report)
    assert "statically_stable" in summary
    assert "gait_feasible" in summary


def test_verification_stability_load_case(tmp_path: Path, humanoid):
    design_dir = tmp_path / "humanoid"
    design_dir.mkdir()
    (design_dir / "feature_tree.json").write_text(humanoid.model_dump_json(), encoding="utf-8")
    request = VerificationRequest(
        design_id="humanoid",
        load_case=LoadCase.STABILITY_CHECK,
        parameters={"robot_mass_kg": 20.0, "lateral_accel_m_s2": 0.5},
    )
    result = run_verification(request, design_dir=design_dir)
    assert result.passed or not result.errors
    assert "statically_stable" in result.metrics or result.raw_output


def test_verification_workspace_load_case(tmp_path: Path, humanoid):
    design_dir = tmp_path / "humanoid"
    design_dir.mkdir()
    (design_dir / "feature_tree.json").write_text(humanoid.model_dump_json(), encoding="utf-8")
    request = VerificationRequest(
        design_id="humanoid",
        load_case=LoadCase.REACHABLE_WORKSPACE,
        parameters={"end_effector_id": "hand_r"},
    )
    result = run_verification(request, design_dir=design_dir)
    assert result.passed or not result.errors
    assert "envelope_x_mm" in result.metrics


def test_verification_gait_feasibility_load_case(tmp_path: Path, humanoid):
    design_dir = tmp_path / "humanoid"
    design_dir.mkdir()
    (design_dir / "feature_tree.json").write_text(humanoid.model_dump_json(), encoding="utf-8")
    request = VerificationRequest(
        design_id="humanoid",
        load_case=LoadCase.GAIT_FEASIBILITY,
        parameters={"robot_mass_kg": 20.0, "swing_foot_id": "foot_l"},
    )
    result = run_verification(request, design_dir=design_dir)
    assert result.load_case == LoadCase.GAIT_FEASIBILITY
    assert "gait_feasible" in result.metrics
