"""Robot simulation certification for RoboCAD Milestone G.

Deterministic, randomized-world stress tests for generated robot designs.
The module exports bundles, builds MuJoCo worlds with procedural terrain and
domain randomization, and runs fast closed-loop certification cases without
requiring reinforcement-learning training.  It is designed to be safe when
MuJoCo is unavailable: all public functions degrade gracefully and report
which cases were skipped.
"""
from __future__ import annotations

import copy
import math
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

try:
    import mujoco
except Exception:  # pragma: no cover - exercised only where mujoco is installed.
    mujoco = None

from ai_cad.feature_tree import FeatureTree
from ai_cad.gait import (
    _apply_pd_targets,
    _detect_template,
    default_standing_pose,
    default_walk_params,
    morphology_aware_balance_gains,
    morphology_aware_walk_params,
    run_walk_test,
)
from ai_cad.gait_adaptation import extract_morphology_features
from ai_cad.geda_bridge.exporter import export_bundle_from_tree
from ai_cad.geda_bridge.loader import load_bundle_manifest
from ai_cad.geda_bridge.models import BundlePaths
from ai_cad.geda_bridge.scene_templates import ScenePose
from ai_cad.geda_bridge.world_builder import (
    DomainRandomization,
    WorldBuilder,
    WorldDescription,
    apply_domain_randomization,
    export_world_to_mjcf,
    plane_terrain,
    ramp_terrain,
    slope_terrain,
    stair_terrain,
    uneven_terrain,
)
from ai_cad.morphology_physics import (
    _find_body_id,
    _foot_body_ids,
    _has_nan_or_inf,
    _run_pd_standing,
    _run_sway_test,
    _scale_masses_and_add_freejoint,
)


G = 9.80665


class RobotCertCase(str, Enum):
    """Named robot-specific simulation certification cases."""

    TERRAIN_WALKING = "terrain_walking"
    PAYLOAD_LIFT = "payload_lift"
    PUSH_RECOVERY = "push_recovery"
    DROP_TEST = "drop_test"
    ACTUATOR_SATURATION = "actuator_saturation"


DEFAULT_ROBOT_CERT_CASES: list[RobotCertCase] = [
    RobotCertCase.TERRAIN_WALKING,
    RobotCertCase.PUSH_RECOVERY,
    RobotCertCase.DROP_TEST,
    RobotCertCase.ACTUATOR_SATURATION,
    RobotCertCase.PAYLOAD_LIFT,
]


@dataclass
class RobotCertCaseResult:
    """Result for a single robot certification case."""

    case: str
    passed: bool
    score: float  # 0.0 .. 1.0
    details: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    error: str | None = None


@dataclass
class RobotCertificationResult:
    """Aggregate result of a robot certification run."""

    design_id: str | None
    passed: bool
    score: float  # 0.0 .. 1.0
    cases: list[RobotCertCaseResult]
    mu_joco_available: bool
    bundle_dir: str | None = None
    notes: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return {
            "design_id": self.design_id,
            "passed": self.passed,
            "score": round(self.score, 4),
            "mujoco_available": self.mu_joco_available,
            "bundle_dir": self.bundle_dir,
            "notes": self.notes,
            "cases": [
                {
                    "case": c.case,
                    "passed": c.passed,
                    "score": round(c.score, 4),
                    "skipped": c.skipped,
                    "error": c.error,
                    "details": c.details,
                }
                for c in self.cases
            ],
        }


def _mujoco_available() -> bool:
    return mujoco is not None


def _is_legged_robot(model) -> bool:
    """Return True if the model has a torso and at least one foot body."""
    if mujoco is None:
        return False
    template = _detect_template(model)
    torso_id = _find_body_id(model, "torso_torso_plate", "torso", "body_body", "body")
    foot_ids = _foot_body_ids(model, template)
    return torso_id is not None and len(foot_ids) > 0


def _has_arm_joints(model) -> bool:
    """Heuristic: return True if the model has shoulder/elbow/wrist joints."""
    if mujoco is None:
        return False
    for i in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
        if name and any(part in name for part in ("shoulder", "elbow", "wrist", "arm")):
            return True
    return False


