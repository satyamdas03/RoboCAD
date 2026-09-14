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
from ai_cad.gait import default_step_params, run_step_test
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

    # Add freejoint to the first body under worldbody so the robot is free-floating.
    worldbody = root.find("worldbody")
    if worldbody is not None:
        first_body = worldbody.find("body")
        if first_body is not None and first_body.find("freejoint") is None:
            # Insert freejoint before inertial/geom/joint so MuJoCo is happy.
            ET.SubElement(first_body, "freejoint")

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

    # Map actuators to joint dofs. In a simple MJCF with one actuator per joint,
    # data.ctrl order matches the actuator order, which matches the joint order
    # for hinge/slide joints. We apply a conservative damping/restore torque.
    torso_id = _find_body_id(model, "torso_torso_plate", "torso")
    initial_torso_z = float(data.xpos[torso_id, 2]) if torso_id is not None else 0.0

    max_qacc = 0.0
    min_torso_z = initial_torso_z
    max_pitch_roll = 0.0
    nan_inf = False

    for _ in range(n_steps):
        # Simple PD on joint velocities/positions via ctrl.
        # data.ctrl is per actuator. Use gear=1 motors; torque = ctrl.
        # This is a passive standing controller: bring every joint to zero.
        for i in range(model.nu):
            # Find the actuator's joint id.
            actuator_id = i
            joint_id = model.actuator_trnid[actuator_id, 0]
            qpos_addr = model.jnt_qposadr[joint_id]
            qvel_addr = model.jnt_dofadr[joint_id]
            joint_type = model.jnt_type[joint_id]
            if joint_type == mujoco.mjtJoint.mjJNT_FREE:
                continue
            pos_error = float(data.qpos[qpos_addr] - target_positions[qvel_addr])
            vel = float(data.qvel[qvel_addr])
            data.ctrl[i] = -kp * pos_error - kd * vel

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
    torso_id = _find_body_id(model, "torso_torso_plate", "torso")
    if torso_id is None:
        return {"sway_ok": False, "error": "no torso body found"}

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

        for i in range(model.nu):
            actuator_id = i
            joint_id = model.actuator_trnid[actuator_id, 0]
            qpos_addr = model.jnt_qposadr[joint_id]
            qvel_addr = model.jnt_dofadr[joint_id]
            if model.jnt_type[joint_id] == mujoco.mjtJoint.mjJNT_FREE:
                continue
            pos_error = float(data.qpos[qpos_addr])
            vel = float(data.qvel[qvel_addr])
            data.ctrl[i] = -kp * pos_error - kd * vel

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
        "standing_score": 0.0,
        "sway_score": 0.0,
        "step_score": 0.0,
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

        # Sway test: reset data and run push/recovery.
        mujoco.mj_resetData(model, data)
        sway = _run_sway_test(model, data, n_steps=n_steps + 100)
        result["sway"] = sway
        result["sway_ok"] = sway.get("sway_ok", False)
        result["sway_score"] = 1.0 if result["sway_ok"] else 0.0
        if sway.get("nan_inf"):
            result["sway_score"] = 0.0

        # Step test: open-loop rhythmic foot lifting (Phase 29).
        mujoco.mj_resetData(model, data)
        step = run_step_test(model, data, template=None, n_steps=n_steps + 100)
        result["step"] = step
        result["step_ok"] = step.get("step_ok", False)
        result["step_score"] = 1.0 if result["step_ok"] else 0.0
        if step.get("nan_inf"):
            result["step_score"] = 0.0

        # Composite physics score: standing 50%, sway 25%, step 25%.
        result["physics_score"] = round(
            0.5 * result["standing_score"]
            + 0.25 * result["sway_score"]
            + 0.25 * result["step_score"],
            6,
        )

        if not result["standing_ok"]:
            result["notes"].append("standing test failed")
        if not result["sway_ok"]:
            result["notes"].append("sway test failed")
        if not result["step_ok"]:
            result["notes"].append("stepping test failed")
        if result["physics_score"] >= 0.75:
            result["notes"].append("candidate looks dynamically stable")
    finally:
        if cleanup and tmp_dir is None:
            shutil.rmtree(work_dir, ignore_errors=True)

    return result
