"""Tests for the RoboCAD launcher and health CLI."""
from __future__ import annotations

import importlib
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


def test_launcher_loads_repo_dotenv_at_import(monkeypatch):
    """Regression: start.py must load .env before checking API keys."""
    import dotenv

    captured: list[tuple[Path, bool]] = []

    def _fake_load_dotenv(path, override=False, encoding=None):
        captured.append((Path(path), override))

    monkeypatch.setattr(dotenv, "load_dotenv", _fake_load_dotenv)
    importlib.reload(launcher)
    assert any(path == REPO_ROOT / ".env" and override is True for path, override in captured)


def test_start_entry_point_loads_repo_dotenv(monkeypatch):
    """Regression: ``python start.py`` loads .env before importing launcher."""
    import dotenv

    captured: list[tuple[Path, bool]] = []

    def _fake_load_dotenv(path, override=False, encoding=None):
        captured.append((Path(path), override))

    monkeypatch.setattr(dotenv, "load_dotenv", _fake_load_dotenv)
    # start.py imports launcher, which would also call load_dotenv; we only care
    # that the first call happens from start.py and points at the repo-root .env.
    import runpy
    runpy.run_path(str(REPO_ROOT / "start.py"), run_name="__test_start__")
    assert any(path == REPO_ROOT / ".env" and override is True for path, override in captured)


def test_start_entry_point_loads_env_value(tmp_path: Path, monkeypatch):
    """Regression: ``python start.py`` actually exports ANTHROPIC_API_KEY from .env."""
    import runpy
    import os

    # Write a temporary .env in the repo root. start.py resolves the repo root
    # from __file__, so we must place the file at REPO_ROOT.
    original_key = os.environ.get("ANTHROPIC_API_KEY")
    test_key = "robocad-test-key-from-start-py"
    env_path = REPO_ROOT / ".env"
    backup = None
    if env_path.exists():
        backup = env_path.read_text(encoding="utf-8")
    env_path.write_text(f"ANTHROPIC_API_KEY={test_key}\n", encoding="utf-8")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        runpy.run_path(str(REPO_ROOT / "start.py"), run_name="__test_start__")
        assert os.environ.get("ANTHROPIC_API_KEY") == test_key
    finally:
        if backup is not None:
            env_path.write_text(backup, encoding="utf-8")
        else:
            env_path.unlink(missing_ok=True)
        if original_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = original_key
        else:
            os.environ.pop("ANTHROPIC_API_KEY", None)


def test_start_entry_point_loads_bom_encoded_env_value(tmp_path: Path, monkeypatch):
    """Regression: ``python start.py`` handles UTF-8 BOM encoded .env files."""
    import runpy
    import os

    original_key = os.environ.get("ANTHROPIC_API_KEY")
    test_key = "robocad-test-key-from-bom-env"
    env_path = REPO_ROOT / ".env"
    backup = None
    if env_path.exists():
        backup = env_path.read_bytes()
    env_path.write_bytes(b"\xef\xbb\xbfANTHROPIC_API_KEY=" + test_key.encode("utf-8") + b"\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        runpy.run_path(str(REPO_ROOT / "start.py"), run_name="__test_start__")
        assert os.environ.get("ANTHROPIC_API_KEY") == test_key
    finally:
        if backup is not None:
            env_path.write_bytes(backup)
        else:
            env_path.unlink(missing_ok=True)
        if original_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = original_key
        else:
            os.environ.pop("ANTHROPIC_API_KEY", None)
