"""Tests for Phase 24 world-model simulation builder."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_cad.geda_bridge import (
    apply_domain_randomization,
    build_world,
    drone_hover_world_template,
    export_world_to_isaac_json,
    export_world_to_mjcf,
    humanoid_stand_world_template,
    pick_place_world_template,
    push_world_template,
    resolve_body_alias,
    resolve_world_body_aliases,
    validate_isaac_world_json,
    walker_world_template,
)
from ai_cad.geda_bridge.models import BundleManifest


def _cube_asset(tmp_path: Path):
    """Build a small cube asset bundle and return (BundlePaths, parts)."""
    build123d = pytest.importorskip("build123d")
    from ai_cad.geda_bridge import export_bundle_from_shape, package_bundle_paths

    with build123d.BuildPart() as bp:
        build123d.Box(20, 20, 20)
    bundle_dir = tmp_path / "cube_asset"
    paths = export_bundle_from_shape(bp.part, bundle_dir, name="cube", material="PLA")
    paths = package_bundle_paths(paths)
    manifest = BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8")))
    return paths, manifest.parts


def test_pick_place_template(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = pick_place_world_template(parts)
    assert world.template == "pick_place"
    assert any(t.name == "table" for t in world.terrain)
    assert any(o.name == "target_cube" for o in world.scene.objects)
    assert any(s.sensor_type == "camera" for s in world.sensors)
    assert world.task is not None
    assert world.task.task_type == "pick_place"


def test_push_template(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = push_world_template(parts)
    assert world.template == "push"
    assert any(o.name == "block" for o in world.scene.objects)
    assert world.task is not None


def test_walker_template(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = walker_world_template(parts, terrain_type="plane")
    assert world.template == "walker"
    assert any(t.name == "floor" for t in world.terrain)
    assert any(s.sensor_type == "imu" for s in world.sensors)


def test_walker_slope_template(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = walker_world_template(parts, terrain_type="slope")
    assert any(t.name == "slope" for t in world.terrain)


def test_drone_hover_template(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = drone_hover_world_template(parts, hover_height_m=1.2)
    assert world.template == "drone_hover"
    assert any(t.name == "pad" for t in world.terrain)
    assert world.task is not None


def test_humanoid_stand_template(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = humanoid_stand_world_template(parts, robot_height_m=1.0)
    assert world.template == "humanoid_stand"
    assert any(s.name == "head_camera" for s in world.sensors)


def test_build_world_registry(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = build_world("push", parts)
    assert world.template == "push"


def test_unknown_world_template_raises():
    with pytest.raises(ValueError, match="Unknown world template"):
        build_world("not_a_template", [])


def test_domain_randomization_deterministic(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = push_world_template(parts)
    world_1 = apply_domain_randomization(world, seed=42)
    world_2 = apply_domain_randomization(world, seed=42)

    obj_1 = next(o for o in world_1.scene.objects if o.name == "block")
    obj_2 = next(o for o in world_2.scene.objects if o.name == "block")
    assert obj_1.density == obj_2.density
    assert obj_1.friction == obj_2.friction

    # Randomization actually changed something vs the original.
    original = next(o for o in world.scene.objects if o.name == "block")
    assert obj_1.density != original.density or obj_1.friction != original.friction


def test_isaac_json_export(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = pick_place_world_template(parts)
    json_path = paths.directory / "world_pick_place.isaac.json"
    export_world_to_isaac_json(world, json_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0.0"
    assert data["template"] == "pick_place"
    assert "terrain" in data
    assert "sensors" in data
    assert "objects" in data
    assert data["task"]["task_type"] == "pick_place"


def test_world_mjcf_without_robot_include(tmp_path: Path):
    """Fallback export with no robot MJCF places asset parts flat."""
    paths, parts = _cube_asset(tmp_path)
    world = pick_place_world_template(parts)
    world.robot_mjcf_file = None
    world_mjcf_path = paths.directory / "world_pick_place.mjcf"
    export_world_to_mjcf(world, world_mjcf_path)
    assert world_mjcf_path.exists()
    text = world_mjcf_path.read_text(encoding="utf-8")
    assert "cube" in text


def test_sensor_and_terrain_serialization(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = pick_place_world_template(parts)
    json_path = paths.directory / "world_pick_place.isaac.json"
    export_world_to_isaac_json(world, json_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data["terrain"]) >= 2
    assert any(t["type"] == "plane" for t in data["terrain"])
    camera = next(s for s in data["sensors"] if s["sensor_type"] == "camera")
    assert camera["resolution"] == [640, 480]
    assert camera["fov_deg"] == 75


def test_isaac_json_schema_validation(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = pick_place_world_template(parts)
    json_path = paths.directory / "world_pick_place.isaac.json"
    export_world_to_isaac_json(world, json_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    ok, errors = validate_isaac_world_json(data)
    assert ok, errors
    assert errors == []

    # Schema rejects an invalid payload.
    bad = {"name": "bad"}
    ok, errors = validate_isaac_world_json(bad)
    assert not ok
    assert any("missing required key" in e for e in errors)


def test_walker_stair_terrain(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = walker_world_template(parts, terrain_type="stairs")
    assert any(t.name.startswith("stairs_") for t in world.terrain)
    assert world.template == "walker"


def test_walker_ramp_terrain(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = walker_world_template(parts, terrain_type="ramp")
    assert any(t.name == "ramp" for t in world.terrain)


def test_walker_uneven_terrain(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = walker_world_template(parts, terrain_type="uneven")
    assert any(t.name.startswith("uneven_ground_") for t in world.terrain)


def test_body_alias_resolution(tmp_path: Path):
    paths, parts = _cube_asset(tmp_path)
    world = humanoid_stand_world_template(parts)
    assert resolve_body_alias("torso", {"torso_plate"}) == "torso_plate"
    assert resolve_body_alias("base", {"mobile_base"}) == "mobile_base"
    assert resolve_body_alias("torso", {"body"}) == "body"
    assert resolve_body_alias("torso", {"no_match"}) is None

    # Alias resolver updates world sensor / task references when names are known.
    resolved = resolve_world_body_aliases(world, available_names={"torso_plate"})
    imu = next(s for s in resolved.sensors if s.sensor_type == "imu")
    assert imu.attach_body == "torso_plate"
    assert resolved.task.success_criteria["body"] == "torso_plate"


@pytest.mark.mujoco
@pytest.mark.heavy
def test_world_mjcf_loads_in_mujoco(tmp_path: Path):
    mujoco = pytest.importorskip("mujoco")
    paths, parts = _cube_asset(tmp_path)
    manifest = BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8")))
    world = pick_place_world_template(parts)
    world.robot_mjcf_file = manifest.mjcf_file
    world_mjcf_path = paths.directory / "world_pick_place.mjcf"
    export_world_to_mjcf(world, world_mjcf_path)

    assert world_mjcf_path.exists()
    model = mujoco.MjModel.from_xml_path(str(world_mjcf_path))
    data = mujoco.MjData(model)
    for _ in range(20):
        mujoco.mj_step(model, data)
    assert model.nbody >= 3


@pytest.mark.mujoco
@pytest.mark.heavy
def test_world_replay(tmp_path: Path):
    mujoco = pytest.importorskip("mujoco")
    paths, parts = _cube_asset(tmp_path)
    manifest = BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8")))
    world = push_world_template(parts)
    world.robot_mjcf_file = manifest.mjcf_file
    world_mjcf_path = paths.directory / "world_push.mjcf"
    export_world_to_mjcf(world, world_mjcf_path)

    from ai_cad.geda_bridge.world_loaders import run_world_replay

    replay = run_world_replay(world_mjcf_path, duration_seconds=1.0, fps=10.0, body_names=["cube"])
    assert replay["success"]
    assert len(replay["times"]) > 0
    # Rich replay carries positions, velocities, and orientations.
    assert "cube" in replay["bodies"]
    assert replay["bodies"]["cube"][0]["pos"]
    assert replay["bodies"]["cube"][0]["quat"]
    assert replay["bodies"]["cube"][0]["linvel"]
    assert isinstance(replay["contacts"], list)