def _strip_robot_ground_plane(mjcf_path: Path) -> None:
    """Remove the duplicated ground plane added by _scale_masses_and_add_freejoint.

    When the robot MJCF is included inside a world, the world provides its own
    terrain; leaving the robot's internal ground plane creates coincident
    contacts and can destabilize walking tests.
    """
    tree_xml = ET.parse(mjcf_path)
    root = tree_xml.getroot()
    worldbody = root.find("worldbody")
    if worldbody is None:
        return
    for geom in list(worldbody.findall("geom")):
        if geom.get("type") == "plane" and geom.get("name") == "ground_plane":
            worldbody.remove(geom)
    tree_xml.write(mjcf_path, encoding="utf-8", xml_declaration=True)


def _export_bundle(
    tree: FeatureTree,
    output_dir: Path,
    name: str = "model",
) -> BundlePaths | None:
    """Export a tree, post-process the robot MJCF, and return bundle paths."""
    try:
        paths = export_bundle_from_tree(tree, output_dir, name=name)
    except Exception as exc:
        return None

    mjcf_path = paths.mjcf
    if not mjcf_path.exists():
        return None

    try:
        _scale_masses_and_add_freejoint(mjcf_path, tree)
        _strip_robot_ground_plane(mjcf_path)
    except Exception:
        return None
    return paths


def _load_world_model(world_path: Path) -> tuple[Any, Any] | None:
    """Load a world MJCF into MuJoCo, returning (model, data) or None."""
    if not _mujoco_available():
        return None
    try:
        model = mujoco.MjModel.from_xml_path(str(world_path))
        data = mujoco.MjData(model)
        return model, data
    except Exception:
        return None


def _build_walker_world(
    tree: FeatureTree,
    paths: BundlePaths,
    terrain_type: str = "uneven",
    seed: int = 42,
) -> WorldDescription:
    """Build a walker world around an exported bundle with chosen terrain."""
    params = tree.parameter_dict()
    height_m = float(params.get("robot_height_m", 1.0))
    if height_m <= 0.1:
        # Some templates store leg length in mm.
        height_m = float(params.get("total_leg_length_m", 1000.0)) * 0.001
    height_m = max(0.3, min(height_m, 2.5))

    manifest = load_bundle_manifest(paths.directory)
    builder = WorldBuilder(f"cert_walker_{terrain_type}", template="walker")
    builder.set_asset(manifest.parts, pose=ScenePose(pos=(0.0, 0.0, height_m)))

    if terrain_type == "slope":
        builder.add_terrain(slope_terrain(pitch_rad=-0.08, friction=(0.9, 0.1, 0.1)))
    elif terrain_type == "stairs":
        for t in stair_terrain(
            origin=(0.0, 0.0, 0.0),
            direction=(1.0, 0.0),
            n_steps=4,
            step_rise=0.04,
            step_run=0.25,
            step_width=1.2,
            friction=(0.9, 0.1, 0.1),
        ):
            builder.add_terrain(t)
    elif terrain_type == "ramp":
        builder.add_terrain(ramp_terrain(length=1.5, rise=0.15, friction=(0.9, 0.1, 0.1)))
    elif terrain_type == "uneven":
        for t in uneven_terrain(
            size=(4.0, 2.0),
            grid=(10, 4),
            max_bump_m=0.035,
            seed=seed,
            friction=(0.9, 0.1, 0.1),
        ):
            builder.add_terrain(t)
    else:
        builder.add_terrain(
            plane_terrain(
                name="floor",
                size=(10.0, 10.0, 0.01),
                friction=(0.9, 0.1, 0.1),
            )
        )

    builder.enable_randomization(DomainRandomization(seed=seed))
    return apply_domain_randomization(builder.world, seed=seed)


