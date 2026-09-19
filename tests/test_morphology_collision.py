"""Tests for Milestone C self-collision scoring."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.slow


def test_humanoid_default_pose_has_no_self_collision(tmp_path):
    from ai_cad.morphology_collision import score_candidate_collision
    from ai_cad.robot_templates import humanoid_template

    tree = humanoid_template()
    result = score_candidate_collision(tree, output_dir=tmp_path)
    assert result["collision_penalty"] < 0.5
    assert result["poses_checked"] >= 1


@pytest.mark.heavy
def test_morphology_search_prefers_collision_free_humanoid():
    from ai_cad.morphology import default_space, search_morphologies

    space = default_space("humanoid")
    space.n_max = 8
    space.end_effectors = ["default"]
    candidates = search_morphologies(space, payload_kg=5.0, robot_mass_kg=20.0, use_physics=False, use_structural=False, use_collision=True)
    assert candidates
    top = max(candidates, key=lambda c: c.composite_score)
    assert top.scores.get("collision_penalty", 1.0) < 0.5
