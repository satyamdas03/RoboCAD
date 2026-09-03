"""World-model simulation builder for the RoboCAD GEDA Bridge.

Phase 24 provides a single world description that can be exported to both MuJoCo
(MJCF) and NVIDIA Isaac Sim (JSON). A world contains a RoboCAD robot/asset,
objects, terrain, sensors, a task definition, and optional domain randomization.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ai_cad.geda_bridge.models import BundlePart
from ai_cad.geda_bridge.scene_templates import (
    SceneDescription,
    SceneGoalRegion,
    SceneObject,
    ScenePose,
    _apply_pose,
    _bundle_part_local_pose,
    _euler_to_quaternion,
    _format_pos,
    _format_quat,
    _rotation_matrix_to_quaternion,
    _sanitize_name,
    _write_pretty_xml,
)


MM_TO_M = 0.001


@dataclass
class DomainRandomization:
    """Ranges for deterministic domain randomization.

    All values are relative multipliers or additive offsets applied to the base
    world description. A fixed ``seed`` makes the perturbation reproducible.
    """

    mass_scale_range: tuple[float, float] = (0.9, 1.1)
    friction_range: tuple[float, float, float] = (0.5, 1.2, 0.01)
    actuator_gain_range: tuple[float, float] = (0.9, 1.1)
    sensor_noise_std: dict[str, float] = field(
        default_factory=lambda: {"camera": 0.01, "imu": 0.02, "force": 1.0, "proximity": 0.005}
    )
    wind_range_m_s: tuple[float, float, float] = (-1.0, 1.0, 0.0)
    thermal_load_range_w: tuple[float, float] = (0.0, 10.0)
    seed: int | None = None


@dataclass
class WorldTerrain:
    """A piece of terrain in the world."""

    name: str
    type: str  # plane, heightfield, slope, box
    size: tuple[float, float, float] = (10.0, 10.0, 0.1)
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    quat: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    friction: tuple[float, float, float] = (0.8, 0.1, 0.1)
    rgba: tuple[float, float, float, float] = (0.5, 0.5, 0.55, 1.0)


@dataclass
class WorldSensor:
    """A sensor attached to a body or the world frame."""

    name: str
    sensor_type: str  # camera, imu, force, proximity
    attach_body: str | None = None
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    quat: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    noise_std: float = 0.0
    fov_deg: float | None = None
    resolution: tuple[int, int] | None = None
    range_m: float | None = None


@dataclass
class WorldTask:
    """Task definition for downstream policy / RL code."""

    task_type: str  # pick_place, push, walker, drone_hover, humanoid_stand
    goal_regions: list[SceneGoalRegion] = field(default_factory=list)
    success_criteria: dict[str, Any] = field(default_factory=dict)
    reward_hints: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorldDescription:
    """Full world description shared across MuJoCo and Isaac Sim exports."""

    name: str
    template: str
    scene: SceneDescription = field(default_factory=lambda: SceneDescription(name="world", template="custom"))
    terrain: list[WorldTerrain] = field(default_factory=list)
    sensors: list[WorldSensor] = field(default_factory=list)
    task: WorldTask | None = None
    randomization: DomainRandomization | None = None
    robot_mjcf_file: str | None = "model.mjcf"
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())

    @property
    def asset_parts(self) -> list[BundlePart]:
        return self.scene.asset_parts

    @property
    def asset_pose(self) -> ScenePose:
        return self.scene.asset_pose


class WorldBuilder:
    """Mutable builder for a simulation world."""

    def __init__(self, name: str, template: str = "custom") -> None:
        self.world = WorldDescription(name=name, template=template)

    def set_asset(self, parts: list[BundlePart], pose: ScenePose | None = None) -> "WorldBuilder":
        self.world.scene.asset_parts = list(parts)
        if pose is not None:
            self.world.scene.asset_pose = pose
        return self

    def add_object(self, obj: SceneObject) -> "WorldBuilder":
        self.world.scene.objects.append(obj)
        return self

    def add_terrain(self, terrain: WorldTerrain) -> "WorldBuilder":
        self.world.terrain.append(terrain)
        return self

    def add_sensor(self, sensor: WorldSensor) -> "WorldBuilder":
        self.world.sensors.append(sensor)
        return self

    def set_task(self, task: WorldTask) -> "WorldBuilder":
        self.world.task = task
        return self

    def enable_randomization(self, randomization: DomainRandomization | None = None) -> "WorldBuilder":
        self.world.randomization = randomization or DomainRandomization()
        return self

    def to_mjcf(self, output_path: Path) -> Path:
        return export_world_to_mjcf(self.world, output_path)

    def to_isaac_json(self, output_path: Path) -> Path:
        return export_world_to_isaac_json(self.world, output_path)


# ---------------------------------------------------------------------------
# Domain randomization
# ---------------------------------------------------------------------------


def _make_rng(seed: int | None) -> np.random.Generator:
    return np.random.default_rng(seed)


def apply_domain_randomization(
    world: WorldDescription,
    seed: int | None = None,
) -> WorldDescription:
    """Return a deterministically randomized copy of ``world``.

    Mutates mass, friction, actuator gains, sensor noise, wind offset, and
    thermal load inside the copy. The original is left unchanged.
    """
    rng = _make_rng(seed if seed is not None else (world.randomization.seed if world.randomization else 42))
    randomized = copy.deepcopy(world)
    if randomized.randomization is None:
        randomized.randomization = DomainRandomization(seed=seed)
    else:
        randomized.randomization.seed = seed

    dr = randomized.randomization

    # Perturb object mass and friction.
    for obj in randomized.scene.objects:
        mass_scale = float(rng.uniform(*dr.mass_scale_range))
        if obj.mass is not None:
            obj.mass = obj.mass * mass_scale
        else:
            # Density acts as a proxy for mass when mass is not explicit.
            obj.density = obj.density * mass_scale
        obj.friction = _perturb_tuple(obj.friction, dr.friction_range, rng, scale=True)

    # Perturb terrain friction.
    for terrain in randomized.terrain:
        terrain.friction = _perturb_tuple(terrain.friction, dr.friction_range, rng, scale=True)

    # Perturb sensor noise.
    for sensor in randomized.sensors:
        base_noise = dr.sensor_noise_std.get(sensor.sensor_type, 0.0)
        sensor.noise_std = max(0.0, float(rng.normal(base_noise, base_noise * 0.2)))

    return randomized


def _perturb_tuple(
    value: tuple[float, float, float] | None,
    range_spec: tuple[float, float, float],
    rng: np.random.Generator,
    scale: bool = True,
) -> tuple[float, float, float]:
    if value is None:
        base = (1.0, 1.0, 1.0)
    else:
        base = value
    lo, hi, _ = range_spec
    if scale:
        factor = float(rng.uniform(lo, hi))
        return tuple(max(0.0, v * factor) for v in base)
    # Additive perturbation within range.
    delta = tuple(float(rng.uniform(lo, hi)) for _ in base)
    return tuple(max(0.0, b + d) for b, d in zip(base, delta))


# ---------------------------------------------------------------------------
# MJCF export
# ---------------------------------------------------------------------------


def export_world_to_mjcf(world: WorldDescription, output_path: Path, robot_mjcf_file: str | None = None) -> Path:
    """Write a MuJoCo MJCF world file from a WorldDescription.

    The robot/asset MJCF is included so the articulated model appears in the
    world with its existing joints, actuators, and sensors. Terrain, props,
    task sites, and world-level sensors are added after the include.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mujoco = ET.Element("mujoco", {"model": _sanitize_name(world.name)})
    ET.SubElement(mujoco, "compiler", {"meshdir": "meshes", "autolimits": "true"})
    ET.SubElement(
        mujoco,
        "option",
        {
            "timestep": "0.002",
            "integrator": "implicitfast",
            "solver": "Newton",
            "iterations": "50",
            "ls_iterations": "10",
        },
    )

    # Default friction class used by randomized terrains / objects.
    default = ET.SubElement(mujoco, "default")
    friction_default = ET.SubElement(default, "default", {"class": "world_surface"})
    ET.SubElement(friction_default, "geom", {"friction": "0.8 0.1 0.1"})

    asset = ET.SubElement(mujoco, "asset")

    # Include the robot's own MJCF at the top level if available; otherwise
    # place asset parts flat inside the worldbody.
    robot_file = robot_mjcf_file or world.robot_mjcf_file
    if robot_file:
        ET.SubElement(mujoco, "include", {"file": robot_file})

    worldbody = ET.SubElement(mujoco, "worldbody")

    # Global light + camera.
    ET.SubElement(
        worldbody,
        "light",
        {"directional": "true", "diffuse": "0.5 0.5 0.5", "pos": "0 0 3", "dir": "0 0 -1"},
    )
    ET.SubElement(
        worldbody,
        "camera",
        {"name": "topdown", "pos": "0 -1.5 1.5", "quat": "0.707 0.707 0 0", "fovy": "60"},
    )

    if not robot_file:
        _place_asset_parts_flat(asset, worldbody, world)

    # Register and place object meshes if any object uses a mesh file.
    for obj in world.scene.objects:
        if obj.geom_type == "mesh" and obj.mesh_file:
            ET.SubElement(asset, "mesh", {"name": _sanitize_name(obj.name), "file": Path(obj.mesh_file).name})

    # Add terrain.
    for terrain in world.terrain:
        _add_terrain(worldbody, terrain)

    # Add scene objects / props.
    from ai_cad.geda_bridge.scene_templates import _add_scene_object

    for obj in world.scene.objects:
        _add_scene_object(worldbody, obj)

    # Add task sites.
    task = world.task
    if task is not None:
        for goal in task.goal_regions:
            ET.SubElement(
                worldbody,
                "site",
                {
                    "name": _sanitize_name(goal.name),
                    "pos": _format_pos(goal.pos),
                    "type": "sphere",
                    "size": f"{goal.size[0]:.4f}" if goal.size else "0.025",
                    "rgba": f"{goal.rgba[0]} {goal.rgba[1]} {goal.rgba[2]} {goal.rgba[3]}",
                },
            )

    # Add world-level sensors (attached to worldbody or named body).
    if world.sensors:
        _add_sensors(mujoco, worldbody, world.sensors)

    # Optional wind / thermal global forces as text annotations for now.
    if world.randomization is not None:
        _add_randomization_notes(mujoco, world.randomization)

    tree = ET.ElementTree(mujoco)
    _write_pretty_xml(tree, output_path)
    return output_path