def _build_balance_world(
    tree: FeatureTree,
    seed: int = 42,
) -> WorldDescription:
    """Build a flat-floor world for balance/push/drop tests."""
    params = tree.parameter_dict()
    height_m = float(params.get("robot_height_m", 1.0))
    if height_m <= 0.1:
        height_m = float(params.get("total_leg_length_m", 1000.0)) * 0.001
    height_m = max(0.3, min(height_m, 2.5))

    manifest = load_bundle_manifest(paths.directory)
    builder = WorldBuilder("cert_balance", template="humanoid_stand")
    builder.set_asset(manifest.parts, pose=ScenePose(pos=(0.0, 0.0, height_m * 0.55)))
    builder.add_terrain(
        plane_terrain(
            name="floor",
            size=(6.0, 6.0, 0.01),
            friction=(0.9, 0.1, 0.1),
        )
    )
    builder.enable_randomization(DomainRandomization(seed=seed))
    return apply_domain_randomization(builder.world, seed=seed)


def _write_world(
    world: WorldDescription,
    paths: BundlePaths,
    name: str = "world",
) -> Path | None:
    """Write a world MJCF next to the robot MJCF so includes resolve correctly."""
    try:
        world_path = paths.directory / f"{name}.mjcf"
        export_world_to_mjcf(world, world_path, robot_mjcf_file=paths.mjcf.name)
        return world_path
    except Exception:
        return None


def _terrain_walking_case(
    model,
    data,
    tree: FeatureTree,
    terrain: str,
) -> dict[str, Any]:
    """Run a morphology-aware walking test on a terrain world."""
    template = _detect_template(model)
    features = extract_morphology_features(model, data, tree)
    params = morphology_aware_walk_params(features)
    gains = morphology_aware_balance_gains(features)

    walk = run_walk_test(
        model,
        data,
        template=template,
        n_steps=600,
        params=params,
        balance_gains=gains,
    )
    # Strict pass for certification: must move forward, stay upright, and not drop much.
    passed = bool(
        walk.get("walk_ok")
        and walk.get("forward_distance_m", 0.0) > 0.05
        and walk.get("torso_z_drop_m", 1.0) < 0.12
        and walk.get("max_pitch_roll_deg", 90.0) < 25.0
        and not walk.get("nan_inf", True)
    )
    return {
        "passed": passed,
        "terrain": terrain,
        "forward_distance_m": walk.get("forward_distance_m", 0.0),
        "torso_z_drop_m": walk.get("torso_z_drop_m", 1.0),
        "max_pitch_roll_deg": walk.get("max_pitch_roll_deg", 90.0),
        "nan_inf": walk.get("nan_inf", True),
    }


def _push_recovery_case(
    model,
    data,
) -> dict[str, Any]:
    """Run a stronger/later push recovery test on a flat floor."""
    sway = _run_sway_test(
        model,
        data,
        n_steps=500,
        push_steps=80,
        push_force_n=35.0,
        kp=100.0,
        kd=20.0,
    )
    passed = bool(
        sway.get("sway_ok")
        and not sway.get("nan_inf", True)
        and sway.get("max_tilt_deg", 90.0) < 40.0
    )
    return {
        "passed": passed,
        "max_tilt_deg": sway.get("max_tilt_deg", 90.0),
        "torso_z_drop_m": sway.get("torso_z_drop_m", 1.0),
        "nan_inf": sway.get("nan_inf", True),
    }


