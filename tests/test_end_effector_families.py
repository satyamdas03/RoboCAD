"""Tests for real end-effector part families (Milestone D)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from ai_cad.part_families import instantiate_family


@pytest.mark.parametrize(
    "family",
    [
        "parallel_jaw_gripper",
        "three_finger_hand",
        "vacuum_gripper",
        "point_foot",
        "compliant_foot",
    ],
)
def test_end_effector_family_instantiates(family: str) -> None:
    part = instantiate_family(family, part_id=f"ee_{family}")
    assert part.id == f"ee_{family}"
    assert part.family == family
    assert len(part.sketches) >= 1
    assert len(part.features) >= 1


@pytest.mark.slow
def test_humanoid_parallel_jaw_changes_part_family() -> None:
    from ai_cad.morphology import _attach_end_effector, _make_tree

    tree = _make_tree("humanoid", {"robot_height": 1000.0})
    tree_ee = _attach_end_effector(tree, "parallel_jaw_gripper")
    right_hand = tree_ee.find_part("hand_r")
    assert right_hand is not None
    assert right_hand.family == "parallel_jaw_gripper"


@pytest.mark.slow
def test_quadruped_point_foot_changes_part_family() -> None:
    from ai_cad.morphology import _attach_end_effector, _make_tree

    tree = _make_tree("quadruped", {"robot_height": 600.0})
    tree_ee = _attach_end_effector(tree, "point_foot")
    foot = tree_ee.find_part("foot_fl")
    assert foot is not None
    assert foot.family == "point_foot"


@pytest.mark.slow
def test_manipulator_vacuum_changes_part_family() -> None:
    from ai_cad.morphology import _attach_end_effector, _make_tree

    tree = _make_tree("manipulator_on_base", {"reach": 800.0})
    tree_ee = _attach_end_effector(tree, "vacuum_gripper")
    ee = tree_ee.find_part("end_effector")
    assert ee is not None
    assert ee.family == "vacuum_gripper"


@pytest.mark.heavy
@pytest.mark.mujoco
def test_parallel_jaw_humanoid_exports_and_loads_in_mujoco() -> None:
    try:
        import mujoco  # type: ignore[import-untyped]
    except Exception as exc:
        pytest.skip(f"MuJoCo not available: {exc}")
    from ai_cad.geda_bridge.exporter import export_bundle_from_tree
    from ai_cad.morphology import _attach_end_effector, _make_tree

    tree = _attach_end_effector(
        _make_tree("humanoid", {"robot_height": 1000.0}),
        "parallel_jaw_gripper",
    )
    out_dir = Path(tempfile.mkdtemp())
    bundle = export_bundle_from_tree(tree, out_dir, name="humanoid_parallel_jaw")
    model = mujoco.MjModel.from_xml_path(str(bundle.mjcf))
    assert model.nq > 0
    assert model.nbody > 0


@pytest.mark.heavy
@pytest.mark.mujoco
def test_point_foot_quadruped_exports_and_loads_in_mujoco() -> None:
    try:
        import mujoco  # type: ignore[import-untyped]
    except Exception as exc:
        pytest.skip(f"MuJoCo not available: {exc}")
    from ai_cad.geda_bridge.exporter import export_bundle_from_tree
    from ai_cad.morphology import _attach_end_effector, _make_tree

    tree = _attach_end_effector(
        _make_tree("quadruped", {"robot_height": 600.0}),
        "point_foot",
    )
    out_dir = Path(tempfile.mkdtemp())
    bundle = export_bundle_from_tree(tree, out_dir, name="quadruped_point_foot")
    model = mujoco.MjModel.from_xml_path(str(bundle.mjcf))
    assert model.nq > 0
    assert model.nbody > 0
