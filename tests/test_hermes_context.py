"""Tests for HERMES design context builder."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.hermes.context import build_design_context, build_global_context


def test_build_context_for_missing_design(tmp_path):
    ctx = build_design_context("missing", tmp_path)
    assert "error" in ctx


def test_build_context_reads_metadata_parameters_and_reports(tmp_path):
    design_dir = tmp_path / "d123"
    design_dir.mkdir()
    metadata = {
        "id": "d123",
        "prompt": "robot base plate",
        "domain": "mechanical",
        "success": True,
        "model": "claude-test",
        "created_at": "2026-09-01T00:00:00Z",
        "dfm_report": {"pass": False, "issues": [{"message": "too thin"}]},
        "brain": {"success": True, "success_rate": 0.8},
    }
    parameters = [
        {"name": "thickness", "value": 3.0, "description": "plate thickness"},
    ]
    (design_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (design_dir / "parameters.json").write_text(json.dumps(parameters), encoding="utf-8")
    (design_dir / "feature_tree.json").write_text(
        json.dumps({"schema_version": "2.0.0", "assemblies": [], "parts": []}), encoding="utf-8"
    )

    ctx = build_design_context("d123", tmp_path)
    assert ctx["prompt"] == "robot base plate"
    assert ctx["domain"] == "mechanical"
    assert len(ctx["parameters"]) == 1
    assert ctx["parameters"][0]["name"] == "thickness"
    assert "dfm" in ctx["latest_reports"]
    assert "brain" in ctx["latest_reports"]
    assert "regenerate_parameters" in ctx["available_actions"]


def test_build_global_context_merges_backend_callables(tmp_path):
    backend = {"run_dfm_report": lambda: {"ok": True}}
    ctx = build_global_context("d123", tmp_path, backend_callables=backend)
    assert ctx["run_dfm_report"] == backend["run_dfm_report"]
    assert ctx["design_id"] == "d123"
