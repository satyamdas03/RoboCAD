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
