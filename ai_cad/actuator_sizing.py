"""Actuator sizing for RoboCAD humanoid / robot systems.

Conservative static formulas to estimate required joint torque, speed, and
power from payload, link dimensions, and safety factor. Not a full inverse
dynamics solver, but sufficient as a pre-design gate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ai_cad.feature_tree import Assembly, FeatureTree, KinematicJoint


G = 9.80665  # m/s^2


@dataclass
class ActuatorSpec:
    """Sizing result for one joint actuator."""

    joint_id: str
    type: str
    torque_nm: float | None = None
    speed_rpm: float | None = None
    power_w: float | None = None
    force_n: float | None = None  # for prismatic actuators


def _resolve_parameter(tree: FeatureTree, name: str, default: float) -> float:
    """Read a numeric parameter from the feature tree, falling back to default."""
    params = tree.parameter_dict()
    value = params.get(name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def size_actuators_for_tree(
    tree: FeatureTree,
    payload_kg: float = 5.0,
    safety_factor: float = 2.0,
    walking_speed_m_s: float = 0.5,
) -> dict[str, ActuatorSpec]:
    """Compute conservative actuator specs for every joint in the tree."""
    assembly = tree.assemblies[0] if tree.assemblies else None
    if assembly is None:
        return {}
    return size_actuators_for_assembly(tree, assembly, payload_kg, safety_factor, walking_speed_m_s)


def size_actuators_for_assembly(
    tree: FeatureTree,
    assembly: Assembly,
    payload_kg: float = 5.0,
    safety_factor: float = 2.0,
    walking_speed_m_s: float = 0.5,
) -> dict[str, ActuatorSpec]:
    """Compute conservative actuator specs for every joint in an assembly."""
    specs: dict[str, ActuatorSpec] = {}
    joints = assembly.joints or []

    thigh_length = _resolve_parameter(tree, "thigh_length", 220.0) * 0.001
    shin_length = _resolve_parameter(tree, "shin_length", 240.0) * 0.001
    segment_length = _resolve_parameter(tree, "segment_length", 150.0) * 0.001
    robot_height = _resolve_parameter(tree, "robot_height", 1000.0) * 0.001

    # Link mass estimate: 10% of payload per leg link, 5% per arm link.
    leg_link_mass = payload_kg * 0.10
    arm_link_mass = payload_kg * 0.05

    for joint in joints:
        jtype = joint.type
        jid = joint.id
        # Simple heuristic: required torque scales with payload * lever arm * safety.
        if jtype == "revolute":
            torque = 0.0
            speed_rpm = 30.0
            if "hip" in jid or "shoulder" in jid:
                lever = max(thigh_length, segment_length, robot_height * 0.15)
                torque = payload_kg * G * lever * safety_factor
                speed_rpm = 30.0
            elif "knee" in jid or "elbow" in jid:
                lever = max(shin_length, segment_length, robot_height * 0.12)
                # load includes lower leg/hand mass as well.
                torque = (payload_kg * 0.5 + leg_link_mass) * G * lever * safety_factor
                speed_rpm = 45.0
            elif "ankle" in jid or "wrist" in jid or "foot" in jid or "hand" in jid:
                lever = robot_height * 0.08
                torque = (payload_kg * 0.25 + leg_link_mass * 0.5) * G * lever * safety_factor
                speed_rpm = 60.0
            else:
                lever = max(thigh_length, segment_length)
                torque = payload_kg * G * lever * safety_factor
                speed_rpm = 45.0

            power = torque * (speed_rpm * 2 * math.pi / 60)
            specs[jid] = ActuatorSpec(
                joint_id=jid,
                type=jtype,
                torque_nm=round(torque, 4),
                speed_rpm=round(speed_rpm, 2),
                power_w=round(power, 4),
            )
        elif jtype == "prismatic":
            force = payload_kg * G * safety_factor
            speed_m_s = walking_speed_m_s * 0.2
            power = force * speed_m_s
            specs[jid] = ActuatorSpec(
                joint_id=jid,
                type=jtype,
                force_n=round(force, 4),
                speed_rpm=round(speed_m_s * 1000.0, 2),  # mm/s as a proxy display
                power_w=round(power, 4),
            )

    return specs


def actuator_summary(specs: dict[str, ActuatorSpec]) -> dict[str, Any]:
    """Aggregate actuator sizing data for reports."""
    if not specs:
        return {}
    torques = [s.torque_nm for s in specs.values() if s.torque_nm is not None]
    forces = [s.force_n for s in specs.values() if s.force_n is not None]
    powers = [s.power_w for s in specs.values() if s.power_w is not None]
    return {
        "joint_count": len(specs),
        "max_torque_nm": max(torques) if torques else 0.0,
        "max_force_n": max(forces) if forces else 0.0,
        "total_power_w": sum(powers) if powers else 0.0,
    }
