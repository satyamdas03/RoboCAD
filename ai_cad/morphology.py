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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ai_cad.actuator_sizing import actuator_summary, size_actuators_for_tree
from ai_cad.feature_tree import FeatureTree
from ai_cad.kinematic_tree import sample_reachable_workspace
from ai_cad.robot_templates import humanoid_template, manipulator_on_base_template, quadruped_template
from ai_cad.stability import check_stability, stability_summary


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
class MorphologyCandidate:
    """One scored morphology candidate."""

    candidate_id: str
    template: str
    parameters: dict[str, float]
    tree: FeatureTree
    scores: dict[str, float] = field(default_factory=dict)
    composite_score: float = 0.0
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize candidate without the full tree for API responses."""
        return {
            "candidate_id": self.candidate_id,
            "template": self.template,
            "parameters": self.parameters,
            "scores": self.scores,
            "composite_score": round(self.composite_score, 6),
            "rank": self.rank,
        }

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
    """Apply a simple end-effector choice to the tree.

    Currently this is a placeholder that records the choice in the prompt and
    tags. A future phase can swap part families for grippers, feet, etc.
    """
    if ee_type == "default" or not ee_type:
        return tree
    tree = copy.deepcopy(tree)
    tree.prompt = f"{tree.prompt} with {ee_type} end-effector"
    return tree


def _normalize(value: float, lo: float, hi: float) -> float:
    """Normalize a value to [0, 1] with soft clamping."""
    if hi == lo:
        return 1.0 if value >= hi else 0.0
    return _clamp((value - lo) / (hi - lo), 0.0, 1.0)


def score_candidate(
    tree: FeatureTree,
    payload_kg: float = 5.0,
    robot_mass_kg: float = 20.0,
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Score a candidate tree using existing deterministic analysis tools.

    Returns a dict of normalized sub-scores and a composite score in [0, 1].
    """
    weights = weights or {}
    w_stability = weights.get("stability", 0.30)
    w_workspace = weights.get("workspace", 0.25)
    w_gait = weights.get("gait", 0.25)
    w_actuator = weights.get("actuator", 0.15)
    w_compact = weights.get("compactness", 0.05)

    # Stability score.
    stability_report = check_stability(tree, robot_mass_kg=robot_mass_kg)
    stability_score = 0.0
    if stability_report.statically_stable:
        stability_score += 0.4
    if stability_report.dynamically_stable:
        stability_score += 0.4
    if stability_report.gait_feasible:
        stability_score += 0.2

    # Workspace score from end-effector / foot reachability.
    # Pick a reasonable end-effector id based on the template.
    prompt_lower = tree.prompt.lower()
    if "quadruped" in prompt_lower:
        end_effector_id = "foot_fl"
    elif "manipulator" in prompt_lower or "base" in prompt_lower:
        end_effector_id = "end_effector"
    else:
        end_effector_id = "hand_r"
    workspace = sample_reachable_workspace(tree, end_effector_id, samples_per_joint=4)
    envelope = workspace.get("envelope_mm", (0.0, 0.0, 0.0))
    volume = workspace.get("volume_estimate_mm3", 0.0)
    # Use maximum reach distance as a robust proxy (sagittal-plane robots can
    # have zero Y envelope but large X/Z reach).
    reach_mm = max(envelope) if envelope else 0.0
    workspace_score = _normalize(reach_mm, 0.0, 1500.0)

    # Gait score.
    gait_score = 1.0 if stability_report.gait_feasible else 0.0

    # Actuator feasibility: lower max torque and power are better.
    specs = size_actuators_for_tree(tree, payload_kg=payload_kg)
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

    composite = (
        w_stability * stability_score
        + w_workspace * workspace_score
        + w_gait * gait_score
        + w_actuator * actuator_score
        + w_compact * compact_score
    )

    return {
        "stability": round(stability_score, 4),
        "workspace": round(workspace_score, 4),
        "gait": round(gait_score, 4),
        "actuator": round(actuator_score, 4),
        "compactness": round(compact_score, 4),
        "composite": round(composite, 6),
        "max_torque_nm": round(max_torque, 4),
        "total_power_w": round(total_power, 4),
        "workspace_volume_mm3": round(volume, 4),
        "workspace_envelope_mm": [round(e, 4) for e in envelope],
        "workspace_reach_mm": round(reach_mm, 4),
        "span_ratio": round(ratio, 4),
        "zmp_margin_m": round(stability_report.zmp_margin_m, 6),
        "statically_stable": bool(stability_report.statically_stable),
        "dynamically_stable": bool(stability_report.dynamically_stable),
        "gait_feasible": bool(stability_report.gait_feasible),
    }


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
            end_effectors=["default"],
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
            end_effectors=["default"],
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
            end_effectors=["default"],
            n_max=48,
            seed=0,
        )
    return MorphologySpace(template=template, dimensions=[], n_max=48, seed=0)


def search_morphologies(
    space: MorphologySpace,
    payload_kg: float = 5.0,
    robot_mass_kg: float | None = None,
    weights: dict[str, float] | None = None,
) -> list[MorphologyCandidate]:
    """Run a deterministic morphology search and return ranked candidates.

    Args:
        space: the search space to explore.
        payload_kg: design payload used by actuator sizing.
        robot_mass_kg: total mass estimate; defaults to payload * 4.
        weights: optional scoring weights.

    Returns:
        Candidates sorted by composite score (highest first).
    """
    rng = np.random.default_rng(space.seed)
    if robot_mass_kg is None:
        robot_mass_kg = payload_kg * 4.0

    param_sets = space.parameter_grid(rng)
    candidates: list[MorphologyCandidate] = []
    counter = 0
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
            scores = score_candidate(tree, payload_kg, robot_mass_kg, weights)
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
    for i, c in enumerate(candidates):
        c.rank = i + 1
    return candidates


def save_search_results(
    search_id: str,
    space: MorphologySpace,
    candidates: list[MorphologyCandidate],
    output_dir: Path,
) -> Path:
    """Persist a morphology search to disk for later retrieval."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "search_id": search_id,
        "space": {
            "template": space.template,
            "dimensions": [
                {"name": d.name, "min": d.min, "max": d.max, "step": d.step}
                for d in space.dimensions
            ],
            "n_max": space.n_max,
            "seed": space.seed,
        },
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
