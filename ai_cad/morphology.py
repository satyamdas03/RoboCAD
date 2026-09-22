"""Morphology co-design lab for RoboCAD Phase 28D.

Provides a deterministic, bounded search over robot morphology parameters
(link lengths, limb counts, joint ranges, end-effector choices) and scores
each candidate with lightweight stability, workspace, gait, and actuator
feasibility checks. The search is seedable so results are reproducible and
testable without relying on an LLM.
"""
from __future__ import annotations

import copy
import json
import math
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ai_cad.actuator_sizing import actuator_summary, size_actuators_for_tree
from ai_cad.feature_tree import FeatureTree, Parameter
from ai_cad.kinematic_tree import sample_reachable_workspace
from ai_cad.morphology_physics import physics_score_candidate
from ai_cad.morphology_collision import score_candidate_collision
from ai_cad.morphology_structural import run_deep_structural_for_candidate, score_candidate_structural
from ai_cad.morphology_workspace import workspace_proxy
from ai_cad.part_families import get_family, instantiate_family
from ai_cad.robot_templates import humanoid_template, manipulator_on_base_template, quadruped_template
from ai_cad.stability import check_stability, stability_summary
from ai_cad.topology_composer import topology_to_feature_tree


DEFAULT_TEMPLATE_FACTORIES: dict[str, Any] = {
    "humanoid": humanoid_template,
    "quadruped": quadruped_template,
    "manipulator_on_base": manipulator_on_base_template,
}


@dataclass
class MorphologyDimension:
    """One searchable numeric dimension with inclusive bounds and step size."""

    name: str
    min: float
    max: float
    step: float = 1.0

    def values(self, max_count: int = 8) -> list[float]:
        """Return a finite list of sampled values, capped at ``max_count``."""
        if self.min == self.max:
            return [float(self.min)]
        n_steps = int(round((self.max - self.min) / self.step)) + 1
        count = min(max(n_steps, 2), max_count)
        vals = [self.min + (self.max - self.min) * i / (count - 1) for i in range(count)]
        # Snap to step grid.
        snapped = [round(v / self.step) * self.step for v in vals]
        # De-duplicate while preserving order.
        seen: set[float] = set()
        out: list[float] = []
        for v in snapped:
            key = round(v, 6)
            if key not in seen:
                seen.add(key)
                out.append(float(v))
        return out


@dataclass
class MorphologySpace:
    """Search space for a robot template."""

    template: str
    dimensions: list[MorphologyDimension]
    limb_counts: list[int] = field(default_factory=list)
    joint_range_scale: tuple[float, float] = (0.8, 1.2)
    end_effectors: list[str] = field(default_factory=lambda: ["default"])
    n_max: int = 64
    seed: int = 0

    def parameter_grid(self, rng: np.random.Generator) -> list[dict[str, float]]:
        """Return a list of parameter dictionaries covering the space.

        The grid is built from the Cartesian product of dimension values, then
        capped deterministically at ``n_max`` by uniform subsampling.
        """
        dim_values = [d.values() for d in self.dimensions]
        if not dim_values:
            return [{}]

        import itertools

        products = list(itertools.product(*dim_values))
        # Subsample deterministically if too many.
        if len(products) > self.n_max:
            idx = np.linspace(0, len(products) - 1, self.n_max).astype(int)
            # Add a little jitter from the RNG to avoid always picking extremes.
            jitter = rng.integers(-2, 3, size=len(idx))
            idx = np.clip(idx + jitter, 0, len(products) - 1)
            idx = sorted(set(int(i) for i in idx))
            products = [products[i] for i in idx]

        out: list[dict[str, float]] = []
        for combo in products:
            params: dict[str, float] = {}
            for dim, value in zip(self.dimensions, combo):
                params[dim.name] = float(value)
            out.append(params)
        return out


@dataclass
class TopologySpace:
    """Search space over Milestone E grammar topologies."""

    topologies: list[Any]
    n_max: int = 64
    seed: int = 0