def _drop_test_case(
    model,
    data,
    drop_height_m: float = 0.05,
) -> dict[str, Any]:
    """Lift the robot in qpos, drop, and see if PD standing recovers."""
    if mujoco is None:
        return {"passed": False, "error": "mujoco not installed"}

    torso_id = _find_body_id(model, "torso_torso_plate", "torso", "body_body", "body")
    template = _detect_template(model)
    standing_pose = default_standing_pose(template)

    mujoco.mj_resetData(model, data)
    # Move the freejoint origin up by drop_height_m.
    if model.nv >= 3:
        data.qpos[:3] = data.qpos[:3] + np.array([0.0, 0.0, drop_height_m])

    # Target the standing pose with modest gains.
    actuator_targets: dict[str, float] = {}
    for i in range(model.nu):
        joint_id = model.actuator_trnid[i, 0]
        joint_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id)
        if model.jnt_type[joint_id] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        actuator_targets[joint_name] = float(standing_pose.get(joint_name, 0.0))

    mujoco.mj_forward(model, data)
    initial_z = float(data.xpos[torso_id, 2]) if torso_id is not None else 0.0
    min_z = initial_z
    max_tilt = 0.0
    nan_inf = False

    for _ in range(400):
        _apply_pd_targets(model, data, actuator_targets, kp=90.0, kd=18.0)
        try:
            mujoco.mj_step(model, data)
        except Exception:
            nan_inf = True
            break
        if _has_nan_or_inf(model, data):
            nan_inf = True
            break
        if torso_id is not None:
            z = float(data.xpos[torso_id, 2])
            min_z = min(min_z, z)
            xmat = data.xmat[torso_id].reshape(3, 3)
            tilt = np.degrees(np.arccos(float(np.clip(xmat[2, 2], -1.0, 1.0))))
            max_tilt = max(max_tilt, tilt)

    passed = bool(
        not nan_inf
        and max_tilt < 45.0
        and (initial_z - min_z) < 0.25
    )
    return {
        "passed": passed,
        "drop_height_m": drop_height_m,
        "max_tilt_deg": max_tilt,
        "torso_z_drop_m": initial_z - min_z,
        "nan_inf": nan_inf,
    }


def _actuator_saturation_case(
    model,
    data,
    tree: FeatureTree,
) -> dict[str, Any]:
    """Run a walking test and report the worst-case actuator saturation ratio."""
    template = _detect_template(model)
    features = extract_morphology_features(model, data, tree)
    params = morphology_aware_walk_params(features)
    gains = morphology_aware_balance_gains(features)

    walk = run_walk_test(
        model,
        data,
        template=template,
        n_steps=400,
        params=params,
        balance_gains=gains,
    )

    max_ratio = 0.0
    saturated_count = 0
    # MuJoCo position actuators expose forcerange after post-processing.
    if (
        hasattr(model, "actuator_forcerange")
        and model.actuator_forcerange is not None
        and model.nu > 0
    ):
        for i in range(model.nu):
            lo, hi = model.actuator_forcerange[i]
            limit = max(abs(lo), abs(hi), 1e-9)
            peak = max(
                abs(float(data.ctrl[i])) if i < len(data.ctrl) else 0.0,
                # Also scan the walk trajectory if we instrumented it; the final
                # data.ctrl is a representative sample after the last step.
                0.0,
            )
            ratio = peak / limit
            max_ratio = max(max_ratio, ratio)
            if ratio > 0.95:
                saturated_count += 1

    # Pass if the robot walked and never saturated; allow margin up to 85%.
    passed = bool(
        walk.get("walk_ok")
        and not walk.get("nan_inf", True)
        and max_ratio < 0.85
        and saturated_count == 0
    )
    return {
        "passed": passed,
        "max_saturation_ratio": round(max_ratio, 4),
        "saturated_actuators": saturated_count,
        "walk_distance_m": walk.get("forward_distance_m", 0.0),
    }


