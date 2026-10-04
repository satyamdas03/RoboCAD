"""Tests for HERMES automated orchestration backend endpoints."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web.backend import main as main_module
from web.backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_designs(tmp_path: Path):
    original = main_module.DESIGNS_DIR
    test_dir = tmp_path / "designs"
    test_dir.mkdir(parents=True, exist_ok=True)
    main_module.DESIGNS_DIR = test_dir
    yield
    main_module.DESIGNS_DIR = original


@pytest.fixture(autouse=True)
def patch_auto_callables(monkeypatch):
    """Replace slow backend callables with fast deterministic mocks."""

    def classify(prompt: str) -> dict:
        if "humanoid" in prompt or "biped" in prompt:
            return {"primary": "humanoid"}
        if any(word in prompt for word in ("quadruped", "dog", "trot")):
            return {"primary": "quadruped"}
        return {"primary": "mechanical"}

    search_calls: list[dict] = []

    def run_morphology_search(request) -> dict:
        search_calls.append({"template": request.template, "end_effectors": request.end_effectors})
        return {
            "search_id": "search_auto_001",
            "candidates": [
                {"candidate_id": "cand_auto_001", "composite_score": 0.88},
                {"candidate_id": "cand_auto_002", "composite_score": 0.82},
            ],
        }

    brain_calls: list[tuple[str, str]] = []

    def simulate_morphology_candidate(search_id: str, candidate_id: str, request) -> dict:
        brain_calls.append((search_id, candidate_id))
        return {"success": True, "search_id": search_id, "candidate_id": candidate_id}

    cert_calls: list[str] = []

    def sim_cert_run(design_id: str) -> dict:
        cert_calls.append(design_id)
        return {
            "certificate": {
                "cert_id": "cert_auto_001",
                "design_id": design_id,
                "score": 88.0,
                "passed": True,
                "checks": [],
            }
        }

    monkeypatch.setattr(main_module, "_classify_domain_safe", classify)
    monkeypatch.setattr(main_module, "run_morphology_search", run_morphology_search)
    monkeypatch.setattr(main_module, "simulate_morphology_candidate", simulate_morphology_candidate)
    monkeypatch.setattr(main_module, "sim_cert_run", sim_cert_run)
    yield


def test_hermes_auto_endpoint_happy_path(patch_auto_callables):
    created = client.post("/hermes/session", json={}).json()
    session_id = created["session_id"]

    response = client.post(
        f"/hermes/session/{session_id}/auto",
        json={
            "prompt": "a biped humanoid robot",
            "max_retries": 1,
            "cert_threshold": 0.75,
            "timeout_seconds": 30.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "certified"
    assert data["search_id"] == "search_auto_001"
    assert data["candidate_id"] == "cand_auto_001"
    assert data["certificate"]["passed"] is True
    assert data["certificate"]["score"] >= 75.0
    assert len(data["audit"]) == 1
    assert data["audit"][0]["passed"] is True

    # Audit endpoint should return the same trail.
    audit_resp = client.get(f"/hermes/session/{session_id}/audit")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["status"] == "certified"
    assert len(audit_data["audit"]) == 1
    assert audit_data["audit"][0]["search_id"] == "search_auto_001"


def test_hermes_auto_endpoint_retry_then_certify(patch_auto_callables, monkeypatch):
    created = client.post("/hermes/session", json={}).json()
    session_id = created["session_id"]

    cert_attempts: list[str] = []

    def sim_cert_run_retry(design_id: str) -> dict:
        cert_attempts.append(design_id)
        score = 55.0 if len(cert_attempts) == 1 else 85.0
        return {
            "certificate": {
                "cert_id": f"cert_{len(cert_attempts)}",
                "design_id": design_id,
                "score": score,
                "passed": score >= 75.0,
                "checks": [],
            }
        }

    monkeypatch.setattr(main_module, "sim_cert_run", sim_cert_run_retry)

    response = client.post(
        f"/hermes/session/{session_id}/auto",
        json={
            "prompt": "a humanoid robot",
            "max_retries": 2,
            "cert_threshold": 0.75,
            "timeout_seconds": 30.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "certified"
    assert len(data["audit"]) == 2
    assert data["audit"][0]["passed"] is False
    assert data["audit"][1]["passed"] is True


def test_hermes_auto_endpoint_non_robot_uses_generate(patch_auto_callables, monkeypatch):
    created = client.post("/hermes/session", json={}).json()
    session_id = created["session_id"]

    generated: list[str] = []

    def mock_generate(request) -> main_module.GenerateResponse:
        generated.append(request.prompt)
        return main_module.GenerateResponse(prompt=request.prompt, design_id="cube_auto_001", success=True)

    monkeypatch.setattr(main_module, "generate", mock_generate)

    response = client.post(
        f"/hermes/session/{session_id}/auto",
        json={
            "prompt": "a cube",
            "max_retries": 1,
            "cert_threshold": 0.75,
            "timeout_seconds": 30.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "certified"
    assert data["design_id"] == "cube_auto_001"
    assert data["search_id"] is None
    assert data["candidate_id"] is None
    assert generated == ["a cube"]
    assert len(data["audit"]) == 1
