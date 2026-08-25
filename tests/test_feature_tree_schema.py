"""Tests for the Feature-Tree JSON schema and benchmark helpers."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from benchmarks.evaluate_complexity import (
    LADDER_PATH,
    _classify_failure,
    _estimate_feature_count,
    _flatten_prompts,
    _load_ladder,
    _summarize,
)


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "docs" / "feature_tree_schema.md"


def test_schema_document_exists():
    assert SCHEMA_PATH.exists(), "feature_tree_schema.md must exist"
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "Feature-Tree JSON Schema" in text
    assert '"parameters"' in text
    assert '"features"' in text
    assert '"parts"' in text
    assert '"assemblies"' in text


def test_ladder_exists_and_is_valid_json():
    assert LADDER_PATH.exists(), "complexity_ladder.json must exist"
    data = _load_ladder()
    assert "schema_version" in data
    assert "tiers" in data
    assert len(data["tiers"]) == 5


def test_ladder_contains_expected_number_of_prompts():
    data = _load_ladder()
    total = sum(len(t.get("prompts", [])) for t in data["tiers"])
    assert total == 30, f"Expected 30 prompts, got {total}"


def test_flatten_prompts_includes_tier_context():
    data = _load_ladder()
    flat = _flatten_prompts(data)
    assert len(flat) == 30
    assert all("tier" in p for p in flat)
    assert {p["tier"] for p in flat} == {
        "T1 - Primitive",
        "T2 - Basic part",
        "T3 - Intermediate",
        "T4 - Advanced",
        "T5 - Expert",
    }


def test_every_prompt_has_expected_keys():
    data = _load_ladder()
    required_keys = {
        "id",
        "prompt",
        "expected_features",
        "expected_feature_types",
        "expected_constraints",
        "expected_assembly_instances",
        "tags",
    }
    for tier in data["tiers"]:
        for p in tier["prompts"]:
            missing = required_keys - set(p.keys())
            assert not missing, f"Prompt {p.get('id')} missing keys: {missing}"
            assert isinstance(p["prompt"], str)
            assert isinstance(p["expected_features"], int)
            assert isinstance(p["expected_feature_types"], list)
            assert isinstance(p["expected_constraints"], int)
            assert isinstance(p["expected_assembly_instances"], int)
            assert isinstance(p["tags"], list)


def test_tier_id_prefix_matches_tier_number():
    data = _load_ladder()
    tier_map = {t["name"]: idx + 1 for idx, t in enumerate(data["tiers"])}
    for tier in data["tiers"]:
        for p in tier["prompts"]:
            prefix = f"t{tier_map[tier['name']]}"
            assert p["id"].startswith(prefix), (
                f"Prompt {p['id']} does not belong to tier {tier['name']}"
            )


def test_summarize_computes_pass_rate_and_tiers():
    results = [
        {"success": True, "tier": "T1", "latency_seconds": 10.0, "failure_mode": "success"},
        {"success": False, "tier": "T1", "latency_seconds": 5.0, "failure_mode": "syntax"},
        {"success": True, "tier": "T2", "latency_seconds": 20.0, "failure_mode": "success"},
    ]
    summary = _summarize(results)
    assert summary["total"] == 3
    assert summary["successes"] == 2
    assert summary["failures"] == 1
    assert summary["overall_pass_rate"] == pytest.approx(2 / 3, abs=0.01)
    assert summary["avg_latency_s"] == pytest.approx(15.0, abs=0.01)
    assert summary["by_tier"]["T1"]["total"] == 2
    assert summary["by_tier"]["T1"]["successes"] == 1
    assert summary["by_tier"]["T1"]["pass_rate"] == 0.5
    assert summary["by_tier"]["T2"]["total"] == 1
    assert summary["by_failure_mode"]["success"] == 2
    assert summary["by_failure_mode"]["syntax"] == 1


def test_classify_failure_known_modes():
    assert _classify_failure(None, None, True) == "success"
    assert _classify_failure("timed out", None, False) == "timeout"
    assert _classify_failure("ANTHROPIC_API_KEY not set", None, False) == "config"
    assert _classify_failure("unexpected indent", None, False) == "syntax"
    assert _classify_failure("not watertight", None, False) == "geometry"
    assert _classify_failure("some runtime", "Traceback", False) == "runtime"


def test_estimate_feature_count():
    code = """
with BuildPart() as p:
    Box(10, 10, 10)
    Cylinder(5, 10)
    extrude(p.sketch, amount=5)
    fillet(p.edges(), radius=1)
"""
    assert _estimate_feature_count(code) == 4
    assert _estimate_feature_count(None) == 0
    assert _estimate_feature_count("") == 0


def test_ladder_expected_feature_types_are_in_schema_terms():
    """All expected feature type names should be terms used by the schema."""
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    data = _load_ladder()
    allowed_types = {
        "extrude",
        "cut",
        "revolve",
        "fillet",
        "chamfer",
        "shell",
        "mirror",
        "linear_pattern",
        "circular_pattern",
        "sketch",
        "revolve_cut",
        "sweep",
        "loft",
        "draft",
        "hole",
    }
    for tier in data["tiers"]:
        for p in tier["prompts"]:
            for ft in p["expected_feature_types"]:
                assert ft in allowed_types, f"Unexpected feature type: {ft}"
                assert ft in schema_text, f"Feature type {ft} not mentioned in schema"
