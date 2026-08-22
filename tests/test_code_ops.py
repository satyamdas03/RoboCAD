"""Tests for safe code-level parameter updates."""
from __future__ import annotations

import pytest

from ai_cad.code_ops import update_parameter, update_parameters


CODE = """from build123d import *

length = 120.0  # param: plate length
width = 80.0
thickness = 3
hole_diameter = 3.2

with BuildPart() as p:
    Box(length, width, thickness)

result = p.part
"""


def test_update_single_parameter():
    updated = update_parameter(CODE, "length", 150.0)
    assert "length = 150.0" in updated
    assert "# param: plate length" in updated


def test_update_integer_parameter():
    updated = update_parameter(CODE, "thickness", 5)
    assert "thickness = 5" in updated


def test_update_preserves_other_parameters():
    updated = update_parameter(CODE, "width", 100.0)
    assert "width = 100.0" in updated
    assert "length = 120.0" in updated
    assert "thickness = 3" in updated


def test_update_missing_parameter_raises():
    with pytest.raises(ValueError):
        update_parameter(CODE, "radius", 10.0)


def test_update_parameters_multiple():
    updated = update_parameters(CODE, {"length": 150.0, "thickness": 5})
    assert "length = 150.0" in updated
    assert "thickness = 5" in updated
    assert "width = 80.0" in updated


def test_update_parameters_missing_one_raises():
    with pytest.raises(ValueError):
        update_parameters(CODE, {"length": 150.0, "radius": 10.0})


def test_update_parameter_does_not_touch_augmented_assignment():
    code_with_aug = "x = 1\nx += 2\n"
    updated = update_parameter(code_with_aug, "x", 5)
    assert "x = 5" in updated
    assert "x += 2" in updated
