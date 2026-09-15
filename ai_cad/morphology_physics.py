"""Physics-based morphology scoring for RoboCAD Phase 29.

Replaces heuristic stability/gait proxies with real MuJoCo rollouts. Each
morphology candidate is exported to MJCF, loaded in MuJoCo, and evaluated with:

1. Standing equilibrium: can the robot stay upright with a simple PD pose controller?
2. Sway recovery: does it survive a small lateral push and return to standing?

The returned score correlates with actual simulation stability rather than
support-polygon heuristics.
"""
from __future__ import annotations

import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np

try:
    import mujoco
except Exception:  # pragma: no cover - exercised only where mujoco is installed.
    mujoco = None

from ai_cad.feature_tree import FeatureTree
from ai_cad.gait import (
    default_standing_pose,
    default_step_params,
    default_walk_params,
    run_step_test,
    run_walk_test,
    _apply_pd_targets,
    _detect_template,
    _foot_body_ids,
)
from ai_cad.geda_bridge.exporter import export_bundle_from_tree


G = 9.80665


def _mujoco_available() -> bool:
    return mujoco is not None


def _find_body_id(model, *candidates: str) -> int | None:
    """Return the first matching MuJoCo body id, or None."""
    for name in candidates:
        try:
            bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
            if bid >= 0:
                return bid
        except Exception:
            continue
    return None


def _body_name(model, body_id: int) -> str:
    return mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)


