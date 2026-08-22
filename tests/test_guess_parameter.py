"""Tests for face-to-parameter guessing heuristic."""
from __future__ import annotations

import pytest

from ai_cad.guess_parameter import guess_parameter
from ai_cad.models import CADParameter


BASE_PLATE_PARAMS = [
    CADParameter(name="length", value=120.0),
    CADParameter(name="width", value=80.0),
    CADParameter(name="thickness", value=3.0),
    CADParameter(name="hole_diameter", value=3.2),
    CADParameter(name="hole_spacing_x", value=100.0),
    CADParameter(name="hole_spacing_y", value=60.0),
]

BASE_PLATE_BOUNDS = (120.0, 80.0, 3.0)


def test_top_face_guesses_thickness():
    result = guess_parameter(BASE_PLATE_PARAMS, BASE_PLATE_BOUNDS, (0.0, 0.0, 1.0))
    assert result["guessed_parameter"] == "thickness"
    assert result["axis"] == 2
    assert result["confidence"] > 0.5


def test_bottom_face_guesses_thickness():
    result = guess_parameter(BASE_PLATE_PARAMS, BASE_PLATE_BOUNDS, (0.0, 0.0, -1.0))
    assert result["guessed_parameter"] == "thickness"
    assert result["axis"] == 2


def test_left_right_face_guesses_length():
    result = guess_parameter(BASE_PLATE_PARAMS, BASE_PLATE_BOUNDS, (1.0, 0.0, 0.0))
    assert result["guessed_parameter"] == "length"
    assert result["axis"] == 0


def test_front_back_face_guesses_width():
    result = guess_parameter(BASE_PLATE_PARAMS, BASE_PLATE_BOUNDS, (0.0, 1.0, 0.0))
    assert result["guessed_parameter"] == "width"
    assert result["axis"] == 1


def test_no_parameters_returns_none():
    result = guess_parameter([], BASE_PLATE_BOUNDS, (0.0, 0.0, 1.0))
    assert result["guessed_parameter"] is None
    assert result["confidence"] == 0.0


def test_diagonal_normal_resolves_to_dominant_axis():
    result = guess_parameter(BASE_PLATE_PARAMS, BASE_PLATE_BOUNDS, (0.9, 0.3, 0.3))
    # Dominant component is X.
    assert result["axis"] == 0
    assert result["guessed_parameter"] == "length"


def test_hole_diameter_not_guessed_for_faces():
    """hole_diameter is not a face dimension, so it should never be selected
    for a planar face normal.
    """
    for normal in [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]:
        result = guess_parameter(BASE_PLATE_PARAMS, BASE_PLATE_BOUNDS, normal)
        assert result["guessed_parameter"] != "hole_diameter"