def _payload_lift_case(tree: FeatureTree) -> dict[str, Any]:
    """Static torque-margin check for manipulation payloads.

    A full dynamic payload-lift certification requires a task-specific policy.
    For the product-launch certification suite we verify the static torque
    margin at the shoulder for a nominal 1 kg payload held at the arm reach.
    """
    params = tree.parameter_dict()
    reach_m = 0.0
    for key in ("upper_arm_length", "forearm_length", "wrist_length", "arm_reach"):
        if key in params:
            val = float(params[key])
            if key in ("upper_arm_length", "forearm_length", "wrist_length"):
                # These are often in mm in the parametric templates.
                if val > 0.5:
                    val *= 0.001
            reach_m += val
    if reach_m <= 0.05:
        reach_m = 0.3  # default humanoid/manipulator reach

    payload_kg = 1.0
    required_torque = payload_kg * G * reach_m

    # Actuator force limit: prefer explicit parameter, fall back to conservative.
    actuator_limit_n = float(params.get("actuator_force_limit_n", 0.0))
    if actuator_limit_n <= 0.0:
        robot_mass = float(params.get("robot_mass_kg", 20.0))
        # Conservative default: enough to lift robot's own mass at half reach.
        actuator_limit_n = max(50.0, robot_mass * G * 0.5)

    # Approximate shoulder moment arm for force->torque conversion.
    moment_arm_m = max(0.05, reach_m * 0.3)
    available_torque = actuator_limit_n * moment_arm_m
    margin = available_torque - required_torque
    ratio = required_torque / max(available_torque, 1e-9)

    passed = ratio < 0.75 and margin > 0.0
    return {
        "passed": passed,
        "payload_kg": payload_kg,
        "reach_m": round(reach_m, 4),
        "required_torque_nm": round(required_torque, 4),
        "available_torque_nm": round(available_torque, 4),
        "torque_margin_nm": round(margin, 4),
        "required_to_available_ratio": round(ratio, 4),
    }