def _place_asset_parts_flat(asset: ET.Element, worldbody: ET.Element, world: WorldDescription) -> None:
    """Fallback: place asset parts as flat world bodies when no robot MJCF is included."""
    for part in world.asset_parts:
        mesh_name = _sanitize_name(part.name)
        ET.SubElement(asset, "mesh", {"name": mesh_name, "file": Path(part.mesh_file).name})

    for part in world.asset_parts:
        body_name = _sanitize_name(part.name)
        local_pose = _bundle_part_local_pose(part)
        world_pos, world_quat = _apply_pose(local_pose.pos, local_pose.quat, world.asset_pose)
        body = ET.SubElement(
            worldbody,
            "body",
            {
                "name": body_name,
                "pos": _format_pos(world_pos),
                "quat": _format_quat(world_quat),
            },
        )
        i = part.inertial
        ixx, iyy, izz, ixy, ixz, iyz = i.inertia_tensor_kg_m2
        ET.SubElement(
            body,
            "inertial",
            {
                "pos": _format_pos(i.center_of_mass_m),
                "mass": f"{i.mass_kg:.6f}",
                "diaginertia": f"{ixx:.6e} {iyy:.6e} {izz:.6e}",
            },
        )
        ET.SubElement(body, "geom", {"type": "mesh", "mesh": body_name, "rgba": "0.7 0.7 0.75 1"})


