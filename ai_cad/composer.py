"""Compose decomposed system intents into a single FeatureTree assembly.

Phase 18 scope: take a ``DecompositionResult`` (sub-parts + domains + families)
and produce a domain-tagged ``FeatureTree`` containing multiple ``Part`` objects,
an ``Assembly`` of ``Instance`` placements, and inferred ``Mate`` relationships.
"""
from __future__ import annotations

import math
from typing import Any

from ai_cad.decomposition import DecomposedPart, DecompositionResult
from ai_cad.feature_tree import (
    Assembly,
    CoordinateSystem,
    FeatureTree,
    Instance,
    KinematicJoint,
    Mate,
    MateEntity,
    Parameter,
    Part,
)
from ai_cad.intent_parser import parse_domain_intent
from ai_cad.mate_inference import infer_mates
from ai_cad.part_families import get_family, instantiate_family


# Orientation helpers expressed as (rotation_x, rotation_y, rotation_z) degrees.
_ORIENTATION_PRESETS: dict[str, tuple[float, float, float]] = {
    "up": (0.0, 0.0, 0.0),
    "right": (0.0, 0.0, 90.0),
    "down": (0.0, 0.0, 180.0),
    "left": (0.0, 0.0, -90.0),
    "forward": (0.0, -90.0, 0.0),
    "back": (0.0, 90.0, 0.0),
}


