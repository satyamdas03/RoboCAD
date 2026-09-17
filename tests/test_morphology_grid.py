"""Grid regression tests for morphology gait robustness (Milestone A)."""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.mujoco]


def _skip_if_no_mujoco():
    try:
        import mujoco  # noqa: F401
    except Exception as exc:
        pytest.skip(f"MuJoCo not available: {exc}")


def test_physics_score_candidate_uses_sweep():
    _skip_if_no_mujoco()
    from ai_cad.morphology_physics import physics_score_candidate
    from ai_cad.robot_templates import humanoid_template

    tree = humanoid_template()
    result = physics_score_candidate(tree, n_steps=100)
    assert result["mujoco_available"] is True
    assert "walk_score" in result
    assert result["walk_score"] >= 0.0
    assert result["walk_score"] <= 1.0
