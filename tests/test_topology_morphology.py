"""End-to-end morphology tests for Milestone E topologies.

These tests wire topology grammar + composer into the morphology scoring pipeline
and look for real caveats: MuJoCo load, physics score, structural score, and
search integration.
"""
from __future__ import annotations

import pytest


@pytest.mark.slow
@pytest.mark.mujoco
def test_hexapod_topology_mujoco_loads():
    from pathlib import Path
    import tempfile

    import mujoco

    from ai_cad.geda_bridge.exporter import export_bundle_from_tree
    from ai_cad.topology_grammar import default_topology
    from ai_cad.topology_composer import topology_to_feature_tree

    topo = default_topology("hexapod", payload_kg=1.0, mass_budget_kg=10.0)
    tree = topology_to_feature_tree(topo)

    with tempfile.TemporaryDirectory() as tmp:
        bundle = export_bundle_from_tree(tree, Path(tmp))
        model = mujoco.MjModel.from_xml_path(str(bundle.mjcf))
        assert model.nq > 0


@pytest.mark.slow
@pytest.mark.mujoco
def test_wheeled_topology_mujoco_loads():
    from pathlib import Path
    import tempfile

    import mujoco

    from ai_cad.geda_bridge.exporter import export_bundle_from_tree
    from ai_cad.topology_grammar import default_topology
    from ai_cad.topology_composer import topology_to_feature_tree

    topo = default_topology("wheeled", payload_kg=2.0, mass_budget_kg=20.0)
    tree = topology_to_feature_tree(topo)

    with tempfile.TemporaryDirectory() as tmp:
        bundle = export_bundle_from_tree(tree, Path(tmp))
        model = mujoco.MjModel.from_xml_path(str(bundle.mjcf))
        assert model.nq >= 0


@pytest.mark.slow
def test_hexapod_topology_scores_nonzero():
    from ai_cad.morphology import score_candidate
    from ai_cad.topology_grammar import default_topology
    from ai_cad.topology_composer import topology_to_feature_tree

    topo = default_topology("hexapod", payload_kg=1.0, mass_budget_kg=10.0)
    tree = topology_to_feature_tree(topo)
    result = score_candidate(tree, payload_kg=1.0, robot_mass_kg=10.0)
    assert result["composite"] > 0.0
    assert result.get("actuator", 0.0) >= 0.0


@pytest.mark.slow
def test_wheeled_topology_scores_nonzero():
    from ai_cad.morphology import score_candidate
    from ai_cad.topology_grammar import default_topology
    from ai_cad.topology_composer import topology_to_feature_tree

    topo = default_topology("wheeled", payload_kg=2.0, mass_budget_kg=20.0)
    tree = topology_to_feature_tree(topo)
    result = score_candidate(tree, payload_kg=2.0, robot_mass_kg=20.0)
    assert result["composite"] > 0.0


@pytest.mark.heavy
def test_topology_search_returns_ranked_candidates():
    from ai_cad.morphology import TopologySpace, search_morphologies
    from ai_cad.topology_grammar import enumerate_topologies

    topologies = enumerate_topologies({"base_type": "walker"}, max_count=4, seed=42)
    space = TopologySpace(
        topologies=topologies,
        n_max=8,
        seed=42,
    )
    candidates = search_morphologies(space, payload_kg=1.0, robot_mass_kg=10.0)
    assert len(candidates) > 0
    top = max(candidates, key=lambda c: c.composite_score)
    assert top.composite_score > 0.0
    assert top.topology is not None
