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
    """If the result matches a robot arm layout, return instances + mates."""
    text = result.prompt.lower()
    if not any(w in text for w in {"robot arm", "manipulator", "robotic arm"}):
        return None

    instances: list[Instance] = []
    mates: list[Mate] = []
    link_length = 120.0
    for dp in result.parts:
        if dp.id in {"upper_link", "forearm_link"} and dp.parameters:
            for p in dp.parameters:
                if p.name == "link_length":
                    try:
                        link_length = float(p.value)
                    except (TypeError, ValueError):
                        pass

    # Base at origin.
    instances.append(Instance(id="i_arm_base", part_id="arm_base", name="Arm base"))

    # Upper link stands up from base.
    instances.append(
        Instance(
            id="i_upper_link",
            part_id="upper_link",
            name="Upper arm link",
            transform={
                "translation": (0.0, 0.0, 10.0),
                "rotation": (0.0, 0.0, 0.0),
            },
        )
    )
    mates.append(
        Mate(
            id="m_base_upper",
            type="fixed",
            entities=[
                MateEntity(instance_id="i_upper_link"),
                MateEntity(instance_id="i_arm_base"),
            ],
        )
    )

    # Forearm extends forward from upper link end.
    instances.append(
        Instance(
            id="i_forearm_link",
            part_id="forearm_link",
            name="Forearm link",
            transform={
                "translation": (link_length / 2, 0.0, link_length / 2 + 10.0),
                "rotation": (0.0, 90.0, 0.0),
            },
        )
    )
    mates.append(
        Mate(
            id="m_upper_forearm",
            type="fixed",
            entities=[
                MateEntity(instance_id="i_forearm_link"),
                MateEntity(instance_id="i_upper_link"),
            ],
        )
    )

    # Gripper jaws at forearm end — parallel-jaw prismatic mechanism.
    if any(dp.id == "gripper" for dp in result.parts):
        jaw_spacing = 10.0
        jaw_travel = 15.0
        for dp in result.parts:
            if dp.id == "gripper" and dp.parameters:
                for p in dp.parameters:
                    if p.name == "gripper_gap":
                        try:
                            jaw_spacing = float(p.value)
                        except (TypeError, ValueError):
                            pass
                    elif p.name == "jaw_travel":
                        try:
                            jaw_travel = float(p.value)
                        except (TypeError, ValueError):
                            pass

        for side, sign in enumerate((-1.0, 1.0)):
            offset = sign * jaw_spacing / 2
            instances.append(
                Instance(
                    id=f"i_gripper_{side}",
                    part_id="gripper",
                    name=f"Gripper jaw {side + 1}",
                    transform={
                        "translation": (link_length + 20.0, offset, link_length / 2 + 10.0),
                        "rotation": (0.0, 90.0, 0.0),
                    },
                )
            )
            # Each jaw slides relative to the forearm along the local Y axis.
            mates.append(
                Mate(
                    id=f"m_gripper_{side}_forearm",
                    type="prismatic",
                    entities=[
                        MateEntity(instance_id=f"i_gripper_{side}"),
                        MateEntity(instance_id="i_forearm_link"),
                    ],
                    parameters={"distance": sign * jaw_travel},
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
                respect_existing_mates=False,
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