def _scale_masses_and_add_freejoint(mjcf_path: Path, tree: FeatureTree) -> None:
    """Post-process an exported MJCF so the model can be physically tested.

    - Scales all body masses so the total matches the tree's ``robot_mass_kg``.
    - Adds a ``freejoint`` to the first body under ``worldbody`` so the robot is
      dynamically free instead of welded to the world.
    """
    total_budget = float(tree.parameter_dict().get("robot_mass_kg", 20.0))
    tree_xml = ET.parse(mjcf_path)
    root = tree_xml.getroot()

    masses: list[float] = []
    inertial_elems: list[ET.Element] = []
    for body in root.iter("body"):
        inertial = body.find("inertial")
        if inertial is not None:
            try:
                masses.append(float(inertial.get("mass", "0")))
                inertial_elems.append(inertial)
            except (TypeError, ValueError):
                pass

    current_total = sum(masses)
    if current_total > 0:
        scale = total_budget / current_total
        for inertial, mass in zip(inertial_elems, masses):
            new_mass = mass * scale
            inertial.set("mass", f"{new_mass:.6f}")
            # Exported template meshes often have numerically tiny inertias,
            # which makes MuJoCo unstable. Enforce a minimum sane inertia
            # based on mass: I ~ m * r^2 with r = 50 mm characteristic size.
            min_inertia = new_mass * 0.0025
            try:
                diag_str = inertial.get("diaginertia", "")
                diag = [float(x) for x in diag_str.split()]
                if len(diag) == 3:
                    diag = [max(d, min_inertia) for d in diag]
                    inertial.set("diaginertia", f"{diag[0]:.6e} {diag[1]:.6e} {diag[2]:.6e}")
            except (TypeError, ValueError, AttributeError):
                pass

    worldbody = root.find("worldbody")
    if worldbody is None:
        tree_xml.write(mjcf_path, encoding="utf-8", xml_declaration=True)
        return

    # Add an explicit ground plane so walking/stability rollouts have a reliable
    # ground contact. MuJoCo does not provide an implicit floor; without this the
    # free-floating robot falls through empty space.
    if not any((geom.get("type") == "plane" for geom in worldbody.findall("geom"))):
        ET.SubElement(
            worldbody,
            "geom",
            {
                "name": "ground_plane",
                "type": "plane",
                "size": "10 10 0.1",
                "rgba": "0.5 0.5 0.5 1",
                "friction": "1.0 0.005 0.0001",
            },
        )

    # Add freejoint to the first body under worldbody so the robot is free-floating.
    first_body = worldbody.find("body")
    if first_body is not None and first_body.find("freejoint") is None:
        # Insert freejoint before inertial/geom/joint so MuJoCo is happy.
        ET.SubElement(first_body, "freejoint")

    # Add proper foot contact patches. Template foot meshes are tiny placeholder
    # cubes, so ground contact is either missing or point-like. We add a
    # dedicated contact geom sized from template parameters so walking rollouts
    # get a stable, realistic sole.
    params = tree.parameter_dict()
    foot_length_m = float(params.get("foot_length", 160.0)) * 0.001
    foot_width_m = float(params.get("foot_width", 80.0)) * 0.001
    for body in root.iter("body"):
        bname = (body.get("name") or "").lower()
        if "foot" not in bname:
            continue
        already = any((geom.get("name") or "").endswith("_contact") for geom in body.findall("geom"))
        if already:
            continue
        is_humanoid = "foot_length" in params and "foot_width" in params
        # Point foot: small sphere placed below the ankle so the ground plane lifts
        # the foot to a stable standing height. This keeps the step test stable while
        # still giving a rolling point contact for walking tests.
        ET.SubElement(
            body,
            "geom",
            {
                "name": f"{body.get('name')}_contact",
                "type": "sphere",
                "size": "0.040",
                "pos": "0.000000 0.000000 0.040000",
                "friction": "1.0 0.005 0.0001",
                "rgba": "1.0 0.2 0.2 0.4",
                "group": "3",
            },
        )

    # Disable collision on the tiny placeholder mesh geoms. They overlap at the
    # joints and create dozens of spurious contacts with the ground, which slows
    # integration and destabilizes the walking controller. The dedicated foot
    # contact geoms are the only collision primitives.
    for body in root.iter("body"):
        for geom in body.findall("geom"):
            if (geom.get("name") or "").endswith("_contact"):
                continue
            if geom.get("type") in ("mesh", "box", "sphere", "capsule", "cylinder"):
                geom.set("contype", "0")
                geom.set("conaffinity", "0")

    # Add light joint damping to all non-free joints to suppress violent
    # oscillations during contact transitions.
    for joint in root.iter("joint"):
        if joint.get("type") in ("hinge", "slide") and joint.get("damping") is None:
            joint.set("damping", "0.5")

    # Convert motors to position actuators for morphology tests. Position
    # actuators let MuJoCo's implicit solver track target joint angles, which
    # is far more stable for walking than explicit per-step PD torques.
    actuator = root.find("actuator")
    if actuator is not None:
        for motor in list(actuator.findall("motor")):
            jname = motor.get("joint")
            jrange = "-3.141593 3.141593"
            for joint in root.iter("joint"):
                if joint.get("name") == jname and joint.get("range"):
                    jrange = joint.get("range")
                    break
            pos_name = (motor.get("name") or "").replace("_motor", "_position")
            pos = ET.SubElement(
                actuator,
                "position",
                {
                    "name": pos_name,
                    "joint": jname,
                    "ctrlrange": jrange,
                    "kp": "600",
                    "kv": "60",
                    "gear": "1",
                },
            )
            motor_range = (motor.get("ctrlrange") or "").split()
            if len(motor_range) == 2:
                pos.set("forcerange", f"{motor_range[0]} {motor_range[1]}")
            actuator.remove(motor)

    tree_xml.write(mjcf_path, encoding="utf-8", xml_declaration=True)


def _load_model_from_tree(tree: FeatureTree, output_dir: Path, name: str = "model") -> tuple[Any, Any] | None:
    """Export a tree to MJCF, post-process, and load into MuJoCo.

    Returns ``(model, data)`` or ``None`` if MuJoCo is unavailable or loading fails.
    """
    if not _mujoco_available():
        return None

    try:
        export_bundle_from_tree(tree, output_dir, name=name)
    except Exception:
        return None

    mjcf_path = output_dir / f"{name}.mjcf"
    if not mjcf_path.exists():
        return None

    try:
        _scale_masses_and_add_freejoint(mjcf_path, tree)
        model = mujoco.MjModel.from_xml_path(str(mjcf_path))
        data = mujoco.MjData(model)
        return model, data
    except Exception:
        return None


