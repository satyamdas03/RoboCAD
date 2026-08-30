"""Shared pytest fixtures and hooks for RoboCAD.

Goals:
- Keep the local test run light and safe on limited RAM.
- Force cleanup of heavy geometry/mesh objects between tests.
- Provide markers so heavy/mujoco/benchmark tests can be skipped locally.
"""
from __future__ import annotations

import gc
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _cleanup_after_test():
    """Run garbage collection after every test to release build123d/trimesh objects.

    build123d / OpenCASCADE and trimesh can hold large native objects. Python's
    cyclic GC may not reclaim them promptly during a long pytest session, which
    contributes to the RAM spikes that crash the laptop. This fixture forces a
    collection after every test.
    """
    yield
    gc.collect()


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    """Final garbage collection at session end."""
    gc.collect()
