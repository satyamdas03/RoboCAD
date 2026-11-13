"""P0-a: is the joint origin offset real, or an artefact of comparing two frames?

Three measurements, in the order the review asks for them:

1. Register the two models with one rigid transform, computed from the BASE LINK'S OWN GEOMETRY
   (its mesh vertices in both models), not from an assumed identity. The transform and its residual
   are printed, because a registration that fits badly makes every number after it meaningless.
2. Measure each joint as a LINE (a point on the axis plus a unit direction) in that common frame and
   report both the angle between the axes and the minimum distance between the lines. A distance
   that survives a good registration is a real origin difference; one that collapses was the frame.
3. Independent of joint lines: forward-kinematics error of a fixed point on the jaw tip over random
   configurations. This is the number that says whether the robot MOVES wrongly, which is the claim
   that actually matters.

Nothing here reads the other lane's report. Both models are loaded in MuJoCo and measured the same
way, so the comparison cannot inherit a bug from the producer.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib

import numpy as np


def _load(path: pathlib.Path):
    import mujoco

    path = path.resolve()
    cwd = os.getcwd()
    try:
        os.chdir(path.parent)
        return mujoco.MjModel.from_xml_path(path.name)
    finally:
        os.chdir(cwd)


def _body_points(mujoco, model, body_name: str, max_points: int = 4000):
    """World-space points of one body's mesh geoms at the zero pose, for registration."""
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
        R = data.geom_xmat[geom].reshape(3, 3)
        t = data.geom_xpos[geom]
        pts.append((verts @ R.T) + t)
    if not pts:
        return np.zeros((0, 3))
    allpts = np.vstack(pts)
    if len(allpts) > max_points:
        idx = np.linspace(0, len(allpts) - 1, max_points).astype(int)
        allpts = allpts[idx]
    return allpts


def _principal_frame(points: np.ndarray):
    """Centroid plus a right-handed frame from the covariance eigenvectors."""
    c = points.mean(axis=0)
    cov = np.cov((points - c).T)
    vals, vecs = np.linalg.eigh(cov)          # ascending eigenvalues
    order = np.argsort(vals)[::-1]
    E = vecs[:, order]
    if np.linalg.det(E) < 0:
        E[:, -1] *= -1
    return c, E