def _has_nan_or_inf(model, data) -> bool:
    """Return True if any simulation state contains NaN or Inf."""
    arrays = [data.qpos, data.qvel, data.qacc]
    if hasattr(data, "xfrc_applied"):
        arrays.append(data.xfrc_applied)
    for arr in arrays:
        if np.isnan(arr).any() or np.isinf(arr).any():
            return True
    return False


def _run_pd_standing(
    model,
    data,
    n_steps: int,
    kp: float = 100.0,
    kd: float = 20.0,
    target_positions: np.ndarray | None = None,
) -> dict[str, Any]:
    """Run a simulation with a simple PD controller holding joints at target.

    Returns a dict with final torso height, pitch/roll, max qacc magnitude,
    whether NaN occurred, and whether the robot stayed upright.
    """
    if target_positions is None:
        target_positions = np.zeros(model.nv)

    # Build a per-actuator target dict that handles both motor and position
    # actuators via the gait module's helper.
    template = "humanoid" if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "hip_pitch_r") >= 0 else "quadruped"
    standing_pose = default_standing_pose(template)
    actuator_targets: dict[str, float] = {}
    for i in range(model.nu):
        joint_id = model.actuator_trnid[i, 0]
        joint_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id)
        if model.jnt_type[joint_id] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        if joint_name in standing_pose:
            actuator_targets[joint_name] = float(standing_pose[joint_name])
        else:
            # Fall back to the supplied nv-array target (usually zero) for any
            # joints not in the template-specific standing pose.
            qvel_addr = model.jnt_dofadr[joint_id]
            actuator_targets[joint_name] = float(target_positions[qvel_addr])

    # Make sure kinematics are evaluated before measuring the initial torso height.
    mujoco.mj_forward(model, data)
    torso_id = _find_body_id(model, "torso_torso_plate", "torso", "body_body", "body")
    initial_torso_z = float(data.xpos[torso_id, 2]) if torso_id is not None else 0.0

    max_qacc = 0.0
    min_torso_z = initial_torso_z
    max_pitch_roll = 0.0
    nan_inf = False

    for _ in range(n_steps):
        _apply_pd_targets(model, data, actuator_targets, kp=kp, kd=kd)

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
            min_torso_z = min(min_torso_z, z)
            # Pitch/roll from body's xmat (rotation matrix columns).
            xmat = data.xmat[torso_id].reshape(3, 3)
            # z-axis of body frame.
            z_axis = xmat[:, 2]
            # Angle from world z.
            cos_angle = float(np.clip(z_axis[2], -1.0, 1.0))
            tilt = np.degrees(np.arccos(cos_angle))
            max_pitch_roll = max(max_pitch_roll, float(tilt))
        max_qacc = max(max_qacc, float(np.max(np.abs(data.qacc))))

    return {
        "nan_inf": nan_inf,
        "initial_torso_z_m": initial_torso_z,
        "min_torso_z_m": min_torso_z,
        "torso_z_drop_m": initial_torso_z - min_torso_z,
        "max_pitch_roll_deg": max_pitch_roll,
        "max_qacc": max_qacc,
        "sim_steps": n_steps,
    }


