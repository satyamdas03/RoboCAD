"""Domain part-family library for RoboCAD Phase 18.

A part family is a reusable, domain-tagged template that produces a symbolic
``Part`` (sketches + features) for common robotics subsystems. Families are not
meshes; they are feature-tree snippets that feed the existing transpiler and can
be overridden by per-sub-part intent parameters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_cad.feature_tree import (
    Constraint,
    CoordinateSystem,
    Dimension,
    Feature,
    Mate,
    MateEntity,
    Parameter,
    Part,
    PlaneReference,
    Sketch,
    SketchEntity,
    SurfaceFeature,
)


@dataclass
class PartFamily:
    """Reusable template for a domain-specific part.

    Attributes:
        name: Unique registry key (e.g., "bracket").
        domain: One of mechanical/aero/thermal/electronics/humanoid.
        display_name: Human-readable label.
        default_parameters: Parameters always present unless overridden.
        sketches: Default 2D sketches (may be empty for surface-only families).
        features: Default modeling operations or domain features.
        mates: Default mate relationships relative to other families.
        interface_csys: Local connection frame used for assembly placement.
    """

    name: str
    domain: str
    display_name: str
    default_parameters: list[Parameter] = field(default_factory=list)
    sketches: list[Sketch] = field(default_factory=list)
    features: list[Any] = field(default_factory=list)
    mates: list[Mate] = field(default_factory=list)
    interface_csys: CoordinateSystem | None = None


# ---------------------------------------------------------------------------
# Helpers for common sketch/feature patterns
# ---------------------------------------------------------------------------

def _rect_sketch(
    sketch_id: str,
    width_param: str,
    height_param: str,
    plane: str = "XY",
) -> Sketch:
    return Sketch(
        id=sketch_id,
        name=f"{sketch_id}_profile",
        plane=PlaneReference(type="base", name=plane),
        entities=[
            SketchEntity(
                type="rectangle",
                id=f"{sketch_id}_rect",
                center=(0, 0),
                width=width_param,
                height=height_param,
            )
        ],
        constraints=[],
        dimensions=[],
    )


def _circle_sketch(
    sketch_id: str,
    diameter_param: str,
    center: tuple[str | float, str | float] = (0, 0),
    plane: str = "XY",
) -> Sketch:
    return Sketch(
        id=sketch_id,
        name=f"{sketch_id}_profile",
        plane=PlaneReference(type="base", name=plane),
        entities=[
            SketchEntity(
                type="circle",
                id=f"{sketch_id}_circle",
                center=center,
                radius=f"{diameter_param} / 2",
            )
        ],
        constraints=[],
        dimensions=[],
    )


def _mounting_hole_pattern(
    sketch_id: str,
    bolt_diameter_param: str,
    pitch_x_param: str,
    pitch_y_param: str,
    plane: str = "XY",
) -> Sketch:
    """Four mounting holes on a rectangle (used by brackets / plates / mounts)."""
    holes = []
    for idx, (sx, sy) in enumerate([(1, 1), (1, -1), (-1, 1), (-1, -1)]):
        holes.append(
            SketchEntity(
                type="circle",
                id=f"{sketch_id}_hole_{idx}",
                center=(f"{sx} * {pitch_x_param} / 2", f"{sy} * {pitch_y_param} / 2"),
                radius=f"{bolt_diameter_param} / 2",
            )
        )
    outer = SketchEntity(
        type="rectangle",
        id=f"{sketch_id}_rect",
        center=(0, 0),
        width=pitch_x_param,
        height=pitch_y_param,
    )
    return Sketch(
        id=sketch_id,
        name=f"{sketch_id}_mount_pattern",
        plane=PlaneReference(type="base", name=plane),
        entities=[outer, *holes],
        constraints=[],
        dimensions=[],
    )


def _extrude_feature(feature_id: str, sketch_id: str, amount_param: str, *, mode: str = "add") -> Feature:
    return Feature(
        id=feature_id,
        type="extrude",
        sketch_id=sketch_id,
        parameters={"amount": amount_param, "mode": mode},
    )


# ---------------------------------------------------------------------------
# Mechanical families
# ---------------------------------------------------------------------------

def _mechanical_bracket() -> PartFamily:
    params = [
        Parameter(name="bracket_width", value=60.0, unit="mm"),
        Parameter(name="bracket_height", value=40.0, unit="mm"),
        Parameter(name="bracket_thickness", value=4.0, unit="mm"),
        Parameter(name="bolt_diameter", value=3.0, unit="mm"),
        Parameter(name="hole_pitch_x", value=50.0, unit="mm"),
        Parameter(name="hole_pitch_y", value=30.0, unit="mm"),
    ]
    sketch = _mounting_hole_pattern("bracket_base", "bolt_diameter", "hole_pitch_x", "hole_pitch_y")
    feature = _extrude_feature("bracket_body", "bracket_base", "bracket_thickness")
    interface = CoordinateSystem(
        id="bracket_interface",
        name="bracket mount face",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="bracket",
        domain="mechanical",
        display_name="Flat bracket with mounting holes",
        default_parameters=params,
        sketches=[sketch],
        features=[feature],
        interface_csys=interface,
    )


def _mechanical_link() -> PartFamily:
    params = [
        Parameter(name="link_length", value=120.0, unit="mm"),
        Parameter(name="link_width", value=20.0, unit="mm"),
        Parameter(name="link_thickness", value=6.0, unit="mm"),
        Parameter(name="axle_diameter", value=6.0, unit="mm"),
        Parameter(name="end_offset", value=10.0, unit="mm"),
    ]
    sketch = Sketch(
        id="link_profile",
        name="link_profile",
        plane=PlaneReference(type="base", name="XY"),
        entities=[
            SketchEntity(
                type="rectangle",
                id="link_rect",
                center=("link_length / 2 - end_offset", 0),
                width="link_length - 2 * end_offset",
                height="link_width",
            ),
            SketchEntity(
                type="circle",
                id="link_hole_a",
                center=("end_offset", 0),
                radius="axle_diameter / 2",
            ),
            SketchEntity(
                type="circle",
                id="link_hole_b",
                center=("link_length - end_offset", 0),
                radius="axle_diameter / 2",
            ),
        ],
        constraints=[],
        dimensions=[],
    )
    feature = _extrude_feature("link_body", "link_profile", "link_thickness")
    interface = CoordinateSystem(
        id="link_interface_a",
        name="link end A",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="link",
        domain="mechanical",
        display_name="Bar link with end holes",
        default_parameters=params,
        sketches=[sketch],
        features=[feature],
        interface_csys=interface,
    )


def _mechanical_hub() -> PartFamily:
    params = [
        Parameter(name="hub_diameter", value=40.0, unit="mm"),
        Parameter(name="hub_thickness", value=8.0, unit="mm"),
        Parameter(name="bore_diameter", value=8.0, unit="mm"),
        Parameter(name="bolt_circle_diameter", value=30.0, unit="mm"),
        Parameter(name="bolt_count", value=4, unit=""),
        Parameter(name="bolt_diameter", value=3.0, unit="mm"),
    ]
    outer = _circle_sketch("hub_outer", "hub_diameter")
    outer.entities[0].radius = "hub_diameter / 2"
    bore = _circle_sketch("hub_bore", "bore_diameter")
    # The outer and bore are on the same sketch in a real part; here we model
    # them as two sketches and two extrudes, which the current transpiler can
    # handle by union / cut semantics.
    outer_feature = _extrude_feature("hub_body", "hub_outer", "hub_thickness")
    bore_feature = _extrude_feature("hub_bore_cut", "hub_bore", "hub_thickness", mode="subtract")
    interface = CoordinateSystem(
        id="hub_interface",
        name="hub face",
        origin=(0, 0, 8.0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="hub",
        domain="mechanical",
        display_name="Circular hub with bore",
        default_parameters=params,
        sketches=[outer, bore],
        features=[outer_feature, bore_feature],
        interface_csys=interface,
    )


def _mechanical_mount() -> PartFamily:
    """Simple flat mounting plate / motor mount."""
    params = [
        Parameter(name="mount_width", value=40.0, unit="mm"),
        Parameter(name="mount_height", value=40.0, unit="mm"),
        Parameter(name="mount_thickness", value=3.0, unit="mm"),
        Parameter(name="center_hole_diameter", value=12.0, unit="mm"),
        Parameter(name="corner_hole_diameter", value=2.5, unit="mm"),
        Parameter(name="corner_pitch", value=32.0, unit="mm"),
    ]
    # Outer plate plus corner mounting holes in a single sketch.
    base = _mounting_hole_pattern("mount_base", "corner_hole_diameter", "mount_width", "mount_height")
    feature = _extrude_feature("mount_body", "mount_base", "mount_thickness")
    interface = CoordinateSystem(
        id="mount_interface",
        name="mount face",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="mount",
        domain="mechanical",
        display_name="Flat mounting plate",
        default_parameters=params,
        sketches=[base],
        features=[feature],
        interface_csys=interface,
    )


# ---------------------------------------------------------------------------
# Aero / thermal families
# ---------------------------------------------------------------------------

def _aero_airfoil() -> PartFamily:
    params = [
        Parameter(name="chord", value=200.0, unit="mm"),
        Parameter(name="naca", value="2412", unit=""),
        Parameter(name="span", value=400.0, unit="mm"),
    ]
    sketch = Sketch(
        id="airfoil_profile",
        name="airfoil_profile",
        plane=PlaneReference(type="base", name="XY"),
        entities=[
            SketchEntity(
                type="airfoil",
                id="airfoil_shape",
                naca="2412",
                chord="chord",
            )
        ],
        points={"airfoil_shape": []},  # solved at transpile time
        constraints=[],
        dimensions=[],
    )
    surface = SurfaceFeature(
        id="airfoil_surface",
        type="airfoil",
        profile={"naca": "naca", "chord_param": "chord"},
    )
    interface = CoordinateSystem(
        id="airfoil_root",
        name="airfoil root",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="airfoil",
        domain="aero",
        display_name="NACA 4-digit airfoil surface",
        default_parameters=params,
        sketches=[sketch],
        features=[surface],
        interface_csys=interface,
    )


def _aero_wing() -> PartFamily:
    params = [
        Parameter(name="wing_span", value=500.0, unit="mm"),
        Parameter(name="wing_chord", value=120.0, unit="mm"),
        Parameter(name="wing_naca", value="2412", unit=""),
        Parameter(name="wing_thickness", value=8.0, unit="mm"),
    ]
    sketch = Sketch(
        id="wing_profile",
        name="wing_profile",
        plane=PlaneReference(type="base", name="XY"),
        entities=[
            SketchEntity(
                type="airfoil",
                id="wing_airfoil",
                naca="2412",
                chord="wing_chord",
            )
        ],
        points={"wing_airfoil": []},
        constraints=[],
        dimensions=[],
    )
    surface = SurfaceFeature(
        id="wing_surface",
        type="wing",
        profile={"naca": "wing_naca", "chord_param": "wing_chord", "span_param": "wing_span"},
    )
    interface = CoordinateSystem(
        id="wing_root",
        name="wing root",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="wing",
        domain="aero",
        display_name="Straight extruded wing",
        default_parameters=params,
        sketches=[sketch],
        features=[surface],
        interface_csys=interface,
    )


def _aero_duct() -> PartFamily:
    params = [
        Parameter(name="duct_diameter", value=80.0, unit="mm"),
        Parameter(name="duct_length", value=120.0, unit="mm"),
        Parameter(name="duct_wall", value=2.0, unit="mm"),
    ]
    sketch = _circle_sketch("duct_outer", "duct_diameter")
    sketch.entities[0].radius = "duct_diameter / 2"
    feature = _extrude_feature("duct_body", "duct_outer", "duct_length")
    # Shell feature to hollow the cylinder
    shell = Feature(
        id="duct_shell",
        type="shell",
        parameters={"thickness": "duct_wall"},
    )
    interface = CoordinateSystem(
        id="duct_interface",
        name="duct axis start",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="duct",
        domain="aero",
        display_name="Cylindrical duct / shroud",
        default_parameters=params,
        sketches=[sketch],
        features=[feature, shell],
        interface_csys=interface,
    )


def _thermal_heat_sink() -> PartFamily:
    params = [
        Parameter(name="base_length", value=60.0, unit="mm"),
        Parameter(name="base_width", value=60.0, unit="mm"),
        Parameter(name="base_height", value=6.0, unit="mm"),
        Parameter(name="fin_count", value=9, unit=""),
        Parameter(name="fin_height", value=25.0, unit="mm"),
        Parameter(name="fin_thickness", value=2.0, unit="mm"),
    ]
    base = _rect_sketch("hs_base", "base_length", "base_width")
    base_feature = _extrude_feature("hs_base_body", "hs_base", "base_height")
    # Single centered fin for Phase 18; multi-fin patterns are Phase 19/20 scope.
    fin = _rect_sketch("hs_fin", "fin_thickness", "base_width")
    fin_feature = _extrude_feature("hs_fin_body", "hs_fin", "fin_height")
    interface = CoordinateSystem(
        id="hs_interface",
        name="heat sink base",
        origin=(0, 0, 6.0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="heat_sink",
        domain="thermal",
        display_name="Pin/fin heat sink",
        default_parameters=params,
        sketches=[base, fin],
        features=[base_feature, fin_feature],
        interface_csys=interface,
    )


# ---------------------------------------------------------------------------
# Electronics families
# ---------------------------------------------------------------------------

def _electronics_pcb_bracket() -> PartFamily:
    params = [
        Parameter(name="pcb_length", value=85.0, unit="mm"),
        Parameter(name="pcb_width", value=56.0, unit="mm"),
        Parameter(name="bracket_thickness", value=3.0, unit="mm"),
        Parameter(name="standoff_height", value=6.0, unit="mm"),
        Parameter(name="mounting_hole_diameter", value=2.5, unit="mm"),
        Parameter(name="corner_offset", value=3.5, unit="mm"),
    ]
    outline = _rect_sketch("pcb_outline", "pcb_length", "pcb_width")
    bracket = _extrude_feature("bracket_base", "pcb_outline", "bracket_thickness")
    interface = CoordinateSystem(
        id="pcb_interface",
        name="pcb mounting face",
        origin=(0, 0, 3.0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="pcb_bracket",
        domain="electronics",
        display_name="PCB mounting bracket / standoff",
        default_parameters=params,
        sketches=[outline],
        features=[bracket],
        interface_csys=interface,
    )


def _electronics_enclosure() -> PartFamily:
    params = [
        Parameter(name="enc_length", value=100.0, unit="mm"),
        Parameter(name="enc_width", value=80.0, unit="mm"),
        Parameter(name="enc_height", value=40.0, unit="mm"),
        Parameter(name="wall_thickness", value=2.0, unit="mm"),
        Parameter(name="lid_overlap", value=4.0, unit="mm"),
    ]
    base = _rect_sketch("enc_outer", "enc_length", "enc_width")
    body = _extrude_feature("enc_body", "enc_outer", "enc_height")
    interface = CoordinateSystem(
        id="enc_interface",
        name="enclosure base",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="enclosure",
        domain="electronics",
        display_name="Rectangular electronics enclosure",
        default_parameters=params,
        sketches=[base],
        features=[body],
        interface_csys=interface,
    )


# ---------------------------------------------------------------------------
# Humanoid / robot families
# ---------------------------------------------------------------------------

def _humanoid_limb_segment() -> PartFamily:
    params = [
        Parameter(name="segment_length", value=150.0, unit="mm"),
        Parameter(name="segment_width", value=30.0, unit="mm"),
        Parameter(name="segment_thickness", value=8.0, unit="mm"),
        Parameter(name="joint_bore", value=8.0, unit="mm"),
        Parameter(name="end_offset", value=15.0, unit="mm"),
    ]
    sketch = Sketch(
        id="limb_profile",
        name="limb_profile",
        plane=PlaneReference(type="base", name="XY"),
        entities=[
            SketchEntity(
                type="rectangle",
                id="limb_rect",
                center=("segment_length / 2 - end_offset", 0),
                width="segment_length - 2 * end_offset",
                height="segment_width",
            ),
            SketchEntity(
                type="circle",
                id="limb_hole_a",
                center=("end_offset", 0),
                radius="joint_bore / 2",
            ),
            SketchEntity(
                type="circle",
                id="limb_hole_b",
                center=("segment_length - end_offset", 0),
                radius="joint_bore / 2",
            ),
        ],
        constraints=[],
        dimensions=[],
    )
    feature = _extrude_feature("limb_body", "limb_profile", "segment_thickness")
    interface = CoordinateSystem(
        id="limb_interface_a",
        name="limb joint A",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="limb_segment",
        domain="humanoid",
        display_name="Robot limb tube with joint bores",
        default_parameters=params,
        sketches=[sketch],
        features=[feature],
        interface_csys=interface,
    )


def _humanoid_end_effector() -> PartFamily:
    params = [
        Parameter(name="jaw_length", value=60.0, unit="mm"),
        Parameter(name="jaw_width", value=20.0, unit="mm"),
        Parameter(name="jaw_thickness", value=8.0, unit="mm"),
        Parameter(name="gripper_gap", value=10.0, unit="mm"),
        Parameter(name="pivot_diameter", value=6.0, unit="mm"),
    ]
    sketch = Sketch(
        id="gripper_profile",
        name="gripper_profile",
        plane=PlaneReference(type="base", name="XY"),
        entities=[
            SketchEntity(
                type="rectangle",
                id="gripper_body",
                center=("jaw_length / 2", "gripper_gap / 2 + jaw_width / 2"),
                width="jaw_length",
                height="jaw_width",
            ),
            SketchEntity(
                type="circle",
                id="gripper_pivot",
                center=(0, 0),
                radius="pivot_diameter / 2",
            ),
        ],
        constraints=[],
        dimensions=[],
    )
    feature = _extrude_feature("gripper_body", "gripper_profile", "jaw_thickness")
    interface = CoordinateSystem(
        id="gripper_interface",
        name="gripper pivot",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    return PartFamily(
        name="end_effector",
        domain="humanoid",
        display_name="Parallel-jaw gripper jaw",
        default_parameters=params,
        sketches=[sketch],
        features=[feature],
        interface_csys=interface,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_FAMILY_BUILDERS: dict[str, Any] = {
    "bracket": _mechanical_bracket,
    "link": _mechanical_link,
    "hub": _mechanical_hub,
    "mount": _mechanical_mount,
    "airfoil": _aero_airfoil,
    "wing": _aero_wing,
    "duct": _aero_duct,
    "heat_sink": _thermal_heat_sink,
    "pcb_bracket": _electronics_pcb_bracket,
    "enclosure": _electronics_enclosure,
    "limb_segment": _humanoid_limb_segment,
    "end_effector": _humanoid_end_effector,
}

PART_FAMILY_REGISTRY: dict[str, PartFamily] = {
    name: builder() for name, builder in _FAMILY_BUILDERS.items()
}


def list_families(domain: str | None = None) -> list[PartFamily]:
    """Return all registered families, optionally filtered by domain."""
    families = list(PART_FAMILY_REGISTRY.values())
    if domain:
        families = [f for f in families if f.domain == domain]
    return families


def get_family(name: str) -> PartFamily:
    """Look up a family by name; raises KeyError if missing."""
    if name not in PART_FAMILY_REGISTRY:
        raise KeyError(f"Unknown part family '{name}'. Available: {list(PART_FAMILY_REGISTRY)}")
    return PART_FAMILY_REGISTRY[name]


def _merge_parameters(
    defaults: list[Parameter],
    overrides: list[Parameter],
) -> list[Parameter]:
    """Override default parameters by name."""
    merged = {p.name: p for p in defaults}
    for p in overrides:
        merged[p.name] = p
    return list(merged.values())


def instantiate_family(
    name: str,
    part_id: str,
    *,
    parameter_overrides: list[Parameter] | None = None,
    name_override: str | None = None,
) -> Part:
    """Create a ``Part`` from a registered family with optional overrides."""
    family = get_family(name)
    params = _merge_parameters(family.default_parameters, parameter_overrides or [])
    return Part(
        id=part_id,
        name=name_override or family.display_name,
        domain=family.domain,
        sketches=family.sketches,
        features=family.features,
    )
