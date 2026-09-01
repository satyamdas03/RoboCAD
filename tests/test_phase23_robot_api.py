"""End-to-end API tests for Phase 23 robot system synthesis."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.slow]

from web.backend import main as main_module
from web.backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_designs(tmp_path: Path):
    """Use a temporary designs directory for every test."""
    original = main_module.DESIGNS_DIR
    test_dir = tmp_path / "designs"
    test_dir.mkdir(parents=True, exist_ok=True)
    main_module.DESIGNS_DIR = test_dir
    yield
    main_module.DESIGNS_DIR = original


@pytest.mark.parametrize("template", ["humanoid", "quadruped", "manipulator_on_base"])
def test_create_robot_template(template: str):
    r = client.post("/robot-templates", json={"template": template, "parameters": {}})
    assert r.status_code == 200
    data = r.json()
    assert data["template"] == template
    assert data["design_id"]
    assert "feature_tree" in data


def test_list_robot_templates():
    r = client.get("/robot-templates")
    assert r.status_code == 200
    names = [t["name"] for t in r.json().get("templates", [])]
    assert "humanoid" in names
    assert "quadruped" in names
    assert "manipulator_on_base" in names


def test_robot_analysis_humanoid():
    r = client.post("/robot-templates", json={"template": "humanoid", "parameters": {"robot_height": 1000}})
    design_id = r.json()["design_id"]

    r = client.post(f"/designs/{design_id}/robot-analysis", json={})
    assert r.status_code == 200
    data = r.json()
    assert data["actuator_summary"]["joint_count"] > 0
    assert "statically_stable" in data["stability"]
    assert data["reachable_workspace"]["point_count"] > 0
    assert "gait_feasible" in data


@pytest.mark.parametrize("template", ["humanoid", "quadruped", "manipulator_on_base"])
def test_simulate_robot_template(template: str):
    r = client.post("/robot-templates", json={"template": template, "parameters": {}})
    design_id = r.json()["design_id"]

    r = client.post(f"/designs/{design_id}/simulate", json={"format": "mjcf", "tolerance": 0.1})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True
    assert data["bundle_url"]
    assert data["manifest"]["mjcf_file"]
    assert data["manifest"]["urdf_file"]
