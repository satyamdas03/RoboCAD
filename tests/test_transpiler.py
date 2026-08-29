"""Tests for the feature-tree to build123d transpiler."""
from __future__ import annotations

import re

import pytest

from ai_cad.feature_tree import Feature, FeatureTree, Parameter, Part, PlaneReference, Sketch, SketchEntity
from ai_cad.transpiler import transpile


def _base_plate_tree(width=50, depth=30, thickness=5, hole_diameter=4) -> FeatureTree:
    return FeatureTree(
        design_id="test",
        prompt="base plate",
        created_at="2026-08-25T00:00:00Z",
        parameters=[
            Parameter(name="width", value=width, unit="mm"),
            Parameter(name="depth", value=depth, unit="mm"),
            Parameter(name="thickness", value=thickness, unit="mm"),
            Parameter(name="hole_diameter", value=hole_diameter, unit="mm"),
        ],
        parts=[
            Part(
                id="plate",
                sketches=[
                    Sketch(
                        id="profile",
                        plane=PlaneReference(type="base", name="XY"),
                        entities=[
                            SketchEntity(
                                type="rectangle",
                                id="rect1",
                                center=(0, 0),
                                width="width",
                                height="depth",
                            ),
                            SketchEntity(
                                type="circle",
                                id="hole1",
                                center=(15, 10),
                                radius="hole_diameter / 2",
                            ),
                        ],
                    )
                ],
                features=[
                    Feature(
                        id="base",
                        type="extrude",
                        sketch_id="profile",
                        parameters={"amount": "thickness", "mode": "add"},
                    ),
                    Feature(
                        id="cut_hole",
                        type="extrude",
                        sketch_id="profile",
                        parameters={"amount": "thickness", "mode": "subtract"},
                    ),
                ],
            )
        ],
    )


def test_transpile_includes_parameters():
    code = transpile(_base_plate_tree())
    assert "width = 50" in code
    assert "depth = 30" in code
    assert "thickness = 5" in code


def test_transpile_creates_buildpart_context():
    code = transpile(_base_plate_tree())
    assert "with BuildPart() as part:" in code
    assert "result = part.part" in code


def test_transpile_emits_rectangle_and_circle():
    code = transpile(_base_plate_tree())
    assert "Rectangle(width=width, height=depth" in code
    assert "Circle(radius=hole_diameter / 2)" in code


def test_transpile_extrude_add_and_subtract():
    code = transpile(_base_plate_tree())
    assert "Mode.ADD" in code
    assert "Mode.SUBTRACT" in code


def test_transpile_no_parts_raises():
    tree = FeatureTree(design_id="empty", prompt="empty", created_at="2026-08-25T00:00:00Z")
    with pytest.raises(ValueError):
        transpile(tree)


def test_transpile_unsupported_entity():
    tree = _base_plate_tree()
    tree.parts[0].sketches[0].entities[0].type = "spline"
    with pytest.raises(ValueError):
        transpile(tree)


def test_transpile_unsupported_feature():
    tree = _base_plate_tree()
    tree.parts[0].features[0].type = "loft"
    with pytest.raises(ValueError):
        transpile(tree)


def test_transpile_revolve():
    tree = FeatureTree(
        design_id="revolve",
        prompt="revolve test",
        created_at="2026-08-25T00:00:00Z",
        parts=[
            Part(
                id="p1",
                sketches=[
                    Sketch(
                        id="s1",
                        plane=PlaneReference(type="base", name="XY"),
                        entities=[SketchEntity(type="rectangle", id="r1", center=(0, 0), width=10, height=20)],
                    )
                ],
                features=[Feature(id="rev1", type="revolve", sketch_id="s1", parameters={"angle": 270})],
            )
        ],
    )
    code = transpile(tree)
    assert "revolve(axis=Axis.Y, angle=270)" in code


def test_transpile_fillet():
    tree = FeatureTree(
        design_id="fillet",
        prompt="fillet test",
        created_at="2026-08-25T00:00:00Z",
        parts=[
            Part(
                id="p1",
                features=[
                    Feature(
                        id="f1",
                        type="fillet",
                        parameters={"radius": 2, "edges": {"type": "all"}},
                    )
                ],
            )
        ],
    )
    code = transpile(tree)
    assert "fillet(part.edges(), radius=2)" in code


def test_transpile_chamfer():
    tree = FeatureTree(
        design_id="chamfer",
        prompt="chamfer test",
        created_at="2026-08-25T00:00:00Z",
        parts=[
            Part(
                id="p1",
                features=[
                    Feature(
                        id="c1",
                        type="chamfer",
                        parameters={"distance": 1.5, "edges": {"type": "all"}},
                    )
                ],
            )
        ],
    )
    code = transpile(tree)
    assert "chamfer(part.edges(), length=1.5)" in code


def test_transpile_mirror():
    tree = FeatureTree(
        design_id="mirror",
        prompt="mirror test",
        created_at="2026-08-25T00:00:00Z",
        parts=[
            Part(
                id="p1",
                features=[Feature(id="m1", type="mirror", parameters={"plane": {"type": "base", "name": "YZ"}})],
            )
        ],
    )
    code = transpile(tree)
    assert "mirror(about=Plane.YZ)" in code


def test_transpile_shell_uses_custom_part_variable():
    """Regression: shell must reference the active BuildPart variable, not hardcoded 'part'."""
    from ai_cad.transpiler import _transpile_part

    part = Part(
        id="duct",
        sketches=[
            Sketch(
                id="s1",
                plane=PlaneReference(type="base", name="XY"),
                entities=[SketchEntity(type="circle", id="c1", center=(0, 0), radius=20)],
            )
        ],
        features=[
            Feature(id="extrude1", type="extrude", sketch_id="s1", parameters={"amount": 30, "mode": "add"}),
            Feature(id="shell1", type="shell", parameters={"thickness": 2}),
        ],
    )
    code = "\n".join(_transpile_part(part, {}, var_name="part_0"))
    assert "with BuildPart() as part_0:" in code
    assert "part_0.part.hollow([], thickness=2)" in code
    assert "part.part.hollow(" not in code
    assert "part_0.faces()" in code or "part_0.part.hollow" in code


def test_transpile_fillet_uses_custom_part_variable():
    """Regression: fillet/chamfer edge selectors must use the active BuildPart variable."""
    from ai_cad.transpiler import _transpile_part

    part = Part(
        id="plate",
        features=[
            Feature(id="f1", type="fillet", parameters={"radius": 1, "edges": {"type": "all"}}),
            Feature(id="c1", type="chamfer", parameters={"distance": 0.5, "edges": {"type": "all"}}),
        ],
    )
    code = "\n".join(_transpile_part(part, {}, var_name="part_3"))
    assert "fillet(part_3.edges(), radius=1)" in code
    assert "chamfer(part_3.edges(), length=0.5)" in code
    assert "part.edges()" not in code
