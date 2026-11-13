"""A picture of the part and a proxy for its collisions are two different meshes.

The collision mesh is convex hulls, which is right for narrowphase and wrong to look at. This file
pins the visual mesh: it is the part's own surface coarsely tessellated, its size is bounded and
reported, and it is written so the simulator cannot collide it -- which is what makes adding a
picture a change to the picture and not to the physics.
"""
from __future__ import annotations

import numpy as np
import pytest

from ai_cad.compiler.visual import (
    VISUAL_BUDGET_BYTES,
    VISUAL_MAX_TRIANGLES,
    VisualMesh,
    _cluster,
    visual_mesh,
    write_visual_obj,
)

IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def cube(side_m: float):
    from build123d import Box

    return Box(side_m * 1e3, side_m * 1e3, side_m * 1e3).wrapped


def plate_with_bore(side_m: float, wall_m: float, bore_m: float):
    """A plate with a through hole: its convex hull fills the hole, its own surface does not."""
    from build123d import Box, Cylinder, Location, Mode, Part

    plate = Part() + Box(side_m * 1e3, side_m * 1e3, wall_m * 1e3)
    hole = Cylinder(bore_m * 1e3 / 2.0, wall_m * 1e3 * 2.0)
    return (plate - Location((0, 0, 0)) * hole).wrapped


def _part(shape, part_id: str = "p"):
    from types import SimpleNamespace

    from ai_cad.compiler.collision import tessellate

    vertices, faces = tessellate(shape)
    return SimpleNamespace(part_id=part_id, shape=shape, is_solid=True, vertices=vertices, faces=faces)


def _mesh_volume(mesh) -> float:
    v = np.asarray(mesh.vertices)
    f = np.asarray(mesh.faces)
    tri = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(abs(np.einsum("ij,ij->i", tri[0], np.cross(tri[1], tri[2])).sum() / 6.0))


def _assembly(parts, placements):
    from ai_cad.importers.models import (
        ImportedAssembly,
        ImportedInstance,
        ImportedPart,
        PartSignature,
    )

    imported = {
        part_id: ImportedPart(
            part_id=part_id,
            name=part_id,
            signature=PartSignature(
                volume_m3=1e-6,
                surface_area_m2=0.0,
                bbox_min_m=(0.0, 0.0, 0.0),
                bbox_max_m=(0.0, 0.0, 0.0),
                face_count=6,
            ),
            shape=shape,
        )
        for part_id, shape in parts.items()
    }
    instances = [
        ImportedInstance(
            instance_id=instance_id,
            name=instance_id,
            part_id=part_id,
            transform=transform,
            is_reflected=False,
        )
        for instance_id, part_id, transform in placements
    ]
    return ImportedAssembly(parts=imported, instances=instances)


class TestItIsThePartAndNotItsHull:
    def test_a_solid_part_keeps_its_own_volume(self) -> None:
        mesh = visual_mesh(_part(cube(0.04)))
        assert mesh.triangles > 0
        assert _mesh_volume(mesh) == pytest.approx(0.04**3, rel=0.05)

    def test_a_bore_is_visible_to_a_viewer(self) -> None:
        # The collision hull of this part fills the hole; the visual mesh keeps it. That difference
        # is the whole reason the two exist.
        from ai_cad.compiler.collision import collision_mesh

        part = _part(plate_with_bore(0.06, 0.008, 0.03))
        drawn = visual_mesh(part)
        solid = 0.06 * 0.06 * 0.008 - 3.14159 * 0.015**2 * 0.008
        assert _mesh_volume(drawn) == pytest.approx(solid, rel=0.08)
        assert _mesh_volume(drawn) < 0.06 * 0.06 * 0.008 * 0.95

    def test_the_budget_is_enforced_by_clustering_and_reported(self) -> None:
        vertices = np.random.default_rng(0).normal(size=(4000, 3)) * 0.01
        faces = np.arange(3000 * 3).reshape(3000, 3) % len(vertices)
        reduced, reduced_faces, cell = _cluster(vertices, faces, 200)
        assert len(reduced_faces) < 3000
        assert cell > 0.0
        assert len(reduced) < len(vertices)
        # Every surviving vertex moved by at most half a cell, by construction of the snap.
        assert np.all(np.abs(np.diff(np.unique(reduced, axis=0), axis=0)).max() <= cell * 2.0)

    def test_a_mesh_under_budget_is_left_alone(self) -> None:
        vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        faces = np.array([[0, 1, 2], [0, 2, 3]])
        kept, kept_faces, cell = _cluster(vertices, faces, VISUAL_MAX_TRIANGLES)
        assert cell == 0.0
        assert kept.shape == vertices.shape
        assert kept_faces.shape == faces.shape


