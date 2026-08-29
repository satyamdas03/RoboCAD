"""Transpiler unit tests for SurfaceFeature handling (Phase 20)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_cad.feature_tree import FeatureTree, Parameter, Part, PlaneReference, Sketch, SketchEntity, SurfaceFeature
from ai_cad.transpiler import transpile, _transpile_surface_feature


def _airfoil_sketch(sketch_id: str = "airfoil_sketch", naca: str = "0012", chord_param: str = "chord_len") -> Sketch:
    return Sketch(
        id=sketch_id,
        plane=PlaneReference(type="base", name="XY"),
        entities=[
            SketchEntity(
                type="airfoil",
                id=f"{sketch_id}_foil",
                naca=naca,
                chord=chord_param,
            )
        ],
        points={f"{sketch_id}_foil": []},
    )


def test_unknown_surface_feature_raises():
    # SurfaceFeature type is a Literal, so an unknown type fails at construction.
    with pytest.raises(ValidationError):
        SurfaceFeature(id="bad", type="unknown", profile={})


def test_airfoil_surface_feature_emits_parameterized_polyline():
    part = Part(
        id="p1",
        domain="aero",
        sketches=[_airfoil_sketch(naca="0012", chord_param="chord_len")],
        features=[
            SurfaceFeature(
                id="af",
                type="airfoil",
                profile={"naca": "0012", "chord_param": "chord_len"},
            )
        ],
    )
    tree = FeatureTree(
        design_id="test",
        prompt="test",
        parts=[part],
        parameters=[Parameter(name="chord_len", value=120.0)],
    )
    code = transpile(tree)
    assert '"0012"' in code or "0012" in code
    assert "chord_len" in code
    assert "BuildLine(Plane.XY)" in code
    assert "Polyline(" in code
    assert "BuildSketch(Plane.XY)" in code
    assert "make_face(" in code


def test_wing_surface_feature_uses_xz_plane():
    part = Part(
        id="p1",
        domain="aero",
        sketches=[_airfoil_sketch(naca="2412", chord_param="chord_len")],
        features=[
            SurfaceFeature(
                id="wing",
                type="wing",
                profile={
                    "naca": "2412",
                    "chord_param": "chord_len",
                    "span_param": "wing_span",
                },
            )
        ],
    )
    tree = FeatureTree(
        design_id="test",
        prompt="test",
        parts=[part],
        parameters=[
            Parameter(name="chord_len", value=100.0),
            Parameter(name="wing_span", value=500.0),
        ],
    )
    code = transpile(tree)
    assert "Plane.XZ" in code
    assert "wing_span" in code


def test_heat_sink_surface_feature_emits_rect_and_grid():
    part = Part(
        id="p1",
        domain="thermal",
        features=[
            SurfaceFeature(
                id="hs",
                type="heat_sink",
                profile={
                    "base_length": "base_l",
                    "base_width": "base_w",
                    "base_height": "base_h",
                    "fin_count": "n_fins",
                    "fin_height": "fin_h",
                    "fin_thickness": "fin_t",
                },
            )
        ],
    )
    tree = FeatureTree(
        design_id="test",
        prompt="test",
        parts=[part],
        parameters=[
            Parameter(name="base_l", value=60.0),
            Parameter(name="base_w", value=60.0),
            Parameter(name="base_h", value=6.0),
            Parameter(name="n_fins", value=5),
            Parameter(name="fin_h", value=20.0),
            Parameter(name="fin_t", value=2.0),
        ],
    )
    code = transpile(tree)
    assert "Rectangle(" in code
    assert "GridLocations" in code
    assert "n_fins" in code


def test_propeller_blade_surface_feature_transpiles():
    part = Part(
        id="p1",
        domain="aero",
        sketches=[_airfoil_sketch(naca="0012", chord_param="chord_len")],
        features=[
            SurfaceFeature(
                id="pb",
                type="propeller_blade",
                profile={
                    "naca": "0012",
                    "chord_param": "chord_len",
                    "span_param": "blade_span",
                    "twist_deg": "twist",
                },
            )
        ],
    )
    tree = FeatureTree(
        design_id="test",
        prompt="test",
        parts=[part],
        parameters=[
            Parameter(name="chord_len", value=80.0),
            Parameter(name="blade_span", value=200.0),
            Parameter(name="twist", value=15.0),
        ],
    )
    code = transpile(tree)
    assert "BuildLine" in code
    assert "BuildSketch" in code
    assert "blade_span" in code


def test_unsupported_surface_feature_type_raises_via_helper():
    # Build a nominally valid feature and mutate its runtime type to exercise the
    # transpiler's ValueError path for types that are not explicitly handled.
    feature = SurfaceFeature(id="bad", type="heat_sink", profile={})
    feature.type = "unsupported"  # type: ignore[assignment]
    with pytest.raises(ValueError):
        _transpile_surface_feature(feature, Part(id="p1"), {}, {}, var_name="part")
