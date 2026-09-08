"""Tests for Phase 28C deep solver geometry prep and meshing layer.

These tests use synthetic box geometries and are designed to pass even when
Gmsh and Netgen are not installed, by exercising stubs and graceful error
handling paths.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from ai_cad.solvers.geometry_prep import (
    GeometryPrepResult,
    SurfaceLabel,
    label_surfaces_trimesh,
    load_stl,
    prepare_geometry,
    reject_degenerate,
)
from ai_cad.solvers.meshing import (
    MeshResult,
    tet_mesh_with_gmsh,
    tet_mesh_with_netgen,
    tetrahedral_mesh,
    write_openfoam_case_dir,
)


def _box_trimesh(extents: tuple[float, float, float] = (10.0, 10.0, 10.0)) -> trimesh.Trimesh:
    return trimesh.creation.box(extents=extents)


def _write_box_stl(tmp_path: Path) -> Path:
    stl_path = tmp_path / "box.stl"
    _box_trimesh().export(stl_path)
    return stl_path


class TestGeometryPrep:
    def test_load_stl_returns_single_body_mesh(self, tmp_path: Path):
        stl_path = _write_box_stl(tmp_path)
        mesh = load_stl(stl_path)
        assert isinstance(mesh, trimesh.Trimesh)
        assert mesh.is_watertight
        assert len(mesh.faces) == 12

    def test_reject_degenerate_accepts_good_box(self):
        mesh = _box_trimesh()
        ok, issues = reject_degenerate(mesh)
        assert ok
        assert issues == []

    def test_reject_degenerate_rejects_degenerate(self):
        vertices = np.array(
            [
                [0, 0, 0],
                [1, 0, 0],
                [0, 1, 0],
                [0, 0, 0],
                [1, 0, 0],
                [0, 0, 0],
            ],
            dtype=float,
        )
        faces = np.array([[0, 1, 2], [3, 4, 5]])
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        ok, issues = reject_degenerate(mesh)
        assert not ok
        assert any("degenerate" in issue.lower() for issue in issues)

    def test_label_surfaces_box_default_flow(self, tmp_path: Path):
        mesh = load_stl(_write_box_stl(tmp_path))
        labels = label_surfaces_trimesh(mesh)
        values = set(labels.values())
        assert SurfaceLabel.INLET in values
        assert SurfaceLabel.OUTLET in values
        assert SurfaceLabel.LOAD in values
        assert SurfaceLabel.FIXTURE in values
        # A cube has 12 triangular faces; 4 are special, the rest are walls.
        wall_count = sum(1 for v in labels.values() if v == SurfaceLabel.WALL)
        assert wall_count == 8

    def test_label_surfaces_box_custom_flow_direction(self, tmp_path: Path):
        mesh = load_stl(_write_box_stl(tmp_path))
        labels = label_surfaces_trimesh(mesh, flow_direction=np.array([0, 0, 1]))
        # Centroid min/max along +Z should place inlet on bottom, outlet on top.
        assert labels is not None
        assert SurfaceLabel.INLET in labels.values()
        assert SurfaceLabel.OUTLET in labels.values()

    def test_prepare_geometry_stl_success(self, tmp_path: Path):
        stl_path = _write_box_stl(tmp_path)
        result = prepare_geometry(stl_path)
        assert isinstance(result, GeometryPrepResult)
        assert result.success
        assert result.mesh is not None
        assert SurfaceLabel.INLET in result.labels.values()
        assert "vertices" in result.details
        assert result.details["is_watertight"] is True

    def test_prepare_geometry_missing_file(self, tmp_path: Path):
        result = prepare_geometry(tmp_path / "missing.stl")
        assert not result.success
        assert result.errors
        assert not result.labels

    def test_prepare_geometry_unsupported_format(self, tmp_path: Path):
        bad_path = tmp_path / "model.obj"
        bad_path.write_text("# dummy\n")
        result = prepare_geometry(bad_path)
        assert not result.success
        assert any("Unsupported geometry format" in err for err in result.errors)


class TestMeshing:
    def test_tet_mesh_with_gmsh_missing_is_graceful(self, tmp_path: Path):
        mesh = _box_trimesh()
        result = tet_mesh_with_gmsh(mesh, tmp_path / "gmsh", mesh_size=1.0)
        assert isinstance(result, MeshResult)
        assert not result.success
        assert any("not installed" in err.lower() or "gmsh" in err.lower() for err in result.errors)
        assert result.details.get("tool") == "gmsh"

    def test_tet_mesh_with_netgen_missing_is_graceful(self, tmp_path: Path):
        mesh = _box_trimesh()
        result = tet_mesh_with_netgen(mesh, tmp_path / "netgen", mesh_size=1.0)
        assert isinstance(result, MeshResult)
        assert not result.success
        assert any("not installed" in err.lower() or "netgen" in err.lower() for err in result.errors)
        assert result.details.get("tool") == "netgen"

    def test_tetrahedral_mesh_attempts_fallback_or_reports_missing(self, tmp_path: Path):
        mesh = _box_trimesh()
        result = tetrahedral_mesh(mesh, tmp_path / "vol", mesh_size=1.0, prefer="gmsh")
        assert isinstance(result, MeshResult)
        if not result.success:
            assert result.errors
            assert any(
                "gmsh" in err.lower() or "netgen" in err.lower() for err in result.errors
            )
            assert result.details.get("fallback_exhausted") is True

    def test_tetrahedral_mesh_invalid_prefer(self, tmp_path: Path):
        mesh = _box_trimesh()
        result = tetrahedral_mesh(mesh, tmp_path / "vol", prefer="foo")
        assert not result.success
        assert any("Invalid preferred mesher" in err for err in result.errors)

    def test_write_openfoam_case_dir_creates_required_files(self, tmp_path: Path):
        mesh = _box_trimesh()
        result = write_openfoam_case_dir(mesh, tmp_path / "foam_case")
        assert isinstance(result, MeshResult)
        assert result.success
        case = result.solver_case_path
        assert case is not None
        assert (case / "system" / "blockMeshDict").exists()
        assert (case / "system" / "snappyHexMeshDict").exists()
        assert (case / "constant" / "polyMesh").is_dir()
        assert (case / "0").is_dir()
        assert (case / "README.md").exists()
        assert (case / "surface_mesh.stl").exists()
        blockmesh_text = (case / "system" / "blockMeshDict").read_text()
        assert "vertices" in blockmesh_text and "blocks" in blockmesh_text

    def test_write_openfoam_case_dir_from_invalid_input(self, tmp_path: Path):
        result = write_openfoam_case_dir("not-a-shape", tmp_path / "foam_case")
        assert not result.success
        assert any("Unsupported input type" in err for err in result.errors)

    def test_mesh_result_model_dump(self, tmp_path: Path):
        result = MeshResult(
            success=True,
            mesh_path=tmp_path / "mesh.msh",
            format="msh",
            solver="openfoam",
            solver_case_path=tmp_path / "foam",
            errors=[],
            details={"x": 1},
        )
        data = result.model_dump()
        assert data["success"] is True
        assert data["format"] == "msh"
        assert data["mesh_path"] == str(tmp_path / "mesh.msh")
        assert data["solver_case_path"] == str(tmp_path / "foam")
