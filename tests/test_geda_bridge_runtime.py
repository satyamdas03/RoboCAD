"""Runtime validation tests for the Phase 14A GEDA Bridge using MuJoCo."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mujoco")

pytestmark = [pytest.mark.mujoco, pytest.mark.heavy]

from ai_cad.geda_bridge import (
    export_bundle_from_shape,
    export_bundle_from_tree,
    package_bundle_paths,
    validate_bundle_with_mujoco,
    verify_bundle,
)
from tests.test_geda_bridge import (
    _make_cube_part,
    _make_cylinder_part,
    _make_l_bracket_part,
)
from ai_cad.feature_tree import (
    Assembly,
    FeatureTree,
    Instance,
    Mate,
    MateEntity,
)


def _assert_runtime_ok(directory: Path, *, expected_mjcf_nbody: int, expected_urdf_nbody: int):
    """Assert MuJoCo can load MJCF/URDF, simulate, and report expected bodies.

    MuJoCo's URDF loader welds fixed-joint children into their parent, so a
    single fixed part collapses to one body (the world) and a two-part assembly
    also collapses to one body. MJCF preserves each explicit <body>, so its
    nbody count includes the implicit world plus each part.
    """
    verification = verify_bundle(directory)
    assert verification.valid, f"Bundle not valid: {verification.errors + verification.warnings}"

    result = validate_bundle_with_mujoco(directory)
    assert result["mujoco_available"] is True
    assert result["mjcf_loadable"] is True, f"MJCF load failed: {result['errors']}"
    assert result["urdf_loadable"] is True, f"URDF load failed: {result['errors']}"
    assert result["sim_steps_ok"] is True, f"Simulation failed: {result['errors']}"
    assert result["mjcf_nbody"] == expected_mjcf_nbody
    assert result["urdf_nbody"] == expected_urdf_nbody


def test_runtime_shape_cube(tmp_path: Path):
    build123d = pytest.importorskip("build123d")
    with build123d.BuildPart() as bp:
        build123d.Box(10, 10, 10)

    paths = export_bundle_from_shape(bp.part, tmp_path / "cube", name="cube", material="PLA")
    paths = package_bundle_paths(paths)
    _assert_runtime_ok(paths.directory, expected_mjcf_nbody=2, expected_urdf_nbody=1)


def test_runtime_shape_cylinder(tmp_path: Path):
    build123d = pytest.importorskip("build123d")
    with build123d.BuildPart() as bp:
        build123d.Cylinder(radius=5, height=20)

    paths = export_bundle_from_shape(bp.part, tmp_path / "cylinder", name="cyl", material="aluminum")
    paths = package_bundle_paths(paths)
    _assert_runtime_ok(paths.directory, expected_mjcf_nbody=2, expected_urdf_nbody=1)


def test_runtime_tree_l_bracket(tmp_path: Path):
    tree = FeatureTree(
        design_id="lbracket_runtime",
        prompt="L bracket",
        created_at="2026-08-27T00:00:00Z",
        parts=[_make_l_bracket_part()],
    )
    paths = export_bundle_from_tree(tree, tmp_path / "bracket", name="bracket")
    paths = package_bundle_paths(paths)
    _assert_runtime_ok(paths.directory, expected_mjcf_nbody=2, expected_urdf_nbody=1)


def test_runtime_tree_two_part_assembly(tmp_path: Path):
    tree = FeatureTree(
        design_id="asm_runtime",
        prompt="two part assembly",
        created_at="2026-08-27T00:00:00Z",
        parts=[
            _make_cube_part("base", size=40.0, material="PLA"),
            _make_cylinder_part("pin", radius=3.0, height=25.0),
        ],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="i1", part_id="base"),
                    Instance(id="i2", part_id="pin", transform={"translation": [10, 0, 20]}),
                ],
                mates=[
                    Mate(
                        id="m1",
                        type="coincident",
                        entities=[MateEntity(instance_id="i1"), MateEntity(instance_id="i2")],
                    )
                ],
            )
        ],
    )
    paths = export_bundle_from_tree(tree, tmp_path / "asm", name="asm")
    paths = package_bundle_paths(paths)
    _assert_runtime_ok(paths.directory, expected_mjcf_nbody=3, expected_urdf_nbody=1)