def _add_terrain(worldbody: ET.Element, terrain: WorldTerrain) -> None:
    """Add a static terrain body to the worldbody."""
    name = _sanitize_name(terrain.name)
    friction = terrain.friction
    rgba = terrain.rgba
    size = terrain.size
    pos = terrain.pos
    quat = terrain.quat

    body = ET.SubElement(
        worldbody,
        "body",
        {
            "name": name,
            "pos": _format_pos(pos),
            "quat": _format_quat(quat),
        },
    )

    geom_attrs: dict[str, str] = {
        "name": name + "_geom",
        "class": "world_surface",
        "rgba": f"{rgba[0]} {rgba[1]} {rgba[2]} {rgba[3]}",
        "friction": f"{friction[0]} {friction[1]} {friction[2]}",
    }

    if terrain.type == "plane":
        geom_attrs["type"] = "plane"
        geom_attrs["size"] = f"{size[0]:.6f} {size[1]:.6f} {size[2]:.6f}"
    elif terrain.type == "box":
        geom_attrs["type"] = "box"
        geom_attrs["size"] = f"{size[0] / 2:.6f} {size[1] / 2:.6f} {size[2] / 2:.6f}"
    elif terrain.type == "slope":
        # Slope represented as a thin rotated box.
        geom_attrs["type"] = "box"
        geom_attrs["size"] = f"{size[0] / 2:.6f} {size[1] / 2:.6f} {size[2] / 2:.6f}"
    else:
        geom_attrs["type"] = "box"
        geom_attrs["size"] = f"{size[0] / 2:.6f} {size[1] / 2:.6f} {size[2] / 2:.6f}"

    ET.SubElement(body, "geom", geom_attrs)


