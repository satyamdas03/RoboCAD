"""Deterministic mate-inference engine for RoboCAD Phase 19.

This module inspects ``PartFamily.interfaces`` for every pair of instances in
an assembly and emits compatible ``Mate`` and ``KinematicJoint`` objects. The
engine is rule-first: an optional LLM fallback is only used when no mates can be
inferred deterministically.
"""
from __future__ import annotations

import itertools
import logging

from ai_cad.feature_tree import (
    Assembly,
    FeatureTree,
    Instance,
    KinematicJoint,
    Mate,
    MateEntity,
)
from ai_cad.part_families import PART_FAMILY_REGISTRY, Interface, get_family

logger = logging.getLogger(__name__)


# Interface-type compatibility table used by the rule layer.
_COMPATIBLE: dict[str, set[str]] = {
    "pin": {"pin", "bore"},
    "bore": {"pin", "bore"},
    "slot": {"slot"},
    "flange": {"flange", "face", "mount"},
    "face": {"face", "mount", "flange"},
    "mount": {"face", "mount", "flange"},
}


def _hint_priority(hint: str | None) -> int:
    """Motion-carrying mate hints rank higher than static ones."""
    if hint is None:
        return 0
    return {
        "prismatic": 4,
        "revolute": 3,
        "concentric": 2,
        "coincident": 1,
    }.get(hint, 0)


# Keywords that identify a parent instance when ordering a mate.
_PARENT_KEYWORDS = ("base", "chassis", "hub", "arm_base")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_parent_candidate(part_id: str) -> bool:
    lowered = part_id.lower()
    return any(kw in lowered for kw in _PARENT_KEYWORDS)


def _guess_family(part_id: str) -> str | None:
    """Map a part id to a registered family name via substring heuristic.

    The order of checks matters: base-like keywords are preferred so that ids
    such as ``arm_base`` resolve to ``mount`` rather than ``link``.
    """
    lowered = part_id.lower()

    # Direct family name match.
    if lowered in PART_FAMILY_REGISTRY:
        return lowered

    # Ordered keyword -> family mapping. Earlier entries win.
    keyword_families = [
        ("mount", ["mount", "base", "flange", "pedestal"]),
        ("hub", ["hub", "pulley", "wheel_center"]),
        ("bracket", ["bracket", "plate", "torso_plate", "fuselage"]),
        ("end_effector", ["gripper", "hand", "jaw", "end_effector"]),
        ("limb_segment", ["limb", "leg", "thigh", "shin"]),
        ("link", ["link", "arm", "tube", "bar", "strut", "tie"]),
        ("duct", ["duct", "shroud", "shell", "nozzle", "intake"]),
        ("wing", ["wing", "panel"]),
        ("airfoil", ["airfoil", "foil", "section"]),
        ("heat_sink", ["heat_sink", "heatsink", "fin", "cooler"]),
        ("pcb_bracket", ["pcb", "board_mount"]),
        ("enclosure", ["enclosure", "box", "case", "housing"]),
    ]

    for family, keywords in keyword_families:
        if any(kw in lowered for kw in keywords):
            return family

    return None


def _interfaces_for_part(part_id: str) -> list[Interface]:
    family = _guess_family(part_id)
    if family is None:
        return []
    return get_family(family).interfaces


def _pick_parent(inst_a: Instance, inst_b: Instance) -> tuple[Instance, Instance]:
    """Return ``(parent, child)`` ordered pair for a mate."""
    a_parent = _is_parent_candidate(inst_a.part_id)
    b_parent = _is_parent_candidate(inst_b.part_id)
    if a_parent and not b_parent:
        return inst_a, inst_b
    if b_parent and not a_parent:
        return inst_b, inst_a
    # Default: first instance is parent.
    return inst_a, inst_b


