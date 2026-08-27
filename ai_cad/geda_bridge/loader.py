"""Reference bundle loaders for the RoboCAD GEDA Bridge.

Phase 15A provides a clean, tested path for `LearningRobotics` (or any downstream
simulator) to consume a RoboCAD bundle:

    from ai_cad.geda_bridge.loader import load_bundle_into_mujoco, run_stability_rollout
    result = load_bundle_into_mujoco(bundle_dir, scene_template="wedge_push_block")
    stability = run_stability_rollout(result.model, duration_seconds=10.0)

The loader is intentionally simulator-agnostic at the API level: it reads the
bundle manifest, resolves mesh paths, and hands the data to simulator-specific
constructors. Currently MuJoCo is implemented; Isaac Sim has a conditional stub.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ai_cad.geda_bridge.models import BundleManifest
from ai_cad.geda_bridge.scene_templates import (
    TEMPLATE_REGISTRY,
    SceneDescription,
    build_scene,
    export_scene_to_mjcf,
)


try:
    import mujoco
except Exception:  # pragma: no cover - optional dependency
    mujoco = None


@dataclass
class BundleLoadResult:
    """Result of loading a bundle into a simulator."""

    success: bool = False
    simulator: str = ""
    model: Any | None = None
    data: Any | None = None
    nbody: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    scene_description: SceneDescription | None = None
    scene_path: Path | None = None


def load_bundle_manifest(bundle_dir: Path) -> BundleManifest:
    """Read and validate a bundle manifest.json."""
    manifest_path = Path(bundle_dir) / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Bundle manifest not found: {manifest_path}")
    import json

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return BundleManifest(**data)


def _verify_bundle_files(bundle_dir: Path, manifest: BundleManifest) -> list[str]:
    """Return warnings for missing mesh files."""
    warnings: list[str] = []
    for part in manifest.parts:
        mesh_path = Path(bundle_dir) / part.mesh_file
        if not mesh_path.exists():
            warnings.append(f"Missing mesh file for part '{part.name}': {part.mesh_file}")
    return warnings


def load_bundle_into_mujoco(
    bundle_dir: Path,
    scene_template: str | None = None,
    scene_path: Path | None = None,
) -> BundleLoadResult:
    """Load a RoboCAD bundle into MuJoCo.

    If `scene_template` is provided, the bundle asset is placed into a standard
    manipulation scene before loading. If `scene_path` is provided, it is used as
    the output MJCF path; otherwise a path next to the manifest is chosen.
    """
    result = BundleLoadResult(simulator="mujoco")

    if mujoco is None:
        result.errors.append("mujoco is not installed")
        return result

    bundle_dir = Path(bundle_dir)
    try:
        manifest = load_bundle_manifest(bundle_dir)
    except Exception as exc:
        result.errors.append(f"Failed to load manifest: {exc}")
        return result

    result.warnings.extend(_verify_bundle_files(bundle_dir, manifest))

    if scene_template:
        if scene_template not in TEMPLATE_REGISTRY:
            result.errors.append(f"Unknown scene template '{scene_template}'")
            return result
        try:
            scene = build_scene(scene_template, manifest.parts)
            result.scene_description = scene
            if scene_path is None:
                scene_path = bundle_dir / f"scene_{scene_template}.mjcf"
            export_scene_to_mjcf(scene, scene_path)
            result.scene_path = scene_path
            load_path = scene_path
        except Exception as exc:
            result.errors.append(f"Failed to compose scene '{scene_template}': {exc}")
            return result
    else:
        mjcf_path = bundle_dir / (manifest.mjcf_file or "model.mjcf")
        if not mjcf_path.exists():
            result.errors.append(f"MJCF file not found: {mjcf_path}")
            return result
        load_path = mjcf_path

    try:
        model = mujoco.MjModel.from_xml_path(str(load_path))
        data = mujoco.MjData(model)
        result.success = True
        result.model = model
        result.data = data
        result.nbody = int(getattr(model, "nbody", 0))
    except Exception as exc:
        result.errors.append(f"Failed to load MJCF '{load_path}': {exc}")

    return result


def run_stability_rollout(
    model: Any,
    data: Any | None = None,
    duration_seconds: float = 10.0,
    check_nan: bool = True,
    check_penetration: bool = True,
    max_penetration_mm: float = 5.0,
) -> dict[str, Any]:
    """Run a physics rollout and report stability metrics.

    Returns a dict with:
      - steps: number of steps taken
      - duration_seconds: requested duration
      - success: True if no fatal errors
      - nan_detected: True if any qpos/qvel became NaN/Inf
      - max_position_m: max |qpos| observed
      - max_velocity_m_s: max |qvel| observed
      - max_penetration_mm: max contact penetration (mm) if contacts exist
      - energy_drift: (final - initial) total energy / max(1e-9, |initial|)
      - errors: list of error strings
    """
    if mujoco is None:
        return {"success": False, "errors": ["mujoco is not installed"], "steps": 0}

    if data is None:
        data = mujoco.MjData(model)

    dt = float(model.opt.timestep)
    steps = max(1, int(round(duration_seconds / dt)))

    errors: list[str] = []
    max_pos = 0.0
    max_vel = 0.0
    max_pen_mm = 0.0

    mujoco.mj_forward(model, data)
    initial_energy = float(data.energy[0] + data.energy[1])

    for step in range(steps):
        try:
            mujoco.mj_step(model, data)
        except Exception as exc:
            errors.append(f"mj_step failed at step {step}: {exc}")
            break

        qpos = np.asarray(data.qpos)
        qvel = np.asarray(data.qvel)
        if check_nan and not (np.all(np.isfinite(qpos)) and np.all(np.isfinite(qvel))):
            errors.append(f"NaN/Inf detected at step {step}")
            break

        max_pos = max(max_pos, float(np.max(np.abs(qpos))) if qpos.size else 0.0)
        max_vel = max(max_vel, float(np.max(np.abs(qvel))) if qvel.size else 0.0)

        if check_penetration and data.ncon > 0:
            for con in data.contact:
                # MuJoCo contact distance > 0 means separation; < 0 means penetration.
                pen_mm = abs(float(con.dist)) * 1000.0 if con.dist < 0 else 0.0
                max_pen_mm = max(max_pen_mm, pen_mm)

    final_energy = float(data.energy[0] + data.energy[1])
    energy_drift = (final_energy - initial_energy) / max(1e-9, abs(initial_energy))

    success = len(errors) == 0 and (not check_nan or np.all(np.isfinite(data.qpos)))
    if max_pen_mm > max_penetration_mm:
        errors.append(f"Max contact penetration {max_pen_mm:.3f} mm exceeds {max_penetration_mm} mm")
        success = False

    return {
        "success": success,
        "steps": step + 1,
        "duration_seconds": duration_seconds,
        "nan_detected": not np.all(np.isfinite(data.qpos)) or not np.all(np.isfinite(data.qvel)),
        "max_position_m": max_pos,
        "max_velocity_m_s": max_vel,
        "max_penetration_mm": max_pen_mm,
        "energy_drift": energy_drift,
        "errors": errors,
    }


def load_bundle_into_isaac_sim(bundle_dir: Path, scene_template: str | None = None) -> BundleLoadResult:
    """Conditional loader stub for NVIDIA Isaac Sim.

    Returns a successful result only if `isaacsim` or `omni` modules are
    importable. Otherwise returns an error result documenting the missing
    dependency. This keeps Phase 15A testable on machines without Isaac Sim
    installed while providing the exact integration point for `LearningRobotics`.
    """
    result = BundleLoadResult(simulator="isaac_sim")

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
        result.errors.append("Isaac Sim not available in this Python environment")
        return result

    try:
        manifest = load_bundle_manifest(bundle_dir)
        result.warnings.extend(_verify_bundle_files(bundle_dir, manifest))
        # Actual Isaac Sim world construction is environment-specific and is
        # left to the consumer; this function proves the contract point.
        result.success = True
        result.nbody = len(manifest.parts)
    except Exception as exc:
        result.errors.append(f"Failed to read bundle for Isaac Sim: {exc}")

    return result


def stability_check_bundle(
    bundle_dir: Path,
    scene_template: str = "wedge_push_block",
    duration_seconds: float = 10.0,
) -> dict[str, Any]:
    """High-level helper: load a bundle into a standard scene and run stability.

    This is the canonical end-to-end handshake test used by `LearningRobotics`.
    """
    load_result = load_bundle_into_mujoco(bundle_dir, scene_template=scene_template)
    if not load_result.success:
        return {
            "success": False,
            "simulator": load_result.simulator,
            "errors": load_result.errors,
            "warnings": load_result.warnings,
        }

    rollout = run_stability_rollout(
        load_result.model,
        load_result.data,
        duration_seconds=duration_seconds,
    )

    return {
        "success": rollout["success"],
        "simulator": load_result.simulator,
        "scene_template": scene_template,
        "scene_path": str(load_result.scene_path) if load_result.scene_path else None,
        "nbody": load_result.nbody,
        "rollout": rollout,
        "warnings": load_result.warnings,
        "errors": rollout["errors"],
    }
