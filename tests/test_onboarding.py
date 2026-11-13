"""Onboarding smoke tests: environment, launcher, and optional solvers are discoverable."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from web.backend.main import app

client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parent.parent


def test_start_py_help() -> None:
    result = subprocess.run(
        [sys.executable, "start.py", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RoboCAD" in result.stdout or "usage:" in result.stdout.lower()


def test_health_module_main() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "robocad.health"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "RoboCAD Health Report" in result.stdout
    assert "solvers" in result.stdout.lower()


def test_solver_docs_exist() -> None:
    assert (REPO_ROOT / "docs" / "SOLVER_INSTALL.md").is_file()


def test_setup_solvers_script_exists() -> None:
    assert (REPO_ROOT / "scripts" / "setup_solvers.py").is_file()


def test_backend_health_reports_ok_when_the_required_key_is_set(monkeypatch) -> None:
    # The key is set to a placeholder, never a real one: the endpoint checks presence, and a test
    # must not depend on the developer's .env existing. A fresh clone has no .env, and this test
    # failing there was the test's fault, not the endpoint's.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder-not-a-real-key")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_backend_health_reports_degraded_without_the_required_key(monkeypatch) -> None:
    # Degraded is a correct answer, not a failure: the service is up and says what it is missing.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
