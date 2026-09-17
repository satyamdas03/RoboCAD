"""Tests for Milestone C sagittal-plane workspace proxy and manipulability."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.slow


def test_humanoid_workspace_proxy_nonzero_for_sagittal_arm():
    from ai_cad.morphology_workspace import workspace_proxy
    from ai_cad.robot_templates import humanoid_template

    tree = humanoid_template()
    result = workspace_proxy(tree, "hand_r")
    assert result["reach_mm"] > 0.0
    assert result["sagittal_area_mm2"] > 0.0
    assert result["workspace_score"] > 0.0


def test_manipulability_nonzero_for_manipulator():
    from ai_cad.morphology_workspace import manipulability_score
    from ai_cad.robot_templates import manipulator_on_base_template

    tree = manipulator_on_base_template()
    score = manipulability_score(tree, "end_effector")
    assert score > 0.0