@dataclass
class MorphologyCandidate:
    """One scored morphology candidate."""

    candidate_id: str
    template: str
    parameters: dict[str, float]
    tree: FeatureTree
    scores: dict[str, float] = field(default_factory=dict)
    composite_score: float = 0.0
    rank: int = 0
    topology: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize candidate without the full tree for API responses."""
        d = {
            "candidate_id": self.candidate_id,
            "template": self.template,
            "parameters": self.parameters,
            "scores": self.scores,
            "composite_score": round(self.composite_score, 6),
            "rank": self.rank,
        }
        if self.topology is not None:
            d["topology"] = {
                "base_type": self.topology.base_type,
                "limb_count": len(self.topology.limbs),
                "tags": list(self.topology.tags),
                "hash": self.topology.topology_hash(),
            }
        return d

    def with_tree_dict(self) -> dict[str, Any]:
        """Serialize including the feature tree."""
        d = self.to_dict()
        d["feature_tree"] = self.tree.model_dump(mode="json")
        return d


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _make_tree(template: str, params: dict[str, float]) -> FeatureTree:
    """Instantiate a base template and override search parameters."""
    factory = DEFAULT_TEMPLATE_FACTORIES.get(template, humanoid_template)
    tree = factory()
    for name, value in params.items():
        if name in tree.parameter_dict():
            tree = tree.update_parameter(name, value)
    return tree


def _scale_joint_limits(tree: FeatureTree, scale: float) -> FeatureTree:
    """Return a tree with all revolute/prismatic joint limits scaled."""
    if not tree.assemblies:
        return tree
    tree = copy.deepcopy(tree)
    for assembly in tree.assemblies:
        for joint in assembly.joints or []:
            if joint.limits and joint.type in ("revolute", "prismatic"):
                lo, hi = joint.limits
                mid = (lo + hi) / 2.0
                half = (hi - lo) / 2.0 * scale
                joint.limits = (mid - half, mid + half)
    return tree


def _attach_end_effector(tree: FeatureTree, ee_type: str) -> FeatureTree:
    """Swap end-effector part families into the tree based on ``ee_type``.

    The target default family is inferred from the new family's metadata
    (``end_effector_type``).  Every existing part whose ``family`` matches that
    default is replaced by an instantiation of ``ee_type`` while keeping its
    original part id and instance references intact.
    """
    if ee_type == "default" or not ee_type:
        return tree
    family = get_family(ee_type)
    ee_type_meta = family.metadata.get("end_effector_type", "end_effector")
    target_default_family = "foot" if ee_type_meta == "foot" else "end_effector"

    tree = copy.deepcopy(tree)
    existing_param_names = {p.name for p in tree.parameters}
    new_parts: list[Any] = []
    for part in tree.parts:
        if part.family == target_default_family:
            new_part = instantiate_family(
                ee_type,
                part_id=part.id,
                name_override=part.name or None,
            )
            for param in family.default_parameters:
                if param.name not in existing_param_names:
                    tree.parameters.append(param)
                    existing_param_names.add(param.name)
            new_parts.append(new_part)
        else:
            new_parts.append(part)
    tree.parts = new_parts
    tree.prompt = f"{tree.prompt} with {ee_type} end-effector"
    return tree


def _normalize(value: float, lo: float, hi: float) -> float:
    """Normalize a value to [0, 1] with soft clamping."""
    if hi == lo:
        return 1.0 if value >= hi else 0.0
    return _clamp((value - lo) / (hi - lo), 0.0, 1.0)


END_EFFECTOR_FAMILIES: set[str] = {
    "parallel_jaw_gripper",
    "three_finger_hand",
    "vacuum_gripper",
    "point_foot",
    "compliant_foot",
}


def _resolve_numeric(value: Any, param_dict: dict[str, Any]) -> float:
    """Return a numeric value, evaluating a string expression against parameters."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return 0.0
    try:
        return float(value)
    except ValueError:
        pass
    env = {"__builtins__": {}, "pi": math.pi, "sin": math.sin, "cos": math.cos, "sqrt": math.sqrt}
    env.update(param_dict)
    try:
        return float(eval(value, env))
    except Exception:
        return 0.0


def _sketch_entity_area(entity: Any, param_dict: dict[str, Any]) -> float:
    """Approximate 2D area of a sketch entity in mm²."""
    if entity.type == "rectangle":
        width = _resolve_numeric(getattr(entity, "width", 0.0), param_dict)
        height = _resolve_numeric(getattr(entity, "height", 0.0), param_dict)
        return width * height
    if entity.type == "circle":
        radius = _resolve_numeric(getattr(entity, "radius", 0.0), param_dict)
        return math.pi * radius * radius
    return 0.0


