"""Tests for the Phase 11 assembly system."""
from __future__ import annotations

import math

import pytest

pytestmark = [pytest.mark.heavy, pytest.mark.slow]

from ai_cad.assembly import compute_instance_transforms, transpile_assembly
from ai_cad.feature_tree import (
    Assembly,
    CoordinateSystem,
    Feature,
    FeatureTree,
    Instance,
    Mate,
    MateEntity,
    Parameter,
    Part,
    PlaneReference,
    Sketch,
    SketchEntity,
)


def _make_bracket_part(part_id="bracket") -> Part:
    return Part(
        id=part_id,
        sketches=[
            Sketch(
                id="profile",
                plane=PlaneReference(type="base", name="XY"),
                entities=[
                    SketchEntity(type="rectangle", id="base", center=(0, 0), width=40, height=20),
                ],
            )
        ],
        features=[
            Feature(id="extrude1", type="extrude", sketch_id="profile", parameters={"amount": 5, "mode": "add"}),
        ],
    )


def _make_pin_part(part_id="pin") -> Part:
    return Part(
        id=part_id,
        sketches=[
            Sketch(
                id="profile",
                plane=PlaneReference(type="base", name="XY"),
                entities=[SketchEntity(type="circle", id="shaft", center=(0, 0), radius=4)],
            )
        ],
        features=[
            Feature(id="extrude1", type="extrude", sketch_id="profile", parameters={"amount": 20, "mode": "add"}),
        ],
    )


def test_compute_explicit_transform():
    tree = FeatureTree(
        design_id="asm1",
        prompt="two parts",
        created_at="2026-08-25T00:00:00Z",
        parts=[_make_bracket_part(), _make_pin_part()],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="i1", part_id="bracket", transform={"translation": [0, 0, 0], "rotation": [0, 0, 0]}),
                    Instance(id="i2", part_id="pin", transform={"translation": [10, 0, 0], "rotation": [0, 0, 0]}),
                ],
            )
        ],
    )
    transforms = compute_instance_transforms(tree, tree.assemblies[0])
    assert transforms["i1"][:3, 3].tolist() == pytest.approx([0, 0, 0], abs=0.01)
    assert transforms["i2"][:3, 3].tolist() == pytest.approx([10, 0, 0], abs=0.01)


def test_compute_coincident_mate_aligns_origins():
    tree = FeatureTree(
        design_id="asm1",
        prompt="coincident test",
        created_at="2026-08-25T00:00:00Z",
        parts=[_make_bracket_part(), _make_pin_part()],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="i1", part_id="bracket", transform={"translation": [0, 0, 0]}),
                    Instance(id="i2", part_id="pin", transform={"translation": [50, 0, 0]}),
                ],
                mates=[
                    Mate(
                        id="m1",
                        type="coincident",
                        entities=[MateEntity(instance_id="i1"), MateEntity(instance_id="i2")],
                    )
                ],
            )
        ],
    )
    transforms = compute_instance_transforms(tree, tree.assemblies[0])
    o1 = transforms["i1"][:3, 3]
    o2 = transforms["i2"][:3, 3]
    assert o1.tolist() == pytest.approx(o2.tolist(), abs=0.01)


def test_compute_distance_mate_offsets():
    tree = FeatureTree(
        design_id="asm1",
        prompt="distance test",
        created_at="2026-08-25T00:00:00Z",
        parameters=[Parameter(name="offset", value=30, unit="mm")],
        parts=[_make_bracket_part(), _make_pin_part()],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="i1", part_id="bracket", transform={"translation": [0, 0, 0]}),
                    Instance(id="i2", part_id="pin", transform={"translation": [0, 0, 0]}),
                ],
                mates=[
                    Mate(
                        id="m1",
                        type="distance",
                        entities=[MateEntity(instance_id="i1"), MateEntity(instance_id="i2")],
                        parameters={"distance": "offset"},
                    )
                ],
            )
        ],
    )
    transforms = compute_instance_transforms(tree, tree.assemblies[0])
    o1 = transforms["i1"][:3, 3]
    o2 = transforms["i2"][:3, 3]
    dist = math.hypot(*(o2 - o1))
    assert dist == pytest.approx(30, abs=0.1)


