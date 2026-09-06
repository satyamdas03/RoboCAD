"""End-to-end HERMES integration tests with a mocked LLM."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.hermes.llm import deterministic_mock_caller
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


def _seed_design(designs_dir: Path, design_id: str) -> None:
    design_dir = designs_dir / design_id
    design_dir.mkdir()
    metadata = {
        "id": design_id,
        "prompt": "robot base plate",
        "domain": "mechanical",
        "success": True,
        "model": "test",
        "created_at": "2026-09-01T00:00:00Z",
        "dfm_report": {
            "pass": False,
            "issues": [{"severity": "error", "message": "Wall too thin"}],
            "metrics": {"min_wall_mm": 1.0},
        },
        "parameters": [{"name": "thickness", "value": 3.0, "description": "plate thickness"}],
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (design_dir / "parameters.json").write_text(json.dumps(metadata["parameters"]), encoding="utf-8")


def test_hermes_dfm_explain_redesign_regenerate_loop(clean_designs):
    designs_dir = main_module.DESIGNS_DIR
    design_id = "dplate"
    _seed_design(designs_dir, design_id)

    # Create session bound to the design.
    created = client.post("/hermes/session", json={"design_id": design_id}).json()
    session_id = created["session_id"]

    # Mock LLM responds with a plan: explain DFM, propose redesign, regenerate.
    mock_response = json.dumps(
        {
            "plan": {
                "goal": "Fix thin wall",
                "steps": [
                    {
                        "description": "Explain DFM failure",
                        "tool": "explain_last_failure",
                        "parameters": {"target": "dfm"},
                    },
                    {
                        "description": "Propose redesign",
                        "tool": "propose_redesign",
                        "parameters": {"goal": "thicken the plate", "target": "dfm"},
                        "depends_on": [],
                    },
                    {
                        "description": "Regenerate with thicker plate",
                        "tool": "regenerate_parameters",
                        "parameters": {"parameter_updates": {"thickness": 4.0}},
                        "depends_on": [],
                    },
                ],
            }
        }
    )

    # Patch the LLM caller on the module so the agent uses the mock.
    main_module.build_llm_caller = lambda model=None, api_key=None: deterministic_mock_caller(mock_response)

    response = client.post(f"/hermes/session/{session_id}/message", json={
        "session_id": session_id,
        "message": "My plate is too thin. Fix it.",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "awaiting_approval"

    # Approve the regeneration step.
    plan = data["active_plan"]
    regenerate_step = next(s for s in plan["steps"] if s["tool"] == "regenerate_parameters")

    # Bind a mock regenerate callable so approval executes safely.
    original_regenerate = main_module.regenerate
    main_module.regenerate = lambda did, req: {
        "design_id": did,
        "success": True,
        "updated_parameters": req.parameter_updates,
    }
    try:
        approve_resp = client.post(f"/hermes/session/{session_id}/approve", json={
            "session_id": session_id,
            "step_id": regenerate_step["id"],
            "approved": True,
        })
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "done"
    finally:
        main_module.regenerate = original_regenerate


def test_hermes_context_populated_for_design(clean_designs):
    designs_dir = main_module.DESIGNS_DIR
    design_id = "dctx"
    _seed_design(designs_dir, design_id)

    created = client.post("/hermes/session", json={"design_id": design_id}).json()
    session_id = created["session_id"]
    response = client.get(f"/hermes/session/{session_id}")
    data = response.json()
    assert data["context"].get("design_id") == design_id
    assert data["context"].get("design_summary", {}).get("prompt") == "robot base plate"


def test_hermes_message_with_bound_dfm_tool(clean_designs):
    designs_dir = main_module.DESIGNS_DIR
    design_id = "ddfm"
    _seed_design(designs_dir, design_id)

    created = client.post("/hermes/session", json={"design_id": design_id}).json()
    session_id = created["session_id"]

    # Mock LLM asks to run DFM report.
    mock_response = json.dumps({"tool_calls": [{"tool": "run_dfm_report", "parameters": {}}]})
    main_module.build_llm_caller = lambda model=None, api_key=None: deterministic_mock_caller(mock_response)

    # Patch DFM backend so the test does not need a real STL file.
    original_dfm = main_module.dfm_report
    main_module.dfm_report = lambda did: {"design_id": did, "report": {"pass": True, "issues": []}}
    try:
        response = client.post(f"/hermes/session/{session_id}/message", json={
            "session_id": session_id,
            "message": "Run DFM",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "done"
        session_data = client.get(f"/hermes/session/{session_id}").json()
        plan = session_data["active_plan"] or session_data["plans"][-1]
        assert any(s["tool"] == "run_dfm_report" and s["status"] == "completed" for s in plan["steps"])
    finally:
        main_module.dfm_report = original_dfm
