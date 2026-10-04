"""Tests for the HERMES auto-orchestrator."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.hermes.orchestrator import _certificate_passed, run_auto_orchestration
from ai_cad.hermes.session import HermesSession
from ai_cad.hermes.tools import HermesToolRegistry


@pytest.fixture
def tmp_designs(tmp_path):
    return tmp_path / "designs"


def _passing_certificate(score: float = 0.85) -> dict:
    return {
        "cert_id": "cert_123",
        "design_id": "search_123",
        "score": score * 100,
        "passed": score >= 0.75,
        "checks": [],
    }


def test_auto_orchestrator_happy_path_morphology(tmp_designs):
    wrapper = HermesSession.create(base_dir=tmp_designs)

    def morph_search(**kw):
        return {
            "search_id": "search_123",
            "candidates": [{"candidate_id": "cand_001", "composite_score": 0.9}],
        }

    def brain_train(search_id, candidate_id, **kw):
        return {"success": True, "search_id": search_id, "candidate_id": candidate_id}

    def cert(design_id, **kw):
        return {"certificate": _passing_certificate(0.85)}

    context = {
        "classify_domain": lambda p: {"primary": "humanoid"},
        "run_morphology_search": morph_search,
        "train_robot_brain_on_candidate": brain_train,
        "run_simulation_certification": cert,
        "generate_design": lambda **kw: {"design_id": "gen_123"},
        "propose_redesign": lambda **kw: {"parameter_updates": {}},
        "regenerate_parameters": lambda **kw: {"success": True},
    }

    result = run_auto_orchestration(
        session=wrapper,
        prompt="a humanoid robot",
        registry=HermesToolRegistry(),
        context=context,
        max_retries=1,
        cert_threshold=0.7,
        timeout_seconds=60.0,
    )

    assert result["success"] is True
    assert result["search_id"] == "search_123"
    assert result["candidate_id"] == "cand_001"
    assert result["certificate"] is not None
    assert len(result["audit"]) == 1
    assert result["audit"][0]["passed"] is True


def test_auto_orchestrator_retry_then_pass(tmp_designs):
    wrapper = HermesSession.create(base_dir=tmp_designs)

    attempts = []

    def morph_search(**kw):
        attempts.append(kw.get("template"))
        if len(attempts) == 1:
            return {"search_id": "search_001", "candidates": []}
        return {
            "search_id": "search_002",
            "candidates": [{"candidate_id": "cand_002", "composite_score": 0.92}],
        }

    def brain_train(search_id, candidate_id, **kw):
        return {"success": True, "search_id": search_id, "candidate_id": candidate_id}

    cert_calls = []

    def cert(design_id, **kw):
        cert_calls.append(design_id)
        if len(cert_calls) == 1:
            return {"certificate": _passing_certificate(0.5)}
        return {"certificate": _passing_certificate(0.9)}

    context = {
        "classify_domain": lambda p: {"primary": "humanoid"},
        "run_morphology_search": morph_search,
        "train_robot_brain_on_candidate": brain_train,
        "run_simulation_certification": cert,
        "generate_design": lambda **kw: {"design_id": "gen_123"},
        "propose_redesign": lambda **kw: {"parameter_updates": {}},
        "regenerate_parameters": lambda **kw: {"success": True},
    }

    result = run_auto_orchestration(
        session=wrapper,
        prompt="a humanoid robot",
        registry=HermesToolRegistry(),
        context=context,
        max_retries=2,
        cert_threshold=0.7,
        timeout_seconds=60.0,
    )

    assert result["success"] is True
    assert result["search_id"] == "search_002"
    assert result["candidate_id"] == "cand_002"
    assert len(result["audit"]) == 2
    assert result["audit"][0]["passed"] is False
    assert result["audit"][1]["passed"] is True


def test_auto_orchestrator_non_robot_uses_generate(tmp_designs):
    wrapper = HermesSession.create(base_dir=tmp_designs)

    generated = []

    def generate(**kw):
        generated.append(kw.get("prompt"))
        return {"design_id": "cube_123"}

    def cert(design_id, **kw):
        return {"certificate": _passing_certificate(0.8)}

    context = {
        "classify_domain": lambda p: {"primary": "mechanical"},
        "run_morphology_search": lambda **kw: {"search_id": "search_x", "candidates": []},
        "train_robot_brain_on_candidate": lambda **kw: {"success": True},
        "run_simulation_certification": cert,
        "generate_design": generate,
        "propose_redesign": lambda **kw: {"parameter_updates": {}},
        "regenerate_parameters": lambda **kw: {"success": True},
    }

    result = run_auto_orchestration(
        session=wrapper,
        prompt="a cube",
        registry=HermesToolRegistry(),
        context=context,
        max_retries=1,
        cert_threshold=0.7,
        timeout_seconds=60.0,
    )

    assert result["success"] is True
    assert result["design_id"] == "cube_123"
    assert result["search_id"] is None
    assert result["candidate_id"] is None
    assert generated == ["a cube"]
    assert len(result["audit"]) == 1


def test_certificate_passed_skips_robot_checks_when_skipped():
    cert = {
        "passed": False,
        "score": 50.0,
        "checks": [
            {
                "name": "robot_randomized_world_certification",
                "passed": True,
                "details": {"skipped": True},
            }
        ],
    }
    assert _certificate_passed(cert, 0.7) is False


def test_certificate_passed_required_robot_checks_bypass_threshold():
    cert = {
        "passed": False,
        "score": 50.0,
        "checks": [
            {"name": "terrain_walking", "passed": True, "details": {}},
            {"name": "push_recovery", "passed": True, "details": {}},
            {"name": "actuator_saturation", "passed": True, "details": {}},
        ],
    }
    assert _certificate_passed(cert, 0.7) is True
