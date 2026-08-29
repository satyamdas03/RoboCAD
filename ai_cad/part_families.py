"""Domain part-family library for RoboCAD Phase 18/19.

A part family is a reusable, domain-tagged template that produces a symbolic
``Part`` (sketches + features) for common robotics subsystems. Families are not
meshes; they are feature-tree snippets that feed the existing transpiler and can
be overridden by per-sub-part intent parameters.

Phase 19 adds an explicit ``Interface`` library to each family so assembly
synthesis can infer mates, connection types, and kinematic roles from the
family metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

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
class Interface:
    """A local connection frame on a part family with mate semantics.

    Attributes:
        id: Stable interface identifier within the family (e.g., ``mount_face``).
        csys: The 3D coordinate system locating and orienting the interface.
        type: Physical interface category.
        mate_hint: Preferred mate relationship when this interface is used in an
            assembly (``None`` if the family does not prescribe one).
        mate_with: Compatibility tags in ``family/interface`` form. Used by
            assembly synthesis to decide which interfaces may join.
    """

    id: str
    csys: CoordinateSystem
    type: Literal["mount", "pin", "bore", "slot", "flange", "face"]
    mate_hint: (
        Literal["fixed", "revolute", "prismatic", "concentric", "coincident"]
        | None
    ) = None
    mate_with: list[str] | None = None


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
        interfaces: Local connection frames with mate hints for assembly.
    """

    name: str
    domain: str
    display_name: str
    default_parameters: list[Parameter] = field(default_factory=list)
    sketches: list[Sketch] = field(default_factory=list)
    features: list[Any] = field(default_factory=list)
    mates: list[Mate] = field(default_factory=list)
    interfaces: list[Interface] = field(default_factory=list)


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
    mount_face = CoordinateSystem(
        id="bracket_mount_face",
        name="bracket mount face",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="mount_face",
            csys=mount_face,
            type="mount",
            mate_hint="fixed",
            mate_with=["bracket/mount_face", "mount/mount_face", "hub/flange_a"],
        )
    ]
    return PartFamily(
        name="bracket",
        domain="mechanical",
        display_name="Flat bracket with mounting holes",
        default_parameters=params,
        sketches=[sketch],
        features=[feature],
        interfaces=interfaces,
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
    pin_a = CoordinateSystem(
        id="link_pin_a",
        name="link end A",
        origin=(10.0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    pin_b = CoordinateSystem(
        id="link_pin_b",
        name="link end B",
        origin=(110.0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="pin_a",
            csys=pin_a,
            type="pin",
            mate_hint="revolute",
            mate_with=["link/pin_b", "hub/bore", "mount/bore"],
        ),
        Interface(
            id="pin_b",
            csys=pin_b,
            type="pin",
            mate_hint="revolute",
            mate_with=["link/pin_a", "hub/bore", "mount/bore"],
        ),
    ]
    return PartFamily(
        name="link",
        domain="mechanical",
        display_name="Bar link with end holes",
        default_parameters=params,
        sketches=[sketch],
        features=[feature],
        interfaces=interfaces,
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
    outer_feature = _extrude_feature("hub_body", "hub_outer", "hub_thickness")
    bore_feature = _extrude_feature("hub_bore_cut", "hub_bore", "hub_thickness", mode="subtract")
    flange_a = CoordinateSystem(
        id="hub_flange_a",
        name="hub face",
        origin=(0, 0, 8.0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    bore_csys = CoordinateSystem(
        id="hub_bore_csys",
        name="hub bore center",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="flange_a",
            csys=flange_a,
            type="flange",
            mate_hint="fixed",
            mate_with=["bracket/mount_face", "mount/mount_face", "hub/flange_a"],
        ),
        Interface(
            id="bore",
            csys=bore_csys,
            type="bore",
            mate_hint="concentric",
            mate_with=["link/pin_a", "link/pin_b", "limb_segment/pin_a", "limb_segment/pin_b"],
        ),
    ]
    return PartFamily(
        name="hub",
        domain="mechanical",
        display_name="Circular hub with bore",
        default_parameters=params,
        sketches=[outer, bore],
        features=[outer_feature, bore_feature],
        interfaces=interfaces,
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
    base = _mounting_hole_pattern("mount_base", "corner_hole_diameter", "mount_width", "mount_height")
    feature = _extrude_feature("mount_body", "mount_base", "mount_thickness")
    mount_face = CoordinateSystem(
        id="mount_face_csys",
        name="mount face",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="mount_face",
            csys=mount_face,
            type="mount",
            mate_hint="fixed",
            mate_with=["bracket/mount_face", "hub/flange_a", "mount/mount_face"],
        )
    ]
    return PartFamily(
        name="mount",
        domain="mechanical",
        display_name="Flat mounting plate",
        default_parameters=params,
        sketches=[base],
        features=[feature],
        interfaces=interfaces,
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
    root = CoordinateSystem(
        id="airfoil_root",
        name="airfoil root",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="root",
            csys=root,
            type="face",
            mate_hint="fixed",
            mate_with=["airfoil/root", "wing/root"],
        )
    ]
    return PartFamily(
        name="airfoil",
        domain="aero",
        display_name="NACA 4-digit airfoil surface",
        default_parameters=params,
        sketches=[sketch],
        features=[surface],
        interfaces=interfaces,
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
    root = CoordinateSystem(
        id="wing_root",
        name="wing root",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="root",
            csys=root,
            type="face",
            mate_hint="fixed",
            mate_with=["airfoil/root", "wing/root"],
        )
    ]
    return PartFamily(
        name="wing",
        domain="aero",
        display_name="Straight extruded wing",
        default_parameters=params,
        sketches=[sketch],
        features=[surface],
        interfaces=interfaces,
    )


def _aero_duct() -> PartFamily:
    params = [
        Parameter(name="duct_diameter", value=80.0, unit="mm"),
        Parameter(name="duct_length", value=120.0, unit="mm"),
        Parameter(name="duct_wall", value=2.0, unit="mm"),
    ]
    outer = _circle_sketch("duct_outer", "duct_diameter")
    outer.entities[0].radius = "duct_diameter / 2"
    inner = _circle_sketch("duct_inner", "duct_diameter")
    inner.entities[0].radius = "duct_diameter / 2 - duct_wall"
    outer_feature = _extrude_feature("duct_body", "duct_outer", "duct_length")
    inner_cut = _extrude_feature("duct_hollow", "duct_inner", "duct_length", mode="subtract")
    face_a = CoordinateSystem(
        id="duct_face_a",
        name="duct axis start",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    bore = CoordinateSystem(
        id="duct_bore",
        name="duct bore center",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="face_a",
            csys=face_a,
            type="face",
            mate_hint="coincident",
            mate_with=["duct/face_a", "hub/flange_a"],
        ),
        Interface(
            id="bore",
            csys=bore,
            type="bore",
            mate_hint="concentric",
            mate_with=["hub/bore", "propeller/bore"],
        ),
    ]
    return PartFamily(
        name="duct",
        domain="aero",
        display_name="Cylindrical duct / shroud",
        default_parameters=params,
        sketches=[outer, inner],
        features=[outer_feature, inner_cut],
        interfaces=interfaces,
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
    fin = _rect_sketch("hs_fin", "fin_thickness", "base_width")
    fin_feature = _extrude_feature("hs_fin_body", "hs_fin", "fin_height")
    thermal_face = CoordinateSystem(
        id="hs_thermal_face",
        name="heat sink base",
        origin=(0, 0, 6.0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="thermal_face",
            csys=thermal_face,
            type="face",
            mate_hint="fixed",
            mate_with=["heat_sink/thermal_face", "pcb_bracket/mount_face", "enclosure/mount_face"],
        )
    ]
    return PartFamily(
        name="heat_sink",
        domain="thermal",
        display_name="Pin/fin heat sink",
        default_parameters=params,
        sketches=[base, fin],
        features=[base_feature, fin_feature],
        interfaces=interfaces,
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
    mount_face = CoordinateSystem(
        id="pcb_mount_face",
        name="pcb mounting face",
        origin=(0, 0, 3.0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="mount_face",
            csys=mount_face,
            type="face",
            mate_hint="fixed",
            mate_with=["pcb_bracket/mount_face", "enclosure/mount_face", "bracket/mount_face"],
        )
    ]
    return PartFamily(
        name="pcb_bracket",
        domain="electronics",
        display_name="PCB mounting bracket / standoff",
        default_parameters=params,
        sketches=[outline],
        features=[bracket],
        interfaces=interfaces,
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
    mount_face = CoordinateSystem(
        id="enc_mount_face",
        name="enclosure base",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="mount_face",
            csys=mount_face,
            type="face",
            mate_hint="fixed",
            mate_with=["enclosure/mount_face", "pcb_bracket/mount_face", "heat_sink/thermal_face"],
        )
    ]
    return PartFamily(
        name="enclosure",
        domain="electronics",
        display_name="Rectangular electronics enclosure",
        default_parameters=params,
        sketches=[base],
        features=[body],
        interfaces=interfaces,
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
    pin_a = CoordinateSystem(
        id="limb_pin_a",
        name="limb joint A",
        origin=(15.0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    pin_b = CoordinateSystem(
        id="limb_pin_b",
        name="limb joint B",
        origin=(135.0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="pin_a",
            csys=pin_a,
            type="pin",
            mate_hint="revolute",
            mate_with=["limb_segment/pin_b", "hub/bore", "mount/bore"],
        ),
        Interface(
            id="pin_b",
            csys=pin_b,
            type="pin",
            mate_hint="revolute",
            mate_with=["limb_segment/pin_a", "end_effector/pivot", "hub/bore"],
        ),
    ]
    return PartFamily(
        name="limb_segment",
        domain="humanoid",
        display_name="Robot limb tube with joint bores",
        default_parameters=params,
        sketches=[sketch],
        features=[feature],
        interfaces=interfaces,
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
    pivot = CoordinateSystem(
        id="gripper_pivot_csys",
        name="gripper pivot",
        origin=(0, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    slot_a = CoordinateSystem(
        id="gripper_slot_a",
        name="gripper jaw slot",
        origin=(30.0, 15.0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
        z_axis=(0, 0, 1),
    )
    interfaces = [
        Interface(
            id="pivot",
            csys=pivot,
            type="pin",
            mate_hint="revolute",
            mate_with=["end_effector/pivot", "limb_segment/pin_b"],
        ),
        Interface(
            id="slot_a",
            csys=slot_a,
            type="slot",
            mate_hint="prismatic",
            mate_with=["end_effector/slot_a"],
        ),
    ]
    return PartFamily(
        name="end_effector",
        domain="humanoid",
        display_name="Parallel-jaw gripper jaw",
        default_parameters=params,
        sketches=[sketch],
        features=[feature],
        interfaces=interfaces,
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


def _infer_legacy_interface_type(family: PartFamily) -> Literal[
    "mount", "pin", "bore", "slot", "flange", "face"
]:
    """Infer an interface type from a family's domain/mechanics."""
    name = family.name
    domain = family.domain
    if domain == "mechanical":
        if "link" in name or "limb" in name:
            return "pin"
        if "hub" in name or "pulley" in name:
            return "flange"
        if "bracket" in name or "mount" in name:
            return "mount"
        return "face"
    if domain == "aero":
        return "face"
    if domain == "thermal":
        return "face"
    if domain == "electronics":
        return "mount"
    if domain == "humanoid":
        if "limb" in name or "effector" in name:
            return "pin"
        return "face"
    return "face"


def _legacy_interfaces(family: PartFamily) -> list[Interface]:
    """Convert a pre-Phase-19 ``interface_csys`` into an ``Interface`` list."""
    legacy_csys = getattr(family, "interface_csys", None)
    if legacy_csys is None:
        return []
    return [
        Interface(
            id="interface",
            csys=legacy_csys,
            type=_infer_legacy_interface_type(family),
        )
    ]


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
    # Backward compatibility: convert any legacy interface_csys into the new
    # Interface representation on demand (currently kept at the family level).
    _ = family.interfaces or _legacy_interfaces(family)
    return Part(
        id=part_id,
        name=name_override or family.display_name,
        domain=family.domain,
        sketches=family.sketches,
        features=family.features,
    )
