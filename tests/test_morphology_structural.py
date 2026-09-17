"""Tests for morphology structural dynamics / FEA integration (Milestone B)."""
from __future__ import annotations

from pathlib import Path
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


def test_cantilever_beam_check_passes_for_stocky_link():
    from ai_cad.morphology_structural import LinkStructuralProperties, beam_check
    from ai_cad.materials import get_material

    link = LinkStructuralProperties(
        name="stocky_thigh",
        length_m=0.22,
        area_m2=0.0006,
        i_min_m4=4.5e-8,
        i_max_m4=2.0e-7,
        r_min_m=8.7e-3,
        r_max_m=1.8e-2,
        material_name="Aluminum 6061",
        material=get_material("Aluminum 6061"),
    )
    result = beam_check(link, load_case="cantilever_payload", payload_kg=5.0)
    assert result.passed
    assert result.safety_factor > 1.0


def test_slender_link_fails_buckling_or_yield():
    from ai_cad.morphology_structural import LinkStructuralProperties, beam_check
    from ai_cad.materials import get_material

    link = LinkStructuralProperties(
        name="slender_thigh",
        length_m=0.60,
        area_m2=0.0001,
        i_min_m4=8.0e-10,
        i_max_m4=2.0e-9,
        r_min_m=2.8e-3,
        r_max_m=4.5e-3,
        material_name="PLA",
        material=get_material("PLA"),
    )
    result = beam_check(link, load_case="cantilever_payload", payload_kg=5.0)
    assert not result.passed
    assert result.failure_modes


def test_structural_score_penalizes_slender_humanoid():
    from ai_cad.morphology import score_candidate
    from ai_cad.robot_templates import humanoid_template

    tree = humanoid_template()
    # Deliberately long limbs to trigger structural failure.
    tree = tree.update_parameter("thigh_length", 400.0)
    tree = tree.update_parameter("shin_length", 350.0)
    tree = tree.update_parameter("upper_arm_length", 350.0)
    tree = tree.update_parameter("forearm_length", 300.0)
    result = score_candidate(tree, payload_kg=5.0, robot_mass_kg=20.0, use_physics=False, use_structural=True)
    # Long thin limbs should cause at least one link to fail.
    assert result["structural"] < 1.0
    assert result["structural"] >= 0.0


@pytest.mark.heavy
def test_deep_structural_smoke_falls_back_gracefully():
    from ai_cad.morphology_structural import run_deep_structural_for_candidate
    from ai_cad.robot_templates import humanoid_template
    import tempfile

    tree = humanoid_template()
    with tempfile.TemporaryDirectory() as tmp:
        result = run_deep_structural_for_candidate(
            tree, Path(tmp), payload_kg=5.0, solver_mode="surrogate"
        )
        assert result["deep_available"] is True
        assert "passed" in result


@pytest.mark.slow
def test_morphology_search_detects_structural_issues():
    from ai_cad.morphology import default_space, search_morphologies

    space = default_space("humanoid")
    space.n_max = 8
    # Search near the upper end of the default height range where limbs are long.
    candidates = search_morphologies(
        space,
        payload_kg=5.0,
        robot_mass_kg=20.0,
        use_physics=False,
        use_structural=True,
    )
    assert candidates
    top = max(candidates, key=lambda c: c.composite_score)
    assert top.scores.get("structural", 0.0) > 0.0
