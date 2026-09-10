"""Tests for Phase 28D morphology co-design backend endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web.backend.main as main_module
from web.backend.main import app

client = TestClient(app)


@pytest.fixture
def search_dir(monkeypatch, tmp_path):
    """Point the backend's design storage at a temp directory for isolation."""
    monkeypatch.setattr(main_module, "DESIGNS_DIR", tmp_path)
    return tmp_path


def test_list_morphology_templates():
    resp = client.get("/morphology/templates")
    assert resp.status_code == 200
    data = resp.json()
    names = {t["name"] for t in data["templates"]}
    assert names == {"humanoid", "quadruped", "manipulator_on_base"}
    for t in data["templates"]:
        assert "dimensions" in t
        assert "n_max" in t


def test_run_morphology_search(search_dir):
    resp = client.post(
        "/morphology/search",
        json={
            "template": "quadruped",
            "n_max": 4,
            "seed": 0,
            "payload_kg": 2.0,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "search_id" in data
    assert data["template"] == "quadruped"
    assert data["n_candidates"] == 4
    assert len(data["candidates"]) == 4
    assert data["candidates"][0]["rank"] == 1
    # Persisted file exists.
    assert (search_dir / data["search_id"] / f"morphology_search_{data['search_id']}.json").exists()


def test_get_morphology_search(search_dir):
    search_resp = client.post(
        "/morphology/search",
        json={"template": "manipulator_on_base", "n_max": 4, "seed": 1},
    )
    search_id = search_resp.json()["search_id"]

    resp = client.get(f"/morphology/{search_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["search_id"] == search_id
    assert data["template"] == "manipulator_on_base"
    assert data["n_candidates"] == 4


def test_get_missing_morphology_search(search_dir):
    resp = client.get("/morphology/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.slow
def test_simulate_morphology_candidate(search_dir):
    search_resp = client.post(
        "/morphology/search",
        json={"template": "humanoid", "n_max": 4, "seed": 2, "payload_kg": 1.0},
    )
    assert search_resp.status_code == 200, search_resp.text
    search_data = search_resp.json()
    search_id = search_data["search_id"]
    candidate_id = search_data["candidates"][0]["candidate_id"]

    resp = client.post(
        f"/morphology/{search_id}/candidates/{candidate_id}/simulate",
        json={
            "world_template": "walker",
            "n_iters": 3,
            "pop_size": 10,
            "eval_episodes": 1,
            "seed": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["search_id"] == search_id
    assert data["candidate_id"] == candidate_id
    assert "brain_smoke_test" in data
    smoke = data["brain_smoke_test"]
    assert "success_rate" in smoke
    assert "mean_reward" in smoke
    assert "best_training_reward" in smoke
