"""Tests for feature-tree persistence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_cad.feature_store import exists, load, load_latest, save as save_feature_tree
from ai_cad.feature_tree import FeatureTree, Parameter


@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ROBOCAD_DESIGNS_DIR", str(tmp_path))
    return tmp_path


def _tree(width=10) -> FeatureTree:
    return FeatureTree(
        design_id="d",
        prompt="p",
        created_at="2026-08-25T00:00:00Z",
        parameters=[Parameter(name="width", value=width, unit="mm")],
    )


def test_save_creates_file(store_dir):
    save_feature_tree("abc", _tree())
    path = store_dir / "abc" / "feature_tree.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["design_id"] == "d"


def test_exists(store_dir):
    assert not exists("abc")
    save_feature_tree("abc", _tree())
    assert exists("abc")


def test_load_round_trip(store_dir):
    save_feature_tree("abc", _tree(width=42))
    loaded = load("abc")
    assert loaded is not None
    assert loaded.parameter_dict()["width"] == 42


def test_load_latest_multiple_versions(store_dir):
    save_feature_tree("abc", _tree(width=10))
    save_feature_tree("abc", _tree(width=20))
    latest = load_latest("abc")
    assert latest.parameter_dict()["width"] == 20


def test_load_missing_returns_none(store_dir):
    assert load("missing") is None
    assert load_latest("missing") is None
