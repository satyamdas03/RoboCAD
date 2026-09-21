"""Failing tests for Milestone E topology grammar.

These tests exercise the deterministic topology grammar before the composer or
morphology integration exists.
"""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "base_type, expected_limbs",
    [
        ("biped", 2),
        ("quadruped", 4),
        ("hexapod", 6),
    ],
)
def test_default_topology_limb_count(base_type: str, expected_limbs: int):
    from ai_cad.topology_grammar import default_topology

    topo = default_topology(base_type, payload_kg=1.0, mass_budget_kg=10.0)
    assert topo.base_type == base_type
    assert len(topo.limbs) == expected_limbs
    assert all(limb.role == "leg" for limb in topo.limbs)


def test_default_topology_deterministic():
    from ai_cad.topology_grammar import default_topology

    a = default_topology("hexapod", payload_kg=2.0, mass_budget_kg=15.0)
    b = default_topology("hexapod", payload_kg=2.0, mass_budget_kg=15.0)
    assert a == b


def test_enumerate_topologies_returns_multiple_walkers():
    from ai_cad.topology_grammar import enumerate_topologies

    tops = enumerate_topologies(
        {"base_type": "walker", "min_limbs": 2, "max_limbs": 6},
        max_count=8,
        seed=42,
    )
    assert len(tops) >= 3
    base_types = {t.base_type for t in tops}
    assert "biped" in base_types or "quadruped" in base_types or "hexapod" in base_types


def test_enumerate_topologies_deterministic_with_seed():
    from ai_cad.topology_grammar import enumerate_topologies

    a = enumerate_topologies({"base_type": "walker"}, max_count=6, seed=7)
    b = enumerate_topologies({"base_type": "walker"}, max_count=6, seed=7)
    assert [t.base_type for t in a] == [t.base_type for t in b]
    assert [len(t.limbs) for t in a] == [len(t.limbs) for t in b]


def test_infeasible_one_legged_walker_is_pruned():
    from ai_cad.topology_grammar import Topology, LimbSpec, is_feasible

    topo = Topology(
        base_type="biped",
        base_dimensions=(200.0, 100.0, 80.0),
        mass_budget_kg=10.0,
        payload_kg=1.0,
        limbs=[
            LimbSpec(
                role="leg",
                side="left",
                index=0,
                attachment=(0.0, 50.0, 0.0),
                joints=[],
                end_effector_family="point_foot",
            ),
        ],
        tags=["walker"],
    )
    assert not is_feasible(topo)


def test_hexapod_has_six_distinct_attachments():
    from ai_cad.topology_grammar import default_topology

    topo = default_topology("hexapod", payload_kg=1.0, mass_budget_kg=10.0)
    attachments = [limb.attachment for limb in topo.limbs]
    assert len(set(attachments)) == 6


def test_wheeled_topology_is_feasible():
    from ai_cad.topology_grammar import default_topology, is_feasible

    topo = default_topology("wheeled", payload_kg=2.0, mass_budget_kg=20.0)
    assert is_feasible(topo)
    wheel_count = sum(1 for limb in topo.limbs if limb.role == "wheel")
    assert wheel_count >= 2
