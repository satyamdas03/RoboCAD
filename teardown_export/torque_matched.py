"""P0: are the two models in the same physical pose when their torques are compared?

The v1 package reported peak torque 1.26 N m for the published 0.632 kg arm against 0.63 N m for the
compiled 0.902 kg arm. A heavier arm demanding less torque is the kind of number that is either a
finding or a bug, and the cheaper hypothesis is a bug: the two models were posed at the same JOINT
VECTOR, not the same physical pose, and the compiled model's zero pose differs from the published one
by roughly a quarter turn on three joints.

So this script does three things in the order that makes the answer checkable:

1. Apply the documented zero-pose conventions and report how far apart a world-frame jaw-tip point is
   between the two models at five timesteps. If that exceeds the documented residual, nothing after it
   means anything.
2. Recompute inverse-dynamics torque on both models at MATCHED poses, per joint, peak and RMS.
3. Report static gravity torque at three reference poses, which needs no trajectory and no timing.

Contacts are disabled on both, because the compiled hulls overlap at rest and their constraint forces
would otherwise appear as joint torque.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib

import numpy as np

# the conventions from docs/twin/so101/CONVENTIONS.md, base-first, applied to the compiled model
ZERO_POSE_OFFSETS_DEG = [-88.17, 90.29, -90.31, -0.15, 0.00]
GRIPPER_OFFSET_DEG = 0.0
BASE_TRANSLATION_MM = [38.74, 6.64, -2.86]


def _load(path: pathlib.Path):
    import mujoco

    path = path.resolve()
    cwd = os.getcwd()
    try:
        os.chdir(path.parent)
        model = mujoco.MjModel.from_xml_path(path.name)
    finally:
        os.chdir(cwd)
    # contacts AND joint limits: with the documented offsets applied, the compiled joint vector is
    # driven outside its own ranges, and limit constraints then contribute forces that look like
    # torque. That is a harness artefact, not a property of the robot.
    model.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_CONTACT)
    model.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_LIMIT)
    return model


def _tip_local(mujoco, model, body_name: str):
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    pts = []
    for geom in range(model.ngeom):
        if model.geom_bodyid[geom] != body:
            continue
        if model.geom_type[geom] != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        mesh = int(model.geom_dataid[geom])
        start, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
        verts = np.asarray(model.mesh_vert[start:start + count], dtype=float)
        pts.append((verts @ data.geom_xmat[geom].reshape(3, 3).T) + data.geom_xpos[geom])
    if not pts:
        return None
    world = np.vstack(pts).mean(axis=0)
    R = data.xmat[body].reshape(3, 3)
    return R.T @ (world - data.xpos[body])


def _trajectory(model, hz: int, seconds: float):
    """Joint-space trajectory and its derivatives, identical in shape for both models."""
    frames = int(seconds * hz)
    t = np.arange(frames) / hz
    q = np.zeros((frames, model.nq))
    qd = np.zeros((frames, model.nv))
    qdd = np.zeros((frames, model.nv))
    for j in range(model.njnt):
        lo, hi = model.jnt_range[j]
        if hi <= lo:
            lo, hi = -1.7, 1.7
        centre, span = (lo + hi) / 2.0, (hi - lo) / 2.0
        w = 2.0 * math.pi * (0.18 + 0.05 * j)
        q[:, j] = centre + span * 0.30 * np.sin(w * t)
        qd[:, j] = span * 0.30 * w * np.cos(w * t)
        qdd[:, j] = -span * 0.30 * w * w * np.sin(w * t)
    return q, qd, qdd


def _torque(mujoco, model, q, qd, qdd):
    data = mujoco.MjData(model)
    out = np.zeros((len(q), model.njnt))
    for i in range(len(q)):
        data.qpos[:] = q[i]
        data.qvel[:] = qd[i]
        # mj_forward first: mj_inverse reads the constraint and passive state that forward computes,
        # and calling it on an unforwarded data produced 71 N m of "gravity" on a 0.9 kg arm whose
        # own qfrc_bias is 0.34 N m. That is a harness bug, not a model finding.
        mujoco.mj_forward(model, data)
        data.qacc[:] = qdd[i]
        mujoco.mj_inverse(model, data)
        out[i] = data.qfrc_inverse[: model.njnt]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official", required=True)
    parser.add_argument("--compiled", required=True)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--hz", type=int, default=100)
    parser.add_argument("--out", default=None)
    parser.add_argument("--sign", type=float, default=1.0,
                        help="+1 or -1: which side the documented offsets shift")
    args = parser.parse_args()

    import mujoco

    official = _load(pathlib.Path(args.official))
    compiled = _load(pathlib.Path(args.compiled))
    if official.njnt != compiled.njnt:
        raise SystemExit("joint counts differ; nothing here is comparable")

    offsets = np.radians(np.array(ZERO_POSE_OFFSETS_DEG + [GRIPPER_OFFSET_DEG]))
    translation = np.array(BASE_TRANSLATION_MM) / 1000.0

    q_o, qd_o, qdd_o = _trajectory(official, args.hz, args.seconds)
    # the SAME physical motion: our joint vector is theirs plus the documented zero-pose offset
    q_c = q_o + args.sign * offsets
    qd_c, qdd_c = qd_o.copy(), qdd_o.copy()

    tip_o = _tip_local(mujoco, official, "moving_jaw_so101_v1")
    tip_c = _tip_local(mujoco, compiled, "moving_jaw_so101")
    body_o = mujoco.mj_name2id(official, mujoco.mjtObj.mjOBJ_BODY, "moving_jaw_so101_v1")
    body_c = mujoco.mj_name2id(compiled, mujoco.mjtObj.mjOBJ_BODY, "moving_jaw_so101")
    d_o, d_c = mujoco.MjData(official), mujoco.MjData(compiled)

    check_idx = np.linspace(0, len(q_o) - 1, 5).astype(int)
    pose_errors = []
    for i in check_idx:
        d_o.qpos[:] = q_o[i]; mujoco.mj_forward(official, d_o)
        d_c.qpos[:] = q_c[i]; mujoco.mj_forward(compiled, d_c)
        w_o = d_o.xmat[body_o].reshape(3, 3) @ tip_o + d_o.xpos[body_o]
        w_c = d_c.xmat[body_c].reshape(3, 3) @ tip_c + d_c.xpos[body_c] + translation
        pose_errors.append(float(np.linalg.norm(w_c - w_o)) * 1000.0)

    tau_o = _torque(mujoco, official, q_o, qd_o, qdd_o)
    tau_c = _torque(mujoco, compiled, q_c, qd_c, qdd_c)

    names = [mujoco.mj_id2name(official, mujoco.mjtObj.mjOBJ_JOINT, j) for j in range(official.njnt)]
    per_joint = []
    for j in range(official.njnt):
        per_joint.append({
            "joint": names[j],
            "official_peak_nm": round(float(np.abs(tau_o[:, j]).max()), 3),
            "compiled_peak_nm": round(float(np.abs(tau_c[:, j]).max()), 3),
            "official_rms_nm": round(float(np.sqrt(np.mean(tau_o[:, j] ** 2))), 3),
            "compiled_rms_nm": round(float(np.sqrt(np.mean(tau_c[:, j] ** 2))), 3),
        })

    # static gravity at three reference poses, no trajectory involved
    gravity = []
    for label, frac in (("rest", 0.0), ("quarter span", 0.25), ("half span", 0.5)):
        q_s = np.array(q_o[0])
        for j in range(official.njnt):
            lo, hi = official.jnt_range[j]
            if hi <= lo:
                lo, hi = -1.7, 1.7
            q_s[j] = (lo + hi) / 2.0 + frac * (hi - lo) / 2.0
        zero = np.zeros_like(q_s)
        t_o = _torque(mujoco, official, q_s[None, :], zero[None, :], zero[None, :])[0]
        t_c = _torque(mujoco, compiled, (q_s + args.sign * offsets)[None, :], zero[None, :], zero[None, :])[0]
        gravity.append({
            "pose": label,
            "official_peak_nm": round(float(np.abs(t_o).max()), 3),
            "compiled_peak_nm": round(float(np.abs(t_c).max()), 3),
            "per_joint_official": [round(float(v), 3) for v in t_o],
            "per_joint_compiled": [round(float(v), 3) for v in t_c],
        })

    payload = {
        "conventions": {
            "zero_pose_offsets_deg": ZERO_POSE_OFFSETS_DEG + [GRIPPER_OFFSET_DEG],
            "base_translation_mm": BASE_TRANSLATION_MM,
            "applied_to": "compiled model",
        },
        "pose_gate": {
            "tip_check_mm": [round(v, 2) for v in pose_errors],
            "worst_mm": round(max(pose_errors), 2),
            "documented_residual_mm": 11.25,
            "passes": max(pose_errors) <= 11.25,
            "method": "jaw-tip centroid at five timesteps, after applying the documented offsets",
        },
        "peak_torque_nm": {
            "official": round(float(np.abs(tau_o).max()), 3),
            "compiled": round(float(np.abs(tau_c).max()), 3),
        },
        "rms_torque_nm": {
            "official": round(float(np.sqrt(np.mean(tau_o ** 2))), 3),
            "compiled": round(float(np.sqrt(np.mean(tau_c ** 2))), 3),
        },
        "per_joint": per_joint,
        "static_gravity": gravity,
        "masses_kg": {"official": round(float(official.body_mass.sum()), 4),
                      "compiled": round(float(compiled.body_mass.sum()), 4)},
    }
    print(json.dumps(payload, indent=2))
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
