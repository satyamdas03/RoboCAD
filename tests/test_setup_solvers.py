"""Tests for scripts/setup_solvers.py bootstrap helper."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import setup_solvers  # type: ignore[import-not-found]


def test_install_all_dry_run_does_not_call_pm(monkeypatch) -> None:
    runs: list[list[str]] = []
    monkeypatch.setattr(setup_solvers, "_install_with_pm", lambda pm, pkgs, dry_run=False: runs.append([pm, *pkgs]) or True)
    results = setup_solvers.install_all(dry_run=True, solvers=["gmsh"])
    assert results["gmsh"] is True
    assert not runs


def test_check_mode_runs_zero() -> None:
    assert setup_solvers.main(["--check"]) == 0


def test_known_solver_keys() -> None:
    assert "calculix" in setup_solvers.SOLVER_PACKAGES
    assert "elmerfem" in setup_solvers.SOLVER_PACKAGES
    assert "openfoam" in setup_solvers.SOLVER_PACKAGES
    assert "gmsh" in setup_solvers.SOLVER_PACKAGES
