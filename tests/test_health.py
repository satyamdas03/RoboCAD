"""Tests for robocad.health environment report."""
from __future__ import annotations

import robocad.health as health


def test_health_report_structure() -> None:
    report = health.health_report()
    assert isinstance(report, dict)
    assert "ready" in report
    assert isinstance(report["checks"], list)
    groups = {row["group"] for row in report["checks"]}
    assert "solvers" in groups
    assert "api_keys" in groups


def test_solvers_have_install_hints() -> None:
    for solver in health.SOLVERS:
        if solver.get("command"):
            assert solver.get("install_hint"), f"{solver['name']} missing install_hint"


def test_print_health_runs_without_error(capsys) -> None:
    health.print_health()
    captured = capsys.readouterr()
    assert "RoboCAD Health Report" in captured.out
    assert "solvers" in captured.out.lower()
