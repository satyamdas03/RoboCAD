"""Tests for robocad.health environment report."""
from __future__ import annotations

import importlib
from pathlib import Path

import robocad.health as health

REPO_ROOT = Path(__file__).resolve().parent.parent


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


def test_health_loads_repo_dotenv_at_import(monkeypatch) -> None:
    """Regression: python -m robocad.health must load .env before checking API keys."""
    import dotenv

    captured: list[tuple[Path, bool]] = []

    def _fake_load_dotenv(path, override=False):
        captured.append((Path(path), override))

    monkeypatch.setattr(dotenv, "load_dotenv", _fake_load_dotenv)
    importlib.reload(health)
    assert any(path == REPO_ROOT / ".env" and override is True for path, override in captured)