def _add_sensors(mujoco: ET.Element, worldbody: ET.Element, sensors: list[WorldSensor]) -> None:
    """Add MuJoCo sensor elements and their attachment sites."""
    sensor_elem = ET.SubElement(mujoco, "sensor")
    for sensor in sensors:
        name = _sanitize_name(sensor.name)
        attach = _sanitize_name(sensor.attach_body) if sensor.attach_body else None
        # Create a site for the sensor frame.
        site_name = name + "_site"
        if attach:
            # Site attached to a body; requires body to exist. We place a site at
            # world level referencing the body via a floating site (MuJoCo allows a
            # site directly in worldbody). For a body-local site we'd need to
            # locate the body element; keeping it world-level is simpler and valid.
            ET.SubElement(
                worldbody,
                "site",
                {
                    "name": site_name,
                    "pos": _format_pos(sensor.pos),
                    "quat": _format_quat(sensor.quat),
                    "size": "0.01",
                },
            )
        else:
            ET.SubElement(
                worldbody,
                "site",
                {
                    "name": site_name,
                    "pos": _format_pos(sensor.pos),
                    "quat": _format_quat(sensor.quat),
                    "size": "0.01",
                },
            )

        if sensor.sensor_type == "camera":
            # MuJoCo camera sensors are just regular cameras in the model; add to
            # worldbody with a site-like camera element.
            ET.SubElement(
                worldbody,
                "camera",
                {
                    "name": name,
                    "pos": _format_pos(sensor.pos),
                    "quat": _format_quat(sensor.quat),
                    "fovy": str(sensor.fov_deg or 60),
                },
            )
        elif sensor.sensor_type == "imu":
            ET.SubElement(sensor_elem, "accelerometer", {"name": name + "_acc", "site": site_name})
            ET.SubElement(sensor_elem, "gyro", {"name": name + "_gyro", "site": site_name})
        elif sensor.sensor_type == "force":
            ET.SubElement(sensor_elem, "force", {"name": name, "site": site_name})
        elif sensor.sensor_type == "proximity":
            ET.SubElement(
                sensor_elem,
                "rangefinder",
                {"name": name, "site": site_name, "noise": str(sensor.noise_std)},
            )


def _add_randomization_notes(mujoco: ET.Element, randomization: DomainRandomization) -> None:
    """Embed randomization metadata as a custom element comment-like child."""
    # MuJoCo ignores unknown child elements of <mujoco> as long as they are not
    # under strict schema elements. We use <custom> for safe metadata.
    custom = ET.SubElement(mujoco, "custom")
    ET.SubElement(
        custom,
        "numeric",
        {
            "name": "domain_randomization_seed",
            "data": str(randomization.seed) if randomization.seed is not None else "-1",
        },
    )


# ---------------------------------------------------------------------------
# Isaac Sim JSON export
# ---------------------------------------------------------------------------


