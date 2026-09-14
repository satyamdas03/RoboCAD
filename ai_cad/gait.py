"""Simple parameterized gait/stepping tests for RoboCAD legged templates.

Provides deterministic open-loop trajectories for biped humanoid and quadruped
skeletons exported to MuJoCo. Phase 29 uses a "stepping" test (robot lifts feet
rhythmically while staying upright); Phase 30 will build on this for forward
locomotion.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    import mujoco
except Exception:  # pragma: no cover - exercised only where mujoco is installed.
    mujoco = None


@dataclass
class GaitParams:
    """Parameters for an open-loop stepping/walking gait."""

    step_length_m: float = 0.10
    step_height_m: float = 0.03
    step_period_s: float = 1.2
    duty_factor: float = 0.75
    hip_swing_rad: float = 0.20
    knee_lift_rad: float = 0.40
    ankle_comp_rad: float = 0.10
    arm_swing_rad: float = 0.15
    abduction_rad: float = 0.0
    forward_bias_rad: float = 0.0


# Quadruped leg suffixes in MuJoCo naming convention.
_QUADRUPED_LEG_SUFFIXES = ["fl", "fr", "rl", "rr"]


def _swing_phase(phase: float, duty: float, offset: float) -> float | None:
    """Return normalized swing progress [0,1] for a leg, or None if in stance."""
    p = (phase + offset) % 1.0
    if p < duty:
        return None  # stance
    return (p - duty) / (1.0 - duty)


def _humanoid_leg_targets(
    phase: float,
    params: GaitParams,
    side: str,
    opposite_offset: float = 0.5,
) -> dict[str, float]:
    """Return target radians for one humanoid leg at given gait phase."""
    offset = 0.0 if side == "l" else opposite_offset
    swing = _swing_phase(phase, params.duty_factor, offset)

    targets: dict[str, float] = {}
    prefix = f"hip_pitch_{side}"
    knee = f"knee_{side}"
    ankle = f"ankle_{side}"

    if swing is None:
        # Stance: slight hip extension, nearly straight knee, neutral ankle.
        targets[prefix] = -0.03 + params.forward_bias_rad
        targets[knee] = 0.03
        targets[ankle] = 0.0
    else:
        # Swing: lift foot, move forward, then extend.
        # Hip pitch: start slightly back, swing forward through mid, then place.
        targets[prefix] = params.hip_swing_rad * math.sin(math.pi * (swing - 0.3)) + params.forward_bias_rad
        # Knee: bend in first half to lift foot, extend in second half.
        if swing < 0.5:
            targets[knee] = params.knee_lift_rad * math.sin(math.pi * 2.0 * swing)
        else:
            targets[knee] = params.knee_lift_rad * (1.0 - (swing - 0.5) * 2.0)
        # Ankle: dorsiflex early, plantarflex late.
        targets[ankle] = params.ankle_comp_rad * (0.5 - swing)

    return targets


def _humanoid_arm_targets(
    phase: float,
    params: GaitParams,
    side: str,
    opposite_offset: float = 0.5,
) -> dict[str, float]:
    """Return counter-swing arm targets."""
    offset = opposite_offset if side == "l" else 0.0
    swing = _swing_phase(phase, params.duty_factor, offset)
    targets: dict[str, float] = {}
    if swing is None:
        targets[f"shoulder_{side}"] = 0.0
        targets[f"elbow_{side}"] = -0.1
    else:
        targets[f"shoulder_{side}"] = params.arm_swing_rad * math.sin(math.pi * swing)
        targets[f"elbow_{side}"] = -0.1 - 0.15 * abs(math.sin(math.pi * swing))
    return targets


def humanoid_gait_targets(phase: float, params: GaitParams | None = None) -> dict[str, float]:
    """Return target joint positions (radians) for a humanoid at gait phase [0,1]."""
    params = params or GaitParams()
    targets: dict[str, float] = {}
    for side in ("l", "r"):
        targets.update(_humanoid_leg_targets(phase, params, side))
        targets.update(_humanoid_arm_targets(phase, params, side))
    return targets


def _quadruped_leg_targets(
    phase: float,
    params: GaitParams,
    suffix: str,
    gait_style: str,
) -> dict[str, float]:
    """Return targets for one quadruped leg at gait phase."""
    if gait_style == "wave":
        # Wave/crawl: one leg swings at a time in FL, FR, RL, RR order.
        order = {"fl": 0.0, "fr": 0.25, "rl": 0.5, "rr": 0.75}
        offset = order.get(suffix, 0.0)
        # Use a smaller duty factor so each leg has a brief swing.
        effective_duty = 0.75
    else:
        # Trot: diagonal pairs in phase. FL+RR vs FR+RL.
        pair_a = {"fl", "rr"}
        offset = 0.0 if suffix in pair_a else 0.5
        effective_duty = params.duty_factor

    swing = _swing_phase(phase, effective_duty, offset)

    targets: dict[str, float] = {}
    hip_pitch = f"hip_pitch_{suffix}"
    hip_abd = f"hip_abd_{suffix}"
    knee = f"knee_{suffix}"
    ankle = f"ankle_{suffix}"

    if swing is None:
        targets[hip_pitch] = params.forward_bias_rad
        targets[hip_abd] = 0.0
        targets[knee] = 0.03
        targets[ankle] = 0.0
    else:
        targets[hip_pitch] = params.hip_swing_rad * math.sin(math.pi * (swing - 0.3)) + params.forward_bias_rad
        targets[hip_abd] = params.abduction_rad * (1.0 if "l" in suffix else -1.0)
        if swing < 0.5:
            targets[knee] = params.knee_lift_rad * math.sin(math.pi * 2.0 * swing)
        else:
            targets[knee] = params.knee_lift_rad * (1.0 - (swing - 0.5) * 2.0)
        targets[ankle] = params.ankle_comp_rad * (0.5 - swing)

    return targets


def quadruped_gait_targets(
    phase: float,
    params: GaitParams | None = None,
    gait_style: str = "wave",
) -> dict[str, float]:
    """Return target joint positions (radians) for a quadruped at gait phase [0,1]."""
    params = params or GaitParams()
    targets: dict[str, float] = {}
    for suffix in _QUADRUPED_LEG_SUFFIXES:
        targets.update(_quadruped_leg_targets(phase, params, suffix, gait_style))
    return targets


def default_step_params(template: str) -> GaitParams:
    """Return conservative stepping parameters for a template.

    Phase 29 uses a tiny rhythmic motion to verify that a free-floating model
    can move its legs without immediately collapsing. Foot clearance is small
    but measurable; forward locomotion is intentionally not required.
    """
    if template == "humanoid":
        return GaitParams(
            step_length_m=0.01,
            step_height_m=0.01,
            step_period_s=2.4,
            duty_factor=0.90,
            hip_swing_rad=0.03,
            knee_lift_rad=0.08,
            ankle_comp_rad=0.02,
            arm_swing_rad=0.03,
        )
    if template == "quadruped":
        return GaitParams(
            step_length_m=0.005,
            step_height_m=0.005,
            step_period_s=2.4,
            duty_factor=0.92,
            hip_swing_rad=0.02,
            knee_lift_rad=0.05,
            ankle_comp_rad=0.01,
            abduction_rad=0.0,
        )
    return GaitParams()


def default_walk_params(template: str) -> GaitParams:
    """Return more aggressive walking parameters for Phase 30.

    The same gait generator is used, but with larger motion and a forward hip
    bias so the robot attempts to make forward progress. The balance controller
    in Phase 30 will refine this so the gait is stable.
    """
    if template == "humanoid":
        return GaitParams(
            step_length_m=0.08,
            step_height_m=0.03,
            step_period_s=1.2,
            duty_factor=0.75,
            hip_swing_rad=0.15,
            knee_lift_rad=0.30,
            ankle_comp_rad=0.05,
            arm_swing_rad=0.10,
            forward_bias_rad=0.06,
        )
    if template == "quadruped":
        return GaitParams(
            step_length_m=0.05,
            step_height_m=0.02,
            step_period_s=1.4,
            duty_factor=0.80,
            hip_swing_rad=0.08,
            knee_lift_rad=0.15,
            ankle_comp_rad=0.03,
            abduction_rad=0.0,
            forward_bias_rad=0.04,
        )
    return GaitParams()


def run_walk_test(
    model,
    data,
    template: str | None = None,
    n_steps: int = 600,
    params: GaitParams | None = None,
) -> dict[str, Any]:
    """Run an open-loop walking attempt and return locomotion metrics.

    Phase 30 uses this as the target objective for gait synthesis. Success
    requires measurable forward distance while staying upright.
    """
    if mujoco is None:
        return {"walk_ok": False, "error": "mujoco not installed"}

    template = template or _detect_template(model)
    params = params or default_walk_params(template)
    result = run_step_test(model, data, template=template, n_steps=n_steps, params=params)

    # Phase 30 interim success: moved forward at least 5 cm without collapse.
    walk_ok = (
        result["step_ok"]
        and result["forward_distance_m"] > 0.05
        and result["torso_z_drop_m"] < 0.10
        and result["max_pitch_roll_deg"] < 20.0
    )
    result["walk_ok"] = walk_ok
    result["walk_distance_m"] = result["forward_distance_m"]
    return result


def _body_id(model, *candidates: str) -> int | None:
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


def _foot_body_ids(model, template: str) -> list[int]:
    """Return MuJoCo body ids that look like feet."""
    ids: list[int] = []
    if mujoco is None:
        return ids
    for i in range(model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i)
        if name is None:
            continue
        if template == "humanoid" and "foot" in name:
            ids.append(i)
        elif template == "quadruped" and "foot" in name:
            ids.append(i)
    return ids


def _apply_pd_targets(
    model,
    data,
    targets: dict[str, float],
    kp: float = 80.0,
    kd: float = 16.0,
    untracked_kp: float = 40.0,
) -> None:
    """Apply PD torques so each actuator tracks its joint target.

    Untracked joints get a light restoring torque to zero to prevent drift.
    """
    if mujoco is None:
        return
    data.ctrl[:] = 0.0
    for i in range(model.nu):
        joint_id = model.actuator_trnid[i, 0]
        joint_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id)
        if model.jnt_type[joint_id] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        qpos_addr = model.jnt_qposadr[joint_id]
        qvel_addr = model.jnt_dofadr[joint_id]
        if joint_name in targets:
            target = float(targets[joint_name])
            pos_error = float(data.qpos[qpos_addr] - target)
            gain = kp
        else:
            pos_error = float(data.qpos[qpos_addr])
            gain = untracked_kp
        vel = float(data.qvel[qvel_addr])
        data.ctrl[i] = -gain * pos_error - kd * vel


def _has_nan_or_inf(model, data) -> bool:
    """Return True if any simulation state contains NaN or Inf."""
    arrays = [data.qpos, data.qvel, data.qacc]
    if hasattr(data, "xfrc_applied"):
        arrays.append(data.xfrc_applied)
    for arr in arrays:
        if np.isnan(arr).any() or np.isinf(arr).any():
            return True
    return False


def _detect_template(model, default: str = "humanoid") -> str:
    """Infer template from MuJoCo body/joint names."""
    if mujoco is None:
        return default
    names: set[str] = set()
    for i in range(model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i)
        if name is not None:
            names.add(name)
    for i in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
        if name is not None:
            names.add(name)
    # Humanoid has a single right hip pitch joint; quadruped joints use FL/FR/RL/RR.
    if "hip_pitch_r" in names:
        return "humanoid"
    if "hip_pitch_fr" in names or "foot_fl_foot_fl" in names:
        return "quadruped"
    return default


def run_step_test(
    model,
    data,
    template: str | None = None,
    n_steps: int = 400,
    params: GaitParams | None = None,
) -> dict[str, Any]:
    """Run an open-loop stepping test in MuJoCo and return step metrics.

    The robot is settled, then a periodic leg-lifting trajectory is applied.
    Success means the robot stayed upright and lifted at least one foot.

    Args:
        model: loaded MjModel.
        data: MjData.
        template: "humanoid", "quadruped", or None to auto-detect.
        n_steps: simulation steps to run.
        params: optional gait parameters; defaults to template-specific values.

    Returns:
        Dict with step_ok, foot_clearance_m, forward_distance_m,
        max_pitch_roll_deg, nan_inf, etc.
    """
    if mujoco is None:
        return {"step_ok": False, "error": "mujoco not installed"}

    template = template or _detect_template(model)
    params = params or default_step_params(template)

    timestep = float(model.opt.timestep)
    period_steps = max(int(params.step_period_s / timestep), 1)

    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)

    torso_id = _body_id(model, "torso_torso_plate", "torso", "body_body", "body")
    foot_ids = _foot_body_ids(model, template)

    # Phase 1: settle into standing balance.
    # Use a full 80-step settle when possible; a short settle destabilizes the
    # free-floating model before the gait begins.
    settle_steps = min(80, n_steps) if n_steps >= 80 else n_steps // 2
    for _ in range(settle_steps):
        _apply_pd_targets(model, data, {}, kp=60.0, kd=16.0)
        try:
            mujoco.mj_step(model, data)
        except Exception:
            break
        if _has_nan_or_inf(model, data):
            break

    mujoco.mj_forward(model, data)
    initial_x = float(data.xpos[torso_id, 0]) if torso_id is not None else 0.0
    initial_z = float(data.xpos[torso_id, 2]) if torso_id is not None else 0.0
    min_z = initial_z
    max_pitch_roll = 0.0
    nan_inf = False
    initial_foot_z: dict[int, float] = {}
    for fid in foot_ids:
        initial_foot_z[fid] = float(data.xpos[fid, 2])
    max_foot_clearance = 0.0

    # Use gentler gains for the stepping phase so the free-floating robot is
    # less likely to be kicked over by aggressive joint torques.
    step_kp = 60.0
    step_kd = 12.0

    for step in range(n_steps):
        phase = (step % period_steps) / period_steps
        if template == "humanoid":
            targets = humanoid_gait_targets(phase, params)
        elif template == "quadruped":
            targets = quadruped_gait_targets(phase, params, gait_style="wave")
        else:
            targets = {}

        _apply_pd_targets(model, data, targets, kp=step_kp, kd=step_kd, untracked_kp=20.0)

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
            z_axis = xmat[:, 2]
            tilt = math.degrees(math.acos(float(np.clip(z_axis[2], -1.0, 1.0))))
            max_pitch_roll = max(max_pitch_roll, tilt)

        # Measure foot clearance relative to the foot's initial height.
        for fid, iz in initial_foot_z.items():
            clearance = float(data.xpos[fid, 2]) - iz
            max_foot_clearance = max(max_foot_clearance, clearance)

    final_x = float(data.xpos[torso_id, 0]) if torso_id is not None else initial_x
    forward_distance = final_x - initial_x
    z_drop = initial_z - min_z

    # Phase 29 success: rhythmic leg motion that lifts a foot without collapsing.
    min_clearance = 0.005 if template == "humanoid" else 0.003
    step_ok = (
        not nan_inf
        and max_foot_clearance > min_clearance
        and z_drop < 0.30
        and max_pitch_roll < 45.0
    )

    return {
        "template": template,
        "step_ok": step_ok,
        "nan_inf": nan_inf,
        "forward_distance_m": forward_distance,
        "initial_x_m": initial_x,
        "initial_z_m": initial_z,
        "min_torso_z_m": min_z,
        "torso_z_drop_m": z_drop,
        "max_pitch_roll_deg": max_pitch_roll,
        "max_foot_clearance_m": max_foot_clearance,
        "sim_steps": n_steps,
    }
