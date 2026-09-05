"""Tests for HERMES FastAPI backend endpoints."""
from __future__ import annotations

import json
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
    """Use a temporary designs directory for every test."""
    original = main_module.DESIGNS_DIR
    test_dir = tmp_path / "designs"
    test_dir.mkdir(parents=True, exist_ok=True)
    main_module.DESIGNS_DIR = test_dir
    yield
    main_module.DESIGNS_DIR = original


# -----------------------------------------------------------------------------
# Session endpoints
# -----------------------------------------------------------------------------

def test_create_hermes_session():
    response = client.post("/hermes/session", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"].startswith("hermes_")
    assert data["status"] == "idle"


def test_create_hermes_session_with_design():
    response = client.post("/hermes/session", json={"design_id": "d123"})
    data = response.json()
    assert data["design_id"] == "d123"


def test_get_hermes_session():
    created = client.post("/hermes/session", json={}).json()
    session_id = created["session_id"]
    response = client.get(f"/hermes/session/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["status"] == "idle"
    assert data["active_plan"] is None


def test_get_hermes_session_not_found():
    response = client.get("/hermes/session/hermes_nonexistent")
    assert response.status_code == 404


# -----------------------------------------------------------------------------
# Messaging
# -----------------------------------------------------------------------------

def test_hermes_message_explain():
    created = client.post("/hermes/session", json={}).json()
    session_id = created["session_id"]
    response = client.post(f"/hermes/session/{session_id}/message", json={
        "session_id": session_id,
        "message": "explain the last failure",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["reply"]
    assert data["status"] == "done"


def test_hermes_message_train_requires_approval():
    created = client.post("/hermes/session", json={}).json()
    session_id = created["session_id"]
    response = client.post(f"/hermes/session/{session_id}/message", json={
        "session_id": session_id,
        "message": "train a brain",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "awaiting_approval"
    assert len(data["pending_approvals"]) == 1
    assert data["pending_approvals"][0]["tool"] == "train_brain"


def test_hermes_approve_and_continue():
    created = client.post("/hermes/session", json={}).json()
    session_id = created["session_id"]
    client.post(f"/hermes/session/{session_id}/message", json={
        "session_id": session_id,
        "message": "train a brain",
    })
    step = client.get(f"/hermes/session/{session_id}/status").json()["pending_approvals"][0]
    response = client.post(f"/hermes/session/{session_id}/approve", json={
        "session_id": session_id,
        "step_id": step["step_id"],
        "approved": True,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert len(data["results"]) >= 1


def test_hermes_reject_step():
    created = client.post("/hermes/session", json={}).json()
    session_id = created["session_id"]
    client.post(f"/hermes/session/{session_id}/message", json={
        "session_id": session_id,
        "message": "train a brain",
    })
    step = client.get(f"/hermes/session/{session_id}/status").json()["pending_approvals"][0]
    response = client.post(f"/hermes/session/{session_id}/approve", json={
        "session_id": session_id,
        "step_id": step["step_id"],
        "approved": False,
        "reason": "too expensive",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["step"]["status"] == "rejected"


# -----------------------------------------------------------------------------
# Explain endpoint
# -----------------------------------------------------------------------------

def test_hermes_explain_brain():
    created = client.post("/hermes/session", json={}).json()
    session_id = created["session_id"]
    response = client.post(f"/hermes/session/{session_id}/explain", json={
        "session_id": session_id,
        "target": "brain",
    })
    assert response.status_code == 200
    data = response.json()
    assert "explanation" in data
    assert data["target"] == "brain"


# -----------------------------------------------------------------------------
# Status endpoint
# -----------------------------------------------------------------------------

def test_hermes_status():
    created = client.post("/hermes/session", json={}).json()
    session_id = created["session_id"]
    response = client.get(f"/hermes/session/{session_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["status"] == "idle"
    assert data["pending_approvals"] == []
