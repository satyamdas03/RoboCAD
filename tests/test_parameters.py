"""Unit tests for parameter extraction from generated code."""
from __future__ import annotations

from ai_cad.parameters import extract_parameters


def test_extract_simple_parameters():
    code = """
from build123d import *

length = 120.0
width = 80.0
thickness = 3
hole_diameter = 3.2

with BuildPart() as plate:
    Box(length, width, thickness)

result = plate.part
"""
    params = extract_parameters(code)
    by_name = {p.name: p for p in params}
    assert "length" in by_name
    assert by_name["length"].value == 120.0
    assert by_name["width"].value == 80.0
    assert by_name["thickness"].value == 3
    assert by_name["hole_diameter"].value == 3.2


def test_filter_non_parameter_names():
    code = """
from build123d import *

LENGTH = 100.0
_result = 1
_hidden = 5

def helper():
    local = 42

result = Box(1, 2, 3)
"""
    params = extract_parameters(code)
    names = {p.name for p in params}
    assert "LENGTH" not in names
    assert "_result" not in names
    assert "_hidden" not in names
    assert "local" not in names
    assert "result" not in names


def test_extract_param_comment():
    code = """
plate_length = 120.0  # param: overall plate length
plate_width = 80.0    # param: plate width
"""
    params = extract_parameters(code)
    by_name = {p.name: p for p in params}
    assert by_name["plate_length"].description == "overall plate length"
    assert by_name["plate_width"].description == "plate width"


def test_extract_no_numeric_literals_ignored():
    code = """
from build123d import *

message = "hello"
items = [1, 2, 3]

def foo(a, b):
    return a + b

result = Box(1, 2, 3)
"""
    params = extract_parameters(code)
    names = {p.name for p in params}
    assert "message" not in names
    assert "items" not in names
    assert "a" not in names
    assert "b" not in names


def test_extract_handles_syntax_error():
    params = extract_parameters("this is not python {(")
    assert params == []
