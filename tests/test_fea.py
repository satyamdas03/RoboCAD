"""Tests for the FEA wrapper."""
from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

from ai_cad.fea import run_static_analysis


def test_fea_bracket(tmp_path: Path):
    stl = tmp_path / "bracket.stl"
    mesh = trimesh.creation.box(extents=[40, 10, 20])
    mesh.export(str(stl))
    result = run_static_analysis(stl, fixed_face="-x", load_direction=(0, 0, -1), load_magnitude_n=50.0, material="PLA")
    assert result.success
    assert result.max_stress_mpa is not None
    assert result.max_displacement_mm is not None
    assert result.safety_factor is not None


def test_fea_missing_file():
    result = run_static_analysis(Path("/does/not/exist.stl"))
    assert not result.success
    assert len(result.errors) > 0


def test_fea_unknown_face():
    stl = Path("/tmp/dummy.stl")
    result = run_static_analysis(stl, fixed_face="abc")
    assert not result.success
