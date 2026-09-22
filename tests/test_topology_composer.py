"""Failing tests for Milestone E topology composer.

These tests verify that abstract topologies from ai_cad.topology_grammar can be
mapped to concrete FeatureTree assemblies that validate and transpile.
"""
from __future__ import annotations

import pytest


def test_hexapod_tree_has_six_leg_instances():
    from ai_cad.topology_grammar import default_topology
    from ai_cad.topology_composer import topology_to_feature_tree

    topo = default_topology("hexapod", payload_kg=1.0, mass_budget_kg=10.0)
    tree = topology_to_feature_tree(topo)
    # Count the hip hubs that anchor legs; each leg gets one hub.
    leg_hub_instances = [inst for inst in tree.assemblies[0].instances if inst.id.startswith("hub_leg_")]
    assert len(leg_hub_instances) == 6


def test_wheeled_tree_has_wheels():
    from ai_cad.topology_grammar import default_topology
    from ai_cad.topology_composer import topology_to_feature_tree

    topo = default_topology("wheeled", payload_kg=2.0, mass_budget_kg=20.0)
    tree = topology_to_feature_tree(topo)
    wheel_instances = [inst for inst in tree.assemblies[0].instances if "wheel" in inst.id]
    assert len(wheel_instances) >= 2


def test_hexapod_tree_validates():
    from ai_cad.topology_grammar import default_topology
    from ai_cad.topology_composer import topology_to_feature_tree

    topo = default_topology("hexapod", payload_kg=1.0, mass_budget_kg=10.0)
    tree = topology_to_feature_tree(topo)
    errors = tree.validate_tree()
    assert not errors, errors


def test_hexapod_tree_transpiles():
    from ai_cad.executor import execute_code
    from ai_cad.topology_grammar import default_topology
    from ai_cad.topology_composer import topology_to_feature_tree
    from ai_cad.transpiler import transpile

    topo = default_topology("hexapod", payload_kg=1.0, mass_budget_kg=10.0)
    tree = topology_to_feature_tree(topo)
    code = transpile(tree)
    result = execute_code(code, timeout=60)
    assert result["success"], f"Execution failed: {result.get('traceback', result.get('error'))}"
    assert result.get("volume") is not None or result.get("bounds") is not None, "Expected non-empty geometry"


def test_quadruped_topology_matches_family_parts():
    from ai_cad.topology_grammar import default_topology
    from ai_cad.topology_composer import topology_to_feature_tree

    topo = default_topology("quadruped", payload_kg=2.0, mass_budget_kg=20.0)
    tree = topology_to_feature_tree(topo)
    families = {part.family for part in tree.parts}
    assert "limb_segment" in families
    assert "point_foot" in families or "compliant_foot" in families
    assert "torso_plate" in families


def test_fixed_base_arm_topology_has_gripper():
    from ai_cad.topology_grammar import default_topology
    from ai_cad.topology_composer import topology_to_feature_tree

    topo = default_topology("fixed", payload_kg=1.0, mass_budget_kg=10.0)
    tree = topology_to_feature_tree(topo)
    families = {part.family for part in tree.parts}
    assert "parallel_jaw_gripper" in families or "end_effector" in families
