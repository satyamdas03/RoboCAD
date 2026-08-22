"""Tests for RoboCAD Phase 3 parameter editing and Phase 4 design library / remix."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

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
def sample_design(tmp_path: Path):
    """Create a persisted design with code and parameters."""
    design_id = "abc123"
    design_dir = tmp_path / "designs" / design_id
    design_dir.mkdir(parents=True)
    (design_dir / "code.py").write_text(
        "length = 50.0  # overall length (mm)\n"
        "width = 20.0\n"
        "hole_diameter = 5.0\n"
    )
    (design_dir / "prompt.txt").write_text("a bracket")
    metadata = {
        "id": design_id,
        "prompt": "a bracket",
        "success": True,
        "model": "fake-model",
        "attempts_used": 1,
        "max_retries": 2,
        "latency_seconds": 1.0,
        "created_at": "2026-08-22T00:00:00Z",
        "parent_id": None,
        "tags": ["bracket", "structural"],
        "exports": {"stl": "model.stl", "step": None, "script": "code.py"},
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata))
    return design_id


def test_update_design_tags(sample_design):
    response = client.put(f"/designs/{sample_design}", json={"tags": ["updated", "bracket"]})
    assert response.status_code == 200
    data = response.json()
    assert data["tags"] == ["updated", "bracket"]

    meta_path = main_module.DESIGNS_DIR / sample_design / "metadata.json"
    meta = json.loads(meta_path.read_text())
    assert meta["tags"] == ["updated", "bracket"]


def test_update_design_prompt(sample_design):
    response = client.put(f"/designs/{sample_design}", json={"prompt": "a stronger bracket"})
    assert response.status_code == 200
    data = response.json()
    assert data["prompt"] == "a stronger bracket"
    prompt_text = (main_module.DESIGNS_DIR / sample_design / "prompt.txt").read_text()
    assert prompt_text == "a stronger bracket"


def test_list_designs_search(sample_design):
    response = client.get("/designs?search=bracket")
    assert response.status_code == 200
    designs = response.json()
    assert len(designs) == 1
    assert designs[0]["id"] == sample_design

    response = client.get("/designs?search=nonexistent")
    assert response.json() == []


def test_list_designs_tag_filter(sample_design):
    response = client.get("/designs?tag=structural")
    assert response.status_code == 200
    designs = response.json()
    assert len(designs) == 1

    response = client.get("/designs?tag=motion")
    assert response.json() == []


def test_regenerate_creates_version(sample_design, tmp_path: Path):
    stl_path = tmp_path / "new_model.stl"
    stl_path.write_text("fake stl")

    with (
        mock.patch("web.backend.main.execute_code") as mock_exec,
        mock.patch.object(main_module, "validate_model") as mock_validate,
    ):
        mock_exec.return_value = {
            "success": True,
            "stl_path": str(stl_path),
            "step_path": None,
            "error": None,
            "traceback": None,
        }
        mock_validate.return_value = {
            "valid": True,
            "manifold": True,
            "watertight": True,
            "bounds_mm": [60.0, 20.0, 5.0],
            "volume_mm3": 6000.0,
            "surface_area_mm2": 3000.0,
            "warnings": [],
            "errors": [],
        }
        response = client.post(
            f"/designs/{sample_design}/regenerate",
            json={"parameter_updates": {"length": 60.0, "hole_diameter": 6}},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["design_id"] == sample_design
    assert data["export_urls"]["stl"].startswith(f"/exports/{sample_design}/versions/")
    assert "/exports/model.stl" in data["export_urls"]["stl"]

    # Check version directory created.
    design_dir = main_module.DESIGNS_DIR / sample_design
    version_dirs = list((design_dir / "versions").iterdir())
    assert len(version_dirs) == 1
    version_dir = version_dirs[0]
    updated_code = (version_dir / "code.py").read_text()
    assert "length = 60.0" in updated_code
    assert "hole_diameter = 6" in updated_code

    # The exported STL must actually exist at the versioned path.
    assert (version_dir / "exports" / "model.stl").exists()

    # Parent metadata should point to version export.
    meta = json.loads((design_dir / "metadata.json").read_text())
    assert meta["exports"]["stl"].startswith("versions/")
    assert "/exports/model.stl" in meta["exports"]["stl"]


def test_regenerate_missing_parameter(sample_design):
    response = client.post(
        f"/designs/{sample_design}/regenerate",
        json={"parameter_updates": {"missing_param": 10.0}},
    )
    assert response.status_code == 400
    assert "missing_param" in response.text


def test_remix_links_parent(tmp_path: Path):
    # Seed parent design.
    parent_id = "parent00"
    parent_dir = tmp_path / "designs" / parent_id
    parent_dir.mkdir(parents=True)
    (parent_dir / "prompt.txt").write_text("original bracket")
    (parent_dir / "metadata.json").write_text(
        json.dumps(
            {
                "id": parent_id,
                "prompt": "original bracket",
                "success": True,
                "model": "fake",
                "attempts_used": 1,
                "max_retries": 2,
                "latency_seconds": 1.0,
                "created_at": "2026-08-22T00:00:00Z",
                "exports": {"stl": "model.stl", "step": None, "script": "code.py"},
            }
        )
    )

    stl_path = tmp_path / "remix_model.stl"
    stl_path.write_text("fake stl")
    from tests.test_web_backend import RoboCADBackendStub, make_generation_result

    backend = RoboCADBackendStub(
        api_key="fake-key",
        result=make_generation_result(
            prompt="remix prompt",
            success=True,
            code="length = 30.0\n",
            parameters=[{"name": "length", "value": 30.0, "unit": "mm", "description": None}],
            exports={"stl": str(stl_path), "step": None, "script": None},
        ),
    )

    captured = {}
    original_generate = backend.generate

    def capturing_generate(prompt, **kwargs):
        captured["prompt"] = prompt
        return original_generate(prompt, **kwargs)

    backend.generate = capturing_generate

    with mock.patch("web.backend.main.backend", backend):
        response = client.post(f"/designs/{parent_id}/remix", json={"prompt": "make it wider"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["parent_id"] == parent_id
    assert "make it wider" in captured["prompt"]
    assert "original bracket" in captured["prompt"]

    # Verify child metadata.
    child_dir = main_module.DESIGNS_DIR / data["design_id"]
    meta = json.loads((child_dir / "metadata.json").read_text())
    assert meta["parent_id"] == parent_id
    assert "make it wider" in meta["prompt"]
