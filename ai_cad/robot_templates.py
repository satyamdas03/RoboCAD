"""Parameterized humanoid and legged robot templates for RoboCAD.

Templates produce a full FeatureTree skeleton that decomposition + composer
can expand into part families. They also expose a consistent parameter set
(height, mass budget, payload, DOF, gait style) for downstream sizing and
simulation export.
"""
from __future__ import annotations

from typing import Any

from ai_cad.feature_tree import (
    Assembly,
    FeatureTree,
    Instance,
    KinematicJoint,
    Mate,
    MateEntity,
    Parameter,
    Part,
)


MM_TO_M = 0.001


def _param(name: str, value: float | int, unit: str = "mm", description: str = "") -> Parameter:
    """Build a Parameter entry for a template."""
    return Parameter(name=name, value=value, unit=unit, description=description)


def _identity_dict() -> dict[str, Any]:
    return {
        "a": [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    }


def _translate_dict(x: float, y: float, z: float) -> dict[str, Any]:
    return {
        "a": [[1.0, 0.0, 0.0, x], [0.0, 1.0, 0.0, y], [0.0, 0.0, 1.0, z], [0.0, 0.0, 0.0, 1.0]]
    }


def _link(name: str, length_mm: float = 100.0, radius_mm: float = 15.0) -> Part:
    """Create a minimal link part. The transpiler/family builder will replace it."""
    return Part(
        id=name,
        name=name,
        domain="mechanical",
        sketches=[],
        features=[],
    )


def _joint(
    jid: str,
    jtype: str,
    parent: str,
    child: str,
    origin: tuple[float, float, float],
    axis: tuple[float, float, float] | None = None,
    limits: tuple[float, float] | None = None,
) -> KinematicJoint:
    return KinematicJoint(
        id=jid,
        type=jtype,  # type: ignore[arg-type]
        parent_link=parent,
        child_link=child,
        origin=origin,
        axis=axis,
        limits=limits,
    )


def humanoid_template(
    height_mm: float = 1000.0,
    payload_kg: float = 5.0,
    mass_kg: float = 20.0,
    leg_dof: int = 6,
    arm_dof: int = 4,
    gait_style: str = "biped_walk",
) -> FeatureTree:
    """Return a FeatureTree skeleton for a biped humanoid robot."""
    scale = height_mm / 1000.0
    thigh_length = 220.0 * scale
    shin_length = 240.0 * scale
    foot_length = 160.0 * scale
    foot_width = 80.0 * scale
    torso_width = 200.0 * scale
    torso_depth = 120.0 * scale
    shoulder_span = 320.0 * scale
    upper_arm_length = 180.0 * scale
    forearm_length = 170.0 * scale
    hip_width = torso_width * 0.9

    parameters = [
        _param("robot_height", height_mm, "mm", "Overall standing height"),
        _param("payload_kg", payload_kg, "kg", "Design payload mass"),
        _param("robot_mass_kg", mass_kg, "kg", "Estimated total robot mass"),
        _param("leg_dof", leg_dof, "", "Number of active leg joints"),
        _param("arm_dof", arm_dof, "", "Number of active arm joints per side"),
        _param("gait_style", gait_style, "", "Gait style tag"),
        _param("thigh_length", thigh_length, "mm", "Thigh link length"),
        _param("shin_length", shin_length, "mm", "Shin link length"),
        _param("foot_length", foot_length, "mm", "Foot contact length"),
        _param("foot_width", foot_width, "mm", "Foot contact width"),
        _param("torso_width", torso_width, "mm", "Torso width"),
        _param("torso_depth", torso_depth, "mm", "Torso depth"),
        _param("shoulder_span", shoulder_span, "mm", "Shoulder separation"),
        _param("upper_arm_length", upper_arm_length, "mm", "Upper arm length"),
        _param("forearm_length", forearm_length, "mm", "Forearm length"),
        _param("hip_width", hip_width, "mm", "Hip joint separation"),
    ]

    # Placeholder parts matching the family builders. Composer will override placement.
    parts = [
        _link("torso_plate"),
        _link("hip_hub_l"),
        _link("hip_hub_r"),
        _link("shoulder_hub_l"),
        _link("shoulder_hub_r"),
        _link("thigh_l"),
        _link("thigh_r"),
        _link("shin_l"),
        _link("shin_r"),
        _link("foot_l"),
        _link("foot_r"),
        _link("upper_arm_l"),
        _link("upper_arm_r"),
        _link("forearm_l"),
        _link("forearm_r"),
        _link("hand_l"),
        _link("hand_r"),
    ]

    instances = [
        Instance(id="torso", part_id="torso_plate", name="torso"),
        Instance(id="hip_l", part_id="hip_hub_l", name="hip_l"),
        Instance(id="hip_r", part_id="hip_hub_r", name="hip_r"),
        Instance(id="shoulder_l", part_id="shoulder_hub_l", name="shoulder_l"),
        Instance(id="shoulder_r", part_id="shoulder_hub_r", name="shoulder_r"),
        Instance(id="thigh_l", part_id="thigh_l", name="thigh_l"),
        Instance(id="thigh_r", part_id="thigh_r", name="thigh_r"),
        Instance(id="shin_l", part_id="shin_l", name="shin_l"),
        Instance(id="shin_r", part_id="shin_r", name="shin_r"),
        Instance(id="foot_l", part_id="foot_l", name="foot_l"),
        Instance(id="foot_r", part_id="foot_r", name="foot_r"),
        Instance(id="upper_arm_l", part_id="upper_arm_l", name="upper_arm_l"),
        Instance(id="upper_arm_r", part_id="upper_arm_r", name="upper_arm_r"),
        Instance(id="forearm_l", part_id="forearm_l", name="forearm_l"),
        Instance(id="forearm_r", part_id="forearm_r", name="forearm_r"),
        Instance(id="hand_l", part_id="hand_l", name="hand_l"),
        Instance(id="hand_r", part_id="hand_r", name="hand_r"),
    ]

    joints = [
        _joint("hip_yaw_l", "revolute", "torso", "hip_l", (-hip_width / 2, 0.0, thigh_length + shin_length), axis=(0, 0, 1), limits=(-45, 45)),
        _joint("hip_pitch_l", "revolute", "hip_l", "thigh_l", (-hip_width / 2, 0.0, thigh_length + shin_length), axis=(0, 1, 0), limits=(-90, 90)),
        _joint("knee_l", "revolute", "thigh_l", "shin_l", (-hip_width / 2, 0.0, shin_length), axis=(0, 1, 0), limits=(0, 135)),
        _joint("ankle_l", "revolute", "shin_l", "foot_l", (-hip_width / 2, 0.0, 0.0), axis=(0, 1, 0), limits=(-45, 45)),
        _joint("hip_yaw_r", "revolute", "torso", "hip_r", (hip_width / 2, 0.0, thigh_length + shin_length), axis=(0, 0, 1), limits=(-45, 45)),
        _joint("hip_pitch_r", "revolute", "hip_r", "thigh_r", (hip_width / 2, 0.0, thigh_length + shin_length), axis=(0, 1, 0), limits=(-90, 90)),
        _joint("knee_r", "revolute", "thigh_r", "shin_r", (hip_width / 2, 0.0, shin_length), axis=(0, 1, 0), limits=(0, 135)),
        _joint("ankle_r", "revolute", "shin_r", "foot_r", (hip_width / 2, 0.0, 0.0), axis=(0, 1, 0), limits=(-45, 45)),
        _joint("shoulder_l", "revolute", "torso", "shoulder_l", (-shoulder_span / 2, 0.0, thigh_length + shin_length + 60.0 * scale), axis=(0, 1, 0), limits=(-180, 180)),
        _joint("elbow_l", "revolute", "shoulder_l", "upper_arm_l", (-shoulder_span / 2, 0.0, thigh_length + shin_length + 60.0 * scale - upper_arm_length), axis=(0, 1, 0), limits=(-135, 0)),
        _joint("wrist_l", "revolute", "upper_arm_l", "forearm_l", (-shoulder_span / 2, 0.0, thigh_length + shin_length + 60.0 * scale - upper_arm_length - forearm_length), axis=(0, 1, 0), limits=(-90, 90)),
        _joint("shoulder_r", "revolute", "torso", "shoulder_r", (shoulder_span / 2, 0.0, thigh_length + shin_length + 60.0 * scale), axis=(0, 1, 0), limits=(-180, 180)),
        _joint("elbow_r", "revolute", "shoulder_r", "upper_arm_r", (shoulder_span / 2, 0.0, thigh_length + shin_length + 60.0 * scale - upper_arm_length), axis=(0, 1, 0), limits=(-135, 0)),
        _joint("wrist_r", "revolute", "upper_arm_r", "forearm_r", (shoulder_span / 2, 0.0, thigh_length + shin_length + 60.0 * scale - upper_arm_length - forearm_length), axis=(0, 1, 0), limits=(-90, 90)),
    ]

    tree = FeatureTree(
        design_id=f"humanoid_{int(height_mm)}mm",
        domain="mechanical",
        prompt=f"{int(height_mm)} mm tall humanoid robot with {leg_dof} leg DOF, {arm_dof} arm DOF, {payload_kg} kg payload, {gait_style} gait",
        parameters=parameters,
        parts=parts,
        assemblies=[
            Assembly(
                id="main",
                name="humanoid",
                instances=instances,
                joints=joints,
            )
        ],
    )
    return tree


def quadruped_template(
    height_mm: float = 600.0,
    payload_kg: float = 10.0,
    mass_kg: float = 25.0,
    leg_dof: int = 3,
    gait_style: str = "trot",
) -> FeatureTree:
    """Return a FeatureTree skeleton for a quadruped robot."""
    scale = height_mm / 600.0
    body_length = 350.0 * scale
    body_width = 180.0 * scale
    hip_offset_x = body_length * 0.35
    hip_offset_y = body_width * 0.45
    thigh_length = 160.0 * scale
    shin_length = 160.0 * scale

    parameters = [
        _param("robot_height", height_mm, "mm", "Standing shoulder height"),
        _param("payload_kg", payload_kg, "kg", "Design payload mass"),
        _param("robot_mass_kg", mass_kg, "kg", "Estimated total robot mass"),
        _param("leg_dof", leg_dof, "", "Number of active joints per leg"),
        _param("gait_style", gait_style, "", "Gait style tag"),
        _param("body_length", body_length, "mm", "Body length"),
        _param("body_width", body_width, "mm", "Body width"),
        _param("thigh_length", thigh_length, "mm", "Thigh length"),
        _param("shin_length", shin_length, "mm", "Shin length"),
        _param("hip_offset_x", hip_offset_x, "mm", "Longitudinal hip offset"),
        _param("hip_offset_y", hip_offset_y, "mm", "Lateral hip offset"),
    ]

    parts = []
    instances = []
    joints = []

    parts.append(_link("body"))
    instances.append(Instance(id="body", part_id="body", name="body"))

    for suffix, sx, sy in [
        ("fl", -hip_offset_x, hip_offset_y),
        ("fr", -hip_offset_x, -hip_offset_y),
        ("rl", hip_offset_x, hip_offset_y),
        ("rr", hip_offset_x, -hip_offset_y),
    ]:
        hip_id = f"hip_{suffix}"
        thigh_id = f"thigh_{suffix}"
        shin_id = f"shin_{suffix}"
        foot_id = f"foot_{suffix}"
        parts.extend([_link(hip_id), _link(thigh_id), _link(shin_id), _link(foot_id)])
        instances.extend(
            [
                Instance(id=hip_id, part_id=hip_id, name=hip_id),
                Instance(id=thigh_id, part_id=thigh_id, name=thigh_id),
                Instance(id=shin_id, part_id=shin_id, name=shin_id),
                Instance(id=foot_id, part_id=foot_id, name=foot_id),
            ]
        )
        joints.extend(
            [
                _joint(f"hip_abd_{suffix}", "revolute", "body", hip_id, (sx, sy, height_mm * 0.8), axis=(1, 0, 0), limits=(-30, 30)),
                _joint(f"hip_pitch_{suffix}", "revolute", hip_id, thigh_id, (sx, sy, height_mm * 0.8), axis=(0, 1, 0), limits=(-90, 90)),
                _joint(f"knee_{suffix}", "revolute", thigh_id, shin_id, (sx, sy, height_mm * 0.8 - thigh_length), axis=(0, 1, 0), limits=(0, 135)),
                _joint(f"ankle_{suffix}", "revolute", shin_id, foot_id, (sx, sy, height_mm * 0.8 - thigh_length - shin_length), axis=(0, 1, 0), limits=(-45, 45)),
            ]
        )

    tree = FeatureTree(
        design_id=f"quadruped_{int(height_mm)}mm",
        domain="mechanical",
        prompt=f"{int(height_mm)} mm tall quadruped robot with {leg_dof} DOF legs, {payload_kg} kg payload, {gait_style} gait",
        parameters=parameters,
        parts=parts,
        assemblies=[Assembly(id="main", name="quadruped", instances=instances, joints=joints)],
    )
    return tree


def manipulator_on_base_template(
    base_size_mm: float = 300.0,
    reach_mm: float = 800.0,
    payload_kg: float = 2.0,
    mass_kg: float = 15.0,
    dof: int = 6,
) -> FeatureTree:
    """Return a FeatureTree skeleton for a manipulator mounted on a mobile base."""
    scale = reach_mm / 800.0
    link1 = 250.0 * scale
    link2 = 300.0 * scale
    link3 = 250.0 * scale

    parameters = [
        _param("base_size", base_size_mm, "mm", "Mobile base width/depth"),
        _param("reach", reach_mm, "mm", "Arm horizontal reach"),
        _param("payload_kg", payload_kg, "kg", "Arm payload"),
        _param("robot_mass_kg", mass_kg, "kg", "Total robot mass"),
        _param("arm_dof", dof, "", "Arm degrees of freedom"),
        _param("link1_length", link1, "mm", "Base / shoulder link"),
        _param("link2_length", link2, "mm", "Upper arm link"),
        _param("link3_length", link3, "mm", "Forearm link"),
    ]

    parts = [
        _link("mobile_base"),
        _link("shoulder_pan"),
        _link("shoulder_lift"),
        _link("upper_arm"),
        _link("elbow"),
        _link("forearm"),
        _link("wrist"),
        _link("end_effector"),
    ]
    instances = [Instance(id=p.id, part_id=p.id, name=p.id) for p in parts]
    joints = [
        _joint("base_fixed", "fixed", "world", "mobile_base", (0.0, 0.0, base_size_mm / 2), axis=None),
        _joint("shoulder_pan", "revolute", "mobile_base", "shoulder_pan", (0.0, 0.0, base_size_mm), axis=(0, 0, 1), limits=(-180, 180)),
        _joint("shoulder_lift", "revolute", "shoulder_pan", "shoulder_lift", (0.0, 0.0, base_size_mm + 40.0), axis=(0, 1, 0), limits=(-90, 90)),
        _joint("elbow", "revolute", "shoulder_lift", "upper_arm", (0.0, 0.0, base_size_mm + 40.0 + link1), axis=(0, 1, 0), limits=(-135, 0)),
        _joint("wrist_pitch", "revolute", "upper_arm", "forearm", (0.0, 0.0, base_size_mm + 40.0 + link1 + link2), axis=(0, 1, 0), limits=(-90, 90)),
        _joint("wrist_roll", "revolute", "forearm", "wrist", (0.0, 0.0, base_size_mm + 40.0 + link1 + link2 + link3), axis=(1, 0, 0), limits=(-180, 180)),
        _joint("ee_fixed", "fixed", "wrist", "end_effector", (0.0, 0.0, base_size_mm + 40.0 + link1 + link2 + link3 + 40.0), axis=None),
    ]

    tree = FeatureTree(
        design_id=f"manipulator_base_{int(reach_mm)}mm",
        domain="mechanical",
        prompt=f"Mobile base with {dof} DOF manipulator, {reach_mm} mm reach, {payload_kg} kg payload",
        parameters=parameters,
        parts=parts,
        assemblies=[Assembly(id="main", name="manipulator_on_base", instances=instances, joints=joints)],
    )
    return tree
