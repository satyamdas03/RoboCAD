"""Tests for the Phase 28C CalculiX and ElmerFEM solver adapters.

These tests mock solver execution and verify that:

* input/case files are written correctly;
* synthetic result files are parsed into sensible metrics;
* a simple box produces positive stress/displacement/temperature values.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_cad.solvers.calculix_adapter import (
    _mock_dat_for_static,
    _parse_calculix_dat,
    run_calculix_modal,
    run_calculix_static,
)
from ai_cad.solvers.elmerfem_adapter import (
    _generate_boundary_faces,
    _infer_divisions,
    run_elmer_thermal_conduction,
    run_elmer_thermal_stress,
)
from ai_cad.solvers.models import BoundaryCondition, Mesh


# ---------------------------------------------------------------------------
# CalculiX
# ---------------------------------------------------------------------------


def test_calculix_static_writes_input_and_mock_result(tmp_path: Path):
    mesh = Mesh.box(extents=(0.04, 0.01, 0.01), divisions=(8, 2, 2))
    bcs = [
        BoundaryCondition("fixed", "-x"),
        BoundaryCondition("force", "+x", value=100.0, direction=(0.0, 0.0, -1.0)),
    ]
    result = run_calculix_static(
        mesh,
        "Aluminum 6061",
        bcs,
        workdir=tmp_path,
        run_solver=False,
        mock=True,
    )
    assert result.success, result.errors
    assert result.solver == "calculix"
    assert result.analysis_type == "static"
    assert (tmp_path / "analysis.inp").exists()
    assert (tmp_path / "analysis.dat").exists()
    assert result.metrics["max_stress_mpa"] > 0
    assert result.metrics["max_displacement_mm"] > 0
    assert result.metrics["safety_factor"] > 0


def test_calculix_modal_writes_input_and_mock_result(tmp_path: Path):
    mesh = Mesh.box(extents=(0.04, 0.01, 0.01), divisions=(8, 2, 2))
    bcs = [BoundaryCondition("fixed", "-x")]
    result = run_calculix_modal(
        mesh,
        "Aluminum 6061",
        bcs,
        modes=5,
        workdir=tmp_path,
        run_solver=False,
        mock=True,
    )
    assert result.success, result.errors
    assert result.metrics["first_natural_frequency_hz"] > 0
    assert result.metrics["mode_count"] == pytest.approx(5.0)


def test_calculix_dat_parser_extracts_metrics(tmp_path: Path):
    mesh = Mesh.box(extents=(0.01, 0.01, 0.01), divisions=(2, 2, 2))
    bcs = [
        BoundaryCondition("fixed", "-x"),
        BoundaryCondition("force", "+x", value=50.0, direction=(0.0, 0.0, -1.0)),
    ]
    dat_path = tmp_path / "analysis.dat"
    _mock_dat_for_static(dat_path, mesh, bcs, "PLA")
    metrics = _parse_calculix_dat(dat_path, "static")
    assert "max_stress_mpa" in metrics
    assert "max_displacement_mm" in metrics
    assert metrics["max_stress_mpa"] > 0
    assert metrics["max_displacement_mm"] > 0


# ---------------------------------------------------------------------------
# ElmerFEM
# ---------------------------------------------------------------------------


def test_elmer_thermal_conduction_writes_case_and_mock_result(tmp_path: Path):
    mesh = Mesh.box(extents=(0.01, 0.01, 0.01), divisions=(2, 2, 2))
    bcs = [
        BoundaryCondition("temperature", "-x", value=20.0),
        BoundaryCondition("temperature", "+x", value=100.0),
    ]
    result = run_elmer_thermal_conduction(
        mesh,
        "Aluminum 6061",
        bcs,
        initial_temperature=20.0,
        workdir=tmp_path,
        run_solver=False,
        mock=True,
    )
    assert result.success, result.errors
    assert result.solver == "elmerfem"
    assert result.analysis_type == "thermal_conduction"
    assert (tmp_path / "case.sif").exists()
    assert (tmp_path / "mesh" / "mesh.nodes").exists()
    assert (tmp_path / "mesh" / "mesh.elements").exists()
    assert (tmp_path / "mesh" / "mesh.boundary").exists()
    assert result.metrics["max_temperature_c"] == pytest.approx(100.0)
    assert result.metrics["min_temperature_c"] == pytest.approx(20.0)


def test_elmer_thermal_stress_writes_case_and_mock_result(tmp_path: Path):
    mesh = Mesh.box(extents=(0.04, 0.01, 0.01), divisions=(4, 2, 2))
    bcs = [
        BoundaryCondition("fixed", "-x"),
        BoundaryCondition("temperature", "-x", value=20.0),
        BoundaryCondition("temperature", "+x", value=120.0),
    ]
    result = run_elmer_thermal_stress(
        mesh,
        "Aluminum 6061",
        bcs,
        initial_temperature=20.0,
        workdir=tmp_path,
        run_solver=False,
        mock=True,
    )
    assert result.success, result.errors
    assert (tmp_path / "case.sif").exists()
    assert "max_temperature_c" in result.metrics
    assert "max_stress_mpa" in result.metrics
    assert "max_displacement_mm" in result.metrics
    assert result.metrics["max_stress_mpa"] > 0
    assert result.metrics["max_displacement_mm"] > 0
    assert result.metrics["safety_factor"] > 0


def test_elmer_boundary_face_generation_for_box():
    mesh = Mesh.box(extents=(0.01, 0.01, 0.01), divisions=(2, 2, 2))
    divisions = _infer_divisions(mesh)
    faces = _generate_boundary_faces(mesh, divisions)
    expected = 2 * (divisions[1] * divisions[2] + divisions[0] * divisions[2] + divisions[0] * divisions[1])
    assert len(faces) == expected
    for _bid, _parent, _name, nodes in faces:
        assert len(nodes) == 4
        assert all(isinstance(n, int) and n >= 1 for n in nodes)