def _rigid_from_point_clouds(source: np.ndarray, target: np.ndarray):
    """Register two point clouds by their own geometry.

    Kabsch needs paired points, and two different meshes of the same part have no index
    correspondence, so pairing by index produces a transform that looks confident and means nothing.
    Instead: align the two principal frames, try every sign combination that keeps the rotation
    proper, and keep the one whose nearest-neighbour distance is smallest. That is registration by
    geometry, with a residual that can be inspected.
    """
    import itertools

    cs, Es = _principal_frame(source)
    ct, Et = _principal_frame(target)
    best = None
    for signs in itertools.product((1, -1), repeat=3):
        S = np.diag(signs)
        R = Et @ S @ Es.T
        if np.linalg.det(R) < 0:
            continue
        t = ct - R @ cs
        moved = (source @ R.T) + t
        sample = moved[np.linspace(0, len(moved) - 1, min(300, len(moved))).astype(int)]
        # nearest neighbour, chunked to keep memory sane on 300 x N
        step = max(1, len(target) // 2000)
        dist = np.linalg.norm(sample[:, None, :] - target[::step][None, :, :], axis=2).min(axis=1)
        score = float(np.median(dist))
        if best is None or score < best[0]:
            best = (score, R, t, float(np.percentile(dist, 95)))
    score, R, t, p95 = best
    return R, t, score, p95


def _axes_registration(mujoco, compiled, official):
    """Register by joint AXES with a full sense search, then place the frames by the anchors.

    This is the fallback when base-geometry registration cannot be trusted, which is the case while
    the compiled bundle carries collision hulls instead of visual meshes: a hull of the base is not
    the same surface as the published base mesh, so a cloud-to-cloud fit measures the hull error, not
    the frame.
    """
    import itertools

    ac, _ = _axes_only(mujoco, compiled)
    ao, _ = _axes_only(mujoco, official)
    best = None
    for signs in itertools.product((1, -1), repeat=len(ac)):
        target = ao * np.array(signs)[:, None]
        H = ac.T @ target
        U, S, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T
        if np.linalg.det(R) < 0:
            Vt[-1] *= -1
            R = Vt.T @ U.T
        res = [float(np.degrees(np.arccos(np.clip(float((R @ ac[i]) @ target[i]), -1.0, 1.0))))
               for i in range(len(ac))]
        score = float(np.sqrt(np.mean(np.square(res))))
        if best is None or score < best[0]:
            best = (score, R, signs, res)
    score, R, signs, res = best
    _, anc_c = _axes_only(mujoco, compiled)
    _, anc_o = _axes_only(mujoco, official)
    moved = anc_c @ R.T
    t = anc_o.mean(axis=0) - moved.mean(axis=0)
    return R, t, score, signs, res


def _axes_only(mujoco, model):
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    axes = np.array([data.xaxis[j] for j in range(model.njnt)], dtype=float)
    axes /= np.linalg.norm(axes, axis=1)[:, None]
    return axes, np.array([data.xanchor[j] for j in range(model.njnt)], dtype=float)


def _joint_lines(mujoco, model, R=None, t=None, joint_limit: int | None = None):
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    lines = []
    n = model.njnt if joint_limit is None else min(joint_limit, model.njnt)
    for j in range(n):
        axis = np.array(data.xaxis[j], dtype=float)
        axis /= np.linalg.norm(axis)
        point = np.array(data.xanchor[j], dtype=float)
        if R is not None:
            axis = R @ axis
            point = R @ point + t
        lines.append((point, axis))
    return lines


def _line_distance(p1, d1, p2, d2):
    """Minimum distance between two lines, and the angle between their directions."""
    cross = np.cross(d1, d2)
    norm = np.linalg.norm(cross)
    angle = float(np.degrees(np.arccos(np.clip(abs(float(d1 @ d2)), -1.0, 1.0))))
    if norm < 1e-9:  # parallel: distance from one point to the other line
        w = p2 - p1
        return float(np.linalg.norm(w - (w @ d1) * d1)), angle
    n = cross / norm
    return float(abs((p2 - p1) @ n)), angle


def _tip_point(mujoco, model, body_name: str, definition: str = "extreme"):
    """A fixed point on the end body, in world coordinates at the zero pose.

    Two definitions, both stated so two operators can compare numbers:
    ``centroid`` is the mean of the body's mesh vertices, which is what Lane A intends to use.
    ``extreme`` is the vertex furthest from that centroid, which amplifies any orientation error and
    is therefore the harder test. FK errors from the two are not interchangeable.
    """
    pts = _body_points(mujoco, model, body_name)
    if len(pts) == 0:
        return None
    centre = pts.mean(axis=0)
    if definition == "centroid":
        return centre
    return pts[np.argmax(np.linalg.norm(pts - centre, axis=1))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiled", required=True, help="compiled model.mjcf")
    parser.add_argument("--official", required=True, help="published model xml")
    parser.add_argument("--base-body-compiled", default=None)
    parser.add_argument("--base-body-official", default=None)
    parser.add_argument("--tip-body", default=None)
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--out", default=None)
    parser.add_argument("--tip-definition", choices=("centroid", "extreme"), default="extreme")
    parser.add_argument("--inside-limits", action="store_true", default=True)
    parser.add_argument("--register", choices=("axes", "base"), default="axes",
                        help="axes is the reliable option while the bundle carries hulls only")
    args = parser.parse_args()

    import mujoco

    compiled = _load(pathlib.Path(args.compiled))
    official = _load(pathlib.Path(args.official))

    def first_body(model):
        for b in range(1, model.nbody):
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b)
            if name:
                return name
        return None

    base_c = args.base_body_compiled or first_body(compiled)
    base_o = args.base_body_official or first_body(official)
    tip_c = args.tip_body or mujoco.mj_id2name(compiled, mujoco.mjtObj.mjOBJ_BODY, compiled.nbody - 1)
    tip_o = mujoco.mj_id2name(official, mujoco.mjtObj.mjOBJ_BODY, official.nbody - 1)

    mode = args.register
    if mode == "base":
        pc = _body_points(mujoco, compiled, base_c)
        po = _body_points(mujoco, official, base_o)
        if len(pc) == 0 or len(po) == 0:
            print("registration failed: no mesh geometry on the base body in one of the models")
            return 2
        R, t, res_med, res_p95 = _rigid_from_point_clouds(pc, po)
        reg = {"mode": "base_geometry", "residual_median_mm": round(res_med * 1000, 2),
               "residual_p95_mm": round(res_p95 * 1000, 2)}
    else:
        R, t, rms, senses, residuals = _axes_registration(mujoco, compiled, official)
        reg = {"mode": "joint_axes_sense_search", "axis_fit_rms_deg": round(rms, 3),
               "senses": [int(v) for v in senses],
               "axis_residual_deg": [round(v, 2) for v in residuals]}

    lines_c = _joint_lines(mujoco, compiled, R, t)
    lines_o = _joint_lines(mujoco, official)
    rows = []
    for j, ((p1, d1), (p2, d2)) in enumerate(zip(lines_c, lines_o)):
        dist_mm, angle_deg = _line_distance(p1, d1, p2, d2)
        rows.append({"joint": j + 1, "angle_deg": round(angle_deg, 2), "line_distance_mm": round(dist_mm * 1000, 1)})

    # forward kinematics of a fixed tip point, both models, same joint vectors
    rng = np.random.default_rng(0)
    tip_c_local = _tip_point(mujoco, compiled, tip_c, args.tip_definition)
    tip_o_local = _tip_point(mujoco, official, tip_o, args.tip_definition)
    dc, do = mujoco.MjData(compiled), mujoco.MjData(official)
    mujoco.mj_forward(compiled, dc)
    mujoco.mj_forward(official, do)
    body_c = mujoco.mj_name2id(compiled, mujoco.mjtObj.mjOBJ_BODY, tip_c)
    body_o = mujoco.mj_name2id(official, mujoco.mjtObj.mjOBJ_BODY, tip_o)
    local_c = dc.xmat[body_c].reshape(3, 3).T @ (tip_c_local - dc.xpos[body_c])
    local_o = do.xmat[body_o].reshape(3, 3).T @ (tip_o_local - do.xpos[body_o])

    # sample inside the PUBLISHED model's limits, because those are the joint ranges a real SO-101
    # has. The compiled bundle ships no limits at all (range 0 0), so sampling its own range would
    # silently draw every pose from a fallback and call it "inside the limits".
    lo = official.jnt_range[:, 0].copy()
    hi = official.jnt_range[:, 1].copy()
    unlimited = hi <= lo
    lo[unlimited], hi[unlimited] = -0.4, 0.4
    errors = []
    for _ in range(args.samples):
        q = rng.uniform(lo, hi) if args.inside_limits else rng.uniform(-0.4, 0.4, compiled.nq)
        dc.qpos[:] = q
        do.qpos[:] = q
        mujoco.mj_forward(compiled, dc)
        mujoco.mj_forward(official, do)
        wc = dc.xmat[body_c].reshape(3, 3) @ local_c + dc.xpos[body_c]
        wo = do.xmat[body_o].reshape(3, 3) @ local_o + do.xpos[body_o]
        wc = R @ wc + t
        errors.append(float(np.linalg.norm(wc - wo)))
    errors = np.array(errors)

    payload = {
        "registration": {
            **reg,
            "base_body_compiled": base_c, "base_body_official": base_o,
            "rotation_det": round(float(np.linalg.det(R)), 6),
            "translation_m": [round(float(v), 4) for v in t],
        },
        "joints": rows,
        "tip_body_compiled": tip_c, "tip_body_official": tip_o,
        "fk_tip_error_mm": {
            "max": round(float(errors.max()) * 1000, 2),
            "median": round(float(np.median(errors)) * 1000, 2),
            "samples": int(args.samples),
        },
    }
    print(json.dumps(payload, indent=2))
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
