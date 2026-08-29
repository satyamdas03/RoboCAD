"""Tests for Phase 19 GEDA Bridge mechanism export with real joints/actuators/sensors."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

pytest.importorskip("mujoco")

import mujoco

from ai_cad.feature_tree import (
    Assembly,
    Feature,
    FeatureTree,
    Instance,
    KinematicJoint,
    Parameter,
    Part,
    PlaneReference,
    Sketch,
    SketchEntity,
)
from ai_cad.geda_bridge import export_bundle_from_tree, package_bundle_paths, verify_bundle
from ai_cad.geda_bridge.models import BundleManifest


def _make_cube_part(part_id: str, size: float = 10.0, material: str = "PLA") -> Part:
    return Part(
        id=part_id,
        material=material,
        sketches=[
            Sketch(
                id=f"{part_id}_profile",
                plane=PlaneReference(type="base", name="XY"),
                entities=[
                    SketchEntity(
                        type="rectangle",
                        id=f"{part_id}_rect",
                        center=(0, 0),
                        width=size,
                        height=size,
                    )
                ],
            )
        ],
        features=[
            Feature(
                id=f"{part_id}_extrude",
                type="extrude",
                sketch_id=f"{part_id}_profile",
                parameters={"amount": size, "mode": "add"},
            )
        ],
    )


def _make_box_part(
    part_id: str,
    width: float,
    height: float,
    depth: float,
    material: str = "PLA",
) -> Part:
    return Part(
        id=part_id,
        material=material,
        sketches=[
            Sketch(
                id=f"{part_id}_profile",
                plane=PlaneReference(type="base", name="XY"),
                entities=[
                    SketchEntity(
                        type="rectangle",
                        id=f"{part_id}_rect",
                        center=(0, 0),
                        width=width,
                        height=height,
                    )
                ],
            )
        ],
        features=[
            Feature(
                id=f"{part_id}_extrude",
                type="extrude",
                sketch_id=f"{part_id}_profile",
                parameters={"amount": depth, "mode": "add"},
            )
        ],
    )


def test_two_link_arm_urdf_has_one_revolute_joint(tmp_path: Path):
    """A 2-link serial arm exports a URDF with one revolute joint that MuJoCo can load."""
    base = _make_cube_part("base", size=40.0, material="PLA")
    link = _make_box_part("link", width=10.0, height=10.0, depth=80.0, material="aluminum")

    tree = FeatureTree(
        design_id="arm_2dof",
        prompt="two link serial arm",
        created_at="2026-08-29T00:00:00Z",
        parameters=[Parameter(name="joint_z", value=40.0, unit="mm")],
        parts=[base, link],
        assemblies=[
            Assembly(
                id="asm",
                instances=[
                    Instance(id="i_base", part_id="base"),
                    Instance(id="i_link", part_id="link", transform={"translation": [0, 0, 40]}),
                ],
                joints=[
                    KinematicJoint(
                        id="shoulder",
                        type="revolute",
                        parent_link="i_base",
                        child_link="i_link",
                        origin=(0, 0, 40),
                        axis=(0, 0, 1),
                        limits=(-180.0, 180.0),
                    )
                ],
            )
        ],
    )

    paths = export_bundle_from_tree(tree, tmp_path / "arm", name="arm")
    paths = package_bundle_paths(paths)

    manifest = BundleManifest(**__import__("json").loads(paths.manifest_json.read_text(encoding="utf-8")))
    assert len(manifest.parts) == 2

    verification = verify_bundle(paths.directory)
    assert verification.valid, verification.errors + verification.warnings

    urdf_text = paths.urdf.read_text(encoding="utf-8")
    root = ET.fromstring(urdf_text)
    revolute_joints = [j for j in root.findall("joint") if j.get("type") == "revolute"]
    assert len(revolute_joints) == 1

    joint = revolute_joints[0]
    assert joint.find("parent").get("link") == "i_base_base"
    assert joint.find("child").get("link") == "i_link_link"
    assert joint.find("axis") is not None
    assert joint.find("limit") is not None

    model = mujoco.MjModel.from_xml_path(str(paths.urdf))
    assert model.njnt >= 1


def test_gripper_mjcf_has_actuators_and_sensors(tmp_path: Path):
    """A parallel-jaw gripper exports an MJCF with two prismatic actuators and sensors."""
    base = _make_box_part("base", width=60.0, height=20.0, depth=20.0, material="PLA")
    jaw = _make_box_part("jaw", width=30.0, height=10.0, depth=8.0, material="PLA")

    tree = FeatureTree(
        design_id="gripper",
        prompt="parallel jaw gripper",
        created_at="2026-08-29T00:00:00Z",
        parts=[base, jaw],
        assemblies=[
            Assembly(
                id="asm",
                instances=[
                    Instance(id="i_base", part_id="base"),
                    Instance(id="i_left", part_id="jaw", transform={"translation": [-20, 0, 20]}),
                    Instance(id="i_right", part_id="jaw", transform={"translation": [20, 0, 20]}),
                ],
                joints=[
                    KinematicJoint(
                        id="left_jaw_slide",
                        type="prismatic",
                        parent_link="i_base",
                        child_link="i_left",
                        origin=(-20, 0, 20),
                        axis=(-1, 0, 0),
                        limits=(0, 50),
                    ),
                    KinematicJoint(
                        id="right_jaw_slide",
                        type="prismatic",
                        parent_link="i_base",
                        child_link="i_right",
                        origin=(20, 0, 20),
                        axis=(1, 0, 0),
                        limits=(0, 50),
                    ),
                ],
            )
        ],
    )

    paths = export_bundle_from_tree(tree, tmp_path / "gripper", name="gripper")
    paths = package_bundle_paths(paths)

    manifest = BundleManifest(**__import__("json").loads(paths.manifest_json.read_text(encoding="utf-8")))
    assert len(manifest.parts) == 3

    verification = verify_bundle(paths.directory)
    assert verification.valid, verification.errors + verification.warnings

    mjcf_text = paths.mjcf.read_text(encoding="utf-8")
    root = ET.fromstring(mjcf_text)

    actuators = root.find("actuator")
    assert actuators is not None
    motors = actuators.findall("motor")
    assert len(motors) == 2

    sensor = root.find("sensor")
    assert sensor is not None
    sensor_count = len(sensor.findall("jointpos")) + len(sensor.findall("jointvel")) + len(sensor.findall("jointactuatorfrc"))
    assert sensor_count >= 2

    model = mujoco.MjModel.from_xml_path(str(paths.mjcf))
    assert model.njnt >= 2
    assert model.nu >= 2


def test_fixed_only_assembly_still_loads(tmp_path: Path):
    """An assembly with no real joints keeps the existing fixed export behavior."""
    base = _make_cube_part("base", size=40.0, material="PLA")
    pin = _make_box_part("pin", width=6.0, height=6.0, depth=25.0, material="aluminum")

    tree = FeatureTree(
        design_id="fixed_asm",
        prompt="fixed two part assembly",
        created_at="2026-08-29T00:00:00Z",
        parts=[base, pin],
        assemblies=[
            Assembly(
                id="asm",
                instances=[
                    Instance(id="i_base", part_id="base"),
                    Instance(id="i_pin", part_id="pin", transform={"translation": [10, 0, 20]}),
                ],
            )
        ],
    )

    paths = export_bundle_from_tree(tree, tmp_path / "fixed", name="fixed")
    paths = package_bundle_paths(paths)

    manifest = BundleManifest(**__import__("json").loads(paths.manifest_json.read_text(encoding="utf-8")))
    assert len(manifest.parts) == 2

    verification = verify_bundle(paths.directory)
    assert verification.valid, verification.errors + verification.warnings

    model_mjcf = mujoco.MjModel.from_xml_path(str(paths.mjcf))
    model_urdf = mujoco.MjModel.from_xml_path(str(paths.urdf))
    assert model_mjcf.nbody >= 2
    assert model_urdf.nbody >= 1

    data = mujoco.MjData(model_mjcf)
    for _ in range(20):
        mujoco.mj_step(model_mjcf, data)
