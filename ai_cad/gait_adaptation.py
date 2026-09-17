"""Extract morphology-derived features used to adapt gait parameters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import mujoco
except Exception:  # pragma: no cover
    mujoco = None


@dataclass
class GaitMorphologyFeatures:
    """Morphology measurements used to scale gait and balance gains."""

    template: str
    com_height_m: float
    total_leg_length_m: float
    robot_mass_kg: float
    foot_length_m: float
    foot_width_m: float


def _detect_template(model, default: str = "humanoid") -> str:
    """Infer template from MuJoCo joint names."""
    if mujoco is None:
        return default
    names: set[str] = set()
    for i in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
        if name is not None:
            names.add(name)
    if "hip_pitch_r" in names:
        return "humanoid"
    if "hip_pitch_fr" in names or "hip_pitch_fl" in names:
        return "quadruped"
    return default


def _find_body_id(model, *candidates: str) -> int | None:
    """Return first matching MuJoCo body id."""
    if mujoco is None:
        return None
    for name in candidates:
        try:
            bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
            if bid >= 0:
                return bid
        except Exception:
            continue
    return None


def _torso_z(model, data) -> float:
    """Return current torso height in meters."""
    torso_id = _find_body_id(model, "torso_torso_plate", "torso", "body_body", "body")
    if torso_id is None:
        return 0.0
    return float(data.xpos[torso_id, 2])


def _leg_length_from_tree(tree: Any) -> float:
    """Sum thigh + shin length (or segment length fallback) in meters."""
    params = tree.parameter_dict() if hasattr(tree, "parameter_dict") else {}
    thigh = float(params.get("thigh_length", 220.0)) * 0.001
    shin = float(params.get("shin_length", 240.0)) * 0.001
    return thigh + shin


def _foot_size_from_tree(tree: Any) -> tuple[float, float]:
    """Return foot length and width in meters."""
    params = tree.parameter_dict() if hasattr(tree, "parameter_dict") else {}
    length = float(params.get("foot_length", 160.0)) * 0.001
    width = float(params.get("foot_width", 80.0)) * 0.001
    return length, width


def _robot_mass_from_tree(tree: Any) -> float:
    """Return total robot mass budget in kg."""
    params = tree.parameter_dict() if hasattr(tree, "parameter_dict") else {}
    return float(params.get("robot_mass_kg", 20.0))


def extract_morphology_features(
    model,
    data,
    tree: Any,
) -> GaitMorphologyFeatures:
    """Measure morphology features needed to scale gait parameters."""
    template = _detect_template(model)
    mujoco.mj_forward(model, data)
    com_height_m = _torso_z(model, data)
    total_leg_length_m = _leg_length_from_tree(tree)
    robot_mass_kg = _robot_mass_from_tree(tree)
    foot_length_m, foot_width_m = _foot_size_from_tree(tree)
    return GaitMorphologyFeatures(
        template=template,
        com_height_m=com_height_m,
        total_leg_length_m=total_leg_length_m,
        robot_mass_kg=robot_mass_kg,
        foot_length_m=foot_length_m,
        foot_width_m=foot_width_m,
    )
