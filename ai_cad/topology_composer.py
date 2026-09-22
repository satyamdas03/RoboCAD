"""Map an abstract Milestone E Topology to a concrete FeatureTree assembly.

The composer reuses existing part families (`torso_plate`, `limb_segment`,
`hip_hub`, `end_effector` families) and builds a FeatureTree with instances,
mates, and kinematic joints that mirror the structure produced by the legacy
robot templates. This lets the existing transpiler/executor and morphology
scoring pipeline operate on arbitrary grammar-generated topologies.
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
from ai_cad.part_families import instantiate_family
from ai_cad.topology_grammar import JointSpec, LimbSpec, Topology


def _placement(x: float, y: float, z: float) -> dict[str, Any]:
    """Return an instance transform dict used by the assembly solver."""
    return {"translation": (x, y, z), "rotation": (0.0, 0.0, 0.0)}


def _param(name: str, value: float | int, unit: str = "mm", description: str = "") -> Parameter:
    return Parameter(name=name, value=value, unit=unit, description=description)


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


def _base_family(base_type: str) -> str:
    """Return the part family used for the base."""
    return "torso_plate"


def _base_params(base_type: str, dims: tuple[float, float, float]) -> list[Parameter]:
    """Return default base parameters derived from topology dimensions."""
    length, width, height = dims
    params: list[Parameter] = [
        _param("torso_width", width, "mm", "Base width"),
        _param("torso_depth", length, "mm", "Base depth"),
        _param("torso_thickness", height, "mm", "Base thickness"),
    ]
    if base_type in {"biped", "quadruped", "hexapod"}:
        params.extend(
            [
                _param("hip_bore", 10.0, "mm", "Hip joint bore"),
            ]
        )
    return params


def _limb_segment_length(limb: LimbSpec, base_dims: tuple[float, float, float]) -> float:
    """Derive a default segment length for a limb from topology heuristics."""
    length, width, height = base_dims
    if limb.role == "leg":
        # Leg length scales with base height so the robot can stand.
        return max(80.0, height * 2.5)
    if limb.role == "arm":
        return max(80.0, width * 0.8)
    if limb.role == "tail":
        return max(40.0, length * 0.35)
    if limb.role == "wheel":
        return max(30.0, height * 0.6)
    return 100.0


def _limb_params(limb: LimbSpec, base_dims: tuple[float, float, float]) -> list[Parameter]:
    """Return per-limb default parameters."""
    seg_length = _limb_segment_length(limb, base_dims)
    width = max(15.0, seg_length * 0.15)
    thickness = max(6.0, seg_length * 0.08)
    return [
        _param(f"{limb.role}_segment_length_{limb.index}", seg_length, "mm", f"{limb.role} segment length"),
        _param(f"{limb.role}_segment_width_{limb.index}", width, "mm", f"{limb.role} segment width"),
        _param(f"{limb.role}_segment_thickness_{limb.index}", thickness, "mm", f"{limb.role} segment thickness"),
        _param(f"{limb.role}_joint_bore_{limb.index}", 8.0, "mm", f"{limb.role} joint bore"),
        _param(f"{limb.role}_end_offset_{limb.index}", 15.0, "mm", f"{limb.role} end offset"),
    ]


def _joints_for_limb(
    limb: LimbSpec,
    parent_instance_id: str,
    segment_instance_ids: list[str],
    tip_instance_id: str,
    joint_origin: tuple[float, float, float],
) -> list[KinematicJoint]:
    """Build kinematic joints connecting a limb chain."""
    joints: list[KinematicJoint] = []
    x, y, z = joint_origin
    prev = parent_instance_id
    for i, segment_id in enumerate(segment_instance_ids):
        js = limb.joints[i] if i < len(limb.joints) else JointSpec(
            type="revolute", axis=(0.0, 1.0, 0.0), range_deg=(-90.0, 90.0)
        )
        axis = js.axis or (0.0, 1.0, 0.0)
        limits = js.range_deg if js.range_deg != (0.0, 0.0) else None
        joints.append(
            _joint(
                f"{limb.role}_joint_{limb.index}_{i}",
                js.type,
                prev,
                segment_id,
                (x, y, z),
                axis=axis,
                limits=limits,
            )
        )
        prev = segment_id
        # Approximate next joint origin slightly lower along Z.
        z -= 50.0
    # Fixed attachment from last segment to end-effector.
    joints.append(
        _joint(
            f"{limb.role}_tip_fixed_{limb.index}",
            "fixed",
            segment_instance_ids[-1],
            tip_instance_id,
            (x, y, z),
        )
    )
    return joints


def topology_to_feature_tree(topology: Topology, seed: int = 0) -> FeatureTree:
    """Convert a Topology into a concrete FeatureTree assembly."""
    length, width, height = topology.base_dimensions
    base_family = _base_family(topology.base_type)

    # Global parameters.
    parameters: list[Parameter] = [
        _param("robot_mass_kg", topology.mass_budget_kg, "kg", "Estimated total robot mass"),
        _param("payload_kg", topology.payload_kg, "kg", "Design payload mass"),
        _param("base_length", length, "mm", "Base length"),
        _param("base_width", width, "mm", "Base width"),
        _param("base_height", height, "mm", "Base height"),
    ]
    parameters.extend(_base_params(topology.base_type, topology.base_dimensions))

    # Base part.
    base_part_id = "base"
    base_part = instantiate_family(base_family, part_id=base_part_id, name_override="base")
    parts: list[Part] = [base_part]

    instances: list[Instance] = [
        Instance(id="base", part_id=base_part_id, name="base", transform=_placement(0.0, 0.0, height / 2.0))
    ]
    joints: list[KinematicJoint] = []
    mates: list[Mate] = []

    for limb in topology.limbs:
        limb_params = _limb_params(limb, topology.base_dimensions)
        parameters.extend(limb_params)

        # Each limb has a small hub at the base attachment (simplifies mates).
        hub_id = f"hub_{limb.role}_{limb.index}"
        hub_part = instantiate_family("hip_hub", part_id=hub_id, name_override=hub_id)
        parts.append(hub_part)
        ax, ay, az = limb.attachment
        instances.append(
            Instance(id=hub_id, part_id=hub_id, name=hub_id, transform=_placement(ax, ay, height / 2.0))
        )

        # Hub fixed to base.
        joints.append(
            _joint(
                f"base_to_{hub_id}",
                "fixed",
                "base",
                hub_id,
                (ax, ay, height / 2.0),
            )
        )

        # Limb segments: 1 segment per joint.
        segment_ids: list[str] = []
        segment_length = _limb_segment_length(limb, topology.base_dimensions)
        for seg_i in range(max(1, len(limb.joints))):
            seg_id = f"{limb.role}_segment_{limb.index}_{seg_i}"
            segment_ids.append(seg_id)
            segment_part = instantiate_family(
                "limb_segment",
                part_id=seg_id,
                name_override=seg_id,
                parameter_overrides=[
                    Parameter(name="segment_length", value=segment_length, unit="mm"),
                    Parameter(name="segment_width", value=20.0, unit="mm"),
                    Parameter(name="segment_thickness", value=8.0, unit="mm"),
                ],
            )
            parts.append(segment_part)
            seg_z = height / 2.0 - segment_length / 2.0 - seg_i * segment_length
            instances.append(
                Instance(id=seg_id, part_id=seg_id, name=seg_id, transform=_placement(ax, ay, seg_z))
            )

        # End-effector / tip part.
        tip_id = f"{limb.role}_tip_{limb.index}"
        tip_family = limb.end_effector_family
        if tip_family == "point_foot" and limb.role == "wheel":
            # Wheels use a small cylindrical contact approximation in first pass.
            tip_family = "point_foot"
        tip_part = instantiate_family(tip_family, part_id=tip_id, name_override=tip_id)
        parts.append(tip_part)
        tip_z = height / 2.0 - len(segment_ids) * segment_length
        instances.append(
            Instance(id=tip_id, part_id=tip_id, name=tip_id, transform=_placement(ax, ay, tip_z))
        )

        # Joints.
        joints.extend(
            _joints_for_limb(
                limb,
                parent_instance_id=hub_id,
                segment_instance_ids=segment_ids,
                tip_instance_id=tip_id,
                joint_origin=(ax, ay, height / 2.0),
            )
        )

    # Build tree.
    design_id = f"topology_{topology.base_type}_{len(topology.limbs)}limbs_{seed}"
    tree = FeatureTree(
        design_id=design_id,
        domain="mechanical",
        prompt=f"{topology.base_type} robot with {len(topology.limbs)} limbs generated from topology grammar",
        parameters=parameters,
        parts=parts,
        assemblies=[
            Assembly(
                id="main",
                name=f"{topology.base_type}_topology",
                instances=instances,
                joints=joints,
                mates=mates,
            )
        ],
    )
    return tree