def _transform_origin(
    inst: Instance,
    local_origin: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Apply instance translation to a local interface origin.

    Rotation is intentionally not applied in Phase 19; all built-in family
    interface Z axes are aligned with the global Z axis.
    """
    tx = inst.transform or {}
    translation = tx.get("translation") or (0.0, 0.0, 0.0)
    return (
        local_origin[0] + float(translation[0]),
        local_origin[1] + float(translation[1]),
        local_origin[2] + float(translation[2]),
    )


def _midpoint(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)


def _compatible_pair(iface_a: Interface, iface_b: Interface) -> bool:
    return iface_b.type in _COMPATIBLE.get(iface_a.type, set())


def _hint_priority(hint: str | None) -> int:
    """Numerical priority used to select among multiple compatible interface pairs."""
    return {
        "prismatic": 3,
        "revolute": 2,
        "concentric": 1,
        "coincident": 1,
        "fixed": 0,
    }.get(hint or "fixed", 0)


def _resolve_mate_hint(iface_a: Interface, iface_b: Interface) -> str:
    """Choose the dominant mate hint for a compatible pair.

    Motion-carrying hints (prismatic, revolute) win over static ones.
    Defaults to ``fixed`` if neither interface specifies a hint.
    """
    hints = {iface_a.mate_hint, iface_b.mate_hint}
    hints.discard(None)
    if "prismatic" in hints:
        return "prismatic"
    if "revolute" in hints:
        return "revolute"
    if "concentric" in hints:
        return "concentric"
    if "coincident" in hints:
        return "coincident"
    return "fixed"


def _llm_propose_mates(
    prompt: str | None,
    parts: list[tuple[str, str]],
) -> list[tuple[str, str, str]]:
    """Thin LLM fallback; returns an empty list and logs a warning.

    The real Anthropic integration will be wired in a later step.
    """
    logger.warning(
        "LLM mate proposal is not wired in Phase 19 baseline; returning empty list."
    )
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def infer_mates(
    tree: FeatureTree,
    assembly: Assembly,
    *,
    use_llm: bool = False,
    prompt: str | None = None,
) -> tuple[list[Mate], list[KinematicJoint]]:
    """Infer mates and kinematic joints for an assembly.

    Args:
        tree: The feature tree containing the referenced parts.
        assembly: The assembly whose instances should be mated.
        use_llm: If True, call the LLM fallback when no deterministic mates are found.
        prompt: Optional user prompt for the LLM fallback.

    Returns:
        A tuple of inferred ``(mates, joints)``.
    """
    mates: list[Mate] = []
    joints: list[KinematicJoint] = []
    seen_pairs: set[frozenset[str]] = set()
    parent_exists = any(_is_parent_candidate(inst.part_id) for inst in assembly.instances)

    for inst_a, inst_b in itertools.combinations(assembly.instances, 2):
        pair = frozenset({inst_a.id, inst_b.id})
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        family_a = _guess_family(inst_a.part_id)
        family_b = _guess_family(inst_b.part_id)
        # In hub/base layouts, suppress direct sibling-to-sibling mating so that
        # appendages attach only to the central parent (e.g. hub + 4 arms = 4 mates).
        if parent_exists and family_a is not None and family_a == family_b:
            continue

        ifaces_a = _interfaces_for_part(inst_a.part_id)
        ifaces_b = _interfaces_for_part(inst_b.part_id)

        candidates: list[tuple[Interface, Interface, str]] = []
        for iface_a in ifaces_a:
            for iface_b in ifaces_b:
                if _compatible_pair(iface_a, iface_b):
                    hint = _resolve_mate_hint(iface_a, iface_b)
                    candidates.append((iface_a, iface_b, hint))
        matched: tuple[Interface, Interface, str] | None = None
        if candidates:
            candidates.sort(key=lambda c: _hint_priority(c[2]), reverse=True)
            matched = candidates[0]

        if not matched:
            if not ifaces_a or not ifaces_b:
                # Unknown parts: emit a fixed mate as fallback.
                parent, child = _pick_parent(inst_a, inst_b)
                mates.append(
                    Mate(
                        id=f"m_{parent.id}_{child.id}",
                        type="fixed",
                        entities=[
                            MateEntity(instance_id=parent.id),
                            MateEntity(instance_id=child.id),
                        ],
                    )
                )
            continue

        iface_a, iface_b, hint = matched
        parent, child = _pick_parent(inst_a, inst_b)

        # Order entities parent first, child second.
        mate_entities: list[MateEntity] = []
        for inst, iface in (
            (parent, iface_a if parent.id == inst_a.id else iface_b),
            (child, iface_b if child.id == inst_b.id else iface_a),
        ):
            mate_entities.append(
                MateEntity(instance_id=inst.id, csys_id=iface.csys.id)
            )

        mates.append(
            Mate(
                id=f"m_{parent.id}_{child.id}",
                type=hint,
                entities=mate_entities,
            )
        )

        if hint in ("revolute", "prismatic"):
            origin_a = _transform_origin(inst_a, iface_a.csys.origin)
            origin_b = _transform_origin(inst_b, iface_b.csys.origin)
            origin = _midpoint(origin_a, origin_b)

            axis = (0.0, 0.0, 1.0)
            limits = (-180.0, 180.0) if hint == "revolute" else (-50.0, 50.0)

            joints.append(
                KinematicJoint(
                    id=f"j_{parent.id}_{child.id}",
                    type=hint,
                    parent_link=parent.id,
                    child_link=child.id,
                    origin=origin,
                    axis=axis,
                    limits=limits,
                )
            )

    if use_llm and not mates and prompt:
        _llm_propose_mates(
            prompt, [(inst.id, inst.part_id) for inst in assembly.instances]
        )

    return mates, joints
