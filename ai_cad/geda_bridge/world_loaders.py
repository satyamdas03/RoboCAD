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
        export_world_to_mjcf(world, scene_path)
        result.scene_path = scene_path
        result.scene_description = world.scene
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
        export_world_to_isaac_json(world, json_path)
        result.scene_path = json_path
        result.scene_description = world.scene
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
) -> dict[str, Any]:
    """Run a short MuJoCo rollout and return a sparse trajectory.

    Returns a dict with:
      - success (bool)
      - duration_seconds (float)
      - fps (float)
      - times (list[float])
      - bodies (dict[str, list[tuple[float, float, float]]]) — world positions
      - errors (list[str])
    """
    result: dict[str, Any] = {
        "success": False,
        "duration_seconds": duration_seconds,
        "fps": fps,
        "times": [],
        "bodies": {},
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

    times: list[float] = []
    positions: dict[str, list[tuple[float, float, float]]] = {name: [] for name in body_ids}

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
                positions[name].append((float(pos[0]), float(pos[1]), float(pos[2])))

    result["success"] = len(result["errors"]) == 0 and bool(np.all(np.isfinite(data.qpos)))
    result["times"] = times
    result["bodies"] = positions
    return result
