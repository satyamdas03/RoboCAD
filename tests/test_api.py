"""Unit tests for the unified RoboCADBackend.generate() API."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

pytestmark = [pytest.mark.heavy, pytest.mark.slow]

from ai_cad.api import RoboCADBackend


VALID_CODE = """
from build123d import *

length = 10.0

with BuildPart() as p:
    Box(length, length, length)

result = p.part
"""


def test_generate_success_path(tmp_path: Path):
    backend = RoboCADBackend(api_key="fake-key")
    with mock.patch("ai_cad.api.generate_model") as mock_generate:
        mock_generate.return_value = {
            "success": True,
            "code": VALID_CODE,
            "raw_response": "",
            "model": "fake-model",
            "error": None,
        }
        result = backend.generate("a 10 mm cube", output_dir=tmp_path)

    assert result.success is True
    assert result.code is not None
    assert result.exports.stl is not None
    assert result.validation is not None
    assert result.validation.valid is True
    assert result.attempts_used == 1
    assert any(p.name == "length" for p in result.parameters)


def test_generate_missing_api_key():
    backend = RoboCADBackend(api_key=None)
    with mock.patch("ai_cad.api.generate_model") as mock_generate:
        mock_generate.return_value = {
            "success": False,
            "code": None,
            "raw_response": "",
            "model": "none",
            "error": "ANTHROPIC_API_KEY not set.",
        }
        result = backend.generate("a cube")
    assert result.success is False
    assert "ANTHROPIC_API_KEY" in (result.error or "")


def test_generate_self_corrects_on_runtime_error(tmp_path: Path):
    backend = RoboCADBackend(api_key="fake-key")
    bad_code = "from build123d import *\nresult = Box('a', 'b', 'c')"

    with (
        mock.patch("ai_cad.api.generate_model") as mock_generate,
        mock.patch("ai_cad.api.self_correct") as mock_correct,
    ):
        mock_generate.return_value = {
            "success": True,
            "code": bad_code,
            "raw_response": "",
            "model": "fake-model",
            "error": None,
        }
        mock_correct.return_value = {
            "success": True,
            "code": VALID_CODE,
            "raw_response": "",
            "model": "fake-model",
            "error": None,
        }
        result = backend.generate("a cube", max_retries=2, output_dir=tmp_path)

    assert result.success is True
    assert result.attempts_used == 2


def test_generate_self_corrects_on_validation_failure(tmp_path: Path):
    backend = RoboCADBackend(api_key="fake-key")
    # Mock the validation report to be invalid on first call, then valid.
    from ai_cad.models import ValidationReport

    invalid_report = ValidationReport(valid=False, errors=["Model is not watertight."])
    valid_report = ValidationReport(valid=True)

    with (
        mock.patch("ai_cad.api.generate_model") as mock_generate,
        mock.patch("ai_cad.api.self_correct") as mock_correct,
        mock.patch.object(backend, "_build_validation_report") as mock_validate,
    ):
        mock_generate.return_value = {
            "success": True,
            "code": VALID_CODE,
            "raw_response": "",
            "model": "fake-model",
            "error": None,
        }
        mock_correct.return_value = {
            "success": True,
            "code": VALID_CODE,
            "raw_response": "",
            "model": "fake-model",
            "error": None,
        }
        mock_validate.side_effect = [invalid_report, valid_report]
        result = backend.generate("two cubes", max_retries=2, output_dir=tmp_path)

    assert result.success is True
    assert result.attempts_used == 2