def _estimate_part_mass_kg(part: Any) -> float:
    """Lightweight bounding-volume mass estimate for a part family instance."""
    family_name = getattr(part, "family", None)
    if not family_name:
        return 0.0
    try:
        family = get_family(family_name)
    except KeyError:
        return 0.0
    param_dict = {p.name: p.value for p in family.default_parameters}

    # Positive area comes from "add" sketches; subtractive sketches reduce it.
    positive_sketch_ids: set[str] = set()
    subtract_sketch_ids: set[str] = set()
    max_thickness_mm = 5.0
    for feature in part.features:
        if getattr(feature, "type", None) != "extrude":
            continue
        sketch_id = getattr(feature, "sketch_id", None)
        mode = feature.parameters.get("mode", "add") if hasattr(feature, "parameters") else "add"
        amount = _resolve_numeric(
            feature.parameters.get("amount", 0.0) if hasattr(feature, "parameters") else 0.0,
            param_dict,
        )
        if not sketch_id:
            continue
        if mode == "subtract":
            subtract_sketch_ids.add(sketch_id)
        else:
            positive_sketch_ids.add(sketch_id)
            if amount > max_thickness_mm:
                max_thickness_mm = amount

    positive_area = 0.0
    subtract_area = 0.0
    for sketch in part.sketches:
        sketch_area = sum(_sketch_entity_area(ent, param_dict) for ent in sketch.entities)
        if sketch.id in positive_sketch_ids:
            positive_area += sketch_area
        if sketch.id in subtract_sketch_ids:
            subtract_area += sketch_area

    volume_mm3 = max(0.0, positive_area - subtract_area) * max_thickness_mm
    density_kg_m3 = float(part.metadata.get("density_kg_m3", 1200.0))
    return volume_mm3 * 1e-9 * density_kg_m3


def _total_end_effector_mass_kg(tree: FeatureTree) -> tuple[float, list[str]]:
    """Return total mass (kg) and list of end-effector families used in the tree."""
    total = 0.0
    families: list[str] = []
    for part in tree.parts:
        family = part.family
        if family in END_EFFECTOR_FAMILIES:
            mass = _estimate_part_mass_kg(part)
            total += mass
            families.append(family)
    return total, families


