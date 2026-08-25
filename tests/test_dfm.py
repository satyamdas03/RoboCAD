"""Tests for the DFM rule engine."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from ai_cad.dfm import analyze_dfm


def _cube_stl(path: Path, size: float = 10.0, hole_diameter: float | None = None) -> Path:
    """Create a watertight cube STL, optionally with a through-hole."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if hole_diameter is None:
        mesh = trimesh.creation.box(extents=[size, size, size])
    else:
        box = trimesh.creation.box(extents=[size, size, size])
        hole = trimesh.creation.cylinder(radius=hole_diameter / 2, height=size + 1, sections=32)
        mesh = box.difference(hole)
    mesh.export(str(path))
    return path


def test_dfm_flags_thin_wall(tmp_path: Path):
    stl = tmp_path / "thin.stl"
    mesh = trimesh.creation.box(extents=[10, 10, 0.2])
    mesh.export(str(stl))
    report = analyze_dfm(stl, min_wall_thickness_mm=0.8)
    assert not report.valid
    assert "min_wall_thickness" in report.failed_rules


def test_dfm_passes_thick_wall(tmp_path: Path):
    stl = _cube_stl(tmp_path / "thick.stl", size=10.0)
    report = analyze_dfm(stl, min_wall_thickness_mm=0.8)
    assert report.valid
    assert report.min_wall_thickness_mm is not None
    assert report.min_wall_thickness_mm >= 0.8


def test_dfm_flags_small_hole(tmp_path: Path):
    stl = _cube_stl(tmp_path / "small_hole.stl", size=10.0, hole_diameter=1.0)
    report = analyze_dfm(stl, min_hole_diameter_mm=2.0)
    assert "min_hole_diameter" in [r.name for r in report.rules if r.severity == "warning"]


def test_dfm_missing_file():
    report = analyze_dfm(Path("/does/not/exist.stl"))
    assert not report.valid
    assert any(r.name == "load" for r in report.rules)