def _unique_param_name(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    idx = 2
    while f"{base}_{idx}" in used:
        idx += 1
    name = f"{base}_{idx}"
    used.add(name)
    return name


def _effective_parameters(dp: DecomposedPart) -> list[Parameter]:
    """Return family defaults overridden by decomposition parameters."""
    family = get_family(dp.family)
    merged = {p.name: p for p in family.default_parameters}
    for p in dp.parameters:
        merged[p.name] = p
    return list(merged.values())


def _merge_global_parameters(parts: list[DecomposedPart]) -> list[Parameter]:
    """Collect effective parameters for all sub-parts.

    Part families are designed so their default parameter names do not collide
    across the standard Phase 18 assemblies. If a collision occurs we keep the
    first occurrence and drop duplicates.
    """
    used: set[str] = set()
    merged: list[Parameter] = []
    for dp in parts:
        for p in _effective_parameters(dp):
            if p.name in used:
                continue
            used.add(p.name)
            merged.append(p)
    return merged


def _build_part(dp: DecomposedPart) -> Part:
    """Create a Part from a decomposition entry, merging family defaults + intent."""
    # Start from the registered part family.
    part = instantiate_family(
        dp.family,
        dp.id,
        name_override=dp.name,
        parameter_overrides=dp.parameters,
    )
    # Optionally enrich with a per-domain LLM intent. In Phase 18 this is off by
    # default for speed/tests; the sub_prompt is stored for future use.
    return part


def _place_quad_copter(result: DecompositionResult) -> tuple[list[Instance], list[Mate]] | None:
    """If the result matches a quadcopter layout, return instances + mates."""
    text = result.prompt.lower()
    if not any(w in text for w in {"quadcopter", "drone", "multirotor", "hexacopter", "octocopter", "uav"}):
        return None

    instances: list[Instance] = []
    mates: list[Mate] = []
    arm_length = 100.0
    arm_count = 4
    for dp in result.parts:
        if dp.id == "motor_arm":
            if dp.parameters:
                for p in dp.parameters:
                    if p.name == "link_length":
                        try:
                            arm_length = float(p.value)
                        except (TypeError, ValueError):
                            pass
            arm_count = dp.count

    # Place frame hub at origin.
    instances.append(Instance(id="i_frame_hub", part_id="frame_hub", name="Frame hub"))

    # Place motor arms radially.
    for i in range(arm_count):
        angle_deg = i * (360.0 / arm_count)
        rad = math.radians(angle_deg)
        # Arm extends from hub center outward.
        tx = (arm_length / 2) * math.cos(rad)
        ty = (arm_length / 2) * math.sin(rad)
        inst_id = f"i_motor_arm_{i}"
        instances.append(
            Instance(
                id=inst_id,
                part_id="motor_arm",
                name=f"Motor arm {i + 1}",
                transform={
                    "translation": (tx, ty, 0.0),
                    "rotation": (0.0, 0.0, angle_deg),
                },
            )
        )
        # Mate arm root to hub (coincident origin + concentric Z).
        mates.append(
            Mate(
                id=f"m_arm_hub_{i}",
                type="fixed",
                entities=[
                    MateEntity(instance_id=inst_id),
                    MateEntity(instance_id="i_frame_hub"),
                ],
            )
        )

    # Place motor mounts at the ends of arms.
    for i in range(arm_count):
        angle_deg = i * (360.0 / arm_count)
        rad = math.radians(angle_deg)
        tx = arm_length * math.cos(rad)
        ty = arm_length * math.sin(rad)
        inst_id = f"i_motor_mount_{i}"
        instances.append(
            Instance(
                id=inst_id,
                part_id="motor_mount",
                name=f"Motor mount {i + 1}",
                transform={
                    "translation": (tx, ty, 0.0),
                    "rotation": (0.0, 0.0, angle_deg),
                },
            )
        )
        mates.append(
            Mate(
                id=f"m_mount_arm_{i}",
                type="fixed",
                entities=[
                    MateEntity(instance_id=inst_id),
                    MateEntity(instance_id=f"i_motor_arm_{i}"),
                ],
            )
        )

    # Optional aero shell above hub.
    if any(dp.id == "aero_shell" for dp in result.parts):
        instances.append(
            Instance(
                id="i_aero_shell",
                part_id="aero_shell",
                name="Aerodynamic shell",
                transform={"translation": (0.0, 0.0, 25.0)},
            )
        )

    return instances, mates


def _place_robot_arm(result: DecompositionResult) -> tuple[list[Instance], list[Mate]] | None:
    """If the result matches a robot arm layout, build an articulated serial arm.

    Parts are expected from the rule-based decomposition:
      * arm_base   -> mount family
      * upper_link -> limb_segment family
      * forearm_link -> limb_segment family
      * gripper    -> end_effector family (count 2)

    The layout keeps every link in the global XY plane (z = base_thickness) and
    aligns the limb_segment pin interfaces so the upper and forearm form a real
    revolute chain.  The two end_effector jaws form a parallel-jaw prismatic
    gripper that opens symmetrically along the global Y axis.
    """
    text = result.prompt.lower()
    if not any(w in text for w in {"robot arm", "manipulator", "robotic arm"}):
        return None

    # Read geometry from the decomposed parts / family defaults.
    segment_length = _param_value(result.parts, "upper_link", "segment_length", 150.0)
    end_offset = _param_value(result.parts, "upper_link", "end_offset", 15.0)
    base_thickness = _param_value(result.parts, "arm_base", "mount_thickness", 3.0)

    jaw_thickness = _param_value(result.parts, "gripper", "jaw_thickness", 8.0)
    jaw_travel = _param_value(result.parts, "gripper", "jaw_travel", 15.0)

    # Effective distance between the two pin centers on a limb segment.
    body_length = segment_length - 2.0 * end_offset
    shoulder_z = base_thickness

    instances: list[Instance] = []
    mates: list[Mate] = []

    # Base plate sits on the ground; its top face is the shoulder plane.
    instances.append(Instance(id="i_arm_base", part_id="arm_base", name="Arm base"))

    # Upper arm: place it so its pin_a coincides with the shoulder joint.
    # limb_pin_a is at local (end_offset, 0, 0), so shift the part back by end_offset.
    upper_origin = (-end_offset, 0.0, shoulder_z)
    instances.append(
        Instance(
            id="i_upper_link",
            part_id="upper_link",
            name="Upper arm link",
            transform={"translation": upper_origin, "rotation": (0.0, 0.0, 0.0)},
        )
    )
    # Shoulder fixed to base, aligned at the upper pin_a.
    mates.append(
        Mate(
            id="m_base_upper",
            type="fixed",
            entities=[
                MateEntity(instance_id="i_arm_base", csys_id="origin"),
                MateEntity(instance_id="i_upper_link", csys_id="limb_pin_a"),
            ],
        )
    )

    # Forearm: place it so its pin_a coincides with the upper pin_b (elbow).
    # upper pin_b world x = upper_origin.x + (segment_length - end_offset)
    #                     = -end_offset + segment_length - end_offset
    #                     = segment_length - 2*end_offset = body_length.
    elbow_x = body_length
    forearm_origin = (elbow_x - end_offset, 0.0, shoulder_z)
    instances.append(
        Instance(
            id="i_forearm_link",
            part_id="forearm_link",
            name="Forearm link",
            transform={"translation": forearm_origin, "rotation": (0.0, 0.0, 0.0)},
        )
    )
    # Elbow: explicit revolute mate between upper pin_b and forearm pin_a.
    mates.append(
        Mate(
            id="m_elbow",
            type="revolute",
            entities=[
                # Moving child first, as required by the motion-mate -> joint builder.
                MateEntity(instance_id="i_forearm_link", csys_id="limb_pin_a"),
                MateEntity(instance_id="i_upper_link", csys_id="limb_pin_b"),
            ],
        )
    )

    # Wrist is at forearm pin_b.
    wrist_x = elbow_x + body_length
    # Gripper mount plane is the same Z as the limb segments.
    jaw_z = shoulder_z

    # Parallel-jaw gripper: two mirrored end_effector instances.
    if any(dp.id == "gripper" for dp in result.parts):
        for side in (0, 1):
            # The end_effector family draws the jaw body on the +Y side of its pivot.
            # Mirror the second jaw 180° around the global X axis (Y -> -Y, Z -> -Z).
            # Because the jaw is a uniform extrusion, flipping Z just moves the body
            # to the -Z side of the pivot; translating up by jaw_thickness puts both
            # jaw bodies in the same Z range above the forearm.
            rotation = (0.0, 0.0, 0.0) if side == 0 else (180.0, 0.0, 0.0)
            jaw_origin = (wrist_x, 0.0, jaw_z + jaw_thickness)
            instances.append(
                Instance(
                    id=f"i_gripper_{side}",
                    part_id="gripper",
                    name=f"Gripper jaw {side + 1}",
                    transform={"translation": jaw_origin, "rotation": rotation},
                )
            )
            # Each jaw slides along Y to open/close.  Jaw 0 is on the +Y side and
            # opens by moving +Y; jaw 1 is on the -Y side and opens by moving -Y.
            axis = (0.0, 1.0, 0.0) if side == 0 else (0.0, -1.0, 0.0)
            mates.append(
                Mate(
                    id=f"m_gripper_{side}_forearm",
                    type="prismatic",
                    entities=[
                        # Moving child first.
                        MateEntity(instance_id=f"i_gripper_{side}", csys_id="gripper_pivot_csys"),
                        MateEntity(instance_id="i_forearm_link", csys_id="limb_pin_b"),
                    ],
                    parameters={"distance": jaw_travel, "axis": axis},
                )
            )

    return instances, mates


def _param_value(
    parts: list[DecomposedPart],
    part_id: str,
    param_name: str,
    default: float,
) -> float:
    """Read a numeric parameter from a decomposed part or its family defaults."""
    for dp in parts:
        if dp.id != part_id:
            continue
        for p in dp.parameters:
            if p.name == param_name:
                try:
                    return float(p.value)
                except (TypeError, ValueError):
                    return default
        try:
            family = get_family(dp.family)
            for p in family.default_parameters:
                if p.name == param_name:
                    try:
                        return float(p.value)
                    except (TypeError, ValueError):
                        return default
        except KeyError:
            return default
    return default


def _place_electronics_stack(
    result: DecompositionResult,
) -> tuple[list[Instance], list[Mate]] | None:
    """If the result matches an electronics stack, return instances + mates."""
    text = result.prompt.lower()
    if not any(
        w in text
        for w in {
            "raspberry pi",
            "arduino",
            "pcb with enclosure",
            "electronics enclosure",
            "motor driver stack",
            "flight controller",
            "esc",
            "board with case",
        }
    ):
        return None

    instances: list[Instance] = []
    mates: list[Mate] = []

    has_pcb = any(dp.id == "pcb" for dp in result.parts)
    has_enclosure = any(dp.id == "enclosure" for dp in result.parts)
    has_fan = any(dp.id == "fan_mount" for dp in result.parts)
    has_cable = any(dp.id == "cable_channel" for dp in result.parts)
    has_spreader = any(dp.id == "heat_spreader" for dp in result.parts)
    has_connector = any(dp.id == "connector" for dp in result.parts)
    has_compute = any(dp.id == "compute_module" for dp in result.parts)
    has_event_camera = any(dp.id == "event_camera_mount" for dp in result.parts)

    standoff_height = _param_value(result.parts, "enclosure", "standoff_height", 6.0)
    enc_height = _param_value(result.parts, "enclosure", "enc_height", 40.0)
    pcb_thickness = _param_value(result.parts, "pcb", "pcb_thickness", 1.6)

    # Enclosure shell sits at the origin; its standoffs point upward.
    if has_enclosure:
        instances.append(
            Instance(id="i_enclosure", part_id="enclosure", name="Enclosure")
        )

    # PCB rests on top of the standoffs.
    if has_pcb:
        pcb_z = standoff_height if has_enclosure else 0.0
        instances.append(
            Instance(
                id="i_pcb",
                part_id="pcb",
                name="PCB",
                transform={"translation": (0.0, 0.0, pcb_z)},
            )
        )
        if has_enclosure:
            mates.append(
                Mate(
                    id="m_pcb_enclosure",
                    type="fixed",
                    entities=[
                        MateEntity(instance_id="i_pcb"),
                        MateEntity(instance_id="i_enclosure"),
                    ],
                )
            )

    # Heat spreader sits between the PCB and the enclosure floor.
    if has_spreader:
        spreader_thickness = _param_value(
            result.parts, "heat_spreader", "spread_thickness", 3.0
        )
        spreader_z = (
            standoff_height - spreader_thickness if has_enclosure else 0.0
        )
        instances.append(
            Instance(
                id="i_heat_spreader",
                part_id="heat_spreader",
                name="Heat spreader",
                transform={"translation": (0.0, 0.0, spreader_z)},
            )
        )
        if has_enclosure:
            mates.append(
                Mate(
                    id="m_spreader_enclosure",
                    type="fixed",
                    entities=[
                        MateEntity(instance_id="i_heat_spreader"),
                        MateEntity(instance_id="i_enclosure"),
                    ],
                )
            )

    # Fan mount on top of the enclosure lid.
    if has_fan:
        fan_z = enc_height if has_enclosure else 40.0
        instances.append(
            Instance(
                id="i_fan_mount",
                part_id="fan_mount",
                name="Fan mount",
                transform={"translation": (0.0, 0.0, fan_z)},
            )
        )
        if has_enclosure:
            mates.append(
                Mate(
                    id="m_fan_enclosure",
                    type="fixed",
                    entities=[
                        MateEntity(instance_id="i_fan_mount"),
                        MateEntity(instance_id="i_enclosure"),
                    ],
                )
            )

    # Cable channel runs along the back of the enclosure.
    if has_cable:
        cable_y = -60.0
        instances.append(
            Instance(
                id="i_cable_channel",
                part_id="cable_channel",
                name="Cable channel",
                transform={"translation": (0.0, cable_y, 10.0)},
            )
        )
        if has_enclosure:
            mates.append(
                Mate(
                    id="m_cable_enclosure",
                    type="fixed",
                    entities=[
                        MateEntity(instance_id="i_cable_channel"),
                        MateEntity(instance_id="i_enclosure"),
                    ],
                )
            )

    # Generic connectors sit on the PCB top face along one edge.
    if has_connector and has_pcb:
        for idx, _ in enumerate(
            [dp for dp in result.parts if dp.id == "connector"]
        ):
            for side in range(2):
                instances.append(
                    Instance(
                        id=f"i_connector_{idx}_{side}",
                        part_id="connector",
                        name=f"Connector {idx + 1}-{side + 1}",
                        transform={
                            "translation": (-20.0 + side * 40.0, 30.0, pcb_z + 1.6)
                        },
                    )
                )
                mates.append(
                    Mate(
                        id=f"m_connector_{idx}_{side}_pcb",
                        type="fixed",
                        entities=[
                            MateEntity(instance_id=f"i_connector_{idx}_{side}"),
                            MateEntity(instance_id="i_pcb"),
                        ],
                    )
                )

    # Onboard compute module sits above the PCB, carrying compute budget metadata.
    if has_compute:
        compute_z = pcb_z + pcb_thickness if has_pcb else standoff_height
        instances.append(
            Instance(
                id="i_compute_module",
                part_id="compute_module",
                name="Compute module",
                transform={"translation": (0.0, 10.0, compute_z)},
            )
        )
        target_id = "i_pcb" if has_pcb else "i_enclosure"
        mates.append(
            Mate(
                id="m_compute_pcb",
                type="fixed",
                entities=[
                    MateEntity(instance_id="i_compute_module"),
                    MateEntity(instance_id=target_id),
                ],
            )
        )

    # Event camera mount attached to the front of the stack.
    if has_event_camera:
        cam_z = enc_height if has_enclosure else 10.0
        instances.append(
            Instance(
                id="i_event_camera",
                part_id="event_camera_mount",
                name="Event camera mount",
                transform={"translation": (0.0, 25.0, cam_z)},
            )
        )
        target_id = "i_enclosure" if has_enclosure else "i_pcb" if has_pcb else None
        if target_id:
            mates.append(
                Mate(
                    id="m_event_camera_stack",
                    type="fixed",
                    entities=[
                        MateEntity(instance_id="i_event_camera"),
                        MateEntity(instance_id=target_id),
                    ],
                )
            )

    return instances, mates


def _generic_layout(result: DecompositionResult) -> tuple[list[Instance], list[Mate]]:
    """Fallback layout: place instances in a row along X."""
    instances: list[Instance] = []
    mates: list[Mate] = []
    x = 0.0
    spacing = 60.0
    prev_id: str | None = None
    for dp in result.parts:
        for i in range(dp.count):
            inst_id = f"i_{dp.id}_{i}" if dp.count > 1 else f"i_{dp.id}"
            instances.append(
                Instance(
                    id=inst_id,
                    part_id=dp.id,
                    name=f"{dp.name} {i + 1}" if dp.count > 1 else dp.name,
                    transform={"translation": (x, 0.0, 0.0)},
                )
            )
            if prev_id is not None:
                mates.append(
                    Mate(
                        id=f"m_{inst_id}_{prev_id}",
                        type="fixed",
                        entities=[
                            MateEntity(instance_id=inst_id),
                            MateEntity(instance_id=prev_id),
                        ],
                    )
                )
            prev_id = inst_id
            x += spacing
    return instances, mates


def _layout_parts(result: DecompositionResult) -> tuple[list[Instance], list[Mate]]:
    """Choose a domain-specific layout or fall back to a linear row."""
    layout = _place_quad_copter(result)
    if layout:
        return layout
    layout = _place_robot_arm(result)
    if layout:
        return layout
    layout = _place_electronics_stack(result)
    if layout:
        return layout
    layout = _place_humanoid(result)
    if layout:
        return layout
    return _generic_layout(result)


def compose_feature_tree(
    result: DecompositionResult,
    *,
    enrich_with_intent: bool = False,
) -> FeatureTree:
    """Build a ``FeatureTree`` from a decomposition result.

    Args:
        result: Decomposition plan produced by ``ai_cad.decomposition``.
        enrich_with_intent: If True, call the per-domain LLM intent parser for
            each sub-part. Disabled by default for speed and determinism.

    Returns:
        A domain-tagged ``FeatureTree`` with ``parts`` and an ``assembly``.
    """
    parts: list[Part] = []
    for dp in result.parts:
        if enrich_with_intent:
            intent = parse_domain_intent(dp.sub_prompt, domain=dp.domain)
            # Merge intent parameters on top of family defaults.
            overrides = dp.parameters + [
                Parameter(name=p.name, value=p.value, unit=p.unit, description=p.description)
                for p in intent.parameters
            ]
            part = instantiate_family(dp.family, dp.id, name_override=dp.name, parameter_overrides=overrides)
        else:
            part = _build_part(dp)
        parts.append(part)

    instances, mates = _layout_parts(result)

    # Phase 19: for mechanical assemblies, infer mates + kinematic joints from
    # part-family interfaces. Keep the layout mates if inference returns nothing.
    inferred_mates: list[Mate] = []
    inferred_joints: list[KinematicJoint] = []
    if result.primary_domain == "mechanical" and len(parts) >= 2:
        draft_assembly = Assembly(
            id="asm_1",
            name="Generated assembly",
            domain=result.primary_domain,
            instances=instances,
            mates=mates,
        )
        try:
            inferred_mates, inferred_joints = infer_mates(
                FeatureTree(
                    design_id="draft",
                    prompt=result.prompt,
                    parts=parts,
                    assemblies=[draft_assembly],
                ),
                draft_assembly,
                respect_existing_mates=True,
            )
        except Exception:
            inferred_mates, inferred_joints = [], []

        # Explicit motion mates (e.g. prismatic gripper jaws) are authoritative:
        # do not let inference attach the moving child to any other parent, and do
        # not let inference add redundant fixed mates for already-fixed parts.
        motion_children: set[str] = set()
        fixed_instances: set[str] = set()
        for m in mates:
            if len(m.entities) < 2:
                continue
            ids = [e.instance_id for e in m.entities]
            if m.type in ("revolute", "prismatic"):
                # In explicit motion mates the first entity is the moving child.
                motion_children.add(ids[0])
            else:
                fixed_instances.update(ids)

        def _motion_pair(joint: KinematicJoint) -> frozenset[str]:
            return frozenset({joint.parent_link, joint.child_link})

        inferred_mates = [
            m
            for m in inferred_mates
            if len(m.entities) >= 2
            and not any(e.instance_id in motion_children for e in m.entities)
            and not (
                m.type == "fixed"
                and any(e.instance_id in fixed_instances for e in m.entities)
            )
        ]
        inferred_joints = [
            j
            for j in inferred_joints
            if not (j.parent_link in motion_children or j.child_link in motion_children)
            and not (
                j.type == "fixed"
                and (j.parent_link in fixed_instances or j.child_link in fixed_instances)
            )
        ]

        # Inferred mates replace explicit layout mates when they are more
        # specific (e.g. prismatic gripper jaws vs fixed). Deduplicate by
        # instance pair, preferring non-fixed, motion-carrying mates.
        if inferred_mates:
            seen_pairs: set[frozenset[str]] = set()
            merged: list[Mate] = []
            for m in mates + inferred_mates:
                if len(m.entities) < 2:
                    continue
                pair = frozenset(e.instance_id for e in m.entities)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                existing_idx = next(
                    (
                        i
                        for i, x in enumerate(merged)
                        if frozenset(e.instance_id for e in x.entities) == pair
                    ),
                    None,
                )
                if existing_idx is None:
                    merged.append(m)
                elif merged[existing_idx].type == "fixed" and m.type != "fixed":
                    merged[existing_idx] = m
            mates = merged

        # Emit joints for explicit motion mates (layout provides these when the
        # composer already knows the mechanism, e.g. a parallel-jaw gripper).
        instances_by_id = {inst.id: inst for inst in instances}
        for m in mates:
            if m.type not in ("revolute", "prismatic"):
                continue
            child_id = m.entities[0].instance_id
            parent_id = m.entities[1].instance_id
            if child_id not in instances_by_id or parent_id not in instances_by_id:
                continue
            child_t = instances_by_id[child_id].transform or {}
            parent_t = instances_by_id[parent_id].transform or {}
            c_origin = child_t.get("translation") or (0.0, 0.0, 0.0)
            p_origin = parent_t.get("translation") or (0.0, 0.0, 0.0)
            # Use an explicit axis from the mate parameters when provided;
            # otherwise derive the joint axis from the child-parent origin vector.
            param_axis = (m.parameters or {}).get("axis")
            if (
                param_axis
                and isinstance(param_axis, (list, tuple))
                and len(param_axis) == 3
            ):
                ax, ay, az = (float(v) for v in param_axis)
                axis = (ax, ay, az)
            else:
                dx = c_origin[0] - p_origin[0]
                dy = c_origin[1] - p_origin[1]
                dz = c_origin[2] - p_origin[2]
                length = math.sqrt(dx * dx + dy * dy + dz * dz)
                if length > 1e-9:
                    axis = (dx / length, dy / length, dz / length)
                else:
                    axis = (0.0, 0.0, 1.0)
            if m.type == "revolute":
                limits = (-180.0, 180.0)
            else:
                dist = abs(float(m.parameters.get("distance", 15.0))) if m.parameters else 15.0
                limits = (0.0, dist)
            inferred_joints.append(
                KinematicJoint(
                    id=f"j_{parent_id}_{child_id}",
                    type=m.type,
                    parent_link=parent_id,
                    child_link=child_id,
                    origin=c_origin,
                    axis=axis,
                    limits=limits,
                )
            )

    # Deduplicate instance IDs (safety) and ensure every part_id exists.
    seen_ids: set[str] = set()
    valid_instances: list[Instance] = []
    part_ids = {p.id for p in parts}
    for inst in instances:
        if inst.id in seen_ids:
            continue
        if inst.part_id not in part_ids:
            continue
        seen_ids.add(inst.id)
        valid_instances.append(inst)

    # Filter mates referencing valid instances.
    valid_instance_ids = {inst.id for inst in valid_instances}
    valid_mates = [
        m for m in mates
        if all(e.instance_id in valid_instance_ids for e in m.entities)
    ]

    assembly = Assembly(
        id="asm_1",
        name="Generated assembly",
        domain=result.primary_domain,
        instances=valid_instances,
        mates=valid_mates,
        joints=inferred_joints,
    )

    tree = FeatureTree(
        design_id="decomposed",
        prompt=result.prompt,
        domain=result.primary_domain,
        parameters=_merge_global_parameters(result.parts),
        parts=parts,
        assemblies=[assembly],
        coordinate_systems=[
            CoordinateSystem(
                id="origin",
                name="Global origin",
                origin=(0, 0, 0),
                x_axis=(1, 0, 0),
                y_axis=(0, 1, 0),
                z_axis=(0, 0, 1),
            )
        ],
    )
    return tree


# ---------------------------------------------------------------------------
# Humanoid / legged robot layout
# ---------------------------------------------------------------------------


def _place_humanoid(result: DecompositionResult) -> tuple[list[Instance], list[Mate]] | None:
    """If the result matches a humanoid/biped/quadruped layout, build an articulated chain."""
    text = result.prompt.lower()
    if not any(w in text for w in {"humanoid", "biped", "quadruped", "leg", "torso", "manipulator on base", "robot on base"}):
        return None

    instances: list[Instance] = []
    mates: list[Mate] = []

    # Default scaling from prompt keywords.
    robot_height = 1000.0
    found = _find_number_near(text, "mm", "tall") or _find_number_near(text, "mm", "height")
    if found:
        robot_height = found
    elif "small" in text or "mini" in text:
        robot_height = 400.0
    elif "large" in text:
        robot_height = 1500.0

    thigh_length = robot_height * 0.22
    shin_length = robot_height * 0.24
    foot_length = robot_height * 0.10
    torso_width = robot_height * 0.12
    torso_z = thigh_length + shin_length

    # Torso plate at top of legs.
    instances.append(
        Instance(
            id="i_torso",
            part_id="torso_plate",
            name="Torso",
            transform={"translation": (0.0, 0.0, torso_z)},
        )
    )

    leg_count = 2 if "biped" in text or "humanoid" in text or "manipulator on base" in text or "robot on base" in text else 4
    leg_names = ["left", "right"] if leg_count == 2 else ["front_left", "front_right", "back_left", "back_right"]
    side_signs = [(-1, 1), (1, 1)] if leg_count == 2 else [(-1, 1), (1, 1), (-1, -1), (1, -1)]

    for i, (name, (sx, sy)) in enumerate(zip(leg_names, side_signs)):
        hip_x = sx * torso_width / 2
        hip_y = sy * torso_width / 3

        hip_id = f"i_hip_{name}"
        instances.append(
            Instance(
                id=hip_id,
                part_id="hip_hub",
                name=f"Hip {name}",
                transform={"translation": (hip_x, hip_y, torso_z)},
            )
        )
        mates.append(
            Mate(
                id=f"m_torso_hip_{name}",
                type="fixed",
                entities=[MateEntity(instance_id="i_torso"), MateEntity(instance_id=hip_id)],
            )
        )

        thigh_id = f"i_thigh_{name}"
        # Thigh hangs downward from hip.
        instances.append(
            Instance(
                id=thigh_id,
                part_id="thigh",
                name=f"Thigh {name}",
                transform={
                    "translation": (hip_x, hip_y, torso_z - thigh_length / 2),
                    "rotation": (0.0, 0.0, 0.0),
                },
            )
        )
        mates.append(
            Mate(
                id=f"m_hip_thigh_{name}",
                type="revolute",
                entities=[MateEntity(instance_id=hip_id), MateEntity(instance_id=thigh_id)],
            )
        )

        knee_id = f"i_knee_{name}"
        knee_z = torso_z - thigh_length
        instances.append(
            Instance(
                id=knee_id,
                part_id="hip_hub",
                name=f"Knee {name}",
                transform={"translation": (hip_x, hip_y, knee_z)},
            )
        )
        mates.append(
            Mate(
                id=f"m_thigh_knee_{name}",
                type="revolute",
                entities=[MateEntity(instance_id=thigh_id), MateEntity(instance_id=knee_id)],
            )
        )

        shin_id = f"i_shin_{name}"
        instances.append(
            Instance(
                id=shin_id,
                part_id="shin",
                name=f"Shin {name}",
                transform={
                    "translation": (hip_x, hip_y, knee_z - shin_length / 2),
                    "rotation": (0.0, 0.0, 0.0),
                },
            )
        )
        mates.append(
            Mate(
                id=f"m_knee_shin_{name}",
                type="revolute",
                entities=[MateEntity(instance_id=knee_id), MateEntity(instance_id=shin_id)],
            )
        )

        foot_id = f"i_foot_{name}"
        instances.append(
            Instance(
                id=foot_id,
                part_id="foot",
                name=f"Foot {name}",
                transform={
                    "translation": (hip_x + foot_length / 4, hip_y, torso_z - thigh_length - shin_length),
                    "rotation": (0.0, 0.0, 0.0),
                },
            )
        )
        mates.append(
            Mate(
                id=f"m_shin_foot_{name}",
                type="revolute",
                entities=[MateEntity(instance_id=shin_id), MateEntity(instance_id=foot_id)],
            )
        )

    # Optional arms for biped/humanoid.
    arm_parts = {"shoulder_hub", "upper_arm", "forearm", "hand"}
    has_arms = any(dp.id in arm_parts for dp in result.parts)
    if has_arms:
        for side, sx in [("left", -1), ("right", 1)]:
            shoulder_x = sx * torso_width / 2
            shoulder_z = torso_z + 20.0
            shoulder_id = f"i_shoulder_{side}"
            instances.append(
                Instance(
                    id=shoulder_id,
                    part_id="shoulder_hub",
                    name=f"Shoulder {side}",
                    transform={"translation": (shoulder_x, 0.0, shoulder_z)},
                )
            )
            mates.append(
                Mate(
                    id=f"m_torso_shoulder_{side}",
                    type="fixed",
                    entities=[MateEntity(instance_id="i_torso"), MateEntity(instance_id=shoulder_id)],
                )
            )
            upper_id = f"i_upper_arm_{side}"
            instances.append(
                Instance(
                    id=upper_id,
                    part_id="upper_arm",
                    name=f"Upper arm {side}",
                    transform={
                        "translation": (shoulder_x, 0.0, shoulder_z - thigh_length * 0.6),
                        "rotation": (0.0, 0.0, 0.0),
                    },
                )
            )
            mates.append(
                Mate(
                    id=f"m_shoulder_upper_{side}",
                    type="revolute",
                    entities=[MateEntity(instance_id=shoulder_id), MateEntity(instance_id=upper_id)],
                )
            )
            elbow_id = f"i_elbow_{side}"
            instances.append(
                Instance(
                    id=elbow_id,
                    part_id="hip_hub",
                    name=f"Elbow {side}",
                    transform={"translation": (shoulder_x, 0.0, shoulder_z - thigh_length * 0.6)},
                )
            )
            mates.append(
                Mate(
                    id=f"m_upper_elbow_{side}",
                    type="revolute",
                    entities=[MateEntity(instance_id=upper_id), MateEntity(instance_id=elbow_id)],
                )
            )
            forearm_id = f"i_forearm_{side}"
            instances.append(
                Instance(
                    id=forearm_id,
                    part_id="forearm",
                    name=f"Forearm {side}",
                    transform={
                        "translation": (shoulder_x, 0.0, shoulder_z - thigh_length * 1.1),
                        "rotation": (0.0, 0.0, 0.0),
                    },
                )
            )
            mates.append(
                Mate(
                    id=f"m_elbow_forearm_{side}",
                    type="revolute",
                    entities=[MateEntity(instance_id=elbow_id), MateEntity(instance_id=forearm_id)],
                )
            )
            if any(dp.id == "hand" for dp in result.parts):
                hand_id = f"i_hand_{side}"
                instances.append(
                    Instance(
                        id=hand_id,
                        part_id="hand",
                        name=f"Hand {side}",
                        transform={
                            "translation": (shoulder_x, 0.0, shoulder_z - thigh_length * 1.4),
                            "rotation": (0.0, 90.0, 0.0),
                        },
                    )
                )
                mates.append(
                    Mate(
                        id=f"m_forearm_hand_{side}",
                        type="revolute",
                        entities=[MateEntity(instance_id=forearm_id), MateEntity(instance_id=hand_id)],
                    )
                )

    return instances, mates


def _find_number_near(text: str, unit: str, keyword: str) -> float | None:
    """Find a number near a keyword followed by a unit, e.g. '1000 mm tall'."""
    import re
    pattern = re.compile(r"(\d+(?:\.\d+)?)\s*" + re.escape(unit) + r"\s+" + re.escape(keyword))
    match = pattern.search(text)
    if match:
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            pass
    # Try keyword before number.
    pattern2 = re.compile(re.escape(keyword) + r"\s+(\d+(?:\.\d+)?)\s*" + re.escape(unit))
    match2 = pattern2.search(text)
    if match2:
        try:
            return float(match2.group(1))
        except (TypeError, ValueError):
            pass
    return None
