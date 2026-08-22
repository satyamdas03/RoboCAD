"""Unit tests for the code execution sandbox."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_cad.executor import execute_code


VALID_CODE = """
from build123d import *

with BuildPart() as p:
    Box(10, 10, 10)

result = p.part
"""


def test_execute_code_success(tmp_path: Path):
    result = execute_code(VALID_CODE, output_dir=tmp_path)
    assert result["success"] is True
    assert result["result_type"] in {"Solid", "Part"}
    assert result["stl_path"] is not None
    assert result["stl_path"].exists()
    assert result["step_path"] is not None
    assert result["script_path"] is not None
    assert result["bounds"] is not None
    assert result["volume"] is not None


def test_execute_code_missing_result(tmp_path: Path):
    code = "x = 1 + 1"
    result = execute_code(code, output_dir=tmp_path)
    assert result["success"] is False
    assert result["traceback"] is not None
    assert "NameError" in result["traceback"]


def test_execute_code_runtime_error(tmp_path: Path):
    code = "from build123d import *\nresult = Box('a', 'b', 'c')"
    result = execute_code(code, output_dir=tmp_path)
    assert result["success"] is False
    assert "failed to execute" in result["error"].lower()


def test_execute_code_timeout(tmp_path: Path):
    # The subprocess should still finish quickly, but we exercise the path.
    result = execute_code(VALID_CODE, timeout=30, output_dir=tmp_path)
    assert result["success"] is True
