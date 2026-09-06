"""Tests for HERMES tool executors."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.hermes.executor import execute_tool
from ai_cad.hermes.validation import ValidationErrorMessage, validate_tool_parameters


def test_execute_classify_domain_with_mock_context():
    ctx = {"classify_domain": lambda prompt: {"domain": "mechanical", "prompt": prompt}}
    result = execute_tool("classify_domain", {"prompt": "a cube"}, context=ctx)
    assert result["domain"] == "mechanical"


def test_execute_get_design_summary_with_mock_context():
    ctx = {"get_design_summary": lambda: {"design_id": "d1", "prompt": "cube"}}
    result = execute_tool("get_design_summary", {}, context=ctx)
    assert result["design_id"] == "d1"


def test_execute_explain_last_failure_reads_context_report():
    ctx = {"latest_reports": {"dfm": {"pass": False, "issues": [{"message": "thin wall"}]}}}
    result = execute_tool("explain_last_failure", {"target": "dfm"}, context=ctx)
    assert result["status"] == "success"
    assert "thin wall" in result["explanation"]


def test_execute_propose_redesign_uses_heuristic():
    report = {"issues": [{"severity": "error", "message": "Wall is too thin"}]}
    result = execute_tool("propose_redesign", {"goal": "make it stronger", "failure_report": report}, context={})
    assert result["status"] == "success"
    assert "thickness" in result["parameter_updates"]


def test_execute_generate_design_missing_context_returns_error():
    result = execute_tool("generate_design", {"prompt": "a cube"}, context={})
    assert result["status"] == "error"
    assert "generate_design" in result["message"]


def test_execute_regenerate_parameters_with_mock_context():
    ctx = {"regenerate_parameters": lambda parameter_updates: {"success": True, "updated": parameter_updates}}
    result = execute_tool("regenerate_parameters", {"parameter_updates": {"thickness": 2.0}}, context=ctx)
    assert result["success"] is True
    assert result["updated"]["thickness"] == 2.0


def test_validation_rejects_invalid_max_retries():
    with pytest.raises(ValidationErrorMessage) as exc_info:
        validate_tool_parameters("generate_design", {"prompt": "cube", "max_retries": -1})
    assert "max_retries" in str(exc_info.value)


def test_validation_rejects_empty_prompt():
    with pytest.raises(ValidationErrorMessage):
        validate_tool_parameters("generate_design", {"prompt": ""})


def test_validation_accepts_unknown_tool():
    params = validate_tool_parameters("unknown_tool", {"anything": 123})
    assert params == {"anything": 123}


def test_execute_tool_validates_before_calling_executor():
    ctx = {"generate_design": lambda **kw: {"called": True}}
    with pytest.raises(ValidationErrorMessage) as exc_info:
        execute_tool("generate_design", {"prompt": "cube", "max_retries": -1}, context=ctx)
    assert "max_retries" in str(exc_info.value)
