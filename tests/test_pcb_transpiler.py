"""Tests for PCBOutline transpilation."""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.heavy]

from ai_cad.executor import execute_code
from ai_cad.feature_tree import FeatureTree, PCBOutline, Part
from ai_cad.transpiler import transpile


def _rect_board_tree(**overrides) -> FeatureTree:
    return FeatureTree(
        design_id="pcb_test",
        prompt="rectangular pcb",
        created_at="2026-08-29T00:00:00Z",
        parts=[
            Part(
                id="board",
                domain="electronics",
                features=[
                    PCBOutline(
                        id="pcb_outline",
                        board_shape=[(-40, -30), (40, -30), (40, 30), (-40, 30)],
                        board_thickness=overrides.get("board_thickness", 1.6),
                        mounting_holes=overrides.get("mounting_holes", [(-35, -25, 3), (35, -25, 3), (35, 25, 3), (-35, 25, 3)]),
                        keepouts=overrides.get("keepouts", []),
                        connector_positions=overrides.get("connector_positions", []),
                    )
                ],
            )
        ],
    )


def test_transpile_pcb_includes_board_shape():
    code = transpile(_rect_board_tree())
    assert "Polyline(" in code
    assert "make_face(" in code
    assert "extrude(" in code
    assert "Mode.ADD" in code


def test_transpile_pcb_includes_mounting_holes():
    code = transpile(_rect_board_tree())
    assert "Cylinder(" in code
    assert "Mode.SUBTRACT" in code
    assert "(-35.000000, -25.000000, 0)" in code


def test_transpile_pcb_includes_keepouts():
    tree = _rect_board_tree(
        keepouts=[
            {"type": "circle", "x": 0, "y": 0, "diameter": 6},
            {"type": "rectangle", "x": 20, "y": 0, "width": 8, "height": 4},
        ]
    )
    code = transpile(tree)
    assert "Rectangle(width=8.000000" in code
    assert "height=4.000000" in code
    assert "Cylinder(radius=3.000000" in code


def test_transpile_pcb_includes_connector_positions():
    tree = _rect_board_tree(
        connector_positions=[{"x": -30, "y": 0, "width": 10, "height": 4}]
    )
    code = transpile(tree)
    assert "Rectangle(width=10.000000" in code
    assert "height=4.000000" in code


def test_pcb_outline_executes():
    tree = _rect_board_tree()
    code = transpile(tree)
    result = execute_code(code, timeout=60)
    assert result["success"], result.get("traceback", result.get("error"))
    assert result["stl_path"] is not None
    assert result["volume"] is not None


def test_pcb_outline_with_keepouts_executes():
    tree = _rect_board_tree(
        keepouts=[
            {"type": "circle", "x": 0, "y": 0, "diameter": 6},
            {"type": "rectangle", "x": 20, "y": 0, "width": 8, "height": 4},
        ],
        connector_positions=[{"x": -30, "y": 0, "width": 10, "height": 4}],
    )
    code = transpile(tree)
    result = execute_code(code, timeout=60)
    assert result["success"], result.get("traceback", result.get("error"))
    assert result["stl_path"] is not None
