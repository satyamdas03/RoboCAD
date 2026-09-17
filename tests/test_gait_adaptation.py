"""Tests for morphology-aware gait adaptation."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.slow


def _skip_if_no_mujoco():
    try:
        import mujoco  # noqa: F401
    except Exception as exc:
        pytest.skip(f"MuJoCo not available: {exc}")


def test_gait_morphology_features_humanoid():
    _skip_if_no_mujoco()
    from ai_cad.gait_adaptation import extract_morphology_features
    from ai_cad.morphology_physics import _load_model_from_tree
    from ai_cad.robot_templates import humanoid_template

    import tempfile
    from pathlib import Path

    tree = humanoid_template()
    with tempfile.TemporaryDirectory() as tmp:
        loaded = _load_model_from_tree(tree, Path(tmp), name="candidate")
        assert loaded is not None
        model, data = loaded
        features = extract_morphology_features(model, data, tree)
        assert features.template == "humanoid"
        assert features.com_height_m > 0.3
        assert features.total_leg_length_m > 0.2
        assert features.robot_mass_kg > 0.0
        assert features.foot_length_m > 0.0
        assert features.foot_width_m > 0.0


def test_gait_morphology_features_quadruped():
    _skip_if_no_mujoco()
    from ai_cad.gait_adaptation import extract_morphology_features
    from ai_cad.morphology_physics import _load_model_from_tree
    from ai_cad.robot_templates import quadruped_template

    import tempfile
    from pathlib import Path

    tree = quadruped_template()
    with tempfile.TemporaryDirectory() as tmp:
        loaded = _load_model_from_tree(tree, Path(tmp), name="candidate")
        assert loaded is not None
        model, data = loaded
        features = extract_morphology_features(model, data, tree)
        assert features.template == "quadruped"
        assert features.com_height_m > 0.1
        assert features.total_leg_length_m > 0.1


def test_morphology_aware_params_humanoid():
    _skip_if_no_mujoco()
    from ai_cad.gait_adaptation import GaitMorphologyFeatures
    from ai_cad.gait import morphology_aware_walk_params, morphology_aware_balance_gains

    features = GaitMorphologyFeatures(
        template="humanoid",
        com_height_m=1.0,
        total_leg_length_m=0.46,
        robot_mass_kg=20.0,
        foot_length_m=0.16,
        foot_width_m=0.08,
    )
    params = morphology_aware_walk_params(features)
    gains = morphology_aware_balance_gains(features)
    assert params.step_period_s > 0.0
    assert 0.0 < params.duty_factor < 1.0
    assert params.step_height_m > 0.0
    assert gains.hip_pitch_gain > 0.0
    assert gains.ankle_pitch_gain > 0.0


def test_morphology_aware_params_quadruped():
    _skip_if_no_mujoco()
    from ai_cad.gait_adaptation import GaitMorphologyFeatures
    from ai_cad.gait import morphology_aware_walk_params, morphology_aware_balance_gains

    features = GaitMorphologyFeatures(
        template="quadruped",
        com_height_m=0.5,
        total_leg_length_m=0.30,
        robot_mass_kg=15.0,
        foot_length_m=0.10,
        foot_width_m=0.05,
    )
    params = morphology_aware_walk_params(features)
    gains = morphology_aware_balance_gains(features)
    assert params.step_period_s > 0.0
    assert gains.com_vel_target >= 0.0
