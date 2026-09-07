"""Tests for the RoboCAD launcher and health CLI."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from robocad import health, launcher


def test_check_python_version_passes():
    report = launcher.check_python_version((3, 1))
    assert report["ok"] is True
    assert report["name"] == "python"


def test_check_python_version_fails_for_unreasonably_high_version():
    report = launcher.check_python_version((sys.version_info[0] + 1, 0))
    assert report["ok"] is False


def test_check_virtualenv_report_has_keys():
    report = launcher.check_virtualenv()
    assert report["name"] == "virtualenv"
    assert "message" in report


def test_environment_report_has_required_rows():
    rows = launcher.environment_report()
    names = {row["name"] for row in rows}
    assert "python" in names
    assert "pip" in names
    assert "ANTHROPIC_API_KEY" in names


def test_report_is_ready_requires_required_rows():
    ok_rows = [{"required": True, "ok": True}, {"required": False, "ok": False}]
    assert launcher.report_is_ready(ok_rows) is True
    bad_rows = [{"required": True, "ok": False}, {"required": False, "ok": True}]
    assert launcher.report_is_ready(bad_rows) is False


def test_find_command_finds_python():
    path = launcher.find_command(sys.executable)
    assert path is not None


def test_health_report_structure():
    report = health.health_report()
    assert "ready" in report
    assert "checks" in report
    groups = {row["group"] for row in report["checks"]}
    assert "environment" in groups
    assert "api_keys" in groups
    assert "python_deps" in groups
    assert "solvers" in groups


def test_health_api_keys_reflect_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    report = health.health_report()
    antropic_rows = [r for r in report["checks"] if r["group"] == "api_keys" and r["name"] == "ANTHROPIC_API_KEY"]
    assert len(antropic_rows) == 1
    assert antropic_rows[0]["ok"] is True


def test_health_main_return_code_honours_readiness(monkeypatch):
    # Force readiness to False by removing required key.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert health.main() == 1


def test_main_argparse_help_does_not_crash():
    with pytest.raises(SystemExit) as exc_info:
        launcher.main(["--help"])
    assert exc_info.value.code == 0
