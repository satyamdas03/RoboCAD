"""Tests for the structured feature-tree model and store."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_cad.feature_store import exists, load, load_latest, save as save_feature_tree
from ai_cad.feature_tree import (
    Feature,
    FeatureTree,
    Parameter,
    Part,
    PlaneReference,
    Sketch,
    SketchEntity,
)


def _base_plate_tree() -> FeatureTree:
    return FeatureTree(
        design_id="test-123",
        prompt="A 50x30x5 base plate with four 4 mm corner holes",
        created_at="2026-08-25T00:00:00Z",
        parameters=[
            Parameter(name="width", value=50, unit="mm", description="Plate width"),
            Parameter(name="depth", value=30, unit="mm", description="Plate depth"),
            Parameter(name="thickness", value=5, unit="mm", description="Plate thickness"),
            Parameter(name="hole_diameter", value=4, unit="mm", description="Mounting hole diameter"),
        ],
        parts=[
            Part(
                id="base_plate",
                name="Base plate",
                sketches=[
                    Sketch(
                        id="profile",
                        plane=PlaneReference(type="base", name="XY"),
                        entities=[
                            SketchEntity(
                                type="rectangle",
                                id="rect1",
                                center=(0, 0),
                                width="width",
                                height="depth",
                            )
                        ],
                    )
                ],
                features=[
                    Feature(
                        id="extrude1",
                        type="extrude",
                        sketch_id="profile",
                        parameters={"amount": "thickness", "direction": "positive", "mode": "add"},
                    ),
                    Feature(
                        id="holes",
                        type="extrude",
                        sketch_id="profile",
                        parameters={"amount": "thickness", "direction": "positive", "mode": "subtract"},
                    ),
                ],
            )
        ],
    )


def test_parameter_dict():
    tree = _base_plate_tree()
    assert tree.parameter_dict() == {
        "width": 50,
        "depth": 30,
        "thickness": 5,
        "hole_diameter": 4,
    }


def test_update_parameter_returns_new_tree():
    tree = _base_plate_tree()
    updated = tree.update_parameter("width", 60)
    assert updated is not tree
    assert updated.parameter_dict()["width"] == 60
    assert tree.parameter_dict()["width"] == 50


def test_find_part_and_feature():
    tree = _base_plate_tree()
    assert tree.find_part("base_plate") is not None
    assert tree.find_part("missing") is None
    assert tree.find_feature("base_plate", "extrude1") is not None
    assert tree.find_feature("base_plate", "missing") is None


def test_validate_tree_missing_sketch():
    tree = FeatureTree(
        design_id="bad",
        prompt="bad",
        created_at="2026-08-25T00:00:00Z",
        parts=[
            Part(
                id="p1",
                features=[
                    Feature(id="f1", type="extrude", sketch_id="missing", parameters={})
                ],
            )
        ],
    )
    errors = tree.validate_tree()
    assert any("missing sketch" in e for e in errors)


def test_validate_tree_missing_dependency():
    tree = FeatureTree(
        design_id="bad",
        prompt="bad",
        created_at="2026-08-25T00:00:00Z",
        parts=[
            Part(
                id="p1",
                features=[
                    Feature(id="f1", type="fillet", parameters={}, depends_on=["missing"])
                ],
            )
        ],
    )
    errors = tree.validate_tree()
    assert any("missing feature" in e for e in errors)


def test_feature_requires_sketch_for_extrude():
    with pytest.raises(ValueError):
        Feature(id="f1", type="extrude", parameters={})


@pytest.fixture
def clean_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ROBOCAD_DESIGNS_DIR", str(tmp_path))
    return tmp_path


def test_save_and_load(clean_store):
    tree = _base_plate_tree()
    save_feature_tree("d1", tree)
    assert exists("d1")
    loaded = load("d1")
    assert loaded.design_id == "test-123"
    assert loaded.parameter_dict()["width"] == 50


def test_load_latest_returns_most_recent(clean_store):
    save_feature_tree("d1", _base_plate_tree())
    second = _base_plate_tree()
    second = second.update_parameter("width", 70)
    save_feature_tree("d1", second)
    latest = load_latest("d1")
    assert latest.parameter_dict()["width"] == 70


def test_load_missing_returns_none(clean_store):
    assert not exists("missing")
    assert load("missing") is None
    assert load_latest("missing") is None
