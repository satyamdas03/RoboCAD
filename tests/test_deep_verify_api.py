"""Tests for the Phase 28C deep-analysis backend endpoints.

All heavy solver work is mocked so the suite exercises the HTTP wiring, request
validation, and response shape without running external solvers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.solvers.job_store import JobStatus, VerificationJob
from ai_cad.verification_models import LoadCase
from web.backend import main as main_module
from web.backend.main import app

client = TestClient(app)


def _metadata(design_id: str) -> dict:
    return {
        "id": design_id,
        "prompt": "deep analysis test design",
        "success": True,
        "model": "fake",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "created_at": "2026-09-01T00:00:00Z",
        "exports": {},
    }


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
def fake_design(tmp_path: Path):
    """Create a persisted design with only metadata (no mesh required for mocks)."""
    design_id = "deep123"
    design_dir = tmp_path / "designs" / design_id
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "metadata.json").write_text(json.dumps(_metadata(design_id)))
    return design_id


def _completed_job(design_id: str, job_id: str, passed: bool = True) -> VerificationJob:
    return VerificationJob(
        job_id=job_id,
        design_id=design_id,
        load_case=LoadCase.STATIC_STRESS,
        solver_type="calculix",
        status=JobStatus.COMPLETED,
        progress=1.0,
        result={"overall_passed": passed, "metrics": {"max_stress_mpa": 12.0}},
        created_at=0.0,
        updated_at=0.0,
    )


def test_deep_verify_start_and_poll(fake_design: str, monkeypatch: pytest.MonkeyPatch):
    """POST starts a job and GET returns its polled status."""
    job_id = "job123"

    def fake_submit(request, design_dir=None, job_store=None):
        assert request.design_id == fake_design
        assert request.load_case == LoadCase.STATIC_STRESS
        assert request.parameters["solver"] == "calculix"
        return job_id

    def fake_poll(jid, job_store=None):
        if jid == job_id:
            return _completed_job(fake_design, job_id, passed=True)
        return None

    monkeypatch.setattr(main_module, "submit_deep_verification", fake_submit)
    monkeypatch.setattr(main_module, "poll_deep_verification", fake_poll)

    response = client.post(
        f"/designs/{fake_design}/deep-verify",
        json={
            "load_case": "static_stress",
            "solver": "calculix",
            "parameters": {"load_magnitude_n": 50},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == fake_design
    assert data["job_id"] == job_id
    assert data["status"] == "queued"

    get_response = client.get(f"/designs/{fake_design}/deep-verify/{job_id}")
    assert get_response.status_code == 200
    job = get_response.json()["job"]
    assert job["job_id"] == job_id
    assert job["status"] == "completed"
    assert job["result"]["overall_passed"] is True


def test_deep_verify_routing_without_solver_override(fake_design: str, monkeypatch: pytest.MonkeyPatch):
    """When no solver is requested, the dispatcher picks one from the load case."""
    job_id = "jobthermal"

    def fake_submit(request, design_dir=None, job_store=None):
        assert request.parameters.get("solver") is None
        assert request.load_case == LoadCase.HEAT_SINK_THERMAL_RESISTANCE
        return job_id

    monkeypatch.setattr(main_module, "submit_deep_verification", fake_submit)
    monkeypatch.setattr(
        main_module,
        "poll_deep_verification",
        lambda jid, job_store=None: (
            _completed_job(fake_design, job_id) if jid == job_id else None
        ),
    )

    response = client.post(
        f"/designs/{fake_design}/deep-verify",
        json={"load_case": "heat_sink_thermal_resistance", "parameters": {"heat_flux_w": 5}},
    )
    assert response.status_code == 200


def test_solver_availability(fake_design: str, monkeypatch: pytest.MonkeyPatch):
    """GET /solver-availability returns the registered solver list."""
    monkeypatch.setattr(
        main_module,
        "solver_availability",
        lambda: {
            "solvers": [
                {"name": "calculix", "available": False},
                {"name": "elmerfem", "available": False},
                {"name": "openfoam", "available": False},
                {"name": "surrogate", "available": True},
            ]
        },
    )

    response = client.get(f"/designs/{fake_design}/solver-availability")
    assert response.status_code == 200
    data = response.json()
    assert data["design_id"] == fake_design
    assert {s["name"] for s in data["solvers"]} == {"calculix", "elmerfem", "openfoam", "surrogate"}


def test_deep_verify_design_not_found():
    """Starting a deep-analysis job for a missing design returns 404."""
    response = client.post(
        "/designs/missing-design/deep-verify",
        json={"load_case": "static_stress"},
    )
    assert response.status_code == 404


def test_deep_verify_invalid_load_case(fake_design: str):
    """An unknown load case is rejected before a job is created."""
    response = client.post(
        f"/designs/{fake_design}/deep-verify",
        json={"load_case": "not_a_case"},
    )
    assert response.status_code == 400
    assert "Unsupported load case" in response.text


def test_deep_verify_status_not_found(fake_design: str, monkeypatch: pytest.MonkeyPatch):
    """Polling an unknown job id returns 404."""
    monkeypatch.setattr(main_module, "poll_deep_verification", lambda jid, job_store=None: None)
    response = client.get(f"/designs/{fake_design}/deep-verify/nosuchjob")
    assert response.status_code == 404


def test_deep_verify_status_wrong_design(fake_design: str, monkeypatch: pytest.MonkeyPatch):
    """A job belonging to another design is not accessible from this design's route."""
    monkeypatch.setattr(
        main_module,
        "poll_deep_verification",
        lambda jid, job_store=None: _completed_job("other-design", jid),
    )
    response = client.get(f"/designs/{fake_design}/deep-verify/jobother")
    assert response.status_code == 404


