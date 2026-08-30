"""Tests for Phase 19 assembly-level collision/clearance checks."""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.heavy, pytest.mark.slow]

from ai_cad.assembly_collision import check_assembly_collision, CollisionReport
from ai_cad.feature_tree import (
    Assembly,
    Feature,
    FeatureTree,
    Instance,
    Part,
    PlaneReference,
    Sketch,
    SketchEntity,
)


def _make_cube_part(part_id: str = "cube", size: float = 10.0) -> Part:
    half = size / 2
    return Part(
        id=part_id,
        sketches=[
            Sketch(
                id="profile",
                plane=PlaneReference(type="base", name="XY"),
                entities=[
                    SketchEntity(
                        type="rectangle", id="base", center=(0, 0), width=size, height=size
                    )
                ],
            )
        ],
        features=[
            Feature(
                id="extrude1",
                type="extrude",
                sketch_id="profile",
                parameters={"amount": size, "mode": "add"},
            )
        ],
    )


def test_two_separated_cubes_report_clearance(tmp_path):
    tree = FeatureTree(
        design_id="clearance_asm",
        prompt="two separated cubes",
        created_at="2026-08-29T00:00:00Z",
        parts=[_make_cube_part("cube", size=10.0)],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="i1", part_id="cube"),
                    Instance(
                        id="i2",
                        part_id="cube",
                        transform={"translation": [20, 0, 0]},
                    ),
                ],
            )
        ],
    )
    reports = check_assembly_collision(tree, tmp_path, samples=500)
    assert len(reports) == 1
    report = reports[0]
    assert isinstance(report, CollisionReport)
    assert {report.instance_a, report.instance_b} == {"i1", "i2"}
    assert report.classification == "clearance"
    assert report.min_clearance_mm > 0
    # Two 10 mm cubes centered 20 mm apart in X have a 10 mm face-to-face gap.
    assert report.min_clearance_mm == pytest.approx(10.0, abs=0.5)


def test_two_overlapping_cubes_report_interference(tmp_path):
    tree = FeatureTree(
        design_id="interference_asm",
        prompt="two overlapping cubes",
        created_at="2026-08-29T00:00:00Z",
        parts=[_make_cube_part("cube", size=10.0)],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="i1", part_id="cube"),
                    Instance(
                        id="i2",
                        part_id="cube",
                        transform={"translation": [5, 0, 0]},
                    ),
                ],
            )
        ],
    )
    reports = check_assembly_collision(tree, tmp_path, samples=500)
    assert len(reports) == 1
    report = reports[0]
    assert report.classification == "interference"
    assert report.min_clearance_mm < 0


def test_single_instance_returns_empty_list(tmp_path):
    tree = FeatureTree(
        design_id="single_asm",
        prompt="single cube",
        created_at="2026-08-29T00:00:00Z",
        parts=[_make_cube_part("cube", size=10.0)],
        assemblies=[
            Assembly(
                id="a1",
                instances=[Instance(id="i1", part_id="cube")],
            )
        ],
    )
    reports = check_assembly_collision(tree, tmp_path)
    assert reports == []


def test_no_assembly_returns_empty_list(tmp_path):
    tree = FeatureTree(
        design_id="no_asm",
        prompt="no assembly",
        created_at="2026-08-29T00:00:00Z",
        parts=[_make_cube_part("cube", size=10.0)],
    )
    reports = check_assembly_collision(tree, tmp_path)
    assert reports == []
