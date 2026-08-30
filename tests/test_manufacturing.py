"""Tests for ai_cad.manufacturing manufacturability analysis."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

pytestmark = [pytest.mark.heavy, pytest.mark.slow]

from ai_cad.manufacturing import analyze_model


def _make_cube_stl(tmp_path: Path, size: float = 10.0) -> Path:
    """Write a simple cube STL for testing."""
    mesh = trimesh.creation.box(extents=(size, size, size))
    path = tmp_path / "cube.stl"
    mesh.export(str(path))
    return path


def test_analyze_missing_file():
    report = analyze_model("/nonexistent/file.stl")
    assert report["valid"] is False
    assert any("not found" in err for err in report["errors"])


def test_analyze_cube(tmp_path):
    stl = _make_cube_stl(tmp_path, size=10.0)
    report = analyze_model(stl)
    assert report["valid"] is True
    assert report["bounds_mm"] == pytest.approx((10.0, 10.0, 10.0), abs=0.01)
    assert report["volume_cm3"] == pytest.approx(1.0, abs=0.01)
    assert report["surface_area_cm2"] == pytest.approx(6.0, abs=0.01)
    assert report["estimated_print_time_min"] > 0
    assert report["overhang_ratio"] == 0.0


def test_analyze_overhang_bracket(tmp_path):
    # A 20x10x5 block with a 5-unit cantilever overhang.
    base = trimesh.creation.box(extents=(20.0, 10.0, 5.0))
    # Shift so the bottom is at z=0.
    base.apply_translation((10.0, 5.0, 2.5))
    overhang = trimesh.creation.box(extents=(10.0, 10.0, 5.0))
    overhang.apply_translation((17.5, 5.0, 7.5))
    mesh = base + overhang
    stl = tmp_path / "bracket.stl"
    mesh.export(str(stl))

    report = analyze_model(stl)
    assert report["valid"] is True
    assert report["overhang_ratio"] > 0.0
    assert report["min_feature_size_mm"] is not None


def test_analyze_hole_detection(tmp_path):
    # A plate with a cylindrical hole through it, created via boolean difference.
    plate = trimesh.creation.box(extents=(20.0, 20.0, 3.0))
    hole = trimesh.creation.cylinder(radius=2.0, height=4.0, sections=32)
    mesh = trimesh.boolean.difference([plate, hole], engine="manifold")
    stl = tmp_path / "hole_plate.stl"
    mesh.export(str(stl))

    report = analyze_model(stl)
    assert report["valid"] is True
    assert report["min_hole_diameter_mm"] is not None
    assert report["min_hole_diameter_mm"] < 5.0
