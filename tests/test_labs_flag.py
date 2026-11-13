"""The Labs flag: one switch, default off, visible on /health.

The point of these tests is that a frozen feature cannot come back by accident. If a value other
than an explicit "1" enabled it, an environment file typo would silently re-open the old product.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robocad.labs import LABS_ENV_VAR, labs_enabled  # noqa: E402
from web.backend.main import app  # noqa: E402


@pytest.fixture()
def clean_env(monkeypatch):
    monkeypatch.delenv(LABS_ENV_VAR, raising=False)
    return monkeypatch


def test_default_is_off(clean_env):
    assert labs_enabled() is False


@pytest.mark.parametrize("value", ["1", " 1 ", "1\n"])
def test_explicit_one_turns_it_on(clean_env, value):
    clean_env.setenv(LABS_ENV_VAR, value)
    assert labs_enabled() is True


@pytest.mark.parametrize("value", ["0", "", "true", "yes", "on", "2", "01"])
def test_anything_else_stays_off(clean_env, value):
    clean_env.setenv(LABS_ENV_VAR, value)
    assert labs_enabled() is False


def test_health_reports_the_flag(clean_env):
    client = TestClient(app)
    clean_env.setenv(LABS_ENV_VAR, "0")
    assert client.get("/health").json()["labs"] is False

    clean_env.setenv(LABS_ENV_VAR, "1")
    body = client.get("/health").json()
    assert body["labs"] is True
    # The minimal response stays minimal; the flag is the one addition.
    assert set(body) <= {"status", "labs"}


def test_health_verbose_also_reports_it(clean_env):
    client = TestClient(app)
    clean_env.setenv(LABS_ENV_VAR, "1")
    body = client.get("/health", params={"verbose": 1}).json()
    assert body["labs"] is True
    assert "checks" in body
