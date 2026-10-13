"""Unit tests for the code execution sandbox."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.heavy, pytest.mark.slow]

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


def test_execute_code_cleans_temp_script_on_success(tmp_path: Path):
    result = execute_code(VALID_CODE, output_dir=tmp_path)
    assert result["success"] is True
    # The generated Python script and empty error file should be removed on success.
    assert not any(tmp_path.glob("generated_*.py"))
    assert not any(tmp_path.glob("error_*.txt"))
    # STL/STEP results are retained so callers can copy them.
    assert result["stl_path"] is not None
    assert result["stl_path"].exists()


def test_execute_code_keeps_artifacts_on_failure(tmp_path: Path):
    code = "from build123d import *\nresult = Box('a', 'b', 'c')"
    result = execute_code(code, output_dir=tmp_path)
    assert result["success"] is False
    # Failure artifacts should be retained for debugging.
    assert result["script_path"] is not None
    assert result["script_path"].exists()
    assert any(tmp_path.glob("error_*.txt"))


def test_execute_code_rejects_disallowed_imports(tmp_path: Path):
    """The executor must reject generated code that imports unsafe modules."""
    code = "import os\nfrom subprocess import run\nfrom build123d import *\nresult = Box(1,1,1)"
    result = execute_code(code, output_dir=tmp_path)
    assert result["success"] is False
    assert "security validation" in result["error"].lower()
    assert "Disallowed import" in (result["traceback"] or "")


def test_execute_code_rejects_disallowed_builtins(tmp_path: Path):
    """The executor must reject generated code that calls dangerous builtins."""
    code = "from build123d import *\neval('1+1')\nresult = Box(1,1,1)"
    result = execute_code(code, output_dir=tmp_path)
    assert result["success"] is False
    assert "security validation" in result["error"].lower()
    assert "Disallowed builtin" in (result["traceback"] or "")


def test_execute_code_runs_in_sandboxed_mode(tmp_path: Path):
    """The subprocess must run with safe path and no bytecode so generated code
    cannot tamper with sys.path or leave compiled artifacts behind."""
    code = """
from build123d import *
import sys

assert sys.flags.safe_path, "expected safe path (-P)"
assert sys.flags.dont_write_bytecode, "expected no bytecode (-B)"

result = Box(1, 1, 1)
"""
    result = execute_code(code, output_dir=tmp_path)
    assert result["success"] is True, result.get("traceback")
