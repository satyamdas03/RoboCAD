"""Tests for the Phase 14A GEDA Bridge: MJCF/URDF bundle exporter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.heavy]

from ai_cad.feature_tree import (
    Assembly,
    Feature,
    FeatureTree,
    Instance,
    Mate,
    MateEntity,
    Parameter,
    Part,
    PlaneReference,
    Sketch,
    SketchEntity,
)
from ai_cad.geda_bridge import (
    export_bundle_from_shape,
    export_bundle_from_tree,
    material_density,
    package_bundle_paths,
    shape_to_trimesh,
    verify_bundle,
)
from ai_cad.geda_bridge.models import BundleManifest


def _make_cube_part(part_id="cube", size: float = 10.0, material: str = "PLA") -> Part:
    return Part(
        id=part_id,
        material=material,
        sketches=[
            Sketch(
                id="profile",
                plane=PlaneReference(type="base", name="XY"),
                entities=[
                    SketchEntity(type="rectangle", id="base", center=(0, 0), width=size, height=size)
                ],
            )
        ],
        features=[
            Feature(id="extrude1", type="extrude", sketch_id="profile", parameters={"amount": size, "mode": "add"})
        ],
    )


def _make_cylinder_part(part_id="cylinder", radius: float = 5.0, height: float = 20.0) -> Part:
    return Part(
        id=part_id,
        material="aluminum",
        sketches=[
            Sketch(
                id="profile",
                plane=PlaneReference(type="base", name="XY"),
                entities=[SketchEntity(type="circle", id="shaft", center=(0, 0), radius=radius)],
            )
        ],
        features=[
            Feature(id="extrude1", type="extrude", sketch_id="profile", parameters={"amount": height, "mode": "add"})
        ],
    )


def _make_l_bracket_part(part_id="l_bracket") -> Part:
    return Part(
        id=part_id,
        material="steel",
        sketches=[
            Sketch(
                id="profile",
                plane=PlaneReference(type="base", name="XY"),
                entities=[
                    SketchEntity(type="rectangle", id="leg1", center=(15, 0), width=30, height=10),
                    SketchEntity(type="rectangle", id="leg2", center=(0, 15), width=10, height=30),
                ],
            )
        ],
        features=[
            Feature(id="extrude1", type="extrude", sketch_id="profile", parameters={"amount": 5, "mode": "add"})
        ],
    )


def _make_gripper_jaw_part(part_id="gripper_jaw") -> Part:
    # Phase 14A tests the exporter, not sketch boolean reliability, so keep the jaw as a simple solid block.
    return Part(
        id=part_id,
        material="PLA",
        sketches=[
            Sketch(
                id="profile",
                plane=PlaneReference(type="base", name="XY"),
                entities=[
                    SketchEntity(type="rectangle", id="base", center=(0, 0), width=30, height=10),
                ],
            )
        ],
        features=[
            Feature(id="extrude1", type="extrude", sketch_id="profile", parameters={"amount": 8, "mode": "add"}),
        ],
    )


def _make_assembly_tree_with_duplicate_part() -> FeatureTree:
    part = _make_cube_part("shared_cube", size=10.0)
    return FeatureTree(
        design_id="dup_asm",
        prompt="two cubes",
        created_at="2026-08-29T00:00:00Z",
        parts=[part],
        assemblies=[
            Assembly(
                id="a1",
                instances=[
                    Instance(id="i1", part_id="shared_cube"),
                    Instance(id="i2", part_id="shared_cube", transform={"translation": [20, 0, 0]}),
                ],
            )
        ],
    )


def test_material_density_lookup():
    assert material_density("PLA") > 0
    assert material_density("aluminum") > material_density("PLA")
    assert material_density(None) == material_density("default")


def test_shape_to_trimesh_cube():
    build123d = pytest.importorskip("build123d")
    with build123d.BuildPart() as bp:
        build123d.Box(10, 10, 10)
    mesh = shape_to_trimesh(bp.part, tolerance=0.1)
    assert mesh.is_watertight
    assert mesh.volume > 0


def test_export_bundle_from_shape_cube(tmp_path: Path):
    build123d = pytest.importorskip("build123d")
    with build123d.BuildPart() as bp:
        build123d.Box(10, 10, 10)

    out = tmp_path / "bundle"
    paths = export_bundle_from_shape(bp.part, out, name="cube", material="PLA")
    paths = package_bundle_paths(paths)

    assert paths.manifest_json.exists()
    assert paths.urdf.exists()
    assert paths.mjcf.exists()
    assert paths.zip.exists()

    manifest = BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8")))
    assert len(manifest.parts) == 1
    part = manifest.parts[0]
    assert part.material == "PLA"
    assert part.inertial.mass_kg > 0
    assert pytest.approx(part.inertial.center_of_mass_m, abs=1e-6) == (0.0, 0.0, 0.0)

    verification = verify_bundle(paths.directory)
    assert verification.valid
    assert verification.all_watertight
    assert verification.all_masses_positive
    assert verification.all_inertia_positive_definite


def test_export_bundle_from_shape_cylinder(tmp_path: Path):
    build123d = pytest.importorskip("build123d")
    with build123d.BuildPart() as bp:
        build123d.Cylinder(radius=5, height=20)

    paths = export_bundle_from_shape(bp.part, tmp_path / "bundle", name="cyl", material="aluminum")
    paths = package_bundle_paths(paths)

    manifest = BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8")))
    assert len(manifest.parts) == 1
    com = manifest.parts[0].inertial.center_of_mass_m
    assert abs(com[0]) < 1e-5
    assert abs(com[1]) < 1e-5
    verification = verify_bundle(paths.directory)
    assert verification.valid


def test_export_bundle_from_tree_l_bracket(tmp_path: Path):
    tree = FeatureTree(
        design_id="lbracket1",
        prompt="L bracket",
        created_at="2026-08-25T00:00:00Z",
        parts=[_make_l_bracket_part()],
    )
    paths = export_bundle_from_tree(tree, tmp_path / "bundle", name="bracket")
    paths = package_bundle_paths(paths)

    manifest = BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8")))
    assert len(manifest.parts) == 1
    assert manifest.parts[0].material == "steel"
    assert manifest.parts[0].inertial.mass_kg > 0
    assert verify_bundle(paths.directory).valid


def test_export_bundle_from_tree_two_part_assembly(tmp_path: Path):
    tree = FeatureTree(
        design_id="asm1",
        prompt="two part assembly",
        created_at="2026-08-25T00:00:00Z",
        parts=[_make_cube_part("base", size=40.0, material="PLA"), _make_cylinder_part("pin", radius=3.0, height=25.0)],
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
    paths = export_bundle_from_tree(tree, tmp_path / "bundle", name="asm")
    paths = package_bundle_paths(paths)

    manifest = BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8")))
    assert len(manifest.parts) == 2
    names = {p.name for p in manifest.parts}
    assert len(names) == 2

    urdf_text = paths.urdf.read_text(encoding="utf-8")
    assert '<link name="world"' in urdf_text
    assert len([line for line in urdf_text.splitlines() if '<joint' in line]) == 2

    mjcf_text = paths.mjcf.read_text(encoding="utf-8")
    assert "<mujoco" in mjcf_text
    assert mjcf_text.count("<body ") == 2

    verification = verify_bundle(paths.directory)
    assert verification.valid


def test_export_bundle_from_tree_gripper_jaw(tmp_path: Path):
    tree = FeatureTree(
        design_id="gripper1",
        prompt="gripper jaw",
        created_at="2026-08-25T00:00:00Z",
        parts=[_make_gripper_jaw_part()],
    )
    paths = export_bundle_from_tree(tree, tmp_path / "bundle", name="jaw")
    paths = package_bundle_paths(paths)

    manifest = BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8")))
    assert len(manifest.parts) == 1
    assert manifest.parts[0].inertial.mass_kg > 0
    verification = verify_bundle(paths.directory)
    assert verification.valid


def test_exporter_mjcf_has_mesh_assets(tmp_path: Path):
    build123d = pytest.importorskip("build123d")
    with build123d.BuildPart() as bp:
        build123d.Box(10, 10, 10)

    paths = export_bundle_from_shape(bp.part, tmp_path / "bundle", name="cube")
    mjcf_text = paths.mjcf.read_text(encoding="utf-8")
    assert "<mesh " in mjcf_text
    assert "<geom type=\"mesh\"" in mjcf_text


def test_exporter_urdf_has_inertial_and_visual(tmp_path: Path):
    build123d = pytest.importorskip("build123d")
    with build123d.BuildPart() as bp:
        build123d.Box(10, 10, 10)

    paths = export_bundle_from_shape(bp.part, tmp_path / "bundle", name="cube")
    urdf_text = paths.urdf.read_text(encoding="utf-8")
    assert "<inertial>" in urdf_text
    assert "<inertia " in urdf_text
    assert "<visual>" in urdf_text
    assert "<collision>" in urdf_text


def test_export_bundle_reuses_part_mesh_for_duplicate_instances(tmp_path: Path, monkeypatch):
    tree = _make_assembly_tree_with_duplicate_part()
    exporter = __import__("ai_cad.geda_bridge.exporter", fromlist=["_build_part_mesh"])

    call_count = 0
    original_build = exporter._build_part_mesh

    def _counting_build(part, parameters, output_dir, tolerance=0.1):
        nonlocal call_count
        call_count += 1
        return original_build(part, parameters, output_dir, tolerance)

    monkeypatch.setattr(exporter, "_build_part_mesh", _counting_build)

    paths = export_bundle_from_tree(tree, tmp_path / "bundle", name="dup")
    paths = package_bundle_paths(paths)

    manifest = BundleManifest(**json.loads(paths.manifest_json.read_text(encoding="utf-8")))
    assert len(manifest.parts) == 2
    assert call_count == 1, "Duplicate part instances should reuse a single built mesh"
