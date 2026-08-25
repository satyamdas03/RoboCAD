"""Tests for tolerance/fit checks."""
from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

from ai_cad.tolerances import check_fit


def _shaft_and_hole_stls(tmp_path: Path, shaft_d: float, hole_d: float, length: float = 20.0) -> tuple[Path, Path]:
    shaft = trimesh.creation.cylinder(radius=shaft_d / 2, height=length, sections=32)
    hole_cyl = trimesh.creation.cylinder(radius=hole_d / 2, height=length + 1, sections=32)
    box = trimesh.creation.box(extents=[hole_d + 4, hole_d + 4, length + 1])
    hole_part = box.difference(hole_cyl)

    shaft_path = tmp_path / "shaft.stl"
    hole_path = tmp_path / "hole.stl"
    shaft.export(str(shaft_path))
    hole_part.export(str(hole_path))
    return shaft_path, hole_path


def test_clearance_fit(tmp_path: Path):
    shaft, hole = _shaft_and_hole_stls(tmp_path, shaft_d=5.8, hole_d=6.0)
    fit = check_fit(shaft, hole, name="shaft_hole", samples=500)
    assert fit.classification == "clearance"
    assert fit.min_clearance_mm > 0


def test_interference_fit(tmp_path: Path):
    shaft, hole = _shaft_and_hole_stls(tmp_path, shaft_d=6.2, hole_d=6.0)
    fit = check_fit(shaft, hole, name="shaft_hole", samples=500)
    assert fit.classification == "interference"
    assert fit.min_clearance_mm < 0


def test_transition_fit(tmp_path: Path):
    # Equal nominal sizes are classified as transition if within thresholds.
    shaft, hole = _shaft_and_hole_stls(tmp_path, shaft_d=6.0, hole_d=6.0)
    fit = check_fit(shaft, hole, name="shaft_hole", samples=500)
    assert fit.classification in ("transition", "interference")
