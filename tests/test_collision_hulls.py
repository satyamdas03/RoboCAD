"""M3 acceptance for collision geometry: hulls that are closed, convex and load in MuJoCo.

The failure this suite exists to catch is quiet. A mesh that is not closed, or is wound inside-out,
still produces convex hulls and still loads in a simulator; it just lets bodies pass through each
other. So closure, winding and coverage are asserted on shapes whose answer is known.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from ai_cad.compiler.collision import (
    MAX_HULL_VERTICES,
    CollisionError,
    CollisionMesh,
    Hull,
    _closed,
    _triangle_volume,
    bound_point_cloud,
    collision_mesh,
    convex_hull,
    decompose,
    mjcf_body,
    write_assets,
    write_obj,
    tessellate,
)
from ai_cad.importers.models import ImportedPart, PartSignature


def box_part(side_mm: float = 20.0, part_id: str = "box") -> ImportedPart:
    from build123d import Box

    return ImportedPart(
        part_id=part_id,
        name=part_id,
        signature=PartSignature(
            volume_m3=(side_mm**3) * 1e-9,
            surface_area_m2=0.0,
            bbox_min_m=(0.0, 0.0, 0.0),
            bbox_max_m=(0.0, 0.0, 0.0),
            face_count=6,
        ),
        shape=Box(side_mm, side_mm, side_mm).wrapped,
    )


def l_shape_part(part_id: str = "lshape") -> ImportedPart:
    """A genuinely non-convex part: two boxes in an L, one hull cannot cover it without waste."""
    from build123d import Box, Pos

    base = Box(40, 10, 10)
    upright = Pos(15, 0, 10) * Box(10, 10, 20)
    shape = base + upright
    volume = shape.volume
    return ImportedPart(
        part_id=part_id,
        name=part_id,
        signature=PartSignature(
            volume_m3=volume * 1e-9,
            surface_area_m2=0.0,
            bbox_min_m=(0.0, 0.0, 0.0),
            bbox_max_m=(0.0, 0.0, 0.0),
            face_count=12,
        ),
        shape=shape.wrapped,
    )


def signed_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


class TestTessellation:
    def test_a_cube_tessellates_to_the_right_volume_and_closes(self) -> None:
        from build123d import Box

        vertices, faces = tessellate(Box(20, 30, 40).wrapped)
        assert len(vertices) == 8
        assert len(faces) == 12
        assert _closed(vertices, faces) is True
        assert abs(signed_volume(vertices, faces)) * 1e9 == pytest.approx(24000.0, rel=1e-6)

    def test_the_winding_is_outward(self) -> None:
        """A mesh wound inward has the right triangles and the wrong normal, so every contact in a
        simulator is computed on the far side of the surface."""
        from build123d import Box

        vertices, faces = tessellate(Box(20, 30, 40).wrapped)
        assert signed_volume(vertices, faces) > 0.0

    def test_a_cylinder_tessellates_to_its_analytic_volume(self) -> None:
        from build123d import Cylinder

        vertices, faces = tessellate(Cylinder(10, 30).wrapped)
        expected = math.pi * 10**2 * 30
        assert _closed(vertices, faces) is True
        assert abs(signed_volume(vertices, faces)) * 1e9 == pytest.approx(expected, rel=5e-3)

    def test_shared_vertices_are_welded(self) -> None:
        """OCP hands every face its own copy of a shared vertex; without welding the mesh is a soup
        of disconnected triangles and the closure test is meaningless."""
        from build123d import Box

        vertices, _ = tessellate(Box(20, 30, 40).wrapped)
        assert len(vertices) == 8
        assert len(np.unique(np.round(vertices, 12), axis=0)) == 8

    def test_a_shape_with_no_faces_is_refused(self) -> None:
        with pytest.raises(CollisionError, match="zero triangles"):
            tessellate(_empty_compound())


def _empty_compound():
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    return compound


class TestHullCap:
    def test_a_dense_point_cloud_is_capped_and_says_how_far_it_moved(self) -> None:
        """The cap itself, on a cloud built in numpy so it costs milliseconds and runs by default.

        The cap is what stood between a 169 MB bundle and a 2.4 MB one, so it must be covered in the
        default tier. Tessellating a real sphere to feed it is a kernel job that belongs in the
        heavy tier, and the test below it does exactly that.
        """
        import numpy as np

        # A Fibonacci sphere: every point on its own facet, so the raw hull is as dense as the cloud.
        count = 5000
        index = np.arange(count, dtype=float)
        phi = np.arccos(1.0 - 2.0 * (index + 0.5) / count)
        theta = np.pi * (1.0 + 5.0**0.5) * index
        radius = 0.02
        points = radius * np.column_stack(
            [np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)]
        )

        hull = convex_hull(points)
        assert len(hull.vertices) <= MAX_HULL_VERTICES
        assert hull.reduced is True
        assert 0.0 < hull.snap_m < 0.05

    @pytest.mark.heavy
    def test_a_dense_curved_hull_is_decimated_to_the_cap(self) -> None:
        # A sphere tessellated at the collision deflection puts almost every vertex on its own hull.
        # Left alone that hull is a second copy of the CAD: on SO-101 one came to 15.8 MB, which
        # MuJoCo loads and then grinds against for the rest of the run.
        from build123d import Sphere

        vertices, _ = tessellate(Sphere(20.0).wrapped)
        hull = convex_hull(vertices)
        assert len(vertices) > 1000, "the fixture must actually be dense"
        assert len(hull.vertices) <= MAX_HULL_VERTICES
        assert hull.reduced is True
        # Snapping is bounded: every vertex is within half a cell of the true surface, and the cell
        # never grows past the part's own diagonal.
        assert 0.0 < hull.snap_m < 0.05

    def test_a_compact_hull_is_left_alone(self) -> None:
        from build123d import Box

        vertices, _ = tessellate(Box(20, 20, 20).wrapped)
        hull = convex_hull(vertices)
        assert len(hull.vertices) == 8
        assert hull.reduced is False
        assert hull.snap_m == 0.0


class TestPointBudget:
    """The hull is built before the triangle cap is consulted, so the cap cannot bound it.

    A pathological tessellation reached ``convex_hull`` as a whole point cloud and the hull was built
    at that size; the ``COACD_TRIANGLE_LIMIT`` branch is only reached afterwards. The budget bounds the
    operation that actually runs first, and says so when it fires.
    """

    def _cloud(self, count: int) -> np.ndarray:
        rng = np.random.default_rng(0)
        return rng.random((count, 3)) * 0.05

    def test_a_cloud_under_the_budget_is_returned_untouched(self) -> None:
        points = self._cloud(500)
        same, cell = bound_point_cloud(points, budget=1000)
        assert cell == 0.0
        assert same is not None and len(same) == len(points)

    def test_an_oversized_cloud_is_reduced_to_the_budget_and_the_cell_is_reported(self) -> None:
        points = self._cloud(20000)
        reduced, cell = bound_point_cloud(points, budget=500)
        assert len(reduced) <= 500
        assert cell > 0.0
        # Snapping moves a point by at most half a cell, so every kept point is within that of the
        # cloud it came from -- the same bound ``convex_hull`` relies on.
        extent = points.max(axis=0) - points.min(axis=0)
        assert cell < float(np.linalg.norm(extent))

    def test_the_reduction_keeps_every_point_inside_the_reported_bound(self) -> None:
        # The cell is the guarantee the report prints, so it has to be true of every point the hull
        # is built from: a snapped point is at most half a cell from the input point it came from, on
        # each axis, so no point moves further than half a cell diagonal.
        points = self._cloud(20000)
        reduced, cell = bound_point_cloud(points, budget=500)
        nearest = np.sqrt(
            ((reduced[:, None, :] - points[None, :, :]) ** 2).sum(axis=2)
        ).min(axis=1)
        assert float(nearest.max()) <= cell * math.sqrt(3) / 2.0 + 1e-12


class TestDecomposition:
    def test_a_cube_becomes_one_hull_that_matches_its_volume(self) -> None:
        mesh = collision_mesh(box_part())
        assert mesh.hull_count == 1
        assert mesh.closed is True
        assert mesh.fill_ratio == pytest.approx(1.0, abs=0.1)
        assert mesh.warnings == []

    def test_a_non_convex_part_needs_more_than_one_hull(self) -> None:
        """If this ever returns one hull, CoACD has been configured into a single bounding box and
        every concave feature in the robot is a lie."""
        mesh = collision_mesh(l_shape_part())
        assert mesh.hull_count >= 2
        # The hulls cover the L without a large volume of empty space: a single box would be 2.5x.
        assert 0.9 <= mesh.fill_ratio <= 2.0

    def test_the_decomposition_is_deterministic(self) -> None:
        part = l_shape_part()
        first = collision_mesh(part)
        second = collision_mesh(part)
        assert first.hull_count == second.hull_count
        for a, b in zip(first.hulls, second.hulls):
            assert np.allclose(np.array(a.vertices), np.array(b.vertices), atol=1e-9)
            assert a.faces == b.faces

    def test_a_capped_decomposition_says_so(self) -> None:
        mesh = collision_mesh(l_shape_part(), max_hulls=1)
        assert mesh.hull_count == 1
        assert any("hull cap" in w for w in mesh.warnings)

    def test_hulls_are_convex(self) -> None:
        """A hull whose vertices are not their own convex hull is one MuJoCo will collide against
        wrongly, because it treats a mesh geom as convex without checking."""
        import trimesh

        mesh = collision_mesh(l_shape_part())
        for hull in mesh.hulls:
            points = np.array(hull.vertices)
            reference = trimesh.convex.convex_hull(points)
            assert float(reference.volume) == pytest.approx(hull.volume_m3, rel=1e-6)


class TestRefusal:
    def test_a_part_with_no_shape_is_refused(self) -> None:
        part = box_part()
        part.shape = None
        with pytest.raises(CollisionError, match="no shape"):
            collision_mesh(part)

    def test_a_part_that_is_not_a_solid_is_refused(self) -> None:
        part = box_part()
        part.is_solid = False
        with pytest.raises(CollisionError, match="not a closed solid"):
            collision_mesh(part)

    def test_zero_hulls_is_an_error(self) -> None:
        vertices, faces = tessellate(box_part().shape)
        with pytest.raises(CollisionError):
            decompose(vertices, faces, max_hulls=0)


class TestAssets:
    def test_obj_files_are_written_in_metres(self, tmp_path) -> None:
        mesh = collision_mesh(box_part(20.0))
        names = write_assets(mesh, tmp_path)
        assert names == ["box_h0.obj"]
        lines = (tmp_path / names[0]).read_text(encoding="utf-8").splitlines()
        vertices = [line for line in lines if line.startswith("v ")]
        faces = [line for line in lines if line.startswith("f ")]
        assert len(vertices) == len(mesh.hulls[0].vertices)
        assert len(faces) == len(mesh.hulls[0].faces)
        # The box is 20 mm across, so its vertices sit at ±10 mm, which must appear as 0.01 m and not
        # as 10 or 0.01 mm. A file written in millimetres is the classic way a mesh arrives 1000x too
        # big.
        coordinates = [float(v) for line in vertices for v in line.split()[1:]]
        assert max(abs(c) for c in coordinates) == pytest.approx(0.01, rel=1e-3)

    def test_writing_a_single_hull_creates_its_directory(self, tmp_path) -> None:
        hull = Hull(vertices=[(0.0, 0.0, 0.0)], faces=[(0, 0, 0)], volume_m3=0.0)
        target = write_obj(hull, tmp_path / "nested" / "h.obj")
        assert target.exists()


@pytest.mark.mujoco
class TestMuJoCo:
    def test_collision_hulls_load_in_mujoco_with_zero_warnings(self, tmp_path) -> None:
        """The acceptance gate, measured through MuJoCo's own warning channel rather than claimed."""
        from ai_cad.compiler.collision import load_in_mujoco

        mesh = collision_mesh(l_shape_part())
        body = mjcf_body(mesh, tmp_path, body_name="lshape")
        model, warnings = load_in_mujoco(body, tmp_path)
        assert warnings == []
        assert model.ngeom == mesh.hull_count
        assert model.nbody == 2  # world + body
        # MuJoCo derives mass from the mesh volume and a density; it must be finite and positive.
        assert model.body_mass.sum() > 0.0
        assert np.all(np.isfinite(model.geom_pos))
