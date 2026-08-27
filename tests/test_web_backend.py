"""Tests for the RoboCAD Phase 2 FastAPI backend."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

# Ensure repo root is on sys.path for `ai_cad` imports.
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
    # Restore original path.
    main_module.DESIGNS_DIR = original


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_generate_missing_api_key():
    with mock.patch("web.backend.main.backend", RoboCADBackendStub(api_key=None)):
        response = client.post("/generate", json={"prompt": "a cube"})
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.text


def test_generate_success_persists_design(tmp_path: Path):
    stl_path = tmp_path / "model.stl"
    stl_path.write_text("fake stl")
    step_path = tmp_path / "model.step"
    step_path.write_text("fake step")

    backend = RoboCADBackendStub(
        api_key="fake-key",
        result=make_generation_result(
            prompt="a cube",
            success=True,
            code="length = 10.0\n",
            parameters=[{"name": "length", "value": 10.0, "unit": "mm", "description": None}],
            exports={"stl": str(stl_path), "step": str(step_path), "script": None},
        ),
    )

    with mock.patch("web.backend.main.backend", backend):
        response = client.post("/generate", json={"prompt": "a cube", "max_retries": 2})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["prompt"] == "a cube"
    assert data["design_id"] is not None
    assert data["export_urls"]["stl"].startswith(f"/exports/{data['design_id']}/")
    assert data["export_urls"]["stl"].endswith("/model.stl")

    # Check filesystem persistence.
    design_dir = main_module.DESIGNS_DIR / data["design_id"]
    assert (design_dir / "prompt.txt").read_text() == "a cube"
    assert (design_dir / "code.py").read_text() == "length = 10.0\n"
    params = json.loads((design_dir / "parameters.json").read_text())
    assert params[0]["name"] == "length"
    meta = json.loads((design_dir / "metadata.json").read_text())
    assert meta["success"] is True


def test_list_designs(tmp_path: Path):
    # Seed one design directory manually.
    design_dir = tmp_path / "designs" / "abc123"
    design_dir.mkdir(parents=True)
    (design_dir / "metadata.json").write_text(
        json.dumps(
            {
                "id": "abc123",
                "prompt": "a bracket",
                "success": True,
                "model": "fake",
                "attempts_used": 1,
                "max_retries": 2,
                "latency_seconds": 1.5,
                "created_at": "2026-08-22T00:00:00Z",
                "exports": {"stl": "model.stl", "step": None, "script": None},
            }
        )
    )

    response = client.get("/designs")
    assert response.status_code == 200
    designs = response.json()
    assert len(designs) == 1
    assert designs[0]["id"] == "abc123"


def test_get_design_not_found():
    response = client.get("/designs/does-not-exist")
    assert response.status_code == 404


def test_get_export_file(tmp_path: Path):
    design_dir = tmp_path / "designs" / "exp456"
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True)
    (exports_dir / "model.stl").write_text("fake binary stl")

    response = client.get("/exports/exp456/model.stl")
    assert response.status_code == 200
    assert response.content == b"fake binary stl"


def test_get_export_file_not_found():
    response = client.get("/exports/no-such/file.stl")
    assert response.status_code == 404


def test_dfm_report_endpoint(tmp_path: Path):
    design_dir, stl_path = _seed_cube_design(tmp_path, "cube1", size=10.0)
    response = client.get("/designs/cube1/dfm-report")
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == "cube1"
    report = data["report"]
    assert isinstance(report["valid"], bool)
    assert report["min_wall_thickness_mm"] is not None


def test_fea_report_endpoint(tmp_path: Path):
    design_dir, stl_path = _seed_cube_design(tmp_path, "cube2", size=10.0)
    response = client.post("/designs/cube2/fea-report", json={"fixed_face": "-x", "load_magnitude_n": 50, "material": "PLA"})
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == "cube2"
    report = data["report"]
    assert report["success"] is True
    assert report["max_stress_mpa"] is not None


def test_fit_check_endpoint(tmp_path: Path):
    _seed_cube_design(tmp_path, "shaft", size=6.0)
    _seed_cube_design(tmp_path, "hole", size=8.0)
    response = client.post(
        "/designs/shaft/fit-check",
        json={"other_design_id": "hole", "name": "shaft_hole", "samples": 500},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == "shaft"
    assert data["other_design_id"] == "hole"
    report = data["report"]
    assert report["classification"] in ("clearance", "transition", "interference")


# Helpers

class RoboCADBackendStub:
    def __init__(self, api_key: str | None = "fake-key", result=None):
        self.api_key = api_key
        self._result = result

    def generate(self, prompt, **kwargs):
        if self._result is None:
            raise RuntimeError("Stub not configured")
        return self._result


def make_generation_result(
    success: bool,
    code: str | None,
    parameters: list[dict],
    exports: dict,
    prompt: str = "ignored",
):
    from ai_cad.models import ExportPaths, GenerationResult, ValidationReport

    return GenerationResult(
        prompt=prompt,
        success=success,
        code=code,
        parameters=[__parse_param(p) for p in parameters],
        exports=ExportPaths(
            step=exports.get("step"),
            stl=exports.get("stl"),
            script=exports.get("script"),
        ),
        validation=ValidationReport(valid=success),
        attempts_used=1,
        max_retries=2,
        model="fake-model",
    )


def __parse_param(p: dict):
    from ai_cad.models import CADParameter

    return CADParameter(**p)


def _seed_cube_design(tmp_path: Path, design_id: str, size: float = 10.0):
    """Create a persisted design with a minimal ASCII STL cube."""
    design_dir = tmp_path / "designs" / design_id
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True)
    stl_path = exports_dir / "model.stl"
    stl_path.write_text(_ascii_cube_stl(size))
    metadata = {
        "id": design_id,
        "prompt": f"a {size} mm cube",
        "success": True,
        "model": "fake",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "created_at": "2026-08-25T00:00:00Z",
        "exports": {"stl": "model.stl", "step": None, "script": None},
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata))
    return design_dir, stl_path


def test_simulate_endpoint_stl_fallback(tmp_path: Path):
    design_dir, stl_path = _seed_cube_design(tmp_path, "simcube", size=10.0)
    response = client.post("/designs/simcube/simulate", json={"material": "PLA", "tolerance": 0.1})
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == "simcube"
    assert data["valid"] is True
    assert data["bundle_url"].startswith("/exports/simcube/simulation/bundle.zip")


def test_get_simulation_report_endpoint(tmp_path: Path):
    _seed_cube_design(tmp_path, "simcube2", size=10.0)
    response = client.post("/designs/simcube2/simulate", json={"material": "PLA"})
    assert response.status_code == 200

    response = client.get("/designs/simcube2/simulation")
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == "simcube2"
    assert "manifest" in data
    assert "verification" in data


def test_download_bundle_endpoint(tmp_path: Path):
    _seed_cube_design(tmp_path, "simcube3", size=10.0)
    response = client.post("/designs/simcube3/simulate", json={"material": "PLA"})
    assert response.status_code == 200

    response = client.get("/designs/simcube3/bundle")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert len(response.content) > 0


def test_compose_scene_endpoint(tmp_path: Path):
    pytest.importorskip("mujoco")
    _seed_cube_design(tmp_path, "scenecube", size=10.0)
    response = client.post("/designs/scenecube/scene", json={"template": "gripper_cube_grasp", "material": "PLA", "tolerance": 0.1})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["design_id"] == "scenecube"
    assert data["template"] == "gripper_cube_grasp"
    assert data["runtime_ok"] is True
    assert data["scene_url"].startswith("/exports/scenecube/simulation/scene_gripper_cube_grasp.mjcf")


def test_get_scene_report_endpoint(tmp_path: Path):
    pytest.importorskip("mujoco")
    _seed_cube_design(tmp_path, "scenecube2", size=10.0)
    response = client.post("/designs/scenecube2/scene", json={"template": "wedge_push_block"})
    assert response.status_code == 200

    response = client.get("/designs/scenecube2/scene?template=wedge_push_block")
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == "scenecube2"
    assert data["template"] == "wedge_push_block"
    assert "scene" in data


def test_simulate_endpoint_with_feature_tree(tmp_path: Path):
    design_dir = tmp_path / "designs" / "ftcube"
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True)
    stl_path = exports_dir / "model.stl"
    stl_path.write_text(_ascii_cube_stl(10.0))

    feature_tree = {
        "schema_version": "1.0.0",
        "design_id": "ftcube",
        "prompt": "a 10 mm cube",
        "created_at": "2026-08-25T00:00:00Z",
        "units": "mm",
        "parameters": [],
        "parts": [
            {
                "id": "cube",
                "material": "PLA",
                "sketches": [
                    {
                        "id": "profile",
                        "plane": {"type": "base", "name": "XY"},
                        "entities": [
                            {"type": "rectangle", "id": "base", "center": [0, 0], "width": 10, "height": 10}
                        ],
                    }
                ],
                "features": [
                    {"id": "extrude1", "type": "extrude", "sketch_id": "profile", "parameters": {"amount": 10, "mode": "add"}}
                ],
            }
        ],
    }
    (design_dir / "feature_tree.json").write_text(json.dumps(feature_tree))
    metadata = {
        "id": "ftcube",
        "prompt": "a 10 mm cube",
        "success": True,
        "model": "fake",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "created_at": "2026-08-25T00:00:00Z",
        "exports": {"stl": "model.stl", "step": None, "script": None},
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata))

    response = client.post("/designs/ftcube/simulate", json={"material": "PLA", "tolerance": 0.1})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["design_id"] == "ftcube"
    assert data["valid"] is True
    manifest = data["manifest"]
    assert len(manifest["parts"]) == 1
    assert manifest["parts"][0]["material"] == "PLA"


def _ascii_cube_stl(size: float = 10.0) -> str:
    """Return a minimal valid ASCII STL for a centered cube."""
    h = size / 2.0
    v = [
        (-h, -h, -h),
        (h, -h, -h),
        (h, h, -h),
        (-h, h, -h),
        (-h, -h, h),
        (h, -h, h),
        (h, h, h),
        (-h, h, h),
    ]
    # 12 triangles (two per face).
    faces = [
        (0, 2, 1),
        (0, 3, 2),  # front/back
        (4, 5, 6),
        (4, 6, 7),
        (0, 1, 5),
        (0, 5, 4),  # bottom
        (3, 6, 2),
        (3, 7, 6),  # top
        (0, 4, 7),
        (0, 7, 3),  # left
        (1, 2, 6),
        (1, 6, 5),  # right
    ]
    lines = ["solid cube"]
    for a, b, c in faces:
        p1, p2, p3 = v[a], v[b], v[c]
        lines.append("  facet normal 0 0 0")
        lines.append("    outer loop")
        lines.append(f"      vertex {p1[0]} {p1[1]} {p1[2]}")
        lines.append(f"      vertex {p2[0]} {p2[1]} {p2[2]}")
        lines.append(f"      vertex {p3[0]} {p3[1]} {p3[2]}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid cube")
    return "\n".join(lines) + "\n"
