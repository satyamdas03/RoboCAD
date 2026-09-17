"""Tests for morphology structural dynamics / FEA integration (Milestone B)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.slow


def test_extract_limb_segment_properties():
    from ai_cad.morphology_structural import extract_link_properties
    from ai_cad.robot_templates import humanoid_template

    tree = humanoid_template()
    links = extract_link_properties(tree)
    assert len(links) >= 4  # at least thigh, shin, upper_arm, forearm per side
    thigh = [l for l in links if "thigh" in l.name]
    assert thigh
    assert thigh[0].length_m > 0.1
    assert thigh[0].area_m2 > 0.0
    assert thigh[0].i_min_m4 > 0.0
    assert thigh[0].i_max_m4 > 0.0