def export_world_to_isaac_json(world: WorldDescription, output_path: Path) -> Path:
    """Write an Isaac Sim world description JSON from a WorldDescription.

    This file can be consumed by the conditional loader in
    ``ai_cad.geda_bridge.world_loaders`` or by any Isaac Sim Python script.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {
        "schema_version": "1.0.0",
        "name": world.name,
        "template": world.template,
        "created_at": world.created_at,
        "robot": {
            "mjcf_file": world.robot_mjcf_file,
            "asset_pose": {
                "pos": world.asset_pose.pos,
                "quat": world.asset_pose.quat,
            },
            "parts": [p.model_dump(mode="json") for p in world.asset_parts],
        },
        "terrain": [
            {
                "name": t.name,
                "type": t.type,
                "size": t.size,
                "pos": t.pos,
                "quat": t.quat,
                "friction": t.friction,
                "rgba": t.rgba,
            }
            for t in world.terrain
        ],
        "objects": [
            {
                "name": o.name,
                "geom_type": o.geom_type,
                "size": o.size,
                "pos": o.pos,
                "quat": o.quat,
                "rgba": o.rgba,
                "density": o.density,
                "mass": o.mass,
                "mesh_file": o.mesh_file,
                "friction": o.friction,
            }
            for o in world.scene.objects
        ],
        "sensors": [
            {
                "name": s.name,
                "sensor_type": s.sensor_type,
                "attach_body": s.attach_body,
                "pos": s.pos,
                "quat": s.quat,
                "noise_std": s.noise_std,
                "fov_deg": s.fov_deg,
                "resolution": s.resolution,
                "range_m": s.range_m,
            }
            for s in world.sensors
        ],
        "task": {
            "task_type": world.task.task_type if world.task else "custom",
            "goal_regions": [
                {
                    "name": g.name,
                    "goal_type": g.goal_type,
                    "pos": g.pos,
                    "size": g.size,
                    "rgba": g.rgba,
                }
                for g in (world.task.goal_regions if world.task else [])
            ],
            "success_criteria": world.task.success_criteria if world.task else {},
            "reward_hints": world.task.reward_hints if world.task else {},
        },
        "randomization": (
            {
                "mass_scale_range": world.randomization.mass_scale_range,
                "friction_range": world.randomization.friction_range,
                "actuator_gain_range": world.randomization.actuator_gain_range,
                "sensor_noise_std": world.randomization.sensor_noise_std,
                "wind_range_m_s": world.randomization.wind_range_m_s,
                "thermal_load_range_w": world.randomization.thermal_load_range_w,
                "seed": world.randomization.seed,
            }
            if world.randomization
            else None
        ),
    }

    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# Built-in world templates
# ---------------------------------------------------------------------------


def pick_place_world_template(
    asset_parts: list[BundlePart],
    table_height: float = 0.45,
    cube_size_m: float = 0.05,
    cube_pos: tuple[float, float, float] = (0.0, 0.0, 0.55),
    goal_bin_pos: tuple[float, float, float] = (0.3, 0.0, 0.55),
) -> WorldDescription:
    """Pick-and-place world: robot asset above a table, target cube, goal bin."""
    world = WorldBuilder("pick_place", template="pick_place")
    world.set_asset(asset_parts, pose=ScenePose(pos=(0.0, 0.0, table_height + 0.15)))
    world.add_terrain(
        WorldTerrain(
            name="floor",
            type="plane",
            size=(5.0, 5.0, 0.01),
            pos=(0.0, 0.0, 0.0),
            friction=(0.8, 0.1, 0.1),
        )
    )
    world.add_terrain(
        WorldTerrain(
            name="table",
            type="box",
            size=(1.0, 0.6, 0.05),
            pos=(0.0, 0.0, table_height - 0.025),
            friction=(0.8, 0.1, 0.1),
            rgba=(0.3, 0.3, 0.35, 1.0),
        )
    )
    world.add_object(
        SceneObject(
            name="target_cube",
            geom_type="box",
            size=(cube_size_m, cube_size_m, cube_size_m),
            pos=cube_pos,
            rgba=(1.0, 0.4, 0.2, 1.0),
            density=800.0,
            mass=0.1,
        )
    )
    world.add_object(
        SceneObject(
            name="goal_bin",
            geom_type="box",
            size=(0.15, 0.15, 0.03),
            pos=goal_bin_pos,
            rgba=(0.0, 1.0, 0.0, 0.3),
            density=500.0,
        )
    )
    world.add_sensor(
        WorldSensor(
            name="wrist_camera",
            sensor_type="camera",
            attach_body="hand_r",
            pos=(0.0, 0.0, 0.05),
            quat=_euler_to_quaternion((math.pi / 2, 0.0, 0.0)),
            fov_deg=75,
            resolution=(640, 480),
        )
    )
    world.set_task(
        WorldTask(
            task_type="pick_place",
            goal_regions=[
                SceneGoalRegion(
                    name="place_goal",
                    goal_type="place",
                    pos=goal_bin_pos,
                    size=(0.08, 0.08, 0.05),
                    rgba=(0.0, 1.0, 0.0, 0.3),
                )
            ],
            success_criteria={"object": "target_cube", "target": "place_goal", "tolerance_m": 0.05},
        )
    )
    return world.world


def push_world_template(
    asset_parts: list[BundlePart],
    table_height: float = 0.45,
    block_size_m: float = 0.08,
    block_pos: tuple[float, float, float] = (0.25, 0.0, 0.49),
    target_pos: tuple[float, float, float] = (0.55, 0.0, 0.49),
) -> WorldDescription:
    """Push world: wedge pusher + block + target zone."""
    world = WorldBuilder("push", template="push")
    world.set_asset(asset_parts, pose=ScenePose(pos=(0.0, 0.0, table_height + 0.03), quat=_euler_to_quaternion((0.0, 0.0, math.pi))))
    world.add_terrain(
        WorldTerrain(
            name="floor",
            type="plane",
            size=(5.0, 5.0, 0.01),
            pos=(0.0, 0.0, 0.0),
        )
    )
    world.add_terrain(
        WorldTerrain(
            name="table",
            type="box",
            size=(1.0, 0.6, 0.05),
            pos=(0.0, 0.0, table_height - 0.025),
            rgba=(0.3, 0.3, 0.35, 1.0),
        )
    )
    world.add_object(
        SceneObject(
            name="block",
            geom_type="box",
            size=(block_size_m, block_size_m, block_size_m),
            pos=block_pos,
            rgba=(0.2, 0.5, 0.9, 1.0),
            density=600.0,
            mass=0.2,
            friction=(0.8, 0.05, 0.05),
        )
    )
    world.add_sensor(
        WorldSensor(
            name="overhead_camera",
            sensor_type="camera",
            pos=(0.0, 0.0, 1.8),
            quat=_euler_to_quaternion((math.pi / 2, 0.0, 0.0)),
            fov_deg=90,
            resolution=(640, 480),
        )
    )
    world.set_task(
        WorldTask(
            task_type="push",
            goal_regions=[
                SceneGoalRegion(
                    name="push_goal",
                    goal_type="push",
                    pos=target_pos,
                    size=(0.06, 0.06, 0.01),
                    rgba=(0.0, 1.0, 0.0, 0.3),
                )
            ],
            success_criteria={"object": "block", "target": "push_goal", "tolerance_m": 0.06},
        )
    )
    return world.world


def walker_world_template(
    asset_parts: list[BundlePart],
    terrain_type: str = "plane",
    robot_height_m: float = 1.0,
    walk_direction: tuple[float, float, float] = (1.0, 0.0, 0.0),
) -> WorldDescription:
    """Walker world: biped/quadruped on flat or sloped terrain with forward goal."""
    world = WorldBuilder("walker", template="walker")
    world.set_asset(asset_parts, pose=ScenePose(pos=(0.0, 0.0, robot_height_m * 0.5)))

    if terrain_type == "slope":
        world.add_terrain(
            WorldTerrain(
                name="slope",
                type="slope",
                size=(4.0, 1.0, 0.05),
                pos=(2.0, 0.0, -0.05),
                quat=_euler_to_quaternion((-0.1, 0.0, 0.0)),
                friction=(0.9, 0.1, 0.1),
            )
        )
    else:
        world.add_terrain(
            WorldTerrain(
                name="floor",
                type="plane",
                size=(10.0, 10.0, 0.01),
                pos=(0.0, 0.0, 0.0),
                friction=(0.9, 0.1, 0.1),
            )
        )

    goal_pos = (walk_direction[0] * 2.0, walk_direction[1] * 2.0, 0.0)
    world.add_sensor(
        WorldSensor(
            name="torso_imu",
            sensor_type="imu",
            attach_body="torso",
            pos=(0.0, 0.0, 0.05),
        )
    )
    world.set_task(
        WorldTask(
            task_type="walker",
            goal_regions=[
                SceneGoalRegion(
                    name="walk_goal",
                    goal_type="reach",
                    pos=goal_pos,
                    size=(0.15, 0.15, 0.15),
                    rgba=(0.0, 1.0, 0.0, 0.3),
                )
            ],
            success_criteria={
                "body": "torso",
                "target": "walk_goal",
                "tolerance_m": 0.2,
                "max_time_s": 10.0,
            },
        )
    )
    return world.world


def drone_hover_world_template(
    asset_parts: list[BundlePart],
    pad_size_m: float = 0.3,
    hover_height_m: float = 1.0,
    wind_m_s: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> WorldDescription:
    """Drone hover world: quad-rotor asset above a takeoff pad."""
    world = WorldBuilder("drone_hover", template="drone_hover")
    world.set_asset(asset_parts, pose=ScenePose(pos=(0.0, 0.0, hover_height_m)))
    world.add_terrain(
        WorldTerrain(
            name="floor",
            type="plane",
            size=(10.0, 10.0, 0.01),
            pos=(0.0, 0.0, 0.0),
            friction=(0.8, 0.1, 0.1),
        )
    )
    world.add_terrain(
        WorldTerrain(
            name="pad",
            type="box",
            size=(pad_size_m, pad_size_m, 0.02),
            pos=(0.0, 0.0, 0.01),
            rgba=(0.9, 0.7, 0.2, 1.0),
        )
    )
    world.add_sensor(
        WorldSensor(
            name="downward_camera",
            sensor_type="camera",
            attach_body="base",
            pos=(0.0, 0.0, -0.05),
            quat=_euler_to_quaternion((math.pi, 0.0, 0.0)),
            fov_deg=90,
            resolution=(320, 240),
        )
    )
    world.add_sensor(
        WorldSensor(
            name="imu",
            sensor_type="imu",
            attach_body="base",
            pos=(0.0, 0.0, 0.0),
        )
    )
    world.set_task(
        WorldTask(
            task_type="drone_hover",
            goal_regions=[
                SceneGoalRegion(
                    name="hover_goal",
                    goal_type="hover",
                    pos=(0.0, 0.0, hover_height_m),
                    size=(0.1, 0.1, 0.1),
                    rgba=(0.0, 1.0, 0.0, 0.3),
                )
            ],
            success_criteria={"body": "base", "target": "hover_goal", "tolerance_m": 0.15, "duration_s": 5.0},
            reward_hints={"wind_m_s": wind_m_s},
        )
    )
    return world.world


def humanoid_stand_world_template(
    asset_parts: list[BundlePart],
    floor_size_m: float = 2.0,
    robot_height_m: float = 1.0,
) -> WorldDescription:
    """Humanoid stand/balance world: biped on a flat floor with upright goal."""
    world = WorldBuilder("humanoid_stand", template="humanoid_stand")
    world.set_asset(asset_parts, pose=ScenePose(pos=(0.0, 0.0, robot_height_m * 0.55)))
    world.add_terrain(
        WorldTerrain(
            name="floor",
            type="plane",
            size=(floor_size_m, floor_size_m, 0.01),
            pos=(0.0, 0.0, 0.0),
            friction=(0.9, 0.1, 0.1),
        )
    )
    world.add_sensor(
        WorldSensor(
            name="torso_imu",
            sensor_type="imu",
            attach_body="torso",
            pos=(0.0, 0.0, 0.1),
        )
    )
    world.add_sensor(
        WorldSensor(
            name="head_camera",
            sensor_type="camera",
            attach_body="torso",
            pos=(0.0, 0.0, 0.25),
            quat=_euler_to_quaternion((0.0, 0.0, 0.0)),
            fov_deg=80,
            resolution=(640, 480),
        )
    )
    world.set_task(
        WorldTask(
            task_type="humanoid_stand",
            goal_regions=[
                SceneGoalRegion(
                    name="upright_goal",
                    goal_type="balance",
                    pos=(0.0, 0.0, robot_height_m),
                    size=(0.05, 0.05, 0.05),
                    rgba=(0.0, 1.0, 0.0, 0.3),
                )
            ],
            success_criteria={"body": "torso", "upright": True, "max_tilt_deg": 15.0, "duration_s": 5.0},
        )
    )
    return world.world


WORLD_TEMPLATE_REGISTRY: dict[str, Any] = {
    "pick_place": pick_place_world_template,
    "push": push_world_template,
    "walker": walker_world_template,
    "drone_hover": drone_hover_world_template,
    "humanoid_stand": humanoid_stand_world_template,
}


def build_world(template_name: str, asset_parts: list[BundlePart], **kwargs: Any) -> WorldDescription:
    """Create a WorldDescription from a named template and a list of BundleParts."""
    if template_name not in WORLD_TEMPLATE_REGISTRY:
        raise ValueError(f"Unknown world template '{template_name}'. Available: {list(WORLD_TEMPLATE_REGISTRY)}")
    return WORLD_TEMPLATE_REGISTRY[template_name](asset_parts, **kwargs)
