"""Tests for Phase 28E real-solver dispatch and field export.

These tests monkeypatch the solver binaries so they exercise the real dispatch
path without requiring CalculiX/ElmerFEM/OpenFOAM to be installed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import trimesh

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.solvers import calculix_adapter, elmerfem_adapter, field_export, openfoam_adapter
from ai_cad.solvers.job_store import JobStore
from ai_cad.solvers.verification_deep import (
    DeepVerificationDispatcher,
    run_deep_verification,
)
from ai_cad.verification_models import LoadCase, VerificationRequest


@pytest.fixture
def sample_design(tmp_path: Path) -> Path:
    """Create a persisted design directory with a simple bracket STL."""
    design_dir = tmp_path / "designs" / "bracket_real"
    exports_dir = design_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    mesh = trimesh.creation.box(extents=(50.0, 20.0, 5.0))
    mesh.export(str(exports_dir / "model.stl"))
    metadata = {
        "id": "bracket_real",
        "prompt": "bracket",
        "success": True,
        "model": "fake",
        "attempts_used": 1,
        "max_retries": 0,
        "latency_seconds": 0.0,
        "created_at": "2026-09-01T00:00:00Z",
        "exports": {"stl": "exports/model.stl"},
    }
    (design_dir / "metadata.json").write_text(json.dumps(metadata))
    return design_dir


@pytest.fixture
def temp_job_store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "verification_jobs.db")


def test_auto_mode_uses_real_calculix_when_available(
    sample_design: Path,
    temp_job_store: JobStore,
    monkeypatch: pytest.MonkeyPatch,
):
    """With ccx on PATH, static_stress should run the real CalculiX adapter."""
    monkeypatch.setattr(calculix_adapter, "_find_ccx", lambda: "ccx")
    calls: list[dict] = []

    def fake_run_calculix(*args, **kwargs):
        calls.append(kwargs)
        from ai_cad.solvers.models import SolverResult

        return SolverResult(
            success=True,
            solver="calculix",
            analysis_type="static",
            input_files=[],
            result_files={},
            metrics={"max_stress_mpa": 12.0, "safety_factor": 4.0},
            errors=[],
            details={},
        )

    monkeypatch.setattr(calculix_adapter, "run_calculix", fake_run_calculix)

    result = run_deep_verification(
        design_id="bracket_real",
        load_case=LoadCase.STATIC_STRESS,
        params={"material": "PLA", "load_magnitude_n": 50, "solver_mode": "auto"},
        design_dir=sample_design,
        job_store=temp_job_store,
    )

    assert result.load_case == LoadCase.STATIC_STRESS
    assert result.metrics["max_stress_mpa"] == pytest.approx(12.0)
    assert result.metrics["safety_factor"] == pytest.approx(4.0)
    assert calls, "Real CalculiX adapter was not invoked"


def test_real_mode_fails_when_calculix_missing(
    sample_design: Path,
    temp_job_store: JobStore,
    monkeypatch: pytest.MonkeyPatch,
):
    """solver_mode=real must fail fast if the binary is not installed."""
    monkeypatch.setattr(calculix_adapter, "_find_ccx", lambda: None)

    result = run_deep_verification(
        design_id="bracket_real",
        load_case=LoadCase.STATIC_STRESS,
        params={"material": "PLA", "load_magnitude_n": 50, "solver_mode": "real"},
        design_dir=sample_design,
        job_store=temp_job_store,
    )

    assert result.passed is False
    assert any("ccx" in e.lower() for e in result.errors)


def test_auto_mode_falls_back_to_estimate_when_calculix_missing(
    sample_design: Path,
    temp_job_store: JobStore,
    monkeypatch: pytest.MonkeyPatch,
):
    """Without ccx, auto mode should still return a lightweight estimate."""
    monkeypatch.setattr(calculix_adapter, "_find_ccx", lambda: None)

    result = run_deep_verification(
        design_id="bracket_real",
        load_case=LoadCase.STATIC_STRESS,
        params={"material": "PLA", "load_magnitude_n": 50, "solver_mode": "auto"},
        design_dir=sample_design,
        job_store=temp_job_store,
    )

    assert result.load_case == LoadCase.STATIC_STRESS
    assert "max_stress_mpa" in result.metrics
    assert any("estimate" in w.lower() for w in result.warnings)


def test_elmer_real_dispatch_thermal_resistance(
    sample_design: Path,
    temp_job_store: JobStore,
    monkeypatch: pytest.MonkeyPatch,
):
    """With ElmerSolver available, thermal case returns real metrics."""
    monkeypatch.setattr(elmerfem_adapter, "_find_elmer", lambda: "ElmerSolver")
    calls: list[str] = []

    def fake_run_elmer_thermal_conduction(*args, **kwargs):
        calls.append("thermal_conduction")
        from ai_cad.solvers.models import SolverResult

        return SolverResult(
            success=True,
            solver="elmerfem",
            analysis_type="thermal_conduction",
            input_files=[],
            result_files={},
            metrics={"max_temperature_c": 85.0, "min_temperature_c": 25.0},
            errors=[],
            details={},
        )

    monkeypatch.setattr(
        elmerfem_adapter,
        "run_elmer_thermal_conduction",
        fake_run_elmer_thermal_conduction,
    )

    result = run_deep_verification(
        design_id="bracket_real",
        load_case=LoadCase.HEAT_SINK_THERMAL_RESISTANCE,
        params={"heat_flux_w": 5.0, "target_theta_c_per_w": 10.0, "material": "Aluminum 6061"},
        design_dir=sample_design,
        job_store=temp_job_store,
    )

    assert result.load_case == LoadCase.HEAT_SINK_THERMAL_RESISTANCE
    assert "thermal_resistance_c_per_w" in result.metrics
    assert calls == ["thermal_conduction"]


def test_openfoam_real_dispatch_drag_coefficient(
    sample_design: Path,
    temp_job_store: JobStore,
    monkeypatch: pytest.MonkeyPatch,
):
    """With OpenFOAM available, drag coefficient is parsed from the run."""
    monkeypatch.setattr(openfoam_adapter, "_local_openfoam_available", lambda *_: True)
    monkeypatch.setattr(openfoam_adapter, "_docker_available", lambda: False)
    built: list[dict] = []
    ran: list[dict] = []

    def fake_build(*args, **kwargs):
        built.append(kwargs)
        from ai_cad.solvers.openfoam_adapter import OpenFOAMCaseResult

        return OpenFOAMCaseResult(success=True, case_dir=Path("/tmp/foam"), files_written=[], coefficients={})

    def fake_run(*args, **kwargs):
        ran.append(kwargs)
        from ai_cad.solvers.openfoam_adapter import OpenFOAMCaseResult

        return OpenFOAMCaseResult(
            success=True,
            case_dir=Path("/tmp/foam"),
            run_success=True,
            coefficients={"Cd": 0.42},
            errors=[],
        )

    monkeypatch.setattr(openfoam_adapter, "build_openfoam_case", fake_build)
    monkeypatch.setattr(openfoam_adapter, "run_openfoam_case", fake_run)

    result = run_deep_verification(
        design_id="bracket_real",
        load_case=LoadCase.WIND_TUNNEL_DRAG,
        params={"velocity_m_s": 10.0},
        design_dir=sample_design,
        job_store=temp_job_store,
    )

    assert result.load_case == LoadCase.WIND_TUNNEL_DRAG
    assert result.metrics["drag_coefficient"] == pytest.approx(0.42)
    assert built and ran


def test_extract_calculix_displacement_field():
    """Field parser extracts nodal displacement magnitudes from a mocked .dat."""
    from ai_cad.solvers.models import BoundaryCondition, BoundaryConditionType, Mesh

    mesh = Mesh.box(extents=(10.0, 10.0, 10.0), divisions=(2, 2, 2))
    bc_list = [
        BoundaryCondition(bc_type=BoundaryConditionType.FIXED, region="-x", label="fixed"),
        BoundaryCondition(bc_type=BoundaryConditionType.FORCE, region="+x", value=100.0, direction=(0, 0, -1), label="load"),
    ]
    from ai_cad.solvers.calculix_adapter import _mock_dat_for_static

    workdir = Path("/tmp/robocad_test_field")
    workdir.mkdir(parents=True, exist_ok=True)
    dat_path = workdir / "analysis.dat"
    _mock_dat_for_static(dat_path, mesh, bc_list, "PLA")

    field = field_export.extract_calculix_field(dat_path, nodes=mesh.nodes, field="displacement_magnitude_mm")
    assert field["message"] == "ok"
    assert len(field["scalars"]) > 0
    assert field["max"] >= field["min"]


def test_extract_elmer_temperature_field():
    """Field parser extracts nodal temperature from a synthetic Elmer .ep file."""
    ep_path = Path("/tmp/robocad_test_field") / "case.ep"
    ep_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <ElmerPostFile>
          <Simulation>
            <Timestep index="0">
              <Data index="1" x="0" y="0" z="0" temperature="25.0"/>
              <Data index="2" x="1" y="0" z="0" temperature="85.0"/>
            </Timestep>
          </Simulation>
        </ElmerPostFile>
        """
    )
    field = field_export.extract_elmer_field(ep_path, field="temperature_c")
    assert field["message"] == "ok"
    assert len(field["scalars"]) == 2
    assert field["max"] == pytest.approx(85.0)
    assert field["min"] == pytest.approx(25.0)
