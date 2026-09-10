"""Tests for Phase 28D morphology co-design engine."""
from __future__ import annotations

import pytest

from ai_cad.morphology import (
    MorphologyCandidate,
    MorphologyDimension,
    MorphologySpace,
    default_space,
    load_search_results,
    save_search_results,
    score_candidate,
    search_morphologies,
)


def test_default_space_humanoid_has_dimensions():
    space = default_space("humanoid")
    assert space.template == "humanoid"
    names = {d.name for d in space.dimensions}
    assert "robot_height" in names
    assert "thigh_length" in names
    assert "shin_length" in names
    assert space.n_max == 48


def test_default_space_quadruped_and_manipulator():
    quad = default_space("quadruped")
    assert quad.template == "quadruped"
    assert any(d.name == "thigh_length" for d in quad.dimensions)

    manip = default_space("manipulator_on_base")
    assert manip.template == "manipulator_on_base"
    assert any(d.name == "reach" for d in manip.dimensions)


def test_dimension_values_respects_max_count():
    dim = MorphologyDimension("x", 0.0, 100.0, 1.0)
    values = dim.values(max_count=8)
    assert 2 <= len(values) <= 8
    assert values[0] == pytest.approx(0.0)
    assert values[-1] == pytest.approx(100.0)


def test_dimension_values_single_value():
    dim = MorphologyDimension("x", 5.0, 5.0, 1.0)
    assert dim.values() == [5.0]


def test_parameter_grid_deterministic_with_seed():
    space = MorphologySpace(
        template="quadruped",
        dimensions=[
            MorphologyDimension("robot_height", 300.0, 800.0, 100.0),
            MorphologyDimension("thigh_length", 100.0, 220.0, 40.0),
        ],
        n_max=8,
        seed=42,
    )
    import numpy as np

    rng = np.random.default_rng(42)
    grid_a = space.parameter_grid(rng)
    rng = np.random.default_rng(42)
    grid_b = space.parameter_grid(rng)
    assert grid_a == grid_b
    assert len(grid_a) <= space.n_max


def test_search_morphologies_ranked_and_seeded():
    space = default_space("manipulator_on_base")
    space.n_max = 3
    space.seed = 7
    candidates_a = search_morphologies(space, payload_kg=2.0)
    candidates_b = search_morphologies(space, payload_kg=2.0)
    assert len(candidates_a) == 3
    assert [c.candidate_id for c in candidates_a] == [c.candidate_id for c in candidates_b]
    scores_a = [c.composite_score for c in candidates_a]
    scores_b = [c.composite_score for c in candidates_b]
    assert scores_a == scores_b
    assert candidates_a[0].rank == 1
    assert candidates_a[-1].rank == len(candidates_a)
    assert candidates_a == sorted(candidates_a, key=lambda c: c.composite_score, reverse=True)


def test_score_candidate_returns_expected_keys():
    space = default_space("manipulator_on_base")
    space.n_max = 2
    candidates = search_morphologies(space, payload_kg=5.0)
    assert candidates
    scores = score_candidate(candidates[0].tree, payload_kg=5.0)
    expected = {"stability", "workspace", "gait", "actuator", "compactness", "composite"}
    assert expected.issubset(scores.keys())
    assert 0.0 <= scores["composite"] <= 1.0
    assert all(0.0 <= scores[k] <= 1.0 for k in expected if k != "composite")


def test_save_and_load_search_results(tmp_path):
    space = default_space("manipulator_on_base")
    space.n_max = 3
    space.seed = 3
    candidates = search_morphologies(space, payload_kg=1.0)
    out = save_search_results("test-search-123", space, candidates, tmp_path)
    assert out.exists()
    data = load_search_results(out)
    assert data["search_id"] == "test-search-123"
    assert data["space"]["template"] == "manipulator_on_base"
    assert len(data["candidates"]) == len(candidates)
    assert data["candidates"][0]["rank"] == 1


def test_custom_weights_change_composite():
    space = default_space("manipulator_on_base")
    space.n_max = 3
    c1 = search_morphologies(space, payload_kg=5.0, weights={"stability": 1.0})[0]
    c2 = search_morphologies(space, payload_kg=5.0, weights={"workspace": 1.0})[0]
    # Different weightings should usually produce different top candidates.
    assert c1.composite_score != pytest.approx(c2.composite_score) or c1.candidate_id != c2.candidate_id


def test_candidate_to_dict_and_with_tree():
    space = default_space("manipulator_on_base")
    space.n_max = 2
    c = search_morphologies(space)[0]
    d = c.to_dict()
    assert "tree" not in d
    assert "candidate_id" in d
    assert "composite_score" in d
    full = c.with_tree_dict()
    assert "feature_tree" in full
