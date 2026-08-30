"""Tests for the RoboCAD mesh-quality pre-checker."""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest
import trimesh

pytestmark = [pytest.mark.heavy, pytest.mark.slow]

from ai_cad.mesh_quality import check_mesh_quality, load_mesh


def test_load_good_box_stl(tmp_path: Path):
    mesh = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
    stl_path = tmp_path / "box.stl"
    mesh.export(stl_path)
    loaded = load_mesh(stl_path)
    assert loaded is not None
    assert loaded.is_watertight


def test_check_mesh_quality_good_box(tmp_path: Path):
    mesh = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
    stl_path = tmp_path / "box.stl"
    mesh.export(stl_path)
    report = check_mesh_quality(stl_path)
    assert report.is_suitable_for_solver is True
    assert report.triangle_count > 0
    assert report.watertight is True
    assert report.non_manifold_edges == 0
    assert report.degenerate_triangles == 0
    assert report.high_aspect_ratio_triangles == 0


def test_check_mesh_quality_detects_degenerate(tmp_path: Path):
    # Two valid triangles plus a zero-area degenerate one.
    vertices = np.array([
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 0],  # duplicate of first vertex
        [1, 0, 0],
        [0, 0, 0],
    ], dtype=float)
    faces = np.array([[0, 1, 2], [3, 4, 5]])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    stl_path = tmp_path / "degenerate.stl"
    mesh.export(stl_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        report = check_mesh_quality(stl_path)
    assert report.is_suitable_for_solver is False
    assert report.degenerate_triangles > 0


def test_check_mesh_quality_missing_file():
    report = check_mesh_quality("/nonexistent/path/model.stl")
    assert report.is_suitable_for_solver is False
    assert any("Failed to load mesh file" in issue for issue in report.issues)


def test_check_mesh_quality_extreme_size(tmp_path: Path):
    mesh = trimesh.creation.box(extents=(1e9, 1e9, 1e9))
    stl_path = tmp_path / "huge.stl"
    mesh.export(stl_path)
    report = check_mesh_quality(stl_path)
    assert report.is_suitable_for_solver is False
    assert any("too large" in issue for issue in report.issues)
