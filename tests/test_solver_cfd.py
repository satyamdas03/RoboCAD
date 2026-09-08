"""Tests for the Phase 28C OpenFOAM CFD solver adapter."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

def _load_adapter():
    """Import the adapter, falling back to direct file loading if the package
    ``__init__.py`` is in a temporarily inconsistent state.
    """
    try:
        from ai_cad.solvers.openfoam_adapter import (
            OpenFOAMCaseResult,
            build_openfoam_case,
            parse_force_coefficients,
            run_openfoam_case,
        )

        return OpenFOAMCaseResult, build_openfoam_case, parse_force_coefficients, run_openfoam_case
    except Exception:
        import importlib.util
        import sys
        import types

        adapter_path = (
            Path(__file__).resolve().parent.parent
            / "ai_cad"
            / "solvers"
            / "openfoam_adapter.py"
        )
        pkg_name = "ai_cad.solvers"
        sys.modules.pop(pkg_name, None)
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(adapter_path.parent)]
        sys.modules[pkg_name] = pkg
        spec = importlib.util.spec_from_file_location(
            f"{pkg_name}.openfoam_adapter", str(adapter_path)
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        pkg.openfoam_adapter = mod
        spec.loader.exec_module(mod)
        return mod.OpenFOAMCaseResult, mod.build_openfoam_case, mod.parse_force_coefficients, mod.run_openfoam_case


OpenFOAMCaseResult, build_openfoam_case, parse_force_coefficients, run_openfoam_case = _load_adapter()


def _make_simple_wing_mesh() -> trimesh.Trimesh:
    """Return a thin rectangular slab that acts as a 2-D wing."""
    mesh = trimesh.creation.box(extents=[2.0, 0.4, 0.05])
    mesh.apply_translation([0.5, 0.0, 0.0])
    return mesh


def _make_boundary_conditions() -> dict:
    return {
        "inlet": {
            "U": {"type": "fixedValue", "value": [10.0, 0.0, 0.0]},
            "p": {"type": "zeroGradient"},
        },
        "outlet": {
            "p": {"type": "fixedValue", "value": 0.0},
            "U": {"type": "zeroGradient"},
        },
        "top": {
            "U": {"type": "slip"},
            "p": {"type": "zeroGradient"},
        },
        "bottom": {
            "U": {"type": "slip"},
            "p": {"type": "zeroGradient"},
        },
        "front": {
            "U": {"type": "slip"},
            "p": {"type": "zeroGradient"},
        },
        "back": {
            "U": {"type": "slip"},
            "p": {"type": "zeroGradient"},
        },
        "model": {
            "U": {"type": "noSlip"},
            "p": {"type": "zeroGradient"},
        },
    }


def test_build_openfoam_case_creates_expected_files(tmp_path: Path):
    case_dir = tmp_path / "wing_case"
    mesh = _make_simple_wing_mesh()
    bc = _make_boundary_conditions()
    reference = {
        "flow_velocity_ms": 10.0,
        "angle_of_attack_deg": 3.0,
        "characteristic_length_m": 1.0,
    }

    result = build_openfoam_case(
        surface_mesh=mesh,
        case_dir=case_dir,
        boundary_conditions=bc,
        reference_values=reference,
    )

    assert isinstance(result, OpenFOAMCaseResult)
    assert result.success, f"Case build failed: {result.errors}"
    assert result.case_dir == case_dir
    assert {Path(f).as_posix() for f in result.files_written} >= {
        "system/blockMeshDict",
        "system/snappyHexMeshDict",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
        "constant/transportProperties",
        "constant/turbulenceProperties",
        "constant/triSurface/model.stl",
        "0/p",
        "0/U",
        "README.md",
    }

    assert (case_dir / "system" / "blockMeshDict").exists()
    assert (case_dir / "system" / "snappyHexMeshDict").exists()
    assert (case_dir / "system" / "controlDict").exists()
    assert (case_dir / "constant" / "triSurface" / "model.stl").exists()
    assert (case_dir / "0" / "p").exists()
    assert (case_dir / "0" / "U").exists()


def test_block_mesh_dict_encloses_surface_and_has_boundary_patches(tmp_path: Path):
    case_dir = tmp_path / "box_case"
    mesh = trimesh.creation.box(extents=[1.0, 1.0, 1.0])
    bc = _make_boundary_conditions()

    result = build_openfoam_case(
        surface_mesh=mesh,
        case_dir=case_dir,
        boundary_conditions=bc,
    )
    assert result.success

    text = (case_dir / "system" / "blockMeshDict").read_text()
    assert "convertToMeters 1.0;" in text
    assert "hex (0 1 2 3 4 5 6 7)" in text
    for patch in ("inlet", "outlet", "top", "bottom", "front", "back"):
        assert f"    {patch}" in text, f"Missing patch {patch}"


def test_snappy_hex_mesh_dict_references_surface_stl(tmp_path: Path):
    case_dir = tmp_path / "box_case"
    mesh = trimesh.creation.box(extents=[1.0, 1.0, 1.0])
    bc = _make_boundary_conditions()

    result = build_openfoam_case(
        surface_mesh=mesh,
        case_dir=case_dir,
        boundary_conditions=bc,
        mesh_name="wing.stl",
    )
    assert result.success

    text = (case_dir / "system" / "snappyHexMeshDict").read_text()
    assert "castellatedMesh true;" in text
    assert "snap true;" in text
    assert "constant/triSurface/wing.stl" in text
    assert "type triSurfaceMesh;" in text


def test_boundary_condition_files_have_expected_types(tmp_path: Path):
    case_dir = tmp_path / "box_case"
    mesh = trimesh.creation.box(extents=[1.0, 1.0, 1.0])
    bc = _make_boundary_conditions()

    result = build_openfoam_case(
        surface_mesh=mesh,
        case_dir=case_dir,
        boundary_conditions=bc,
    )
    assert result.success

    p_text = (case_dir / "0" / "p").read_text()
    u_text = (case_dir / "0" / "U").read_text()

    assert "internalField" in p_text
    assert "boundaryField" in p_text
    assert "inlet" in p_text and "zeroGradient" in p_text
    assert "outlet" in p_text and "fixedValue" in p_text

    assert "internalField" in u_text
    assert "boundaryField" in u_text
    assert "inlet" in u_text and "fixedValue" in u_text
    assert "model" in u_text and "noSlip" in u_text

    # U should be a vector field and use a vector uniform value.
    assert "dimensions\n    (0 1 -1 0 0 0 0);" in u_text
    assert "class       volVectorField;" in u_text
    assert "uniform (10.0 0.0 0.0)" in u_text


def test_reference_values_influence_internal_u(tmp_path: Path):
    case_dir = tmp_path / "wing_case"
    mesh = _make_simple_wing_mesh()
    bc = _make_boundary_conditions()

    result = build_openfoam_case(
        surface_mesh=mesh,
        case_dir=case_dir,
        boundary_conditions=bc,
        reference_values={
            "flow_velocity_ms": 20.0,
            "angle_of_attack_deg": 90.0,
        },
    )
    assert result.success
    u_text = (case_dir / "0" / "U").read_text()
    # At 90 degrees the x component should be ~0 and y ~20.
    assert "uniform (0.0 20.0 0.0)" in u_text


def test_run_openfoam_case_is_graceful_when_openfoam_missing(tmp_path: Path, monkeypatch):
    case_dir = tmp_path / "case_no_solver"
    mesh = _make_simple_wing_mesh()
    bc = _make_boundary_conditions()

    build_openfoam_case(
        surface_mesh=mesh,
        case_dir=case_dir,
        boundary_conditions=bc,
    )

    # Force the adapter to believe no OpenFOAM runner is present.
    monkeypatch.setattr(
        "ai_cad.solvers.openfoam_adapter._local_openfoam_available", lambda _=None: False
    )
    monkeypatch.setattr(
        "ai_cad.solvers.openfoam_adapter._docker_available", lambda: False
    )

    result = run_openfoam_case(case_dir)
    assert isinstance(result, OpenFOAMCaseResult)
    assert result.openfoam_detected is False
    assert result.run_success is False
    assert any("OpenFOAM not detected" in e for e in result.errors)


def test_parse_force_coefficients_reads_latest_force_coeffs(tmp_path: Path):
    coeffs_dir = tmp_path / "postProcessing" / "forceCoeffs" / "0"
    coeffs_dir.mkdir(parents=True)
    coeffs_file = coeffs_dir / "forceCoeffs.dat"
    coeffs_file.write_text(
        "# Time Cd Cl CmFront CmRear\n"
        "100 0.42 0.12 0.01 -0.01\n"
        "200 0.45 0.15 0.02 -0.02\n",
        encoding="utf-8",
    )

    coeffs = parse_force_coefficients(tmp_path)
    assert coeffs["Time"] == 200.0
    assert coeffs["Cd"] == 0.45
    assert coeffs["Cl"] == 0.15


def test_parse_force_coefficients_fallback_columns(tmp_path: Path):
    forces_dir = tmp_path / "postProcessing" / "forces" / "0"
    forces_dir.mkdir(parents=True)
    forces_file = forces_dir / "forces.dat"
    forces_file.write_text(
        "# header ignored\n"
        "50 0.10 0.05\n"
        "100 0.12 0.07\n",
        encoding="utf-8",
    )

    coeffs = parse_force_coefficients(tmp_path)
    assert coeffs["time"] == 100.0
    assert coeffs["Cd"] == 0.12
    assert coeffs["Cl"] == 0.07
