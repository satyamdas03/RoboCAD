"""Tests for the internal 2D sketch constraint solver."""
from __future__ import annotations

import math

import pytest

from ai_cad.feature_tree import Constraint, Dimension, Sketch, SketchEntity, PlaneReference
from ai_cad.sketch_solver import solve_sketch


def _sketch_with_constraints(entities, constraints=None, dimensions=None) -> Sketch:
    return Sketch(
        id="s1",
        plane=PlaneReference(type="base", name="XY"),
        entities=entities,
        constraints=constraints or [],
        dimensions=dimensions or [],
    )


def test_distance_dimension_between_two_points():
    sketch = _sketch_with_constraints(
        entities=[
            SketchEntity(type="circle", id="c1", center=(0, 0), radius=1),
            SketchEntity(type="circle", id="c2", center=(10, 0), radius=1),
        ],
        dimensions=[
            Dimension(name="spacing", type="distance", entities=["c1", "c2"], value=20),
        ],
    )
    solved = solve_sketch(sketch)
    c1 = next(e for e in solved.entities if e.id == "c1")
    c2 = next(e for e in solved.entities if e.id == "c2")
    dx = c2.center[0] - c1.center[0]
    dy = c2.center[1] - c1.center[1]
    assert math.hypot(dx, dy) == pytest.approx(20, abs=0.01)


def test_coincident_makes_centers_equal():
    sketch = _sketch_with_constraints(
        entities=[
            SketchEntity(type="circle", id="c1", center=(0, 0), radius=5),
            SketchEntity(type="circle", id="c2", center=(10, 10), radius=3),
        ],
        constraints=[
            Constraint(type="coincident", entities=["c1", "c2"]),
        ],
    )
    solved = solve_sketch(sketch)
    c1 = next(e for e in solved.entities if e.id == "c1")
    c2 = next(e for e in solved.entities if e.id == "c2")
    assert c1.center == pytest.approx(c2.center, abs=0.01)


def test_horizontal_aligns_y():
    sketch = _sketch_with_constraints(
        entities=[
            SketchEntity(type="circle", id="c1", center=(0, 0), radius=2),
            SketchEntity(type="circle", id="c2", center=(10, 5), radius=2),
        ],
        constraints=[
            Constraint(type="horizontal", entities=["c1", "c2"]),
        ],
    )
    solved = solve_sketch(sketch)
    c1 = next(e for e in solved.entities if e.id == "c1")
    c2 = next(e for e in solved.entities if e.id == "c2")
    assert c1.center[1] == pytest.approx(c2.center[1], abs=0.01)


def test_vertical_aligns_x():
    sketch = _sketch_with_constraints(
        entities=[
            SketchEntity(type="circle", id="c1", center=(0, 0), radius=2),
            SketchEntity(type="circle", id="c2", center=(5, 10), radius=2),
        ],
        constraints=[
            Constraint(type="vertical", entities=["c1", "c2"]),
        ],
    )
    solved = solve_sketch(sketch)
    c1 = next(e for e in solved.entities if e.id == "c1")
    c2 = next(e for e in solved.entities if e.id == "c2")
    assert c1.center[0] == pytest.approx(c2.center[0], abs=0.01)


def test_equal_radii():
    sketch = _sketch_with_constraints(
        entities=[
            SketchEntity(type="circle", id="c1", center=(0, 0), radius=2),
            SketchEntity(type="circle", id="c2", center=(10, 0), radius=8),
        ],
        constraints=[
            Constraint(type="equal", entities=["c1", "c2"]),
        ],
    )
    solved = solve_sketch(sketch)
    c1 = next(e for e in solved.entities if e.id == "c1")
    c2 = next(e for e in solved.entities if e.id == "c2")
    assert c1.radius == pytest.approx(c2.radius, abs=0.01)


def test_fix_keeps_point_in_place():
    sketch = _sketch_with_constraints(
        entities=[
            SketchEntity(type="circle", id="c1", center=(3, 4), radius=2),
        ],
        constraints=[
            Constraint(type="fix", entities=["c1"]),
        ],
        dimensions=[
            Dimension(name="spacing", type="distance", entities=["c1", "c2"], value=10),
        ],
    )
    # c2 is missing, so dimension is ignored; fix should preserve c1.
    solved = solve_sketch(sketch)
    c1 = next(e for e in solved.entities if e.id == "c1")
    assert c1.center[0] == pytest.approx(3, abs=0.01)
    assert c1.center[1] == pytest.approx(4, abs=0.01)


def test_parameter_substitution_in_dimension():
    sketch = _sketch_with_constraints(
        entities=[
            SketchEntity(type="circle", id="c1", center=(0, 0), radius=1),
            SketchEntity(type="circle", id="c2", center=(5, 0), radius=1),
        ],
        dimensions=[
            Dimension(name="spacing", type="distance", entities=["c1", "c2"], value="spacing"),
        ],
    )
    solved = solve_sketch(sketch, parameters={"spacing": 15})
    c1 = next(e for e in solved.entities if e.id == "c1")
    c2 = next(e for e in solved.entities if e.id == "c2")
    assert math.hypot(c2.center[0] - c1.center[0], c2.center[1] - c1.center[1]) == pytest.approx(15, abs=0.01)


def test_no_constraints_returns_unchanged():
    sketch = _sketch_with_constraints(
        entities=[
            SketchEntity(type="circle", id="c1", center=(3, 4), radius=2),
        ]
    )
    solved = solve_sketch(sketch)
    assert solved.entities[0].center == (3, 4)
