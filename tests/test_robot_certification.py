"""Tests for robot simulation certification (Milestone G)."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_cad.feature_tree import FeatureTree
from ai_cad.robot_certification import (
    DEFAULT_ROBOT_CERT_CASES,
    RobotCertCase,
    RobotCertificationResult,
    run_robot_certification,
)
from ai_cad.robot_templates import humanoid_template, quadruped_template


pytestmark = pytest.mark.slow


def _skip_if_no_mujoco():
    try:
        import mujoco  # noqa: F401
    except Exception as exc:
        pytest.skip(f"MuJoCo not available: {exc}")


def test_robot_cert_module_imports():
    """The certification module should import without MuJoCo side effects."""
    from ai_cad.robot_certification import DEFAULT_ROBOT_CERT_CASES

    assert len(DEFAULT_ROBOT_CERT_CASES) >= 5
    assert RobotCertCase.TERRAIN_WALKING in DEFAULT_ROBOT_CERT_CASES


def test_run_robot_certification_no_mujoco(monkeypatch):
    """Without MuJoCo the function degrades gracefully and reports skips."""
    import ai_cad.robot_certification as rc

    monkeypatch.setattr(rc, "mujoco", None)
    tree = humanoid_template()
    result = run_robot_certification(tree, cases=[RobotCertCase.TERRAIN_WALKING], cleanup=True)
    assert isinstance(result, RobotCertificationResult)
    assert result.mu_joco_available is False
    assert result.passed is False
    assert result.score == 0.0
    assert len(result.cases) == 1
    assert result.cases[0].skipped is True
    assert "mujoco not installed" in result.notes[0]


def test_run_robot_certification_non_robot_tree_skips():
    """A generic bracket-like tree has no applicable robot cases."""
    tree = FeatureTree(design_id="bracket_1", prompt="bracket")
    result = run_robot_certification(tree, cleanup=True)
    assert isinstance(result, RobotCertificationResult)
    # No legs/torso means all dynamic cases are skipped.
    skipped = [c for c in result.cases if c.skipped]
    assert len(skipped) >= 4


def test_humanoid_certification_runs_all_cases():
    """Default humanoid template should exercise every robot cert case."""
    _skip_if_no_mujoco()
    tree = humanoid_template()
    result = run_robot_certification(tree, cleanup=True)
    assert isinstance(result, RobotCertificationResult)
    case_names = {c.case for c in result.cases}
    for expected in DEFAULT_ROBOT_CERT_CASES:
        assert expected.value in case_names
    # At least one non-skipped dynamic case should run for a legged robot.
    dynamic = [c for c in result.cases if not c.skipped and c.case != RobotCertCase.PAYLOAD_LIFT.value]
    assert len(dynamic) >= 1
    assert 0.0 <= result.score <= 1.0


def test_humanoid_certification_keeps_bundle():
    """When output_dir is supplied the bundle directory is recorded."""
    _skip_if_no_mujoco()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cert"
        tree = humanoid_template()
        result = run_robot_certification(tree, output_dir=out, cleanup=False, cases=[RobotCertCase.PUSH_RECOVERY])
        assert result.bundle_dir is not None
        assert Path(result.bundle_dir).exists()


def test_quadruped_certification_runs_terrain_case():
    """Quadruped template should attempt terrain walking."""
    _skip_if_no_mujoco()
    tree = quadruped_template()
    result = run_robot_certification(tree, cases=[RobotCertCase.TERRAIN_WALKING], cleanup=True)
    terrain_case = next(c for c in result.cases if c.case == RobotCertCase.TERRAIN_WALKING.value)
    assert terrain_case.skipped is False
    assert "terrain" in terrain_case.details
