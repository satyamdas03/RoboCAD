"""Legged-robot layout, joint emission and MuJoCo export of composed designs."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from ai_cad.assembly import (
    _matrix_to_intrinsic_xyz,
    compute_instance_transforms,
    solve_assembly,
    transpile_assembly,
)
from ai_cad.composer import compose_feature_tree
from ai_cad.decomposition import decompose
from ai_cad.robot_templates import humanoid_template, quadruped_template


def _compose(prompt: str):
    tree = compose_feature_tree(decompose(prompt))
    return tree, tree.assemblies[0]


def test_biped_layout_is_solved_without_overconstraint():
    tree, assembly = _compose("biped humanoid robot")
    solved = solve_assembly(tree, assembly)
    assert solved["overconstrained"] is False
    assert solved["residual_mm"] == pytest.approx(0.0)

    # The solver must keep the explicit layout instead of collapsing the chain.
    transforms = compute_instance_transforms(tree, assembly)
    for inst in assembly.instances:
        expected = inst.transform["translation"]
        assert transforms[inst.id][:3, 3] == pytest.approx(expected, abs=1e-6)


def test_biped_legs_hang_vertically_and_stand_on_ground():
    tree, assembly = _compose("biped humanoid robot")
    transforms = compute_instance_transforms(tree, assembly)

    for leg in ("left", "right"):
        for link in ("thigh", "shin"):
            rotation = transforms[f"i_{link}_{leg}"][:3, :3]
            # Bar long axis (local +X) points straight down, bore axis is lateral.
            assert rotation @ np.array([1.0, 0.0, 0.0]) == pytest.approx([0.0, 0.0, -1.0], abs=1e-9)
            assert rotation @ np.array([0.0, 0.0, 1.0]) == pytest.approx([0.0, 1.0, 0.0], abs=1e-9)
        assert transforms[f"i_foot_{leg}"][2, 3] == pytest.approx(0.0)

    torso_z = transforms["i_torso"][2, 3]
    assert torso_z > transforms["i_thigh_left"][2, 3] - 1e-6
    assert transforms["i_thigh_left"][2, 3] > transforms["i_shin_left"][2, 3] > 0.0
    # Left and right legs are mirrored about the sagittal plane.
    assert transforms["i_foot_left"][1, 3] == pytest.approx(-transforms["i_foot_right"][1, 3])


def test_biped_emits_revolute_leg_joints():
    _, assembly = _compose("biped humanoid robot")
    joints = {j.id: j for j in assembly.joints}
    for name in ("hip_pitch_l", "knee_l", "ankle_l", "hip_pitch_r", "knee_r", "ankle_r"):
        assert joints[name].type == "revolute"
        assert joints[name].axis == pytest.approx((0.0, 1.0, 0.0))

    # Joints descend from hip to ankle and form a serial chain per leg.
    assert joints["hip_pitch_l"].origin[2] > joints["knee_l"].origin[2] > joints["ankle_l"].origin[2]
    assert joints["hip_pitch_l"].parent_link == "i_torso"
    assert joints["knee_l"].parent_link == joints["hip_pitch_l"].child_link
    assert joints["ankle_l"].parent_link == joints["knee_l"].child_link

    instance_ids = {inst.id for inst in assembly.instances}
    for joint in assembly.joints:
        assert joint.child_link in instance_ids
        assert joint.parent_link in instance_ids


def test_quadruped_layout_has_four_articulated_legs():
    tree, assembly = _compose("quadruped walker")
    assert solve_assembly(tree, assembly)["overconstrained"] is False
    revolute = [j for j in assembly.joints if j.type == "revolute"]
    assert len(revolute) == 12
    assert {"hip_pitch_fl", "hip_pitch_fr", "hip_pitch_rl", "hip_pitch_rr"} <= {j.id for j in revolute}


def test_intrinsic_xyz_angles_reproduce_rotation():
    def rot(axis: str, deg: float) -> np.ndarray:
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        return {
            "x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]),
            "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
            "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]),
        }[axis]

    rng = np.random.default_rng(7)
    samples = [tuple(rng.uniform(-170, 170, 3)) for _ in range(20)] + [(0.0, 90.0, 0.0), (30.0, -90.0, 0.0)]
    for a, b, c in samples:
        M = np.eye(4)
        M[:3, :3] = rot("x", a) @ rot("y", b) @ rot("z", c)
        ra, rb, rc = _matrix_to_intrinsic_xyz(M)
        assert rot("x", ra) @ rot("y", rb) @ rot("z", rc) == pytest.approx(M[:3, :3], abs=1e-6)


def test_transpile_assembly_quotes_string_parameters():
    # Templates carry string parameters such as gait_style; they must be
    # emitted as Python string literals, not bare names.
    code = transpile_assembly(humanoid_template())
    assert "gait_style = 'biped_walk'" in code


def test_template_bundle_has_visible_link_geometry(tmp_path: Path):
    import trimesh

    from ai_cad.geda_bridge.exporter import export_bundle_from_tree, skeleton_preview_mesh

    for template in (humanoid_template(), quadruped_template()):
        out = tmp_path / template.design_id
        out.mkdir()
        bundle = export_bundle_from_tree(template, out, name="robot")
        extents = [trimesh.load_mesh(p).extents.max() for p in (out / "meshes").glob("*thigh*.stl")]
        assert extents and min(extents) > 0.05  # metres; placeholder cubes were 0.01
        assert bundle.mjcf.exists()

        preview = skeleton_preview_mesh(template)
        assert preview is not None
        assert preview.extents[2] > 300.0  # millimetres

    tree, _ = _compose("biped humanoid robot")
    assert skeleton_preview_mesh(tree) is None  # real CAD parts are not a skeleton


@pytest.mark.heavy
@pytest.mark.mujoco
def test_generated_biped_exports_articulated_mjcf_and_stands(tmp_path: Path):
    mujoco = pytest.importorskip("mujoco")

    from ai_cad.geda_bridge.exporter import export_bundle_from_tree
    from ai_cad.morphology_physics import _scale_masses_and_add_freejoint

    tree, assembly = _compose("biped humanoid robot")
    bundle = export_bundle_from_tree(tree, tmp_path, name="biped")

    model = mujoco.MjModel.from_xml_path(str(bundle.mjcf))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    assert model.njnt == 6
    assert model.nu == 6

    # Every body sits exactly where the assembly solver placed its instance,
    # including rotated links nested under rotated parents.
    transforms = compute_instance_transforms(tree, assembly)
    for inst in assembly.instances:
        body_id = next(
            i for i in range(model.nbody)
            if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) or "").startswith(inst.id + "_")
        )
        assert data.xpos[body_id] == pytest.approx(transforms[inst.id][:3, 3] / 1000.0, abs=1e-5)
        assert data.xmat[body_id].reshape(3, 3) == pytest.approx(transforms[inst.id][:3, :3], abs=1e-6)
    for joint_id in range(model.njnt):
        assert data.xaxis[joint_id] == pytest.approx([0.0, 1.0, 0.0], abs=1e-6)

    # With a free base, ground contact and position servos the robot keeps
    # standing on its own soles.
    _scale_masses_and_add_freejoint(bundle.mjcf, tree)
    model = mujoco.MjModel.from_xml_path(str(bundle.mjcf))
    data = mujoco.MjData(model)
    torso = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "i_torso_torso_plate")
    mujoco.mj_forward(model, data)
    start_z = float(data.xpos[torso, 2])
    max_tilt = 0.0
    for _ in range(int(5.0 / model.opt.timestep)):
        data.ctrl[:] = 0.0
        mujoco.mj_step(model, data)
        up = data.xmat[torso].reshape(3, 3)[2, 2]
        max_tilt = max(max_tilt, math.degrees(math.acos(max(-1.0, min(1.0, float(up))))))
    assert max_tilt < 2.0
    assert abs(float(data.xpos[torso, 2]) - start_z) < 0.005


def _mesh_poses(mujoco, model, data):
    poses = {}
    for geom in range(model.ngeom):
        if model.geom_type[geom] == mujoco.mjtGeom.mjGEOM_MESH:
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MESH, model.geom_dataid[geom])
            poses[name] = data.geom_xpos[geom].copy()
    return poses


@pytest.mark.mujoco
def test_urdf_and_mjcf_describe_the_same_robot(tmp_path: Path):
    """URDF link frames must reproduce the MJCF kinematics at rest and when posed."""
    mujoco = pytest.importorskip("mujoco")

    from ai_cad.geda_bridge.exporter import export_bundle_from_tree

    bundle = export_bundle_from_tree(humanoid_template(), tmp_path, name="robot")
    urdf = bundle.urdf.read_text(encoding="utf-8")
    cut = urdf.index(">", urdf.index("<robot")) + 1
    compiler = '<mujoco><compiler meshdir="meshes" strippath="true" discardvisual="false" fusestatic="false"/></mujoco>'
    urdf_path = tmp_path / "robot_check.urdf"
    urdf_path.write_text(urdf[:cut] + compiler + urdf[cut:], encoding="utf-8")

    m_urdf = mujoco.MjModel.from_xml_path(str(urdf_path))
    m_mjcf = mujoco.MjModel.from_xml_path(str(bundle.mjcf))
    d_urdf, d_mjcf = mujoco.MjData(m_urdf), mujoco.MjData(m_mjcf)
    assert m_urdf.njnt == m_mjcf.njnt > 0

    for angle in (0.0, 0.3):
        for joint in range(m_mjcf.njnt):
            name = mujoco.mj_id2name(m_mjcf, mujoco.mjtObj.mjOBJ_JOINT, joint)
            other = mujoco.mj_name2id(m_urdf, mujoco.mjtObj.mjOBJ_JOINT, name)
            assert other >= 0
            d_mjcf.qpos[m_mjcf.jnt_qposadr[joint]] = angle
            d_urdf.qpos[m_urdf.jnt_qposadr[other]] = angle
        mujoco.mj_forward(m_urdf, d_urdf)
        mujoco.mj_forward(m_mjcf, d_mjcf)
        a, b = _mesh_poses(mujoco, m_urdf, d_urdf), _mesh_poses(mujoco, m_mjcf, d_mjcf)
        assert set(a) == set(b)
        for name in b:
            assert a[name] == pytest.approx(b[name], abs=1e-5)
