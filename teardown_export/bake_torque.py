"""Torque comparison: what the mass difference does to the motors.

Both models are driven through the SAME joint trajectory. The published model has position
actuators, so it generates the trajectory; the compiled bundle has no actuators, so it is posed
kinematically at each sample. Required joint torque then comes from inverse dynamics on both, which
isolates the effect of mass and inertia: same motion, different bodies, different torque.

The joint order is index compatible between the two models (both are six hinge joints, root first),
so the trajectory is applied by index, never by name. Names differ.

Output is a classic script for the offline page, plus a JSON for the report.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib

import numpy as np


def _trajectory(mujoco, model, seconds: float, hz: int, amplitude: float = 0.30):
    """A smooth joint-space trajectory, written analytically rather than produced by the servo.

    Driving the published model's actuators cannot be used here: its position servo has a stiffness
    of about 998 N m per rad and a 3.35 N m forcerange, so essentially any commanded motion saturates
    it, and inverse dynamics then reports the torque limit instead of the mass difference. Imposing
    the motion analytically keeps the comparison about bodies, not about the servo's authority.
    """
    frames = int(seconds * hz)
    t = np.arange(frames) / hz
    qpos = np.zeros((frames, model.nq))
    qvel = np.zeros((frames, model.nv))
    qacc = np.zeros((frames, model.nv))
    for j in range(model.njnt):
        lo, hi = model.jnt_range[j]
        centre, span = (lo + hi) / 2.0, (hi - lo) / 2.0
        w = 2.0 * math.pi * (0.18 + 0.05 * j)
        qpos[:, j] = centre + span * amplitude * np.sin(w * t)
        qvel[:, j] = span * amplitude * w * np.cos(w * t)
        qacc[:, j] = -span * amplitude * w * w * np.sin(w * t)
    return qpos, qvel, qacc


def _required_torque(mujoco, model, qpos: np.ndarray, qvel: np.ndarray,
                     qacc: np.ndarray) -> np.ndarray:
    """Inverse dynamics along a recorded trajectory: the torque the motors would have to supply.

    Contacts are disabled on both models. The compiled bundle's convex hulls overlap at rest (its own
    report says so, 7.9 mm), and inverse dynamics folds those constraint forces into the joint torque,
    which produced a 989 N m reading on a joint whose gravity load is 0.6 N m. This panel compares
    inertial and gravity load, not contact, and says so.
    """
    model.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_CONTACT)
    data = mujoco.MjData(model)
    out = []
    for i in range(len(qpos)):
        data.qpos[:] = qpos[i]
        data.qvel[:] = qvel[i]
        data.qacc[:] = qacc[i]
        mujoco.mj_inverse(model, data)
        out.append(data.qfrc_inverse[: model.njnt].copy())
    return np.asarray(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("official", help="published model XML")
    parser.add_argument("compiled", help="compiled bundle model.mjcf")
    parser.add_argument("out", help="torque.js next to the page")
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--hz", type=int, default=100)
    parser.add_argument("--rated", type=float, default=3.35, help="servo rated torque, N m")
    args = parser.parse_args()

    import mujoco

    from ai_cad.compiler.conventions import from_bundle

    official = mujoco.MjModel.from_xml_path(args.official)
    qpos, qvel, qacc = _trajectory(mujoco, official, args.seconds, args.hz)
    # keep the excitation inside the servo's authority: a trajectory that saturates the published
    # actuators measures the torque limit, not the mass difference, and 3.349 N m against a 3.35 N m
    # rated servo is exactly that artefact.

    # the compiled bundle is posed from the same trajectory; meshdir is relative, so resolve from its dir
    compiled_path = pathlib.Path(args.compiled).resolve()
    import os

    cwd = os.getcwd()
    os.chdir(compiled_path.parent)
    try:
        compiled = mujoco.MjModel.from_xml_path(compiled_path.name)
    finally:
        os.chdir(cwd)

    # the line on the chart is the bundle's own actuator limit, not a datasheet guess typed here
    if compiled.nu:
        limits = [abs(float(compiled.actuator_forcerange[a][1])) for a in range(compiled.nu)
                  if compiled.actuator_forcelimited[a]]
        if limits:
            args.rated = min(limits)

    if compiled.njnt != official.njnt:
        raise SystemExit(f"joint count differs: official {official.njnt}, compiled {compiled.njnt}")

    tau_official = _required_torque(mujoco, official, qpos, qvel, qacc)
    tau_compiled = _required_torque(mujoco, compiled, qpos, qvel, qacc)

    peak_official = float(np.abs(tau_official).max())
    peak_compiled = float(np.abs(tau_compiled).max())
    saturated = peak_official >= 0.98 * args.rated

    names = [mujoco.mj_id2name(compiled, mujoco.mjtObj.mjOBJ_JOINT, j) or f"joint_{j+1}"
             for j in range(compiled.njnt)]

    # joint axes and anchors must be compared in the WORLD frame at rest: axes are expressed in each
    # model's own body frame, and the two models do not share body orientations
    def world_frame(m):
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        axes = np.array([d.xmat[int(m.jnt_bodyid[j])].reshape(3, 3) @ m.jnt_axis[j]
                         for j in range(m.njnt)])
        axes /= np.linalg.norm(axes, axis=1)[:, None]
        return axes, d.xanchor.copy()

    axes_c, anchors_c = world_frame(compiled)
    axes_o, anchors_o = world_frame(official)
    axis_angle_deg = [
        float(np.degrees(np.arccos(np.clip(float(a @ b), -1.0, 1.0))))
        for a, b in zip(axes_c, axes_o)
    ]

    # A revolute axis has no natural sense, so the comparison must search all 64 sense combinations
    # and refit the rotation inside each one. A signed fit that cannot flip a sense has to buy a
    # reversed axis with a rotation that bends every other joint, which is what produced the wrong
    # "90 degree axes" reading earlier in this sprint.
    import itertools

    best = None
    for signs in itertools.product((1, -1), repeat=len(axes_c)):
        target = axes_o * np.array(signs)[:, None]
        H = axes_c.T @ target
        U, S, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T
        if np.linalg.det(R) < 0:
            Vt[-1] *= -1
            R = Vt.T @ U.T
        res = [float(np.degrees(np.arccos(np.clip(float((R @ axes_c[i]) @ target[i]), -1.0, 1.0))))
               for i in range(len(axes_c))]
        score = float(np.sqrt(np.mean(np.square(res))))
        if best is None or score < best[0]:
            best = (score, res, R, signs)
    axis_fit_rms_deg, axis_residual_deg, R, senses = best

    moved = (R @ anchors_c.T).T
    moved = moved + (anchors_o.mean(axis=0) - moved.mean(axis=0))
    anchor_perp_mm, anchor_along_mm = [], []
    for i in range(len(anchors_c)):
        delta = moved[i] - anchors_o[i]
        axis = axes_o[i] / np.linalg.norm(axes_o[i])
        anchor_perp_mm.append(float(np.linalg.norm(delta - (delta @ axis) * axis) * 1000.0))
        anchor_along_mm.append(float(abs(delta @ axis) * 1000.0))

    names = [mujoco.mj_id2name(compiled, mujoco.mjtObj.mjOBJ_JOINT, j) or f"joint_{j+1}"
             for j in range(compiled.njnt)]

    # joint axes and anchors must be compared in the WORLD frame at rest: axes are expressed in each
    # model's own body frame, and the two models do not share body orientations
    anchor_delta_mm = [float(v) for v in np.linalg.norm(anchors_c - anchors_o, axis=1) * 1000.0]
    # static comparison at matched poses, which is the part that is physically valid. The trajectory
    # comparison is NOT comparable and the payload says so, because the jaw frame differs by tens of
    # millimetres and that difference is not a mass effect.
    def _static(m, shift):
        d = mujoco.MjData(m)
        rows = []
        for label, frac in (("rest", 0.0), ("quarter span", 0.25), ("half span", 0.5)):
            q = np.array([((m.jnt_range[j][0] + m.jnt_range[j][1]) / 2.0
                           + frac * (m.jnt_range[j][1] - m.jnt_range[j][0]) / 2.0)
                          if m.jnt_range[j][1] > m.jnt_range[j][0] else frac
                          for j in range(m.njnt)])
            d.qpos[:] = q + shift
            d.qvel[:] = 0.0
            mujoco.mj_forward(m, d)
            rows.append({"pose": label, "peak_nm": round(float(np.abs(d.qfrc_bias).max()), 4)})
        return rows

    from ai_cad.compiler.conventions import from_bundle

    conv = from_bundle(str(compiled_path.parent))
    offsets = np.asarray(conv.offset_vector_rad([f"joint_{i+1}" for i in range(compiled.njnt)]))
    translation = np.asarray(conv.base_translation_mm, dtype=float) / 1000.0
    # pose gate: how far apart the two models put the same world point, which is why the moving-arm
    # comparison is refused. It has to travel WITH the payload, or a demo quoting it is quoting a
    # number the viewer cannot reach.
    def _tip(m, body_name):
        d = mujoco.MjData(m); mujoco.mj_forward(m, d)
        body = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, body_name)
        pts = []
        for g in range(m.ngeom):
            if m.geom_bodyid[g] != body or m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH:
                continue
            mesh = int(m.geom_dataid[g]); a, n = m.mesh_vertadr[mesh], m.mesh_vertnum[mesh]
            verts = np.asarray(m.mesh_vert[a:a + n], dtype=float)
            pts.append(verts @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g])
        world = np.vstack(pts).mean(axis=0)
        return d.xmat[body].reshape(3, 3).T @ (world - d.xpos[body])

    tip_o = _tip(official, "moving_jaw_so101_v1")
    tip_c = _tip(compiled, "moving_jaw_so101")
    body_o = mujoco.mj_name2id(official, mujoco.mjtObj.mjOBJ_BODY, "moving_jaw_so101_v1")
    body_c = mujoco.mj_name2id(compiled, mujoco.mjtObj.mjOBJ_BODY, "moving_jaw_so101")
    do2, dc2 = mujoco.MjData(official), mujoco.MjData(compiled)
    gate = []
    for i in np.linspace(0, len(qpos) - 1, 5).astype(int):
        do2.qpos[:] = qpos[i]; mujoco.mj_forward(official, do2)
        dc2.qpos[:] = qpos[i] + offsets; mujoco.mj_forward(compiled, dc2)
        w_o = do2.xmat[body_o].reshape(3, 3) @ tip_o + do2.xpos[body_o]
        w_c = dc2.xmat[body_c].reshape(3, 3) @ tip_c + dc2.xpos[body_c] + translation
        gate.append(float(np.linalg.norm(w_c - w_o)) * 1000.0)
    pose_gate_worst_mm = round(max(gate), 2)

    static_compiled = _static(compiled, offsets)
    static_official = _static(official, np.zeros(official.njnt))

    payload = {
        "hz": args.hz,
        "frames": int(len(qpos)),
        "joints": names,
        "joint_order": "index order, both models six hinge joints root first; names differ, indices do not",
        "rated_nm": args.rated,
        "official_total_kg": float(official.body_mass.sum()),
        "compiled_total_kg": float(compiled.body_mass.sum()),
        "official": np.round(tau_official, 4).tolist(),
        "compiled": np.round(tau_compiled, 4).tolist(),
        "label": "same joint-space trajectory, different bodies",
        "saturated": saturated,
        "static_by_pose": [{"pose": a["pose"], "compiled_nm": a["peak_nm"], "published_nm": b["peak_nm"]}
                           for a, b in zip(static_compiled, static_official)],
        "dynamic_comparable": False,
        "pose_gate_worst_mm": pose_gate_worst_mm,
        "pose_gate_samples_mm": [round(v, 2) for v in gate],
        "dynamic_reason": "jaw frame differs by tens of mm; a constant offset cannot map a joint "
                          "vector to a matching tip",
        "axis_angle_deg": [round(v, 1) for v in axis_angle_deg],
        "anchor_delta_mm": [round(v, 1) for v in anchor_delta_mm],
        "axis_residual_deg_after_datum_fit": [round(v, 2) for v in axis_residual_deg],
        "axis_fit_rms_deg": round(axis_fit_rms_deg, 2),
        "axis_senses": [int(v) for v in senses],
        "anchor_perp_mm_after_datum_fit": [round(v, 1) for v in anchor_perp_mm],
        "anchor_along_mm_after_datum_fit": [round(v, 1) for v in anchor_along_mm],
        "datum_fit_note": "best of 64 sense combinations, rotation refitted inside each, then a "
                          "translation fitted on the anchors. Along-axis offset is the freedom every "
                          "revolute joint has and is not evidence of anything; perpendicular offset is.",
        "note": "contacts disabled on both models; the compiled hulls overlap at rest and their "
                "constraint forces would otherwise appear as joint torque",
    }
    out = pathlib.Path(args.out)
    out.write_text("window.SO101_TORQUE = " + json.dumps(payload) + ";\n", encoding="utf-8")

    ratio = peak_compiled / peak_official if peak_official else float("nan")
    print(f"{out} {out.stat().st_size} bytes, {payload['frames']} frames, {len(names)} joints")
    print(f"peak torque official {peak_official:.3f} N m, compiled {peak_compiled:.3f} N m, ratio {ratio:.2f}")
    print(f"rated servo torque used as the line on the chart: {args.rated} N m")
    print("world joint axis angle difference (deg):", [round(v, 1) for v in axis_angle_deg])
    print("world joint anchor distance (mm):", [round(v, 1) for v in anchor_delta_mm])
    print("axis residual after sense-searched datum fit (deg):", [round(v, 2) for v in axis_residual_deg],
          "rms", round(axis_fit_rms_deg, 2), "senses", senses)
    print("anchor perpendicular distance after datum fit (mm):", [round(v, 1) for v in anchor_perp_mm])
    if saturated:
        print("WARNING: the published servo reaches its rated torque, so part of this trajectory is "
              "a saturation artefact; lower the amplitude before quoting these numbers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