class TestAddingAPictureDoesNotChangeThePhysics:
    def _bundle(self, visual: bool):
        from ai_cad.compiler.collision import collision_mesh
        from ai_cad.compiler.kinematics import BodyAssignment, DerivedJoint, Skeleton
        from ai_cad.compiler.twin_bundle import build_bundle

        shapes = {"base": cube(0.05), "arm": cube(0.03)}
        asm = _assembly(shapes, [("i0", "base", IDENTITY), ("i1", "arm", IDENTITY)])
        skeleton = Skeleton(
            bodies=[
                BodyAssignment(body_id="base", name="Base", instance_ids=["i0"], part_ids=["base"]),
                BodyAssignment(body_id="arm", name="Arm", instance_ids=["i1"], part_ids=["arm"]),
            ],
            joints=[
                DerivedJoint(
                    joint_id="joint_1",
                    parent_body="base",
                    child_body="arm",
                    axis_point=(0.0, 0.0, 0.05),
                    axis_dir=(0.0, 1.0, 0.0),
                    servo="i0",
                    horn_instance="i0",
                )
            ],
        )
        visuals = {pid: visual_mesh(_part(shape, pid)) for pid, shape in shapes.items()}
        hulls = {pid: collision_mesh(asm.parts[pid]) for pid in shapes}
        model, _, meshes = build_bundle(
            skeleton,
            asm,
            name="toy",
            hull_cache=hulls,
            visual=visuals if visual else None,
        )
        return model, asm, visuals, meshes

    def test_the_visual_geoms_are_not_collided(self, tmp_path) -> None:
        import mujoco

        from ai_cad.compiler.twin_bundle import write_meshes, write_mjcf, write_visual_meshes

        model, asm, visuals, meshes = self._bundle(visual=True)
        assert model.bodies[0].visual_files and model.bodies[0].visual_triangles > 0
        write_meshes(model, asm, meshes, tmp_path / "meshes")
        write_visual_meshes(model, asm, visuals, tmp_path / "meshes")
        path = write_mjcf(model, tmp_path / "model.mjcf")
        compiled = mujoco.MjModel.from_xml_path(str(path))
        visual = [i for i in range(compiled.ngeom) if compiled.geom_contype[i] == 0]
        assert len(visual) == 2
        assert all(compiled.geom_conaffinity[i] == 0 for i in visual)
        assert all(compiled.geom_group[i] == 2 for i in visual)

    def test_the_contact_set_is_identical_with_and_without_pictures(self, tmp_path) -> None:
        import mujoco

        from ai_cad.compiler.twin_bundle import write_meshes, write_mjcf, write_visual_meshes

        plain, asm, visuals, meshes = self._bundle(visual=False)
        write_meshes(plain, asm, meshes, tmp_path / "meshes")
        plain_path = write_mjcf(plain, tmp_path / "plain.mjcf")
        painted, asm2, visuals2, meshes2 = self._bundle(visual=True)
        write_meshes(painted, asm2, meshes2, tmp_path / "meshes")
        write_visual_meshes(painted, asm2, visuals2, tmp_path / "meshes")
        painted_path = write_mjcf(painted, tmp_path / "painted.mjcf")

        counts = []
        for path in (plain_path, painted_path):
            compiled = mujoco.MjModel.from_xml_path(str(path))
            data = mujoco.MjData(compiled)
            mujoco.mj_forward(compiled, data)
            counts.append((int(data.ncon), float(compiled.body_mass.sum())))
        assert counts[0] == counts[1]

    def test_no_visual_meshes_means_no_visual_geoms(self, tmp_path) -> None:
        from ai_cad.compiler.twin_bundle import write_meshes, write_mjcf

        model, asm, _, meshes = self._bundle(visual=False)
        assert model.bodies[0].visual_files == []
        write_meshes(model, asm, meshes, tmp_path / "meshes")
        path = write_mjcf(model, tmp_path / "model.mjcf")
        assert "conaffinity" not in path.read_text(encoding="utf-8")

    def test_a_picture_is_counted_as_a_mesh_the_model_asked_for(self, tmp_path) -> None:
        # Both kinds of file become <mesh> assets, so a count of hulls only reported the pictures as
        # 259 surplus meshes on the SO-101 and failed the check for having more than it expected.
        from ai_cad.compiler.bundle_checks import check_meshes_load
        from ai_cad.compiler.twin_bundle import write_meshes, write_mjcf, write_visual_meshes

        model, asm, visuals, meshes = self._bundle(visual=True)
        write_meshes(model, asm, meshes, tmp_path / "meshes")
        write_visual_meshes(model, asm, visuals, tmp_path / "meshes")
        path = write_mjcf(model, tmp_path / "model.mjcf")
        result = check_meshes_load(path, tmp_path / "meshes", model)
        assert result.status == "pass", result.explanation
        assert result.measured["visual_meshes"] > 0
        assert result.measured["meshes"] == result.threshold["expected_meshes"]


