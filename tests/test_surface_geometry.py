"""Tests for aero/thermal surface geometry generation (Phase 20)."""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.heavy]

from ai_cad.feature_tree import FeatureTree
from ai_cad.part_families import get_family, instantiate_family
from ai_cad.sketch_solver import _naca_4digit_points
from ai_cad.transpiler import transpile


@pytest.mark.parametrize("naca, chord", [("0012", 100.0), ("2412", 200.0), ("4412", 150.0)])
def test_naca_airfoil_generates_closed_loop(naca: str, chord: float):
    pts = _naca_4digit_points(naca, chord)
    # Upper surface from LE to TE, then lower surface back to LE.
    assert len(pts) == 2 * 40 + 2
    assert pts[0] == pytest.approx((0.0, 0.0))
    assert pts[-1] == pytest.approx((0.0, 0.0))
    assert pts[1][0] > 0  # upper surface moves toward TE
    assert pts[41][0] == pytest.approx(chord)  # trailing edge
    assert pts[42][0] < chord  # lower surface moves back toward LE


def test_airfoil_family_has_surface_feature():
    family = get_family("airfoil")
    part = instantiate_family("airfoil", "af1")
    assert part.domain == "aero"
    assert len(part.features) == 1
    assert part.features[0].type == "airfoil"


def test_wing_family_has_surface_feature():
    family = get_family("wing")
    part = instantiate_family("wing", "w1")
    assert part.domain == "aero"
    assert part.features[0].type == "wing"
    assert part.features[0].profile.get("span_param") == "wing_span"


def test_heat_sink_family_has_surface_feature():
    family = get_family("heat_sink")
    part = instantiate_family("heat_sink", "hs1")
    assert part.domain == "thermal"
    assert len(part.sketches) == 0
    assert part.features[0].type == "heat_sink"
    assert part.features[0].profile.get("fin_count") == "fin_count"


def test_propeller_blade_family_registered():
    family = get_family("propeller_blade")
    part = instantiate_family("propeller_blade", "pb1")
    assert part.domain == "aero"
    assert part.features[0].type == "propeller_blade"


def test_airfoil_transpiles_to_build123d():
    family = get_family("airfoil")
    part = instantiate_family("airfoil", "af1")
    tree = FeatureTree(
        design_id="test",
        prompt="test",
        parts=[part],
        parameters=family.default_parameters,
    )
    code = transpile(tree)
    assert "BuildLine(Plane.XY)" in code
    assert "Polyline(" in code
    assert "BuildSketch(Plane.XY)" in code
    assert "make_face(" in code
    assert "extrude(" in code


def test_wing_transpiles_to_build123d():
    family = get_family("wing")
    part = instantiate_family("wing", "w1")
    tree = FeatureTree(
        design_id="test",
        prompt="test",
        parts=[part],
        parameters=family.default_parameters,
    )
    code = transpile(tree)
    assert "BuildLine(Plane.XZ)" in code
    assert "BuildSketch(Plane.XZ)" in code
    assert "wing_span" in code


def test_heat_sink_transpiles_to_build123d():
    family = get_family("heat_sink")
    part = instantiate_family("heat_sink", "hs1")
    tree = FeatureTree(
        design_id="test",
        prompt="test",
        parts=[part],
        parameters=family.default_parameters,
    )
    code = transpile(tree)
    assert "Rectangle" in code
    assert "GridLocations" in code
    assert "extrude(" in code
