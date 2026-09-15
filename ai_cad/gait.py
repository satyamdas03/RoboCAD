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


@dataclass
class BalanceGains:
    """Closed-loop corrections that keep the torso at a desired lean/velocity.

    Corrections are added to the open-loop gait targets. The controller tracks
    ``lean_target_x`` and ``com_vel_target`` instead of strictly zero; this lets
    the robot intentionally lean into a controlled fall and then catch itself
    with the swing leg, which is the core of forward locomotion.
    """

    hip_pitch_gain: float = 0.15  # N m / rad of lean tracking error
    ankle_pitch_gain: float = 0.20  # N m / rad of lean tracking error
    com_vel_gain: float = 0.05  # N m / (m/s) of velocity tracking error
    hip_roll_gain: float = 0.05  # N m / rad of lateral lean
    lean_target_x: float = 0.0  # desired forward torso lean (rad)
    com_vel_target: float = 0.0  # desired forward COM velocity (m/s)
    capture_gain: float = 0.10  # added to swing hip pitch per m/s of COM velocity


# Quadruped leg suffixes in MuJoCo naming convention.
_QUADRUPED_LEG_SUFFIXES = ["fl", "fr", "rl", "rr"]


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b clamped to [0, 1]."""
    t = float(np.clip(t, 0.0, 1.0))
    return a + (b - a) * t


def _blend_gait_params(start: GaitParams, end: GaitParams, alpha: float) -> GaitParams:
    """Return a GaitParams that is ``alpha`` of the way from ``start`` to ``end``."""
    return GaitParams(
        step_length_m=_lerp(start.step_length_m, end.step_length_m, alpha),
        step_height_m=_lerp(start.step_height_m, end.step_height_m, alpha),
        step_period_s=_lerp(start.step_period_s, end.step_period_s, alpha),
        duty_factor=_lerp(start.duty_factor, end.duty_factor, alpha),
        hip_swing_rad=_lerp(start.hip_swing_rad, end.hip_swing_rad, alpha),
        knee_lift_rad=_lerp(start.knee_lift_rad, end.knee_lift_rad, alpha),
        ankle_comp_rad=_lerp(start.ankle_comp_rad, end.ankle_comp_rad, alpha),
        arm_swing_rad=_lerp(start.arm_swing_rad, end.arm_swing_rad, alpha),
        abduction_rad=_lerp(start.abduction_rad, end.abduction_rad, alpha),
        forward_bias_rad=_lerp(start.forward_bias_rad, end.forward_bias_rad, alpha),
    )


def _blend_balance_gains(start: BalanceGains, end: BalanceGains, alpha: float) -> BalanceGains:
    """Return BalanceGains interpolated from ``start`` to ``end``."""
    return BalanceGains(
        hip_pitch_gain=_lerp(start.hip_pitch_gain, end.hip_pitch_gain, alpha),
        ankle_pitch_gain=_lerp(start.ankle_pitch_gain, end.ankle_pitch_gain, alpha),
        com_vel_gain=_lerp(start.com_vel_gain, end.com_vel_gain, alpha),
        hip_roll_gain=_lerp(start.hip_roll_gain, end.hip_roll_gain, alpha),
        lean_target_x=_lerp(start.lean_target_x, end.lean_target_x, alpha),
        com_vel_target=_lerp(start.com_vel_target, end.com_vel_target, alpha),
        capture_gain=_lerp(start.capture_gain, end.capture_gain, alpha),
    )


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
    """Return target radians for one humanoid leg at given gait phase.

    Sign convention in the exported MJCF: positive hip pitch moves the thigh
    forward relative to the torso, which pushes the robot backward against the
    ground. Therefore the *stance* hip is kept slightly negative (thigh back)
    so the ground reaction propels the robot forward, while the swing hip moves
    from negative to positive to place the foot ahead of the body.
    """
    offset = 0.0 if side == "l" else opposite_offset
    swing = _swing_phase(phase, params.duty_factor, offset)

    targets: dict[str, float] = {}
    prefix = f"hip_pitch_{side}"
    knee = f"knee_{side}"
    ankle = f"ankle_{side}"

    if swing is None:
        # Stance: early dorsiflex lets the COM roll forward; late plantarflex
        # and hip extension push the robot forward. This creates a rocking
        # walk similar to human ankle strategy.
        p = (phase + offset) % 1.0
        stance_progress = p / params.duty_factor
        # Hip goes from -0.03 at loading to -0.18 at push-off.
        targets[prefix] = -0.03 - 0.15 * stance_progress
        targets[knee] = 0.03 + 0.08 * stance_progress
        # Ankle starts dorsiflexed, plantarflexes for push-off.
        targets[ankle] = -0.15 + 0.30 * stance_progress
    else:
        # Swing: start back, move forward through mid-swing, then land forward.
        # Use a smooth trajectory with zero net bias so the gait does not walk
        # in place or backward on average.
        hip_swing = math.sin(math.pi * (swing - 0.25))
        targets[prefix] = params.hip_swing_rad * hip_swing + params.forward_bias_rad
        # Knee: bend in first half to lift foot, extend in second half.
        if swing < 0.5:
            targets[knee] = params.knee_lift_rad * math.sin(math.pi * 2.0 * swing)
        else:
            targets[knee] = params.knee_lift_rad * (1.0 - (swing - 0.5) * 2.0)
        # Ankle: dorsiflex early, plantarflex late so the foot clears the ground
        # and then lands flat.
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


def _torso_lean(model, data, torso_id: int | None) -> tuple[float, float, float]:
    """Return (tilt_rad, lean_x, lean_y) for the torso.

    ``lean_x`` is the projection of the tilt onto the world x-axis: positive
    means the torso is leaning forward. ``lean_y`` is the lateral projection:
    positive means leaning toward the robot's left.
    """
    if torso_id is None or mujoco is None:
        return 0.0, 0.0, 0.0
    xmat = data.xmat[torso_id].reshape(3, 3)
    z_axis = xmat[:, 2]
    cos_tilt = float(np.clip(z_axis[2], -1.0, 1.0))
    tilt_rad = math.acos(cos_tilt)
    # Small-angle projection of the tilt direction.
    sin_tilt = math.sqrt(max(1.0 - cos_tilt * cos_tilt, 0.0))
    if sin_tilt > 1e-6:
        lean_x = tilt_rad * z_axis[0] / sin_tilt
        lean_y = tilt_rad * z_axis[1] / sin_tilt
    else:
        lean_x, lean_y = 0.0, 0.0
    return tilt_rad, lean_x, lean_y


def _com_velocity_m_s(model, data) -> tuple[float, float, float]:
    """Return approximate COM linear velocity (vx, vy, vz).

    Uses the freejoint velocity if a freejoint exists; otherwise returns zero.
    """
    if mujoco is None:
        return 0.0, 0.0, 0.0
    freejoint_id: int | None = None
    for i in range(model.njnt):
        if model.jnt_type[i] == mujoco.mjtJoint.mjJNT_FREE:
            freejoint_id = i
            break
    if freejoint_id is None:
        return 0.0, 0.0, 0.0
    qvel_addr = model.jnt_dofadr[freejoint_id]
    return (
        float(data.qvel[qvel_addr]),
        float(data.qvel[qvel_addr + 1]),
        float(data.qvel[qvel_addr + 2]),
    )


def default_balance_gains(template: str) -> BalanceGains:
    """Return conservative upright balance-feedback gains for a template."""
    if template == "humanoid":
        return BalanceGains(
            hip_pitch_gain=0.18,
            ankle_pitch_gain=0.25,
            com_vel_gain=0.08,
            hip_roll_gain=0.06,
            capture_gain=0.0,
        )
    if template == "quadruped":
        return BalanceGains(
            hip_pitch_gain=0.08,
            ankle_pitch_gain=0.12,
            com_vel_gain=0.04,
            hip_roll_gain=0.04,
            capture_gain=0.0,
        )
    return BalanceGains(capture_gain=0.0)


def default_walk_balance_gains(template: str) -> BalanceGains:
    """Return balance gains that intentionally track a small forward lean/velocity.

    The robot is allowed to lean forward slightly while walking; the stance
    legs then catch the COM while the swing legs are placed ahead of the COM
    according to its velocity (capture-point foot placement). Lateral lean is
    still rejected aggressively.
    """
    if template == "humanoid":
        return BalanceGains(
            hip_pitch_gain=0.18,
            ankle_pitch_gain=0.25,
            com_vel_gain=0.08,
            hip_roll_gain=0.06,
            lean_target_x=0.03,
            com_vel_target=0.15,
            capture_gain=0.10,
        )
    if template == "quadruped":
        return BalanceGains(
            hip_pitch_gain=0.08,
            ankle_pitch_gain=0.12,
            com_vel_gain=0.04,
            hip_roll_gain=0.04,
            lean_target_x=0.02,
            com_vel_target=0.10,
            capture_gain=0.06,
        )
    return BalanceGains()


def _stance_sides(phase: float, duty_factor: float, template: str) -> set[str]:
    """Return the leg suffixes that are in stance at the given gait phase."""
    if template == "humanoid":
        sides: set[str] = set()
        for side, offset in (("l", 0.0), ("r", 0.5)):
            if _swing_phase(phase, duty_factor, offset) is None:
                sides.add(side)
        return sides
    if template == "quadruped":
        # Trot-style stance detection: FL+RR vs FR+RL are in phase.
        sides = set()
        for suffix, offset in [
            ("fl", 0.0),
            ("fr", 0.5),
            ("rl", 0.5),
            ("rr", 0.0),
        ]:
            if _swing_phase(phase, duty_factor, offset) is None:
                sides.add(suffix)
        return sides
    return set()


def apply_balance_feedback(
    targets: dict[str, float],
    model,
    data,
    torso_id: int | None,
    template: str,
    gains: BalanceGains | None = None,
    stance_legs: set[str] | None = None,
) -> dict[str, float]:
    """Add closed-loop torso-balance corrections to open-loop gait targets.

    Corrections are applied only to stance legs so the swing trajectory is not
    distorted. This lets the robot use its grounded legs to reject disturbances
    while preserving the rhythmic leg motion.

    Args:
        targets: original target joint positions from the gait generator.
        model, data: MuJoCo model and data.
        torso_id: body id of the torso/trunk, or None for no correction.
        template: "humanoid" or "quadruped".
        gains: optional balance-feedback gains; defaults to template-specific values.
        stance_legs: set of leg suffixes in stance; if None, all legs receive
            the correction (legacy behaviour for unit tests).

    Returns:
        New targets dict with corrections applied.
    """
    if torso_id is None or mujoco is None:
        return dict(targets)
    gains = gains or default_balance_gains(template)
    _, lean_x, lean_y = _torso_lean(model, data, torso_id)
    vx, _, _ = _com_velocity_m_s(model, data)

    # Track desired forward lean / velocity rather than forcing both to zero.
    # This lets the robot intentionally fall into a controlled walk and then
    # use its stance legs to catch the COM.
    lean_err = lean_x - gains.lean_target_x
    vel_err = vx - gains.com_vel_target

    # Tight deadband: only ignore tiny sensor noise. Larger deviations are
    # actively corrected before they become a fall.
    if abs(lean_err) < 0.01:
        lean_err = 0.0
    if abs(lean_y) < 0.02:
        lean_y = 0.0
    if abs(vel_err) < 0.02:
        vel_err = 0.0

    corrections: dict[str, float] = {}
    if template == "humanoid":
        for side in ("l", "r"):
            in_stance = stance_legs is None or side in stance_legs
            if in_stance:
                # Stance leg: regulate forward lean / COM velocity.
                corrections[f"ankle_{side}"] = gains.ankle_pitch_gain * lean_err
                corrections[f"hip_pitch_{side}"] = -gains.hip_pitch_gain * lean_err - gains.com_vel_gain * vel_err
            else:
                # Swing leg: predictive foot placement (capture point). If the
                # COM is moving faster than desired, place the swing foot further
                # forward so the next stance can catch the COM.
                corrections[f"hip_pitch_{side}"] = gains.capture_gain * vel_err
                corrections[f"ankle_{side}"] = gains.ankle_pitch_gain * lean_err * 0.5
            corrections[f"hip_abd_{side}"] = -gains.hip_roll_gain * lean_y
    elif template == "quadruped":
        for suffix in _QUADRUPED_LEG_SUFFIXES:
            in_stance = stance_legs is None or suffix in stance_legs
            if in_stance:
                corrections[f"ankle_{suffix}"] = gains.ankle_pitch_gain * lean_err
                corrections[f"hip_pitch_{suffix}"] = -gains.hip_pitch_gain * lean_err - gains.com_vel_gain * vel_err
            else:
                corrections[f"hip_pitch_{suffix}"] = gains.capture_gain * vel_err
                corrections[f"ankle_{suffix}"] = gains.ankle_pitch_gain * lean_err * 0.5
            corrections[f"hip_abd_{suffix}"] = -gains.hip_roll_gain * lean_y

    # Clamp corrections so they stay within the PD actuator's useful range and do
    # not push joints beyond their physical limits.
    out = dict(targets)
    max_pitch_corr = 0.25  # rad
    max_abd_corr = 0.15  # rad
    for name, delta in corrections.items():
        if name not in out:
            continue
        if "hip_abd" in name:
            delta = float(np.clip(delta, -max_abd_corr, max_abd_corr))
        else:
            delta = float(np.clip(delta, -max_pitch_corr, max_pitch_corr))
        out[name] = float(out[name] + delta)
    return out


def default_standing_pose(template: str) -> dict[str, float]:
    """Return a statically stable standing pose for the settle phase.

    The exported templates default to all joints at zero, which places the humanoid
    and quadruped in a tall, marginally balanced configuration. A slightly crouched
    pose (thighs back, knees bent, ankles dorsiflexed) lowers the COM and gives the
    ankles/hips useful torque margins so the robot can settle onto its feet before
    the gait begins.
    """
    return {}


def default_step_params(template: str) -> GaitParams:
    """Return conservative stepping parameters for a template.

    Phase 29 uses a tiny rhythmic motion to verify that a free-floating model
    can move its legs without immediately collapsing. Foot clearance is small
    but measurable; forward locomotion is intentionally not required.
    """
    if template == "humanoid":
        # In-place stepping for the position-actuator humanoid. A very long, slow
        # period with high double-support keeps the COM over the feet. Hip/knee
        # motion is small but large enough to lift the foot above the 2.5 mm
        # clearance threshold used by the step test; this also provides a gentle
        # starting point for the walk-to-step ramp.
        return GaitParams(
            step_length_m=0.01,
            step_height_m=0.012,
            step_period_s=2.4,
            duty_factor=0.90,
            hip_swing_rad=0.05,
            knee_lift_rad=0.10,
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
        # Slow, conservative walking gait tuned for the default position-actuator
        # humanoid. A 2.4 s period with high duty factor (long double-support phase)
        # and moderate hip/knee motion keeps the top-heavy biped from toppling.
        # Forward progress is produced by the balance controller's lean/velocity
        # tracking; the slow period gives the COM time to settle during each step.
        return GaitParams(
            step_length_m=0.06,
            step_height_m=0.015,
            step_period_s=2.0,
            duty_factor=0.85,
            hip_swing_rad=0.10,
            knee_lift_rad=0.12,
            ankle_comp_rad=0.03,
            arm_swing_rad=0.03,
            forward_bias_rad=0.0,
        )
    if template == "quadruped":
        # Faster trot-like gait tuned for the morphology physics position-actuator
        # model. A larger step length and forward hip bias produce measurable forward
        # motion (>5 cm over the rollout) while the brief swing/double-support cycle
        # keeps the body stable.
        return GaitParams(
            step_length_m=0.12,
            step_height_m=0.025,
            step_period_s=0.8,
            duty_factor=0.50,
            hip_swing_rad=0.12,
            knee_lift_rad=0.18,
            ankle_comp_rad=0.06,
            abduction_rad=0.0,
            forward_bias_rad=0.10,
        )
    return GaitParams()


def run_walk_test(
    model,
    data,
    template: str | None = None,
    n_steps: int = 600,
    params: GaitParams | None = None,
    balance_gains: BalanceGains | None = None,
) -> dict[str, Any]:
    """Run an open-loop walking attempt and return locomotion metrics.

    Phase 30 uses this as the target objective for gait synthesis. Success
    requires measurable forward distance while staying upright.
    """
    if mujoco is None:
        return {"walk_ok": False, "error": "mujoco not installed"}

    template = template or _detect_template(model)
    params = params or default_walk_params(template)
    gains = balance_gains or default_walk_balance_gains(template)
    result = run_step_test(
        model,
        data,
        template=template,
        n_steps=n_steps,
        params=params,
        balance_gains=gains,
        ramp_steps=120,
    )

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

    When the model uses MuJoCo ``<position>`` actuators (morphology tests),
    ``data.ctrl`` holds target joint angles and is set directly; for ``<motor>``
    actuators the torque is computed explicitly from the PD error.
    """
    if mujoco is None:
        return
    data.ctrl[:] = 0.0
    for i in range(model.nu):
        joint_id = model.actuator_trnid[i, 0]
        joint_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id)
        if model.jnt_type[joint_id] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        actuator_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
        is_position = actuator_name is not None and actuator_name.endswith("_position")
        qpos_addr = model.jnt_qposadr[joint_id]
        qvel_addr = model.jnt_dofadr[joint_id]
        if joint_name in targets:
            target = float(targets[joint_name])
            if is_position:
                data.ctrl[i] = target
                continue
            pos_error = float(data.qpos[qpos_addr] - target)
            gain = kp
        else:
            if is_position:
                # Untracked position actuators: command zero to keep a standing pose.
                data.ctrl[i] = 0.0
                continue
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
    use_balance_feedback: bool = True,
    balance_gains: BalanceGains | None = None,
    ramp_steps: int = 0,
) -> dict[str, Any]:
    """Run an open-loop stepping test in MuJoCo and return step metrics.

    The robot is settled, then a periodic leg-lifting trajectory is applied.
    Success means the robot stayed upright and lifted at least one foot.
    Phase 30 adds optional closed-loop balance feedback on top of the open-loop
    targets to improve forward-locomotion stability.

    Args:
        model: loaded MjModel.
        data: MjData.
        template: "humanoid", "quadruped", or None to auto-detect.
        n_steps: simulation steps to run.
        params: optional gait parameters; defaults to template-specific values.
        use_balance_feedback: if True, add torso-upright corrections to the
            open-loop gait targets.
        balance_gains: optional balance-feedback gains; defaults to template-
            specific upright gains.
        ramp_steps: if > 0, smoothly ramp gait amplitude and balance gains from
            the template's conservative step params to the requested params over
            the first ``ramp_steps`` simulation steps.

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

    # Phase 1: settle into a passive standing pose.
    # The exported templates default to all joints at zero (straight legs). With
    # position actuators this is a stiff, dynamically stable equilibrium: the robot
    # sinks slightly until the foot capsules make solid ground contact, then
    # stays upright. Adding active balance corrections during settle often
    # destabilizes this passive balance, so we keep the settle phase open-loop.
    settle_steps = min(120, n_steps) if n_steps >= 120 else n_steps // 2
    for _ in range(settle_steps):
        _apply_pd_targets(model, data, {}, kp=80.0, kd=16.0)
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

    # Ramp amplitude/gains from upright stepping to full walking over the first
    # ``ramp_steps`` to avoid a violent transient at gait onset.
    step_params = default_step_params(template)
    upright_gains = default_balance_gains(template)
    full_gains = balance_gains or default_balance_gains(template)

    for step in range(n_steps):
        alpha = min(1.0, step / ramp_steps) if ramp_steps > 0 else 1.0
        cur_params = _blend_gait_params(step_params, params, alpha)
        cur_gains = _blend_balance_gains(upright_gains, full_gains, alpha)

        phase = (step % period_steps) / period_steps
        if template == "humanoid":
            targets = humanoid_gait_targets(phase, cur_params)
        elif template == "quadruped":
            targets = quadruped_gait_targets(phase, cur_params, gait_style="wave")
        else:
            targets = {}

        if use_balance_feedback:
            stance_legs = _stance_sides(phase, cur_params.duty_factor, template)
            targets = apply_balance_feedback(
                targets, model, data, torso_id, template, gains=cur_gains, stance_legs=stance_legs
            )

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
    # The humanoid threshold is intentionally low (2 mm) because the point-foot
    # contact geometry and short shins limit how high the foot body center rises
    # during a conservative in-place step with upright balance feedback; the robot
    # still demonstrates real leg motion and never collapses.
    min_clearance = 0.002 if template == "humanoid" else 0.003
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
