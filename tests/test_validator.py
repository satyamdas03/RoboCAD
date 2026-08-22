"""Unit tests for STL/geometry validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_cad.executor import execute_code
from ai_cad.validator import validate_model


VALID_CODE = """
from build123d import *

with BuildPart() as p:
    Box(10, 10, 10)

result = p.part
"""


def _make_stl(tmp_path: Path) -> Path:
    exec_result = execute_code(VALID_CODE, output_dir=tmp_path)
    assert exec_result["success"] is True
    stl_path = exec_result["stl_path"]
    assert stl_path is not None
    return stl_path


def test_validate_model_success(tmp_path: Path):
    stl_path = _make_stl(tmp_path)
    report = validate_model(stl_path)
    assert report["valid"] is True
    assert report["watertight"] is True
    assert report["manifold"] is True
    assert report["bounds_mm"] is not None
    assert report["volume_mm3"] > 0
    assert report["errors"] == []


def test_validate_model_missing_file():
    report = validate_model(Path("/nonexistent/model.stl"))
    assert report["valid"] is False
    assert any("no stl" in err.lower() for err in report["errors"])
