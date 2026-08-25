"""Tests for the complexity benchmark runner."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from ai_cad.models import CADParameter, ExportPaths, GenerationResult, ValidationReport
from benchmarks.evaluate_complexity import _run_single, _write_markdown_report, main


VALID_CODE = """
from build123d import *
length = 10.0
with BuildPart() as p:
    Box(length, length, length)
result = p.part
"""


def _make_result(success: bool, attempts_used: int = 1, error: str | None = None) -> GenerationResult:
    return GenerationResult(
        prompt="a cube",
        success=success,
        code=VALID_CODE if success else None,
        parameters=[CADParameter(name="length", value=10.0, unit="mm")] if success else [],
        exports=ExportPaths(
            stl=Path("/tmp/test.stl") if success else None,
            step=Path("/tmp/test.step") if success else None,
            script=Path("/tmp/test.py") if success else None,
        ),
        validation=ValidationReport(
            valid=True,
            manifold=True,
            watertight=True,
        ) if success else ValidationReport(
            valid=False,
            errors=[error or "boom"],
        ),
        attempts_used=attempts_used,
        max_retries=2,
        model="fake-model",
        error=error,
        latency_seconds=12.34,
    )


def test_run_single_records_success(tmp_path: Path):
    backend = mock.Mock()
    backend.generate.return_value = _make_result(success=True)

    prompt_item = {
        "id": "t1.1",
        "prompt": "a 10 mm cube",
        "tier": "Primitive",
    }

    result = _run_single(backend, prompt_item, max_retries=2, output_dir=tmp_path)

    assert result["id"] == "t1.1"
    assert result["tier"] == "Primitive"
    assert result["success"] is True
    assert result["failure_mode"] == "success"
    assert result["attempts_used"] == 1
    assert result["parameter_count"] == 1
    assert result["estimated_features"] == 1
    assert result["manifold"] is True
    assert result["watertight"] is True


def test_run_single_records_failure(tmp_path: Path):
    backend = mock.Mock()
    backend.generate.return_value = _make_result(
        success=False,
        attempts_used=2,
        error="syntax error near unexpected token",
    )

    prompt_item = {
        "id": "t1.2",
        "prompt": "a cube with bad code",
        "tier": "Primitive",
    }

    result = _run_single(backend, prompt_item, max_retries=2, output_dir=tmp_path)

    assert result["success"] is False
    assert result["failure_mode"] == "syntax"
    assert result["attempts_used"] == 2
    assert result["manifold"] is False


def test_run_single_catches_runner_exception(tmp_path: Path):
    backend = mock.Mock()
    backend.generate.side_effect = RuntimeError("backend exploded")

    prompt_item = {
        "id": "t1.3",
        "prompt": "a cube",
        "tier": "Primitive",
    }

    result = _run_single(backend, prompt_item, max_retries=2, output_dir=tmp_path)

    assert result["success"] is False
    assert "Runner crashed" in (result["error"] or "")
    assert result["failure_mode"] == "runner_crash"


def test_markdown_report_includes_summary_and_table(tmp_path: Path):
    results = [
        {
            "id": "t1.1",
            "tier": "T1",
            "prompt": "a cube",
            "success": True,
            "error": None,
            "traceback": None,
            "failure_mode": "success",
            "latency_seconds": 10.0,
            "attempts_used": 1,
            "model": "fake-model",
            "parameter_count": 1,
            "estimated_features": 1,
            "manifold": True,
            "watertight": True,
            "validation_errors": [],
            "validation_warnings": [],
            "export_stl": None,
            "export_step": None,
            "export_script": None,
        },
        {
            "id": "t1.2",
            "tier": "T1",
            "prompt": "a cylinder",
            "success": False,
            "error": "syntax error",
            "traceback": None,
            "failure_mode": "syntax",
            "latency_seconds": 5.0,
            "attempts_used": 2,
            "model": "fake-model",
            "parameter_count": 0,
            "estimated_features": 0,
            "manifold": None,
            "watertight": None,
            "validation_errors": [],
            "validation_warnings": [],
            "export_stl": None,
            "export_step": None,
            "export_script": None,
        },
    ]
    summary = {
        "total": 2,
        "successes": 1,
        "failures": 1,
        "overall_pass_rate": 0.5,
        "avg_latency_s": 10.0,
        "by_tier": {
            "T1": {"total": 2, "successes": 1, "failures": 1, "pass_rate": 0.5, "avg_latency_s": 10.0},
        },
        "by_failure_mode": {"success": 1, "syntax": 1},
    }
    ladder = {"max_retries": 2}
    md_path = tmp_path / "report.md"

    _write_markdown_report(results, summary, md_path, ladder)

    text = md_path.read_text(encoding="utf-8")
    assert "# RoboCAD Complexity Benchmark Report" in text
    assert "Overall pass rate:** 50.0%" in text
    assert "| T1 |" in text
    assert "| t1.1 |" in text
    assert "| t1.2 |" in text
    assert "### t1.2 (T1)" in text
    assert "**Prompt:** a cylinder" in text


def test_main_with_limit_and_tier(tmp_path: Path):
    """Smoke-test the CLI path with mocking so no real LLM calls happen."""
    with mock.patch("benchmarks.evaluate_complexity.RoboCADBackend") as mock_backend_cls:
        mock_backend = mock_backend_cls.return_value
        mock_backend.generate.return_value = _make_result(success=True)

        with mock.patch("sys.argv", [
            "evaluate_complexity.py",
            "--limit", "2",
            "--tier", "T1 - Primitive",
            "--output", str(tmp_path / "run_cli"),
            "--model", "fake-model",
            "--max-retries", "1",
        ]):
            main()

    json_path = tmp_path / "run_cli" / "results.json"
    md_path = tmp_path / "run_cli" / "report.md"
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["meta"]["model"] == "fake-model"
    assert data["meta"]["max_retries"] == 1
    assert data["summary"]["total"] == 2
    assert data["summary"]["successes"] == 2
