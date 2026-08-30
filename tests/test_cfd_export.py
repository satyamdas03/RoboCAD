"""Tests for CFD mesh export and solver stub writers (Phase 20)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.heavy]

from ai_cad.cfd import (
    CFDMeshResult,
    export_cfd_mesh,
    export_cfd_mesh_from_stl,
    _write_openfoam_stubs,
    _write_su2_config,
)
from ai_cad.feature_tree import FeatureTree
from ai_cad.part_families import get_family, instantiate_family
from ai_cad.transpiler import transpile


def _build_airfoil_stl(tmp_path: Path) -> Path:
    family = get_family("airfoil")
    part = instantiate_family("airfoil", "af1")
    tree = FeatureTree(
        design_id="test",
        prompt="test",
        parts=[part],
        parameters=family.default_parameters,
    )
    code = transpile(tree)
    ns: dict = {}
    exec(code, ns)
    shape = ns["result"]
    result = export_cfd_mesh(shape, tmp_path / "mesh.stl", solver="su2_stub")
    assert result.success and result.mesh_path is not None
    return result.mesh_path


def test_export_cfd_mesh_returns_result(tmp_path: Path):
    mesh_path = _build_airfoil_stl(tmp_path)
    result = export_cfd_mesh_from_stl(
        mesh_path,
        output_dir=tmp_path / "cfd",
        solver="su2_stub",
        angle_of_attack_deg=5.0,
        flow_velocity_ms=10.0,
    )
    assert isinstance(result, CFDMeshResult)
    assert result.success
    assert result.mesh_path is not None and result.mesh_path.exists()
    assert result.solver_config_path is not None and result.solver_config_path.exists()


def test_export_cfd_mesh_openfoam_returns_result(tmp_path: Path):
    mesh_path = _build_airfoil_stl(tmp_path)
    result = export_cfd_mesh_from_stl(
        mesh_path,
        output_dir=tmp_path / "cfd",
        solver="openfoam_stub",
        angle_of_attack_deg=0.0,
        flow_velocity_ms=10.0,
    )
    assert result.success
    assert result.mesh_path is not None and result.mesh_path.exists()
    assert result.solver_config_path is not None and result.solver_config_path.exists()
    assert (result.solver_config_path / "system" / "blockMeshDict").exists()
    assert (result.solver_config_path / "system" / "snappyHexMeshDict").exists()


def test_su2_config_contains_boundary_markers(tmp_path: Path):
    config_path = tmp_path / "su2.cfg"
    _write_su2_config(
        config_path,
        mesh_filename="surface_mesh.stl",
        reference_values={
            "mach_number": 0.1,
            "angle_of_attack_deg": 3.0,
            "reynolds_number": 1e5,
        },
    )
    text = config_path.read_text()
    assert "MESH_FILENAME" in text
    assert "MARKER_EULER" in text or "MARKER_FAR" in text
    assert "SOLVER" in text


def test_openfoam_stubs_have_required_files(tmp_path: Path):
    _write_openfoam_stubs(
        tmp_path / "openfoam",
        mesh_filename="surface_mesh.stl",
        reference_values={"mach_number": 0.1, "angle_of_attack_deg": 0.0},
    )
    assert (tmp_path / "openfoam").is_dir()
    assert (tmp_path / "openfoam" / "system" / "blockMeshDict").exists()
    assert (tmp_path / "openfoam" / "system" / "snappyHexMeshDict").exists()
    assert (tmp_path / "openfoam" / "constant" / "polyMesh").exists()
    assert (tmp_path / "openfoam" / "0").is_dir()