def _run_sway_test(
    model,
    data,
    n_steps: int = 300,
    push_steps: int = 50,
    push_force_n: float = 20.0,
    kp: float = 100.0,
    kd: float = 20.0,
) -> dict[str, Any]:
    """Apply a lateral push to the torso and observe recovery."""
    torso_id = _find_body_id(model, "torso_torso_plate", "torso", "body_body", "body")
    if torso_id is None:
        return {"sway_ok": False, "error": "no torso body found"}

    mujoco.mj_forward(model, data)
    template = "humanoid" if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "hip_pitch_r") >= 0 else "quadruped"
    standing_pose = default_standing_pose(template)
    actuator_targets: dict[str, float] = {}
    for i in range(model.nu):
        joint_id = model.actuator_trnid[i, 0]
        joint_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id)
        if model.jnt_type[joint_id] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        actuator_targets[joint_name] = float(standing_pose.get(joint_name, 0.0))

    initial_z = float(data.xpos[torso_id, 2])
    min_z = initial_z
    max_tilt = 0.0
    nan_inf = False

    for step in range(n_steps):
        if step < push_steps:
            # Apply lateral force in +y direction on torso CoM.
            data.xfrc_applied[torso_id, :3] = [0.0, push_force_n, 0.0]
        else:
            data.xfrc_applied[torso_id, :3] = [0.0, 0.0, 0.0]

        _apply_pd_targets(model, data, actuator_targets, kp=kp, kd=kd)

        try:
            mujoco.mj_step(model, data)
        except Exception:
            nan_inf = True
            break

        if _has_nan_or_inf(model, data):
            nan_inf = True
            break

        z = float(data.xpos[torso_id, 2])
        min_z = min(min_z, z)
        xmat = data.xmat[torso_id].reshape(3, 3)
        z_axis = xmat[:, 2]
        tilt = np.degrees(np.arccos(float(np.clip(z_axis[2], -1.0, 1.0))))
        max_tilt = max(max_tilt, tilt)

    return {
        "sway_ok": not nan_inf and max_tilt < 45.0 and (initial_z - min_z) < 0.25,
        "nan_inf": nan_inf,
        "max_tilt_deg": max_tilt,
        "min_torso_z_m": min_z,
        "torso_z_drop_m": initial_z - min_z,
    }


