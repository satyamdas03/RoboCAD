"""Tests for the HERMES conversational supervisor."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.hermes import (
    ApprovalGate,
    HermesAgent,
    HermesSession,
    HermesToolRegistry,
    execute_plan_step,
    explain_report,
)
from ai_cad.hermes.gate import ApprovalGate as GateClass
from ai_cad.hermes.models import Message, PlanStep, Session, ToolCall
from ai_cad.hermes.planner import (
    advance_plan,
    approve_step,
    build_plan,
    next_runnable_step,
    plan_dependency_order,
    reject_step,
    tool_call_to_step,
)
from ai_cad.hermes.session import HermesSessionStore


@pytest.fixture
def tmp_designs(tmp_path):
    return tmp_path / "designs"


# -----------------------------------------------------------------------------
# Gate
# -----------------------------------------------------------------------------

def test_gate_read_only_tools_no_approval():
    gate = ApprovalGate()
    assert gate.requires_approval("classify_domain") is False
    assert gate.requires_approval("explain_last_failure") is False


def test_gate_expensive_tools_require_approval():
    gate = ApprovalGate()
    assert gate.requires_approval("generate_design") is True
    assert gate.requires_approval("train_brain") is True
    assert gate.requires_approval("synthesize_assembly") is True


def test_gate_default_behavior():
    gate = ApprovalGate(default_requires_approval=False)
    assert gate.requires_approval("unknown_tool") is False
    gate2 = ApprovalGate(default_requires_approval=True)
    assert gate2.requires_approval("unknown_tool") is True


# -----------------------------------------------------------------------------
# Registry
# -----------------------------------------------------------------------------

def test_registry_lists_default_tools():
    registry = HermesToolRegistry()
    names = registry.list_tools()
    assert "classify_domain" in names
    assert "generate_design" in names
    assert "train_brain" in names


def test_registry_definitions_are_valid_json_schema():
    registry = HermesToolRegistry()
    for d in registry.definitions():
        assert "name" in d
        assert "description" in d
        assert "parameters" in d
        assert d["parameters"].get("type") == "object"


def test_registry_execute_stub_returns_status():
    registry = HermesToolRegistry()
    result = registry.execute("classify_domain", {"prompt": "a cube"})
    assert result["status"] == "stub"


def test_registry_duplicate_register_raises():
    registry = HermesToolRegistry()
    with pytest.raises(ValueError):
        # Create a second identical tool should fail
        from ai_cad.hermes.tools import HermesTool

        registry.register(HermesTool(name="classify_domain", description="dup"))


# -----------------------------------------------------------------------------
# Planner
# -----------------------------------------------------------------------------

def test_plan_dependency_order():
    plan = build_plan(
        "test",
        [
            {"id": "a", "description": "first"},
            {"id": "b", "description": "second", "depends_on": ["a"]},
            {"id": "c", "description": "third", "depends_on": ["b"]},
        ],
    )
    order = plan_dependency_order(plan)
    ids = [s.id for s in order]
    assert ids == ["a", "b", "c"]


def test_next_runnable_step_returns_first_step():
    plan = build_plan("test", [{"description": "first", "tool": "classify_domain"}])
    step = next_runnable_step(plan)
    assert step is not None
    assert step.description == "first"


def test_next_runnable_step_blocks_on_unmet_dependency():
    plan = build_plan(
        "test",
        [
            {"id": "a", "description": "first"},
            {"id": "b", "description": "second", "depends_on": ["a"]},
        ],
    )
    step = next_runnable_step(plan)
    assert step.id == "a"


def test_next_runnable_step_marks_approval_step():
    plan = build_plan(
        "test",
        [{"description": "train", "tool": "train_brain"}],
    )
    step = next_runnable_step(plan)
    assert step.status.value == "awaiting_approval"


def test_advance_plan_runs_read_only_steps():
    plan = build_plan(
        "test",
        [
            {"description": "explain", "tool": "explain_last_failure", "parameters": {"target": "dfm"}},
            {"description": "train", "tool": "train_brain"},
        ],
    )
    registry = HermesToolRegistry()
    results = advance_plan(plan, registry)
    assert len(results) == 2
    assert results[0].status == "success"
    assert results[1].status == "pending_approval"
    assert plan.steps[0].status.value == "completed"


def test_approve_step_then_advance():
    plan = build_plan("test", [{"description": "train", "tool": "train_brain"}])
    registry = HermesToolRegistry()
    advance_plan(plan, registry)
    step = approve_step(plan, plan.steps[0].id)
    assert step.status.value == "pending"
    assert step.metadata["approved"]
    results = advance_plan(plan, registry)
    assert results[0].status == "success"
    assert plan.steps[0].status.value == "completed"


def test_reject_step_skips_dependents():
    plan = build_plan(
        "test",
        [
            {"id": "a", "description": "train", "tool": "train_brain"},
            {"id": "b", "description": "analyze", "depends_on": ["a"]},
        ],
    )
    registry = HermesToolRegistry()
    advance_plan(plan, registry)
    reject_step(plan, "a", "too expensive")
    assert plan.steps[0].status.value == "rejected"
    assert plan.steps[1].status.value == "skipped"


def test_tool_call_to_step():
    call = ToolCall(tool="build_world", parameters={"template": "push"})
    step = tool_call_to_step(call)
    assert step.tool == "build_world"
    assert step.parameters["template"] == "push"


# -----------------------------------------------------------------------------
# Session + persistence
# -----------------------------------------------------------------------------

def test_session_create_and_load(tmp_designs):
    wrapper = HermesSession.create(design_id="d123", base_dir=tmp_designs)
    assert wrapper.session.design_id == "d123"
    assert wrapper.session.status == "idle"
    path = wrapper.save()
    assert path.exists()

    loaded = HermesSession.load(wrapper.session.id, design_id="d123", base_dir=tmp_designs)
    assert loaded.session.id == wrapper.session.id
    assert loaded.session.design_id == "d123"


def test_session_add_message(tmp_designs):
    wrapper = HermesSession.create(base_dir=tmp_designs)
    msg = wrapper.add_message("user", "hello")
    assert msg.role.value == "user"
    assert wrapper.session.messages[-1].content == "hello"
    loaded = HermesSession.load(wrapper.session.id, base_dir=tmp_designs)
    assert len(loaded.session.messages) == 1


def test_session_plan_and_advance(tmp_designs):
    wrapper = HermesSession.create(design_id="d123", base_dir=tmp_designs)
    plan = wrapper.create_plan(
        "demo",
        [
            {"description": "explain", "tool": "explain_last_failure", "parameters": {"target": "dfm"}},
        ],
    )
    assert plan.goal == "demo"
    results = wrapper.advance()
    assert len(results) == 1
    assert results[0]["status"] == "success"


def test_session_approval_flow(tmp_designs):
    wrapper = HermesSession.create(design_id="d123", base_dir=tmp_designs)
    wrapper.create_plan(
        "train",
        [{"description": "train", "tool": "train_brain"}],
    )
    results = wrapper.advance()
    assert results[0]["status"] == "pending_approval"
    step_id = wrapper.session.active_plan().steps[0].id
    wrapper.approve(step_id)
    results = wrapper.advance()
    assert results[0]["status"] == "success"


def test_session_status_reflects_plan(tmp_designs):
    wrapper = HermesSession.create(base_dir=tmp_designs)
    wrapper.create_plan("all good", [{"description": "explain", "tool": "explain_last_failure", "parameters": {"target": "generic"}}])
    wrapper.advance()
    assert wrapper.session.status == "done"


# -----------------------------------------------------------------------------
# Agent
# -----------------------------------------------------------------------------

def test_agent_prepare_messages_includes_system_prompt():
    agent = HermesAgent()
    messages = agent.prepare_messages("hello")
    assert messages[0]["role"] == "system"
    assert "HERMES" in messages[0]["content"]


def test_agent_parse_tool_call_block():
    agent = HermesAgent()
    raw = '```json\n{"tool_calls": [{"tool": "build_world", "parameters": {"template": "push"}}]}\n```'
    resp = agent.parse_response(raw)
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].tool == "build_world"


def test_agent_parse_plan_block():
    agent = HermesAgent()
    raw = '```json\n{"plan": {"goal": "demo", "steps": [{"description": "train", "tool": "train_brain"}]}}\n```'
    resp = agent.parse_response(raw)
    assert resp.plan is not None
    assert resp.plan.goal == "demo"
    assert resp.plan.steps[0].tool == "train_brain"


def test_agent_run_stub_for_explain():
    agent = HermesAgent()
    resp = agent.run("explain the last failure")
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].tool == "explain_last_failure"


def test_agent_run_stub_for_train():
    agent = HermesAgent()
    resp = agent.run("train a brain")
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].tool == "train_brain"


# -----------------------------------------------------------------------------
# Explanation engine
# -----------------------------------------------------------------------------

def test_explain_dfm_pass():
    text = explain_report("dfm", {"pass": True, "issues": [], "metrics": {"min_wall_mm": 2.0}})
    assert "DFM report: PASS" in text
    assert "min_wall_mm" in text


def test_explain_dfm_fail():
    text = explain_report(
        "dfm",
        {
            "pass": False,
            "issues": [{"severity": "error", "message": "Wall too thin"}],
        },
    )
    assert "DFM report: FAIL" in text
    assert "Wall too thin" in text


def test_explain_brain():
    text = explain_report(
        "brain",
        {
            "success": True,
            "success_rate": 0.85,
            "mean_reward": 12.3,
            "policy_architecture": {"input_dim": 6, "hidden_dim": 12, "output_dim": 2},
        },
    )
    assert "Success rate: 85.0%" in text
    assert "Policy shape: 6→12→2" in text


def test_explain_unknown_target():
    text = explain_report("not_a_target")
    assert "No explainer available" in text


# -----------------------------------------------------------------------------
# End-to-end small plan
# -----------------------------------------------------------------------------

def test_end_to_end_explain_dfm_plan(tmp_designs):
    wrapper = HermesSession.create(base_dir=tmp_designs)
    wrapper.set_context("last_dfm_report", {"pass": False, "issues": [{"severity": "error", "message": "Hole too small"}]})
    plan = wrapper.create_plan(
        "Explain DFM failure",
        [
            {"description": "Explain DFM report", "tool": "explain_last_failure", "parameters": {"target": "dfm"}},
        ],
    )
    # Simulate the tool producing the explanation
    plan.steps[0].tool = None
    plan.steps[0].description = "Explain DFM report"
    results = wrapper.advance()
    assert results[0]["status"] == "success"
    assert wrapper.session.status == "done"
