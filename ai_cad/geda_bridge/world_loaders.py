"""Reference loaders for Phase 24 world descriptions.

Provides MuJoCo and Isaac Sim ingestion of a ``WorldDescription`` plus a short
replay helper used by the frontend inspection endpoint.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ai_cad.geda_bridge.loader import BundleLoadResult, load_bundle_manifest
from ai_cad.geda_bridge.runtime_validator import validate_bundle_with_mujoco
from ai_cad.geda_bridge.world_builder import (
    WorldDescription,
    build_world,
    export_world_to_isaac_json,
    export_world_to_mjcf,
    resolve_world_body_aliases,
)

try:
    import mujoco
except Exception:  # pragma: no cover - optional dependency
    mujoco = None


def _world_description_from_bundle(
    bundle_dir: Path,
    template: str,
    **kwargs: Any,
) -> WorldDescription:
    """Build a WorldDescription from a bundle directory and template name."""
    bundle_dir = Path(bundle_dir)
    manifest = load_bundle_manifest(bundle_dir)
    world = build_world(template, manifest.parts, **kwargs)
    world.robot_mjcf_file = manifest.mjcf_file or "model.mjcf"
    return world


def load_world_into_mujoco(
    world: WorldDescription,
    output_dir: Path,
) -> BundleLoadResult:
    """Write a world MJCF and load it into MuJoCo.

    The robot asset is included from the bundle's own MJCF so articulated joints,
    actuators, and sensors are preserved.
    """
    result = BundleLoadResult(simulator="mujoco")

    if mujoco is None:
        result.errors.append("mujoco is not installed")
        return result

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_path = output_dir / f"world_{world.template}.mjcf"

    try:
        # Resolve canonical body aliases (e.g. "torso" -> "torso_plate") using the
        # included robot MJCF so that sensors and task criteria reference real bodies.
        resolved = resolve_world_body_aliases(world, mjcf_path=scene_path)
        export_world_to_mjcf(resolved, scene_path)
        result.scene_path = scene_path
        result.scene_description = resolved.scene
    except Exception as exc:
        result.errors.append(f"Failed to export world MJCF: {exc}")
        return result

    try:
        model = mujoco.MjModel.from_xml_path(str(scene_path))
        data = mujoco.MjData(model)
        result.success = True
        result.model = model
        result.data = data
        result.nbody = int(getattr(model, "nbody", 0))
    except Exception as exc:
        result.errors.append(f"Failed to load world MJCF: {exc}")

    return result


def load_world_into_isaac_sim(
    world: WorldDescription,
    output_dir: Path,
    world_settings: dict[str, Any] | None = None,
) -> BundleLoadResult:
    """Write an Isaac Sim JSON world description and load it if Isaac Sim is available."""
    result = BundleLoadResult(simulator="isaac_sim")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"world_{world.template}.isaac.json"

    try:
        # Resolve body aliases against the MuJoCo robot file (if available) so the
        # Isaac JSON references real body names.
        resolved = resolve_world_body_aliases(world, mjcf_path=json_path)
        export_world_to_isaac_json(resolved, json_path)
        result.scene_path = json_path
        result.scene_description = resolved.scene
    except Exception as exc:
        result.errors.append(f"Failed to export Isaac Sim JSON: {exc}")
        return result

    # Try common Isaac Sim import paths.
    isaac_available = False
    for module in ("isaacsim", "omni", "omni.isaac.core"):
        try:
            __import__(module)
            isaac_available = True
            break
        except Exception:
            continue

    if not isaac_available:
        result.warnings.append("Isaac Sim not available in this Python environment; JSON exported for later load")
        return result

    try:
        from omni.isaac.core import World  # type: ignore[import-not-found]

        settings = world_settings or {
            "stage_units_in_meters": 1.0,
            "physics_dt": 1 / 500,
            "rendering_dt": 1 / 60,
        }
        world_obj = World(**settings)
        result.success = True
        result.model = world_obj
        result.nbody = 1 + len(world.terrain) + len(world.scene.objects)
    except Exception as exc:
        result.errors.append(f"Isaac Sim world construction failed: {exc}")

    return result


def run_world_replay(
    mjcf_path: Path | str,
    duration_seconds: float = 5.0,
    fps: float = 20.0,
    body_names: list[str] | None = None,
    capture_contacts: bool = True,
    capture_sensors: bool = True,
    capture_actuators: bool = True,
) -> dict[str, Any]:
    """Run a short MuJoCo rollout and return a rich sparse trajectory.

    Returns a dict with:
      - success (bool)
      - duration_seconds (float)
      - fps (float)
      - times (list[float])
      - bodies (dict[str, list[pos, vel, quat]]) — world positions, linear
        velocities, and orientations per sampled frame
      - contacts (list[dict]) — contact forces at sample frames (if enabled)
      - sensors (dict[str, list[float | list[float]]]) — MuJoCo sensor data
      - actuators (dict[str, list[float]]) — control inputs and actuator forces
      - errors (list[str])
    """
    result: dict[str, Any] = {
        "success": False,
        "duration_seconds": duration_seconds,
        "fps": fps,
        "times": [],
        "bodies": {},
        "contacts": [],
        "sensors": {},
        "actuators": {},
        "saliency": {},
        "errors": [],
    }

    if mujoco is None:
        result["errors"].append("mujoco is not installed")
        return result

    mjcf_path = Path(mjcf_path)
    if not mjcf_path.exists():
        result["errors"].append(f"MJCF not found: {mjcf_path}")
        return result

    try:
        model = mujoco.MjModel.from_xml_path(str(mjcf_path))
        data = mujoco.MjData(model)
    except Exception as exc:
        result["errors"].append(f"Failed to load MJCF for replay: {exc}")
        return result

    dt = float(model.opt.timestep)
    total_steps = max(1, int(round(duration_seconds / dt)))
    sample_interval = max(1, int(round(1.0 / (fps * dt))))

    mujoco.mj_forward(model, data)

    # Pre-resolve body ids if requested.
    body_ids: dict[str, int] = {}
    if body_names:
        for name in body_names:
            try:
                body_ids[name] = model.body(name).id
            except Exception:
                pass

    # Pre-resolve actuator and sensor ids if enabled.
    actuator_ids: dict[str, int] = {}
    if capture_actuators and model.nu > 0:
        for i in range(model.nu):
            try:
                aname = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
                actuator_ids[aname] = i
            except Exception:
                pass

    sensor_ids: dict[str, int] = {}
    sensor_addr: dict[str, int] = {}
    if capture_sensors and model.nsensordata > 0:
        for i in range(model.nsensor):
            try:
                sname = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_SENSOR, i)
                stype = model.sensor_type[i]
                # Skip user sensors that have no address.
                if stype == mujoco.mjtSensor.mjSENS_USER:
                    continue
                sensor_addr[sname] = int(model.sensor_adr[i])
                sensor_ids[sname] = i
            except Exception:
                pass

    times: list[float] = []
    positions: dict[str, list[Any]] = {name: [] for name in body_ids}
    contact_frames: list[dict[str, Any]] = []
    sensor_frames: dict[str, list[Any]] = {name: [] for name in sensor_ids}
    actuator_frames: dict[str, list[Any]] = {name: [] for name in actuator_ids}
    saliency_acc: dict[str, dict[str, Any]] = {
        name: {"max_vel": 0.0, "max_acc": 0.0, "prev_linvel": None, "max_force": 0.0}
        for name in body_ids
    }

    for step in range(total_steps):
        try:
            mujoco.mj_step(model, data)
        except Exception as exc:
            result["errors"].append(f"mj_step failed at step {step}: {exc}")
            break

        if step % sample_interval == 0:
            t = step * dt
            times.append(t)
            for name, bid in body_ids.items():
                pos = data.xpos[bid]
                quat = data.xquat[bid]
                linvel = data.cvel[bid, :3]
                positions[name].append(
                    {
                        "pos": (float(pos[0]), float(pos[1]), float(pos[2])),
                        "quat": (float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])),
                        "linvel": (float(linvel[0]), float(linvel[1]), float(linvel[2])),
                    }
                )
                vel_mag = float(np.linalg.norm(linvel))
                saliency_acc[name]["max_vel"] = max(saliency_acc[name]["max_vel"], vel_mag)
                prev = saliency_acc[name]["prev_linvel"]
                if prev is not None:
                    delta = linvel - prev
                    acc_mag = float(np.linalg.norm(delta)) / max(dt * sample_interval, 1e-9)
                    saliency_acc[name]["max_acc"] = max(saliency_acc[name]["max_acc"], acc_mag)
                saliency_acc[name]["prev_linvel"] = np.asarray(linvel, dtype=float)

            if capture_contacts and data.ncon > 0:
                frame_contacts: list[dict[str, Any]] = []
                for con_id, con in enumerate(data.contact):
                    force = np.zeros(6)
                    mujoco.mj_contactForce(model, data, con_id, force)
                    force_mag = float(np.linalg.norm(force[:3]))
                    # Attribute contact force to the bodies owning the colliding geoms.
                    for geom_id in (con.geom1, con.geom2):
                        try:
                            body_id = int(model.geom_bodyid[geom_id])
                            body_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
                            if body_name in saliency_acc:
                                saliency_acc[body_name]["max_force"] = max(
                                    saliency_acc[body_name]["max_force"], force_mag
                                )
                        except Exception:
                            pass
                    frame_contacts.append(
                        {
                            "geom1": model.geom(con.geom1).name,
                            "geom2": model.geom(con.geom2).name,
                            "pos": (float(con.pos[0]), float(con.pos[1]), float(con.pos[2])),
                            "force": (float(force[0]), float(force[1]), float(force[2])),
                        }
                    )
                contact_frames.append({"time": t, "contacts": frame_contacts})

            if capture_actuators:
                for name, aid in actuator_ids.items():
                    actuator_frames[name].append(
                        {
                            "ctrl": float(data.ctrl[aid]),
                            "force": float(data.qfrc_actuator[aid]) if aid < len(data.qfrc_actuator) else None,
                        }
                    )

            if capture_sensors:
                for name, addr in sensor_addr.items():
                    dim = model.sensor_dim[sensor_ids[name]]
                    values = data.sensordata[addr : addr + dim]
                    sensor_frames[name].append([float(v) for v in values])

    result["success"] = len(result["errors"]) == 0 and bool(np.all(np.isfinite(data.qpos)))
    result["times"] = times
    result["bodies"] = positions
    result["contacts"] = contact_frames
    result["sensors"] = sensor_frames
    result["actuators"] = actuator_frames
    result["saliency"] = {
        name: {"max_vel": acc["max_vel"], "max_acc": acc["max_acc"], "max_force": acc["max_force"]}
        for name, acc in saliency_acc.items()
    }
    return result