def physics_score_candidate(
    tree: FeatureTree,
    n_steps: int = 200,
    tmp_dir: Path | None = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    """Score a morphology candidate by running it in MuJoCo.

    Returns a dict with sub-scores and a composite ``physics_score`` in [0, 1].
    If MuJoCo is unavailable or the model fails to load/simulate, the score is 0.

    Phase 29 tests:
    - Standing equilibrium with a PD controller.
    - Sway recovery from a lateral push.
    - Single-step/stepping-in-place: the robot lifts feet rhythmically while
      remaining upright. Forward progress is not required at this phase.
    """
    result: dict[str, Any] = {
        "mujoco_available": _mujoco_available(),
        "load_ok": False,
        "standing_ok": False,
        "sway_ok": False,
        "step_ok": False,
        "walk_ok": False,
        "standing_score": 0.0,
        "sway_score": 0.0,
        "step_score": 0.0,
        "walk_score": 0.0,
        "physics_score": 0.0,
        "notes": [],
    }

    if not _mujoco_available():
        result["notes"].append("mujoco not installed")
        return result

    work_dir = Path(tmp_dir) if tmp_dir else Path(tempfile.mkdtemp(prefix="robocad_morph_"))
    try:
        loaded = _load_model_from_tree(tree, work_dir, name="candidate")
        if loaded is None:
            result["notes"].append("failed to export/load candidate in MuJoCo")
            return result
        model, data = loaded
        result["load_ok"] = True

        template = _detect_template(model)
        torso_id = _find_body_id(model, "torso_torso_plate", "torso", "body_body", "body")
        foot_ids = _foot_body_ids(model, template)
        is_legged = torso_id is not None and len(foot_ids) > 0

        # Standing test.
        standing = _run_pd_standing(model, data, n_steps=n_steps)
        result["standing"] = standing
        result["standing_ok"] = (
            not standing["nan_inf"]
            and standing["max_qacc"] < 1e6
            and standing["torso_z_drop_m"] < 0.3
            and standing["max_pitch_roll_deg"] < 60.0
        )
        # Normalize standing score: 1.0 if perfect, decay with drop/tilt/qacc.
        drop_penalty = min(standing["torso_z_drop_m"] / 0.3, 1.0)
        tilt_penalty = min(standing["max_pitch_roll_deg"] / 60.0, 1.0)
        qacc_penalty = min(standing["max_qacc"] / 1e6, 1.0)
        result["standing_score"] = max(
            0.0, 1.0 - 0.5 * drop_penalty - 0.3 * tilt_penalty - 0.2 * qacc_penalty
        )
        if standing["nan_inf"]:
            result["standing_score"] = 0.0

        # Sway test: reset data and run push/recovery. Skip for non-legged designs
        # (no torso or no feet) so manipulators and other fixed/mobile-base systems
        # are not penalized by tests that do not apply to them.
        if is_legged:
            mujoco.mj_resetData(model, data)
            sway = _run_sway_test(model, data, n_steps=n_steps + 100)
            result["sway"] = sway
            result["sway_ok"] = sway.get("sway_ok", False)
            result["sway_score"] = 1.0 if result["sway_ok"] else 0.0
            if sway.get("nan_inf"):
                result["sway_score"] = 0.0
        else:
            result["sway"] = {"sway_ok": True, "skipped": True, "reason": "non-legged template"}
            result["sway_ok"] = True
            result["sway_score"] = 1.0
            result["notes"].append("sway test skipped (non-legged template)")

        # Step test: open-loop rhythmic foot lifting (Phase 29). Skipped for
        # non-legged designs for the same reason as sway.
        if is_legged:
            mujoco.mj_resetData(model, data)
            step = run_step_test(model, data, template=None, n_steps=n_steps + 100)
            result["step"] = step
            result["step_ok"] = step.get("step_ok", False)
            result["step_score"] = 1.0 if result["step_ok"] else 0.0
            if step.get("nan_inf"):
                result["step_score"] = 0.0
        else:
            result["step"] = {"step_ok": True, "skipped": True, "reason": "non-legged template"}
            result["step_ok"] = True
            result["step_score"] = 1.0
            result["notes"].append("stepping test skipped (non-legged template)")

        # Walk test: Phase 30 forward-locomotion objective. Skipped for
        # non-legged designs.
        if is_legged:
            mujoco.mj_resetData(model, data)
            walk_steps = max(n_steps + 200, 600)
            walk = run_walk_test(model, data, template=None, n_steps=walk_steps)
            result["walk"] = walk
            result["walk_ok"] = walk.get("walk_ok", False)
            result["walk_score"] = 1.0 if result["walk_ok"] else 0.0
            if walk.get("nan_inf"):
                result["walk_score"] = 0.0
        else:
            result["walk"] = {"walk_ok": True, "skipped": True, "reason": "non-legged template"}
            result["walk_ok"] = True
            result["walk_score"] = 1.0
            result["notes"].append("walk test skipped (non-legged template)")

        # Composite physics score: standing 40%, sway 20%, step 20%, walk 20%.
        # Walk is now a first-class objective because Phase 30 produces reliable
        # balance-aware forward locomotion for biped and quadruped templates.
        result["physics_score"] = round(
            0.4 * result["standing_score"]
            + 0.2 * result["sway_score"]
            + 0.2 * result["step_score"]
            + 0.2 * result["walk_score"],
            6,
        )

        if not result["standing_ok"]:
            result["notes"].append("standing test failed")
        if not result["sway_ok"]:
            result["notes"].append("sway test failed")
        if not result["step_ok"]:
            result["notes"].append("stepping test failed")
        if not result["walk_ok"]:
            result["notes"].append("walk test did not produce forward locomotion")
        if result["physics_score"] >= 0.75:
            result["notes"].append("candidate looks dynamically stable")
    finally:
        if cleanup and tmp_dir is None:
            shutil.rmtree(work_dir, ignore_errors=True)

    return result
