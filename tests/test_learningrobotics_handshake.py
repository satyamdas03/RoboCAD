"""End-to-end handshake tests for Phase 15A: RoboCAD → LearningRobotics bundle consumption.

These tests verify that a RoboCAD bundle can be loaded into a standard MuJoCo
scene and survive a 10-second physics rollout without NaNs, explosions, or
excessive penetration. This is the canonical cross-repo acceptance test.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mujoco")

import mujoco

from ai_cad.geda_bridge import (
    build_scene,
    export_bundle_from_shape,
    export_scene_to_mjcf,
    get_capabilities,
    load_bundle_into_mujoco,
    load_bundle_manifest,
    package_bundle_paths,
    run_stability_rollout,
    stability_check_bundle,
)


def _wedge_shape():
    """Return a simple wedge-shaped pusher (mm scale)."""
    build123d = pytest.importorskip("build123d")
    with build123d.BuildPart() as bp:
        # Wedge: triangular prism, 60 mm long, 20 mm wide, 15 mm tall.
        face = build123d.BuildSketch(build123d.Plane.YZ)
        with face:
            build123d.Polygon((0, 0), (20, 0), (0, 15))
        build123d.extrude(amount=60, mode=build123d.Mode.ADD)
    return bp.part


def test_load_bundle_manifest_and_meshes(tmp_path: Path):
    shape = _wedge_shape()
    paths = export_bundle_from_shape(shape, tmp_path / "wedge", name="wedge", material="PLA")
    paths = package_bundle_paths(paths)

    manifest = load_bundle_manifest(paths.directory)
    assert manifest.schema_version == "2.0.0"
    assert len(manifest.parts) == 1
    assert manifest.parts[0].name == "wedge"
    assert (paths.directory / manifest.parts[0].mesh_file).exists()


def test_load_bundle_into_mujoco_with_scene(tmp_path: Path):
    shape = _wedge_shape()
    paths = export_bundle_from_shape(shape, tmp_path / "wedge", name="wedge", material="PLA")
    paths = package_bundle_paths(paths)

    result = load_bundle_into_mujoco(paths.directory, scene_template="wedge_push_block")
    assert result.success, result.errors
    assert result.simulator == "mujoco"
    assert result.nbody >= 3  # world + wedge + table + block
    assert result.model is not None
    assert result.data is not None
    assert result.scene_path is not None
    assert result.scene_path.exists()


def test_run_stability_rollout_10s(tmp_path: Path):
    shape = _wedge_shape()
    paths = export_bundle_from_shape(shape, tmp_path / "wedge", name="wedge", material="PLA")
    paths = package_bundle_paths(paths)

    result = load_bundle_into_mujoco(paths.directory, scene_template="wedge_push_block")
    assert result.success

    rollout = run_stability_rollout(result.model, result.data, duration_seconds=10.0)
    assert rollout["success"], rollout["errors"]
    assert rollout["steps"] == 5000  # dt=0.002
    assert rollout["nan_detected"] is False
    assert rollout["max_penetration_mm"] < 5.0
    assert abs(rollout["energy_drift"]) < 1.0  # No explosive energy growth


def test_stability_check_bundle_high_level(tmp_path: Path):
    shape = _wedge_shape()
    paths = export_bundle_from_shape(shape, tmp_path / "wedge", name="wedge", material="PLA")
    paths = package_bundle_paths(paths)

    check = stability_check_bundle(paths.directory, scene_template="wedge_push_block", duration_seconds=10.0)
    assert check["success"], check["errors"]
    assert check["simulator"] == "mujoco"
    assert check["nbody"] >= 3
    assert check["scene_path"] is not None
    assert check["rollout"]["steps"] == 5000


def test_load_bundle_into_isaac_sim_missing_dependency(tmp_path: Path):
    from ai_cad.geda_bridge.loader import load_bundle_into_isaac_sim

    shape = _wedge_shape()
    paths = export_bundle_from_shape(shape, tmp_path / "wedge", name="wedge", material="PLA")
    paths = package_bundle_paths(paths)

    result = load_bundle_into_isaac_sim(paths.directory)
    # Should fail gracefully because Isaac Sim is not installed in pytest env.
    assert result.success is False
    assert "Isaac Sim not available" in result.errors[0]


def test_capabilities_registry():
    caps = get_capabilities()
    assert caps["bundle_schema_version"] == "2.0.0"
    assert "mujoco" in caps["supported_simulators"]
    assert "wedge_push_block" in caps["supported_scene_templates"]
    assert "wedge" in caps["supported_part_families"]
    assert "GET /capabilities" in caps["endpoints"].values()


def test_scene_without_template_uses_mjcf(tmp_path: Path):
    shape = _wedge_shape()
    paths = export_bundle_from_shape(shape, tmp_path / "wedge", name="wedge", material="PLA")
    paths = package_bundle_paths(paths)

    result = load_bundle_into_mujoco(paths.directory)
    assert result.success, result.errors
    assert result.nbody >= 2  # world + wedge