def score_candidate(
    tree: FeatureTree,
    payload_kg: float = 5.0,
    robot_mass_kg: float = 20.0,
    weights: dict[str, float] | None = None,
    use_physics: bool = True,
    use_structural: bool = True,
    use_collision: bool = True,
) -> dict[str, float]:
    """Score a candidate tree using existing deterministic analysis tools.

    Returns a dict of normalized sub-scores and a composite score in [0, 1].

    Args:
        use_physics: when True, run real MuJoCo standing/sway rollouts to
            validate morphology instead of purely heuristic stability checks.
        use_structural: when True, run lightweight beam stress/buckling checks
            on structural links and include the result in the composite score.
        use_collision: when True, run representative-pose self-collision checks
            and include the resulting penalty in the composite score.
    """
    weights = weights or {}
    w_stability = weights.get("stability", 0.22)
    w_workspace = weights.get("workspace", 0.20)
    w_gait = weights.get("gait", 0.22)
    w_actuator = weights.get("actuator", 0.13)
    w_compact = weights.get("compactness", 0.05)
    w_structural = weights.get("structural", 0.05)
    w_collision = weights.get("collision", 0.05)
    w_manipulability = weights.get("manipulability", 0.08)

    if use_physics:
        physics_scores = physics_score_candidate(tree, n_steps=200)
        # Phase 30: real forward locomotion is now part of the morphology score.
        # Walk is weighted alongside standing, sway, and step because a robot
        # that can walk is strictly more capable than one that only stands.
        stability_score = (
            physics_scores["standing_score"] * 0.35
            + physics_scores["sway_score"] * 0.25
            + physics_scores["step_score"] * 0.20
            + physics_scores["walk_score"] * 0.20
        )
        # Gait feasibility requires real walking for legged templates, but
        # falls back to stepping-in-place for non-walking templates.
        gait_feasible = (
            physics_scores["walk_score"] >= 0.5
            or physics_scores["step_score"] >= 0.5
        )
        dynamically_stable = physics_scores["sway_score"] >= 0.5
        statically_stable = physics_scores["standing_score"] >= 0.5
        zmp_margin_m = physics_scores.get("zmp_margin_m", 0.0)
    else:
        # Stability score.
        stability_report = check_stability(tree, robot_mass_kg=robot_mass_kg)
        stability_score = 0.0
        if stability_report.statically_stable:
            stability_score += 0.4
        if stability_report.dynamically_stable:
            stability_score += 0.4
        if stability_report.gait_feasible:
            stability_score += 0.2
        gait_feasible = bool(stability_report.gait_feasible)
        dynamically_stable = bool(stability_report.dynamically_stable)
        statically_stable = bool(stability_report.statically_stable)
        zmp_margin_m = float(stability_report.zmp_margin_m)

    # Workspace score from end-effector / foot reachability.
    # Pick a reasonable end-effector id based on the template.
    prompt_lower = tree.prompt.lower()
    if "quadruped" in prompt_lower:
        end_effector_id = "foot_fl"
    elif "manipulator" in prompt_lower or "base" in prompt_lower:
        end_effector_id = "end_effector"
    else:
        end_effector_id = "hand_r"
    proxy = workspace_proxy(tree, end_effector_id, samples_per_joint=4)
    workspace_score = proxy["workspace_score"]
    manipulability_score_value = proxy["manipulability_score"]
    # Keep legacy fields for API compatibility.
    reach_mm = proxy["reach_mm"]
    sagittal_area_mm2 = proxy["sagittal_area_mm2"]
    lateral_span_mm = proxy["lateral_span_mm"]
    volume = proxy["sagittal_area_mm2"]  # backwards-compatible volume proxy

    # Gait score.
    gait_score = 1.0 if gait_feasible else 0.0

    # End-effector mass estimate for morphology scoring.
    end_effector_mass_kg, end_effector_families = _total_end_effector_mass_kg(tree)
    effective_payload_kg = payload_kg + end_effector_mass_kg

    # Actuator feasibility: lower max torque and power are better.
    specs = size_actuators_for_tree(tree, payload_kg=effective_payload_kg)
    summary = actuator_summary(specs)
    max_torque = summary.get("max_torque_nm", 0.0)
    total_power = summary.get("total_power_w", 0.0)
    # Penalize excessive torque/power; 50 N·m and 1000 W are considered high.
    actuator_score = (
        _normalize(50.0 - max_torque, 0.0, 50.0) * 0.6
        + _normalize(1000.0 - total_power, 0.0, 1000.0) * 0.4
    )

    # Compactness: prefer limb lengths that are a reasonable fraction of the
    # overall robot height. Very long or very short limbs relative to height are
    # penalized. We measure the total leg + arm span against the robot height.
    params = tree.parameter_dict()
    height = float(params.get("robot_height", 1000.0))
    leg_sum = (
        float(params.get("thigh_length", 0.0))
        + float(params.get("shin_length", 0.0))
        + float(params.get("body_length", 0.0)) * 0.5
    )
    arm_sum = (
        float(params.get("upper_arm_length", 0.0))
        + float(params.get("forearm_length", 0.0))
        + float(params.get("link1_length", 0.0))
        + float(params.get("link2_length", 0.0))
        + float(params.get("link3_length", 0.0))
    )
    total_span = leg_sum + arm_sum
    # Ideal total leg span is ~45-55% of height; ideal arm span similar.
    # Score peaks when total_span / height is between 0.4 and 1.0.
    ratio = total_span / height if height > 0 else 0.0
    if 0.4 <= ratio <= 1.0:
        compact_score = 1.0
    elif ratio < 0.4:
        compact_score = _normalize(ratio, 0.0, 0.4)
    else:
        compact_score = _normalize(2.0 - ratio, 1.0, 2.0)

    # Structural dynamics: penalize links that fail conservative beam checks.
    structural_report = (
        score_candidate_structural(tree, payload_kg=effective_payload_kg)
        if use_structural
        else {"structural_score": 1.0}
    )
    structural_score = float(structural_report["structural_score"])

    # Self-collision: penalize candidates that interfere with themselves in
    # representative task poses.
    collision_report = score_candidate_collision(tree) if use_collision else {"collision_penalty": 0.0}
    collision_penalty = float(collision_report["collision_penalty"])
    collision_score = 1.0 - collision_penalty

    composite = (
        w_stability * stability_score
        + w_workspace * workspace_score
        + w_gait * gait_score
        + w_actuator * actuator_score
        + w_compact * compact_score
        + w_structural * structural_score
        + w_collision * collision_score
        + w_manipulability * manipulability_score_value
    )

    result: dict[str, Any] = {
        "stability": round(stability_score, 4),
        "workspace": round(workspace_score, 4),
        "gait": round(gait_score, 4),
        "actuator": round(actuator_score, 4),
        "compactness": round(compact_score, 4),
        "structural": round(structural_score, 4),
        "collision_penalty": round(collision_penalty, 4),
        "collision_score": round(collision_score, 4),
        "manipulability": round(manipulability_score_value, 4),
        "composite": round(composite, 6),
        "max_torque_nm": round(max_torque, 4),
        "total_power_w": round(total_power, 4),
        "workspace_volume_mm3": round(volume, 4),
        "workspace_sagittal_area_mm2": round(sagittal_area_mm2, 4),
        "workspace_lateral_span_mm": round(lateral_span_mm, 4),
        "workspace_reach_mm": round(reach_mm, 4),
        "span_ratio": round(ratio, 4),
        "zmp_margin_m": round(zmp_margin_m, 6),
        "statically_stable": bool(statically_stable),
        "dynamically_stable": bool(dynamically_stable),
        "gait_feasible": bool(gait_feasible),
        "end_effector_family": end_effector_families[0] if end_effector_families else "default",
        "end_effector_mass_kg": round(end_effector_mass_kg, 6),
    }
    if use_physics:
        result["physics_standing_score"] = round(physics_scores["standing_score"], 4)
        result["physics_sway_score"] = round(physics_scores["sway_score"], 4)
        result["physics_step_score"] = round(physics_scores["step_score"], 4)
        result["physics_walk_score"] = round(physics_scores["walk_score"], 4)
        result["physics_score"] = round(physics_scores["physics_score"], 4)
    return result


