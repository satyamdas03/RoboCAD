"""Tests for the Phase 28E deep verification report export."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.solvers.report_export import generate_deep_verify_report, write_deep_verify_report


def test_generate_report_includes_basic_sections():
    result = {
        "load_case": "static_stress",
        "passed": True,
        "metrics": {
            "max_stress_mpa": 12.5,
            "safety_factor": 2.4,
        },
        "warnings": ["Using lightweight estimate."],
        "redesign_suggestions": [],
        "failure_modes": [],
        "errors": [],
        "raw_output": {
            "solver": "calculix",
            "analysis_type": "static",
            "details": {"node_count": 125, "element_count": 64},
        },
    }
    report = generate_deep_verify_report("design_1", "job_1", result)
    assert "# RoboCAD Deep Verification Report" in report
    assert "static_stress" in report
    assert "PASS" in report
    assert "max_stress_mpa" in report
    assert "12.5" in report
    assert "Using lightweight estimate." in report


def test_generate_report_handles_missing_data():
    result = {"load_case": "mesh_quality", "passed": False}
    report = generate_deep_verify_report("design_2", "job_2", result)
    assert "FAIL" in report
    assert "No metrics produced." in report


def test_write_report_to_disk(tmp_path: Path):
    result = {"load_case": "wind_tunnel_drag", "passed": True, "metrics": {"drag_coefficient": 0.42}}
    output_dir = tmp_path / "reports"
    path = write_deep_verify_report("d3", "job_3", result, output_dir)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "wind_tunnel_drag" in text
    assert "0.42" in text