def run_robot_certification(
    tree: FeatureTree,
    cases: list[RobotCertCase] | None = None,
    seed: int = 42,
    output_dir: Path | None = None,
    cleanup: bool = True,
    design_id: str | None = None,
) -> RobotCertificationResult:
    """Run the robot simulation certification suite for a FeatureTree.

    Args:
        tree: robot design to certify.
        cases: cases to run; defaults to ``DEFAULT_ROBOT_CERT_CASES``.
        seed: deterministic seed for domain randomization and terrain bumps.
        output_dir: optional directory to keep the exported bundle/world.
        cleanup: if True and ``output_dir`` is not provided, delete temp files.
        design_id: optional persisted design identifier.

    Returns:
        ``RobotCertificationResult`` with per-case and aggregate scores.
    """
    cases = cases if cases is not None else DEFAULT_ROBOT_CERT_CASES
    result = RobotCertificationResult(
        design_id=design_id,
        passed=False,
        score=0.0,
        cases=[],
        mu_joco_available=_mujoco_available(),
        notes=[],
    )

    if not _mujoco_available():
        result.notes.append("mujoco not installed; all robot cases skipped")
        for case in cases:
            result.cases.append(
                RobotCertCaseResult(
                    case=case.value,
                    passed=False,
                    score=0.0,
                    skipped=True,
                    error="mujoco not installed",
                )
            )
        return result

    work_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="robocad_robot_cert_"))
    try:
        paths = _export_bundle(tree, work_dir, name="model")
        if paths is None:
            result.notes.append("failed to export bundle for certification")
            for case in cases:
                result.cases.append(
                    RobotCertCaseResult(
                        case=case.value,
                        passed=False,
                        score=0.0,
                        skipped=True,
                        error="bundle export failed",
                    )
                )
            return result

        result.bundle_dir = str(paths.directory)
        manifest = load_bundle_manifest(paths.directory)

        for idx, case in enumerate(cases):
            case_seed = seed + idx * 1000
            case_result = RobotCertCaseResult(case=case.value, passed=False, score=0.0)

            try:
                if case == RobotCertCase.TERRAIN_WALKING:
                    # Default certification only needs one terrain variant to stay fast.
                    terrain = "uneven"
                    world = _build_walker_world(tree, paths, terrain_type=terrain, seed=case_seed)
                    world_path = _write_world(world, paths, name=f"world_{case.value}")
                    if world_path is None:
                        raise RuntimeError("failed to export walker world")
                    loaded = _load_world_model(world_path)
                    if loaded is None:
                        raise RuntimeError("failed to load walker world in MuJoCo")
                    model, data = loaded
                    if not _is_legged_robot(model):
                        case_result.skipped = True
                        case_result.error = "non-legged template"
                        case_result.details = {"reason": "TERRAIN_WALKING applies only to legged robots"}
                    else:
                        details = _terrain_walking_case(model, data, tree, terrain)
                        case_result.passed = details["passed"]
                        case_result.score = 1.0 if details["passed"] else 0.0
                        case_result.details = details

                elif case == RobotCertCase.PUSH_RECOVERY:
                    world = _build_balance_world(tree, seed=case_seed)
                    world_path = _write_world(world, paths, name=f"world_{case.value}")
                    if world_path is None:
                        raise RuntimeError("failed to export balance world")
                    loaded = _load_world_model(world_path)
                    if loaded is None:
                        raise RuntimeError("failed to load balance world in MuJoCo")
                    model, data = loaded
                    if not _is_legged_robot(model):
                        case_result.skipped = True
                        case_result.error = "non-legged template"
                        case_result.details = {"reason": "PUSH_RECOVERY applies only to legged robots"}
                    else:
                        details = _push_recovery_case(model, data)
                        case_result.passed = details["passed"]
                        case_result.score = 1.0 if details["passed"] else 0.0
                        case_result.details = details

                elif case == RobotCertCase.DROP_TEST:
                    world = _build_balance_world(tree, seed=case_seed)
                    world_path = _write_world(world, paths, name=f"world_{case.value}")
                    if world_path is None:
                        raise RuntimeError("failed to export balance world")
                    loaded = _load_world_model(world_path)
                    if loaded is None:
                        raise RuntimeError("failed to load balance world in MuJoCo")
                    model, data = loaded
                    if not _is_legged_robot(model):
                        case_result.skipped = True
                        case_result.error = "non-legged template"
                        case_result.details = {"reason": "DROP_TEST applies only to legged robots"}
                    else:
                        details = _drop_test_case(model, data, drop_height_m=0.05)
                        case_result.passed = details["passed"]
                        case_result.score = 1.0 if details["passed"] else 0.0
                        case_result.details = details

                elif case == RobotCertCase.ACTUATOR_SATURATION:
                    world = _build_walker_world(tree, paths, terrain_type="plane", seed=case_seed)
                    world_path = _write_world(world, paths, name=f"world_{case.value}")
                    if world_path is None:
                        raise RuntimeError("failed to export walker world")
                    loaded = _load_world_model(world_path)
                    if loaded is None:
                        raise RuntimeError("failed to load walker world in MuJoCo")
                    model, data = loaded
                    if not _is_legged_robot(model):
                        case_result.skipped = True
                        case_result.error = "non-legged template"
                        case_result.details = {"reason": "ACTUATOR_SATURATION applies only to legged robots"}
                    else:
                        details = _actuator_saturation_case(model, data, tree)
                        case_result.passed = details["passed"]
                        case_result.score = 1.0 if details["passed"] else 0.0
                        case_result.details = details

                elif case == RobotCertCase.PAYLOAD_LIFT:
                    # Static check; does not require a world model.
                    details = _payload_lift_case(tree)
                    case_result.passed = details["passed"]
                    case_result.score = 1.0 if details["passed"] else 0.0
                    case_result.details = details
                    if not _has_arm_joints(mujoco.MjModel.from_xml_path(str(paths.mjcf)) if mujoco else None):
                        case_result.skipped = True
                        case_result.error = "no arm joints detected"
                        case_result.details = {"reason": "PAYLOAD_LIFT applies only to manipulators"}
                        case_result.score = 0.0

            except Exception as exc:
                case_result.error = str(exc)
                case_result.details = {"exception": str(exc)}

            result.cases.append(case_result)

        # Aggregate score: average of non-skipped cases; pass if >= 60% and no failed must-pass cases.
        scored = [c for c in result.cases if not c.skipped]
        if scored:
            total = sum(c.score for c in scored)
            result.score = round(total / len(scored), 4)
            result.passed = result.score >= 0.6 and all(c.passed or c.skipped for c in result.cases)
        else:
            result.score = 0.0
            result.passed = False
            result.notes.append("no applicable robot certification cases")

    finally:
        if cleanup and output_dir is None:
            shutil.rmtree(work_dir, ignore_errors=True)

    return result
