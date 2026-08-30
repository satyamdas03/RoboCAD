"""Tests for the RoboCAD verification backend endpoints."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import trimesh
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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


@pytest.fixture
def bracket_design(tmp_path: Path):
    """Create a persisted design with a simple bracket STL."""
    design_id = "bracket123"
    design_dir = tmp_path / "designs" / design_id
    design_dir.mkdir(parents=True, exist_ok=True)
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    mesh = trimesh.creation.box(extents=(50.0, 20.0, 5.0))
    stl_path = exports_dir / "model.stl"
    mesh.export(stl_path)

    metadata = {
        "id": design_id,
        "prompt": "a bracket",
        "success": True,
        "model": "fake",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "created_at": "2026-08-29T00:00:00Z",
        "exports": {"stl": "exports/model.stl", "step": None, "script": None},
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata))
    return design_id


def test_verify_static_stress(bracket_design: str):
    response = client.post(
        f"/designs/{bracket_design}/verify",
        json={"load_case": "static_stress", "materials": {}, "parameters": {"material": "PLA", "load_magnitude_n": 50}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == bracket_design
    report = data["report"]
    assert report["load_case"] == "static_stress"
    assert "max_stress_mpa" in report["metrics"]
    assert "report_id" in report


def test_verify_mesh_quality(bracket_design: str):
    response = client.post(
        f"/designs/{bracket_design}/verify",
        json={"load_case": "mesh_quality"},
    )
    assert response.status_code == 200
    data = response.json()
    report = data["report"]
    assert report["load_case"] == "mesh_quality"
    assert report["mesh_report"]["is_suitable_for_solver"] is True


def test_mesh_quality_check_endpoint(bracket_design: str):
    response = client.post(f"/designs/{bracket_design}/mesh-quality-check", json={})
    assert response.status_code == 200
    report = response.json()["report"]
    assert report["load_case"] == "mesh_quality"
    assert report["mesh_report"]["triangle_count"] > 0


def test_verify_unknown_load_case(bracket_design: str):
    response = client.post(
        f"/designs/{bracket_design}/verify",
        json={"load_case": "unknown_case"},
    )
    assert response.status_code == 400
    assert "Unsupported load case" in response.text


def test_verify_report_not_found(bracket_design: str):
    response = client.get(f"/designs/{bracket_design}/verify-report/nosuchid")
    assert response.status_code == 404


def test_verify_thermal_resistance(bracket_design: str):
    response = client.post(
        f"/designs/{bracket_design}/verify",
        json={
            "load_case": "heat_sink_thermal_resistance",
            "parameters": {"heat_flux_w": 5.0, "target_theta_c_per_w": 10.0, "material": "Aluminum 6061"},
        },
    )
    assert response.status_code == 200
    report = response.json()["report"]
    assert report["load_case"] == "heat_sink_thermal_resistance"
    assert "thermal_resistance_c_per_w" in report["metrics"]


def test_verify_wind_tunnel_drag(bracket_design: str):
    response = client.post(
        f"/designs/{bracket_design}/verify",
        json={"load_case": "wind_tunnel_drag", "parameters": {"velocity_m_s": 10.0, "drag_coefficient": 1.0}},
    )
    assert response.status_code == 200
    report = response.json()["report"]
    assert report["load_case"] == "wind_tunnel_drag"
    assert "drag_force_n" in report["metrics"]


def test_verify_joint_torque_check():
    design_id = "joint123"
    design_dir = main_module.DESIGNS_DIR / design_id
    design_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "id": design_id,
        "prompt": "an arm",
        "success": True,
        "model": "fake",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "created_at": "2026-08-29T00:00:00Z",
        "exports": {},
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata))
    response = client.post(
        f"/designs/{design_id}/verify",
        json={
            "load_case": "joint_torque_check",
            "parameters": {"load_mass_kg": 0.5, "arm_length_m": 0.2, "stall_torque_nm": 5.0},
        },
    )
    assert response.status_code == 200
    report = response.json()["report"]
    assert report["load_case"] == "joint_torque_check"
    assert report["metrics"]["required_torque_nm"] > 0