def default_space(template: str) -> MorphologySpace:
    """Return a sensible default search space for a template."""
    if template == "humanoid":
        return MorphologySpace(
            template="humanoid",
            dimensions=[
                MorphologyDimension("robot_height", 600.0, 1400.0, 200.0),
                MorphologyDimension("thigh_length", 150.0, 300.0, 50.0),
                MorphologyDimension("shin_length", 150.0, 300.0, 50.0),
                MorphologyDimension("upper_arm_length", 100.0, 250.0, 50.0),
                MorphologyDimension("forearm_length", 100.0, 250.0, 50.0),
            ],
            limb_counts=[2],
            joint_range_scale=(0.8, 1.2),
            end_effectors=["default", "parallel_jaw_gripper", "three_finger_hand", "vacuum_gripper"],
            n_max=48,
            seed=0,
        )
    if template == "quadruped":
        return MorphologySpace(
            template="quadruped",
            dimensions=[
                MorphologyDimension("robot_height", 300.0, 800.0, 100.0),
                MorphologyDimension("thigh_length", 100.0, 220.0, 40.0),
                MorphologyDimension("shin_length", 100.0, 220.0, 40.0),
            ],
            limb_counts=[4],
            joint_range_scale=(0.8, 1.2),
            end_effectors=["default", "point_foot", "compliant_foot"],
            n_max=48,
            seed=0,
        )
    if template == "manipulator_on_base":
        return MorphologySpace(
            template="manipulator_on_base",
            dimensions=[
                MorphologyDimension("reach", 400.0, 1200.0, 200.0),
                MorphologyDimension("link1_length", 150.0, 400.0, 50.0),
                MorphologyDimension("link2_length", 150.0, 400.0, 50.0),
                MorphologyDimension("link3_length", 100.0, 300.0, 50.0),
            ],
            limb_counts=[1],
            joint_range_scale=(0.8, 1.2),
            end_effectors=["default", "parallel_jaw_gripper", "three_finger_hand", "vacuum_gripper"],
            n_max=48,
            seed=0,
        )
    return MorphologySpace(template=template, dimensions=[], n_max=48, seed=0)


