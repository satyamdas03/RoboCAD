"""Tests for the RoboCAD Phase 2 FastAPI backend."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.slow]

from ai_cad.feature_tree import (
    Assembly,
    Feature,
    FeatureTree,
    Instance,
    Part,
    PlaneReference,
    Sketch,
    SketchEntity,
)

# Ensure repo root is on sys.path for `ai_cad` imports.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web.backend import main as main_module
from web.backend.main import app

# Auth middleware requires a bearer token when the client is not on a loopback
# address. TestClient presents itself as "testclient", so every test must both
# configure the key in the environment and send it as a header.
TEST_API_KEY = "test-api-key"
os.environ["ROBOCAD_API_KEY"] = TEST_API_KEY
client = TestClient(app, headers={"Authorization": f"Bearer {TEST_API_KEY}"})


def _hex_id(label: str = "a") -> str:
    """Return a valid 32-character hex design_id derived from *label*."""
    h = "".join(f"{ord(c):02x}" for c in label)
    if len(h) < 32:
        h = (h * ((32 // len(h)) + 1))[:32]
    return h[:32]


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
    response = client.get("/health?verbose=1")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "checks" in data


def test_generate_missing_anthropic_key():
    """Authenticated requests still fail with 503 if the backend has no ANTHROPIC_API_KEY."""
    with mock.patch("web.backend.main.backend", RoboCADBackendStub(api_key=None)):
        response = client.post("/generate", json={"prompt": "a cube"})
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.text


def test_public_auth_enforcement():
    """Public auth is on by default; non-loopback requests without a valid token are rejected."""
    async def call_generate_as_public(host: str, headers: list[list[bytes]] | None = None) -> tuple[int, bytes]:
        status: int | None = None
        body = b""

        async def receive():
            return {"type": "http.request", "body": b'{"prompt":"a cube"}'}

        async def send(message):
            nonlocal status, body
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                body += message.get("body", b"")

        request_headers: list[list[bytes]] = [
            [b"host", b"example.com"],
            [b"content-type", b"application/json"],
        ]
        if headers:
            request_headers.extend(headers)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/generate",
            "raw_path": b"/generate",
            "query_string": b"",
            "headers": request_headers,
            "scheme": "http",
            "server": ("example.com", 8000),
            "client": (host, 12345),
            "root_path": "",
        }
        await app(scope, receive, send)
        return status, body

    # By default, non-loopback requests without a bearer token are rejected.
    status, body = asyncio.run(call_generate_as_public("192.168.1.100"))
    assert status == 401
    assert b"API key" in body or b"Public access" in body or b"Invalid or missing API key" in body

    # A valid bearer token allows the request through (it may still fail on missing API key).
    status, _ = asyncio.run(
        call_generate_as_public("192.168.1.100", headers=[[b"authorization", f"Bearer {TEST_API_KEY}".encode()]])
    )
    assert status in (200, 503)

    # Loopback/TestClient requests remain exempt.
    response = client.post("/generate", json={"prompt": "a cube"})
    assert response.status_code in (200, 503)

    # Public auth can be explicitly disabled.
    with mock.patch.dict(os.environ, {"ROBOCAD_ENABLE_PUBLIC_AUTH": "0"}):
        status, _ = asyncio.run(call_generate_as_public("192.168.1.100"))
        assert status in (200, 503)




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
    design_id = _hex_id("1")
    design_dir = tmp_path / "designs" / design_id
    design_dir.mkdir(parents=True)
    (design_dir / "metadata.json").write_text(
        json.dumps(
            {
                "id": design_id,
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
    assert designs[0]["id"] == design_id


def test_get_design_not_found():
    design_id = _hex_id("f")
    response = client.get(f"/designs/{design_id}")
    assert response.status_code == 404


def test_get_export_file(tmp_path: Path):
    design_id = _hex_id("e")
    design_dir = tmp_path / "designs" / design_id
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True)
    (exports_dir / "model.stl").write_text("fake binary stl")

    response = client.get(f"/exports/{design_id}/model.stl")
    assert response.status_code == 200
    assert response.content == b"fake binary stl"


def test_get_export_file_not_found():
    design_id = _hex_id("f")
    response = client.get(f"/exports/{design_id}/file.stl")
    assert response.status_code == 404


def test_get_export_file_rejects_traversal(tmp_path: Path):
    """Raw dot-segment paths must be rejected before leaving the design directory."""
    design_id = _hex_id("d")
    design_dir = tmp_path / "designs" / design_id
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True)
    (exports_dir / "model.stl").write_text("ok", encoding="utf-8")
    probe = tmp_path / "outside.txt"
    probe.write_text("exploit-ok", encoding="utf-8")
    main_module.DESIGNS_DIR = tmp_path / "designs"

    async def call_raw(path: str) -> tuple[int, bytes]:
        status: int | None = None
        body = b""

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            nonlocal status, body
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                body += message.get("body", b"")

        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [[b"host", b"localhost"]],
            "scheme": "http",
            "server": ("localhost", 8000),
            "client": ("127.0.0.1", 0),
            "root_path": "",
        }
        await app(scope, receive, send)
        return status, body

    status, body = asyncio.run(call_raw(f"/exports/{design_id}/../../outside.txt"))
    assert status == 400
    assert b"exploit-ok" not in body


def test_resolve_export_path_rejects_traversal_in_metadata(tmp_path: Path):
    """Filenames read from persisted metadata must also stay inside the design dir."""
    design_id = _hex_id("g")
    main_module.DESIGNS_DIR = tmp_path / "designs"
    design_dir = tmp_path / "designs" / design_id
    design_dir.mkdir(parents=True)
    (tmp_path / "outside.txt").write_text("exploit", encoding="utf-8")

    with pytest.raises(Exception):
        main_module._resolve_export_path(design_id, "../../outside.txt")


def test_dfm_report_endpoint(tmp_path: Path):
    design_id = _hex_id("c")
    design_dir, stl_path = _seed_cube_design(tmp_path, design_id, size=10.0)
    response = client.get(f"/designs/{design_id}/dfm-report")
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == design_id
    report = data["report"]
    assert isinstance(report["valid"], bool)
    assert report["min_wall_thickness_mm"] is not None


def test_fea_report_endpoint(tmp_path: Path):
    design_id = _hex_id("b")
    design_dir, stl_path = _seed_cube_design(tmp_path, design_id, size=10.0)
    response = client.post(
        f"/designs/{design_id}/fea-report",
        json={"fixed_face": "-x", "load_magnitude_n": 50, "material": "PLA"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == design_id
    report = data["report"]
    assert report["success"] is True
    assert report["max_stress_mpa"] is not None


def test_fit_check_endpoint(tmp_path: Path):
    shaft_id = _hex_id("s")
    hole_id = _hex_id("h")
    _seed_cube_design(tmp_path, shaft_id, size=6.0)
    _seed_cube_design(tmp_path, hole_id, size=8.0)
    response = client.post(
        f"/designs/{shaft_id}/fit-check",
        json={"other_design_id": hole_id, "name": "shaft_hole", "samples": 500},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == shaft_id
    assert data["other_design_id"] == hole_id
    report = data["report"]
    assert report["classification"] in ("clearance", "transition", "interference")


def test_classify_domain_endpoint():
    from ai_cad.domain import DomainPrediction

    with mock.patch(
        "web.backend.main.classify_domain",
        return_value=DomainPrediction(
            primary="aero",
            scores={"mechanical": 0.0, "aero": 1.0, "thermal": 0.0, "electronics": 0.0, "humanoid": 0.0},
            reasoning="keyword",
            multi_domain=False,
        ),
    ):
        response = client.post("/classify-domain", json={"prompt": "NACA 2412 airfoil"})
    assert response.status_code == 200
    data = response.json()
    assert data["primary"] == "aero"


def test_generate_with_domain_detection(tmp_path: Path, monkeypatch):
    from ai_cad.domain import DomainPrediction

    monkeypatch.setenv("ROBOCAD_DESIGNS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "ai_cad.intent_parser._llm_extract",
        lambda p, d: {
            "parameters": [{"name": "chord", "value": 200.0, "unit": "mm"}],
            "features": [{"type": "airfoil", "id": "af1"}],
            "constraints": [],
            "notes": [],
            "confidence": 0.9,
        },
    )
    monkeypatch.setattr(
        "web.backend.main.classify_domain",
        lambda p: DomainPrediction(
            primary="aero",
            scores={"mechanical": 0.0, "aero": 1.0, "thermal": 0.0, "electronics": 0.0, "humanoid": 0.0},
            reasoning="keyword",
            multi_domain=False,
        ),
    )

    stl_path = tmp_path / "model.stl"
    stl_path.write_text("fake stl")
    backend = RoboCADBackendStub(
        api_key="fake-key",
        result=make_generation_result(
            prompt="NACA 2412 airfoil",
            success=True,
            code="",
            parameters=[],
            exports={"stl": str(stl_path), "step": None, "script": None},
        ),
    )
    with mock.patch("web.backend.main.backend", backend):
        response = client.post("/generate", json={"prompt": "NACA 2412 airfoil", "detect_domain": True, "max_retries": 0})

    assert response.status_code == 200
    data = response.json()
    assert data.get("domain") == "aero"
    assert (main_module.DESIGNS_DIR / data["design_id"] / "domain_intent.json").exists()


def test_decompose_endpoint(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ROBOCAD_DESIGNS_DIR", str(tmp_path))
    response = client.post("/decompose", json={"prompt": "450 mm quadcopter with four motor arms"})
    assert response.status_code == 200
    data = response.json()
    assert data["primary_domain"] == "mechanical"
    assert data["multi_domain"] is True
    ids = {p["id"] for p in data["parts"]}
    assert "frame_hub" in ids
    assert "motor_arm" in ids
    motor_arm = next(p for p in data["parts"] if p["id"] == "motor_arm")
    assert motor_arm["count"] == 4


def test_generate_with_decompose_system_prompt(tmp_path: Path, monkeypatch):
    """A system prompt with decompose=True uses the Phase 18 composer path."""
    monkeypatch.setenv("ROBOCAD_DESIGNS_DIR", str(tmp_path))
    response = client.post(
        "/generate",
        json={"prompt": "450 mm quadcopter with four motor arms", "decompose": True, "detect_domain": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["model"] == "phase18-decomposer"
    assert data.get("decomposition") is not None
    assert data["decomposition"]["primary_domain"] == "mechanical"

    design_dir = main_module.DESIGNS_DIR / data["design_id"]
    assert (design_dir / "decomposition.json").exists()
    assert (design_dir / "feature_tree.json").exists()
    assert (design_dir / "code.py").exists()


def test_generate_with_decompose_false_uses_backend(tmp_path: Path, monkeypatch):
    """A system prompt with decompose=False falls back to the normal LLM backend."""
    monkeypatch.setenv("ROBOCAD_DESIGNS_DIR", str(tmp_path))
    stl_path = tmp_path / "model.stl"
    stl_path.write_text("fake stl")
    backend = RoboCADBackendStub(
        api_key="fake-key",
        result=make_generation_result(
            prompt="450 mm quadcopter with four motor arms",
            success=True,
            code="",
            parameters=[],
            exports={"stl": str(stl_path), "step": None, "script": None},
        ),
    )
    with mock.patch("web.backend.main.backend", backend):
        response = client.post(
            "/generate",
            json={"prompt": "450 mm quadcopter with four motor arms", "decompose": False, "max_retries": 0},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "fake-model"
    assert data.get("decomposition") is None


def test_assembly_poses_endpoint(tmp_path: Path):
    """GET /designs/{id}/assembly-poses returns sampled poses."""
    design_id = _hex_id("p")
    design_dir = tmp_path / "designs" / design_id
    design_dir.mkdir(parents=True)
    tree = {
        "schema_version": "2.0.0",
        "design_id": design_id,
        "prompt": "test arm",
        "parts": [],
        "assemblies": [
            {
                "id": "asm",
                "instances": [
                    {"id": "base", "part_id": "base"},
                    {"id": "arm", "part_id": "arm", "transform": {"translation": [100, 0, 0]}},
                ],
                "joints": [
                    {
                        "id": "j1",
                        "type": "revolute",
                        "parent_link": "base",
                        "child_link": "arm",
                        "origin": [0, 0, 0],
                        "axis": [0, 0, 1],
                        "limits": [-90, 90],
                    }
                ],
            }
        ],
    }
    (design_dir / "feature_tree.json").write_text(json.dumps(tree))
    response = client.get(f"/designs/{design_id}/assembly-poses?samples_per_joint=4")
    assert response.status_code == 200
    data = response.json()
    assert data["joint_count"] == 1
    assert len(data["frames"]) == 4


def test_assembly_collision_endpoint(tmp_path: Path):
    """POST /designs/{id}/assembly-collision returns pairwise clearance report."""
    design_id = _hex_id("x")
    design_dir, _ = _seed_feature_tree_design(tmp_path, design_id)
    response = client.post(f"/designs/{design_id}/assembly-collision")
    assert response.status_code == 200
    data = response.json()
    assert data["pair_count"] == 1
    assert data["worst"]["classification"] == "clearance"


def test_simulate_endpoint_stl_fallback(tmp_path: Path):
    design_id = _hex_id("m")
    design_dir, stl_path = _seed_cube_design(tmp_path, design_id, size=10.0)
    response = client.post(f"/designs/{design_id}/simulate", json={"material": "PLA", "tolerance": 0.1})
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == design_id
    assert data["valid"] is True
    assert data["bundle_url"].startswith(f"/exports/{design_id}/simulation/bundle.zip")


def test_get_simulation_report_endpoint(tmp_path: Path):
    design_id = _hex_id("n")
    _seed_cube_design(tmp_path, design_id, size=10.0)
    response = client.post(f"/designs/{design_id}/simulate", json={"material": "PLA"})
    assert response.status_code == 200

    response = client.get(f"/designs/{design_id}/simulation")
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == design_id
    assert "manifest" in data
    assert "verification" in data


def test_download_bundle_endpoint(tmp_path: Path):
    design_id = _hex_id("o")
    _seed_cube_design(tmp_path, design_id, size=10.0)
    response = client.post(f"/designs/{design_id}/simulate", json={"material": "PLA"})
    assert response.status_code == 200

    response = client.get(f"/designs/{design_id}/bundle")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert len(response.content) > 0


def test_compose_scene_endpoint(tmp_path: Path):
    pytest.importorskip("mujoco")
    design_id = _hex_id("q")
    _seed_cube_design(tmp_path, design_id, size=10.0)
    response = client.post(
        f"/designs/{design_id}/scene",
        json={"template": "gripper_cube_grasp", "material": "PLA", "tolerance": 0.1},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["design_id"] == design_id
    assert data["template"] == "gripper_cube_grasp"
    assert data["runtime_ok"] is True
    assert data["scene_url"].startswith(f"/exports/{design_id}/simulation/scene_gripper_cube_grasp.mjcf")


def test_get_scene_report_endpoint(tmp_path: Path):
    pytest.importorskip("mujoco")
    design_id = _hex_id("r")
    _seed_cube_design(tmp_path, design_id, size=10.0)
    response = client.post(f"/designs/{design_id}/scene", json={"template": "wedge_push_block"})
    assert response.status_code == 200

    response = client.get(f"/designs/{design_id}/scene?template=wedge_push_block")
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == design_id
    assert data["template"] == "wedge_push_block"
    assert "scene" in data


def test_capabilities_endpoint():
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["bundle_schema_version"] == "2.0.0"
    assert "wedge_push_block" in data["supported_scene_templates"]
    assert "GET /capabilities" in data["endpoints"].values()


def test_handshake_endpoint(tmp_path: Path):
    pytest.importorskip("mujoco")
    design_id = _hex_id("w")
    _seed_wedge_design(tmp_path, design_id)
    response = client.post(f"/designs/{design_id}/handshake", params={"template": "wedge_push_block"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["design_id"] == design_id
    assert data["template"] == "wedge_push_block"
    assert data["success"] is True, data
    assert "rollout" in data
    assert data["rollout"]["steps"] == 5000
    assert data["nbody"] >= 3


def test_get_handshake_report_endpoint(tmp_path: Path):
    pytest.importorskip("mujoco")
    design_id = _hex_id("v")
    _seed_wedge_design(tmp_path, design_id)
    response = client.post(f"/designs/{design_id}/handshake", params={"template": "wedge_push_block"})
    assert response.status_code == 200

    response = client.get(f"/designs/{design_id}/handshake?template=wedge_push_block")
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == design_id
    assert data["template"] == "wedge_push_block"
    assert "handshake" in data
    assert data["handshake"]["success"] is True, data["handshake"]
    assert "rollout" in data["handshake"]


def test_recommend_skill_endpoint(tmp_path: Path):
    design_id = _hex_id("u")
    _seed_wedge_design(tmp_path, design_id)
    response = client.post(f"/designs/{design_id}/recommend-skill", json={"skill_description": "push the block to the goal"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["design_id"] == design_id
    assert data["template"] == "wedge_push_block"
    assert data["confidence"] > 0.0


def test_train_skill_endpoint(tmp_path: Path):
    pytest.importorskip("mujoco")
    design_id = _hex_id("t")
    _seed_wedge_design(tmp_path, design_id)
    response = client.post(
        f"/designs/{design_id}/train-skill",
        json={"skill_description": "push the block", "n_iters": 5, "pop_size": 10, "eval_episodes": 3},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["design_id"] == design_id
    assert "success_rate" in data
    assert "weights" in data
    assert "policy_file" in data


def test_list_skills_endpoint(tmp_path: Path):
    design_id = _hex_id("l")
    _seed_wedge_design(tmp_path, design_id)
    client.post(f"/designs/{design_id}/recommend-skill", json={"skill_description": "push the block"})
    response = client.get(f"/designs/{design_id}/skills")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["design_id"] == design_id
    assert "recommended_skills" in data


def test_variant_sweep_endpoint(tmp_path: Path):
    design_id = _hex_id("g")
    design_dir = tmp_path / "designs" / design_id
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True)
    stl_path = exports_dir / "model.stl"
    stl_path.write_text(_ascii_cube_stl(10.0))

    feature_tree = {
        "schema_version": "1.0.0",
        "design_id": design_id,
        "prompt": "a cube",
        "created_at": "2026-08-25T00:00:00Z",
        "units": "mm",
        "parameters": [
            {"name": "size", "value": 10.0, "default_value": 10.0, "unit": "mm", "description": "side length"}
        ],
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
        "id": design_id,
        "prompt": "a cube",
        "success": True,
        "model": "fake",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "created_at": "2026-08-25T00:00:00Z",
        "exports": {"stl": "model.stl", "step": None, "script": None},
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata))

    response = client.post(
        f"/designs/{design_id}/variant-sweep",
        json={"parameter_ranges": {"size": {"relative_min": -0.1, "relative_max": 0.1}}, "n_variants": 3, "run_stability": False},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True, data
    assert len(data["variants"]) == 3
    assert data["aggregate"]["n_variants"] == 3


def test_simulate_endpoint_with_feature_tree(tmp_path: Path):
    design_id = _hex_id("i")
    design_dir = tmp_path / "designs" / design_id
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True)
    stl_path = exports_dir / "model.stl"
    stl_path.write_text(_ascii_cube_stl(10.0))

    feature_tree = {
        "schema_version": "1.0.0",
        "design_id": design_id,
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
        "id": design_id,
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

    response = client.post(f"/designs/{design_id}/simulate", json={"material": "PLA", "tolerance": 0.1})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["design_id"] == design_id
    assert data["valid"] is True
    manifest = data["manifest"]
    assert len(manifest["parts"]) == 1
    assert manifest["parts"][0]["material"] == "PLA"


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


def _seed_wedge_design(
    tmp_path: Path,
    design_id: str,
    length_mm: float = 80.0,
    width_mm: float = 40.0,
    height_mm: float = 60.0,
):
    """Create a persisted design with a real outward-facing triangular-prism wedge STL (mm)."""
    design_dir = tmp_path / "designs" / design_id
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True)
    stl_path = exports_dir / "model.stl"

    L, W, H = length_mm, width_mm, height_mm
    verts = np.array(
        [
            [L / 2, -W / 2, -H / 2],  # 0 tip bottom
            [-L / 2, -W / 2, -H / 2],  # 1 back bottom
            [-L / 2, -W / 2, H / 2],  # 2 back top
            [L / 2, W / 2, -H / 2],  # 3 tip bottom (right side)
            [-L / 2, W / 2, -H / 2],  # 4 back bottom
            [-L / 2, W / 2, H / 2],  # 5 back top
        ],
        dtype=float,
    )
    faces = np.array(
        [
            [0, 1, 2],  # left end cap
            [3, 5, 4],  # right end cap
            [0, 3, 4],
            [0, 4, 1],  # bottom
            [1, 4, 5],
            [1, 5, 2],  # back vertical face
            [0, 2, 5],
            [0, 5, 3],  # slanted top face
        ]
    )
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    if mesh.volume < 0:
        mesh.invert()
    mesh.export(stl_path)

    metadata = {
        "id": design_id,
        "prompt": "a wedge pusher",
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


def _seed_feature_tree_design(tmp_path: Path, design_id: str):
    """Create a persisted design whose feature tree has two separated cubes."""
    cube = Part(
        id="cube",
        sketches=[
            Sketch(
                id="profile",
                plane=PlaneReference(type="base", name="XY"),
                entities=[
                    SketchEntity(type="rectangle", id="base", center=(0, 0), width=10, height=10)
                ],
            )
        ],
        features=[
            Feature(id="extrude1", type="extrude", sketch_id="profile", parameters={"amount": 10, "mode": "add"})
        ],
    )
    tree = FeatureTree(
        design_id=design_id,
        prompt="two cubes",
        parts=[cube],
        assemblies=[
            Assembly(
                id="asm",
                instances=[
                    Instance(id="i1", part_id="cube"),
                    Instance(id="i2", part_id="cube", transform={"translation": [20, 0, 0]}),
                ],
            )
        ],
    )

    design_dir = tmp_path / "designs" / design_id
    design_dir.mkdir(parents=True)
    (design_dir / "feature_tree.json").write_text(json.dumps(tree.model_dump(mode="json")))
    return design_dir, None


def _ascii_cube_stl(size: float) -> str:
    """Return a minimal valid ASCII STL for a centered cube."""
    half = size / 2
    vertices = [
        (-half, -half, -half),
        (half, -half, -half),
        (half, half, -half),
        (-half, half, -half),
        (-half, -half, half),
        (half, -half, half),
        (half, half, half),
        (-half, half, half),
    ]
    faces = [
        (0, 2, 1),
        (0, 3, 2),
        (4, 5, 6),
        (4, 6, 7),
        (0, 1, 5),
        (0, 5, 4),
        (1, 2, 6),
        (1, 6, 5),
        (2, 3, 7),
        (2, 7, 6),
        (3, 0, 4),
        (3, 4, 7),
    ]
    lines = ["solid cube"]
    for face in faces:
        lines.append("  facet normal 0 0 0")
        lines.append("    outer loop")
        for vi in face:
            v = vertices[vi]
            lines.append(f"      vertex {v[0]} {v[1]} {v[2]}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid cube")
    return "\n".join(lines)


def _seed_step_design(design_id: str) -> Path:
    """Create a persisted design with a dummy STEP export file."""
    design_dir = main_module.DESIGNS_DIR / design_id
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True)
    step_path = exports_dir / "model.step"
    step_path.write_text("ISO-10303-21; dummy STEP content", encoding="utf-8")
    metadata = {
        "id": design_id,
        "prompt": "a cube",
        "success": True,
        "model": "fake",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "created_at": "2026-08-25T00:00:00Z",
        "exports": {"step": "model.step", "stl": None, "script": None},
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return step_path


def test_onshape_upload_requires_existing_document(monkeypatch):
    """RoboCAD refuses to auto-create Onshape documents; an existing doc/workspace is required."""
    from ai_cad.onshape import OnshapeClient

    design_id = _hex_id("on")
    _seed_step_design(design_id)

    uploaded: list[tuple[Path, str, str]] = []

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def upload_step(self, step_path: Path, document_id: str, workspace_id: str) -> dict[str, Any]:
            uploaded.append((step_path, document_id, workspace_id))
            return {"document_id": document_id, "workspace_id": workspace_id}

    monkeypatch.setattr(main_module, "OnshapeClient", FakeClient)

    # Missing document_id/workspace_id should be rejected before any network call.
    missing_resp = client.post(
        f"/designs/{design_id}/onshape",
        json={},
    )
    assert missing_resp.status_code == 422
    detail = str(missing_resp.json())
    assert "document_id" in detail.lower() and "workspace_id" in detail.lower()

    # Supplying both ids succeeds.
    success_resp = client.post(
        f"/designs/{design_id}/onshape",
        json={"document_id": "doc_123", "workspace_id": "ws_456"},
    )
    assert success_resp.status_code == 200
    data = success_resp.json()
    assert data["design_id"] == design_id
    assert data["onshape"]["document_id"] == "doc_123"
    assert len(uploaded) == 1
    assert uploaded[0][1] == "doc_123"
    assert uploaded[0][2] == "ws_456"
