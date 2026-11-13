"""Bake a MuJoCo trajectory and simplified meshes for the offline living page.

Output is two classic scripts that assign typed arrays to globals, because a page opened from
file:// has a null origin: fetch() and ES modules are both blocked, a plain <script> is not.

Usage:
    python teardown_export/bake.py <model.xml> <out_dir> [--seconds 6] [--hz 100] [--triangles 2500]
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib

import numpy as np


def _simulate(model, data, mujoco, seconds: float, hz: int) -> dict:
    """Drive every joint through a gentle sweep and record what the page needs."""
    steps_per_frame = max(1, int(round(1.0 / (hz * model.opt.timestep))))
    frames = int(seconds * hz)
    qpos, qfrc, body_pos, body_mat = [], [], [], []

    for frame in range(frames):
        t = frame / hz
        for act in range(model.nu):
            joint = model.actuator_trnid[act, 0]
            lo, hi = model.jnt_range[joint]
            centre, span = (lo + hi) / 2.0, (hi - lo) / 2.0
            phase = 0.32 * np.sin(2.0 * np.pi * (0.18 * t + 0.09 * act))
            data.ctrl[act] = centre + span * phase
        for _ in range(steps_per_frame):
            mujoco.mj_step(model, data)
        qpos.append(data.qpos.copy())
        qfrc.append(data.qfrc_actuator.copy())
        body_pos.append(data.xpos.copy())
        body_mat.append(data.xmat.reshape(-1, 9).copy())

    return {
        "qpos": np.asarray(qpos, dtype=np.float32),
        "qfrc": np.asarray(qfrc, dtype=np.float32),
        "body_pos": np.asarray(body_pos, dtype=np.float32),
        "body_mat": np.asarray(body_mat, dtype=np.float32),
    }


def _simplify(vertices: np.ndarray, faces: np.ndarray, target_triangles: int):
    """Reduce a mesh to a triangle budget; fall back to the original if reduction is not available."""
    if len(faces) <= target_triangles:
        return vertices.astype(np.float32), faces.astype(np.int32)
    try:
        import fast_simplification

        verts, tris = vertices.astype(np.float32), faces.astype(np.int32)
        for _ in range(6):
            if len(tris) <= target_triangles:
                break
            reduction = min(0.95, 1.0 - (target_triangles / float(len(tris))))
            new_verts, new_tris = fast_simplification.simplify(
                verts, tris, target_reduction=reduction
            )
            if len(new_tris) >= len(tris):
                break
            verts, tris = new_verts.astype(np.float32), new_tris.astype(np.int32)
        if len(tris) > target_triangles:
            print(f"  floor reached for this mesh: {len(tris)} triangles (multi-shell geometry)")
        return verts, tris
    except Exception as exc:  # noqa: BLE001 - report the reason rather than hiding it
        print(f"  decimation skipped for {len(faces)} triangles: {type(exc).__name__}: {exc}")
        return vertices.astype(np.float32), faces.astype(np.int32)


def _meshes(model, mujoco, target_triangles: int, visual_only: bool = True):
    """Unique meshes, simplified, plus which mesh each mesh geom uses.

    MuJoCo reuses one mesh across several geoms, so the payload stores each mesh once and the page
    shares the geometry object. That is the difference between a 17 MB page payload and a loadable one.
    """
    unique: dict[int, dict] = {}
    geoms = []
    for geom in range(model.ngeom):
        if model.geom_type[geom] != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        # visual geoms carry contype and conaffinity 0; collision hulls are the ones that collide.
        # Rendering hulls makes the page look like a pile of blocks, so the page takes the visuals
        # and the collision set stays a property of the bundle, not of the picture.
        is_visual = int(model.geom_contype[geom]) == 0 and int(model.geom_conaffinity[geom]) == 0
        if visual_only and not is_visual:
            continue
        if (not visual_only) and is_visual:
            continue
        mesh_id = int(model.geom_dataid[geom])
        if mesh_id not in unique:
            vert_adr, vert_num = model.mesh_vertadr[mesh_id], model.mesh_vertnum[mesh_id]
            face_adr, face_num = model.mesh_faceadr[mesh_id], model.mesh_facenum[mesh_id]
            verts = np.asarray(model.mesh_vert[vert_adr : vert_adr + vert_num], dtype=np.float64)
            faces = np.asarray(model.mesh_face[face_adr : face_adr + face_num], dtype=np.int64)
            verts, faces = _simplify(verts, faces, target_triangles)
            unique[mesh_id] = {
                "verts": verts,
                "faces": faces,
                "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MESH, mesh_id) or f"mesh{mesh_id}",
            }
        geoms.append({
            "geom": int(geom),
            "mesh": mesh_id,
            "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom) or f"geom{geom}",
            "body": int(model.geom_bodyid[geom]),
            "pos": [float(v) for v in model.geom_pos[geom]],
            "quat": [float(v) for v in model.geom_quat[geom]],
        })
    return list(unique.items()), geoms


def _b64(array: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(array).tobytes()).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("out_dir")
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--hz", type=int, default=100)
    parser.add_argument("--triangles", type=int, default=2500)
    parser.add_argument("--visual-only", action="store_true", default=True)
    parser.add_argument("--collision-only", dest="visual_only", action="store_false")
    args = parser.parse_args()

    import mujoco

    model = mujoco.MjModel.from_xml_path(args.model)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    traj = _simulate(model, data, mujoco, args.seconds, args.hz)
    mesh_items, mesh_geoms = _meshes(model, mujoco, args.triangles, args.visual_only)

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    joints, bodies = [], []
    for i in range(model.njnt):
        joint = model.jnt
        joints.append({
            "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i),
            "range": [float(v) for v in model.jnt_range[i]],
        })
    for i in range(model.nbody):
        bodies.append({
            "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i),
            "mass": float(model.body_mass[i]),
            "parent": int(model.body_parentid[i]),
        })

    meta = {
        "source": str(pathlib.Path(args.model).name),
        "hz": args.hz,
        "frames": int(traj["qpos"].shape[0]),
        "nq": int(model.nq),
        "nbody": int(model.nbody),
        "joints": joints,
        "bodies": bodies,
        "total_mass_kg": float(model.body_mass.sum()),
        "body_mass": [float(v) for v in model.body_mass],
        "timestep": float(model.opt.timestep),
        "synthetic": False,
        "geoms": mesh_geoms,
    }

    (out / "trajectory.js").write_text(
        "window.SO101_META = " + json.dumps(meta) + ";\n"
        + "window.SO101_TRAJ = {qpos:'%s', qfrc:'%s', body_pos:'%s', body_mat:'%s'};\n"
        % (_b64(traj["qpos"]), _b64(traj["qfrc"]), _b64(traj["body_pos"]), _b64(traj["body_mat"])),
        encoding="utf-8",
    )

    payload = [
        {"id": mesh_id, "name": m["name"],
         "verts": _b64(m["verts"]), "faces": _b64(m["faces"]), "count": int(len(m["faces"]))}
        for mesh_id, m in mesh_items
    ]
    (out / "meshes.js").write_text(
        "window.SO101_MESHES = " + json.dumps(payload) + ";\n", encoding="utf-8"
    )

    tri_total = sum(len(m["faces"]) for _, m in mesh_items)
    print(f"frames {meta['frames']} joints {len(joints)} bodies {meta['nbody']}")
    print(f"unique meshes {len(mesh_items)} triangles {tri_total} across {len(mesh_geoms)} mesh geoms")
    print(f"trajectory.js {(out / 'trajectory.js').stat().st_size} bytes")
    print(f"meshes.js {(out / 'meshes.js').stat().st_size} bytes")
    print(f"total_mass_kg {meta['total_mass_kg']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
