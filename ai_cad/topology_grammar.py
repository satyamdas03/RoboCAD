"""Deterministic topology grammar for Milestone E.

A robot topology is described by a base type, base dimensions, mass/payload
budget, and a list of limbs with joint sequences and end-effector families. The
grammar supports deterministic enumeration, physical-feasibility pruning, and
stable hashing so it can be used as a cache key and as a seedable search space.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

JointType = Literal["revolute", "prismatic", "spherical", "fixed"]
LimbRole = Literal["leg", "arm", "tail", "head", "wheel"]
BaseType = Literal["biped", "quadruped", "hexapod", "wheeled", "tracked", "fixed"]

_WALKER_BASE_TYPES: set[BaseType] = {"biped", "quadruped", "hexapod"}


@dataclass(frozen=True)
class JointSpec:
    """One joint along a limb."""

    type: JointType
    axis: tuple[float, float, float]
    range_deg: tuple[float, float]
    name: str | None = None


@dataclass(frozen=True)
class LimbSpec:
    """One limb attached to the base."""

    role: LimbRole
    side: str
    index: int
    attachment: tuple[float, float, float]
    joints: list[JointSpec]
    end_effector_family: str
    length_schedule: list[float] | None = None


@dataclass(frozen=True)
class Topology:
    """A concrete robot topology."""

    base_type: BaseType
    base_dimensions: tuple[float, float, float]
    mass_budget_kg: float
    payload_kg: float
    limbs: list[LimbSpec]
    tags: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash(self.topology_hash())

    def topology_hash(self) -> str:
        """Stable string hash suitable for caching."""
        limb_hashes = []
        for limb in self.limbs:
            jh = "|".join(
                f"{j.type}:{j.axis}:{j.range_deg}" for j in limb.joints
            )
            limb_hashes.append(
                f"{limb.role}:{limb.side}:{limb.index}:{limb.attachment}:{jh}:{limb.end_effector_family}"
            )
        return (
            f"{self.base_type}:"
            f"{self.base_dimensions}:"
            f"{self.mass_budget_kg}:"
            f"{self.payload_kg}:"
            f"{';'.join(limb_hashes)}:"
            f"{','.join(sorted(self.tags))}"
        )


def _base_dims(base_type: BaseType, mass_budget_kg: float) -> tuple[float, float, float]:
    """Return conservative default base dimensions in mm."""
    scale = max(1.0, mass_budget_kg / 10.0) ** (1 / 3)
    dims: dict[BaseType, tuple[float, float, float]] = {
        "biped": (180.0, 120.0, 80.0),
        "quadruped": (220.0, 140.0, 70.0),
        "hexapod": (260.0, 160.0, 60.0),
        "wheeled": (240.0, 160.0, 80.0),
        "tracked": (260.0, 180.0, 90.0),
        "fixed": (160.0, 160.0, 40.0),
    }
    l, w, h = dims[base_type]
    return (l * scale, w * scale, h * scale)


def _default_leg_joints() -> list[JointSpec]:
    """Standard 2-DOF leg: hip pitch + knee pitch."""
    return [
        JointSpec(type="revolute", axis=(0.0, 1.0, 0.0), range_deg=(-45.0, 45.0), name="hip_pitch"),
        JointSpec(type="revolute", axis=(0.0, 1.0, 0.0), range_deg=(-90.0, 90.0), name="knee_pitch"),
    ]


def _default_arm_joints() -> list[JointSpec]:
    """Standard 2-DOF arm: shoulder pitch + elbow pitch."""
    return [
        JointSpec(type="revolute", axis=(0.0, 1.0, 0.0), range_deg=(-90.0, 90.0), name="shoulder_pitch"),
        JointSpec(type="revolute", axis=(0.0, 1.0, 0.0), range_deg=(-120.0, 120.0), name="elbow_pitch"),
    ]


def _leg_attachments(base_type: BaseType, length: float, width: float) -> list[tuple[float, float, float]]:
    """Return limb attachment points on the base in mm."""
    half_l = length / 2.0
    half_w = width / 2.0
    if base_type == "biped":
        return [
            (-half_l * 0.3, half_w, 0.0),
            (-half_l * 0.3, -half_w, 0.0),
        ]
    if base_type == "quadruped":
        return [
            (half_l * 0.4, half_w, 0.0),   # front left
            (half_l * 0.4, -half_w, 0.0),  # front right
            (-half_l * 0.4, half_w, 0.0),   # rear left
            (-half_l * 0.4, -half_w, 0.0),  # rear right
        ]
    if base_type == "hexapod":
        points = []
        for i in range(3):
            x = half_l * (0.5 - i * 0.5)
            points.append((x, half_w, 0.0))
            points.append((x, -half_w, 0.0))
        return points
    return []


def _side_name(index: int, total: int) -> str:
    """Generate a stable side label."""
    if total == 2:
        return "left" if index == 0 else "right"
    side = "left" if index % 2 == 0 else "right"
    row = ("front", "middle", "rear")[min(index // 2, 2)]
    return f"{row}_{side}"


def _default_walker_topology(
    base_type: BaseType,
    payload_kg: float,
    mass_budget_kg: float,
) -> Topology:
    """Build the canonical legged topology for a base type."""
    length, width, height = _base_dims(base_type, mass_budget_kg)
    attachments = _leg_attachments(base_type, length, width)
    ee_family = "point_foot" if base_type in ("quadruped", "hexapod") else "compliant_foot"
    limbs = [
        LimbSpec(
            role="leg",
            side=_side_name(i, len(attachments)),
            index=i,
            attachment=attachment,
            joints=_default_leg_joints(),
            end_effector_family=ee_family,
        )
        for i, attachment in enumerate(attachments)
    ]
    return Topology(
        base_type=base_type,
        base_dimensions=(length, width, height),
        mass_budget_kg=mass_budget_kg,
        payload_kg=payload_kg,
        limbs=limbs,
        tags=["walker"],
    )


def _default_wheeled_topology(
    payload_kg: float,
    mass_budget_kg: float,
    wheel_count: int = 4,
) -> Topology:
    """Build a wheeled mobile base with optional caster / drive wheels."""
    length, width, height = _base_dims("wheeled", mass_budget_kg)
    if wheel_count == 2:
        attachments = [
            (length * 0.25, 0.0, 0.0),
            (-length * 0.25, 0.0, 0.0),
        ]
    else:
        half_l = length / 2.0
        half_w = width / 2.0
        attachments = [
            (half_l * 0.5, half_w, 0.0),
            (half_l * 0.5, -half_w, 0.0),
            (-half_l * 0.5, half_w, 0.0),
            (-half_l * 0.5, -half_w, 0.0),
        ]
    limbs = [
        LimbSpec(
            role="wheel",
            side=f"wheel_{i}",
            index=i,
            attachment=attachment,
            joints=[JointSpec(type="fixed", axis=(0.0, 1.0, 0.0), range_deg=(0.0, 0.0))],
            end_effector_family="point_foot",  # contact approximation for first pass
        )
        for i, attachment in enumerate(attachments[:wheel_count])
    ]
    return Topology(
        base_type="wheeled",
        base_dimensions=(length, width, height),
        mass_budget_kg=mass_budget_kg,
        payload_kg=payload_kg,
        limbs=limbs,
        tags=["mobile_base"],
    )


def _default_fixed_topology(
    payload_kg: float,
    mass_budget_kg: float,
    arm_count: int = 1,
) -> Topology:
    """Build a fixed-base manipulator."""
    length, width, height = _base_dims("fixed", mass_budget_kg)
    if arm_count == 1:
        attachments = [(0.0, 0.0, height / 2.0)]
    else:
        attachments = [
            (length * 0.2, width * 0.2, height / 2.0),
            (-length * 0.2, -width * 0.2, height / 2.0),
        ]
    limbs = [
        LimbSpec(
            role="arm",
            side=f"arm_{i}",
            index=i,
            attachment=attachment,
            joints=_default_arm_joints(),
            end_effector_family="parallel_jaw_gripper",
        )
        for i, attachment in enumerate(attachments[:arm_count])
    ]
    return Topology(
        base_type="fixed",
        base_dimensions=(length, width, height),
        mass_budget_kg=mass_budget_kg,
        payload_kg=payload_kg,
        limbs=limbs,
        tags=["manipulator"],
    )


def default_topology(
    base_type: BaseType,
    payload_kg: float,
    mass_budget_kg: float,
) -> Topology:
    """Return the canonical topology for a base type."""
    if base_type == "biped":
        return _default_walker_topology("biped", payload_kg, mass_budget_kg)
    if base_type == "quadruped":
        return _default_walker_topology("quadruped", payload_kg, mass_budget_kg)
    if base_type == "hexapod":
        return _default_walker_topology("hexapod", payload_kg, mass_budget_kg)
    if base_type == "wheeled":
        return _default_wheeled_topology(payload_kg, mass_budget_kg)
    if base_type == "tracked":
        # Tracked approximated as 2 fixed-contact tracks for the first pass.
        length, width, height = _base_dims("tracked", mass_budget_kg)
        return Topology(
            base_type="tracked",
            base_dimensions=(length, width, height),
            mass_budget_kg=mass_budget_kg,
            payload_kg=payload_kg,
            limbs=[
                LimbSpec(
                    role="wheel",
                    side="track_left",
                    index=0,
                    attachment=(0.0, width / 2.0, 0.0),
                    joints=[JointSpec(type="fixed", axis=(1.0, 0.0, 0.0), range_deg=(0.0, 0.0))],
                    end_effector_family="point_foot",
                ),
                LimbSpec(
                    role="wheel",
                    side="track_right",
                    index=1,
                    attachment=(0.0, -width / 2.0, 0.0),
                    joints=[JointSpec(type="fixed", axis=(1.0, 0.0, 0.0), range_deg=(0.0, 0.0))],
                    end_effector_family="point_foot",
                ),
            ],
            tags=["mobile_base"],
        )
    if base_type == "fixed":
        return _default_fixed_topology(payload_kg, mass_budget_kg)
    raise ValueError(f"Unknown base_type: {base_type}")


def all_base_types() -> list[BaseType]:
    """Return all supported base types."""
    return ["biped", "quadruped", "hexapod", "wheeled", "tracked", "fixed"]


def is_feasible(topology: Topology) -> bool:
    """Apply lightweight physical-feasibility pruning."""
    # Walkers need enough support contacts.
    if topology.base_type in _WALKER_BASE_TYPES:
        support = sum(1 for limb in topology.limbs if limb.role == "leg")
        if topology.base_type == "biped" and support < 2:
            return False
        if topology.base_type == "quadruped" and support < 3:
            return False
        if topology.base_type == "hexapod" and support < 4:
            return False

    # Mobile bases need at least two wheels / tracks.
    if topology.base_type in {"wheeled", "tracked"}:
        wheels = sum(1 for limb in topology.limbs if limb.role == "wheel")
        if wheels < 2:
            return False

    # Fixed bases need at least one arm.
    if topology.base_type == "fixed":
        arms = sum(1 for limb in topology.limbs if limb.role == "arm")
        if arms < 1:
            return False

    # Reject unsupported combos.
    if topology.base_type == "tracked" and any(limb.role == "leg" for limb in topology.limbs):
        return False

    # Reject limb-base overlap by simple bounding-box sanity.
    length, width, _ = topology.base_dimensions
    half_l = length / 2.0
    half_w = width / 2.0
    for limb in topology.limbs:
        ax, ay, _ = limb.attachment
        if abs(ax) > half_l * 1.2 or abs(ay) > half_w * 1.2:
            return False

    # Mass sanity: rough limb mass estimate must fit budget.
    estimated_limb_mass = 0.05 * len(topology.limbs) * topology.mass_budget_kg
    if estimated_limb_mass + topology.payload_kg > topology.mass_budget_kg:
        return False

    return True


def enumerate_topologies(
    constraints: dict[str, Any],
    max_count: int = 12,
    seed: int = 0,
) -> list[Topology]:
    """Enumerate feasible topologies matching the constraints.

    Constraints may include:
      - base_type: a literal BaseType, or "walker" to include biped/quadruped/hexapod
      - min_limbs / max_limbs: integer bounds on total limb count
      - roles: list of required limb roles (e.g., ["leg", "arm"])
      - appendages: list of extra appendages to add ("tail", "head", "arm")
      - payload_kg / mass_budget_kg: numeric design budgets
    """
    rng = np.random.default_rng(seed)
    payload_kg = float(constraints.get("payload_kg", 1.0))
    mass_budget_kg = float(constraints.get("mass_budget_kg", 10.0))

    requested = constraints.get("base_type", "walker")
    if requested == "walker":
        base_types: list[BaseType] = ["biped", "quadruped", "hexapod"]
    else:
        if requested in all_base_types():
            base_types = [requested]
        else:
            base_types = []

    candidates: list[Topology] = []
    for base_type in base_types:
        topo = default_topology(base_type, payload_kg, mass_budget_kg)
        candidates.append(topo)

        # Add optional appendages.
        appendages = constraints.get("appendages", [])
        if "tail" in appendages:
            tail_limb = LimbSpec(
                role="tail",
                side="tail",
                index=len(topo.limbs),
                attachment=(-topo.base_dimensions[0] / 2.0, 0.0, 0.0),
                joints=[
                    JointSpec(type="revolute", axis=(0.0, 1.0, 0.0), range_deg=(-30.0, 30.0), name="tail_joint_1"),
                    JointSpec(type="revolute", axis=(0.0, 0.0, 1.0), range_deg=(-30.0, 30.0), name="tail_joint_2"),
                ],
                end_effector_family="point_foot",
            )
            new_limbs = list(topo.limbs) + [tail_limb]
            candidates.append(
                Topology(
                    base_type=topo.base_type,
                    base_dimensions=topo.base_dimensions,
                    mass_budget_kg=topo.mass_budget_kg,
                    payload_kg=topo.payload_kg,
                    limbs=new_limbs,
                    tags=list(topo.tags) + ["tail"],
                )
            )
        if "arm" in appendages and base_type in _WALKER_BASE_TYPES:
            # Add a single arm on top of the base.
            arm_limb = LimbSpec(
                role="arm",
                side="center_arm",
                index=len(topo.limbs),
                attachment=(0.0, 0.0, topo.base_dimensions[2] / 2.0),
                joints=_default_arm_joints(),
                end_effector_family="parallel_jaw_gripper",
            )
            new_limbs = list(topo.limbs) + [arm_limb]
            candidates.append(
                Topology(
                    base_type=topo.base_type,
                    base_dimensions=topo.base_dimensions,
                    mass_budget_kg=topo.mass_budget_kg,
                    payload_kg=topo.payload_kg,
                    limbs=new_limbs,
                    tags=list(topo.tags) + ["arm"],
                )
            )

    # Also consider wheeled / tracked if the user asks for a mobile base.
    if requested in {"mobile", "mobile_base", "wheeled"}:
        for wc in (2, 4):
            candidates.append(_default_wheeled_topology(payload_kg, mass_budget_kg, wheel_count=wc))

    # Filter by limb-count constraints.
    min_limbs = constraints.get("min_limbs")
    max_limbs = constraints.get("max_limbs")
    if min_limbs is not None:
        candidates = [t for t in candidates if len(t.limbs) >= int(min_limbs)]
    if max_limbs is not None:
        candidates = [t for t in candidates if len(t.limbs) <= int(max_limbs)]

    # Filter by required roles.
    required_roles = set(constraints.get("roles", []))
    if required_roles:
        candidates = [
            t for t in candidates if required_roles.issubset({limb.role for limb in t.limbs})
        ]

    # Prune infeasible topologies.
    candidates = [t for t in candidates if is_feasible(t)]

    # Deterministic shuffle + cap.
    rng.shuffle(candidates)
    return candidates[:max_count]