class TestTheSizeIsBoundedAndMeasured:
    def test_the_obj_writer_rounds_to_micrometres(self, tmp_path) -> None:
        mesh = VisualMesh(
            vertices=np.array([[0.0, 0.0, 0.0], [1.2345678, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            faces=np.array([[0, 1, 2]]),
            triangles=1,
        )
        text = write_visual_obj(mesh, tmp_path / "m.obj").read_text(encoding="utf-8")
        assert "v 1.234568 0.000000 0.000000" in text
        assert "f 1 2 3" in text

    def test_the_budget_is_twenty_four_megabytes(self) -> None:
        # Not 5 MB: at 5 MB the SO-101's coarsest part moved 6.83 mm, so the number is a measured
        # fidelity cost rather than a round figure.
        assert VISUAL_BUDGET_BYTES == 24 * 1024 * 1024

    def _dense(self, triangles: int, seed: int = 0) -> "VisualMesh":
        rng = np.random.default_rng(seed)
        vertices = rng.normal(size=(triangles + 2, 3)) * 0.01
        faces = np.arange(triangles * 3).reshape(triangles, 3) % len(vertices)
        return VisualMesh(vertices=vertices, faces=faces, triangles=triangles)

    def test_a_set_over_budget_is_coarsened_until_it_fits(self) -> None:
        # On the real SO-101 the first pass wrote 19.38 MB against a 5 MB budget and only reported
        # the overrun. This is the same arithmetic on a set small enough to run in a second.
        from ai_cad.compiler.visual import estimate_bytes, fit_budget

        meshes = {f"p{i}": self._dense(3000, seed=i) for i in range(12)}
        before = sum(estimate_bytes(m) for m in meshes.values())
        assert before > 1_000_000
        warnings = fit_budget(meshes, budget_bytes=200_000)
        after = sum(estimate_bytes(m) for m in meshes.values())
        assert after <= 200_000, after
        assert warnings == []
        assert all(m.triangles > 0 for m in meshes.values())
        # The reduction is reported per part as the grid cell it ended on.
        assert all(m.cell_m > 0.0 for m in meshes.values())

    def test_a_set_under_budget_is_left_alone(self) -> None:
        from ai_cad.compiler.visual import fit_budget

        meshes = {"p": self._dense(100)}
        warnings = fit_budget(meshes, budget_bytes=VISUAL_BUDGET_BYTES)
        assert warnings == []
        assert meshes["p"].cell_m == 0.0
        assert meshes["p"].triangles == 100

    def test_a_part_used_four_times_is_budgeted_four_times(self) -> None:
        # Meshes are written per placed instance, so budgeting the part-level sum undercounted the
        # SO-101 by about four to one: 5 MB of budget produced a 14 MB directory. Same arithmetic
        # here, one part against four placements.
        from ai_cad.compiler.visual import estimate_bytes, fit_budget

        mesh = self._dense(4000)
        once = {"p": mesh.model_copy(deep=True)}
        assert fit_budget(once, budget_bytes=500_000) == []
        four = {"p": mesh.model_copy(deep=True)}
        assert sum(estimate_bytes(m) for m in four.values()) <= 500_000
        assert fit_budget(four, budget_bytes=500_000, counts={"p": 4}) == []
        assert estimate_bytes(four["p"]) * 4 <= 500_000
        assert four["p"].triangles < once["p"].triangles

    def test_a_set_that_cannot_fit_says_so_rather_than_looping(self) -> None:
        from ai_cad.compiler.visual import fit_budget

        meshes = {"p": self._dense(4000)}
        warnings = fit_budget(meshes, budget_bytes=1)
        assert len(warnings) == 1
        assert "could not be reduced further" in warnings[0]
