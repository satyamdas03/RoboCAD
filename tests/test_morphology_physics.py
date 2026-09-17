"""Tests for Phase 29 physics-based morphology scoring."""
from __future__ import annotations

import pytest

from ai_cad.morphology_physics import physics_score_candidate
from ai_cad.robot_templates import humanoid_template, quadruped_template


pytestmark = pytest.mark.slow


def _skip_if_no_mujoco():
    try:
        import mujoco  # noqa: F401
    except Exception as exc:
        pytest.skip(f"MuJoCo not available: {exc}")


def test_physics_score_candidate_humanoid_returns_keys():
    _skip_if_no_mujoco()
    tree = humanoid_template()
    result = physics_score_candidate(tree, n_steps=100)
    expected_keys = {
        "mujoco_available",
        "load_ok",
        "standing_ok",
        "sway_ok",
        "step_ok",
        "walk_ok",
        "standing_score",
        "sway_score",
        "step_score",
        "walk_score",
        "physics_score",
        "notes",
    }
    assert expected_keys.issubset(result.keys())
    assert isinstance(result["physics_score"], float)
    assert 0.0 <= result["physics_score"] <= 1.0


def test_physics_score_candidate_quadruped_returns_keys():
    _skip_if_no_mujoco()
    tree = quadruped_template()
    result = physics_score_candidate(tree, n_steps=100)
    assert result["mujoco_available"] is True
    assert isinstance(result["physics_score"], float)
    assert 0.0 <= result["physics_score"] <= 1.0


def test_physics_score_standing_score_components():
    _skip_if_no_mujoco()
    tree = humanoid_template()
    result = physics_score_candidate(tree, n_steps=100)
    standing = result.get("standing", {})
    assert isinstance(standing.get("nan_inf"), bool)
    assert isinstance(standing.get("max_pitch_roll_deg"), float)
    assert isinstance(standing.get("torso_z_drop_m"), float)
    assert 0.0 <= result["standing_score"] <= 1.0
    assert 0.0 <= result["sway_score"] <= 1.0
    assert 0.0 <= result["step_score"] <= 1.0
    assert 0.0 <= result["walk_score"] <= 1.0
    assert isinstance(result["step"], dict)
    assert isinstance(result["walk"], dict)


def test_physics_score_candidate_humanoid_step_ok():
    _skip_if_no_mujoco()
    tree = humanoid_template()
    result = physics_score_candidate(tree, n_steps=100)
    assert result["step_ok"] is True
    assert result["physics_score"] >= 0.7


def test_physics_score_candidate_quadruped_runs_without_nan():
    _skip_if_no_mujoco()
    tree = quadruped_template()
    result = physics_score_candidate(tree, n_steps=100)
    assert result["mujoco_available"] is True
    assert isinstance(result["physics_score"], float)
    assert 0.0 <= result["physics_score"] <= 1.0
    assert isinstance(result.get("step", {}).get("nan_inf"), bool)


def test_physics_score_candidate_humanoid_walk_ok():
    _skip_if_no_mujoco()
    tree = humanoid_template()
    result = physics_score_candidate(tree, n_steps=100)
    assert result["walk_ok"] is True
    assert result["walk"]["forward_distance_m"] > 0.05
    assert result["walk"]["torso_z_drop_m"] < 0.10
    assert result["walk"]["max_pitch_roll_deg"] < 20.0


def test_physics_score_candidate_quadruped_walk_ok():
    _skip_if_no_mujoco()
    tree = quadruped_template()
    result = physics_score_candidate(tree, n_steps=100)
    assert result["walk_ok"] is True
    assert result["walk"]["forward_distance_m"] > 0.05
    assert result["walk"]["torso_z_drop_m"] < 0.10
    assert result["walk"]["max_pitch_roll_deg"] < 20.0


def test_physics_score_candidate_no_mujoco_path(monkeypatch):
    """When mujoco is unavailable the function returns gracefully."""
    import ai_cad.morphology_physics as mp

    monkeypatch.setattr(mp, "mujoco", None)
    tree = humanoid_template()
    result = physics_score_candidate(tree)
    assert result["mujoco_available"] is False
    assert result["physics_score"] == 0.0
    assert "mujoco not installed" in result["notes"]


def test_position_actuator_gains_scale_with_mass():
    _skip_if_no_mujoco()
    import mujoco
    from ai_cad.morphology_physics import _load_model_from_tree
    import tempfile
    from pathlib import Path

    tree = humanoid_template().update_parameter("robot_mass_kg", 30.0)
    with tempfile.TemporaryDirectory() as tmp:
        loaded = _load_model_from_tree(tree, Path(tmp), name="candidate")
        assert loaded is not None
        model, _ = loaded
        position_actuators = [
            i for i in range(model.nu)
            if mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i).endswith("_position")
        ]
        assert len(position_actuators) > 0
        # At least one position actuator should have kp != 600 if mass-aware scaling is active.
        kps = [model.actuator_gainprm[i][0] for i in position_actuators]
        assert any(kp != 600.0 for kp in kps)