def test_transpile_assembly_emits_compound():
    tree = FeatureTree(
        design_id="asm1",
        prompt="hinged bracket",
        created_at="2026-08-25T00:00:00Z",
        parts=[_make_bracket_part(), _make_pin_part()],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="i1", part_id="bracket"),
                    Instance(id="i2", part_id="pin", transform={"translation": [15, 0, 0]}),
                ],
            )
        ],
    )
    code = transpile_assembly(tree, tree.assemblies[0])
    assert "from build123d import *" in code
    assert "with BuildPart() as part_0:" in code
    assert "with BuildPart() as part_1:" in code
    assert "result = Compound(children=[" in code
    assert "part_0.part.moved(" in code
    assert "part_1.part.moved(" in code


def test_transpile_assembly_executes(tmp_path):
    tree = FeatureTree(
        design_id="asm1",
        prompt="executed assembly",
        created_at="2026-08-25T00:00:00Z",
        parts=[_make_bracket_part(), _make_pin_part()],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="i1", part_id="bracket"),
                    Instance(id="i2", part_id="pin", transform={"translation": [15, 0, 0]}),
                ],
            )
        ],
    )
    from ai_cad.executor import execute_code

    code = transpile_assembly(tree, tree.assemblies[0])
    result = execute_code(code, timeout=60, output_dir=tmp_path)
    assert result["success"], result.get("traceback", result.get("error"))
    assert result.get("volume") > 0


def test_transpile_assembly_single_part_fallback():
    tree = FeatureTree(
        design_id="single",
        prompt="single part",
        created_at="2026-08-25T00:00:00Z",
        parts=[_make_bracket_part()],
    )
    code = transpile_assembly(tree)
    assert "result = part.part" in code


def test_parallel_mate_aligns_z_axes():
    tree = FeatureTree(
        design_id="asm1",
        prompt="parallel test",
        created_at="2026-08-25T00:00:00Z",
        parts=[_make_bracket_part(), _make_pin_part()],
        coordinate_systems=[
            CoordinateSystem(
                id="cs1",
                origin=(0, 0, 0),
                x_axis=(1, 0, 0),
                y_axis=(0, 0, 1),
                z_axis=(0, -1, 0),
            )
        ],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="i1", part_id="bracket", transform={"translation": [0, 0, 0]}),
                    Instance(id="i2", part_id="pin", transform={"translation": [0, 0, 0], "rotation": [90, 0, 0]}),
                ],
                mates=[
                    Mate(
                        id="m1",
                        type="parallel",
                        entities=[
                            MateEntity(instance_id="i1", csys_id="cs1"),
                            MateEntity(instance_id="i2"),
                        ],
                    )
                ],
            )
        ],
    )
    transforms = compute_instance_transforms(tree, tree.assemblies[0])
    z1 = transforms["i1"][:3, 2]
    z2 = transforms["i2"][:3, 2]
    # After parallel mate, z axes should align.
    assert z1.tolist() == pytest.approx(z2.tolist(), abs=0.01)


def test_transpile_assembly_duplicate_part_instances(tmp_path):
    """Placing the same part twice must not raise an anytree duplicate-child error."""
    tree = FeatureTree(
        design_id="dup_asm",
        prompt="two instances of the same bracket",
        created_at="2026-08-25T00:00:00Z",
        parts=[_make_bracket_part()],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="i1", part_id="bracket"),
                    Instance(id="i2", part_id="bracket", transform={"translation": [30, 0, 0]}),
                ],
            )
        ],
    )
    from ai_cad.executor import execute_code

    code = transpile_assembly(tree, tree.assemblies[0])
    result = execute_code(code, timeout=60, output_dir=tmp_path)
    assert result["success"], result.get("traceback", result.get("error"))
    assert result.get("volume") > 0
