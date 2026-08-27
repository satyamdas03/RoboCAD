"""Tests for Phase 14B standard manipulation scene templates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mujoco")

import mujoco

from ai_cad.geda_bridge import (
    bracket_hook_hang_template,
    build_scene,
    export_bundle_from_shape,
    export_scene_to_mjcf,
    gripper_cube_grasp_template,
    package_bundle_paths,
    peg_insertion_template,
    wedge_push_block_template,
)
from ai_cad.geda_bridge.models import BundleManifest


def _cube_asset(tmp_path: Path):
    """Build a small cube asset bundle and return (BundlePaths, parts)."""
    build123d = pytest.importorskip("build123d")
    with build123d.BuildPart() as bp:
        build123d.Box(20, 20, 20)
    bundle_dir = tmp_path / "cube_asset"
    paths = export_bundle_from_shape(bp.part, bundle_dir, name="cube", material="PLA")
    paths = package_bundle_paths(paths)
    manifest = BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8")))
    return paths, manifest.parts


def _load_and_simulate(mjcf_path: Path, steps: int = 20) -> mujoco.MjModel:
    """Load an MJCF and run physics steps; return the model."""
    model = mujoco.MjModel.from_xml_path(str(mjcf_path))
    data = mujoco.MjData(model)
    for _ in range(steps):
        mujoco.mj_step(model, data)
    return model


def test_gripper_cube_grasp_scene(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    scene = gripper_cube_grasp_template(parts)
    assert scene.template == "gripper_cube_grasp"
    assert any(o.name == "target_cube" for o in scene.objects)
    assert any(g.goal_type == "lift" for g in scene.goals)

    scene_path = paths.directory / "scene_gripper_cube_grasp.mjcf"
    export_scene_to_mjcf(scene, scene_path)
    model = _load_and_simulate(scene_path)
    assert model.nbody >= 3  # world + asset + table + cube


def test_bracket_hook_hang_scene(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    scene = bracket_hook_hang_template(parts)
    assert scene.template == "bracket_hook_hang"
    assert any(o.name == "peg" for o in scene.objects)
    assert any(g.goal_type == "hang" for g in scene.goals)

    scene_path = paths.directory / "scene_bracket_hook_hang.mjcf"
    export_scene_to_mjcf(scene, scene_path)
    model = _load_and_simulate(scene_path)
    assert model.nbody >= 3


def test_wedge_push_block_scene(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    scene = wedge_push_block_template(parts)
    assert scene.template == "wedge_push_block"
    assert any(o.name == "block" for o in scene.objects)
    assert any(g.goal_type == "push" for g in scene.goals)

    scene_path = paths.directory / "scene_wedge_push_block.mjcf"
    export_scene_to_mjcf(scene, scene_path)
    model = _load_and_simulate(scene_path)
    assert model.nbody >= 3


def test_peg_insertion_scene(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    scene = peg_insertion_template(parts)
    assert scene.template == "peg_insertion"
    assert any(o.name.startswith("board_") for o in scene.objects)
    assert any(g.goal_type == "insert" for g in scene.goals)

    scene_path = paths.directory / "scene_peg_insertion.mjcf"
    export_scene_to_mjcf(scene, scene_path)
    model = _load_and_simulate(scene_path)
    assert model.nbody >= 3


def test_build_scene_registry(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    scene = build_scene("gripper_cube_grasp", parts)
    assert scene.template == "gripper_cube_grasp"


def test_unknown_template_raises():
    with pytest.raises(ValueError, match="Unknown scene template"):
        build_scene("not_a_template", [])