def test_deep_verify_cancel(fake_design: str, monkeypatch: pytest.MonkeyPatch):
    """A cancellable job returns cancelled=True."""
    job_id = "jobcancel"
    calls = {}

    def fake_poll(jid, job_store=None):
        if jid == job_id:
            return VerificationJob(
                job_id=job_id,
                design_id=fake_design,
                load_case=LoadCase.STATIC_STRESS,
                solver_type="calculix",
                status=JobStatus.PENDING,
                progress=0.0,
                created_at=0.0,
                updated_at=0.0,
            )
        return None

    def fake_cancel(jid, job_store=None):
        calls["cancelled"] = jid
        return True

    monkeypatch.setattr(main_module, "poll_deep_verification", fake_poll)
    monkeypatch.setattr(main_module, "cancel_deep_verification", fake_cancel)

    response = client.post(f"/designs/{fake_design}/deep-verify/{job_id}/cancel")
    assert response.status_code == 200
    data = response.json()
    assert data["cancelled"] is True
    assert calls["cancelled"] == job_id


def test_deep_verify_cancel_terminal_job(fake_design: str, monkeypatch: pytest.MonkeyPatch):
    """Cancelling an already-terminal job returns cancelled=False."""
    job_id = "jobterminal"

    monkeypatch.setattr(
        main_module,
        "poll_deep_verification",
        lambda jid, job_store=None: _completed_job(fake_design, jid),
    )
    monkeypatch.setattr(main_module, "cancel_deep_verification", lambda jid, job_store=None: False)

    response = client.post(f"/designs/{fake_design}/deep-verify/{job_id}/cancel")
    assert response.status_code == 200
    assert response.json()["cancelled"] is False


def test_deep_verify_cancel_missing_job(fake_design: str, monkeypatch: pytest.MonkeyPatch):
    """Cancelling an unknown job id returns 404."""
    monkeypatch.setattr(main_module, "poll_deep_verification", lambda jid, job_store=None: None)
    response = client.post(f"/designs/{fake_design}/deep-verify/nosuchjob/cancel")
    assert response.status_code == 404
