"""Tests for HERMES tool parameter validation schemas."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_cad.hermes.validation import (
    BuildWorldParams,
    GenerateDesignParams,
    RegenerateParametersParams,
    RunVerificationParams,
    TrainBrainParams,
    ValidationErrorMessage,
    validate_tool_parameters,
)


def test_generate_design_params_defaults():
    p = GenerateDesignParams(prompt="cube")
    assert p.max_retries == 2
    assert p.detect_domain is True


def test_generate_design_params_rejects_negative_retries():
    with pytest.raises(ValidationErrorMessage):
        validate_tool_parameters("generate_design", {"prompt": "cube", "max_retries": -1})


def test_regenerate_params_requires_updates():
    with pytest.raises(ValidationErrorMessage):
        validate_tool_parameters("regenerate_parameters", {"parameter_updates": {}})


def test_build_world_tolerance_bounds():
    with pytest.raises(ValidationErrorMessage):
        validate_tool_parameters("build_world", {"tolerance": 1.5})


def test_run_verification_load_case_string():
    params = validate_tool_parameters("run_verification", {"load_case": "static_stress"})
    assert params["load_case"] == "static_stress"


def test_train_brain_pop_size_bounds():
    with pytest.raises(ValidationErrorMessage):
        validate_tool_parameters("train_brain", {"pop_size": 3})


def test_train_brain_success_threshold_bounds():
    with pytest.raises(ValidationErrorMessage):
        validate_tool_parameters("train_brain", {"success_rate_threshold": 1.5})