def search_morphologies(
    space: MorphologySpace,
    payload_kg: float = 5.0,
    robot_mass_kg: float | None = None,
    weights: dict[str, float] | None = None,
    use_physics: bool = True,
    use_structural: bool = True,
    use_collision: bool = True,
    run_deep_structural: bool = False,
    deep_top_n: int = 3,
) -> list[MorphologyCandidate]:
    """Run a deterministic morphology search and return ranked candidates.

    Args:
        space: the search space to explore.
        payload_kg: design payload used by actuator sizing.
        robot_mass_kg: total mass estimate; defaults to payload * 4.
        weights: optional scoring weights.
        use_physics: when True, run real MuJoCo rollouts to score candidates.
        use_structural: when True, run beam stress/buckling checks.
        use_collision: when True, run representative-pose self-collision checks.
        run_deep_structural: when True, run deep CalculiX/surrogate structural
            verification on the top-N ranked candidates.
        deep_top_n: number of top candidates to verify with deep structural FEA.

    Returns:
        Candidates sorted by composite score (highest first).
    """
    rng = np.random.default_rng(space.seed)
    if robot_mass_kg is None:
        robot_mass_kg = payload_kg * 4.0

    candidates: list[MorphologyCandidate] = []
    counter = 0

    if isinstance(space, TopologySpace):
        topologies = list(space.topologies)
        rng.shuffle(topologies)
        for topo in topologies:
            if len(candidates) >= space.n_max:
                break
            tree = topology_to_feature_tree(topo)
            scores = score_candidate(
                tree,
                payload_kg,
                robot_mass_kg,
                weights,
                use_physics=use_physics,
                use_structural=use_structural,
                use_collision=use_collision,
            )
            candidate_id = f"topology_{topo.base_type}_{counter:04d}"
            candidates.append(
                MorphologyCandidate(
                    candidate_id=candidate_id,
                    template="topology",
                    parameters={"base_type": topo.base_type, "limb_count": float(len(topo.limbs))},
                    tree=tree,
                    scores=scores,
                    composite_score=scores["composite"],
                    topology=topo,
                )
            )
            counter += 1
    else:
        param_sets = space.parameter_grid(rng)
        for params in param_sets:
            for ee_type in space.end_effectors or ["default"]:
                tree = _make_tree(space.template, params)
                tree = _attach_end_effector(tree, ee_type)
                # Optionally vary joint range scale deterministically.
                if space.joint_range_scale and space.joint_range_scale[0] != space.joint_range_scale[1]:
                    scale = float(
                        rng.uniform(space.joint_range_scale[0], space.joint_range_scale[1])
                    )
                    tree = _scale_joint_limits(tree, scale)
                scores = score_candidate(
                    tree, payload_kg, robot_mass_kg, weights, use_physics=use_physics, use_structural=use_structural, use_collision=use_collision
                )
                candidate_id = f"{space.template}_{counter:04d}"
                candidates.append(
                    MorphologyCandidate(
                        candidate_id=candidate_id,
                        template=space.template,
                        parameters={**params, "end_effector": ee_type},
                        tree=tree,
                        scores=scores,
                        composite_score=scores["composite"],
                    )
                )
                counter += 1
                if len(candidates) >= space.n_max:
                    break
            if len(candidates) >= space.n_max:
                break

    candidates.sort(key=lambda c: c.composite_score, reverse=True)

    # Optional deep structural verification on the top-N candidates.
    if run_deep_structural and candidates:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for c in candidates[:deep_top_n]:
                deep = run_deep_structural_for_candidate(
                    c.tree,
                    tmp_path / c.candidate_id,
                    payload_kg=payload_kg,
                    solver_mode="auto",
                )
                c.scores["deep_structural"] = deep

    for i, c in enumerate(candidates):
        c.rank = i + 1
    return candidates


def save_search_results(
    search_id: str,
    space: MorphologySpace | TopologySpace,
    candidates: list[MorphologyCandidate],
    output_dir: Path,
) -> Path:
    """Persist a morphology search to disk for later retrieval."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(space, TopologySpace):
        space_dict: dict[str, Any] = {
            "template": "topology",
            "dimensions": [],
            "n_max": space.n_max,
            "seed": space.seed,
            "topologies": [
                {
                    "base_type": topo.base_type,
                    "limb_count": len(topo.limbs),
                    "tags": list(topo.tags),
                    "hash": topo.topology_hash(),
                }
                for topo in space.topologies
            ],
        }
    else:
        space_dict = {
            "template": space.template,
            "dimensions": [
                {"name": d.name, "min": d.min, "max": d.max, "step": d.step}
                for d in space.dimensions
            ],
            "n_max": space.n_max,
            "seed": space.seed,
        }
    data = {
        "search_id": search_id,
        "space": space_dict,
        "candidates": [c.with_tree_dict() for c in candidates],
    }
    path = output_dir / f"morphology_search_{search_id}.json"
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def load_search_results(path: Path) -> dict[str, Any]:
    """Load a persisted morphology search."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Morphology search not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
